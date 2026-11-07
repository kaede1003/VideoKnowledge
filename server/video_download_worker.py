"""One cancellable download job. Uses yt-dlp's public Python API, no browser cookies."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import sys
import time
from .video_cache import normalize_video_url, ID_RE, MAX_BYTES, MEDIA_EXTS


def emit(kind, **fields):
    print(json.dumps({'kind': kind, **fields}, ensure_ascii=True), flush=True)


def error_code(exc):
    text = str(exc).lower()
    if 'video_live' in text: return 'VIDEO_LIVE'
    if 'video_size' in text or 'larger than max-filesize' in text: return 'VIDEO_SIZE'
    if 'ffmpeg' in text: return 'VIDEO_FFMPEG'
    if 'javascript runtime' in text or 'js runtime' in text: return 'VIDEO_RUNTIME'
    return 'VIDEO_SOURCE_UNAVAILABLE'


def download(spec, factory=None):
    if factory is None:
        from yt_dlp import YoutubeDL
        factory = YoutubeDL
    url = normalize_video_url(spec.get('url'))
    directory = Path(spec['directory']).resolve()
    if not ID_RE.fullmatch(directory.name) or (directory / '.vkn-owned').read_text('ascii') != directory.name:
        raise ValueError('VIDEO_OUTPUT: invalid managed directory')
    limit = min(MAX_BYTES, max(1024, int(spec.get('max_bytes', MAX_BYTES))))
    has_ffmpeg = bool(shutil.which('ffmpeg'))
    last = [0.0]

    def progress(item):
        if item.get('status') == 'finished':
            emit('processing'); return
        size = int(item.get('downloaded_bytes') or 0)
        if size > limit:
            raise ValueError('VIDEO_SIZE')
        if time.monotonic() - last[0] >= 1:
            last[0] = time.monotonic()
            emit('progress', downloaded=size, total=int(item.get('total_bytes') or item.get('total_bytes_estimate') or 0))

    def allowed(info, *, incomplete=False):
        if info.get('is_live') or info.get('live_status') in {'is_live', 'is_upcoming', 'post_live'}:
            raise ValueError('VIDEO_LIVE')
        if info.get('has_drm') or info.get('availability') in {'premium_only', 'subscriber_only', 'needs_auth', 'private'}:
            raise ValueError('VIDEO_SOURCE_UNAVAILABLE')
        return None

    class Quiet:
        def debug(self, msg): pass
        def info(self, msg): pass
        def warning(self, msg): pass
        def error(self, msg): pass

    # With ffmpeg prefer H.264/AAC MP4; then other <=720p formats. Without it,
    # only a format already containing both audio and video is acceptable.
    fmt = ('bv[height<=720][ext=mp4][vcodec^=avc1]+ba[ext=m4a]/b[height<=720][ext=mp4]/'
           'bv[height<=720]+ba/b[height<=720]') if has_ffmpeg else 'b[height<=720][vcodec!=none][acodec!=none]'
    runtimes = {}
    for name in ('deno', 'node'):
        location = shutil.which(name)
        if location:
            runtimes[name] = {'path': location}
    opts = {'format': fmt, 'outtmpl': str(directory / 'media.%(ext)s'),
            'noplaylist': True, 'playlist_items': '1', 'max_downloads': 1,
            'quiet': True, 'no_warnings': True, 'logger': Quiet(), 'progress_hooks': [progress],
            'match_filter': allowed, 'socket_timeout': 20, 'retries': 2, 'fragment_retries': 2,
            'concurrent_fragment_downloads': 1, 'continuedl': False, 'overwrites': False,
            'max_filesize': limit, 'cachedir': False, 'cookiefile': None,
            'cookiesfrombrowser': None, 'usenetrc': False, 'writeinfojson': False,
            'writethumbnail': False, 'writesubtitles': False, 'writeautomaticsub': False,
            'skip_unavailable_fragments': False, 'allow_unplayable_formats': False,
            'js_runtimes': runtimes, 'remote_components': set(),
            'merge_output_format': 'mp4/mkv', 'restrictfilenames': True}
    with factory(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if not info or info.get('_type') in {'playlist', 'multi_video'}:
            raise ValueError('VIDEO_OUTPUT: individual video required')
    files = [p for p in directory.iterdir() if p.stem == 'media' and p.suffix in MEDIA_EXTS and p.is_file() and not p.is_symlink()]
    if len(files) != 1 or files[0].stat().st_size <= 0:
        raise ValueError('VIDEO_OUTPUT')
    if files[0].stat().st_size > limit:
        raise ValueError('VIDEO_SIZE')
    emit('ready', filename=files[0].name)


def main():
    try:
        raw = sys.stdin.buffer.readline(16385)
        if len(raw) > 16384: raise ValueError('VIDEO_OUTPUT')
        download(json.loads(raw))
        return 0
    except ImportError:
        emit('error', code='VIDEO_DEPENDENCY')
    except Exception as exc:
        emit('error', code=error_code(exc))
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
