"""Bounded local Ollama downloads and network diagnostics for the installer.

No private-redirect/TLS bypasses, credential reads, third-party mirrors, model
cache deletion, or changes to the user's proxy/DNS settings. Only /api/pull on
an explicitly validated loopback service causes model downloads.
"""
from __future__ import annotations

from dataclasses import dataclass
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import threading
import time
from urllib.parse import urlsplit

INSTALLER_VERSION = '0.8.4'
BLOB_HOST = 'dd20bb891979d25aebc8bec07b2b3bbc.r2.cloudflarestorage.com'
PROBE_HOSTS = ('registry.ollama.ai', 'ollama.com', BLOB_HOST)
MODEL_NAMES = {'text': 'qwen2.5:3b', 'vision': 'qwen2.5vl:3b',
               'asr': 'frozenlab/qwen3-asr:1.7b'}
# Auto-download only these reviewed ASR tags. Other explicitly configured tags
# can still be used when already installed; the installer won't pull unknown publishers.
OLLAMA_ASR_DOWNLOADABLE = frozenset({MODEL_NAMES['asr'], 'frozenlab/qwen3-asr:0.6b'})
_MODEL_TAG = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$')


def validate_asr_tag(tag: str) -> str:
    """Validate a local model name without importing ASR runtime dependencies."""
    if not isinstance(tag, str) or not _MODEL_TAG.fullmatch(tag) or '://' in tag or '..' in tag:
        raise InstallFailure('Invalid Ollama ASR model tag', code='MODEL_NAME', retryable=False)
    return tag



def redact(value: object) -> str:
    """Keep hostnames useful for diagnosis; strip signed URLs and credentials."""
    text = str(value)
    # Also remove terminal escape/control sequences from subprocess output.
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    text = ''.join(c for c in text if c in '\n\r\t' or ord(c) >= 32)
    def safe_url(match):
        try:
            p = urlsplit(match.group(0))
            host = p.hostname or '[host]'
            port = ':' + str(p.port) if p.port else ''
            return p.scheme + '://' + host + port + '/[path-query-redacted]'
        except ValueError:
            return '[URL REDACTED]'
    text = re.sub(r'https?://[^\s\"\'<>]+', safe_url, text, flags=re.I)
    text = re.sub(r'(?i)(X-Amz-[\w-]+|authorization|api[_-]?key|password|access_token|token)\s*[=:]\s*[^\s&,;]+',
                  r'\1=[REDACTED]', text)
    return text


def local_address(base: str) -> tuple[str, int]:
    p = urlsplit(base)
    if (p.scheme != 'http' or p.hostname not in {'127.0.0.1', 'localhost', '::1'}
            or p.username or p.password or p.query or p.fragment or p.path not in {'', '/'}):
        raise ValueError('Only a loopback Ollama URL without credentials or path is supported.')
    # Pin localhost to loopback; never resolve it through a system proxy or DNS.
    return ('127.0.0.1' if p.hostname == 'localhost' else p.hostname, p.port or 11434)


