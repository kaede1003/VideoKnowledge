"""Frame filters and local websocket, no model downloads or browser needed."""
from __future__ import annotations
import base64
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from server import app as serverapp
from server import lora_core
from server import lora_service

ORIGIN = {'origin': 'chrome-extension://'+'a'*32}

def img_base64(seed=1):
    arr=np.random.default_rng(seed).integers(0,256,size=(240,320,3),dtype=np.uint8)
    image=Image.fromarray(arr)
    output=io.BytesIO()
    image.save(output,format='JPEG',quality=85)
    return 'data:image/jpeg;base64,'+base64.b64encode(output.getvalue()).decode('ascii')


class TestCore(unittest.TestCase):
    def test_rules_clamped(self):
        r=lora_core.make_rule('每0.1秒提取清晰人像，最多999张')
        self.assertEqual(r['interval_seconds'],1)
        self.assertEqual(r['max_frames'],500)
        self.assertEqual(lora_core.make_rule('每3秒截图正脸')['interval_seconds'],3)

    def test_frame_decode_and_malformed_input(self):
        image,raw=lora_core.read_image(img_base64(2))
        self.assertEqual(image.size,(320,240))
        self.assertGreater(len(raw),100)
        for value in ('', 'data:image/png;base64,eA==','data:image/jpeg;base64,?'):
            with self.assertRaises(ValueError):lora_core.read_image(value)

    def test_duplicate_hash(self):
        image,_=lora_core.read_image(img_base64(3))
        q,h=lora_core.quality(image)
        self.assertGreater(q,0)
        self.assertEqual(lora_core.hamming(h,h),0)
        self.assertEqual(lora_core.hamming(0,2**64-1),64)

    def test_parse_vlm_output_fail_closed(self):
        self.assertEqual(lora_core.parse_model_json('{"match":false,"reason":"模糊"}')['match'],False)
        self.assertTrue(lora_core.parse_model_json('{"match":true,"caption":"一个人站在屋内"}')['match'])
        for inp in ('完成','{}','{"match":true,"caption":""}', '{"match":"true"}'):
            with self.assertRaises(ValueError):lora_core.parse_model_json(inp)

    def test_invalid_url(self):
        for v in ['file:///tmp/secret','javascript:alert(1)','http://example.com','https://ex.test/<script>']:
            with self.assertRaises(ValueError):lora_core.safe_url(v)

class TestService(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=lora_service.BASE_DIR
        lora_service.BASE_DIR=pathlib.Path(self.temp.name)
        lora_service.sessions.clear()
        async def ok_model(_):pass
        async def merge(old,prompt):return lora_core.make_rule(prompt,old)
        async def vision(image,prompt,model):return {'match':True,'caption':'一个清晰的测试人物在室内','reason':'符合条件'}
        self.p1=patch.object(lora_service,'check_ollama',ok_model)
        self.p2=patch.object(lora_service,'merge_natural_language_rule',merge)
        self.p3=patch.object(lora_service,'ollama_vision',vision)
        self.p1.start();self.p2.start();self.p3.start()
    def tearDown(self):
        self.p1.stop();self.p2.stop();self.p3.stop()
        lora_service.BASE_DIR=self.base
        lora_service.sessions.clear()
        self.temp.cleanup()

    def test_origin_must_be_extension(self):
        with TestClient(serverapp.app) as c:
            r=c.post('/lora/plan',json={'prompt':'只保留清晰人物全身'},headers={'origin':'https://random.example'})
            self.assertEqual(r.status_code,403)
            with self.assertRaises(WebSocketDisconnect):
                with c.websocket_connect('/lora/stream/'+'1'*32,headers={'origin':'https://random.example'}) as ws:
                    ws.receive_json()

    def test_multiturn_plan(self):
        with TestClient(serverapp.app) as c:
            first=c.post('/lora/plan',json={'prompt':'每3秒采集正面清晰人物'},headers=ORIGIN)
            self.assertEqual(first.status_code,200,first.text)
            self.assertEqual(first.json()['plan']['interval_seconds'],3)
            revised=c.post('/lora/plan',json={'prompt':'最多保存25张完整人像','previous':first.json()['plan']},headers=ORIGIN)
            self.assertEqual(revised.json()['plan']['max_frames'],25)

    def test_accept_duplicate_stop_export(self):
        with TestClient(serverapp.app) as c:
            r=c.post('/lora/session',json={
                'title':'本地合成演示视频', 'url':'https://example.org/watch?v=123',
                'rule':{'prompt':'保留人物完整的图片','interval_seconds':2,'max_frames':4,'min_sharpness':0}
            },headers=ORIGIN)
            self.assertEqual(r.status_code,200,r.text)
            sid=r.json()['session_id']
            with c.websocket_connect('/lora/stream/'+sid,headers=ORIGIN) as ws:
                self.assertEqual(ws.receive_json()['type'],'ready')
                ws.send_text(json.dumps({'type':'frame','time':11.2,'image':img_base64(15)}))
                self.assertEqual(ws.receive_json()['type'],'accepted')
                ws.send_text(json.dumps({'type':'frame','time':12.2,'image':img_base64(15)}))
                ws.send_text(json.dumps({'type':'stop'}))
                message=ws.receive_json()
                while message['type']!='stopped':
                    message=ws.receive_json()
                self.assertEqual(message['status']['accepted'],1)
            link=c.post('/lora/export-link',json={'session_id':sid},headers=ORIGIN)
            self.assertEqual(link.status_code,200,link.text)
            url=link.json()['url'].replace('http://127.0.0.1:8765','')
            r=c.get(url)
            self.assertEqual(r.status_code,200,r.text[:100])
            import zipfile
            archive=zipfile.ZipFile(io.BytesIO(r.content))
            names=archive.namelist()
            self.assertIn('dataset.json',names)
            self.assertEqual(len([x for x in names if x.endswith('.jpg')]),1)
            self.assertEqual(len([x for x in names if x.endswith('.txt') and 'frame_' in x]),1)
            wrong=c.get(url.replace('token=','token=no'))
            self.assertEqual(wrong.status_code,403)

if __name__=='__main__':unittest.main()
