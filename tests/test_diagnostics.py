import importlib.util
import io
import json
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

SPEC = importlib.util.spec_from_file_location('diagnose', Path(__file__).parents[1]/'scripts'/'diagnose_ai_timeout.py')
d = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(d)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def reply(self, body, status=200):
        raw=json.dumps(body,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw)));self.end_headers()
        try:self.wfile.write(raw)
        except (OSError, BrokenPipeError):pass
    def do_GET(self):
        if self.path=='/api/tags': return self.reply({'models':[{'name':'qwen2.5:3b'}]})
        if self.path=='/api/ps': return self.reply({'models':[{'name':'qwen2.5:3b','size':100,'size_vram':100,'context_length':4096}]})
        if self.path=='/api/version': return self.reply({'version':'mock-only'})
        self.reply({},404)
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
        if data.get('model')=='slow':time.sleep(.25);return self.reply({'message':{'content':'late'}})
        if data.get('model')=='fail':return self.reply({'error':'SECRET_TEXT_MUST_NOT_BE_LOGGED'},403)
        items=[{'message':{'content':'测试'},'done':False}]
        if data.get('model')!='broken':
            items+=[{'message':{'content':'完成'},'done':True,'done_reason':'stop','total_duration':600000000,
                     'load_duration':100000000,'prompt_eval_duration':200000000,'eval_duration':300000000,
                     'eval_count':12,'prompt_eval_count':20}]
        raw=b'\n'.join(json.dumps(x,ensure_ascii=False).encode() for x in items)+b'\n'
        self.send_response(200);self.send_header('Content-Type','application/x-ndjson')
        self.send_header('Content-Length',str(len(raw)));self.end_headers()
        # Split within UTF-8 bytes as well as JSON/line boundaries.
        for pos in range(0,len(raw),7):
            try:self.wfile.write(raw[pos:pos+7]);self.wfile.flush()
            except (OSError,BrokenPipeError):break

class TestDiagnostic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
        cls.t=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.t.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()
    def test_loopback_only(self):
        for u in ['https://example.com','http://192.168.1.1:11434','http://user:pass@127.0.0.1:11434','http://localhost/a','http://localhost?secret=key']:
            with self.assertRaises(ValueError):d.local_target(u)
        self.assertEqual(d.local_target('http://localhost:11434'),('127.0.0.1',11434))
    def test_no_cloud_model(self):
        with self.assertRaises(ValueError):d.validate_model('test-cloud')
    def test_metrics_and_no_content_leak(self):
        r=d.request(self.base,'/api/chat',{'model':'qwen2.5:3b'},deadline=3,streaming=True)
        self.assertTrue(r['ok']);self.assertEqual(r['load_s'],.1);self.assertEqual(r['output_tokens_per_s'],40)
        self.assertEqual(r['output_chars'],4);self.assertNotIn('测试',json.dumps(r,ensure_ascii=False))
    def test_absolute_deadline(self):
        r=d.request(self.base,'/api/chat',{'model':'slow'},deadline=.08,streaming=True)
        self.assertFalse(r['ok']);self.assertEqual(r['error'],'LOCAL_DEADLINE');self.assertLess(r['wall_s'],.5)
    def test_status_redacted(self):
        r=d.request(self.base,'/api/chat',{'model':'fail'},deadline=3,streaming=True)
        self.assertEqual(r['error'],'HTTP_403');self.assertNotIn('SECRET_TEXT',json.dumps(r))
    def test_incomplete_stream(self):
        r=d.request(self.base,'/api/chat',{'model':'broken'},deadline=3,streaming=True)
        self.assertEqual(r['error'],'STREAM_ENDED_WITHOUT_DONE')
    def test_running_models(self):
        r=d.running_models(self.base);self.assertTrue(r['ok']);self.assertEqual(r['models'][0]['context_length'],4096)
    def test_full_run(self):
        old=d.gpu_snapshot;d.gpu_snapshot=lambda:{'available':False}
        try:
            with redirect_stdout(io.StringIO()):r,code=d.run(SimpleNamespace(base_url=self.base,model='qwen2.5:3b',medium=True,timeout=3))
        finally:d.gpu_snapshot=old
        self.assertEqual(code,0);self.assertEqual(len(r['tests']),3)
        self.assertTrue(all(x['ok'] for x in r['tests']))
        self.assertNotIn('软件测试资料',json.dumps(r,ensure_ascii=False))
    def test_missing_model_no_inference(self):
        old=d.gpu_snapshot;d.gpu_snapshot=lambda:{'available':False}
        try:r,code=d.run(SimpleNamespace(base_url=self.base,model='absent',medium=True,timeout=3))
        finally:d.gpu_snapshot=old
        self.assertEqual(code,2);self.assertEqual(r['tests'],[])

if __name__=='__main__':unittest.main()
