"""ASR-adapter tests. No real weights, CUDA, network or model-quality claims."""
from __future__ import annotations
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from server.asr_profiles import resolve_profile,create_engine,PROFILES,PROFILE_FILE
from server.qwen_protocol import (ASRBackendError,decode_request,language_code,language_name,
                                  align_words,select_owned,build_segments,RATE)
from server.qwen_worker import recognize
from server.qwen_engine import JsonWorker,QwenEngine
from server.stream_store import Job,StreamStore
from server.stream_protocol import Packet,FINISH
from server.speaker import SpeakerAnnotator
import setup_asr_profile
import qwen_model_setup
import install_all
import evaluate_asr


def req(seconds=2,a=0,b=2,**kw):
    return {'op':'transcribe','pcm16':base64.b64encode(b'\1\0'*int(RATE*seconds)).decode(),
            'owner_start':a,'owner_end':b,**kw}

def job():
    return Job('a'*32,[Packet(1,10,12,0,b'\1\0'*(RATE*2))],1,0,2,{'translate':True,'diarize':False,'correct':False},'')

class Profiles(unittest.TestCase):
    def test_default_preserves_environment(self):
        with tempfile.TemporaryDirectory() as d:
            r=resolve_profile(d,{'VKN_ASR_MODEL':'base','VKN_ASR_DEVICE':'cpu','VKN_ASR_COMPUTE':'int8'})
        self.assertEqual(r['model'],'base');self.assertEqual(r['profile'],'legacy')
    def test_qwen_explicit_no_whisper_override(self):
        with tempfile.TemporaryDirectory() as d:
            setup_asr_profile.activate(d,'qwen17')
            r=resolve_profile(d,{'VKN_ASR_MODEL':'tiny'})
            self.assertEqual(r['model'],'Qwen/Qwen3-ASR-1.7B-hf')
            e=create_engine(d);self.assertIsInstance(e,QwenEngine);self.assertFalse(e.loaded);e.close()
    def test_unknown_profile_not_silently_downgraded(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,PROFILE_FILE).write_text('{"version":1,"profile":"made-up"}')
            with self.assertRaises(ValueError):resolve_profile(d)
    def test_invalid_profile_not_silently_downgraded(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,PROFILE_FILE).write_text('[]')
            with self.assertRaises(ValueError):resolve_profile(d)
    def test_activation_backup_and_legacy(self):
        with tempfile.TemporaryDirectory() as d:
            settings=Path(d,'ASR_SETTINGS.bat');settings.write_bytes(b'original')
            setup_asr_profile.activate(d,'qwen17');setup_asr_profile.activate(d,'legacy')
            self.assertEqual(resolve_profile(d,{})['profile'],'legacy')
            self.assertEqual(settings.read_bytes(),b'original')
            self.assertEqual(len(list(Path(d,'diagnostics/install/asr-profile-backups').glob('*.json'))),1)
    def test_failed_load_never_activates(self):
        with tempfile.TemporaryDirectory() as d:
            setup_asr_profile.activate(d,'legacy');before=Path(d,PROFILE_FILE).read_bytes()
            def runner(cmd,**kwargs):
                if '--smoke' in cmd:raise subprocess.CalledProcessError(1,cmd)
            with patch.object(setup_asr_profile,'ensure_qwen_env',return_value=Path(d)/'.venv-qwen/python'):
                with self.assertRaises(subprocess.CalledProcessError):setup_asr_profile.install('qwen17',root=d,runner=runner)
            self.assertEqual(Path(d,PROFILE_FILE).read_bytes(),before)
    def test_activate_after_same_worker_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            calls=[]
            with patch.object(setup_asr_profile,'ensure_qwen_env',return_value=Path(d)/'py'):
                setup_asr_profile.install('qwen06',root=d,runner=lambda c,**k:calls.append(list(map(str,c))))
            self.assertIn('server.qwen_worker',calls[-1]);self.assertIn('--smoke',calls[-1])
            self.assertEqual(resolve_profile(d,{})['profile'],'qwen06')
    def test_one_entry_plan_no_download(self):
        a=install_all.parse_args(['--profile','asr','--asr-profile','qwen17','--plan'])
        plan=install_all.plan(a.profile,a.asr_model,a.asr_profile)
        self.assertTrue(any('qwen17' in x['description'] for x in plan))
    def test_incomplete_local_model_does_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'config.json').write_text('{}');self.assertFalse(qwen_model_setup.complete(d))
    def test_native_repositories_not_ollama_models(self):
        self.assertTrue(all(PROFILES[x]['model'].endswith('-hf') for x in ('qwen17','qwen06')))

    def test_legacy_rollback_does_not_probe_or_download(self):
        with tempfile.TemporaryDirectory() as d:
            args=install_all.parse_args(['--profile','asr','--asr-profile','legacy'])
            runner=install_all.Installer(args,root=Path(d))
            with patch.object(runner,'network_report') as network, patch.object(runner,'command',return_value=None) as command, patch.object(install_all,'port_active',return_value=False):
                self.assertEqual(runner.run(),0)
                network.assert_not_called()
                self.assertTrue(any('legacy' in call.args[0] for call in command.call_args_list))
    def test_reference_metric_no_semantic_score_claim(self):
        self.assertEqual(evaluate_asr.edit_distance('中国','中果'),1)
        self.assertEqual(evaluate_asr.normalized('Hello, 世界！'),'hello世界')

