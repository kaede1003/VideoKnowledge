"""Synthetic subtitle examples, not a claim about the user's video or model quality."""
import unittest
from server import caption_review as R
S='b'*32

def run(raw, subtitle, **extra):
    cue=dict(id=S+':1:0',time=10.,end=20.,contextEpoch=0,language='zh',text=raw,original=raw)
    ob=dict(id='fixture',stream=S,epoch=0,start=12.,end=14.,source='visible',samples=3,seenSpan=1.,kind='unknown',text=subtitle)
    ob.update(extra)
    return R.validate({'items':[{'cue':cue,'evidence':[ob]}]},checker=lambda a,b:False)['reviews'][0]

class CaptionLatinRegression(unittest.TestCase):
    def test_mixed_script_whole_names_from_caption(self):
        s='这里讨论Cloud Sonet的文本处理能力以及Anthrope的接口实现'
        r=run(s,'这里讨论Claude Sonnet的文本处理能力以及Anthropic的接口实现')
        self.assertEqual(r['status'],'applied')
        self.assertEqual(r['text'],'这里讨论Claude Sonnet的文本处理能力以及Anthropic的接口实现')
        self.assertEqual(r['source'],s)
    def test_different_lengths_but_identical_version(self):
        r=run('这里展示Cloud Sonet 5.5的功能','这里展示Claude Sonnet 5.5的功能')
        self.assertEqual(r['status'],'applied'); self.assertIn('5.5',r['text'])
    def test_no_caption_no_dictionary_fix(self):
        s='这里展示Cloud Sonet的功能';c=dict(id=S+':1:0',time=0.,end=4.,text=s,original=s,language='zh')
        self.assertEqual(R.validate({'items':[{'cue':c,'evidence':[]} ]})['reviews'],[])
    def test_not_global_replace_of_cloud(self):
        r=run('我们讨论Cloud存储的实际用途','我们讨论Cloud存储的实际用途')
        self.assertEqual(r['text'],'我们讨论Cloud存储的实际用途')
    def test_no_version_changes(self):
        r=run('这里展示Cloud Sonet 5.5的功能','这里展示Claude Sonnet 6.0的功能')
        self.assertNotEqual(r['status'],'applied')
    def test_automatic_captions_not_independent(self):
        self.assertNotEqual(run('这里讨论Anthrope的模型接口','这里讨论Anthropic的模型接口',kind='automatic')['status'],'applied')
    def test_no_latin_replacement_without_context(self):
        self.assertNotEqual(run('Cloud Sonet','Claude Sonnet')['status'],'applied')
    def test_negative_term_not_spelling_correction(self):
        self.assertNotEqual(run('这个方法never更改内容','这个方法ever更改内容')['status'],'applied')
    def test_unrelated_name_not_auto_fixed(self):
        self.assertNotEqual(run('这里讨论Google的模型接口','这里讨论OpenAI的模型接口')['status'],'applied')
    def test_single_frame_not_accepted(self):
        self.assertNotEqual(run('这里讨论Anthrope的模型接口','这里讨论Anthropic的模型接口',source='frame',samples=1,seenSpan=0.)['status'],'applied')

class CaptionEvidenceEdgeCases(unittest.TestCase):
    def test_conflicting_stable_captions_veto(self):
        raw='这里讨论Anthrope的模型接口';good='这里讨论Anthropic的模型接口'
        cue=dict(id=S+':1:0',time=10.,end=20.,contextEpoch=0,language='zh',text=raw,original=raw)
        base=dict(stream=S,epoch=0,start=12.,end=14.,source='visible',samples=3,seenSpan=1.,kind='unknown')
        r=R.validate({'items':[{'cue':cue,'evidence':[dict(base,id='a',text=good),dict(base,id='b',text=raw)]}]},checker=lambda a,b:False)['reviews'][0]
        self.assertNotEqual(r['status'],'applied')
    def test_english_utterance_supported_with_english_caption(self):
        raw='This Anthrope model supports local text processing'
        cue=dict(id=S+':1:0',time=10.,end=20.,contextEpoch=0,language='en',text=raw,original=raw)
        ob=dict(id='e',stream=S,epoch=0,start=12.,end=14.,source='track',samples=3,seenSpan=1.,kind='unknown',text='This Anthropic model supports local text processing')
        r=R.validate({'items':[{'cue':cue,'evidence':[ob]}]})['reviews'][0]
        self.assertEqual(r['status'],'applied');self.assertIn('Anthropic',r['text'])
    def test_latin_does_not_require_pinyin(self):
        from unittest.mock import patch
        with patch.object(R,'availability',return_value={'available':False}):
            r=run('这里讨论Anthrope的模型接口','这里讨论Anthropic的模型接口')
            self.assertEqual(r['status'],'applied')
    def test_translated_captions_not_accepted(self):
        r=run('这里讨论Anthrope的模型接口','这里讨论Anthropic的模型接口',kind='translated')
        self.assertNotEqual(r['status'],'applied')
    def test_partial_caption_does_not_remove_surrounding_speech(self):
        raw='前面还有其他内容。这里讨论Anthrope的模型接口，最后保留这个例子。'
        r=run(raw,'这里讨论Anthropic的模型接口')
        self.assertEqual(r['status'],'applied');self.assertTrue(r['text'].endswith('最后保留这个例子。'))
    def test_latin_conflict_does_not_override_number_guard(self):
        r=run('我们需要18个Anthrope模型','我们需要80个Anthropic模型')
        self.assertNotEqual(r['status'],'applied')

class CaptionFrameLineRegression(unittest.IsolatedAsyncioTestCase):
    def frames(self):
        import io,base64
        from PIL import Image,ImageDraw
        im=Image.new('RGB',(600,100),'black');ImageDraw.Draw(im).rectangle((10,30,550,70),fill='white')
        buf=io.BytesIO();im.save(buf,'JPEG');uri='data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode()
        return [dict(image=uri,time=10+i*.5,stream=S,epoch=0) for i in range(2)]
    async def test_stable_latin_line_not_discarded_by_chinese_line(self):
        import httpx,json
        def handler(req):
            return httpx.Response(200,json={'done':True,'message':{'content':json.dumps({'frames':[{'index':0,'lines':['我们来比较模型','Claude Sonnet']},{'index':1,'lines':['现在看另外一种','Claude Sonnet']}]})}})
        r=await R.extract_frames({'frames':self.frames()},lambda:httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        latin=next(o for o in r['observations'] if o['text']=='Claude Sonnet')
        self.assertEqual(latin['samples'],2);self.assertEqual(latin['seenSpan'],.5)
        self.assertNotIn('image',latin)
    async def test_wrapped_mixed_subtitle_keeps_name_case_spaces_and_version(self):
        import httpx,json
        lines=['这里展示Claude Sonnet 5.5','并比较其文本处理表现']
        def handler(req):return httpx.Response(200,json={'done':True,'message':{'content':json.dumps({'frames':[{'index':0,'lines':lines},{'index':1,'lines':lines}]})}})
        r=await R.extract_frames({'frames':self.frames()},lambda:httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        self.assertTrue(any(o['text']==' '.join(lines) and o['samples']==2 for o in r['observations']))