def ip_kind(value: str) -> str:
    try:
        ip = ipaddress.ip_address(value.split('%', 1)[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network('198.18.0.0/15'):
            return 'benchmark-or-fake-ip'
        if not ip.is_global or ip.is_multicast:
            return 'non-public'
        return 'public'
    except ValueError:
        return 'invalid'


def dns_probe(host: str, timeout: float = 5.0, resolver=socket.getaddrinfo) -> dict:
    """Read-only system resolution. A bounded daemon worker handles DNS stalls."""
    result: dict = {'host': host, 'addresses': [], 'status': 'lookup-timeout'}
    done = threading.Event()
    def work():
        try:
            values = sorted({row[4][0] for row in resolver(host, 443, type=socket.SOCK_STREAM)})
            result['addresses'] = [{'ip': ip, 'kind': ip_kind(ip)} for ip in values]
            result['status'] = ('non-public' if any(ip_kind(ip) != 'public' for ip in values)
                                else 'public' if values else 'no-address')
        except OSError as exc:
            result['status'] = 'lookup-failed'
            result['error'] = redact(exc)[:600]
        finally:
            done.set()
    threading.Thread(target=work, daemon=True).start()
    if not done.wait(timeout):
        return {'host': host, 'status': 'lookup-timeout', 'addresses': []}
    return result


@dataclass(frozen=True)
class Failure:
    code: str
    retryable: bool
    hint: str


def classify_failure(message: str, status: int | None = None) -> Failure:
    s = message.lower()
    if 'redirect target not allowed' in s or 'resolves to non-public' in s:
        return Failure('DNS_NON_PUBLIC', False,
                       '下载域名被解析到非公网地址。修复代理 Fake-IP/DNS 后再运行；不要关闭 Ollama 的地址校验。')
    if any(x in s for x in ('digest mismatch', 'checksum mismatch', '-partial-', 'sha256 mismatch')):
        return Failure('CACHE_INTEGRITY', False,
                       'Ollama 报告分片或摘要不一致。保留缓存和日志；不要自动清空所有模型。')
    if any(x in s for x in ('no space left', 'disk full', 'not enough space', '磁盘空间不足')):
        return Failure('DISK_SPACE', False, '模型所在磁盘空间不足；安装器不会删除已有模型腾空间。')
    if any(x in s for x in ('certificate', 'x509:', 'ssl:', 'tlsv1_alert')):
        return Failure('TLS_CERTIFICATE', False, '检查系统时间与受信任证书；不使用跳过 TLS 校验。')
    if status == 412 or 'requires a newer version' in s:
        return Failure('OLLAMA_VERSION', False, '模型需要较新 Ollama；通过官方应用更新，不降级绕过校验。')
    if status in {401, 403} or 'unauthorized' in s or 'forbidden' in s:
        return Failure('ACCESS_DENIED', False, '访问被拒绝；检查服务/网络策略。本机公开模型不需要 API Key。')
    if status == 404 or 'manifest does not exist' in s or 'model not found' in s:
        return Failure('MODEL_NOT_FOUND', False, '模型名或服务路径不存在；不会自动替换为不明镜像。')
    if status == 429:
        return Failure('RATE_LIMIT', True, '远端限流；进行有上限的退避重试。')
    if status and status >= 500:
        return Failure('REMOTE_TEMPORARY', True, '服务暂时不可用；进行有上限的退避重试。')
    if any(x in s for x in ('timeout', 'timed out', 'stall', 'connection', 'eof', 'reset', 'unreachable', 'name resolution', 'no such host')):
        return Failure('NETWORK_TEMPORARY', True, '连接超时或中断；尝试复用 Ollama 已有下载缓存后重试。')
    return Failure('DOWNLOAD_FAILED', False, '下载失败。保留具体错误；请查看安装报告。')


class InstallFailure(RuntimeError):
    def __init__(self, message: str, *, code: str | None = None, retryable: bool | None = None,
                 status: int | None = None):
        f = classify_failure(message, status)
        self.code = code or f.code
        self.retryable = f.retryable if retryable is None else retryable
        self.hint = f.hint
        self.detail = redact(message)[:1800]
        super().__init__(self.code + ': ' + self.detail)


def stop_connection(conn: http.client.HTTPConnection, captured_socket=None) -> None:
    # Closing only this request socket never kills Ollama or another application's job.
    sock = captured_socket or conn.sock
    if sock:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
    conn.close()


class OllamaClient:
    def __init__(self, base: str = 'http://127.0.0.1:11434', *, connect_timeout: float = 10):
        self.host, self.port = local_address(base)
        self.connect_timeout = connect_timeout

    def request_json(self, method: str, path: str, payload=None, timeout: float = 15):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=self.connect_timeout)
        active_socket = [None]
        timer = threading.Timer(timeout, lambda: stop_connection(conn, active_socket[0]))
        timer.daemon = True
        timer.start()
        try:
            conn.connect()
            active_socket[0] = conn.sock
            conn.sock.settimeout(timeout)
            conn.request(method, path, body=(json.dumps(payload).encode('utf-8') if payload is not None else None),
                         headers={'Content-Type': 'application/json', 'Connection': 'close'})
            response = conn.getresponse()
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise InstallFailure('Oversized service response', code='PROTOCOL', retryable=False)
            if response.status >= 300:
                raise InstallFailure(raw.decode('utf-8', 'replace') or f'HTTP {response.status}', status=response.status)
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError('JSON object required')
            if result.get('error'):
                raise InstallFailure(str(result['error']))
            return result
        except InstallFailure:
            raise
        except (OSError, http.client.HTTPException, ValueError) as exc:
            raise InstallFailure(str(exc), code='LOCAL_SERVICE', retryable=True) from exc
        finally:
            timer.cancel()
            stop_connection(conn, active_socket[0])

    def models(self) -> set[str]:
        data = self.request_json('GET', '/api/tags')
        rows = data.get('models')
        if not isinstance(rows, list):
            raise InstallFailure('Invalid /api/tags response', code='PROTOCOL', retryable=False)
        return {str(row.get('name', row.get('model', ''))) for row in rows if isinstance(row, dict)}

    def model_present(self, model: str) -> bool:
        names = self.models()
        aliases = {model, model + ':latest' if ':' not in model else model}
        return bool(names & aliases)

    def verify_model(self, model: str) -> dict:
        if not self.model_present(model):
            raise InstallFailure('Pull finished but model is absent from /api/tags', code='VERIFY_FAILED', retryable=False)
        result = self.request_json('POST', '/api/show', {'model': model}, timeout=30)
        return {'model': model, 'metadata_readable': True, 'inference_tested': False,
                'capabilities': result.get('capabilities', [])}

    def pull_once(self, model: str, *, idle_timeout: float = 180, stall_timeout: float = 600,
                  total_timeout: float = 14400, progress=lambda data: None):
        if model not in MODEL_NAMES.values() and model not in OLLAMA_ASR_DOWNLOADABLE:
            raise InstallFailure('Only this project\'s named local models are accepted', code='MODEL_SCOPE', retryable=False)
        if min(idle_timeout, stall_timeout, total_timeout) <= 0:
            raise ValueError('Timeouts must be positive')
        conn = http.client.HTTPConnection(self.host, self.port, timeout=self.connect_timeout)
        timed_out = threading.Event()
        active_socket = [None]
        def deadline():
            timed_out.set()
            stop_connection(conn, active_socket[0])
        timer = threading.Timer(total_timeout, deadline)
        timer.daemon = True
        timer.start()
        start = time.monotonic()
        last_advance = start
        phase = None
        byte_high_water: dict[str, int] = {}
        try:
            conn.connect()
            active_socket[0] = conn.sock
            conn.sock.settimeout(idle_timeout)
            conn.request('POST', '/api/pull', body=json.dumps({'model': model, 'stream': True}).encode('utf-8'),
                         headers={'Content-Type': 'application/json', 'Connection': 'close'})
            response = conn.getresponse()
            if response.status != 200:
                raise InstallFailure(response.read(65536).decode('utf-8', 'replace'), status=response.status)
            while True:
                raw = response.readline(65537)
                now = time.monotonic()
                if timed_out.is_set() or now - start >= total_timeout:
                    raise InstallFailure('Per-model absolute download timeout reached', code='DOWNLOAD_DEADLINE', retryable=True)
                if not raw:
                    raise InstallFailure('EOF before Ollama reported success', code='INCOMPLETE_STREAM', retryable=True)
                if len(raw) > 65536:
                    raise InstallFailure('Download progress line too large', code='PROTOCOL', retryable=False)
                if not raw.strip():
                    if now - last_advance >= stall_timeout:
                        raise InstallFailure('Download progress stalled', code='DOWNLOAD_STALLED', retryable=True)
                    continue
                try:
                    event = json.loads(raw)
                    if not isinstance(event, dict):
                        raise ValueError('progress object required')
                except (ValueError, UnicodeError) as exc:
                    raise InstallFailure('Invalid progress JSON', code='PROTOCOL', retryable=False) from exc
                if event.get('error'):
                    raise InstallFailure(str(event['error']))
                status = str(event.get('status', ''))[:200]
                digest = str(event.get('digest', ''))[:200]
                count = event.get('completed', 0)
                total = event.get('total', 0)
                if not isinstance(count, int) or not isinstance(total, int) or count < 0 or total < 0:
                    raise InstallFailure('Invalid progress counters', code='PROTOCOL', retryable=False)
                # A stream of unchanged heartbeat/progress objects does NOT reset the stall clock.
                if status != phase or count > byte_high_water.get(digest, -1):
                    last_advance = now
                phase = status
                byte_high_water[digest] = max(count, byte_high_water.get(digest, 0))
                progress({'status': redact(status), 'digest': digest,
                          'completed': count, 'total': total, 'elapsed': round(now - start, 2)})
                if status == 'success':
                    return {'model': model, 'seconds': round(now - start, 2), 'stream_success': True}
                if now - last_advance >= stall_timeout:
                    raise InstallFailure('Download progress stalled', code='DOWNLOAD_STALLED', retryable=True)
        except InstallFailure:
            raise
        except (OSError, http.client.HTTPException) as exc:
            if timed_out.is_set():
                raise InstallFailure('Per-model absolute download timeout reached', code='DOWNLOAD_DEADLINE', retryable=True) from exc
            raise InstallFailure(str(exc), code='NETWORK_TEMPORARY', retryable=True) from exc
        finally:
            timer.cancel()
            stop_connection(conn, active_socket[0])


def ensure_model(client: OllamaClient, model: str, *, attempts: int = 3, progress=lambda data: None,
                 notify=lambda text: None, sleep=time.sleep, **limits) -> dict:
    """Sequential pulls. Resume belongs to Ollama, not an invented mirror downloader."""
    if attempts < 1 or attempts > 6:
        raise ValueError('attempts must be 1..6')
    if client.model_present(model):
        notify('[SKIP] ' + model + ' already installed; checking local metadata.')
        return dict(client.verify_model(model), state='already_present', attempts=0)
    for attempt in range(1, attempts + 1):
        notify(f'[DOWNLOAD] {model} ({attempt}/{attempts})')
        try:
            result = client.pull_once(model, progress=progress, **limits)
            result.update(client.verify_model(model))
            return dict(result, state='installed', attempts=attempt)
        except InstallFailure as exc:
            notify(f'[{exc.code}] {exc.detail}')
            notify(exc.hint)
            if not exc.retryable or attempt == attempts:
                raise
            # A late success may have registered the model after the socket closed.
            try:
                if client.model_present(model):
                    return dict(client.verify_model(model), state='installed', attempts=attempt)
            except InstallFailure:
                pass  # A temporarily unavailable local daemon must not swallow the retry.
            delay = min(60, 5 * (3 ** (attempt - 1)))
            notify(f'[RETRY] Retrying in {delay}s; keeping Ollama cache. No service restart.')
            sleep(delay)
    raise AssertionError('unreachable')


def write_json_atomic(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


class InstallerLock:
    """Advisory lock released on process exit, without stale PID-file lockouts."""
    def __init__(self, path: Path):
        self.path, self.file = path, None
    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open('a+b')
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b'0'); self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close(); self.file = None
            raise InstallFailure('Another installer is running for this project', code='INSTALL_BUSY', retryable=False) from exc
        return self
    def __exit__(self, *exc):
        if self.file:
            if os.name == 'nt':
                import msvcrt
                self.file.seek(0); msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            self.file.close(); self.file = None
