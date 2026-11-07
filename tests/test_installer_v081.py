"""Installer tests use fixtures/local sockets, never real model/WinGet downloads."""
from __future__ import annotations
from contextlib import contextmanager
import http.server
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from install_support import (Failure, InstallFailure, InstallerLock, MODEL_NAMES,
                             OllamaClient, classify_failure, dns_probe, ensure_model,
                             ip_kind, local_address, redact, write_json_atomic)
import install_all


@contextmanager
def fake_ollama(mode='success', present=False):
    state = {'pulls': 0, 'models': set(MODEL_NAMES.values()) if present else set(), 'bodies': []}
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'
        def log_message(self, *a): pass
        def reply(self, obj, code=200):
            raw = json.dumps(obj).encode()
            self.send_response(code); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw))); self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            if self.path == '/api/tags':
                self.reply({'models':[{'name': n} for n in state['models']]})
            elif self.path == '/api/version': self.reply({'version':'fixture'})
            else: self.reply({'error':'not found'},404)
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
            state['bodies'].append((self.path, body))
            if self.path == '/api/show':
                self.reply({'details':{},'capabilities':['completion']}); return
            state['pulls'] += 1
            if mode == 'http503':
                self.reply({'error':'temporary'},503); return
            if mode == 'http404':
                self.reply({'error':'model not found'},404); return
            self.send_response(200); self.send_header('Content-Type','application/x-ndjson'); self.end_headers()
            try:
                if mode == 'slow':
                    time.sleep(.3)
                if mode == 'dns':
                    self.wfile.write(json.dumps({'error':'redirect target not allowed: cdn.example resolves to non-public 198.18.0.253'}).encode()+b'\n'); self.wfile.flush(); return
                if mode == 'invalid':
                    self.wfile.write(b'not json\n'); return
                if mode == 'oversized':
                    self.wfile.write(b'x'*70000+b'\n'); return
                if mode == 'invalidcounter':
                    self.wfile.write(b'{"status":"pulling a","completed":-1,"total":100}\n'); return
                if mode == 'stall':
                    for _ in range(12):
                        self.wfile.write(b'{"status":"pulling a","completed":1,"total":100}\n'); self.wfile.flush(); time.sleep(.02)
                    return
                records = [{'status':'pulling manifest'}, {'status':'pulling abc','digest':'abc','completed':50,'total':100},
                           {'status':'pulling abc','digest':'abc','completed':100,'total':100}, {'status':'verifying sha256 digest'}]
                for record in records:
                    data=json.dumps(record).encode()+b'\n'
                    # Real socket and line framing fragmented across several writes.
                    self.wfile.write(data[:4]); self.wfile.flush(); self.wfile.write(data[4:]); self.wfile.flush()
                    if mode == 'advancing': time.sleep(.035)
                if mode in {'eof', 'retry'} and (mode == 'eof' or state['pulls'] == 1):
                    return
                if mode != 'unregistered': state['models'].add(body['model'])
                self.wfile.write(b'{"status":"success"}\n'); self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    client=OllamaClient(f'http://127.0.0.1:{server.server_port}',connect_timeout=1)
    try: yield client,state
    finally: server.shutdown();server.server_close();thread.join(timeout=2)


