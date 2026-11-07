from __future__ import annotations
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from server import video_cache as V
from server.video_download_worker import download
from server.context_review import validate, attach_context_review_routes

OWNER='chrome-extension://'+'a'*32
OTHER='chrome-extension://'+'b'*32
URL='https://www.youtube.com/watch?v=abcdefghijk'

class VideoStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.now=[1000.];self.store=V.CacheStore(Path(self.temp.name)/'video-cache',clock=lambda:self.now[0])
    def tearDown(self):
        self.store.close();self.temp.cleanup()
    def create(self):return self.store.create(OWNER,URL,'测试视频')[0]
    def ready(self):
        row=self.create();(self.store.directory(row['id'])/'media.mp4').write_bytes(b'\x00\x00\x00\x18ftypisom'+b'fixture-not-real-video');self.store.publish(row['id'],'media.mp4');return self.store.get(row['id'])
    def test_url_allowlist(self):
        self.assertEqual(V.normalize_video_url('https://youtu.be/abcdefghijk?t=20'),URL)
        self.assertEqual(V.normalize_video_url('https://www.bilibili.com/video/BV1xx411c7mD/?p=2'),'https://www.bilibili.com/video/BV1xx411c7mD/?p=2')
    def test_denied_urls(self):
        for value in ['http://127.0.0.1/a','https://youtube.com.evil/watch?v=abcdefghijk','https://www.youtube.com/playlist?list=abc','https://a@www.youtube.com/watch?v=abcdefghijk','https://www.youtube.com:8443/watch?v=abcdefghijk','file:///tmp/test','https://b23.tv/abc']:
            with self.subTest(value=value),self.assertRaises(ValueError):V.normalize_video_url(value)
    def test_same_video_dedup_does_not_extend_expiry(self):
        row=self.ready();self.now[0]+=10;new,created=self.store.create(OWNER,URL,'new');self.assertFalse(created);self.assertEqual(new['id'],row['id']);self.assertEqual(new['expires'],row['expires'])
    def test_completion_starts_72_hour_retention(self):
        row=self.create();self.now[0]+=600;(self.store.directory(row['id'])/'media.mp4').write_bytes(b'\x00\x00\x00\x18ftypisom');self.store.publish(row['id'],'media.mp4');self.assertEqual(self.store.get(row['id'])['expires'],1600+72*3600)
    def test_unexpired_video_not_deleted(self):
        row=self.ready();self.now[0]=row['expires']-.01;self.assertEqual(self.store.cleanup()['removed'],0);self.assertTrue(self.store.media_path(row['id']).exists())
    def test_expired_deleted_only_managed_folder(self):
        row=self.ready();other=self.store.root/'notebook.json';other.write_text('keep');self.now[0]=row['expires'];self.assertEqual(self.store.cleanup()['removed'],1);self.assertEqual(other.read_text(),'keep')
    def test_expired_playback_denied_before_cleanup(self):
        row=self.ready();self.now[0]=row['expires'];self.assertRaises(ValueError,self.store.media_path,row['id'])
    def test_restart_marks_active_interrupted(self):
        row=self.create();self.store.recover();self.assertEqual(self.store.get(row['id'])['state'],'interrupted')
    def test_owner_isolated(self):
        row=self.ready();self.assertRaises(KeyError,self.store.get,row['id'],OTHER);self.assertEqual(self.store.list(OTHER),[])
    def test_unknown_directory_not_removed(self):
        self.assertRaises(ValueError,self.store.directory,'../notes');self.assertRaises(ValueError,self.store.directory,'notes')
    def test_missing_marker_prevents_cleanup(self):
        row=self.ready();(self.store.directory(row['id'])/'.vkn-owned').unlink();self.now[0]=row['expires'];self.assertEqual(self.store.cleanup()['failed'],1);self.assertEqual(self.store.get(row['id'])['state'],'cleanup_failed')
    def test_symlink_prevents_cleanup(self):
        row=self.ready();target=Path(self.temp.name)/'valuable';target.write_text('keep');(self.store.directory(row['id'])/'linked.txt').symlink_to(target);self.now[0]=row['expires'];self.assertEqual(self.store.cleanup()['failed'],1);self.assertEqual(target.read_text(),'keep')
    def test_partial_output_not_ready(self):
        row=self.create();self.assertRaises(ValueError,self.store.publish,row['id'],'media.mp4');p=self.store.directory(row['id'])/'media.mp4';p.write_text('html not video');self.assertRaises(ValueError,self.store.publish,row['id'],'media.mp4')
    def test_active_delete_denied(self):
        row=self.create();self.assertRaises(ValueError,self.store.delete,row['id'],OWNER)
    def test_deleted_row_removes_only_owned_directory(self):
        row=self.ready();self.store.delete(row['id'],OWNER);self.assertFalse((self.store.root/row['id']).exists());self.assertRaises(KeyError,self.store.get,row['id'])

class ManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=V.CacheStore(self.temp.name)
        async def runner(row):
            await asyncio.sleep(.01);(self.store.directory(row['id'])/'media.mp4').write_bytes(b'\x00\x00\x00\x18ftypisom');return 'media.mp4'
        self.manager=V.CacheManager(self.store,runner)
    async def asyncTearDown(self):
        await self.manager.stop();self.store.close();self.temp.cleanup()
    async def test_consent_required(self):
        with self.assertRaises(ValueError):await self.manager.create(OWNER,URL)
    async def test_ready_job_uses_clock_retention(self):
        row=await self.manager.create(OWNER,URL,consent=True);await asyncio.gather(*list(self.manager.tasks.values()));self.assertEqual(self.store.get(row['id'])['state'],'ready')
    async def test_cancel_active_preserves_notes_and_no_ready_state(self):
        async def slow(row):await asyncio.sleep(20)
        self.manager.runner=slow
        row=await self.manager.create(OWNER,URL,consent=True);await asyncio.sleep(.01);r=await self.manager.cancel(row['id'],OWNER);self.assertEqual(r['state'],'cancelled');self.assertFalse(self.store.directory(row['id']).exists())
    async def test_cancel_queued_before_first_run(self):
        row=await self.manager.create(OWNER,URL,consent=True);await self.manager.cancel(row['id'],OWNER);self.assertEqual(self.store.get(row['id'])['state'],'cancelled')
    async def test_failure_is_not_success(self):
        async def fail(row):raise ValueError('VIDEO_SOURCE_UNAVAILABLE')
        self.manager.runner=fail;row=await self.manager.create(OWNER,URL,consent=True);await asyncio.gather(*list(self.manager.tasks.values()));self.assertEqual(self.store.get(row['id'])['state'],'failed')
    async def test_routes_require_origin_and_owner(self):
        app=FastAPI();app.state.video_cache=self.manager;V.attach_video_cache_routes(app)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            bad=await client.post('/media-cache/list',json={});self.assertEqual(bad.status_code,403)
            headers={'origin':OWNER};r=await client.post('/media-cache/create',json={'url':URL,'consent':True},headers=headers);self.assertEqual(r.status_code,200);ident=r.json()['id'];await asyncio.gather(*list(self.manager.tasks.values()))
            r=await client.post(f'/media-cache/{ident}/play',json={},headers={'origin':OTHER});self.assertEqual(r.status_code,404)
            r=await client.post(f'/media-cache/{ident}/play',json={},headers=headers);self.assertEqual(r.status_code,200);from urllib.parse import urlsplit
            u=urlsplit(r.json()['url']);r=await client.get(u.path+'?'+u.query,headers={'range':'bytes=0-7'});self.assertIn(r.status_code,[200,206]);self.assertEqual(r.headers['cache-control'],'no-store')
            r=await client.get(u.path+'?token=bad');self.assertEqual(r.status_code,403)
    async def test_disk_quota_does_not_evict_unexpired(self):
        with patch.object(self.store,'usage',return_value=V.TOTAL_BYTES):
            with self.assertRaisesRegex(ValueError,'VIDEO_SPACE'):await self.manager.create(OWNER,URL,consent=True)

