"""V0.5 regression tests. Model outputs are fixtures, not an accuracy benchmark."""
import asyncio, json, os, pathlib, tempfile, time, unittest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace
import numpy as np
import httpx
from server.stream_protocol import Packet,decode,AUDIO,BOUNDARY,FINISH
from server.stream_store import StreamStore,Job,normalize_options
from server.recognition import StreamingWhisperEngine
from server.text_enrichment import safe_correction,validate_translation,LocalTextEnricher
from server.lora_service import merge_natural_language_rule,visual_instructions

SID='b'*32

def packet(seq,t=None,flag=0,duration=.6,rate=1):
    t=(seq-1)*duration if t is None else t
    return Packet(seq,t,t+duration*rate if flag==0 else t,flag,np.full(int(duration*16000),300,dtype='<i2').tobytes() if flag==0 else b'')

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=pathlib.Path(self.tmp.name)/'cache.db';self.s=StreamStore(self.path,min_free=0);self.s.open(SID,'yt:test',{'translate':False,'chunkSeconds':6})
    def tearDown(self):self.s.close();self.tmp.cleanup()
    def test_wire_roundtrip(self):
        p=packet(1);self.assertEqual(decode(p.encode()),p)
    def test_bad_wire(self):
        for b in (b'x',b'VKN2'+packet(1).encode()[4:],Packet(1,0,float('nan'),0,b'aa').encode(),Packet(1,2,1,0,b'aa').encode()):
            with self.assertRaises(ValueError):decode(b)
    def test_ack_is_durable(self):
        self.s.receive(SID,packet(1));self.s.close();self.s=StreamStore(self.path,min_free=0)
        self.assertEqual(self.s.session(SID)['received'],1);self.assertGreater(self.s.stats(SID)['pendingSeconds'],0)
    def test_duplicate_idempotent_and_mismatch_denied(self):
        p=packet(1);self.s.receive(SID,p);self.assertEqual(self.s.receive(SID,p),1)
        with self.assertRaises(ValueError):self.s.receive(SID,packet(1,t=3))
    def test_sequence_gap_not_acknowledged(self):
        with self.assertRaises(ValueError):self.s.receive(SID,packet(2))
        self.assertEqual(self.s.session(SID)['received'],0)
    def test_full_cache_backpressures_without_ack(self):
        self.s.max_bytes=5
        with self.assertRaises(BufferError):self.s.receive(SID,packet(1))
        self.assertEqual(self.s.session(SID)['received'],0)
    def test_no_window_until_right_context(self):
        for i in range(1,11):self.s.receive(SID,packet(i))
        self.assertIsNone(self.s.next_job(SID))
        for i in [11,12]:self.s.receive(SID,packet(i))
        j=self.s.next_job(SID);self.assertEqual(j.commit_seq,10);self.assertAlmostEqual(j.owner_end,6)
    def test_subsecond_tail_is_transcribed_on_finish(self):
        self.s.receive(SID,packet(1,duration=.2));self.s.receive(SID,packet(2,t=.2,flag=FINISH))
        j=self.s.next_job(SID);self.assertEqual(len(j.pcm),6400);self.s.commit(j,[])
        j=self.s.next_job(SID);self.assertTrue(j.final);self.s.commit(j,[]);self.assertTrue(self.s.stats(SID)['finished'])
    def test_pause_is_ordered_and_does_not_join_new_context(self):
        self.s.receive(SID,packet(1));self.s.receive(SID,packet(2,t=.6,flag=BOUNDARY));self.s.receive(SID,packet(3,t=30));self.s.receive(SID,packet(4,t=30.6,flag=FINISH))
        j=self.s.next_job(SID);self.assertEqual(j.commit_seq,1);self.s.commit(j,[])
        self.s.commit(self.s.next_job(SID),[])
        j=self.s.next_job(SID);self.assertEqual(j.packets[0].start,30);self.assertEqual(j.context,'')
    def test_playback_rate_mapping(self):
        p=packet(1,t=100,duration=.6,rate=2);j=Job(SID,[p],1,0,.6,{},'')
        self.assertAlmostEqual(j.media_time(.3),100.6)
    def test_committed_audio_removed_and_duplicates_still_verifiable(self):
        for i in range(1,31):self.s.receive(SID,packet(i))
        j=self.s.next_job(SID);self.s.commit(j,[{'time':0,'text':'原文','language':'zh'}])
        self.assertIsNone(self.s.db.execute('SELECT pcm FROM packets WHERE seq=1').fetchone()[0]);self.assertEqual(self.s.receive(SID,packet(1)),30)
        self.assertEqual(self.s.events(SID)[0]['original'],'原文')
    def test_failure_keeps_audio_and_watermark(self):
        self.s.receive(SID,packet(1));self.s.fail(SID,'fixture error')
        self.assertEqual(self.s.session(SID)['processed'],0);self.assertGreater(self.s.stats(SID)['pendingSeconds'],0)
    def test_result_replay_keeps_id(self):
        self.s.receive(SID,packet(1));self.s.receive(SID,packet(2,t=.6,flag=FINISH));self.s.commit(self.s.next_job(SID),[{'time':0,'text':'ok','language':'en'}])
        a=self.s.events(SID);self.s.close();self.s=StreamStore(self.path,min_free=0);self.assertEqual(self.s.events(SID)[0]['id'],a[0]['id'])
    def test_completed_session_rejects_more_audio(self):
        self.s.receive(SID,packet(1,t=0,flag=FINISH))
        with self.assertRaises(ValueError):self.s.receive(SID,packet(2))
    def test_options_sanitized(self):
        o=normalize_options({'textModel':'unsafe-cloud','language':'oops','translate':False});self.assertEqual(o['textModel'],'qwen2.5:3b');self.assertEqual(o['language'],'auto');self.assertFalse(o['translate'])

