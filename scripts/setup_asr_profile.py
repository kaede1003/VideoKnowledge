"""INSTALL_ALL's ASR step. Isolated Qwen install; switch only after a load/kernel check.

No global pip, no driver install, no remote scripts, no deletion of model/audio
caches. A failed installation leaves the previously selected profile intact.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server.asr_profiles import PROFILE_FILE, PROFILES, ALIGNER_DIR, resolve_profile


def activate(root, name, report=None, model=None):
    if name not in {*PROFILES,'legacy'}:raise ValueError('Unknown ASR profile')
    target=Path(root)/PROFILE_FILE
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    if target.exists():
        backups=Path(root)/'diagnostics'/'install'/'asr-profile-backups'
        backups.mkdir(parents=True,exist_ok=True)
        shutil.copy2(target,backups/(stamp+'.json'))
    value={'version':1,'profile':name,'selected_at':stamp,
           'verification':report or {'accuracy_tested':False}}
    if model is not None:
        if name != 'ollama17': raise ValueError('Model override only available for Ollama')
        from server.ollama_asr import validate_model
        value['model'] = validate_model(model)
    tmp=target.with_name(target.name+'.tmp')
    try:
        tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        os.replace(tmp,target)
    finally:
        if tmp.exists():tmp.unlink()


def run(command, *, root=ROOT, timeout=7200):
    print('[RUN] '+str(command[0])+' '+(' '.join(map(str,command[1:]))),flush=True)
    subprocess.run(list(map(str,command)),cwd=str(root),check=True,timeout=timeout)


def ensure_qwen_env(root, runner=run):
    root=Path(root);folder=root/'.venv-qwen'
    python=folder/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if folder.exists() and not python.exists():
        raise RuntimeError('ASR_RUNTIME_INCOMPLETE: .venv-qwen exists without Python; it was not deleted')
    if not python.exists():runner([sys.executable,'-m','venv',str(folder)],root=root,timeout=180)
    runner([str(python),'-m','pip','install','--disable-pip-version-check','--retries','3','--timeout','90',
            'torch==2.9.1','--index-url','https://download.pytorch.org/whl/cu128'],root=root)
    runner([str(python),'-m','pip','install','--disable-pip-version-check','--retries','3','--timeout','90',
            '-r','server/requirements-qwen.txt'],root=root)
    runner([str(python),'-m','pip','check'],root=root,timeout=120)
    return python


def install(name, *, root=ROOT, runner=run, model=None, client=None):
    root=Path(root)
    if name=='legacy':
        activate(root,'legacy')
        return {'profile':'legacy','action':'selected_existing_environment','accuracy_tested':False}
    cfg=PROFILES[name]
    if cfg['backend']=='ollama-qwen3-asr':
        from server.ollama_asr import OllamaASRClient, validate_model
        resolved = validate_model(model or cfg['model'])
        api = client or OllamaASRClient(resolved)
        report = api.smoke_test()
        report.update(profile=name, backend=cfg['backend'], verified_model=resolved)
        activate(root,name,report,model=resolved)
        return report
    if cfg['backend']=='qwen3-native':
        python=ensure_qwen_env(root,runner)
        runner([python,'scripts/qwen_model_setup.py','--profile',name],root=root)
        # Download completion alone is NOT activation. This launches and executes
        # the SAME worker used by the service, on the selected CUDA device.
        runner([python,'-u','-m','server.qwen_worker','--model-dir',root/cfg['model_dir'],
                '--aligner-dir',root/ALIGNER_DIR,'--device',cfg['device'],'--smoke'],root=root,timeout=600)
        report={'profile':name,'backend':cfg['backend'],'model':cfg['model'],
                'device':cfg['device'],'load_and_synthetic_kernel_check':True,'accuracy_tested':False}
    else:
        runner([sys.executable,'scripts/prefetch_asr.py','--model',cfg['model'],
                '--device',cfg['device'],'--compute',cfg['compute']],root=root)
        report={'profile':name,'backend':cfg['backend'],'model':cfg['model'],
                'device':cfg['device'],'model_load_verified':True,'accuracy_tested':False}
    activate(root,name,report)
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile',choices=[*PROFILES,'legacy'],required=True)
    p.add_argument('--model',default=None,help='Exact locally installed model tag, only for ollama17')
    p.add_argument('--status',action='store_true')
    args=p.parse_args(argv)
    if args.status:
        print(json.dumps(resolve_profile(ROOT),ensure_ascii=False));return 0
    try:
        report=install(args.profile,model=args.model)
        print('[OK] ASR profile selected: '+json.dumps(report,ensure_ascii=False),flush=True)
        print('[NOTE] This does not verify real speech accuracy, translation or Edge capture.',flush=True)
        return 0
    except KeyboardInterrupt:
        print('[CANCELLED] Previous ASR profile kept; model caches not deleted.');return 130
    except Exception as exc:
        # Installation logs may contain package/download paths, not source audio.
        print('[ERROR] ASR setup failed: '+type(exc).__name__+'. Previous profile kept.',file=sys.stderr)
        if not isinstance(exc,subprocess.CalledProcessError):print(str(exc),file=sys.stderr)
        return 1

if __name__=='__main__':raise SystemExit(main())
