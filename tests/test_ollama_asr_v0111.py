"""Ollama ASR contract tests. Synthetic audio and mocked local HTTP; no model downloads."""
from __future__ import annotations
import base64
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import wave
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.ollama_asr import (DEFAULT_MODEL, OllamaASRClient, OllamaASREngine,
                               parse_reply, pcm_to_wav, validate_model)
from server.qwen_protocol import ASRBackendError, RATE
from server.asr_profiles import PROFILES, create_engine, resolve_profile, PROFILE_FILE
from server.asr_settings import select_for_next_start, attach_asr_settings
from server.stream_protocol import Packet, AUDIO
from server.stream_store import Job, StreamStore
from server.speaker import SpeakerAnnotator
from scripts.setup_asr_profile import install


SESSION = '1'*32
PCM = struct.pack('<h', 3000) * (RATE * 2)


def sample_job():
    packets=[Packet(1,50.0,52.0,AUDIO,PCM)]
    return Job(SESSION,packets,1,0,2,{'language':'auto','translate':True,
            'correct':False,'diarize':True,'maxSpeakers':2},'')


def mock_http(output='language Spanish<asr_text>Buenos días'):
    calls=[]
    def response(request):
        calls.append(request)
        if request.url.path=='/api/tags':
            return httpx.Response(200,json={'models':[{'name':DEFAULT_MODEL}]})
        if request.url.path=='/api/chat':
            return httpx.Response(200,json={'message':{'role':'assistant','content':output}})
        return httpx.Response(404,json={'error':'missing'})
    return httpx.Client(transport=httpx.MockTransport(response),base_url='http://127.0.0.1:11434'),calls


class PayloadTests(unittest.TestCase):
    def test_wav_is_real_mono_16k_pcm16(self):
        wav=pcm_to_wav(PCM)
        with wave.open(io.BytesIO(wav),'rb') as reader:
            self.assertEqual(reader.getframerate(),16000)
            self.assertEqual(reader.getnchannels(),1)
            self.assertEqual(reader.getsampwidth(),2)
            self.assertEqual(reader.readframes(RATE*2),PCM)
    def test_reject_invalid_payload_and_model(self):
        for audio in [b'',b'\x00',bytes(61*RATE*2)]:
            with self.subTest(size=len(audio)), self.assertRaises(ASRBackendError):pcm_to_wav(audio)
        for name in ['https://bad','../config','x'*200,'bad model','']:
            with self.subTest(name=name),self.assertRaises(ASRBackendError):validate_model(name)
    def test_post_contract_and_language(self):
        http,calls=mock_http()
        api=OllamaASRClient(DEFAULT_MODEL,client=http)
        text,lang=api.transcribe(PCM)
        self.assertEqual((text,lang),('Buenos días','es'))
        self.assertEqual(len(calls),1)
        request=json.loads(calls[0].content)
        self.assertEqual(calls[0].url.path,'/api/chat')
        self.assertEqual(request['model'],DEFAULT_MODEL)
        self.assertIs(request['stream'],False)
        self.assertEqual(len(request['messages']),1)
        self.assertEqual(request['messages'][0]['content'],'')
        raw=base64.b64decode(request['messages'][0]['images'][0])
        with wave.open(io.BytesIO(raw),'rb') as w:self.assertEqual(w.readframes(RATE*2),PCM)
    def test_parse_languages_and_require_marker(self):
        for lang, expected in [('Chinese','zh'),('Portuguese','pt'),('English','en')]:
            self.assertEqual(parse_reply({'message':{'content':f'language {lang}<asr_text>Hello'}}),("Hello",expected))
        self.assertEqual(parse_reply({'message':{'content':'<asr_text>你好'}}),('你好','unknown'))
        for value in ({}, {'message':{'content':'I cannot transcribe'}},{'message':{'content':None}}):
            with self.assertRaises(ASRBackendError):parse_reply(value)
    def test_model_check_and_synthetic_probe(self):
        http,calls=mock_http('')
        api=OllamaASRClient(client=http)
        self.assertEqual(api.installed(),[DEFAULT_MODEL])
        self.assertTrue(api.smoke_test()['synthetic_audio_request_passed'])
        self.assertEqual([r.url.path for r in calls],['/api/tags','/api/tags','/api/chat'])
        self.assertLess(len(calls[2].content),50000)
    def test_absent_model_does_not_pull_or_switch(self):
        http=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200,json={'models':[]})),base_url='http://127.0.0.1:11434')
        with self.assertRaisesRegex(ASRBackendError,'MODEL_MISSING'):OllamaASRClient(client=http).smoke_test()
    def test_text_chat_model_is_not_accepted_as_asr(self):
        http,_=mock_http('Hello, I am a text model')
        with self.assertRaisesRegex(ASRBackendError,'UNSUPPORTED'):
            OllamaASRClient(client=http).smoke_test()
    def test_timeout_is_recoverable_code(self):
        def timeout(_):raise httpx.ReadTimeout('synthetic')
        http=httpx.Client(transport=httpx.MockTransport(timeout),base_url='http://127.0.0.1:11434')
        with self.assertRaisesRegex(ASRBackendError,'ASR_OLLAMA_TIMEOUT'):OllamaASRClient(client=http).transcribe(PCM)


