"""Check repository structure and common unsafe commit contents. Read-only.

This is a lightweight guard, not an exhaustive security audit or secret scanner.
Use --staged after git add to inspect exactly the index, including force-added data.
"""
from __future__ import annotations
import argparse
import ast
import fnmatch
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DIRS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache',
                '.cache', 'artifacts', 'diagnostics', 'dist', 'build', 'models',
                'video-cache', 'recordings', 'private-data', 'user-data', 'datasets', 'exports', 'VideoKnowledge_LoRA'}
PRIVATE_EXTS = {'.sqlite', '.sqlite3', '.db', '.pcm', '.wav', '.mp3', '.mp4', '.m4a', '.webm', '.mkv', '.part', '.ytdl',
                '.onnx', '.gguf', '.safetensors', '.pt', '.pth', '.ckpt', '.pem', '.pfx', '.p12', '.key', '.zip'}
TEXT_EXTS = {'.py','.js','.cjs','.md','.json','.html','.css','.txt','.yml','.yaml','.ps1','.bat'}
SECRETS = [re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
           re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b'),
           re.compile(r'\bsk-[A-Za-z0-9_-]{32,}\b'),
           re.compile(r'\bhf_[A-Za-z0-9]{30,}\b')]
REQUIRED = ['README.md','AGENTS.md','VERSION.json','.gitignore','.gitattributes',
            'extension/manifest.json','server/app.py','planning/backlog.json',
            'planning/acceptance.json','docs/STATUS.md','docs/KNOWN_ISSUES.md',
            'scripts/run_checks.py','.github/workflows/checks.yml']

def unsafe_path(name: str) -> str | None:
    p = PurePosixPath(name.replace('\\','/'))
    if p.is_absolute() or '..' in p.parts:
        return 'unsafe relative path'
    if any(part in PRIVATE_DIRS for part in p.parts):
        return 'runtime, private-data or generated directory'
    if p.name == 'ASR_SETTINGS.bat' or (p.name.startswith('.env') and p.name != '.env.example'):
        return 'local configuration'
    if p.suffix.lower() in PRIVATE_EXTS or '.sqlite' in p.name or p.name.endswith(('.db-wal','.db-shm')):
        return 'recording, model, database, archive or credential file'
    if p.name in ('完整笔记.txt',) or p.name.endswith('_知识笔记.html'):
        return 'private notebook export'
    if p.name.endswith(('.local.json','.local.toml','.log','.pyc')):
        return 'local configuration or generated log'
    return None

def inspect_bytes(name: str, raw: bytes, staged: bool = False) -> list[str]:
    errors = []
    reason = unsafe_path(name)
    if reason:
        errors.append(f'{name}: {reason}')
    if len(raw) > 5 * 1024 * 1024:
        errors.append(f'{name}: exceeds the 5 MiB source-file gate; review before committing')
    if name.lower().endswith('.bat'):
        if not raw.isascii() or raw.startswith(b'\xef\xbb\xbf'):
            errors.append(f'{name}: batch files must be ASCII without BOM')
        # Git index uses LF with eol=crlf. Working copies must retain Windows CRLF.
        if not staged and b'\n' in raw.replace(b'\r\n', b''):
            errors.append(f'{name}: working batch file is not CRLF')
        if b'\\"' in raw:
            errors.append(f'{name}: C-style escaped quotes are invalid in these cmd wrappers')
    if PurePosixPath(name).suffix.lower() in TEXT_EXTS or PurePosixPath(name).name.startswith('.'):
        text = raw.decode('utf-8-sig', errors='replace')
        for pattern in SECRETS:
            if pattern.search(text):
                errors.append(f'{name}: possible credential/private key detected (value omitted)')
                break
    return errors