class Protocol(unittest.TestCase):
    def test_languages(self):
        self.assertEqual(language_code('Spanish'),'es');self.assertEqual(language_code('Portuguese'),'pt')
        self.assertEqual(language_name('zh'),'Chinese');self.assertIsNone(language_name('auto'))
        self.assertEqual(language_code('Chinese,English'),'unknown')
    def test_decode(self):
        pcm,a,b,lang,terms=decode_request(req(language='es',hotwords='hola'))
        self.assertEqual(len(pcm),RATE*4);self.assertEqual(lang,'Spanish');self.assertEqual(terms,'hola')
    def test_bad_base64(self):
        with self.assertRaises(ASRBackendError):decode_request({**req(),'pcm16':'not valid !'})
    def test_owner_not_outside_audio(self):
        for a,b in [(-1,1),(0,3),(1,1),(float('nan'),2)]:
            with self.subTest(a=a,b=b),self.assertRaises(ASRBackendError):decode_request(req(a=a,b=b))
    def test_size_limit(self):
        with self.assertRaises(ASRBackendError):decode_request(req(41,0,41))
    def test_no_remote_audio_path(self):
        with self.assertRaises(ASRBackendError):decode_request({'op':'transcribe','path':'https://example.test/a.wav'})
    def test_alignment_preserves_words_punctuation_and_spaces(self):
        text='Hello, world!'
        words=align_words(text,[{'text':'Hello','start_time':0,'end_time':.7},{'text':'world','start_time':.7,'end_time':1.5}],2)
        self.assertEqual(''.join(w['word'] for w in words),text)
    def test_alignment_coverage_is_exact(self):
        with self.assertRaises(ASRBackendError):align_words('one two',[{'text':'one','start_time':0,'end_time':1}],2)
    def test_bad_timing(self):
        for end in [float('nan'),100,-1]:
            with self.subTest(end=end),self.assertRaises(ASRBackendError):
                align_words('hello',[{'text':'hello','start_time':0,'end_time':end}],2)
    def test_disjoint_midpoint_ownership(self):
        words=align_words('你好',[{'text':'你','start_time':0,'end_time':1},{'text':'好','start_time':1,'end_time':2}],2)
        a=select_owned(words,0,1);b=select_owned(words,1,2)
        self.assertEqual(''.join(w['word'] for w in a+b),'你好')
        self.assertFalse({w['word'] for w in a}&{w['word'] for w in b})
    def test_scores_unknown_not_fabricated(self):
        r=build_segments(job(),{'segments':[{'text':'Hola','language':'Spanish','start':0,'end':2,'words':[]}]},'test','cuda:0')[0]
        self.assertIsNone(r['confidence']);self.assertIsNone(r['languageProbability'])
        self.assertEqual(r['language'],'es');self.assertEqual(r['time'],10)
    def test_response_invalid_range(self):
        with self.assertRaises(ASRBackendError):build_segments(job(),{'segments':[{'text':'x','start':-5,'end':0}]},'x','cpu')

class FakeRuntime:
    np=np
    def __init__(self,text='Hello, world!',lang='English',bad_align=False):
        self.text,self.lang,self.bad_align=text,lang,bad_align;self.calls=[]
    def transcribe(self,audio,language,terms):
        self.calls.append((len(audio),language,terms));return self.text,self.lang
    def align(self,audio,text,language):
        if self.bad_align:raise ValueError('synthetic aligner failure')
        return [{'text':'Hello','start_time':0,'end_time':1},{'text':'world','start_time':1,'end_time':2}]