class PipelineTests(unittest.TestCase):
    def test_audio_window_no_fake_words_speaker_and_translation(self):
        http,calls=mock_http()
        engine=OllamaASREngine({'profile':'ollama17','model':DEFAULT_MODEL},
                                client=OllamaASRClient(client=http))
        job=sample_job()
        out=engine.transcribe_job(job)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]['time'],50)
        self.assertEqual(out[0]['end'],52)
        self.assertEqual(out[0]['asrEngine'],'ollama-qwen3-asr')
        self.assertEqual(out[0]['asrTiming'],'audio_window')
        self.assertEqual(out[0]['_words'],[])
        self.assertIsNone(out[0]['confidence'])
        self.assertIn('word_timestamps_missing',out[0]['qualityFlags'])
        # Speaker labels remain uncertain, not invented from a 12s audio window.
        class FakeSpeaker:
            def analyze(self,pcm): return ([],{})
        annotator=SpeakerAnnotator(factory=FakeSpeaker)
        result=annotator.annotate(job,out)
        self.assertEqual(result[0].get('speakerStatus'),'uncertain')
        with tempfile.TemporaryDirectory() as d:
            store=StreamStore(Path(d)/'raw.sqlite3',min_free=0)
            try:
                store.open(SESSION,'test-video',job.options)
                store.receive(SESSION,job.packets[0])
                store.commit(job,result)
                cues=[e for e in store.events(SESSION,0) if e['type']=='segment']
                self.assertEqual(cues[0]['original'],'Buenos días')
                self.assertEqual(cues[0]['translationStatus'],'pending')
                self.assertEqual(store.session(SESSION)['processed'],1)
            finally:store.close()
    def test_owned_interval_sends_no_overlap_and_keeps_media_time(self):
        first=Packet(1,100,102,AUDIO,PCM)
        second=Packet(2,102,104,AUDIO,PCM)
        audio_calls=[]
        class API:
            def transcribe(self,p):audio_calls.append(p);return ('你好','zh')
        job=Job(SESSION,[first,second],2,2,4,{'translate':False},'')
        output=OllamaASREngine({'profile':'ollama17','model':DEFAULT_MODEL},client=API()).transcribe_job(job)
        self.assertEqual(audio_calls,[PCM])
        self.assertEqual(output[0]['time'],102)
        self.assertEqual(output[0]['end'],104)
    def test_transport_error_does_not_advance_durable_cursor(self):
        class ErrorAPI:
            def transcribe(self,p):raise ASRBackendError('ASR_OLLAMA_TIMEOUT')
        j=sample_job()
        with tempfile.TemporaryDirectory() as d:
            store=StreamStore(Path(d)/'raw.sqlite3',min_free=0)
            try:
                store.open(SESSION,'test-video',j.options)
                store.receive(SESSION,j.packets[0])
                engine=OllamaASREngine({'profile':'ollama17','model':DEFAULT_MODEL},client=ErrorAPI())
                with self.assertRaises(ASRBackendError):engine.transcribe_job(j)
                self.assertEqual(store.session(SESSION)['processed'],0)
                self.assertEqual(len(store._packets(SESSION)),1)
            finally:store.close()


