"""No real credentials/network. Validate cookie scope, lifecycle and failure classification."""
from __future__ import annotations
import asyncio
import contextlib
import http.cookiejar
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request
from fastapi import FastAPI
from fastapi.testclient import TestClient
from server.video_auth import clean_cookies,install_cookiejar
from server.video_errors import error_code
from server import video_cache as V
from server.video_download_worker import download
OWNER='chrome-extension://'+'a'*32
URL='https://www.youtube.com/watch?v=abcdefghijk'
SECRET='SYNTHETIC_SESSION_VALUE_NOT_REAL'
def cookie(**kwargs):return dict(name='SAPISID',value=SECRET,domain='.youtube.com',path='/',secure=True,httpOnly=True,hostOnly=False,**kwargs)
class AuthTests(unittest.TestCase):
    def test_consent_required(self):
        with self.assertRaisesRegex(ValueError,'CONSENT'):clean_cookies([cookie()],URL)
    def test_other_site_rejected(self):
        for url in ['https://www.bilibili.com/video/BV1xx411c7mD/','https://www.youtube.com.evil.test/watch?v=a','http://www.youtube.com']:
            with self.subTest(url=url),self.assertRaisesRegex(ValueError,'SCOPE'):clean_cookies([cookie()],url,True)
    def test_domain_allowlist_no_google_or_other_accounts(self):
        for domain in ['.google.com','.com','.youtube.com.evil.test','evil.youtube.com']:
            c=cookie();c['domain']=domain
            with self.subTest(domain=domain),self.assertRaises(ValueError):clean_cookies([c],URL,True)
    def test_expired_and_visitor_only_not_login(self):
        for c in [cookie(expirationDate=1),{**cookie(),'name':'VISITOR_INFO1_LIVE'}]:
            with self.assertRaisesRegex(ValueError,'EMPTY'):clean_cookies([c],URL,True,now=100)
    def test_header_injection_and_separators_rejected(self):
        for field,value in [('value','a\r\nX-Evil:1'),('value','a;b'),('name','a\nb'),('path','/\n')]:
            c=cookie();c[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):clean_cookies([c],URL,True)
    def test_partition_rejected(self):
        with self.assertRaises(ValueError):clean_cookies([cookie(partitionKey={'topLevelSite':'https://evil.test'})],URL,True)
    def test_size_bound(self):
        with self.assertRaises(ValueError):clean_cookies([cookie()]*129,URL,True)
    def test_duplicates_collapsed_and_source_unchanged(self):
        raw=[cookie(),cookie()];res=clean_cookies(raw,URL,True)
        self.assertEqual(len(res),1);self.assertEqual(len(raw),2);self.assertEqual(res[0]['value'],SECRET)
    def test_jar_only_sends_to_youtube_https(self):
        jar=http.cookiejar.CookieJar();install_cookiejar(jar,clean_cookies([cookie()],URL,True))
        for url,expected in [('https://www.youtube.com/watch',True),('https://evil.test',False),('https://www.google.com',False),('https://x.googlevideo.com',False),('http://www.youtube.com',False)]:
            r=Request(url);jar.add_cookie_header(r);self.assertEqual(bool(r.get_header('Cookie')),expected,url)
    def test_error_messages_never_include_secret(self):
        with self.assertRaises(ValueError) as e:clean_cookies([{**cookie(),'domain':SECRET}],URL,True)
        self.assertNotIn(SECRET,str(e.exception))
class WorkerTests(unittest.TestCase):
    def fixture(self,fn,auth=False):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/('a'*32);p.mkdir();(p/'.vkn-owned').write_text(p.name)
            opts={};jars=[]
            class Fake:
                def __init__(self,o):opts.update(o);self.cookiejar=http.cookiejar.CookieJar();jars.append(self.cookiejar)
                def __enter__(self):return self
                def __exit__(self,*args):return False
                def extract_info(self,url,download):return fn(p,opts,self.cookiejar)
            spec={'url':URL,'directory':str(p)}
            if auth:spec.update(youtube_cookies=[cookie()],login_consent=True)
            with patch('server.video_download_worker.emit') as emit:
                download(spec,Fake)
                return opts,jars,emit.call_args_list,spec
    def test_single_video_does_not_raise_limit_after_completion(self):
        class MaxDownloadsReached(Exception):pass
        def run(p,o,j):
            (p/'media.mp4').write_bytes(b'\x00\x00\x00\x18ftypisom')
            if o.get('max_downloads')==1:raise MaxDownloadsReached()
            return {'id':'abcdefghijk'}
        opts,jars,calls,_=self.fixture(run)
        self.assertNotIn('max_downloads',opts);self.assertTrue(opts['noplaylist']);self.assertEqual(calls[-1].args,('ready',))
    def test_no_cookie_read_by_default(self):
        def run(p,o,j):
            self.assertEqual(len(j),0);(p/'media.mp4').write_bytes(b'demo');return {'id':'abcdefghijk'}
        o,*_=self.fixture(run);self.assertIsNone(o['cookiefile']);self.assertIsNone(o['cookiesfrombrowser'])
    def test_opt_in_cookiejar_cleared_after_success(self):
        def run(p,o,j):
            self.assertEqual(len(j),1);self.assertIsNone(o['cookiefile']);(p/'media.mp4').write_bytes(b'demo');return {'id':'abcdefghijk'}
        opts,jars,calls,spec=self.fixture(run,True);self.assertEqual(len(jars[0]),0);self.assertNotIn('youtube_cookies',spec)
    def test_partial_error_never_reports_ready(self):
        def run(p,o,j):
            (p/'media.mp4.part').write_bytes(b'partial');raise RuntimeError('HTTP Error 403: Forbidden')
        with patch('server.video_download_worker.emit') as emit,self.assertRaises(RuntimeError):self.fixture(run)
        self.assertFalse(any(c.args==('ready',) for c in emit.call_args_list))
    def test_limit_signal_not_mislabelled_as_auth_failure(self):
        MaxDownloadsReached=type('MaxDownloadsReached',(Exception,),{})
        self.assertEqual(error_code(MaxDownloadsReached()),'VIDEO_LIMIT_SIGNAL')
    def test_error_classes_are_distinct_and_no_raw_exception_leaks(self):
        cases={'HTTP Error 403: Forbidden':'VIDEO_HTTP_403','HTTP Error 429':'VIDEO_HTTP_429','Sign in to confirm you are not a bot':'VIDEO_LOGIN_REQUIRED','cookies are no longer valid':'VIDEO_LOGIN_EXPIRED','Requested format is not available':'VIDEO_NO_FORMATS','connection reset':'VIDEO_NETWORK','certificate verify failed':'VIDEO_TLS','No supported JavaScript runtime':'VIDEO_RUNTIME','challenge solving failed':'VIDEO_EJS','ffmpeg not found':'VIDEO_FFMPEG','VIDEO_OUTPUT: bad':'VIDEO_OUTPUT','unclassified '+SECRET:'VIDEO_SOURCE_UNAVAILABLE'}
        for text,code in cases.items():self.assertEqual(error_code(RuntimeError(text)),code)
