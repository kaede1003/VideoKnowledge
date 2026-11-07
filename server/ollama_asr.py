"""Local Ollama Qwen3-ASR transport for VideoKnowledge's durable VKN5 audio jobs.

Audio is already mono, signed 16-bit, 16 kHz PCM in StreamStore.  The published
frozenlab/qwen3-asr model accepts base64 WAV via /api/chat messages[].images.
It does NOT supply reliable word timestamps.  We transcribe only the owned
(non-overlapping) interval rather than pretending to align overlap text.
"""
from __future__ import annotations
import base64
import io
import math
import re
import time
import wave
from pathlib import Path

import httpx

from .qwen_protocol import ASRBackendError, RATE, build_segments, language_code

DEFAULT_MODEL = 'frozenlab/qwen3-asr:1.7b'
DEFAULT_URL = 'http://127.0.0.1:11434'
MODEL_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$')
_ASR_PATTERN = re.compile(r'(?is)\A\s*(?:language\s+([^<>\r\n]{1,60}))?\s*<asr_text>(.*)\Z')


def validate_model(name: str) -> str:
    if not isinstance(name, str) or not MODEL_PATTERN.fullmatch(name) or '://' in name or '..' in name:
        raise ASRBackendError('ASR_OLLAMA_INVALID_MODEL', 'use an exact locally installed model tag')
    return name


def pcm_to_wav(pcm: bytes) -> bytes:
    if not isinstance(pcm, bytes) or len(pcm) % 2 or not 0 < len(pcm) <= 60 * RATE * 2:
        raise ASRBackendError('ASR_BAD_AUDIO', 'expected up to 60 s of 16-kHz mono PCM16')
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(pcm)
    return stream.getvalue()


def parse_reply(value):
    if not isinstance(value, dict) or not isinstance(value.get('message'), dict):
        raise ASRBackendError('ASR_OLLAMA_BAD_RESPONSE', 'missing Ollama message')
    output = value['message'].get('content')
    if not isinstance(output, str) or len(output) > 60000:
        raise ASRBackendError('ASR_OLLAMA_BAD_RESPONSE', 'missing/oversized transcript')
    match = _ASR_PATTERN.fullmatch(output.strip())
    if not match:
        raise ASRBackendError('ASR_OLLAMA_BAD_RESPONSE', 'model did not return <asr_text>')
    lang = language_code((match.group(1) or '').strip())
    text = match.group(2).strip()
    if len(text) > 20000:
        raise ASRBackendError('ASR_OLLAMA_BAD_RESPONSE', 'transcript exceeds safety limit')
    return text, lang


def classify_ollama_failure(response):
    """Return an actionable, bounded diagnostic without copying raw server data.

    Ollama HTTP 500 commonly means the *model runner* failed.  A generic
    exception discards the useful response.error field; however that raw
    field may contain local paths, so expose only a curated category.
    """
    try:
        data = response.json()
        message = str(data.get('error', '')) if isinstance(data, dict) else ''
    except (ValueError, TypeError):
        message = ''
    value = message.lower()[:3000]
    if any(token in value for token in ('out of memory', 'not enough memory', 'insufficient memory', 'cuda out of memory')):
        return 'INSUFFICIENT_MEMORY: Ollama could not allocate model memory'
    if any(token in value for token in ('qwen3a', 'projector', 'mmproj', 'unsupported architecture', 'unsupported modality', 'unsupported image', 'unsupported audio')):
        return 'AUDIO_PROJECTOR: installed Ollama or model may not support the audio projector'
    if any(token in value for token in ('runner has unexpectedly stopped', 'runner process has terminated', 'llama-server process has terminated', 'exit status')):
        return 'RUNNER_EXITED: Ollama model runner exited; inspect Ollama server.log'
    if any(token in value for token in ('error loading model', 'unable to load model', 'load model', 'model load failed')):
        return 'MODEL_LOAD: Ollama could not load the selected model'
    if any(token in value for token in ('cuda error', 'cublas', 'driver', 'device-side assert')):
        return 'GPU_RUNTIME: Ollama encountered a GPU/runtime error'
    return 'OLLAMA_INTERNAL: inspect the Ollama server.log for the underlying failure'


