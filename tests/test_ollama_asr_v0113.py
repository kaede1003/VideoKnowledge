"""HTTP 500 diagnostics and durable retry backoff (no real model required)."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
import wave
from unittest.mock import patch

import httpx

from server.ollama_asr import OllamaASRClient, DEFAULT_MODEL, classify_ollama_failure
from server.qwen_protocol import ASRBackendError
from server.stream_store import StreamStore

ROOT=Path(__file__).resolve().parents[1]


def model_client(message):
    transport=httpx.MockTransport(lambda req: httpx.Response(500,json={'error':message},request=req))
    return httpx.Client(transport=transport,base_url='http://127.0.0.1:11434')


class ErrorClassification(unittest.TestCase):
    def test_runner_exit_is_actionable_and_never_exposes_paths(self):
        with model_client('llama-server process has terminated: C:\\Users\\private\\a.log') as client:
            with self.assertRaises(ASRBackendError) as result:
                OllamaASRClient(DEFAULT_MODEL,client=client).transcribe(b'\x01\x00'*16000)
        self.assertEqual(result.exception.code,'ASR_OLLAMA_SERVER_ERROR')
        self.assertIn('RUNNER_EXITED',str(result.exception))
        self.assertNotIn('private',str(result.exception))
    def test_oom_hint(self):
        with model_client('CUDA out of memory') as client:
            with self.assertRaises(ASRBackendError) as result:
                OllamaASRClient(DEFAULT_MODEL,client=client).transcribe(b'\x01\x00'*16000)
        self.assertIn('INSUFFICIENT_MEMORY',str(result.exception))
    def test_projector_hint(self):
        with model_client('qwen3a projector unsupported') as client:
            with self.assertRaises(ASRBackendError) as result:
                OllamaASRClient(DEFAULT_MODEL,client=client).transcribe(b'\x01\x00'*16000)
        self.assertIn('AUDIO_PROJECTOR',str(result.exception))
    def test_unknown_error_no_raw_body(self):
        msg='Unexpected secret-local detail XYZ_123'
        with model_client(msg) as client:
            with self.assertRaises(ASRBackendError) as result:
                OllamaASRClient(DEFAULT_MODEL,client=client).transcribe(b'\x01\x00'*16000)
        self.assertNotIn('XYZ_123',str(result.exception))
        self.assertIn('OLLAMA_INTERNAL',str(result.exception))
    def test_success_response_and_pcm_codec_unchanged(self):
        def response(req):
            body=json.loads(req.content)
            self.assertEqual(body['messages'][0]['content'],'')
            self.assertEqual(body['model'],DEFAULT_MODEL)
            self.assertTrue(body['messages'][0]['images'])
            return httpx.Response(200,json={'message':{'content':'language Chinese<asr_text>测试语音'}})
        with httpx.Client(transport=httpx.MockTransport(response),base_url='http://127.0.0.1:11434') as client:
            text,lang=OllamaASRClient(client=client).transcribe(b'\x01\x00'*16000)
        self.assertEqual((text,lang),('测试语音','zh'))


class DurableCooldown(unittest.TestCase):
    def test_http_500_keeps_audio_and_explicit_retry_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            s=StreamStore(Path(directory)/'storage.db',min_free=0)
            sid='a'*32
            try:
                s.open(sid,'test-video',{'translate':False})
                from server.stream_protocol import Packet
                s.receive(sid,Packet(1,0,1,0,b'\x01\x00'*16000))
                self.assertEqual(s.session(sid)['received'],1)
                s.fail(sid,'ASR_OLLAMA_SERVER_ERROR: 500')
                s.fail(sid,'ASR_OLLAMA_SERVER_ERROR: 500',cool_down=True)
                d=s.session(sid)
                self.assertEqual(d['processed'],0)
                self.assertGreater(d['retry_at'],time.time()+850)
                self.assertEqual(s.db.execute('SELECT LENGTH(pcm) FROM packets WHERE session=?',(sid,)).fetchone()[0],32000)
                self.assertIn('已暂停自动重试',s.events(sid)[-1]['message'])
                s.retry(sid)
                self.assertEqual(s.session(sid)['retry_at'],0)
                self.assertEqual(s.session(sid)['processed'],0)
                self.assertEqual(s.session(sid)['received'],1)
            finally:s.close()


class DiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('diagnose_ollama_asr',ROOT/'scripts/diagnose_ollama_asr.py')
        cls.diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.diag)
    def test_diagnostic_no_audio_without_wav(self):
        self.assertEqual(self.diag.error_kind('llama-server process has terminated'),'RUNNER_EXITED')
    def test_check_wav_rejects_wrong_sample_rate(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'sample.wav'
            with wave.open(str(p),'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\0'*16000)
            with self.assertRaises(ValueError):self.diag.check_wav(p)
    def test_check_wav_accepts_16k_mono(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'sample.wav'
            with wave.open(str(p),'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0'*64000)
            self.assertEqual(self.diag.check_wav(p)[1],2)

if __name__=='__main__':unittest.main()
