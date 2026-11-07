"""Opt-in ASR selection. Never rewrites ASR_SETTINGS.bat or silently falls back."""
from __future__ import annotations
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_FILE = 'asr_profile.local.json'
PROFILES = {
    'qwen17': {'backend': 'qwen3-native', 'model': 'Qwen/Qwen3-ASR-1.7B-hf',
               'model_dir': 'models/qwen3-asr-1.7b-hf', 'device': 'cuda:0', 'compute': 'bfloat16'},
    'qwen06': {'backend': 'qwen3-native', 'model': 'Qwen/Qwen3-ASR-0.6B-hf',
               'model_dir': 'models/qwen3-asr-0.6b-hf', 'device': 'cuda:0', 'compute': 'bfloat16'},
    'whisper-large': {'backend': 'faster-whisper', 'model': 'large-v3', 'device': 'cuda', 'compute': 'int8_float16'},
    'whisper-turbo': {'backend': 'faster-whisper', 'model': 'turbo', 'device': 'cuda', 'compute': 'int8_float16'},
}
ALIGNER_ID = 'Qwen/Qwen3-ForcedAligner-0.6B-hf'
ALIGNER_DIR = 'models/qwen3-forcedaligner-0.6b-hf'


def resolve_profile(root=ROOT, environ=None):
    """Stored profile names only; never accept remote code/URLs/executables from a note."""
    env = os.environ if environ is None else environ
    path = Path(root) / PROFILE_FILE
    name = 'legacy'
    if path.exists():
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict) or value.get('version') != 1:
            raise ValueError('ASR_PROFILE_INVALID: invalid profile; use INSTALL_ALL -AsrProfile legacy')
        name = value.get('profile')
    if name == 'legacy':
        return {'profile': 'legacy', 'backend': 'faster-whisper',
                'model': env.get('VKN_ASR_MODEL', 'small').strip() or 'small',
                'device': env.get('VKN_ASR_DEVICE', 'cpu').strip() or 'cpu',
                'compute': env.get('VKN_ASR_COMPUTE', 'int8').strip() or 'int8'}
    if name not in PROFILES:
        raise ValueError('ASR_PROFILE_UNKNOWN: no automatic engine fallback')
    return {'profile': name, **PROFILES[name]}


def create_engine(root=ROOT):
    cfg = resolve_profile(root)
    if cfg['backend'] == 'qwen3-native':
        from .qwen_engine import QwenEngine
        return QwenEngine(cfg, root=Path(root))
    from .recognition import StreamingWhisperEngine
    engine = StreamingWhisperEngine()
    engine.model_name, engine.device, engine.compute_type = cfg['model'], cfg['device'], cfg['compute']
    engine.backend_name = 'faster-whisper'
    engine.profile_name = cfg['profile']
    return engine
