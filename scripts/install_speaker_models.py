"""Explicit installer for optional local models. No user audio is uploaded."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SEG = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2'
EMB = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx'

def download(url, path):
    print('[INFO] Download:', url, flush=True)
    request = urllib.request.Request(url, headers={'User-Agent': 'VideoKnowledge-OptionalSpeakerInstaller/0.6'})
    with urllib.request.urlopen(request, timeout=90) as response, path.open('wb') as output:
        count = 0
        while block := response.read(1024 * 256):
            count += len(block)
            if count > 200 * 1024 * 1024: raise ValueError('Unexpectedly large model asset')
            output.write(block)
    if path.stat().st_size < 100000: raise ValueError('Download too small to be a model; not installing')
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    dest = Path(os.getenv('VKN_SPEAKER_MODEL_DIR') or str(ROOT / 'models' / 'speakers'))
    dest.mkdir(parents=True, exist_ok=True)
    if all((dest / name).is_file() for name in ('segmentation.onnx', 'embedding.onnx')):
        print('[INFO] Existing model files kept. Running load/silence smoke check.'); return check()
    # Stage all data before replacing final model files. Do not unpack arbitrary paths.
    with tempfile.TemporaryDirectory(prefix='vkn-speaker-', dir=dest) as temp:
        stage = Path(temp)
        seg_hash = download(SEG, stage / 'segmentation.tar.bz2')
        with tarfile.open(stage / 'segmentation.tar.bz2', 'r:bz2') as archive:
            for leaf in ('model.onnx', 'LICENSE', 'README.md'):
                candidates = [x for x in archive.getmembers() if Path(x.name).name == leaf and x.isfile()]
                if not candidates or candidates[0].size > 50 * 1024 * 1024:
                    raise ValueError('Unexpected segmentation archive layout: ' + leaf)
                member = candidates[0]
                with archive.extractfile(member) as source, (stage / ('segmentation.onnx' if leaf == 'model.onnx' else 'segmentation-' + leaf)).open('wb') as output:
                    shutil.copyfileobj(source, output)
        emb_hash = download(EMB, stage / 'embedding.onnx')
        for name in ('segmentation.onnx', 'embedding.onnx', 'segmentation-LICENSE', 'segmentation-README.md'):
            os.replace(stage / name, dest / name)
        (dest / 'download-info.json').write_text(json.dumps({'segmentation': SEG, 'embedding': EMB,
            'downloaded_sha256': {'segmentation_archive': seg_hash, 'embedding': emb_hash},
            'note': 'Hashes record downloaded bytes; not an independent publisher signature.'}, indent=2), encoding='utf-8')
    return check()

def check():
    sys.path.insert(0, str(ROOT))
    from server.speaker import SherpaBackend
    import numpy as np
    model = SherpaBackend()
    turns, _ = model.analyze(np.zeros(16000 * 10, dtype=np.float32))
    print('[OK] Optional models loaded and a silence inference completed.')
    print('[NOTE] This is NOT a speech accuracy/latency benchmark. Restart ASR, enable speaker mode in settings.')
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('[ERROR] Speaker setup failed:', str(exc), file=sys.stderr)
        print('[HELP] Keep speaker mode OFF; ordinary transcription is not removed. Check network/dependency output.', file=sys.stderr)
        raise SystemExit(1)
