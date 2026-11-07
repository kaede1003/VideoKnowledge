"""V0.5 loopback-only durable streaming ASR + optional local translation."""
from __future__ import annotations
from contextlib import asynccontextmanager
import importlib.util
import os
import time
import uuid
from pathlib import Path
import re
from fastapi import FastAPI, WebSocket, Request
import httpx
from .recognition import StreamingWhisperEngine
from .stream_store import StreamStore
from .stream_service import StreamManager
from .lora_service import attach_lora_routes
from .speaker import availability as speaker_availability
from .video_cache import CacheStore, CacheManager, default_cache_dir, attach_video_cache_routes, availability as video_availability

from .caption_review import attach_caption_routes
from .context_review import attach_context_review_routes, availability as review_availability

ENGINE=StreamingWhisperEngine()
MANAGER=None
BOOT_ID=uuid.uuid4().hex
STARTED_AT=time.monotonic()
EXTENSION_ORIGIN=re.compile(r'^chrome-extension://[a-p]{32}$')

def cache_path():
    base=os.getenv('VKN_CACHE_DIR')
    if not base:
        base=str(Path(os.getenv('LOCALAPPDATA',str(Path.home()/'.cache')))/'VideoKnowledge'/'asr-cache')
    return Path(base)/'stream.sqlite3'

@asynccontextmanager
async def lifespan(app):
    global MANAGER
    store=StreamStore(cache_path(),max_bytes=int(os.getenv('VKN_CACHE_MB','256'))*1024*1024)
    store.clean()
    MANAGER=StreamManager(store,ENGINE)
    MANAGER.start()
    video_store=CacheStore(default_cache_dir())
    app.state.video_cache=CacheManager(video_store)
    app.state.video_cache.start()
    try:
        yield
    finally:
        await app.state.video_cache.stop()
        video_store.close()
        app.state.video_cache=None
        await MANAGER.stop()
        store.close()
        MANAGER=None

app=FastAPI(title='Video Knowledge Local ASR',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)

@app.get('/health')
async def health():
    return {'ok':True,'service':'vkn-asr','version':'0.10.0','protocol':5,
            'process_id':os.getpid(),'boot_id':BOOT_ID,'uptime_seconds':round(time.monotonic()-STARTED_AT,1),
            'runtime':MANAGER.snapshot() if MANAGER else {'stopping':True},
            'model':ENGINE.model_name,'device':ENGINE.device,'compute':ENGINE.compute_type,
            'caption_review':{'available':True,'mode':'local_visual_and_visible','model':'qwen2.5vl:3b'},'quality_guard':'0.7.1', 'chunk_seconds_default':12, 'loaded':ENGINE.loaded,'mode':'LOCAL_ONLY','cache':str(cache_path()),
            'ws_transport_available':importlib.util.find_spec('websockets') is not None,
            'active_ws_session':bool(MANAGER and MANAGER.connections),
            'speaker_diarization':speaker_availability(), 'video_cache':video_availability(), 'context_review':review_availability()}

@app.websocket('/asr')
async def asr_websocket(ws:WebSocket):
    if not EXTENSION_ORIGIN.fullmatch(ws.headers.get('origin','')):
        await ws.close(code=1008,reason='Only local Edge extension is allowed');return
    await ws.accept()
    await MANAGER.serve(ws)

attach_lora_routes(app)
attach_video_cache_routes(app)
attach_context_review_routes(app)
attach_caption_routes(app)


@app.post('/diagnostics')
async def diagnostics(request: Request):
    from .lora_service import ensure_origin
    ensure_origin(request)
    result = {'asr': await health(), 'ollama': {'ok':False,'models':[],'running':[]}}
    try:
        async with httpx.AsyncClient(timeout=5,trust_env=False,follow_redirects=False) as client:
            tags=await client.get('http://127.0.0.1:11434/api/tags');tags.raise_for_status()
            result['ollama']['models']=[str(x.get('name','')) for x in tags.json().get('models',[])]
            result['ollama']['ok']=True
            try:
                ps=await client.get('http://127.0.0.1:11434/api/ps');ps.raise_for_status()
                result['ollama']['running']=[{'name':x.get('name'), 'size_vram':x.get('size_vram',0)}
                    for x in ps.json().get('models',[])]
            except httpx.HTTPError:pass
    except Exception as exc:
        result['ollama']['error']='Ollama 未就绪：'+type(exc).__name__
    return result
