"""Fetch ONLY the official native-HF Qwen ASR/aligner repos into project models/.

Invoked in .venv-qwen. Never swaps an incompatible original checkpoint for the
native -hf checkpoint. No TLS/redirect security overrides or arbitrary mirrors.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server.asr_profiles import PROFILES, ALIGNER_ID, ALIGNER_DIR


def complete(folder):
    p=Path(folder)
    if not (p/'config.json').is_file() or not (p/'tokenizer_config.json').is_file():return False
    weights=list(p.glob('*.safetensors'))
    if not weights or any(f.stat().st_size<1024 for f in weights):return False
    index=p/'model.safetensors.index.json'
    if index.exists():
        try:
            return all((p/name).is_file() for name in set(json.loads(index.read_text())['weight_map'].values()))
        except (ValueError,KeyError,OSError):return False
    return True


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile',choices=['qwen17','qwen06'],required=True)
    a=p.parse_args(argv)
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT','120')
    os.environ.setdefault('HF_HUB_ETAG_TIMEOUT','60')
    from huggingface_hub import snapshot_download,HfApi
    cfg=PROFILES[a.profile]
    manifest={'source':'official_huggingface','models':[],'accuracy_tested':False}
    for repo,relative in [(cfg['model'],cfg['model_dir']),(ALIGNER_ID,ALIGNER_DIR)]:
        directory=ROOT/relative
        if complete(directory):
            print('[CACHE] '+repo+' exists; installer will validate model loading.',flush=True)
            manifest['models'].append({'repo':repo,'cached':True})
            continue
        last=None
        for attempt in range(3):
            try:
                # Resolve one immutable revision per attempt; native safetensors only.
                sha=HfApi().model_info(repo).sha
                print('[DOWNLOAD] '+repo+' revision '+sha,flush=True)
                snapshot_download(repo_id=repo,revision=sha,local_dir=directory,max_workers=2,
                    allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.tiktoken','*.jinja','LICENSE*','README.md'])
                if not complete(directory):raise RuntimeError('ASR_MODEL_INCOMPLETE')
                manifest['models'].append({'repo':repo,'revision':sha,'cached':False})
                break
            except Exception as exc:
                last=exc
                status=getattr(getattr(exc,'response',None),'status_code',None)
                if status in (401,403,404,429) or 'certificate' in str(exc).lower() or attempt==2:raise
                print('[RETRY] Download interrupted; reusing official cache. '+type(exc).__name__,flush=True)
                time.sleep(2**(attempt+1))
        else:raise last
    folder=ROOT/'diagnostics'/'install';folder.mkdir(parents=True,exist_ok=True)
    (folder/'qwen-download.local.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0

if __name__=='__main__':raise SystemExit(main())