class WindowIntegration(unittest.TestCase):
    def test_aligned_path_and_context(self):
        r=FakeRuntime();out=recognize(r,req(hotwords='test'))
        self.assertEqual(out['segments'][0]['text'],'Hello, world!')
        self.assertEqual(out['alignment'],'aligned_words');self.assertEqual(len(r.calls),1)
    def test_no_alignment_uses_owned_audio_not_full_overlap(self):
        r=FakeRuntime(bad_align=True);out=recognize(r,req(a=.5,b=1.5))
        self.assertEqual([x[0] for x in r.calls],[RATE*2,RATE])
        item=out['segments'][0];self.assertFalse(item['words']);self.assertEqual(item['start'],.5)
        self.assertIn('word_timestamps_missing',item['flags'])
    def test_unsupported_alignment_language_not_forced_english(self):
        r=FakeRuntime('مرحبا','Arabic');out=recognize(r,req(a=.5,b=1.5))
        self.assertEqual(out['segments'][0]['language'],'Arabic')
        self.assertFalse(out['segments'][0]['words'])
    def test_silence_does_not_invoke_model(self):
        r=FakeRuntime();request=req();request['pcm16']=base64.b64encode(bytes(RATE*4)).decode()
        self.assertEqual(recognize(r,request)['segments'],[]);self.assertFalse(r.calls)
    def test_repetition_flag_not_content_deletion(self):
        text='重复的话'*7;r=FakeRuntime(text,'Chinese',bad_align=True)
        out=recognize(r,req());self.assertEqual(out['segments'][0]['text'],text)
        self.assertIn('asr_repetition_suspected',out['segments'][0]['flags'])
    def test_qwen_original_language_commits_then_translation_pending(self):
        class Bridge:
            status={'loaded':True}
            def call(self,payload):
                self.payload=payload
                return {'segments':[{'text':'Hola mundo','language':'Spanish','start':0,'end':2,'words':[]}]}
            def close(self):pass
        with tempfile.TemporaryDirectory() as d:
            j=job();store=StreamStore(Path(d)/'audio.sqlite3',min_free=0)
            try:
                store.open(j.session,'test-video',j.options);store.receive(j.session,j.packets[0])
                cfg={'profile':'qwen17',**PROFILES['qwen17']};bridge=Bridge()
                engine=QwenEngine(cfg,root=Path(d),bridge=bridge)
                segments=SpeakerAnnotator().annotate(j,engine.transcribe_job(j));store.commit(j,segments)
                rows=store.events(j.session,0);item=next(x for x in rows if x['type']=='segment')
                self.assertEqual(item['original'],'Hola mundo');self.assertEqual(item['translationStatus'],'pending')
                self.assertEqual(item['asrEngine'],'qwen3-native');self.assertNotIn('context',bridge.payload)
            finally:store.close()
    def test_missing_runtime_no_silent_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            e=QwenEngine({'profile':'qwen17',**PROFILES['qwen17']},root=Path(d))
            try:
                with self.assertRaisesRegex(ASRBackendError,'ASR_RUNTIME_MISSING'):e.transcribe_job(job())
            finally:e.close()

# Real child process/stdio checks. The child emits fixed fixtures, NOT ASR.
FAKE_CHILD='''import json,sys,time
mode=sys.argv[1]
if mode=="badhello":
 print("not-json",flush=True);time.sleep(1);sys.exit()
print(json.dumps({"type":"ready","protocol":1,"device":"fixture"}),flush=True)
for line in sys.stdin:
 r=json.loads(line)
 if mode=="timeout":time.sleep(4)
 if mode=="exit":sys.exit(2)
 print(json.dumps({"id":("wrong" if mode=="wrongid" else r["id"]),"ok":True,"segments":[],"audio_seconds":2}),flush=True)
'''
class ChildTransport(unittest.TestCase):
    def make(self,d,mode):
        p=Path(d)/'fixture.py';p.write_text(FAKE_CHILD)
        return JsonWorker([sys.executable,'-u',str(p),mode],cwd=d,load_timeout=2,request_timeout=.15)
    def test_real_stdio_request_and_close(self):
        with tempfile.TemporaryDirectory() as d:
            b=self.make(d,'ok');result=b.call(req());pid=b._proc
            self.assertTrue(result['ok']);self.assertTrue(b.status['loaded']);b.close()
            self.assertIsNotNone(pid.poll())
    def test_response_id_checked(self):
        with tempfile.TemporaryDirectory() as d:
            b=self.make(d,'wrongid')
            try:
                with self.assertRaisesRegex(ASRBackendError,'RESPONSE_ID'):b.call(req())
            finally:b.close()
    def test_deadline_terminates_only_owned_child(self):
        with tempfile.TemporaryDirectory() as d:
            b=self.make(d,'timeout');start=time.monotonic()
            try:
                with self.assertRaisesRegex(ASRBackendError,'TIMEOUT'):b.call(req())
                self.assertLess(time.monotonic()-start,3);self.assertIsNone(b._proc)
            finally:b.close()
    def test_worker_exit_does_not_commit_success(self):
        with tempfile.TemporaryDirectory() as d:
            b=self.make(d,'exit')
            try:
                with self.assertRaises(ASRBackendError):b.call(req())
                self.assertFalse(b.status['loaded'])
            finally:b.close()
    def test_bad_handshake_does_not_get_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            b=self.make(d,'badhello')
            try:
                with self.assertRaisesRegex(ASRBackendError,'PROTOCOL'):b.call(req())
            finally:b.close()

if __name__=='__main__':unittest.main()
