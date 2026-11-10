"""Run repository, fixture-unit and optional DOM checks; never install packages.

Exit codes: 0 all selected checks passed; 1 a check failed; 2 missing tools.
Real Edge/audio/model acceptance is deliberately not implied by this command.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BROWSER_TESTS = ['browser_navigation_v0102.py', 'browser_cache_v0102.py', 'browser_reader_v0101.py', 'browser_caption_v0100.py', 'browser_quality_v071.py',
                 'browser_writing_v070.py', 'browser_ai_v052.py', 'browser_content_v052.py', 'browser_v080.py', 'browser_presentation_v090.py', 'browser_asr_settings_v0112.py', 'browser_task_progress_v0124.py']

def plan(suite: str) -> list[tuple[str, list[str]]]:
    node = shutil.which('node') or 'node'
    rows = [('repository', [sys.executable, 'scripts/check_repo.py'])]
    if suite in ('unit', 'all'):
        rows += [('js-syntax', [node, 'scripts/check_js.cjs']),
                 ('javascript', [node, 'scripts/run_js_tests.cjs']),
                 ('python-compile', [sys.executable, '-m', 'compileall', '-q', 'server', 'scripts', 'tests']),
                 ('python', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', '-v'])]
    if suite in ('browser', 'all'):
        rows += [(Path(name).stem, [sys.executable, 'tests/' + name]) for name in BROWSER_TESTS]
    return rows

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=['repository', 'unit', 'browser', 'all'], default='unit')
    parser.add_argument('--timeout', type=int, default=180, help='Per check deadline in seconds, not a product timeout')
    args = parser.parse_args()
    if args.timeout < 5:
        parser.error('--timeout must be at least 5')
    if args.suite != 'repository' and not shutil.which('node'):
        print('[ERROR] Node.js is required. No test is reported as passed.', file=sys.stderr)
        return 2
    now = datetime.now(timezone.utc)
    out = ROOT / 'artifacts' / 'checks' / now.strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1', PYTHONUNBUFFERED='1')
    rows = []
    for name, command in plan(args.suite):
        print('[RUN]', name, flush=True)
        start = time.monotonic()
        log = out / (name + '.log')
        # Use a file instead of PIPE: a timed-out browser's child processes may
        # keep stdout open and otherwise prevent communicate() from returning.
        rc = 127
        with log.open('w', encoding='utf-8') as sink:
            proc = None
            try:
                group = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
                         if os.name == 'nt' else {'start_new_session': True})
                proc = subprocess.Popen(command, cwd=ROOT, env=env, stdout=sink,
                                        stderr=subprocess.STDOUT, **group)
                rc = proc.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                rc = 124
                if os.name == 'nt':
                    # Only the test process tree started above, never all Node/Python.
                    subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],
                                   stdout=sink,stderr=subprocess.STDOUT,timeout=10)
                else:
                    try: os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                proc.wait(timeout=10)
                sink.write('\nCHECK DEADLINE EXCEEDED\n')
            except OSError as exc:
                sink.write(f'{type(exc).__name__}: {exc}\n')
        text = log.read_text(encoding='utf-8', errors='replace')
        rows.append({'name': name, 'command': command, 'exit_code': rc,
                     'seconds': round(time.monotonic() - start, 3), 'log': log.relative_to(ROOT).as_posix()})
        print('[PASS]' if rc == 0 else '[FAIL]', name, flush=True)
        if rc:
            print(text[-6000:])
    report = {'started_utc': now.isoformat(), 'suite': args.suite,
              'scope': 'Code, fixture unit tests, optional DOM tests; NOT real Edge/ASR/Ollama acceptance',
              'python': sys.version.split()[0], 'platform': sys.platform,
              'all_passed': all(r['exit_code'] == 0 for r in rows), 'checks': rows}
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Report:', out.relative_to(ROOT))
    return 0 if report['all_passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
