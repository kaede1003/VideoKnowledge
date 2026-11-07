"""Run only this project's Uvicorn child; tee bounded logs and retain its exit code.

No automatic crash/restart loop, no killing unrelated processes, no notebook read.
The first saved native traceback or model error is useful evidence, not a fix by
itself.  Ctrl+C is forwarded to the owned process; STOP_LOCAL_ASR remains supported.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
LOG_LIMIT = 5 * 1024 * 1024


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def command():
    return [sys.executable, '-X', 'faulthandler', '-u', '-m', 'uvicorn', 'server.app:app',
            '--host', '127.0.0.1', '--port', '8765', '--ws', 'websockets',
            '--ws-ping-interval', '20', '--ws-ping-timeout', '60',
            '--ws-per-message-deflate', 'false', '--no-access-log', '--log-level', 'info',
            '--log-config', str(ROOT / 'server' / 'logging.json')]


def exit_hex(code):
    return '0x' + format(int(code) & 0xffffffff, '08X')


def write_state(path, data):
    try:
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
        temporary.replace(path)
    except OSError as exc:
        print('[WARN] Could not save service status: ' + type(exc).__name__, flush=True)


def main():
    out = ROOT / 'diagnostics'
    out.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    log = out / ('local-service-' + stamp + '.log')
    status = out / 'local-service-state.json'
    state = {'started_utc': utc_now(), 'state': 'starting', 'log_file': log.name,
             'python_version': sys.version.split()[0], 'platform': sys.platform,
             'asr_model': os.getenv('VKN_ASR_MODEL', 'small'),
             'device': os.getenv('VKN_ASR_DEVICE', 'cpu'),
             'compute': os.getenv('VKN_ASR_COMPUTE', 'int8')}
    write_state(status, state)
    print('[INFO] Service diagnostics: ' + str(out), flush=True)
    print('[INFO] Log: ' + log.name + ' (bounded; may include local paths in errors)', flush=True)
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1', PYTHONFAULTHANDLER='1')
    kwargs = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
    proc = subprocess.Popen(command(), cwd=ROOT, env=env, stdin=None,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
    state.update(state='running', process_id=proc.pid)
    write_state(status, state)

    def copy_output():
        size = 0
        target = log.open('ab')
        try:
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                try:
                    print(line.decode('utf-8', errors='replace').rstrip('\r\n'), flush=True)
                except (OSError, UnicodeError):
                    pass
                try:
                    if size + len(line) > LOG_LIMIT:
                        target.close()
                        backup = log.with_suffix('.previous.log')
                        if backup.exists():
                            backup.unlink()
                        log.replace(backup)
                        target = log.open('ab')
                        size = 0
                    target.write(line)
                    target.flush()
                    size += len(line)
                except OSError:
                    # Disk failure must not terminate the actual ASR process.
                    pass
        finally:
            target.close()
            proc.stdout.close()

    pump = threading.Thread(target=copy_output, name='vkn-log-copy', daemon=True)
    pump.start()
    user_stop = False
    try:
        code = proc.wait()
    except KeyboardInterrupt:
        user_stop = True
        print('[INFO] Stopping the owned local service...', flush=True)
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT if os.name == 'nt' else signal.SIGINT)
            code = proc.wait(timeout=15)
        except (OSError, subprocess.TimeoutExpired, KeyboardInterrupt):
            # Only the process we launched, never every Python/Ollama process.
            proc.terminate()
            try:
                code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                code = proc.wait()
    pump.join(timeout=3)
    user_stop = user_stop or (ROOT / '.venv' / '.vkn_stop_requested').exists()
    state.update(state='user_stopped' if user_stop else 'stopped' if code == 0 else 'failed',
                 ended_utc=utc_now(), exit_code=code, exit_code_hex=exit_hex(code))
    write_state(status, state)
    print('[INFO] Service exit: ' + str(code) + ' / ' + exit_hex(code), flush=True)
    if not user_stop and code != 0:
        print('[ERROR] Local service exited. Logs were retained; no automatic restart loop.', flush=True)
    return 0 if user_stop or code == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
