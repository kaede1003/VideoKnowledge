"""Qwen vision 500 degradation tests. Never changes ASR cache or speech worker."""
import asyncio, base64, io, json, unittest
import httpx
from PIL import Image,ImageDraw
from server import caption_review as R
SID='c'*32
class VisionFailureIsolation(unittest.IsolatedAsyncioTestCase):
 def frames(self):
  im=Image.new('RGB',(640,120),'black');ImageDraw.Draw(im).rectangle((10,30,600,80),fill='white');f=io.BytesIO();im.save(f,'JPEG');u='data:image/jpeg;base64,'+base64.b64encode(f.getvalue()).decode()
  return [{'image':u,'stream':SID,'epoch':0,'time':n*.5+5} for n in range(2)]
 async def test_visual_caption_never_requests_constrained_grammar(self):
  def mock(req):
   body=json.loads(req.content);self.assertNotIn('format',body);return httpx.Response(200,json={'done':True,'message':{'content':json.dumps({'frames':[{'index':0,'lines':['示例']},{'index':1,'lines':['示例']}]})}})
  result=await R.extract_frames({'frames':self.frames()},lambda:httpx.AsyncClient(transport=httpx.MockTransport(mock)))
  self.assertEqual(result['observations'][0]['text'],'示例')
 async def test_visual_500_is_isolated_and_not_claimed_as_asr_failure(self):
  def mock(req):return httpx.Response(500,json={'error':'grammar failure'})
  with self.assertRaises(httpx.HTTPStatusError):await R.extract_frames({'frames':self.frames()},lambda:httpx.AsyncClient(transport=httpx.MockTransport(mock)))
 async def test_empty_200_visual_response_not_used(self):
  def mock(req):return httpx.Response(200,json={'done':True,'message':{'content':''}})
  with self.assertRaises(httpx.RemoteProtocolError):await R.extract_frames({'frames':self.frames()},lambda:httpx.AsyncClient(transport=httpx.MockTransport(mock)))