def validate_backlog(tasks: list[dict], acceptance: list[dict]) -> list[str]:
    errors = []
    ids = [x.get('id') for x in tasks]
    acs = [x.get('id') for x in acceptance]
    if len(set(ids)) != len(ids): errors.append('duplicate task id')
    if len(set(acs)) != len(acs): errors.append('duplicate acceptance id')
    graph = {}
    for task in tasks:
        name = task.get('id','?')
        graph[name] = task.get('depends_on',[])
        for dep in graph[name]:
            if dep not in ids: errors.append(f'{name}: missing dependency {dep}')
        for ac in task.get('acceptance',[]):
            if ac not in acs: errors.append(f'{name}: missing acceptance {ac}')
        if task.get('status') not in {'todo','in_progress','blocked','done'}:
            errors.append(f'{name}: unsupported status')
    visiting, complete = set(), set()
    def visit(n):
        if n in visiting:
            raise ValueError('task dependency cycle')
        if n in complete: return
        visiting.add(n)
        for dep in graph.get(n,[]): visit(dep)
        visiting.remove(n); complete.add(n)
    try:
        for name in graph: visit(name)
    except ValueError as exc: errors.append(str(exc))
    return errors

def candidate_paths(root: Path, staged: bool = False) -> list[str]:
    if staged:
        proc = subprocess.run(['git','-C',str(root),'ls-files','--cached','-z'],capture_output=True)
        if proc.returncode:
            raise RuntimeError('Git index unavailable. Run git init and git add first.')
        return sorted({p.decode('utf-8') for p in proc.stdout.split(b'\0') if p})
    # Without Git, inspect prospective source files only. --staged never skips unsafe files.
    return sorted(p.relative_to(root).as_posix() for p in root.rglob('*')
                  if p.is_file() and not any(x in PRIVATE_DIRS for x in p.relative_to(root).parts)
                  and not unsafe_path(p.relative_to(root).as_posix()))

def read_bytes(root: Path, name: str, staged: bool) -> bytes:
    if not staged: return (root/name).read_bytes()
    proc = subprocess.run(['git','-C',str(root),'show',':'+name],capture_output=True)
    if proc.returncode: raise RuntimeError('Cannot read staged file: '+name)
    return proc.stdout

def check(root: Path, staged: bool = False, baseline: bool = False) -> tuple[list[str], int]:
    paths = candidate_paths(root, staged)
    if not paths: return ['No source files selected. Stage the project first.'], 0
    errors=[]
    for name in REQUIRED:
        if name not in paths: errors.append('Missing required source file: '+name)
    for name in paths:
        if (root/name).is_symlink(): errors.append(name+': symlink requires review'); continue
        errors += inspect_bytes(name,read_bytes(root,name,staged),staged)
    try:
        load=lambda name: json.loads(read_bytes(root,name,staged))
        v,m=load('VERSION.json'),load('extension/manifest.json')
        if v['extension']!=m['version']: errors.append('Extension version does not match VERSION.json')
        app=read_bytes(root,'server/app.py',staged).decode()
        if not re.search(r"['\"]version['\"]\s*:\s*['\"]"+re.escape(v['server'])+r"['\"]",app):
            errors.append('Server version does not match VERSION.json')
        for entry in m.get('content_scripts',[]):
            for name in entry.get('js',[])+entry.get('css',[]):
                if 'extension/'+name not in paths: errors.append('Manifest resource missing: '+name)
        for name in list(m.get('icons',{}).values())+[m['background']['service_worker'],m['options_ui']['page']]:
            if 'extension/'+name not in paths: errors.append('Manifest resource missing: '+name)
        tasks,acs=load('planning/backlog.json')['tasks'],load('planning/acceptance.json')['cases']
        errors += validate_backlog(tasks,acs)
        if baseline:
            for row in load('qa/baseline-source-sha256.json')['files']:
                raw=read_bytes(root,row['path'],staged)
                if hashlib.sha256(raw).hexdigest()!=row['sha256']:
                    errors.append('Baseline changed: '+row['path'])
    except (KeyError, ValueError, OSError, RuntimeError) as exc:
        errors.append('Metadata check failed: '+str(exc))
    return errors,len(paths)

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--staged',action='store_true',help='Inspect every staged file, even force-added ignored files')
    p.add_argument('--baseline',action='store_true',help='Require product sources to match this handoff baseline')
    args=p.parse_args()
    try: errors,count=check(ROOT,args.staged,args.baseline)
    except (OSError,RuntimeError) as exc:
        print('[ERROR]',str(exc)); return 2
    for e in errors: print('[FAIL]',e)
    print(f'[SUMMARY] {count} source files checked; {len(errors)} problems.')
    print('[NOTE] Lightweight gate only; inspect git diff --cached before publishing.')
    return 1 if errors else 0

if __name__=='__main__': raise SystemExit(main())