class CorrectionTests(unittest.TestCase):
    def data(self,**edit):
        text='大家往往恐惧位置，所以很害怕死亡。'
        return {'items':[{'id':'cue-0','text':text}], 'edits':[{'id':'cue-0','before':'位置','after':'未知','kind':'common_term','confidence':.98,'evidence':text,'reason':'恐惧不可预知的未来符合讨论死亡的上下文。',**edit}]}
    def test_valid_patch_with_phonetic_fixture(self):
        data=self.data();result=validate(data,checker=lambda a,b:(a,b)==('位置','未知'));self.assertEqual(len(result['applied']),1);self.assertIn('位置',data['items'][0]['text'])
    def test_pinyin_mismatch_hold(self):self.assertEqual(len(validate(self.data(),checker=lambda a,b:False)['held']),1)
    def test_negation_changes_held(self):self.assertEqual(len(validate(self.data(before='恐惧',after='不怕'),checker=lambda a,b:True)['held']),1)
    def test_numbers_held(self):self.assertEqual(len(validate(self.data(before='位置',after='一位'),checker=lambda a,b:True)['held']),1)
    def test_evidence_must_be_exact_and_contextual(self):
        for e in ['位置','编造的上下文不在原句里面','']:
            self.assertEqual(len(validate(self.data(evidence=e),checker=lambda a,b:True)['held']),1)
    def test_name_kind_held(self):self.assertEqual(len(validate(self.data(kind='person_name'),checker=lambda a,b:True)['held']),1)
    def test_low_self_score_hold(self):self.assertEqual(len(validate(self.data(confidence=.5),checker=lambda a,b:True)['held']),1)
    def test_unknown_id_hold(self):self.assertEqual(len(validate(self.data(id='unknown'),checker=lambda a,b:True)['held']),1)
    def test_manual_or_uncertain_not_changed(self):
        for key in ['manual','uncertain']:
            data=self.data();data['items'][0][key]=True;self.assertEqual(len(validate(data,checker=lambda a,b:True)['held']),1)
    def test_optional_dependency_failure_no_auto_apply(self):
        with patch('server.context_review.availability',return_value={'available':False}):self.assertEqual(validate(self.data())['applied'],[])
    def test_overlapping_patch_held(self):
        data=self.data();data['edits']*=2;result=validate(data,checker=lambda a,b:True);self.assertEqual(len(result['applied']),1);self.assertEqual(len(result['held']),1)
    def test_validator_endpoint_rejects_web_origin(self):
        app=FastAPI();attach_context_review_routes(app)
        with TestClient(app) as client:
            self.assertEqual(client.post('/text-review/validate',json=self.data(),headers={'origin':'https://evil.example'}).status_code,403)
            self.assertEqual(client.post('/text-review/validate',content=b'x'*70000,headers={'origin':OWNER,'content-type':'application/json'}).status_code,413)
            self.assertEqual(client.post('/text-review/validate',json={'items':[],'edits':[]},headers={'origin':OWNER}).status_code,200)

class WorkerTests(unittest.TestCase):
    def test_options_are_public_only_and_do_not_request_subtitles_or_cookies(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/('a'*32);folder.mkdir();(folder/'.vkn-owned').write_text(folder.name);captured={}
            class Fake:
                def __init__(self,opts):captured.update(opts)
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def extract_info(self,url,download):
                    (folder/'media.mp4').write_bytes(b'\x00\x00\x00\x18ftypisom');return {'id':'abcdefghijk'}
            with patch('server.video_download_worker.emit'):
                download({'url':URL,'directory':str(folder)},factory=Fake)
            self.assertIsNone(captured['cookiefile']);self.assertIsNone(captured['cookiesfrombrowser']);self.assertFalse(captured['writesubtitles']);self.assertFalse(captured['allow_unplayable_formats']);self.assertEqual(captured['remote_components'],set());self.assertTrue(captured['noplaylist'])
            with self.assertRaises(ValueError):captured['match_filter']({'is_live':True})
            with self.assertRaises(ValueError):captured['match_filter']({'has_drm':True})
