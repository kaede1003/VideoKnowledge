"""Loopback health + real WebSocket transport probe; no model or audio upload."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import sys
import time
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]


def get_health():
    with build_opener(ProxyHandler({})).open('http://127.0.0.1:8765/health', timeout=4) as response:
        raw = response.read(128 * 1024 + 1)
        if len(raw) > 128 * 1024:
            raise ValueError('health response too large')
        data = json.loads(raw)
    if data.get('service') != 'vkn-asr':
        raise ValueError('unexpected service on port 8765')
    # Deliberately omit cache paths, names of video content and any secrets.
    fields = ('ok', 'service', 'version', 'protocol', 'loaded', 'device', 'compute',
              'model', 'process_id', 'boot_id', 'uptime_seconds', 'runtime', 'ws_transport_available')
    return {key: data[key] for key in fields if key in data}


async def websocket_check():
    import websockets
    async with websockets.connect('ws://127.0.0.1:8765/asr',
                                   origin='chrome-extension://' + 'a' * 32,
                                   open_timeout=5, close_timeout=2) as ws:
        ready = json.loads(await asyncio.wait_for(ws.recv(), 5))
        if ready.get('protocol') != 5:
            raise ValueError('protocol mismatch')
        await ws.send('ping')
        pong = json.loads(await asyncio.wait_for(ws.recv(), 5))
        if pong.get('type') != 'pong':
            raise ValueError('missing application pong')
    return {'ok': True, 'scope': 'transport only; no model inference'}


def collect():
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'health': {}, 'websocket': {},
              'meaning': 'A failed transport probe does not prove a Python process crash.'}
    started = time.monotonic()
    try:
        report['health'] = get_health()
    except Exception as exc:
        report['health'] = {'ok': False, 'error_type': type(exc).__name__}
    report['health_seconds'] = round(time.monotonic() - started, 3)
    try:
        report['websocket'] = asyncio.run(websocket_check())
    except Exception as exc:
        report['websocket'] = {'ok': False, 'error_type': type(exc).__name__}
    state = ROOT / 'diagnostics' / 'local-service-state.json'
    if state.is_file():
        try:
            value = json.loads(state.read_text(encoding='utf-8'))
            report['last_launcher_state'] = {k: value[k] for k in (
                'state', 'started_utc', 'ended_utc', 'process_id', 'exit_code',
                'exit_code_hex', 'log_file') if k in value}
            report['launcher_state_notice'] = 'Last saved state; running may be stale after an unclean launcher exit.'
        except (ValueError, OSError):
            report['launcher_state_notice'] = 'unreadable'
    return report


def main():
    report = collect()
    out = ROOT / 'diagnostics'
    out.mkdir(exist_ok=True)
    path = out / ('connection-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))
    print('[INFO] Report: ' + str(path))
    return 0 if report['health'].get('ok') and report['websocket'].get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
