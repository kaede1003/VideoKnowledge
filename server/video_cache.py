"""Explicit, owner-scoped public-video download cache with a 72-hour TTL.

Only this module's UUID directories are managed. Notebook/model/ASR files are
never deleted. This is NOT a DRM downloader and does not read browser cookies.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import sqlite3
import stat
import sys
import threading
import time
from urllib.parse import parse_qs, urlencode, urlparse
import uuid

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

TTL_SECONDS = 72 * 60 * 60
CLEAN_INTERVAL = 15 * 60
MAX_BYTES = 4 * 1024**3
TOTAL_BYTES = 20 * 1024**3
MIN_FREE = 1024**3
ACTIVE = {'queued', 'downloading', 'processing'}
ID_RE = re.compile(r'^[a-f0-9]{32}$')
ORIGIN_RE = re.compile(r'^chrome-extension://[a-p]{32}$')
MEDIA_EXTS = {'.mp4', '.webm', '.mkv'}


def default_cache_dir():
    return Path(os.getenv('VKN_VIDEO_CACHE_DIR') or
                str(Path(os.getenv('LOCALAPPDATA', str(Path.home() / '.cache'))) /
                    'VideoKnowledge' / 'video-cache')).expanduser()


def normalize_video_url(raw):
    """Allow individual YouTube/Bilibili videos, never arbitrary fetch targets."""
    if not isinstance(raw, str) or len(raw) > 2000:
        raise ValueError('VIDEO_URL: 视频链接无效')
    try:
        u = urlparse(raw)
        if u.scheme != 'https' or u.username or u.password or u.port not in (None, 443):
            raise ValueError()
        host = u.hostname or ''
        q = parse_qs(u.query)
        if host in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'}:
            if host == 'youtu.be':
                ident = u.path.strip('/')
            elif u.path == '/watch':
                ident = q.get('v', [''])[0]
            elif u.path.startswith('/shorts/'):
                ident = u.path.split('/')[2]
            else:
                raise ValueError()
            if not re.fullmatch(r'[A-Za-z0-9_-]{11}', ident):
                raise ValueError()
            return 'https://www.youtube.com/watch?' + urlencode({'v': ident})
        if host in {'www.bilibili.com', 'bilibili.com', 'm.bilibili.com'}:
            match = re.fullmatch(r'/video/(BV[A-Za-z0-9]{10}|av[0-9]{1,16})/?', u.path)
            if not match:
                raise ValueError()
            part = q.get('p', ['1'])[0]
            if not part.isdigit() or not 1 <= int(part) <= 1000:
                raise ValueError()
            return 'https://www.bilibili.com/video/' + match[1] + '/' + (
                '?' + urlencode({'p': int(part)}) if int(part) != 1 else '')
    except (ValueError, TypeError):
        pass
    raise ValueError('VIDEO_URL: 当前仅支持 YouTube / B站单个视频的 HTTPS 页面；不接受播放列表、直播、短链或任意文件地址')


def availability():
    installed = importlib.util.find_spec('yt_dlp') is not None
    return {'installed': installed, 'ffmpeg': bool(shutil.which('ffmpeg')),
            'javascript_runtime': 'deno' if shutil.which('deno') else 'node' if shutil.which('node') else '',
            'retention_hours': 72, 'max_video_bytes': MAX_BYTES, 'max_total_bytes': TOTAL_BYTES,
            'message': ('下载组件已安装；不代表目标网站一定允许下载' if installed else
                        '请运行 INSTALL_VIDEO_CACHE.bat 安装可选下载组件，然后重启本地服务')}


def _is_link(path):
    try:
        info = path.lstat()
        return path.is_symlink() or bool(getattr(info, 'st_file_attributes', 0) &
                                        getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))
    except FileNotFoundError:
        return False


class CacheStore:
    """SQLite metadata; reads don't refresh expiry; clock injectable for TTL tests."""
    def __init__(self, root, clock=time.time):
        self.root = Path(root).expanduser().absolute()
        self.root.mkdir(parents=True, exist_ok=True)
        if _is_link(self.root):
            raise ValueError('VIDEO_PATH: 缓存根目录不能是符号链接或目录联接')
        self.root = self.root.resolve()
        self.clock = clock
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / 'cache.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS videos(
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, url TEXT NOT NULL, title TEXT NOT NULL,
          state TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
          completed REAL, expires REAL NOT NULL, size INTEGER NOT NULL DEFAULT 0,
          progress REAL, filename TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '')''')
        self.db.commit()

    def close(self):
        self.db.close()

    def directory(self, ident):
        if not ID_RE.fullmatch(str(ident)):
            raise ValueError('VIDEO_ID: 无效缓存编号')
        path = self.root / ident
        if _is_link(path) or path.resolve().parent != self.root:
            raise ValueError('VIDEO_PATH: 缓存目录不安全，未读取或删除')
        return path

    def recover(self):
        with self.lock, self.db:
            self.db.execute("UPDATE videos SET state='interrupted',error=?,updated=? WHERE state IN ('queued','downloading','processing')",
                            ('VIDEO_INTERRUPTED: 服务重新启动，未把未完成文件当作可用视频；可重新下载', self.clock()))

    def create(self, owner, url, title):
        url = normalize_video_url(url)
        if not ORIGIN_RE.fullmatch(owner):
            raise ValueError('VIDEO_OWNER: 无效客户端来源')
        now = self.clock()
        with self.lock:
            old = self.db.execute("SELECT * FROM videos WHERE owner=? AND url=? AND expires>? AND state IN ('queued','downloading','processing','ready') ORDER BY created DESC LIMIT 1",
                                  (owner, url, now)).fetchone()
            if old:
                return dict(old), False
            if self.db.execute("SELECT count(*) FROM videos WHERE state IN ('queued','downloading','processing')").fetchone()[0] >= 8:
                raise ValueError('VIDEO_QUEUE_FULL: 缓存任务过多，请先等待或取消已有任务')
            ident = uuid.uuid4().hex
            folder = self.directory(ident)
            folder.mkdir(mode=0o700)
            (folder / '.vkn-owned').write_text(ident, encoding='ascii')
            with self.db:
                self.db.execute('''INSERT INTO videos(id,owner,url,title,state,created,updated,expires)
                                   VALUES(?,?,?,?,?,?,?,?)''',
                                (ident, owner, url, str(title or '视频')[:240], 'queued', now, now, now + TTL_SECONDS))
            return self.get(ident, owner), True

    def get(self, ident, owner=None):
        self.directory(ident)
        row = self.db.execute('SELECT * FROM videos WHERE id=?', (ident,)).fetchone()
        if row is None or (owner is not None and row['owner'] != owner):
            raise KeyError('VIDEO_NOT_FOUND: 本扩展没有此缓存')
        return dict(row)

    def list(self, owner):
        return [dict(row) for row in self.db.execute(
            'SELECT * FROM videos WHERE owner=? ORDER BY created DESC LIMIT 100', (owner,))]

    def update(self, ident, **fields):
        allowed = {'state', 'completed', 'expires', 'size', 'progress', 'filename', 'error'}
        if set(fields) - allowed:
            raise ValueError('Unexpected metadata field')
        fields['updated'] = self.clock()
        with self.lock, self.db:
            self.db.execute('UPDATE videos SET ' + ','.join(k + '=?' for k in fields) + ' WHERE id=?',
                            (*fields.values(), ident))

    def publish(self, ident, filename):
        if Path(filename).name != filename or not re.fullmatch(r'media\.(mp4|webm|mkv)', filename):
            raise ValueError('VIDEO_OUTPUT: 输出文件名不符合缓存约定')
        path = self.directory(ident) / filename
        if _is_link(path) or not path.is_file() or path.stat().st_size == 0:
            raise ValueError('VIDEO_OUTPUT: 没有完整视频文件')
        # Basic container signature, not a guarantee of whole-file integrity.
        with path.open('rb') as stream:
            signature = stream.read(16)
        if not (signature[:4] == b'\x1aE\xdf\xa3' or signature[4:8] == b'ftyp'):
            raise ValueError('VIDEO_OUTPUT: 返回内容不是支持的视频容器')
        now = self.clock()
        self.update(ident, state='ready', filename=filename, size=path.stat().st_size,
                    completed=now, expires=now + TTL_SECONDS, progress=1.0, error='')

    def media_path(self, ident):
        row = self.get(ident)
        if row['expires'] <= self.clock():
            raise ValueError('VIDEO_EXPIRED: 视频缓存已到期；笔记未删除')
        if row['state'] != 'ready':
            raise ValueError('VIDEO_NOT_READY: 视频尚未完成或已被取消')
        filename = row['filename']
        if not re.fullmatch(r'media\.(mp4|webm|mkv)', filename):
            raise ValueError('VIDEO_PATH: 缓存文件名无效')
        path = self.directory(ident) / filename
        if _is_link(path) or not path.is_file():
            raise ValueError('VIDEO_MISSING: 缓存文件不存在或不安全')
        return path

    def purge_files(self, ident):
        """Only delete a recorded UUID directory with our ownership marker."""
        path = self.directory(ident)
        if not path.exists():
            return
        marker = path / '.vkn-owned'
        if _is_link(marker) or not marker.is_file() or marker.read_text(encoding='ascii') != ident:
            raise ValueError('VIDEO_PATH: 所有权标记不符，未删除目录')
        # Refuse junctions/symlinks anywhere. Never follow arbitrary subdirectories.
        for base, dirs, files in os.walk(path, followlinks=False):
            for name in dirs + files:
                if _is_link(Path(base) / name):
                    raise ValueError('VIDEO_PATH: 目录含链接，未自动清理')
        shutil.rmtree(path)

    def delete(self, ident, owner):
        row = self.get(ident, owner)
        if row['state'] in ACTIVE:
            raise ValueError('VIDEO_BUSY: 先取消下载，确认任务停止后再删除')
        self.purge_files(ident)
        with self.lock, self.db:
            self.db.execute('DELETE FROM videos WHERE id=?', (ident,))

    def cleanup(self):
        removed, failed = 0, 0
        rows = self.db.execute("SELECT id FROM videos WHERE expires<=? AND state NOT IN ('queued','downloading','processing')", (self.clock(),)).fetchall()
        for row in rows:
            try:
                self.purge_files(row['id'])
                with self.lock, self.db:
                    self.db.execute('DELETE FROM videos WHERE id=?', (row['id'],))
                removed += 1
            except (OSError, ValueError):
                failed += 1
                self.update(row['id'], state='cleanup_failed', error='VIDEO_CLEANUP: 到期缓存被占用或目录不安全；已停止提供访问，稍后重试')
        return {'removed': removed, 'failed': failed}

    def usage(self):
        """Count only managed directories, including in-progress fragments."""
        total = 0
        for row in self.db.execute('SELECT id FROM videos'):
            folder = self.directory(row['id'])
            if not folder.exists():
                continue
            for base, dirs, files in os.walk(folder, followlinks=False):
                dirs[:] = [name for name in dirs if not _is_link(Path(base) / name)]
                for name in files:
                    path = Path(base) / name
                    if not _is_link(path):
                        with suppress(FileNotFoundError):
                            total += path.stat().st_size
        return total


def public_row(row):
    return {k: row[k] for k in ('id', 'url', 'title', 'state', 'created', 'updated',
                               'completed', 'expires', 'size', 'progress', 'error')}


def friendly_error(code):
    return {
        'VIDEO_DEPENDENCY': '请运行 INSTALL_VIDEO_CACHE.bat 安装下载组件，然后重启本地服务',
        'VIDEO_SOURCE_UNAVAILABLE': '来源拒绝下载、需要登录或没有可用格式；不会读取浏览器登录信息或绕过保护',
        'VIDEO_LIVE': '本版只缓存已发布的点播视频，不下载直播或预约视频',
        'VIDEO_SPACE': '磁盘空间不足或达到缓存容量限制；已有未到期视频保留',
        'VIDEO_SIZE': '本视频超过4 GiB限制，已停止并清除本轮未完成文件',
        'VIDEO_TIMEOUT': '下载超过本轮2小时上限；已停止，笔记保留',
        'VIDEO_OUTPUT': '下载没有生成完整且受支持的视频文件，未报告成功',
        'VIDEO_RUNTIME': 'YouTube解析需要本机JavaScript运行时；安装受支持的Node.js或Deno后重启服务',
        'VIDEO_FFMPEG': '目标视频需要合并音视频，请安装ffmpeg并加入PATH后重试',
        'VIDEO_WORKER': '本次下载失败；可以检查下载依赖及来源访问情况后重试',
    }.get(code, '本次视频缓存任务失败；未修改笔记或已有缓存')


async def terminate_owned(proc):
    """Terminate only this job's child process group, never global Python/Ollama."""
    if proc is None or proc.returncode is not None:
        return
    if os.name == 'nt':
        killer = await asyncio.create_subprocess_exec('taskkill', '/PID', str(proc.pid), '/T', '/F',
                   stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(killer.wait(), 5)
    else:
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
    try:
        await asyncio.wait_for(proc.wait(), 5)
    except asyncio.TimeoutError:
        if os.name != 'nt':
            with suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
        else:
            with suppress(ProcessLookupError):
                proc.kill()
        await proc.wait()


class CacheManager:
    def __init__(self, store, runner=None):
        self.store = store
        self.runner = runner or self._download
        self.tasks = {}
        self.processes = {}
        self.cancelled = set()
        self.semaphore = asyncio.Semaphore(1)
        self.janitor = None
        self.tokens = {}
        self.closing = False

    def start(self):
        self.store.recover()
        self.store.cleanup()
        self.janitor = asyncio.create_task(self._sweep())

    async def _sweep(self):
        while True:
            await asyncio.sleep(CLEAN_INTERVAL)
            self.store.cleanup()
            self.tokens = {k: v for k, v in self.tokens.items() if v['expires'] > time.time()}

    async def stop(self):
        self.closing = True
        if self.janitor:
            self.janitor.cancel()
            with suppress(asyncio.CancelledError):
                await self.janitor
        for ident in list(self.tasks):
            self.cancelled.add(ident)
        for proc in list(self.processes.values()):
            await terminate_owned(proc)
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)
        self.tokens.clear()

    async def create(self, owner, url, title='', consent=False):
        if consent is not True:
            raise ValueError('VIDEO_CONSENT: 请先确认你有权下载该视频，并同意72小时自动清理')
        if self.closing:
            raise ValueError('VIDEO_CLOSING: 服务正在退出')
        if self.runner == self._download and not availability()['installed']:
            raise ValueError('VIDEO_DEPENDENCY: ' + friendly_error('VIDEO_DEPENDENCY'))
        self.store.cleanup()
        if self.store.usage() >= TOTAL_BYTES or shutil.disk_usage(self.store.root).free < MIN_FREE:
            raise ValueError('VIDEO_SPACE: ' + friendly_error('VIDEO_SPACE'))
        row, new = self.store.create(owner, url, title)
        if new:
            task = asyncio.create_task(self._run(row['id']))
            self.tasks[row['id']] = task
            task.add_done_callback(lambda done, ident=row['id']: self.tasks.pop(ident, None))
        return public_row(row)

    async def _run(self, ident):
        try:
            async with self.semaphore:
                if ident in self.cancelled:
                    return
                self.store.update(ident, state='downloading', error='')
                row = self.store.get(ident)
                filename = await asyncio.wait_for(self.runner(row), 2 * 60 * 60)
                if ident in self.cancelled or self.closing:
                    return
                self.store.publish(ident, filename)
        except asyncio.CancelledError:
            self.cancelled.add(ident)
            raise
        except Exception as exc:
            code = 'VIDEO_TIMEOUT' if isinstance(exc, asyncio.TimeoutError) else str(exc).split(':', 1)[0]
            if code not in {'VIDEO_DEPENDENCY', 'VIDEO_SOURCE_UNAVAILABLE', 'VIDEO_LIVE', 'VIDEO_SPACE',
                            'VIDEO_SIZE', 'VIDEO_TIMEOUT', 'VIDEO_OUTPUT', 'VIDEO_RUNTIME', 'VIDEO_FFMPEG'}:
                code = 'VIDEO_WORKER'
            if ident not in self.cancelled:
                self.store.update(ident, state='failed', error=code + ': ' + friendly_error(code))
        finally:
            await terminate_owned(self.processes.pop(ident, None))
            if ident in self.cancelled or self.closing:
                self.store.update(ident, state='cancelled', error='VIDEO_CANCELLED: 已取消本次下载；听写和笔记不受影响')
            if self.store.get(ident)['state'] != 'ready':
                try:
                    self.store.purge_files(ident)
                except (OSError, ValueError):
                    # Don't claim removal when Windows still holds an open file.
                    self.store.update(ident, error='VIDEO_CLEANUP_PENDING: 下载已停止，残留临时文件待下一次清理；未删除其他数据')
            self.cancelled.discard(ident)

    async def _download(self, row):
        kwargs = {'cwd': str(Path(__file__).resolve().parents[1])}
        if os.name == 'nt':
            import subprocess
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        else:
            kwargs['start_new_session'] = True
        proc = await asyncio.create_subprocess_exec(sys.executable, '-u', '-m', 'server.video_download_worker',
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=65536, **kwargs)
        self.processes[row['id']] = proc
        spec = {'url': row['url'], 'directory': str(self.store.directory(row['id'])), 'max_bytes': MAX_BYTES}
        proc.stdin.write((json.dumps(spec) + '\n').encode('utf-8'))
        await proc.stdin.drain()
        proc.stdin.close()
        filename, error, counter = '', '', 0
        read_task = asyncio.create_task(proc.stdout.readline())
        try:
            while True:
                done, _ = await asyncio.wait({read_task}, timeout=2)
                if row['id'] in self.cancelled:
                    raise asyncio.CancelledError()
                if self.store.clock() >= row['expires']:
                    raise ValueError('VIDEO_TIMEOUT')
                counter += 1
                if counter % 3 == 0:
                    if self.store.usage() >= TOTAL_BYTES or shutil.disk_usage(self.store.root).free < MIN_FREE:
                        raise ValueError('VIDEO_SPACE')
                if not done:
                    continue
                line = read_task.result()
                if not line:
                    break
                read_task = asyncio.create_task(proc.stdout.readline())
                try:
                    item = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                kind = item.get('kind')
                if kind == 'progress':
                    size = max(0, int(item.get('downloaded', 0)))
                    if size > MAX_BYTES:
                        raise ValueError('VIDEO_SIZE')
                    total = max(0, int(item.get('total', 0)))
                    self.store.update(row['id'], size=size, progress=min(.99, size / total) if total else None)
                elif kind == 'processing':
                    self.store.update(row['id'], state='processing')
                elif kind == 'ready':
                    filename = str(item.get('filename', ''))
                elif kind == 'error':
                    error = str(item.get('code', 'VIDEO_WORKER'))
            rc = await proc.wait()
            if rc != 0 or not filename:
                raise ValueError(error or 'VIDEO_OUTPUT')
            return filename
        finally:
            if not read_task.done():
                read_task.cancel()
                with suppress(asyncio.CancelledError):
                    await read_task
            await terminate_owned(proc)

    async def cancel(self, ident, owner):
        row = self.store.get(ident, owner)
        if row['state'] not in ACTIVE:
            return public_row(row)
        self.cancelled.add(ident)
        task = self.tasks.get(ident)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        # A queued task can be cancelled before its coroutine executes.
        self.store.update(ident, state='cancelled', error='VIDEO_CANCELLED: 已取消本次下载')
        with suppress(OSError, ValueError):
            self.store.purge_files(ident)
        self.cancelled.discard(ident)
        return public_row(self.store.get(ident, owner))

    def file_token(self, ident, owner):
        row = self.store.get(ident, owner)
        self.store.media_path(ident)
        token = secrets.token_urlsafe(32)
        self.tokens[hashlib.sha256(token.encode()).hexdigest()] = {
            'id': ident, 'expires': min(time.time() + 60 * 60, row['expires'])}
        return token

    def verify_file_token(self, ident, token):
        item = self.tokens.get(hashlib.sha256(str(token).encode()).hexdigest(), {})
        if item.get('id') != ident or item.get('expires', 0) <= time.time():
            raise HTTPException(403, 'VIDEO_TOKEN: 缓存播放许可无效或已过期，请重新点击播放')
        try:
            return self.store.media_path(ident)
        except (KeyError, ValueError):
            raise HTTPException(410, 'VIDEO_EXPIRED: 缓存已到期或不存在')


class _RedactPlaybackToken(logging.Filter):
    def filter(self, record):
        # Uvicorn's access log args contain the raw request path. Never log tokens.
        if isinstance(record.args, tuple):
            record.args = tuple(re.sub(r'([?&]token=)[^&\s]+', r'\1[redacted]', arg)
                                if isinstance(arg, str) else arg for arg in record.args)
        return True


logging.getLogger('uvicorn.access').addFilter(_RedactPlaybackToken())


def attach_video_cache_routes(app):
    def manager():
        result = getattr(app.state, 'video_cache', None)
        if result is None:
            raise HTTPException(503, 'VIDEO_SERVICE: 视频缓存服务未就绪，请启动新版本地服务')
        return result

    def owner(request):
        origin = request.headers.get('origin', '')
        if not ORIGIN_RE.fullmatch(origin):
            raise HTTPException(403, 'VIDEO_ORIGIN: 仅允许本地扩展请求')
        # Origin + JSON POST prevent arbitrary web pages from invoking downloads.
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            raise HTTPException(415, 'VIDEO_JSON: 必须使用JSON请求')
        return origin

    async def body(request):
        raw = bytearray()
        async for part in request.stream():
            raw.extend(part)
            if len(raw) > 8192:
                raise HTTPException(413, 'VIDEO_BODY: 请求过大')
        try:
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, UnicodeError):
            raise HTTPException(400, 'VIDEO_JSON: 无效请求')

    @app.post('/media-cache/list')
    async def video_list(request: Request):
        who, m = owner(request), manager()
        return {'items': [public_row(r) for r in m.store.list(who)],
                'capabilities': availability(), 'directory': str(m.store.root),
                'retention_hours': 72}

    @app.post('/media-cache/create')
    async def video_create(request: Request):
        who, data = owner(request), await body(request)
        try:
            return await manager().create(who, data.get('url'), data.get('title', ''), data.get('consent', False))
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post('/media-cache/{ident}/cancel')
    async def video_cancel(ident: str, request: Request):
        who = owner(request)
        try:
            return await manager().cancel(ident, who)
        except KeyError:
            raise HTTPException(404, 'VIDEO_NOT_FOUND')
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post('/media-cache/{ident}/delete')
    async def video_delete(ident: str, request: Request):
        who = owner(request)
        try:
            manager().store.delete(ident, who)
            return {'deleted': True}
        except KeyError:
            raise HTTPException(404, 'VIDEO_NOT_FOUND')
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except OSError:
            raise HTTPException(409, 'VIDEO_BUSY: 文件正在使用，未删除；关闭本地播放后重试')

    @app.post('/media-cache/{ident}/play')
    async def video_play(ident: str, request: Request):
        who = owner(request)
        try:
            token = manager().file_token(ident, who)
            return {'url': f'http://127.0.0.1:8765/media-cache/file/{ident}?token={token}'}
        except KeyError:
            raise HTTPException(404, 'VIDEO_NOT_FOUND')
        except ValueError as exc:
            raise HTTPException(410, str(exc))

    @app.get('/media-cache/file/{ident}')
    async def video_file(ident: str, token: str = ''):
        path = manager().verify_file_token(ident, token)
        kind = 'video/mp4' if path.suffix == '.mp4' else 'video/webm' if path.suffix == '.webm' else 'video/x-matroska'
        return FileResponse(path, media_type=kind, headers={'Cache-Control': 'no-store',
            'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff',
            'Content-Security-Policy': "default-src 'none'; media-src 'self'; style-src 'unsafe-inline'"})
