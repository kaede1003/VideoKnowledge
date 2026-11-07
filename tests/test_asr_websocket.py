"""Protocol 5 server integration with fixture inference; no model downloads."""
import os,json,tempfile,unittest
from unittest.mock import patch
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from server import app as serverapp
from server.stream_protocol import Packet

ORIGIN='chrome-extension://'+'a'*32
class FakeEngine:
    model_name='fixture';device='cpu';compute_type='int8';loaded=True
    def transcribe_job(self,j):return [{'time':j.media_time(j.owner_start),'end':j.media_time(j.owner_end),'text':'测试转写','language':'zh','confidence':.9}]

class TestApi(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=serverapp.ENGINE;serverapp.ENGINE=FakeEngine()
        self.env=patch.dict(os.environ,{'VKN_CACHE_DIR':self.tmp.name});self.env.start()
    def tearDown(self):serverapp.ENGINE=self.old;self.env.stop();self.tmp.cleanup()
    def until(self,ws,kind):
        for _ in range(50):
            item=ws.receive_json()
            if item['type']==kind:return item
        self.fail('missing event '+kind)
    def hello(self,ws,sid='c'*32):
        self.assertEqual(ws.receive_json()['protocol'],5)
        ws.send_text(json.dumps({'type':'hello','sessionId':sid,'videoKey':'yt:test','options':{'translate':False}}))
        return self.until(ws,'hello')
    def test_health(self):
        with TestClient(serverapp.app) as client:self.assertEqual(client.get('/health').json()['protocol'],5)
    def test_non_extension_origin_rejected(self):
        with TestClient(serverapp.app) as client:
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect('/asr',headers={'origin':'https://example.com'}) as ws:ws.receive_json()
    def test_protocol_ping(self):
        with TestClient(serverapp.app) as c:
            with c.websocket_connect('/asr',headers={'origin':ORIGIN}) as ws:
                ws.receive_json();ws.send_text('ping');self.assertEqual(ws.receive_json()['type'],'pong')
    def test_tail_saved_and_delivered(self):
        with TestClient(serverapp.app) as c:
            with c.websocket_connect('/asr',headers={'origin':ORIGIN}) as ws:
                self.hello(ws);ws.send_bytes(Packet(1,0,.2,0,b'\x01\x00'*3200).encode())
                self.assertEqual(self.until(ws,'ack')['seq'],1)
                ws.send_bytes(Packet(2,.2,.2,2,b'').encode())
                result=self.until(ws,'segment');self.assertEqual(result['original'],'测试转写');self.assertTrue(result['id'])
                self.assertIn('已缓存音频',self.until(ws,'done')['message'])
    def test_duplicate_packet_ack(self):
        with TestClient(serverapp.app) as c:
            with c.websocket_connect('/asr',headers={'origin':ORIGIN}) as ws:
                self.hello(ws);raw=Packet(1,0,.2,0,b'\x01\x00'*3200).encode()
                for _ in range(2):ws.send_bytes(raw);self.assertEqual(self.until(ws,'ack')['seq'],1)
    def test_bad_packet_is_fatal_no_false_ack(self):
        with TestClient(serverapp.app) as c:
            with c.websocket_connect('/asr',headers={'origin':ORIGIN}) as ws:
                self.hello(ws);ws.send_bytes(b'bad');self.assertTrue(self.until(ws,'error')['fatal'])
    def test_rule_succeeds_without_ollama(self):
        with TestClient(serverapp.app) as c:
            with patch('server.lora_service.check_ollama',side_effect=AssertionError('not called')):
                r=c.post('/lora/plan',headers={'origin':ORIGIN},json={'prompt':'清晰全身镜头，每3秒一帧，最多20张'})
                self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['plan']['max_frames'],20)
    def test_browser_restart_replays_results(self):
        with TestClient(serverapp.app) as c:
            with c.websocket_connect('/asr',headers={'origin':ORIGIN}) as ws:
                self.hello(ws);ws.send_bytes(Packet(1,0,.2,0,b'\x01\x00'*3200).encode());self.until(ws,'ack')
                ws.send_bytes(Packet(2,.2,.2,2,b'').encode());first=self.until(ws,'segment');self.until(ws,'done')
        with TestClient(serverapp.app) as c:
            with c.websocket_connect('/asr',headers={'origin':ORIGIN}) as ws:
                hello=self.hello(ws);self.assertEqual(hello['received'],2);self.assertEqual(self.until(ws,'segment')['id'],first['id'])

if __name__=='__main__':unittest.main()
