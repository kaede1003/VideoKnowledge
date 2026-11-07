"""Download/check the exact ASR model selected by the existing startup settings."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', default='small')
    args = p.parse_args()
    from faster_whisper import WhisperModel
    from faster_whisper.utils import available_models, download_model
    name = args.model.strip()
    if not name:
        raise ValueError('Empty ASR model')
    if Path(name).is_dir():
        model_path = name
        print('[INFO] Using existing local ASR directory; no download.', flush=True)
    elif name in available_models():
        try:
            model_path = download_model(name, local_files_only=True)
            if not all((Path(model_path) / f).is_file() for f in ('model.bin', 'config.json', 'tokenizer.json')):
                raise FileNotFoundError('Incomplete cached ASR snapshot')
            print('[SKIP] Complete ASR snapshot already cached; checking local load.', flush=True)
        except Exception:
            print('[INFO] Prefetching ASR model: ' + name + '; existing Hugging Face cache is reused.', flush=True)
            model_path = download_model(name)
    else:
        raise ValueError('Unsupported automatic ASR download name; use a known faster-whisper model or an existing directory.')
    # No transcript or audio is needed for a loading smoke check.
    model = WhisperModel(model_path, device='cpu', compute_type='int8', local_files_only=True, cpu_threads=2)
    del model
    print('[OK] ASR model loaded locally. No speech accuracy or latency benchmark was performed.', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('[ERROR] ASR prefetch/load failed: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
