"""Read-only summary of the actual selected engine, not the old BAT defaults."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.asr_profiles import resolve_profile
if __name__=='__main__':
    try:
        cfg=resolve_profile()
        print('[INFO] ASR engine: '+cfg['backend'])
        print('[INFO] ASR model: '+cfg['model'])
        print('[INFO] ASR device: '+cfg['device']+' / '+cfg['compute'])
        print('[INFO] Profile: '+cfg['profile']+'; see /health for actual runtime loading status.')
    except Exception as exc:
        print('[ERROR] '+str(exc));raise SystemExit(1)
