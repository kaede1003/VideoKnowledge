"""Regression coverage for native sherpa crashes and empty diarization output.

The crash fixture exits only its isolated child process. It must never terminate
this unittest/service process. No real sherpa model or audio download is used.
"""
from __future__ import annotations
import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from server.speaker import (
    IsolatedSherpaBackend,
    SpeakerAnnotator,
    SherpaBackend,
    SpeakerBackendError,
    availability,
    _version_tuple,
)
from server.stream_protocol import Packet, AUDIO, RATE
from server.stream_store import StreamStore, normalize_options
from server.stream_service import StreamManager
from server.qwen_protocol import ASRBackendError

SID = 'b' * 32


def _crashing_speaker_worker(conn):
    """Test child: handshake, receive one request, then emulate native death."""
    try:
        conn.send({'type': 'ready'})
        conn.recv()
        os._exit(7)
    finally:
        conn.close()


def _empty_speaker_worker(conn):
    """Test child: a valid native call that finds no active speakers."""
    try:
        conn.send({'type': 'ready'})
        while True:
            request = conn.recv()
            if request is None:
                return
            conn.send({'type': 'ok', 'turns': [], 'vectors': {}})
    except EOFError:
        return
    finally:
        conn.close()


def _startup_error_worker(conn):
    try:
        conn.send({'type': 'startup_error', 'error': 'RuntimeError'})
    finally:
        conn.close()


def _hanging_speaker_worker(conn):
    try:
        conn.send({'type': 'ready'})
        conn.recv()
        time.sleep(30)
    finally:
        conn.close()


def _pcm(seconds=3, amplitude=0.15):
    n = int(RATE * seconds)
    return (np.sin(np.arange(n, dtype=np.float32) * 0.04) * amplitude).astype(np.float32)


def _job(diarize=True):
    raw = (np.sin(np.arange(RATE * 3, dtype=np.float32) * 0.04) * 4000).astype('<i2').tobytes()
    packet = Packet(1, 0.0, 3.0, AUDIO, raw)
    return type('JobFixture', (), {
        'packets': [packet], 'pcm': raw, 'speaker_state': {},
        'options': normalize_options({'diarize': diarize, 'translate': False}),
        'session': SID, 'owner_start': 0.0, 'owner_end': 3.0,
    })()


class _ASR:
    backend_name = 'ollama-qwen3-asr'

    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def transcribe_job(self, job):
        self.calls += 1
        if self.fail:
            raise ASRBackendError('ASR_OLLAMA_SERVER_ERROR', 'HTTP 500; OLLAMA_INTERNAL')
        return [{'text': '原始音频转写仍然保留', 'time': 0.0, 'end': 3.0,
                 '_words': [], 'qualityFlags': ['word_timestamps_missing']}]


class _EmptyResult:
    def sort_by_start_time(self):
        return []


class _EmptyPipeline:
    def __init__(self):
        self.calls = 0

    def process(self, audio):
        self.calls += 1
        return _EmptyResult()


class _UnusedExtractor:
    def create_stream(self):
        raise AssertionError('no embedding extraction should run for no speakers')




class SherpaRuntimeVersionGateTests(unittest.TestCase):
    def test_version_parser_handles_release_suffixes(self):
        self.assertEqual(_version_tuple('1.13.8'), (1, 13, 8))
        self.assertEqual(_version_tuple('1.13.8+cpu'), (1, 13, 8))
        self.assertIsNone(_version_tuple('unknown'))

    def test_old_runtime_is_blocked_before_native_import(self):
        with tempfile.TemporaryDirectory() as td:
            model_root = Path(td)
            for name in ('segmentation.onnx', 'embedding.onnx'):
                (model_root / name).write_bytes(b'fixture')
            with patch('server.speaker.importlib.util.find_spec', return_value=object()), \
                 patch('server.speaker.distribution_version', return_value='1.12.34'), \
                 patch('server.speaker.model_dir', return_value=model_root):
                state = availability()
            self.assertFalse(state['available'])
            self.assertFalse(state['version_safe'])
            self.assertEqual(state['version'], '1.12.34')
            self.assertIn('低于安全最低版本 1.13.1', state['message'])

    def test_unverifiable_runtime_version_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            model_root = Path(td)
            for name in ('segmentation.onnx', 'embedding.onnx'):
                (model_root / name).write_bytes(b'fixture')
            with patch('server.speaker.importlib.util.find_spec', return_value=object()), \
                 patch('server.speaker.distribution_version', side_effect=__import__('importlib').metadata.PackageNotFoundError), \
                 patch('server.speaker.model_dir', return_value=model_root):
                state = availability()
            self.assertFalse(state['available'])
            self.assertFalse(state['version_safe'])
            self.assertEqual(state['version'], 'unknown')
            self.assertIn('无法确认', state['message'])

    def test_fixed_runtime_is_accepted_when_models_exist(self):
        with tempfile.TemporaryDirectory() as td:
            model_root = Path(td)
            for name in ('segmentation.onnx', 'embedding.onnx'):
                (model_root / name).write_bytes(b'fixture')
            with patch('server.speaker.importlib.util.find_spec', return_value=object()), \
                 patch('server.speaker.distribution_version', return_value='1.13.8'), \
                 patch('server.speaker.model_dir', return_value=model_root):
                state = availability()
            self.assertTrue(state['available'])
            self.assertTrue(state['version_safe'])
            self.assertEqual(state['pinned_version'], '1.13.8')

    def test_backend_refuses_unsafe_runtime_before_import(self):
        with patch('server.speaker.availability',
                   return_value={'available': False, 'message': 'unsafe sherpa runtime'}):
            with self.assertRaisesRegex(RuntimeError, 'unsafe sherpa runtime'):
                SherpaBackend()


