"""Quality guard logic only: no real speech/model accuracy measurements."""
import json, tempfile, pathlib, unittest
from types import SimpleNamespace as NS
import httpx
import numpy as np
from server.stream_store import StreamStore, Job, normalize_options
from server.stream_protocol import Packet, AUDIO, FINISH
from server.recognition import StreamingWhisperEngine
from server.text_enrichment import LocalTextEnricher, translation_warnings

SID='a'*32

def packet(n):
    return Packet(n,(n-1)*.2,n*.2,AUDIO,np.full(3200,300,dtype='<i2').tobytes())

def row(source='It is not certain.',lang='en',**options):
    return {'item':{'original':source,'text':source,'language':lang},'options':normalize_options(options)}

class GuardTests(unittest.TestCase):
    def test_negation_loss_is_flagged(self):
        self.assertTrue(translation_warnings('It is not true.','这是事实。'))
        self.assertFalse(translation_warnings('It is not true.','这不是真的。'))
    def test_contraction_not_lost(self):
        self.assertTrue(translation_warnings("I don't know.",'我知道。'))
    def test_modality_loss(self):
        self.assertTrue(translation_warnings('It might be a mistake.','这就是一个错误。'))
        self.assertFalse(translation_warnings('It might be a mistake.','这可能是一个错误。'))
    def test_numeric_change(self):
        self.assertTrue(translation_warnings('Use 3 samples.','使用8个样本。'))
    def test_direction_reversal(self):
        self.assertTrue(translation_warnings('Use less than 10 grams.','使用大于10克。'))
        self.assertTrue(translation_warnings('Use at least 10 grams.','使用最多10克。'))
    def test_percent_unit(self):
        self.assertTrue(translation_warnings('It is 10 percent.','它是10。'))
    def test_short_fragment_not_implicitly_complete(self):
        self.assertTrue(translation_warnings('because the model','因为模型完全正确。'))
    def test_idiomatic_negation_can_be_false_positive(self):
        self.assertTrue(translation_warnings('It is not uncommon.','这很常见。')) # labelled suspicion, never 'proven wrong'
    def test_other_languages_not_subject_to_english_negation_rules(self):
        self.assertFalse(translation_warnings('no es cierto.','这不是真的。','es'))
    def test_window_options_bounded(self):
        self.assertEqual(normalize_options({})['chunkSeconds'],12)
        self.assertEqual(normalize_options({'chunkSeconds':18})['chunkSeconds'],18)
        self.assertEqual(normalize_options({'chunkSeconds':999})['chunkSeconds'],12)
    def test_longer_window_keeps_overlap(self):
        with tempfile.TemporaryDirectory() as td:
            st=StreamStore(pathlib.Path(td)/'stream.db',min_free=0);st.open(SID,'test',{'chunkSeconds':12})
            for i in range(1,61):st.receive(SID,packet(i))
            self.assertIsNone(st.next_job(SID))
            for i in range(61,73):st.receive(SID,packet(i))
            job=st.next_job(SID);self.assertEqual(job.commit_seq,60);self.assertAlmostEqual(job.owner_end,12)
            self.assertGreater(len(job.pcm)/32000,14);st.close()
    def test_context_has_raw_only_and_respects_jumps(self):
        with tempfile.TemporaryDirectory() as td:
            st=StreamStore(pathlib.Path(td)/'stream.db',min_free=0);st.open(SID,'test',{})
            rows=[{'original':'previous raw','text':'old bad translation','time':1,'end':2,'contextEpoch':0},
                  {'original':'current raw','text':'target','time':2,'end':3,'contextEpoch':0},
                  {'original':'future raw','text':'another translation','time':3,'end':4,'contextEpoch':0}]
            with st.db:
                for i,c in enumerate(rows):st.db.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?)',(f'{SID}:1:{i}',SID,json.dumps(c),'done',0,0,i))
            r={'session':SID,'created':1,'item':rows[1]};ctx=st.text_context(r)
            self.assertEqual(ctx,{'previous':'previous raw','following':'future raw'})
            rows[1]['contextEpoch']=2;self.assertEqual(st.text_context(r),{'previous':'','following':''});st.close()
    def test_previous_recognized_text_not_refed(self):
        class Model:
            def __init__(self,*a,**kw):pass
            def transcribe(self,pcm,**opts):
                self.opts=opts;return iter([]),NS(language='zh',language_probability=.9)
        e=StreamingWhisperEngine(loader=Model);e.transcribe_job(Job(SID,[packet(1)],1,0,.2,{'hotwords':'LoRA'},'WRONG CONTEXT'))
        self.assertFalse(e._model.opts['condition_on_previous_text']);self.assertNotIn('WRONG CONTEXT',str(e._model.opts))
        self.assertIn('LoRA',str(e._model.opts))
    def test_diagnostic_flags_are_retained_not_silently_deleted(self):
        class Model:
            def __init__(self,*a,**kw):pass
            def transcribe(self,pcm,**opts):
                seg=NS(start=0,end=.2,text=' doubtful',words=[NS(start=0,end=.18,word=' doubtful',probability=.5)],avg_logprob=-1.2,no_speech_prob=.7,compression_ratio=3)
                return iter([seg]),NS(language='en',language_probability=.4)
        e=StreamingWhisperEngine(loader=Model);out=e.transcribe_job(Job(SID,[packet(1)],1,0,.2,{},''))
        self.assertEqual(out[0]['text'],'doubtful');self.assertTrue(out[0]['needsReview'])
        self.assertIn('possible_nonspeech',out[0]['qualityFlags']);self.assertEqual(out[0]['verificationStatus'],'machine_unverified')

