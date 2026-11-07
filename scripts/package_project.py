"""Create a reviewed source ZIP from a clean, committed Git working tree.

No pushes, model downloads, .git folders or ignored runtime data are included.
Output defaults to ignored dist/. Refuses overwrite.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
from pathlib import Path
import subprocess
import zipfile
import sys
from check_repo import ROOT, check

def git(*args):
    p=subprocess.run(['git','-C',str(ROOT),*args],capture_output=True,text=True,encoding='utf-8')
    if p.returncode: raise RuntimeError(p.stderr.strip() or 'Git command failed')
    return p.stdout

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='dist/VideoKnowledge_Source.zip')
    args=parser.parse_args()
    try:
        git('rev-parse','--verify','HEAD')
        if git('status','--porcelain'):
            raise RuntimeError('Commit/review pending changes first; source packaging requires a clean worktree.')
        errors,count=check(ROOT,staged=True)
        if errors: raise RuntimeError('\n'.join(errors))
        files=[p for p in git('ls-files','-z').split('\0') if p]
        output=Path(args.output)
        if not output.is_absolute():output=ROOT/output
        output.parent.mkdir(parents=True,exist_ok=True)
        # Deterministic timestamps for an identical working tree.
        with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for name in sorted(files):
                raw=(ROOT/name).read_bytes()
                if name.endswith(('.bat','.cmd','.ps1')):
                    raw=raw.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
                info=zipfile.ZipInfo('VideoKnowledge_Git_Project/'+name,(2026,11,6,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
                archive.writestr(info,raw)
        sha=hashlib.sha256(output.read_bytes()).hexdigest()
        output.with_suffix(output.suffix+'.sha256').write_text(sha+'  '+output.name+'\n',encoding='ascii')
        print(f'[OK] {count} reviewed source files: {output}')
        return 0
    except (OSError,RuntimeError) as exc:
        print('[ERROR]',exc,file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