class RecognitionTests(unittest.TestCase):
    def test_overlap_words_owned_once(self):
        class Model:
            def __init__(self,*a,**kw):pass
            def transcribe(self,pcm,**opts):
                self.opts=opts
                words=[SimpleNamespace(start=.1,end=.6,word=' old',probability=.9),SimpleNamespace(start=1.5,end=2,word=' fresh',probability=.8),SimpleNamespace(start=7.5,end=8,word=' next',probability=.9)]
                return iter([SimpleNamespace(words=words)]),SimpleNamespace(language='en',language_probability=.98)
        engine=StreamingWhisperEngine(loader=Model)
        j=Job(SID,[packet(1,t=0,duration=2),packet(2,t=2,duration=2),packet(3,t=4,duration=2),packet(4,t=6,duration=2)],3,1.2,7.2,{'hotwords':'LoRA'},'context')
        result=engine.transcribe_job(j)
        self.assertEqual(result[0]['text'],'fresh');self.assertTrue(engine._model.opts['word_timestamps']);self.assertEqual(engine._model.opts['task'],'transcribe');self.assertEqual(engine._model.opts['hotwords'],'LoRA')
    def test_exact_digital_silence_no_load(self):
        e=StreamingWhisperEngine(loader=lambda *a,**kw:None);j=Job(SID,[Packet(1,0,.5,0,b'\0'*16000)],1,0,.5,{},'');self.assertEqual(e.transcribe_job(j),[]);self.assertFalse(e.loaded)

class TextTests(unittest.IsolatedAsyncioTestCase):
    def test_correction_guard(self):
        self.assertEqual(safe_correction('今天讲洛拉训练。','今天讲LoRA训练。')[0],'今天讲洛拉训练。') # conservative ratio rejects large edits
        self.assertEqual(safe_correction('损失是10元','损失是100元')[0],'损失是10元')
        self.assertEqual(safe_correction('量子纠产会产生关联','量子纠缠会产生关联')[0],'量子纠缠会产生关联')
    def test_translation_guard(self):
        self.assertEqual(validate_translation('Use 3 samples.','使用3个样本。'),'使用3个样本。')
        with self.assertRaises(ValueError):validate_translation('Use 3 samples.','使用8个样本。')
        with self.assertRaises(ValueError):validate_translation('Hi','Hello')
    async def test_translation_preserves_original_and_local_request(self):
        def handler(req):
            self.assertEqual(req.url.host,'127.0.0.1');body=json.loads(req.content);self.assertFalse(body['stream'])
            return httpx.Response(200,json={'message':{'content':json.dumps({'corrected_text':'Use 3 samples.','chinese_text':'使用3个样本。'})}})
        row={'item':{'original':'Use 3 samples.','text':'Use 3 samples.','language':'en'},'options':normalize_options({})}
        got=await LocalTextEnricher(httpx.MockTransport(handler)).process(row)
        self.assertEqual(got['original'],'Use 3 samples.');self.assertEqual(got['text'],'使用3个样本。');self.assertEqual(got['translationStatus'],'done')
    async def test_bad_translation_keeps_stored_original(self):
        row={'item':{'original':'Use 3 samples.','text':'Use 3 samples.','language':'en'},'options':normalize_options({})}
        def handler(req):return httpx.Response(200,json={'message':{'content':'{"chinese_text":"使用8个样本"}'}})
        got=await LocalTextEnricher(httpx.MockTransport(handler)).process(row)
        self.assertEqual(got['translationStatus'],'needs_review')
        self.assertEqual(got['text'],'Use 3 samples.')
        self.assertEqual(got['translation'],'使用8个样本')
        self.assertEqual(row['item']['original'],'Use 3 samples.')
    async def test_lora_plan_does_not_load_model(self):
        with patch('server.lora_service.httpx.AsyncClient',side_effect=AssertionError('model call forbidden')):
            rule=await merge_natural_language_rule(None,'只要清晰人物正面，每3秒一帧，最多80张')
            self.assertEqual(rule['interval_seconds'],3);self.assertEqual(rule['max_frames'],80)
            r=await merge_natural_language_rule(rule,'改为侧面，每5秒一帧')
            self.assertEqual(r['interval_seconds'],5);self.assertEqual(r['max_frames'],80);self.assertEqual(len(r['instructions']),2)
            self.assertIn('以后者为准',visual_instructions(r))

if __name__=='__main__':unittest.main()