class LocalTranslationTests(unittest.IsolatedAsyncioTestCase):
    def mock(self,value,requests=None):
        def handler(req):
            if requests is not None:requests.append(json.loads(req.content))
            self.assertEqual(req.url.host,'127.0.0.1')
            return httpx.Response(200,json={'message':{'content':json.dumps(value,ensure_ascii=False)}})
        return LocalTextEnricher(httpx.MockTransport(handler))
    async def test_bad_negation_candidate_does_not_replace_original(self):
        r=row();out=await self.mock({'chinese_text':'这是确定的。'}).process(r)
        self.assertEqual(out['text'],'It is not certain.');self.assertEqual(out['translation'],'这是确定的。')
        self.assertEqual(out['translationStatus'],'needs_review');self.assertTrue(out['needsReview'])
    async def test_low_asr_score_not_made_trusted_by_translation(self):
        r=row('Use 3 samples.');r['item'].update(needsReview=True,reviewReason='模型分数低')
        out=await self.mock({'chinese_text':'使用3个样本。'}).process(r)
        self.assertEqual(out['text'],'Use 3 samples.');self.assertEqual(out['translationStatus'],'needs_review')
    async def test_unflagged_still_not_verified(self):
        out=await self.mock({'chinese_text':'这不确定。'}).process(row())
        self.assertEqual(out['text'],'这不确定。');self.assertEqual(out['verificationStatus'],'machine_unverified')
    async def test_correction_is_suggestion_not_overwrite(self):
        r=row('量子纠产会产生关联','zh',correct=True)
        out=await self.mock({'corrected_text':'量子纠缠会产生关联'}).process(r)
        self.assertEqual(out['text'],'量子纠产会产生关联');self.assertEqual(out['corrected'],'量子纠缠会产生关联')
        self.assertEqual(out['correctionStatus'],'suggested')
    async def test_correction_not_translation_source(self):
        calls=[]
        def handler(req):
            data=json.loads(req.content);calls.append(data)
            if len(calls)==1:value={'chinese_text':'这不确定。'}
            else:value={'corrected_text':'It is certainly true.'}
            return httpx.Response(200,json={'message':{'content':json.dumps(value)}})
        r=row(correct=True);out=await LocalTextEnricher(httpx.MockTransport(handler)).process(r)
        self.assertEqual(len(calls),2);self.assertEqual(json.loads(calls[0]['messages'][1]['content'])['text'],r['item']['original'])
        self.assertEqual(out['original'],r['item']['original']);self.assertEqual(out['translation'],'这不确定。')
    async def test_unknown_language_no_invented_translation(self):
        r=row('unknown utterance','unknown');calls=[]
        out=await self.mock({'chinese_text':'胡编译文'},calls).process(r)
        self.assertEqual(calls,[]);self.assertEqual(out['text'],r['item']['original']);self.assertEqual(out['translationStatus'],'needs_review')
    async def test_optional_correction_failure_does_not_erase_translation(self):
        calls=[]
        def handler(req):
            calls.append(req)
            if len(calls)==1:return httpx.Response(200,json={'message':{'content':'{"chinese_text":"这不确定。"}'}})
            return httpx.Response(500,text='unavailable')
        out=await LocalTextEnricher(httpx.MockTransport(handler)).process(row(correct=True))
        self.assertEqual(out['translation'],'这不确定。');self.assertEqual(out['correctionStatus'],'failed')
    async def test_context_structure_and_schema(self):
        calls=[];await self.mock({'chinese_text':'这不确定。'},calls).process(row(),{'previous':'Raw before.','following':'Raw after.'})
        self.assertIsInstance(calls[0]['format'],dict)
        v=json.loads(calls[0]['messages'][1]['content']);self.assertEqual(v['following_context'],'Raw after.')
        self.assertNotIn('api_key',calls[0]);self.assertEqual(calls[0]['options']['temperature'],0)

if __name__=='__main__':unittest.main()