class ConfigurationTests(unittest.TestCase):
    def test_activate_and_resolve_without_native_torch(self):
        class FakeClient:
            def smoke_test(self):return {'synthetic_audio_request_passed':True}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch('scripts.setup_asr_profile.ensure_qwen_env',side_effect=AssertionError('native torch must not install')):
                report=install('ollama17',root=root,client=FakeClient(),model=DEFAULT_MODEL)
            cfg=resolve_profile(root)
            self.assertEqual(cfg['backend'],'ollama-qwen3-asr')
            self.assertEqual(cfg['model'],DEFAULT_MODEL)
            self.assertEqual(report['backend'],'ollama-qwen3-asr')
            self.assertIsInstance(create_engine(root),OllamaASREngine)
    def test_failed_switch_keeps_existing_profile_untouched(self):
        class Missing:
            def smoke_test(self):raise ASRBackendError('ASR_OLLAMA_MODEL_MISSING')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);original='{"version":1,"profile":"legacy"}'
            (root/PROFILE_FILE).write_text(original,encoding='utf-8')
            with self.assertRaises(ASRBackendError):install('ollama17',root=root,client=Missing())
            self.assertEqual((root/PROFILE_FILE).read_text(encoding='utf-8'),original)
    def test_next_start_selection_does_not_change_active_engine(self):
        class Fake:
            def __init__(self,model):self.model=model
            def smoke_test(self):return {'synthetic_audio_request_passed':True}
        with tempfile.TemporaryDirectory() as d:
            outcome=select_for_next_start(Path(d),{'profile':'ollama17','model':DEFAULT_MODEL},client_factory=Fake)
            self.assertEqual(outcome['applies'],'next_service_start')
            self.assertEqual(resolve_profile(Path(d))['profile'],'ollama17')
    def test_installer_routes_ollama_without_torch(self):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
        import install_all
        args = install_all.parse_args(['--profile','asr','--asr-profile','ollama17'])
        with tempfile.TemporaryDirectory() as d:
            worker = install_all.Installer(args,root=Path(d))
            worker.runtime_ok=True
            with patch.object(worker,'ollama_asr',return_value={'model':DEFAULT_MODEL}) as download, patch.object(worker,'command') as command:
                result=worker.asr()
            download.assert_called_once()
            self.assertEqual(result['selected_profile'],'ollama17')
            command.assert_called_once()
            commandline=' '.join(map(str,command.call_args.args[0]))
            self.assertIn('setup_asr_profile.py',commandline)
            self.assertNotIn('torch',commandline)
            self.assertNotIn('.venv-qwen',commandline)
            worker.log.close()
    def test_http_post_is_next_restart_only_and_authenticated(self):
        from server import asr_settings
        class Engine: profile_name='legacy';model_name='small'
        app=FastAPI();attach_asr_settings(app,engine=Engine());client=TestClient(app)
        headers={'origin':'chrome-extension://'+'a'*32}
        self.assertEqual(client.post('/asr/config',json={'profile':'legacy'}).status_code,403)
        with tempfile.TemporaryDirectory() as d:
            def mocked(root,body):
                return {'selected':'ollama17','model':DEFAULT_MODEL,'applies':'next_service_start',
                        'model_test':{'synthetic_audio_request_passed':True}}
            with patch.object(asr_settings,'select_for_next_start',side_effect=mocked):
                res=client.post('/asr/config',json={'profile':'ollama17','model':DEFAULT_MODEL},headers=headers)
            self.assertEqual(res.status_code,200)
            self.assertEqual(res.json()['active_profile'],'legacy')
            self.assertEqual(res.json()['selected'],'ollama17')
    def test_asr_cors_preflight_only_allows_extension_origins(self):
        from fastapi.middleware.cors import CORSMiddleware
        class Engine: profile_name='legacy'; model_name='small'
        app=FastAPI()
        app.add_middleware(CORSMiddleware,
            allow_origin_regex=r'chrome-extension://[a-p]{32}',
            allow_methods=['GET','POST'],
            allow_headers=['Content-Type','X-VKN-Extension-ID'],
            allow_credentials=False)
        attach_asr_settings(app,engine=Engine())
        client=TestClient(app)
        for origin, expected in [('chrome-extension://'+'a'*32,200),('https://untrusted.example',400)]:
            with self.subTest(origin=origin):
                r=client.options('/asr/config',headers={
                    'Origin':origin,'Access-Control-Request-Method':'POST',
                    'Access-Control-Request-Headers':'content-type,x-vkn-extension-id'})
                self.assertEqual(r.status_code,expected)
                self.assertEqual(r.headers.get('access-control-allow-origin'), origin if expected==200 else None)

    def test_http_get_with_extension_id_header_without_origin(self):
        # Some Chromium extension GET requests do not send the Origin header.
        # This request is not supposed to be interpreted as a public web origin.
        class Engine: profile_name='legacy'; model_name='small'
        app=FastAPI(); attach_asr_settings(app,engine=Engine()); client=TestClient(app)
        with patch('server.asr_settings.OllamaASRClient.list_models',return_value=[DEFAULT_MODEL]):
            response=client.get('/asr/config',headers={'X-VKN-Extension-ID':'a'*32})
        self.assertEqual(response.status_code,200)
        self.assertIn(DEFAULT_MODEL,response.json()['installed_ollama_asr_models'])

    def test_http_post_header_identified_extension_without_origin(self):
        from server import asr_settings
        class Engine: profile_name='legacy'; model_name='small'
        app=FastAPI(); attach_asr_settings(app,engine=Engine()); client=TestClient(app)
        with patch.object(asr_settings,'select_for_next_start',return_value={'selected':'ollama17','model':DEFAULT_MODEL}):
            response=client.post('/asr/config',json={'profile':'ollama17'},headers={'X-VKN-Extension-ID':'a'*32})
        self.assertEqual(response.status_code,200)

    def test_http_origin_header_cannot_be_bypassed_by_claiming_extension_id(self):
        class Engine: profile_name='legacy'; model_name='small'
        app=FastAPI(); attach_asr_settings(app,engine=Engine()); client=TestClient(app)
        spoofed=[
            {'origin':'https://untrusted.example','X-VKN-Extension-ID':'a'*32},
            {'origin':'null','X-VKN-Extension-ID':'a'*32},
            {'origin':'chrome-extension://'+'b'*32,'X-VKN-Extension-ID':'a'*32},
            {'X-VKN-Extension-ID':'invalid'},
        ]
        for headers in spoofed:
            with self.subTest(headers=headers):
                self.assertEqual(client.get('/asr/config',headers=headers).status_code,403)
                self.assertEqual(client.post('/asr/config',json={'profile':'legacy'},headers=headers).status_code,403)

    def test_http_route_requires_extension_origin(self):
        with tempfile.TemporaryDirectory() as d:
            class Engine: profile_name='legacy';model_name='small'
            app=FastAPI()
            attach_asr_settings(app,engine=Engine())
            client=TestClient(app)
            self.assertEqual(client.get('/asr/config').status_code,403)
            # GET uses real ROOT; only check the secure origin and shape.
            with patch('server.asr_settings.OllamaASRClient.list_models',return_value=[DEFAULT_MODEL]):
                r=client.get('/asr/config',headers={'origin':'chrome-extension://'+'a'*32})
            self.assertEqual(r.status_code,200)
            self.assertIn(DEFAULT_MODEL,r.json()['installed_ollama_asr_models'])

if __name__=='__main__':unittest.main()
