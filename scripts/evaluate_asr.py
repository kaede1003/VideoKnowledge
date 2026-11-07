"""Local comparison on <=5min authorized 16kHz mono PCM16 WAV; no LLM or upload.

Report in ignored diagnostics/asr-eval/ includes raw recognized text. A reference
is optional; no accuracy score is invented without one. Uses real ordered windows.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
import unicodedata
import wave
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from server.asr_profiles import create_engine,PROFILES
from server.qwen_engine import QwenEngine
from server.recognition import StreamingWhisperEngine
from server.stream_store import StreamStore
from server.stream_protocol import Packet,RATE,AUDIO,FINISH
from server.speaker import SpeakerAnnotator


def edit_distance(a,b):
    previous=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        current=[i]
        for j,y in enumerate(b,1):
            current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(x!=y)))
        previous=current
    return previous[-1]


def normalized(s):
    return ''.join(c.casefold() for c in unicodedata.normalize('NFC',s)
                   if unicodedata.category(c)[0] not in {'P','Z','C'} and not c.isspace())


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('audio',type=Path)
    p.add_argument('--engine',choices=['current','legacy',*PROFILES],default='current')
    p.add_argument('--reference',type=Path)
    p.add_argument('--language',default='auto',choices=['auto','zh','en','es','pt','fr','de','ja','ko','it','ru','ar','hi'])
    a=p.parse_args(argv)
    with wave.open(str(a.audio),'rb') as f:
        if (f.getnchannels(),f.getsampwidth(),f.getframerate(),f.getcomptype())!=(1,2,RATE,'NONE'):
            p.error('Use a 16kHz, mono PCM16 WAV; no automatic download or cloud conversion.')
        if f.getnframes()>300*RATE:p.error('Use an authorized sample of at most 5 minutes.')
        pcm=f.readframes(f.getnframes())
    if not pcm:p.error('WAV contains no samples.')
    if a.engine=='current':engine=create_engine()
    elif a.engine in ('qwen17','qwen06'):
        engine=QwenEngine({'profile':a.engine,**PROFILES[a.engine]},root=ROOT)
    else:
        engine=StreamingWhisperEngine()
        if a.engine in PROFILES:
            cfg=PROFILES[a.engine];engine.model_name=cfg['model'];engine.device=cfg['device'];engine.compute_type=cfg['compute']
    rows=[];sid='b'*32;began=time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='vkn-asr-eval-') as d:
            store=StreamStore(Path(d)/'audio.sqlite3',min_free=0)
            try:
                store.open(sid,'local-evaluation',{'language':a.language,'translate':False,'correct':False,'diarize':False,'chunkSeconds':12})
                size=RATE*2;sequence=0
                for offset in range(0,len(pcm),size):
                    block=pcm[offset:offset+size];sequence+=1
                    store.receive(sid,Packet(sequence,offset/(RATE*2),(offset+len(block))/(RATE*2),AUDIO,block))
                duration=len(pcm)/(RATE*2)
                store.receive(sid,Packet(sequence+1,duration,duration,FINISH,b''))
                while not store.session(sid)['finished']:
                    j=store.next_job(sid)
                    if j is None:raise RuntimeError('Evaluation stalled before completing ordered input')
                    result=engine.transcribe_job(j) if j.packets else []
                    visible=[SpeakerAnnotator.strip_private(x) for x in result]
                    rows.extend(visible);store.commit(j,visible)
                transport=store.stats(sid)
            finally:store.close()
    finally:
        if hasattr(engine,'close'):engine.close()
    elapsed=time.monotonic()-began
    hypothesis='\n'.join(x['text'] for x in rows)
    report={'engine':getattr(engine,'backend_name','faster-whisper'),'model':engine.model_name,
            'device':engine.device,'duration_seconds':duration,'seconds_including_load':elapsed,
            'rtf_including_load':elapsed/duration,'segments':rows,'hypothesis':hypothesis,
            'ordered_audio_status':transport,'score_note':'No reference supplied; accuracy not measured.'}
    if a.reference:
        reference=a.reference.read_text(encoding='utf-8-sig')
        ref=normalized(reference);hyp=normalized(hypothesis)
        if not ref or len(ref)>10000 or len(hyp)>10000:p.error('Use 1..10000 normalized reference characters and <=10000 hypothesis characters.')
        report['cer']=edit_distance(ref,hyp)/len(ref)
        report['score_note']='CER ignores case, whitespace and punctuation; manual reference quality not verified.'
    out=ROOT/'diagnostics'/'asr-eval';out.mkdir(parents=True,exist_ok=True)
    path=out/(time.strftime('%Y%m%d-%H%M%S')+'-'+a.engine+'.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('[REPORT] '+str(path));print('[NOTE] Contains raw hypothesis; review before sharing. No audio/text uploaded.');return 0

if __name__=='__main__':raise SystemExit(main())
