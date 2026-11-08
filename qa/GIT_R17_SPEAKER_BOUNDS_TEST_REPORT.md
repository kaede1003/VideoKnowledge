# git-r17 Sherpa diarization bounds-check test report

**Date:** 2026-11-08  
**Bundle:** VideoKnowledge 0.12.1 / git-r17  
**Scope:** dependency pin, runtime safety gate, isolated model-load path, and regression suite.

## Changes under test

- `server/requirements-speaker.txt`: pin `sherpa-onnx==1.13.8`.
- `server/speaker.py`: report the installed runtime version; require at least 1.13.1 before loading the native library; expose version/safety fields to `/health`; add an explicit isolated-worker startup check.
- `scripts/install_all.py`: verify the installed distribution is exactly 1.13.8.
- `scripts/install_speaker_models.py`: load the native library and ONNX models inside the isolated worker during installation checks.
- `INSTALL_SPEAKER_MODEL.bat`: update the runtime and model check; `CHECK_SPEAKER_RUNTIME.bat`: show installed version and model availability.
- `tests/test_speaker_isolation_v0122.py`: add version parsing, old-version rejection, fixed-version acceptance, and isolated startup tests.

## Automated results

Command: `python scripts/run_checks.py --suite unit`

| Check | Result |
|---|---:|
| Repository hygiene | PASS — 272 source files, 0 problems |
| JavaScript syntax | PASS — 49 files, 0 failures |
| JavaScript tests | PASS — 278 / 278 |
| Python compile | PASS |
| Python unit tests | PASS — 379 / 379 |
| Overall | PASS |

Focused command: `python -m unittest tests.test_speaker_isolation_v0122 -v`  
Result: **14 / 14 passed**, including empty diarization results, worker crash/timeout isolation, ASR fallback, Ollama HTTP 500 audio-watermark protection, and runtime version gating.

Planning generation check: `python scripts/render_planning.py --check` — PASS.  
Batch-file check: both speaker batch files are ASCII and CRLF — PASS.

## Not verified in this environment

- The project test environment was Linux / Python 3.13.5. It did not load the user's Windows native DLL, Windows CPython 3.11 wheel, or the user's actual ONNX speaker models.
- No target Windows inference was run. The claim that upgrading to 1.13.8 resolves the observed `0xC0000005` remains **target-pending** until the user runs `INSTALL_SPEAKER_MODEL.bat`, confirms `/health` reports `speaker_diarization.version = 1.13.8`, and repeats authorized audio tests.
- No real Ollama Qwen3-ASR model request was made. The HTTP 500 root cause remains open pending a short-WAV diagnostic and the corresponding `%LOCALAPPDATA%\Ollama\server.log` excerpt.
- Synthetic tests do not measure speaker accuracy, speaker-role classification accuracy, latency, or GPU/CPU resource use.

## Upgrade / rollback

Stop the service, replace source files with the r17 bundle while preserving `.venv`, `models`, caches, notes, SQLite files, and `ASR_SETTINGS.bat`. Run `INSTALL_SPEAKER_MODEL.bat`, then `CHECK_SPEAKER_RUNTIME.bat`, and restart. To roll back source files, restore the previous source archive; if the runtime must also be downgraded, do so only deliberately with the old package pin and understand that the pre-1.13.1 diarization bounds-check defect is reintroduced. Do not delete model or note data.