class NetworkClassification(unittest.TestCase):
    def test_screenshot_ip_is_fake_range(self): self.assertEqual(ip_kind('198.18.0.253'),'benchmark-or-fake-ip')
    def test_second_half_benchmark_range(self): self.assertEqual(ip_kind('198.19.255.254'),'benchmark-or-fake-ip')
    def test_mapped_fake_ipv6(self): self.assertEqual(ip_kind('::ffff:198.18.0.253'),'benchmark-or-fake-ip')
    def test_public_ip(self): self.assertEqual(ip_kind('1.1.1.1'),'public')
    def test_private_and_multicast_not_public(self):
        for ip in ('10.0.0.1','127.0.0.1','169.254.169.254','224.0.0.1','::1','fc00::1','100.64.1.1'):
            self.assertEqual(ip_kind(ip),'non-public')
    def test_fake_rejection_no_retry(self):
        f=classify_failure('redirect target not allowed: x resolves to non-public 198.18.0.253')
        self.assertEqual(f.code,'DNS_NON_PUBLIC');self.assertFalse(f.retryable)
    def test_transient_retry(self): self.assertTrue(classify_failure('connection reset by peer').retryable)
    def test_disk_not_retry(self): self.assertFalse(classify_failure('no space left on device').retryable)
    def test_tls_not_retry(self): self.assertFalse(classify_failure('x509: certificate signed by unknown authority').retryable)
    def test_digest_does_not_delete_or_loop(self): self.assertEqual(classify_failure('digest mismatch').code,'CACHE_INTEGRITY')
    def test_404_not_retry(self): self.assertFalse(classify_failure('not found',404).retryable)
    def test_503_retry(self): self.assertTrue(classify_failure('service failed',503).retryable)
    def test_412_version_not_retry(self): self.assertEqual(classify_failure('precondition',412).code,'OLLAMA_VERSION')
    def test_redact_signed_url_and_proxy_auth(self):
        s=redact('Get https://cdn.example/a?X-Amz-Signature=secret https://bob:pw@proxy.example:1080/a?x=1 token=hidden')
        for secret in ('secret','bob','pw','hidden','X-Amz-Signature=secret'): self.assertNotIn(secret,s)
        self.assertIn('cdn.example',s);self.assertIn('proxy.example:1080',s)
    def test_dns_probe_fake_fixture(self):
        def resolver(*a,**kw): return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('198.18.0.253',443))]
        self.assertEqual(dns_probe('cdn.example',resolver=resolver)['status'],'non-public')
    def test_dns_probe_timeout(self):
        def resolver(*a,**kw): time.sleep(.08);return []
        self.assertEqual(dns_probe('cdn.example',timeout=.01,resolver=resolver)['status'],'lookup-timeout')
    def test_dns_failure(self):
        def resolver(*a,**kw): raise socket.gaierror('fixture')
        self.assertEqual(dns_probe('cdn.example',resolver=resolver)['status'],'lookup-failed')
    def test_local_service_scope(self):
        for url in ('http://example.com','https://127.0.0.1','http://user:pw@localhost','http://127.0.0.1/x','http://127.0.0.1?x=1'):
            with self.assertRaises(ValueError): local_address(url)
        self.assertEqual(local_address('http://localhost:11434'),('127.0.0.1',11434))


class RealLocalHTTP(unittest.TestCase):
    def test_stream_progress_success_and_verify(self):
        with fake_ollama() as (client,state):
            progress=[]
            r=ensure_model(client,MODEL_NAMES['text'],progress=progress.append)
            self.assertEqual(r['state'],'installed');self.assertEqual(state['pulls'],1)
            self.assertEqual(progress[-1]['status'],'success');self.assertFalse(r['inference_tested'])
            self.assertEqual(next(body for path,body in state['bodies'] if path=='/api/pull')['stream'],True)
    def test_already_present_never_pull(self):
        with fake_ollama(present=True) as (client,state):
            r=ensure_model(client,MODEL_NAMES['vision']);self.assertEqual(r['state'],'already_present');self.assertEqual(state['pulls'],0)
    def test_non_public_error_not_retried(self):
        with fake_ollama('dns') as (client,state):
            with self.assertRaises(InstallFailure) as ctx: ensure_model(client,MODEL_NAMES['vision'],sleep=lambda s:None)
            self.assertEqual(ctx.exception.code,'DNS_NON_PUBLIC');self.assertEqual(state['pulls'],1)
    def test_eof_retry_eventual_success(self):
        with fake_ollama('retry') as (client,state):
            r=ensure_model(client,MODEL_NAMES['text'],sleep=lambda s:None)
            self.assertEqual(r['attempts'],2);self.assertEqual(state['pulls'],2)
    def test_incomplete_stream_never_success(self):
        with fake_ollama('eof') as (client,state):
            with self.assertRaises(InstallFailure): ensure_model(client,MODEL_NAMES['text'],attempts=2,sleep=lambda s:None)
            self.assertEqual(state['pulls'],2)
    def test_no_registered_model_fails_verification(self):
        with fake_ollama('unregistered') as (client,state):
            with self.assertRaises(InstallFailure) as ctx: ensure_model(client,MODEL_NAMES['text'])
            self.assertEqual(ctx.exception.code,'VERIFY_FAILED')
    def test_invalid_json_is_failure(self):
        with fake_ollama('invalid') as (client,state):
            with self.assertRaises(InstallFailure) as ctx: client.pull_once(MODEL_NAMES['text'])
            self.assertEqual(ctx.exception.code,'PROTOCOL')
    def test_oversized_progress_rejected(self):
        with fake_ollama('oversized') as (client,state):
            with self.assertRaises(InstallFailure) as ctx: client.pull_once(MODEL_NAMES['text'])
            self.assertEqual(ctx.exception.code,'PROTOCOL')
    def test_invalid_counter_rejected(self):
        with fake_ollama('invalidcounter') as (client,state):
            with self.assertRaises(InstallFailure) as ctx: client.pull_once(MODEL_NAMES['text'])
            self.assertEqual(ctx.exception.code,'PROTOCOL')
    def test_heartbeat_does_not_mask_stall(self):
        with fake_ollama('stall') as (client,state):
            with self.assertRaises(InstallFailure) as ctx: client.pull_once(MODEL_NAMES['text'],stall_timeout=.06)
            self.assertEqual(ctx.exception.code,'DOWNLOAD_STALLED')
    def test_advancing_progress_does_not_stall(self):
        with fake_ollama('advancing') as (client,state):
            r=client.pull_once(MODEL_NAMES['text'],stall_timeout=.09)
            self.assertTrue(r['stream_success'])
    def test_read_idle_timeout(self):
        with fake_ollama('slow') as (client,state):
            with self.assertRaises(InstallFailure) as ctx: client.pull_once(MODEL_NAMES['text'],idle_timeout=.04)
            self.assertEqual(ctx.exception.code,'NETWORK_TEMPORARY')
    def test_absolute_timeout(self):
        with fake_ollama('slow') as (client,state):
            start=time.monotonic()
            with self.assertRaises(InstallFailure) as ctx: client.pull_once(MODEL_NAMES['text'],total_timeout=.04)
            self.assertEqual(ctx.exception.code,'DOWNLOAD_DEADLINE')
            self.assertLess(time.monotonic()-start,.22)
    def test_http_status_classification(self):
        with fake_ollama('http404') as (client,state):
            with self.assertRaises(InstallFailure) as ctx: client.pull_once(MODEL_NAMES['text'])
            self.assertEqual(ctx.exception.code,'MODEL_NOT_FOUND')
    def test_proxy_environment_not_used_for_loopback(self):
        with patch.dict(os.environ,{'HTTP_PROXY':'http://127.0.0.1:1','HTTPS_PROXY':'http://127.0.0.1:1','ALL_PROXY':'http://127.0.0.1:1'}):
            with fake_ollama() as (client,state):
                self.assertEqual(client.request_json('GET','/api/version')['version'],'fixture')
    def test_scope_reject_unknown_cloud_model(self):
        with fake_ollama() as (client,state):
            with self.assertRaises(InstallFailure):client.pull_once('some-cloud:latest')
            self.assertEqual(state['pulls'],0)


