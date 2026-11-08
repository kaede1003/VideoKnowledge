"""Durable ASR workers and supervised WebSocket delivery (protocol VKN5).

A transport failure is not proof of a process crash.  Only committed audio is
acknowledged.  A transient cache refusal closes the transport without acknowledging
in-flight packets, so they are replayed in order from the browser outbox.
"""
from __future__ import annotations
import asyncio
from contextlib import suppress
import json
import logging
import sqlite3
import time
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect
from .stream_store import StreamStore, normalize_options
from .stream_protocol import decode
from .text_enrichment import LocalTextEnricher
from .speaker import SpeakerAnnotator

LOG = logging.getLogger('vkn.stream')


class StreamManager:
    def __init__(self, store: StreamStore, engine, enricher=None):
        self.store = store
        self.engine = engine
        self.enricher = enricher or LocalTextEnricher()
        self.speakers = SpeakerAnnotator()
        self.tasks = []
        self.wake = asyncio.Event()
        self.connections = set()
        self.owners = {}
        self.stopping = False
        self.worker_state = {}
        self.last_disconnect = None
        self.worker_retry_seconds = 1.0
        self.heartbeat_seconds = 65.0

    def mark(self, name, phase, **fields):
        self.worker_state.setdefault(name, {'restarts': 0, 'error': ''}).update(
            phase=phase, changed_at=time.time(), **fields)

    def snapshot(self):
        # No audio, transcript, URL, voice vector, token or API key in this data.
        return {'workers': {k: dict(v) for k, v in self.worker_state.items()},
                'speaker_backend': self.speakers.snapshot(),
                'active_connections': len(self.connections),
                'last_disconnect': self.last_disconnect,
                'stopping': self.stopping}

    def start(self):
        if self.tasks:
            return
        self.stopping = False
        self.tasks = [asyncio.create_task(self.supervise(name, worker), name='vkn-' + name)
                      for name, worker in (('asr', self.asr_worker), ('text', self.text_worker))]

    async def supervise(self, name, worker):
        while not self.stopping:
            self.mark(name, 'starting')
            try:
                await worker()
                if not self.stopping:
                    raise RuntimeError('worker returned unexpectedly')
            except asyncio.CancelledError:
                self.mark(name, 'stopped')
                raise
            except Exception as exc:
                old = self.worker_state[name]
                self.mark(name, 'retrying', error=type(exc).__name__, restarts=old['restarts'] + 1)
                LOG.exception('Worker %s stopped; durable work retained, retry scheduled', name)
                await asyncio.sleep(self.worker_retry_seconds)

    async def stop(self):
        self.stopping = True
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        # A to_thread call cannot be cancelled directly. The optional sherpa
        # native library therefore runs in its own child process; terminate it
        # on shutdown so a stuck/crashed diarizer cannot outlive this service.
        self.speakers.close()

    def transcribe_and_label(self, job):
        return self.speakers.transcribe_and_annotate(job, self.engine)

    async def asr_worker(self):
        while True:
            progressed = False
            self.mark('asr', 'waiting')
            for sid in self.store.pending_sessions():
                try:
                    job = self.store.next_job(sid)
                    if not job:
                        continue
                    self.mark('asr', 'recognizing', error='')
                    started = time.monotonic()
                    segments = await asyncio.to_thread(self.transcribe_and_label, job) if job.packets else []
                    self.store.commit(job, segments)
                    self.mark('asr', 'waiting', last_success=time.time(),
                              last_job_seconds=round(time.monotonic() - started, 3), error='')
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    code = getattr(exc, 'code', type(exc).__name__)
                    self.mark('asr', 'job_failed', error=code)
                    # One warning per failure, not repeated full tracebacks
                    # for known upstream Ollama errors. The local error code and
                    # server.log carry the diagnosis; do not log raw audio.
                    if code in ('ASR_OLLAMA_SERVER_ERROR','ASR_OLLAMA_HTTP'):
                        LOG.warning('Ollama ASR job failed; audio retained: %s', str(exc)[:240])
                    else:
                        LOG.exception('ASR job retained for retry')
                    # No failed call advances the audio cursor or changes engine.
                    hints = {'ASR_OLLAMA_UNAVAILABLE':'本地Ollama不可连接，原音仍在缓存中，检查11434端口',
                             'ASR_OLLAMA_SERVER_ERROR':'Ollama模型推理HTTP 5xx；检查Ollama server.log中的真实原因',
                             'ASR_OLLAMA_MODEL_MISSING':'未找到已安装的Ollama语音模型，请检查ollama list',
                             'ASR_OLLAMA_TIMEOUT':'本地Ollama识别超时，缓存未删除，检查GPU资源',
                             'ASR_OLLAMA_UNSUPPORTED':'Ollama版本不支持此模型的音频接口',
                             'ASR_OLLAMA_BAD_RESPONSE':'语音模型返回格式异常，原音保留',
                             'ASR_RUNTIME_MISSING':'Qwen环境未安装；运行 INSTALL_ALL.bat -Profile asr -AsrProfile qwen17',
                             'ASR_CUDA_UNAVAILABLE':'Qwen CUDA不可用；原音保留，不自动回退CPU或旧模型',
                             'ASR_OUTPUT_TRUNCATED':'模型输出到达上限，原音保留；请尝试较短识别窗口',
                             'ASR_WORKER_TIMEOUT':'Qwen识别等待超时，原音保留；检查本机资源负载'}
                    # After two consecutive 5xx errors on the same durable
                    # session, back off for 15 minutes; the existing “retry”
                    # control explicitly clears retry_at after Ollama is fixed.
                    prior=self.store.session(sid) or {}
                    cool_down=(code in ('ASR_OLLAMA_SERVER_ERROR','ASR_OLLAMA_HTTP')
                               and prior.get('attempts',0)>=1)
                    detail=str(exc)[:190] if code=='ASR_OLLAMA_SERVER_ERROR' else ''
                    message=code + ': ' + hints.get(code,'local recognition failed; see service log')
                    if detail: message += ' (' + detail + ')'
                    self.store.fail(sid, message, cool_down=cool_down)
                progressed = True
            if not progressed:
                self.wake.clear()
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self.wake.wait(), .25)
            else:
                await asyncio.sleep(0)

    async def text_worker(self):
        while True:
            self.mark('text', 'waiting')
            row = self.store.next_text()
            if not row:
                await asyncio.sleep(.3)
                continue
            try:
                self.mark('text', 'processing', error='')
                value = await self.enricher.process(row, self.store.text_context(row))
                self.store.finish_text(row, value)
                self.mark('text', 'waiting', last_success=time.time(), error='')
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.mark('text', 'job_failed', error=type(exc).__name__)
                LOG.exception('Text processing failed; original transcript retained')
                value = dict(row['item'])
                msg = type(exc).__name__
                value['textError'] = '本地纠错/翻译暂不可用，原文已保存。请检查Ollama文本模型。' + msg
                if value.get('translationStatus') == 'pending':
                    value['translationStatus'] = 'failed'
                if value.get('correctionStatus') == 'pending':
                    value['correctionStatus'] = 'failed'
                self.store.finish_text(row, value, failure=msg)

    async def serve(self, ws: WebSocket):
        sid = None
        tasks = []
        owner = None
        send_lock = asyncio.Lock()
        close_code, close_cause = 1000, 'client_closed'

        async def send(obj):
            async with send_lock:
                await asyncio.wait_for(ws.send_json(obj), 15)

        async def close(code, reason):
            with suppress(Exception):
                await asyncio.wait_for(ws.close(code=code, reason=reason), 2)

        async def transient(cause, message, code=1013):
            nonlocal close_code, close_cause
            close_code, close_cause = code, cause
            data = {'type': 'backpressure', 'code': cause, 'message': message,
                    'fatal': False, 'retryable': True}
            with suppress(Exception):
                data['received'] = self.store.session(sid)['received']
            await send(data)
            await close(code, cause)

        try:
            await send({'type': 'ready', 'protocol': 5, 'version': '0.12.1'})
            while sid is None:
                event = await asyncio.wait_for(ws.receive(), 12)
                if event['type'] == 'websocket.disconnect':
                    close_code = event.get('code', 1000)
                    return
                text = event.get('text', '')
                if text == 'ping':
                    await send({'type': 'pong'})
                    continue
                data = json.loads(text)
                if not isinstance(data, dict) or data.get('type') != 'hello':
                    raise ValueError('需要hello消息建立会话')
                candidate = str(data.get('sessionId', ''))
                previous = self.owners.get(candidate)
                if previous and time.monotonic() - previous['seen'] <= self.heartbeat_seconds:
                    # A short network flap can overlap with the old socket's
                    # close handshake. Never mark this as corrupted audio.
                    close_code, close_cause = 1013, 'SESSION_BUSY'
                    await send({'type': 'error', 'code': 'SESSION_BUSY', 'fatal': False,
                                'retryable': True, 'message': '旧连接尚未释放，保留缓存后自动重试'})
                    await close(1013, 'SESSION_BUSY')
                    return
                if previous:
                    with suppress(Exception):
                        await asyncio.wait_for(previous['ws'].close(code=1012, reason='stale session'), 1)
                self.store.open(candidate, str(data.get('videoKey', '')), data.get('options', {}))
                owner = {'ws': ws, 'seen': time.monotonic()}
                sid = candidate
                self.owners[sid] = owner
                self.connections.add(sid)
                cursor = max(0, int(data.get('lastEvent', 0)))
                await send({'type': 'hello', 'sessionId': sid, **self.store.stats(sid)})

            async def sender():
                nonlocal cursor
                last_status = 0.0
                while self.owners.get(sid) is owner:
                    for out in self.store.events(sid, cursor):
                        await send(out)
                        cursor = out['eventId']
                    if time.monotonic() - last_status >= 1:
                        await send({'type': 'progress', **self.store.stats(sid)})
                        last_status = time.monotonic()
                    await asyncio.sleep(.15)

            async def receiver():
                nonlocal close_code, close_cause
                while self.owners.get(sid) is owner:
                    event = await asyncio.wait_for(ws.receive(), self.heartbeat_seconds)
                    if event['type'] == 'websocket.disconnect':
                        close_code = event.get('code', 1000)
                        close_cause = 'client_closed'
                        return
                    owner['seen'] = time.monotonic()
                    try:
                        if event.get('bytes') is not None:
                            p = decode(event['bytes'])
                            ack = self.store.receive(sid, p)
                            await send({'type': 'ack', 'seq': ack})
                            self.wake.set()
                        elif event.get('text'):
                            text = event['text']
                            if text == 'ping':
                                await send({'type': 'pong'})
                            elif text == 'retry':
                                self.store.retry(sid)
                                self.wake.set()
                                await send({'type': 'retry_ack'})
                            elif text.startswith('{'):
                                msg = json.loads(text)
                                if not isinstance(msg, dict) or msg.get('type') != 'retry':
                                    raise ValueError('未知控制指令')
                                with self.store.db:
                                    self.store.db.execute('UPDATE sessions SET options=? WHERE id=?',
                                        (json.dumps(normalize_options(msg.get('options'))), sid))
                                self.store.retry(sid)
                                self.wake.set()
                                await send({'type': 'retry_ack'})
                            else:
                                raise ValueError('未知控制指令；暂停/结束必须作为有序包发送')
                    except (BufferError, OSError, sqlite3.OperationalError) as exc:
                        LOG.warning('Cache refusal: %s; socket closed for ordered replay', type(exc).__name__)
                        await transient('CACHE_BACKPRESSURE', '本地缓存暂时无法确认写入；未确认音频保留在浏览器，暂停视频并重试。')
                        # Crucial: don't read seq N+1 after rejecting seq N.
                        return
                    except (ValueError, OverflowError) as exc:
                        close_code, close_cause = 1008, 'PROTOCOL_ERROR'
                        await send({'type': 'error', 'code': close_cause, 'fatal': True, 'message': str(exc)[:240]})
                        await close(1008, close_cause)
                        return

            tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                task.result()  # Sender failure must close/reconnect, not silently stall.
        except asyncio.CancelledError:
            # The ASGI connection boundary may be cancelled during client close
            # or shutdown. No model worker/data is owned by this request. Release
            # its socket ownership below and finish without a false ASGI error.
            close_code, close_cause = 1012, 'connection_cancelled'
        except (WebSocketDisconnect, ConnectionError):
            close_code, close_cause = 1006, 'transport_closed'
        except asyncio.TimeoutError:
            close_code, close_cause = 1012, 'transport_timeout'
            await close(1012, close_cause)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            close_code, close_cause = 1008, 'HELLO_INVALID'
            with suppress(Exception):
                await send({'type': 'error', 'code': close_cause, 'fatal': True, 'message': str(exc)[:240]})
            await close(1008, close_cause)
        except Exception as exc:
            close_code, close_cause = 1011, type(exc).__name__
            LOG.exception('ASR transport failed; committed and unacknowledged audio retained')
            with suppress(Exception):
                await send({'type': 'error', 'code': 'SERVER_TRANSIENT', 'fatal': False,
                            'retryable': True, 'message': '本地传输发生异常，缓存保留，正在重新连接；详情见本地服务日志。'})
            await close(1011, 'SERVER_TRANSIENT')
        finally:
            for task in tasks:
                task.cancel()
            # Release synchronous ownership before the first await: a second
            # cancellation must not leave an apparently live session behind.
            if sid and self.owners.get(sid) is owner:
                self.owners.pop(sid, None)
                self.connections.discard(sid)
            if tasks:
                with suppress(asyncio.CancelledError):
                    await asyncio.gather(*tasks, return_exceptions=True)
            self.last_disconnect = {'time': time.time(), 'code': close_code, 'cause': close_cause}
            LOG.info('ASR transport ended: code=%s cause=%s', close_code, close_cause)
            # Never discard model work when a browser disconnects.
