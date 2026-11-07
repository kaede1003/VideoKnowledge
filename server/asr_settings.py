"""Explicit next-start ASR selection; never changes an in-flight recording.

The extension may select Ollama or restore Whisper, but the native Qwen/torch
profiles require the separate installer verification. No model is downloaded.
"""
from __future__ import annotations
import asyncio
from pathlib import Path
import re

from fastapi import HTTPException, Request
from .asr_profiles import ROOT, resolve_profile
from .ollama_asr import OllamaASRClient, DEFAULT_MODEL, validate_model


def profile_status(root=ROOT, engine=None):
    cfg = resolve_profile(root)
    return {'next_profile':cfg['profile'], 'next_model':cfg['model'],
            'active_profile':getattr(engine,'profile_name',cfg['profile']),
            'active_model':getattr(engine,'model_name',cfg['model']),
            'restart_required':cfg['profile'] != getattr(engine,'profile_name',cfg['profile']) or cfg['model'] != getattr(engine,'model_name',cfg['model']),
            'supports': ['legacy','ollama17'],
            'native_qwen_setup':'Use INSTALL_ALL.bat -Profile asr -AsrProfile qwen17'}


def select_for_next_start(root, payload, *, client_factory=OllamaASRClient):
    if not isinstance(payload,dict):raise ValueError('ASR_PROFILE_INVALID')
    name = payload.get('profile')
    if name not in ('legacy','ollama17'):
        raise ValueError('ASR_PROFILE_UNSUPPORTED: select via INSTALL_ALL for native Qwen')
    if name=='ollama17':
        model=validate_model(payload.get('model') or DEFAULT_MODEL)
        client=client_factory(model)
        report=client.smoke_test()
    else:
        model=None;report={'profile':'legacy','note':'existing Whisper engine selected','accuracy_tested':False}
    from scripts.setup_asr_profile import activate
    activate(root,name,report,model=model)
    return {'selected':name,'model':model,'applies':'next_service_start', 'model_test':report}



# Chromium extension pages may omit Origin on a host-permitted localhost fetch.
# Keep explicit, non-simple X-VKN-Extension-ID on both GET and POST so a normal
# website cannot call the local configuration endpoint without a CORS preflight.
# This is a browser-origin boundary; it is not an authentication mechanism
# against malicious native programs already running on the same computer.
EXTENSION_ID = re.compile(r'^[a-p]{32}$')


def ensure_asr_extension_request(request: Request):
    origin = request.headers.get('origin', '')
    ext_id = request.headers.get('x-vkn-extension-id', '')
    if ext_id and not EXTENSION_ID.fullmatch(ext_id):
        raise HTTPException(403, 'ASR_EXTENSION_ID_INVALID')
    if origin:
        if not re.fullmatch(r'chrome-extension://[a-p]{32}', origin):
            raise HTTPException(403, 'ASR_ORIGIN_DENIED')
        if ext_id and origin != 'chrome-extension://' + ext_id:
            raise HTTPException(403, 'ASR_ORIGIN_ID_MISMATCH')
        return
    if not ext_id:
        raise HTTPException(403, 'ASR_EXTENSION_HEADER_REQUIRED')

def attach_asr_settings(app, *, engine):

    @app.get('/asr/config')
    async def read_asr_config(request: Request):
        ensure_asr_extension_request(request)
        info = profile_status(engine=engine)
        try:
            names = await asyncio.to_thread(OllamaASRClient().list_models)
            info['installed_ollama_asr_models'] = [n for n in names if 'qwen3-asr' in n.lower()]
            info['ollama_reachable'] = True
        except Exception:
            info['installed_ollama_asr_models'] = []
            info['ollama_reachable'] = False
        return info

    @app.post('/asr/config')
    async def write_asr_config(request: Request):
        ensure_asr_extension_request(request)
        if int(request.headers.get('content-length','0') or 0)>1024:
            raise HTTPException(413,'ASR config too large')
        try:
            body=await request.json()
            result=await asyncio.to_thread(select_for_next_start,ROOT,body)
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc
        except Exception as exc:
            code=getattr(exc,'code','ASR_CONFIG_FAILED')
            # Never echo audio, credentials or full model output to the browser.
            raise HTTPException(503,code) from exc
        return {**result,**profile_status(engine=engine)}
