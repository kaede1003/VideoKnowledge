"""Transport fault injection: real manager/store, fake socket and inference."""
import asyncio
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from server.stream_store import StreamStore
from server.stream_service import StreamManager
from server.stream_protocol import Packet


class Socket:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.outgoing = asyncio.Queue()
        self.closed = []
        self.sent = []
    async def send_json(self, value):
        self.sent.append(value)
        await self.outgoing.put(value)
    async def receive(self):
        return await self.incoming.get()
    async def close(self, code=1000, reason=''):
        self.closed.append((code, reason))
        await self.incoming.put({'type': 'websocket.disconnect', 'code': code})
    async def send(self, text):
        await self.incoming.put({'type':'websocket.receive', 'text':text})
    async def binary(self, raw):
        await self.incoming.put({'type':'websocket.receive', 'bytes':raw})
    async def next(self, kind):
        for _ in range(30):
            value = await asyncio.wait_for(self.outgoing.get(), 2)
            if value['type'] == kind:
                return value
        raise AssertionError('missing ' + kind)


class Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = StreamStore(Path(self.tmp.name) / 'store.sqlite3', min_free=0)
        self.manager = StreamManager(self.store, object())
        self.open_sockets = []
        self.jobs = []
    async def asyncTearDown(self):
        await self.manager.stop()
        for socket in self.open_sockets:
            await socket.close()
        for task in self.jobs:
            task.cancel()
        await asyncio.gather(*self.jobs, return_exceptions=True)
        self.store.close()
        self.tmp.cleanup()
    async def connect(self, ident='a'*32):
        ws = Socket();self.open_sockets.append(ws)
        task = asyncio.create_task(self.manager.serve(ws));self.jobs.append(task)
        await ws.next('ready')
        await ws.send(json.dumps({'type':'hello','sessionId':ident,'videoKey':'yt:fixture','options':{'translate':False}}))
        return ws, task
    async def test_cancelled_request_releases_owner_without_false_error(self):
        ws, task = await self.connect();await ws.next('hello')
        await ws.binary(Packet(1,0,.1,0,b'\x01\x00'*1600).encode());await ws.next('ack')
        task.cancel()
        await asyncio.wait_for(task,2)
        self.assertNotIn('a'*32,self.manager.connections)
        self.assertEqual(self.store.session('a'*32)['received'],1)
        again, other = await self.connect();await again.next('hello')
        self.assertFalse(other.done())

    async def test_duplicate_socket_is_retryable_and_preserves_original_owner(self):
        one, job = await self.connect();await one.next('hello')
        two, other = await self.connect();event = await two.next('error')
        self.assertFalse(event['fatal']);self.assertTrue(event['retryable'])
        self.assertEqual(event['code'], 'SESSION_BUSY')
        await asyncio.wait_for(other, 2)
        self.assertIn('a'*32, self.manager.connections)
        await one.send('ping');await one.next('pong')
        self.assertFalse(job.done())
    async def test_stale_owner_cleanup_does_not_discard_new_connection(self):
        one, job = await self.connect();await one.next('hello')
        self.manager.owners['a'*32]['seen'] -= 100
        two, other = await self.connect();await two.next('hello')
        await asyncio.wait_for(job, 2)
        self.assertIs(self.manager.owners['a'*32]['ws'], two)
        await two.send('ping');await two.next('pong')
        self.assertIn('a'*32, self.manager.connections)
    async def test_backpressure_does_not_make_inflight_next_packet_fatal(self):
        ws, job = await self.connect();await ws.next('hello')
        one = Packet(1,0,.1,0,b'\x01\x00'*1600).encode()
        two = Packet(2,.1,.2,0,b'\x01\x00'*1600).encode()
        with patch.object(self.store,'receive',side_effect=BufferError('synthetic capacity')):
            await ws.binary(one);await ws.binary(two)
            message=await ws.next('backpressure');self.assertEqual(message['received'],0)
            await asyncio.wait_for(job,2)
        self.assertFalse(any(x['type']=='ack' for x in ws.sent))
        self.assertFalse(any(x.get('fatal') for x in ws.sent))
        again,new = await self.connect();hello=await again.next('hello');self.assertEqual(hello['received'],0)
        await again.binary(one);self.assertEqual((await again.next('ack'))['seq'],1)
        await again.binary(two);self.assertEqual((await again.next('ack'))['seq'],2)
    async def test_database_busy_returns_backpressure_not_silent_disconnect(self):
        ws, task=await self.connect();await ws.next('hello')
        with patch.object(self.store,'receive',side_effect=sqlite3.OperationalError('synthetic database locked')):
            await ws.binary(Packet(1,0,.1,0,b'\x01\x00'*1600).encode())
            out=await ws.next('backpressure');self.assertTrue(out['retryable'])
            await asyncio.wait_for(task,2)
        self.assertEqual(self.store.session('a'*32)['received'],0)
    async def test_sender_failure_is_reported_and_socket_closed_for_replay(self):
        with patch.object(self.store,'events',side_effect=RuntimeError('synthetic outbox error')):
            ws,task=await self.connect();await ws.next('hello')
            event=await ws.next('error');self.assertEqual(event['code'],'SERVER_TRANSIENT')
            self.assertFalse(event['fatal']);await asyncio.wait_for(task,2)
        self.assertTrue(ws.closed)
        self.assertEqual(self.manager.last_disconnect['code'],1011)
    async def test_worker_query_failure_is_supervised(self):
        self.manager.worker_retry_seconds=.01
        method=self.store.pending_sessions
        count=[0]
        def pending():
            count[0]+=1
            if count[0]==1:raise sqlite3.OperationalError('synthetic temporary query failure')
            return method()
        with patch.object(self.store,'pending_sessions',side_effect=pending):
            self.manager.start()
            await asyncio.sleep(.06)
            self.assertEqual(self.manager.snapshot()['workers']['asr']['restarts'],1)
            self.assertFalse(self.manager.tasks[0].done())
    async def test_heartbeat_timeout_releases_session_without_deleting_audio(self):
        self.manager.heartbeat_seconds=.05
        ws, task=await self.connect();await ws.next('hello')
        await ws.binary(Packet(1,0,.1,0,b'\x01\x00'*1600).encode());await ws.next('ack')
        await asyncio.wait_for(task,2)
        self.assertNotIn('a'*32,self.manager.connections)
        self.assertEqual(self.store.session('a'*32)['received'],1)
        self.assertEqual(self.manager.last_disconnect['cause'],'transport_timeout')


class LauncherTests(unittest.TestCase):
    def test_command_keeps_loopback_websocket_and_fault_trace(self):
        from scripts.run_local_service import command
        args=command()
        self.assertIn('faulthandler',args)
        self.assertEqual(args[args.index('--host')+1],'127.0.0.1')
        self.assertEqual(args[args.index('--ws')+1],'websockets')
        self.assertNotIn('--reload',args)
    def test_windows_exit_status_representation(self):
        from scripts.run_local_service import exit_hex
        self.assertEqual(exit_hex(-1073741819),'0xC0000005')
    def test_diagnostics_health_redacts_paths(self):
        from scripts import diagnose_local_service as diag
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return json.dumps({'service':'vkn-asr','ok':True,'cache':'PRIVATE_PATH','model':'fixture'}).encode()
        with patch.object(diag,'build_opener') as opener:
            opener.return_value.open.return_value=Response()
            result=diag.get_health()
        self.assertNotIn('cache',result)
        self.assertEqual(result['model'],'fixture')