class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=V.CacheStore(Path(self.tmp.name)/'cache');self.m=V.CacheManager(self.store,runner=self.runner)
    async def asyncTearDown(self):await self.m.stop();self.store.close();self.tmp.cleanup()
    async def runner(self,row):
        self.assertNotIn('youtube_cookies',row)
        await asyncio.sleep(.01);raise ValueError('VIDEO_HTTP_403')
    async def test_credentials_not_in_database_or_public_response(self):
        job=await self.m.create(OWNER,URL,'Demo',True,[cookie()],True)
        ident=job['id'];self.assertIn(ident,self.m.credentials)
        self.assertNotIn(SECRET,json.dumps(job));self.assertNotIn(SECRET,json.dumps(self.store.get(ident)))
        await asyncio.gather(*list(self.m.tasks.values()));self.assertNotIn(ident,self.m.credentials)
        self.assertTrue(self.store.get(ident)['error'].startswith('VIDEO_HTTP_403'))
        for p in Path(self.tmp.name).rglob('*'):
            if p.is_file():self.assertNotIn(SECRET.encode(),p.read_bytes())
    async def test_cancel_clears_queued_credentials(self):
        await self.m.semaphore.acquire()
        job=await self.m.create(OWNER,URL,'Demo',True,[cookie()],True)
        await self.m.cancel(job['id'],OWNER);self.m.semaphore.release()
        self.assertNotIn(job['id'],self.m.credentials)
    async def test_retry_uses_owner_stored_url_not_client_url(self):
        old,_=self.store.create(OWNER,URL,'Old');self.store.update(old['id'],state='failed')
        row=await self.m.retry(old['id'],OWNER)
        self.assertEqual(row['url'],URL);self.assertNotEqual(row['id'],old['id'])
        self.assertEqual(self.store.get(old['id'])['state'],'failed')
    async def test_other_owner_cannot_retry(self):
        old,_=self.store.create(OWNER,URL,'Old');self.store.update(old['id'],state='failed')
        with self.assertRaises(KeyError):await self.m.retry(old['id'],'chrome-extension://'+'b'*32)
    async def test_auth_expired_before_worker_is_started(self):
        row,_=self.store.create(OWNER,URL,'Old');self.m.credentials[row['id']]={'expires':0,'cookies':[cookie()]}
        with self.assertRaisesRegex(ValueError,'AUTH_EXPIRED'):await self.m._download(row)
        self.assertNotIn(row['id'],self.m.credentials)
class RouteTests(unittest.TestCase):
    def test_retry_origin_scope_consent_and_no_secret_echo(self):
        with tempfile.TemporaryDirectory() as d:
            s=V.CacheStore(Path(d)/'c');m=V.CacheManager(s,runner=lambda row:None);app=FastAPI();app.state.video_cache=m;V.attach_video_cache_routes(app)
            old,_=s.create(OWNER,URL,'fixture');s.update(old['id'],state='failed');path='/media-cache/'+old['id']+'/retry'
            with TestClient(app) as client:
                r=client.post(path,json={},headers={'origin':'https://evil.test'});self.assertEqual(r.status_code,403)
                r=client.post(path,json={'youtube_cookies':[cookie()]},headers={'origin':OWNER});self.assertEqual(r.status_code,400);self.assertNotIn(SECRET,r.text)
                r=client.post(path,json={'youtube_cookies':[{**cookie(),'domain':'.google.com'}],'login_consent':True},headers={'origin':OWNER});self.assertEqual(r.status_code,400)
                r=client.post('/media-cache/list',json={},headers={'origin':OWNER});self.assertTrue(r.json()['capabilities']['login_transfer']);self.assertNotIn(SECRET,r.text)
            s.close()
