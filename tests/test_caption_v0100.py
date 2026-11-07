"""Deterministic captions/validation routes. Vision replies and phonetics are fixtures."""
import asyncio, base64, copy, io, json, unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
from PIL import Image, ImageDraw
from server import caption_review as R
from server.context_review import validate as review
SID='b'*32
OWNER='chrome-extension://'+'a'*32

def cue(**kw):
    return dict(id=SID+':1:0',time=1.,end=5.,contextEpoch=0,language='zh',original='人们很害怕位置的事情',text='人们很害怕位置的事情',**kw)
def obs(**kw):
    d=dict(id='cap1',stream=SID,epoch=0,text='人们很害怕未知的事情',start=1.,end=3.,source='visible',samples=3,seenSpan=1.,kind='unknown');d.update(kw);return d

def check(a,b):return (a,b) in [('位置','未知'),('生','身'),('治','自')]
def run(c=None,observations=None):return R.validate({'items':[{'cue':c or cue(),'evidence':observations or [obs()]}]},checker=check)['reviews']

class CaptionValidation(unittest.TestCase):
    def test_homophone_applied_without_overwriting_raw(self):
        c=cue();r=run(c)[0];self.assertEqual(r['status'],'applied');self.assertEqual(r['text'],'人们很害怕未知的事情');self.assertEqual(c['original'],'人们很害怕位置的事情')
    def test_candidate_does_not_replace_whole_window(self):
        c=cue();c['original']='前面先介绍节目。人们很害怕位置的事情后面还有一些独立内容。';c['text']=c['original'];r=run(c)[0];self.assertEqual(r['status'],'applied');self.assertTrue(r['text'].startswith('前面先介绍节目。'));self.assertTrue(r['text'].endswith('后面还有一些独立内容。'))
    def test_no_cross_video(self):self.assertEqual(run(observations=[obs(stream='c'*32)]),[])
    def test_no_cross_seek(self):self.assertEqual(run(observations=[obs(epoch=3)]),[])
    def test_no_future_subtitle(self):self.assertEqual(run(observations=[obs(start=8.,end=9.)]),[])
    def test_no_old_subtitle(self):self.assertEqual(run(observations=[obs(start=0.,end=.2)]),[])
    def test_single_frame_not_auto_applied(self):self.assertEqual(run(observations=[obs(samples=1,seenSpan=0.)])[0]['status'],'candidate')
    def test_static_logo_not_accepted(self):self.assertEqual(run(observations=[obs(start=0.,end=25.)])[0]['status'],'candidate')
    def test_auto_asr_caption_not_independent_evidence(self):self.assertEqual(run(observations=[obs(kind='automatic')])[0]['status'],'candidate')
    def test_translated_caption_does_not_replace_foreign_speech(self):
        c=cue();c.update(language='en',original='People fear what is unknown.',text='人们害怕未知');self.assertNotEqual(run(c)[0]['status'],'applied')
    def test_english_caption_does_not_replace_chinese(self):self.assertNotEqual(run(observations=[obs(text='People fear what is unknown.')])[0]['status'],'applied')
    def test_large_mismatch_only_candidate(self):self.assertEqual(run(observations=[obs(text='请访问官方网站并订阅我们的频道')])[0]['status'],'candidate')
    def test_repeated_match_ambiguous_not_applied(self):
        c=cue();c['original']=c['original']*3;c['text']=c['original'];self.assertNotEqual(run(c)[0]['status'],'applied')
    def test_digits_protected(self):
        c=cue();c.update(original='这里总共有三个人在说话',text='这里总共有三个人在说话');r=run(c,[obs(text='这里总共有四个人在说话')])[0];self.assertNotEqual(r['status'],'applied')
    def test_negation_insertion_not_auto_applied(self):
        c=cue();c.update(original='我认为这件事是完全正确的',text='我认为这件事是完全正确的');r=run(c,[obs(text='我认为这件事不是完全正确的')])[0];self.assertNotEqual(r['status'],'applied')
    def test_name_context_protected(self):
        c=cue();c.update(original='他的名字叫位置今天来参加节目',text='他的名字叫位置今天来参加节目');self.assertNotEqual(run(c,[obs(text='他的名字叫未知今天来参加节目')])[0]['status'],'applied')
    def test_human_text_protected(self):self.assertNotEqual(run(cue(manuallyEdited=True))[0]['status'],'applied')
    def test_exact_caption_agrees_no_rewrite(self):self.assertEqual(run(observations=[obs(text=cue()['text'])])[0]['status'],'agrees')
    def test_missing_pinyin_becomes_candidate(self):
        with patch.object(R,'phonetic_equal',side_effect=ImportError):
            r=R.validate({'items':[{'cue':cue(),'evidence':[obs()]}]})['reviews'][0];self.assertEqual(r['status'],'candidate')
    def test_limit_rejects_oversized_items(self):
        with self.assertRaises(ValueError):R.validate({'items':[{}]*25})
    def test_nonnumeric_time_dropped(self):
        c=cue();c['time']='bad';self.assertEqual(run(c),[])
    def test_frame_quality_blank_rejected(self):
        im=Image.new('RGB',(500,100));b=io.BytesIO();im.save(b,'JPEG')
        with self.assertRaisesRegex(ValueError,'BLANK'):R.decode_image({'image':'data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()})
    def test_external_image_url_is_rejected(self):
        with self.assertRaises(ValueError):R.decode_image({'image':'http://example.test/image.jpg'})

class CaptionRouteTests(unittest.TestCase):
    def setUp(self):
        app=FastAPI();R.attach_caption_routes(app);self.client=TestClient(app)
    def test_origin_required(self):self.assertEqual(self.client.post('/caption-review/validate',json={}).status_code,403)
    def test_wrong_type_denied(self):self.assertEqual(self.client.post('/caption-review/validate',content='{}',headers={'origin':OWNER,'content-type':'text/plain'}).status_code,415)
    def test_validate_real_route(self):
        with patch.object(R,'phonetic_equal',side_effect=check):
            r=self.client.post('/caption-review/validate',json={'items':[{'cue':cue(),'evidence':[obs()]}]},headers={'origin':OWNER});self.assertEqual(r.status_code,200);self.assertEqual(r.json()['reviews'][0]['status'],'applied')
    def test_missing_pair_reports_error(self):self.assertEqual(self.client.post('/caption-review/frames',json={'frames':[]},headers={'origin':OWNER}).status_code,400)

class CaptionVisionTests(unittest.IsolatedAsyncioTestCase):
    def frames(self):
        im=Image.new('RGB',(600,100),'black');ImageDraw.Draw(im).rectangle((10,30,550,70),fill='white');b=io.BytesIO();im.save(b,'JPEG');uri='data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()
        return [{'image':uri,'time':1+i*.5,'stream':SID,'epoch':0} for i in range(2)]
    async def test_pair_disagreements_not_claimed_stable(self):
        def handler(req):
            data=json.loads(req.content);self.assertEqual(data['model'],'qwen2.5vl:3b');self.assertEqual(len(data['messages'][1]['images']),2);self.assertNotIn('位置',json.dumps(data,ensure_ascii=False))
            return httpx.Response(200,json={'done':True,'message':{'content':json.dumps({'frames':[{'index':0,'lines':['第一句原始字幕']},{'index':1,'lines':['第二句原始字幕']}]})}})
        out=await R.extract_frames({'frames':self.frames()},lambda:httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        self.assertEqual(len(out['observations']),2);self.assertEqual(out['observations'][0]['samples'],1)
    async def test_stable_pair_returns_timestamped_hashes_not_images(self):
        def handler(req):return httpx.Response(200,json={'done':True,'message':{'content':json.dumps({'frames':[{'index':0,'lines':['这是测试字幕']},{'index':1,'lines':['这是测试字幕']}]})}})
        out=await R.extract_frames({'frames':self.frames()},lambda:httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        o=out['observations'][0];self.assertEqual(len(out['observations']),1);self.assertEqual(o['samples'],2);self.assertEqual(o['seenSpan'],.5);self.assertNotIn('image',o);self.assertEqual(len(o['frameHashes']),2)
    async def test_truncated_vision_output_not_used(self):
        def handler(req):return httpx.Response(200,json={'done_reason':'length','message':{'content':'{}'}})
        with self.assertRaisesRegex(ValueError,'INCOMPLETE'):await R.extract_frames({'frames':self.frames()},lambda:httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    async def test_pair_cross_boundary_rejected(self):
        frames=self.frames();frames[1]['epoch']=1
        with self.assertRaisesRegex(ValueError,'CHANGED'):await R.extract_frames({'frames':frames})

class CrossCueContextTests(unittest.TestCase):
    def test_short_homophone_has_cross_cue_evidence(self):
        item={'id':'cue-1','text':'位置','contextBefore':'我们害怕的是','contextAfter':'因为不知道下一刻会发生什么'}
        e={'id':'cue-1','before':'位置','after':'未知','kind':'common_term','confidence':.99,'evidence':'我们害怕的是 位置 因为不知道','reason':'后文描述无法预知，词义应为未知而非地点位置'}
        r=review({'items':[item],'edits':[e]},checker=check);self.assertEqual(r['applied'][0]['start'],0);self.assertEqual(r['applied'][0]['after'],'未知')
    def test_wrong_neighbor_only_evidence_not_authorized(self):
        item={'id':'cue-1','text':'这里提到了位置这个词','contextBefore':'另一个人说害怕位置并不合理'}
        e={'id':'cue-1','before':'位置','after':'未知','kind':'common_term','confidence':.99,'evidence':item['contextBefore'],'reason':'模拟上下文解释足够长但引用未包含目标记录'}
        self.assertEqual(len(review({'items':[item],'edits':[e]},checker=check)['applied']),0)