class NativeIsolationTests(unittest.TestCase):
    def test_silent_and_too_short_audio_skip_native_pipeline(self):
        backend = SherpaBackend.__new__(SherpaBackend)
        backend.pipeline = _EmptyPipeline()
        backend.extractor = _UnusedExtractor()
        turns, vectors = backend.analyze(np.zeros(RATE * 3, dtype=np.float32))
        self.assertEqual((turns, vectors), ([], {}))
        self.assertEqual(backend.pipeline.calls, 0)
        turns, vectors = backend.analyze(_pcm(0.25))
        self.assertEqual((turns, vectors), ([], {}))
        self.assertEqual(backend.pipeline.calls, 0)

    def test_empty_native_diarization_result_is_normal_uncertain_output(self):
        backend = SherpaBackend.__new__(SherpaBackend)
        backend.pipeline = _EmptyPipeline()
        backend.extractor = _UnusedExtractor()
        turns, vectors = backend.analyze(_pcm(3))
        self.assertEqual((turns, vectors), ([], {}))
        self.assertEqual(backend.pipeline.calls, 1)

    def test_start_loads_only_inside_isolated_child(self):
        backend = IsolatedSherpaBackend(
            worker_target=_empty_speaker_worker,
            startup_timeout=15,
            analyze_timeout=5,
        )
        try:
            state = backend.start()
            self.assertEqual(state['phase'], 'ready')
            self.assertEqual(backend.analyze(_pcm(3)), ([], {}))
        finally:
            backend.close()

    def test_native_child_crash_is_contained_and_does_not_restart_loop(self):
        backend = IsolatedSherpaBackend(
            worker_target=_crashing_speaker_worker,
            startup_timeout=15,
            analyze_timeout=5,
        )
        try:
            async def call_from_worker_thread():
                return await asyncio.to_thread(backend.analyze, _pcm(3))
            with self.assertRaises(SpeakerBackendError):
                asyncio.run(call_from_worker_thread())
            self.assertIsNotNone(backend.failure)
            # A second call fails closed instead of repeatedly launching a
            # native library known to have crashed during this service run.
            with self.assertRaises(SpeakerBackendError):
                backend.analyze(_pcm(3))
            self.assertIsNone(backend._process)
        finally:
            backend.close()

    def test_worker_initialization_failure_is_contained(self):
        backend = IsolatedSherpaBackend(
            worker_target=_startup_error_worker,
            startup_timeout=15,
            analyze_timeout=5,
        )
        try:
            with self.assertRaises(SpeakerBackendError):
                backend.analyze(_pcm(3))
            self.assertIn('SHERPA_WORKER_INIT_FAILED', backend.failure)
            self.assertEqual(backend.snapshot()['phase'], 'disabled_after_failure')
        finally:
            backend.close()

    def test_hung_native_call_is_terminated_after_bounded_timeout(self):
        backend = IsolatedSherpaBackend(
            worker_target=_hanging_speaker_worker,
            startup_timeout=15,
            analyze_timeout=5,
        )
        try:
            with self.assertRaises(SpeakerBackendError):
                backend.analyze(_pcm(3))
            self.assertEqual(backend.failure, 'SHERPA_ANALYZE_TIMEOUT')
            self.assertIsNone(backend._process)
        finally:
            backend.close()

    def test_empty_result_round_trips_through_persistent_child(self):
        backend = IsolatedSherpaBackend(
            worker_target=_empty_speaker_worker,
            startup_timeout=15,
            analyze_timeout=5,
        )
        try:
            self.assertEqual(backend.analyze(_pcm(3)), ([], {}))
            self.assertEqual(backend.analyze(_pcm(3)), ([], {}))
            self.assertEqual(backend.snapshot()['phase'], 'ready')
        finally:
            backend.close()

    def test_speaker_failure_falls_back_to_full_audio_without_fake_identity(self):
        backend = IsolatedSherpaBackend(
            worker_target=_crashing_speaker_worker,
            startup_timeout=15,
            analyze_timeout=5,
        )
        asr = _ASR()
        try:
            result = SpeakerAnnotator(lambda: backend).transcribe_and_annotate(_job(), asr)
            self.assertEqual(asr.calls, 1)
            self.assertEqual(result[0]['text'], '原始音频转写仍然保留')
            self.assertEqual(result[0]['speakerStatus'], 'unavailable')
            self.assertEqual(result[0].get('speakerId', ''), '')
        finally:
            backend.close()


class ServiceContinuesAfterOllama500(unittest.TestCase):
    def test_asr_worker_stays_alive_and_audio_watermark_is_not_advanced(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                store = StreamStore(Path(td) / 'stream.sqlite3', min_free=0)
                manager = StreamManager(store, _ASR(fail=True))
                try:
                    store.open(SID, 'synthetic-video', {'diarize': False, 'translate': False})
                    raw = (np.ones(RATE * 15, dtype='<i2') * 1000).tobytes()
                    store.receive(SID, Packet(1, 0.0, 15.0, AUDIO, raw))
                    task = asyncio.create_task(manager.asr_worker())
                    for _ in range(300):
                        await asyncio.sleep(0.02)
                        session = store.session(SID)
                        if session['attempts'] >= 2:
                            break
                    self.assertTrue(task.done() is False, 'ASR worker must remain alive after job-level HTTP 500')
                    self.assertEqual(session['processed'], 0)
                    self.assertEqual(session['received'], 1)
                    self.assertGreater(session['retry_at'] - time.time(), 850)
                    self.assertEqual(manager.engine.calls, 2)
                    self.assertEqual(store._packets(SID)[0].pcm, raw)
                finally:
                    if 'task' in locals():
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                    await manager.stop()
                    store.close()
        asyncio.run(scenario())


if __name__ == '__main__':
    unittest.main()
