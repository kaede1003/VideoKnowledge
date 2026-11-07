"""Real localhost Uvicorn/WebSocket/SQLite check using silence, NOT model quality.
Run manually: python tests/real_transport_v080.py. Uses port 8765 only when free.
"""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener, ProxyHandler

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server.stream_protocol import Packet


def health():
    with build_opener(ProxyHandler({})).open('http://127.0.0.1:8765/health',timeout=2) as r:
        return json.load(r)


async def checks():
    import websockets
    url='ws://127.0.0.1:8765/asr';origin='chrome-extension://'+'a'*32;sid='9'*32
    async def next_kind(ws,kind):
        for _ in range(50):
            item=json.loads(await asyncio.wait_for(ws.recv(),3))
            if item['type']==kind:return item
        raise AssertionError(kind)
    async def hello(ws,last=0):
        ready=await next_kind(ws,'ready');assert ready['version']=='0.8.0'
        await ws.send(json.dumps({'type':'hello','sessionId':sid,'videoKey':'synthetic:transport-only','lastEvent':last,
                                 'options':{'translate':False,'diarize':False}}))
        return await next_kind(ws,'hello')
    async with websockets.connect(url,origin=origin) as ws:
        await hello(ws)
        async with websockets.connect(url,origin=origin) as second:
            await next_kind(second,'ready')
            await second.send(json.dumps({'type':'hello','sessionId':sid,'videoKey':'synthetic:transport-only','options':{}}))
            rejected=await next_kind(second,'error')
            assert rejected['retryable'] and not rejected['fatal']
        await ws.send('ping');assert (await next_kind(ws,'pong'))['type']=='pong'
        raw=Packet(1,0,.2,0,b'\x00\x00'*3200).encode()
        await ws.send(raw);assert (await next_kind(ws,'ack'))['seq']==1
        await ws.send(raw);assert (await next_kind(ws,'ack'))['seq']==1
        await ws.send(Packet(2,.2,.2,2,b'').encode());assert (await next_kind(ws,'ack'))['seq']==2
        await next_kind(ws,'done')
    await asyncio.sleep(.1)
    async with websockets.connect(url,origin=origin) as ws:
        h=await hello(ws);assert h['received']==2 and h['finished']
    return ['real_http_health','real_websocket_hello_ping','duplicate_connection_retryable',
            'durable_silence_ack_and_duplicate','finish_and_reconnect_replay']


def main():
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',8765))==0:
            print('SKIP: port is occupied; no other process is touched.');return 2
    out=ROOT/'artifacts';out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        env=dict(os.environ,VKN_CACHE_DIR=str(Path(tmp)/'asr'),VKN_VIDEO_CACHE_DIR=str(Path(tmp)/'video'),PYTHONUTF8='1')
        output=(out/'launcher-transport-test.log').open('wb')
        proc=subprocess.Popen([sys.executable,'scripts/run_local_service.py'],cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT)
        child=None
        try:
            for _ in range(60):
                if proc.poll() is not None:raise RuntimeError('launcher exited before ready')
                try:
                    info=health();child=info['process_id'];break
                except Exception:time.sleep(.1)
            else:raise RuntimeError('service did not become ready')
            result=asyncio.run(checks())
            # Also execute the user-facing diagnostic against the live service.
            diag=subprocess.run([sys.executable,'scripts/diagnose_local_service.py'],cwd=ROOT,capture_output=True,timeout=15)
            assert diag.returncode==0,diag.stderr.decode('utf-8','replace')
            assert not health()['loaded'], 'This test must not load Whisper'
            result+=['user_diagnostic_health_and_ws','no_whisper_weights_loaded']
        finally:
            if child:
                # Verified PID returned by the private server started above.
                os.kill(child,signal.SIGINT)
            try:proc.wait(timeout=15)
            except subprocess.TimeoutExpired:proc.terminate();proc.wait(timeout=5)
            output.close()
        assert proc.returncode==0
        state=json.loads((ROOT/'diagnostics/local-service-state.json').read_text())
        assert state['exit_code']==0
        report={'created_utc':datetime.now(timezone.utc).isoformat(),'passed':result+['owned_child_exit_code_logged'],
                'scope':'Linux real transport + SQLite with synthetic silence. No Windows, website, speech/role, download or model-quality claim.'}
        (out/'native-transport-v080.json').write_text(json.dumps(report,indent=2)+'\n')
        print('PASS',len(report['passed']),'real local transport/launcher checks; no models loaded')
    return 0

if __name__=='__main__':raise SystemExit(main())
