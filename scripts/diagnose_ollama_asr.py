#!/usr/bin/env python3
"""Local-only Ollama Qwen3-ASR diagnostics. Does not download models or save audio.

Use --wav with a short (preferably 5-15s) real speech sample. The report
contains metadata/errors but never the speech, transcript or signed requests.
"""
from __future__ import annotations
import argparse
import base64
from datetime import datetime
import io
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, ProxyHandler, Request
import wave

BASE = 'http://127.0.0.1:11434'
MODEL = 'frozenlab/qwen3-asr:1.7b'


def error_kind(s):
    value = str(s or '').lower()
    if any(x in value for x in ('out of memory','insufficient memory','not enough memory')): return 'INSUFFICIENT_MEMORY'
    if any(x in value for x in ('mmproj','projector','qwen3a','unsupported architecture', 'unsupported audio')): return 'AUDIO_PROJECTOR'
    if any(x in value for x in ('runner has unexpectedly stopped','llama-server process has terminated','exit status')): return 'RUNNER_EXITED'
    if any(x in value for x in ('error loading model','unable to load model')): return 'MODEL_LOAD'
    if any(x in value for x in ('cuda error','cublas','driver')): return 'GPU_RUNTIME'
    return 'UNKNOWN_UPSTREAM_ERROR'


def get_json(opener, route, data=None, timeout=8):
    request = Request(BASE+route, data=json.dumps(data).encode('utf-8') if data is not None else None,
                      headers={'Content-Type':'application/json'}, method='POST' if data is not None else 'GET')
    try:
        with opener.open(request,timeout=timeout) as response:
            return response.status, json.loads(response.read(2_000_000).decode('utf-8'))
    except HTTPError as exc:
        raw=exc.read(20480)
        try: output=json.loads(raw.decode('utf-8'))
        except (ValueError,UnicodeDecodeError): output={}
        return exc.code, output


def check_wav(path):
    with wave.open(str(path),'rb') as w:
        if w.getnchannels()!=1 or w.getsampwidth()!=2 or w.getframerate()!=16000:
            raise ValueError('WAV must be mono, PCM16, 16000 Hz')
        duration=w.getnframes()/16000
        if not 1 <= duration <= 60:
            raise ValueError('WAV must be between 1 and 60 seconds')
    return path.read_bytes(), round(duration,2)


def diagnose(model, wav=None):
    opener=build_opener(ProxyHandler({}))  # localhost, never send through an HTTP proxy
    report={'checked_at':datetime.now().isoformat(timespec='seconds'), 'endpoint':'127.0.0.1:11434',
            'model':model, 'audio_tested':False}
    try:
        status,value=get_json(opener,'/api/version')
        report['ollama_version']=(value.get('version','') if status==200 and isinstance(value,dict) else 'unavailable')
        status,value=get_json(opener,'/api/tags')
        names=[r.get('name','') for r in value.get('models',[]) if isinstance(r,dict)] if status==200 else []
        report['model_installed']=model in names
        if not names:report['model_list_error']='API_HTTP_'+str(status)
        status,value=get_json(opener,'/api/ps')
        if status==200 and isinstance(value,dict):
            report['loaded_models']=[{'name':r.get('name'), 'size_vram':r.get('size_vram',0)}
                                     for r in value.get('models',[]) if isinstance(r,dict)]
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        report['error']='OLLAMA_UNREACHABLE: '+type(exc).__name__
        return report
    if wav is not None:
        payload_bytes,duration=check_wav(Path(wav))
        report['audio_seconds']=duration
        report['audio_tested']=True
        payload={'model':model,'stream':False,'messages':[{'role':'user','content':'',
                'images':[base64.b64encode(payload_bytes).decode('ascii')]}]}
        try:
            status,answer=get_json(opener,'/api/chat',payload,timeout=120)
            report['asr_http_status']=status
            if status==200:
                reply=(answer.get('message') or {}).get('content','') if isinstance(answer,dict) else ''
                report['asr_message_returned']=isinstance(reply,str)
                report['asr_text_marker_found']=isinstance(reply,str) and '<asr_text>' in reply
            else:
                upstream_error=answer.get('error','') if isinstance(answer,dict) else ''
                report['asr_error_category']=error_kind(upstream_error)
                # Do not save raw response; it may contain machine paths or private data.
        except (URLError,TimeoutError,OSError,ValueError) as exc:
            report['asr_error_category']='REQUEST_FAILED_'+type(exc).__name__
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',default=MODEL)
    p.add_argument('--wav',help='local 16k mono PCM16 WAV (audio never saved to report)')
    p.add_argument('--output',default=None,help='optional report .json path')
    args=p.parse_args(argv)
    report=diagnose(args.model,args.wav)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('Report:',path)
    return 1 if 'error' in report or (args.wav and report.get('asr_http_status') != 200) else 0

if __name__=='__main__':sys.exit(main())
