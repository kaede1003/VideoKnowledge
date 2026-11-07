"""Persistent, bounded stdio bridge to this project's isolated Qwen interpreter."""
from __future__ import annotations
import base64
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid

from .asr_profiles import ALIGNER_DIR
from .qwen_protocol import ASRBackendError, MAX_LINE, build_segments


class JsonWorker:
    def __init__(self, command, *, cwd, load_timeout=300., request_timeout=180.):
        self.command=list(command); self.cwd=str(cwd)
        self.load_timeout=load_timeout; self.request_timeout=request_timeout
        self._proc=None; self._queue=None; self._lock=threading.Lock()
        self._lifecycle=threading.Lock(); self._closed=False
        self.status={'phase':'not_loaded','error':'','loaded':False}

    def _terminate(self, proc):
        if proc is None:return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=3)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=3)
        except OSError:pass
        for stream in (proc.stdin,proc.stdout):
            try:
                if stream: stream.close()
            except (OSError,ValueError):pass

    def close(self):
        # Does not wait for the request lock: shutdown interrupts this worker,
        # not all Python or other applications' GPU processes.
        with self._lifecycle:
            self._closed=True;proc=self._proc;self._proc=None
        self._terminate(proc)
        self.status.update(phase='closed',loaded=False)

    def _read(self, proc, messages, deadline):
        while time.monotonic()<deadline:
            if self._closed: raise ASRBackendError('ASR_WORKER_CLOSED')
            try: data=messages.get(timeout=min(.2,max(.001,deadline-time.monotonic())))
            except queue.Empty:
                if proc.poll() is not None:raise ASRBackendError('ASR_WORKER_EXITED')
                continue
            if isinstance(data,Exception):raise data
            if not isinstance(data,dict):raise ASRBackendError('ASR_WORKER_PROTOCOL')
            return data
        raise ASRBackendError('ASR_WORKER_TIMEOUT','cached audio is not committed or discarded')

    def _ensure(self):
        if self._closed:raise ASRBackendError('ASR_WORKER_CLOSED')
        if self._proc and self._proc.poll() is None:return self._proc,self._queue
        if self._proc: self._terminate(self._proc)
        self.status.update(phase='loading',loaded=False,error='')
        options={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1')
        with self._lifecycle:
            if self._closed:raise ASRBackendError('ASR_WORKER_CLOSED')
            proc=subprocess.Popen(self.command,cwd=self.cwd,env=env,stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,stderr=None,bufsize=0,**options)
            messages=queue.Queue(maxsize=4)
            self._proc,self._queue=proc,messages
        def receiver():
            try:
                while True:
                    line=proc.stdout.readline(MAX_LINE+1)
                    if not line:raise ASRBackendError('ASR_WORKER_EXITED')
                    if len(line)>MAX_LINE or not line.endswith(b'\n'):
                        raise ASRBackendError('ASR_WORKER_PROTOCOL')
                    try:obj=json.loads(line)
                    except (ValueError,UnicodeDecodeError) as exc:
                        raise ASRBackendError('ASR_WORKER_PROTOCOL') from exc
                    messages.put_nowait(obj)
            except Exception as exc:
                try:messages.put_nowait(exc)
                except queue.Full:pass
        threading.Thread(target=receiver,daemon=True,name='vkn-qwen-reader').start()
        hello=self._read(proc,messages,time.monotonic()+self.load_timeout)
        if hello.get('type')!='ready' or hello.get('protocol')!=1:
            raise ASRBackendError(hello.get('code','ASR_WORKER_HANDSHAKE'))
        self.status.update(phase='ready',loaded=True,device=hello.get('device'),dtype=hello.get('dtype'),
                           load_seconds=hello.get('load_seconds'))
        return proc,messages

    def call(self,payload):
        with self._lock:
            proc=None
            try:
                proc,messages=self._ensure()
                request_id=uuid.uuid4().hex
                raw=(json.dumps({**payload,'id':request_id},ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')
                if len(raw)>MAX_LINE:raise ASRBackendError('ASR_BAD_AUDIO')
                self.status.update(phase='recognizing')
                deadline=time.monotonic()+self.request_timeout
                sent=queue.Queue(maxsize=1)
                def write():
                    try:
                        view=memoryview(raw)
                        while view:
                            written=proc.stdin.write(view)
                            if not written:raise BrokenPipeError('worker pipe closed')
                            view=view[written:]
                        proc.stdin.flush();sent.put(None)
                    except Exception as exc:sent.put(exc)
                threading.Thread(target=write,daemon=True,name='vkn-qwen-writer').start()
                while True:
                    if self._closed:raise ASRBackendError('ASR_WORKER_CLOSED')
                    remaining=deadline-time.monotonic()
                    if remaining<=0:raise ASRBackendError('ASR_WORKER_TIMEOUT')
                    try:error=sent.get(timeout=min(.2,remaining));break
                    except queue.Empty:continue
                if error:raise ASRBackendError('ASR_WORKER_WRITE_FAILED') from error
                result=self._read(proc,messages,deadline)
                if result.get('id')!=request_id:raise ASRBackendError('ASR_WORKER_RESPONSE_ID')
                if result.get('ok') is not True:raise ASRBackendError(result.get('code','ASR_WORKER_FAILED'))
                self.status.update(phase='ready',error='',last_audio_seconds=result.get('audio_seconds'),
                    last_recognition_seconds=result.get('recognition_seconds'),last_rtf=result.get('rtf'),
                    last_alignment=result.get('alignment'))
                return result
            except Exception as exc:
                self.status.update(phase='error',loaded=False,error=getattr(exc,'code',type(exc).__name__))
                # _ensure can fail before the local proc assignment.
                failed=proc or self._proc
                self._terminate(failed)
                with self._lifecycle:
                    if self._proc is failed:self._proc=None
                raise


class QwenEngine:
    backend_name='qwen3-native'
    def __init__(self,cfg,*,root,bridge=None):
        self.profile_name=cfg['profile'];self.model_name=cfg['model']
        self.device=cfg['device'];self.compute_type=cfg['compute'];self.root=Path(root)
        exe=self.root/'.venv-qwen'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        self.command=[str(exe),'-u','-m','server.qwen_worker',
            '--model-dir',str(self.root/cfg['model_dir']),
            '--aligner-dir',str(self.root/ALIGNER_DIR),'--device',self.device]
        self.bridge=bridge or JsonWorker(self.command,cwd=self.root)
        self._announced=False

    @property
    def loaded(self):
        if isinstance(self.bridge,JsonWorker) and self.bridge._proc is not None and self.bridge._proc.poll() is not None:
            self.bridge.status.update(loaded=False,phase='exited',error='ASR_WORKER_EXITED')
        return bool(self.bridge.status.get('loaded'))

    def snapshot(self):
        _=self.loaded
        return {'backend':self.backend_name,'profile':self.profile_name,
                'configured_model':self.model_name,'status':dict(self.bridge.status),
                'mode':'windowed_local','accuracy_tested':False}

    def close(self):self.bridge.close()

    def transcribe_job(self,job):
        if not job.packets:return []
        if isinstance(self.bridge,JsonWorker) and not Path(self.command[0]).is_file():
            raise ASRBackendError('ASR_RUNTIME_MISSING','run INSTALL_ALL.bat -Profile asr -AsrProfile qwen17')
        data={'op':'transcribe','pcm16':base64.b64encode(job.pcm).decode('ascii'),
              'owner_start':job.owner_start,'owner_end':job.owner_end,
              'language':job.options.get('language','auto'),
              'hotwords':str(job.options.get('hotwords',''))[:600]}
        # Original language only; translation remains a separate downstream step.
        reply=self.bridge.call(data)
        if not self._announced:
            print('[VKN] Qwen ASR active: '+self.model_name+' on '+self.device+'; original-language transcription.',flush=True)
            self._announced=True
        return build_segments(job,reply,self.model_name,self.device)