class InstallerContracts(unittest.TestCase):
    def test_all_profile_contains_every_component(self):
        self.assertEqual(set(x['id'] for x in install_all.plan('all','small')),{'runtime','review','video','speaker','asr','text','vision'})
    def test_plan_has_no_install_calls(self):
        with patch.object(install_all,'Installer') as mock:
            self.assertEqual(install_all.main(['--plan']),0);mock.assert_not_called()
    def test_lock_rejects_concurrent_install(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x'
            with InstallerLock(p):
                with self.assertRaises(InstallFailure):
                    with InstallerLock(p):pass
            with InstallerLock(p): pass
    def test_atomic_state(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.json';write_json_atomic(p,{'state':'ready'});self.assertEqual(json.loads(p.read_text())['state'],'ready')
            self.assertFalse(p.with_suffix('.json.tmp').exists())
    def test_partial_failure_never_claims_all_ready(self):
        with tempfile.TemporaryDirectory() as d:
            r=install_all.Installer(install_all.parse_args([]),root=Path(d))
            r.step('fixture success',lambda: {'ok':True})
            r.step('fixture failure',lambda: (_ for _ in ()).throw(RuntimeError('failure')))
            self.assertEqual(r.finish(),1);self.assertFalse(json.loads(r.json_path.read_text())['all_selected_ready'])
    def test_setup_preserves_config_and_no_private_bypass(self):
        s=(ROOT/'scripts/install_all.py').read_text()
        self.assertNotIn("verify=False",s);self.assertNotIn("OLLAMA_ORIGINS'",s)
        self.assertNotIn('Set-DnsClientServerAddress',s)
        self.assertNotIn("unlink(",s)
        for file in ['ASR_SETTINGS.bat','models','stream.sqlite3']:
            self.assertNotIn(f"shutil.rmtree('{file}'",s)
    def test_ps_bootstrap_uses_local_venv_and_exact_winget_source(self):
        s=(ROOT/'scripts/install_all.ps1').read_text('utf-8-sig')
        self.assertIn('--source winget',s);self.assertIn('--exact',s)
        self.assertIn('Existing .venv',s);self.assertNotIn('Invoke-Expression',s)
    def test_defaults_distinguish_idle_stall_absolute(self):
        a=install_all.parse_args([])
        self.assertEqual(a.idle_timeout,180);self.assertEqual(a.stall_timeout,600);self.assertEqual(a.model_timeout,14400)
    def test_asr_prefetch_reuses_official_cache_and_loads_offline(self):
        s=(ROOT/'scripts/prefetch_asr.py').read_text()
        self.assertIn('download_model(name)',s);self.assertIn('local_files_only=True',s)

if __name__=='__main__': unittest.main()
