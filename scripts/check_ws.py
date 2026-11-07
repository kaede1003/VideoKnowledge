"""Check both HTTP health and a real WebSocket handshake on loopback.

No microphone, browser permission, or Whisper model download is necessary.
"""
import asyncio
import json
import sys
from urllib.error import URLError
from urllib.request import urlopen

HOST = '127.0.0.1'
PORT = 8765


async def check_socket():
    import websockets

    url = f'ws://{HOST}:{PORT}/asr'
    origin = 'chrome-extension://' + 'a' * 32
    async with websockets.connect(url, origin=origin, open_timeout=4, close_timeout=2) as socket:
        ready = json.loads(await asyncio.wait_for(socket.recv(), timeout=5))
        if ready.get('type') != 'ready' or ready.get('protocol') != 5:
            raise RuntimeError('Wrong protocol: restart the updated v0.6 service')
        await socket.send('ping')
        pong = json.loads(await asyncio.wait_for(socket.recv(), timeout=5))
        if pong.get('type') != 'pong':
            raise RuntimeError('WebSocket ping did not receive pong')


def main():
    try:
        with urlopen(f'http://{HOST}:{PORT}/health', timeout=4) as response:
            info = json.load(response)
        if info.get('service') != 'vkn-asr' or info.get('ok') is not True:
            raise RuntimeError('Wrong process is responding on port 8765')
        if info.get('ws_transport_available') is False:
            raise RuntimeError('The current server has no WebSocket transport library')
        if info.get('active_ws_session') is True:
            print('[OK] HTTP health passed. ASR WebSocket is already in use by a tab.')
            return 0
        asyncio.run(check_socket())
        print('[OK] HTTP health passed; WebSocket handshake and ping/pong passed.')
        return 0
    except ModuleNotFoundError as exc:
        print(f'[ERROR] Missing Python module: {exc.name}. Run START_LOCAL_ASR.bat to repair.')
        return 1
    except Exception as exc:
        # Keep errors readable on Windows regardless of the console code page.
        print(f'[ERROR] ASR diagnostics failed: {type(exc).__name__}: {exc}')
        print('[HELP] Run STOP_LOCAL_ASR.bat and then START_LOCAL_ASR.bat.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