class OllamaASRClient:
    """No internet URLs, user credentials, implicit proxy, or model downloading."""
    def __init__(self, model=DEFAULT_MODEL, *, client=None, timeout=180):
        self.model = validate_model(model)
        self.client = client
        self.timeout = float(timeout)

    def _client(self):
        return self.client or httpx.Client(base_url=DEFAULT_URL, trust_env=False,
                   follow_redirects=False, timeout=httpx.Timeout(self.timeout, connect=5))

    @staticmethod
    def _request(client, method, path, **kwargs):
        try:
            response = client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ASRBackendError('ASR_OLLAMA_TIMEOUT', 'local Ollama did not reply in time') from exc
        except httpx.HTTPError as exc:
            raise ASRBackendError('ASR_OLLAMA_UNAVAILABLE', 'cannot contact localhost:11434') from exc
        if response.status_code == 404:
            raise ASRBackendError('ASR_OLLAMA_MODEL_MISSING', 'model or endpoint missing on local Ollama')
        if response.status_code in (400, 415, 422):
            raise ASRBackendError('ASR_OLLAMA_UNSUPPORTED', f'local Ollama rejected audio: HTTP {response.status_code}')
        if 500 <= response.status_code < 600:
            hint = classify_ollama_failure(response)
            raise ASRBackendError('ASR_OLLAMA_SERVER_ERROR',
                                  f'HTTP {response.status_code}; {hint}')
        if response.status_code != 200:
            raise ASRBackendError('ASR_OLLAMA_HTTP', f'Ollama returned HTTP {response.status_code}')
        try:
            value = response.json()
        except (ValueError, TypeError) as exc:
            raise ASRBackendError('ASR_OLLAMA_BAD_RESPONSE', 'invalid Ollama JSON') from exc
        if not isinstance(value, dict):
            raise ASRBackendError('ASR_OLLAMA_BAD_RESPONSE', 'unexpected Ollama response')
        return value

    def list_models(self):
        client = self._client()
        try:
            data = self._request(client, 'GET', '/api/tags')
            return [str(m.get('name', '')) for m in data.get('models', [])
                    if isinstance(m, dict) and m.get('name')]
        finally:
            if self.client is None: client.close()

    def installed(self):
        names = self.list_models()
        if self.model not in names:
            raise ASRBackendError('ASR_OLLAMA_MODEL_MISSING', 'pull model first: ' + self.model)
        return names

    def transcribe(self, pcm):
        payload = {'model': self.model, 'stream': False,
                   'messages': [{'role': 'user', 'content': '',
                                 'images': [base64.b64encode(pcm_to_wav(pcm)).decode('ascii')]}]}
        client = self._client()
        try:
            output = self._request(client, 'POST', '/api/chat', json=payload)
            return parse_reply(output)
        finally:
            if self.client is None: client.close()

    def smoke_test(self):
        """Checks genuine model invocation with synthetic silence; NOT speech accuracy."""
        self.installed()
        # Some models return no transcription markers for silence, so only
        # require a valid 200 + string reply for this synthetic load probe.
        raw = bytes(RATE * 2)
        payload = {'model': self.model, 'stream': False,
                   'messages': [{'role': 'user', 'content': '',
                                 'images': [base64.b64encode(pcm_to_wav(raw)).decode('ascii')]}]}
        client = self._client()
        try:
            answer = self._request(client, 'POST', '/api/chat', json=payload)
            if not isinstance(answer.get('message'), dict) or not isinstance(answer['message'].get('content'), str):
                raise ASRBackendError('ASR_OLLAMA_BAD_RESPONSE', 'synthetic audio test failed')
            content = answer['message']['content'].strip()
            if content and not _ASR_PATTERN.fullmatch(content):
                raise ASRBackendError('ASR_OLLAMA_UNSUPPORTED', 'model did not produce an ASR-formatted response')
            return {'model':self.model, 'synthetic_audio_request_passed':True, 'speech_accuracy_tested':False}
        finally:
            if self.client is None: client.close()


class OllamaASREngine:
    backend_name = 'ollama-qwen3-asr'
    def __init__(self, cfg, *, client=None):
        self.profile_name = cfg['profile']
        self.model_name = validate_model(cfg['model'])
        self.device = 'ollama-managed'
        self.compute_type = 'ollama'
        self.api = client or OllamaASRClient(self.model_name)
        self.status = {'phase':'not_loaded','loaded':False,'error':''}

    @property
    def loaded(self):
        return self.status['loaded']

    def snapshot(self):
        return {'backend':self.backend_name, 'profile':self.profile_name,
                'configured_model':self.model_name,'status':dict(self.status),
                'mode':'windowed_local','word_timestamps':False,'accuracy_tested':False}

    def transcribe_job(self, job):
        if not job.packets: return []
        audio = job.pcm
        if len(audio) % 2 or not audio:
            raise ASRBackendError('ASR_BAD_AUDIO')
        a = round(job.owner_start * RATE) * 2
        b = round(job.owner_end * RATE) * 2
        if not 0 <= a < b <= len(audio):
            raise ASRBackendError('ASR_BAD_OWNERSHIP')
        owned = audio[a:b]
        if not any(owned): return []
        try:
            self.status.update(phase='recognizing',error='')
            text,lang = self.api.transcribe(owned)
        except Exception as exc:
            code = getattr(exc, 'code', type(exc).__name__)
            self.status.update(phase='error',error=str(code),loaded=False)
            raise
        self.status.update(phase='ready',error='',loaded=True)
        if not text: return []
        flags = ['word_timestamps_missing']
        if lang == 'unknown': flags.append('language_uncertain')
        # A small heuristic catches pathological looping without removing words.
        if len(text) >= 48 and any(text.count(text[i:i+12]) >= 4 for i in range(0,min(len(text)-12,60),12)):
            flags.append('asr_repetition_suspected')
        reply = {'segments':[{'text':text,'language':lang,'start':job.owner_start,
                 'end':job.owner_end,'words':[],'flags':flags}]}
        rows = build_segments(job,reply,self.model_name,self.device)
        for row in rows:
            row.update(asrEngine=self.backend_name,asrTiming='audio_window',qualityVersion='0.11.1')
        return rows
