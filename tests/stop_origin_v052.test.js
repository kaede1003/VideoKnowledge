'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const {makeHarness:rawHarness}=require('./ai_harness');const makeHarness=(store={},options={})=>rawHarness({store,...options});const Origin=require('../extension/local-origin');
const {VknDurableStream}=require('../extension/stream-client');
const E=path.join(__dirname,'../extension'),read=n=>fs.readFileSync(path.join(E,n),'utf8');
const cues=[{time:1,text:'保留原文。'},{time:2,text:'取消不应清空。'},{time:3,text:'保存已有笔记。'}];
function offlineHarness({ack=true,stuckDisk=false,lora=false}={}){
 const listeners=[],events=[],stats={disconnected:0,stopped:0,closed:0,finished:0};
 const tracks=[{stop(){stats.stopped++}}, {stop(){stats.stopped++}}];
 const src={disconnect(){stats.disconnected++;},connect(){}};
 const gain={disconnect(){},gain:{value:0}};
 const ac={close(){stats.closed++;return Promise.resolve();}};
 const client={meta:{context:{tabId:1,sessionKey:'test'},lastTime:10,closed:false},chain:stuckDisk?new Promise(()=>{}):Promise.resolve(),emergency:[],
 enqueue(){return Promise.resolve();},finish(){stats.finished++;return stuckDisk?new Promise(()=>{}):Promise.resolve();}};
 const chrome={runtime:{onMessage:{addListener:f=>listeners.push(f)},getURL:p=>'chrome-extension://'+ 'a'.repeat(32)+'/'+p,
 sendMessage:async m=>{events.push(m);return {ok:true};}}};
 const node={disconnect(){},port:{onmessage:null,postMessage(m){if(ack)queueMicrotask(()=>vm.runInContext('workletWaiters.get('+JSON.stringify(m.id)+')?.()',c));}}};
 const c=vm.createContext({console,chrome,performance,crypto,Int16Array,ArrayBuffer,DataView,Promise,structuredClone,URL,
 setTimeout:(fn,t)=>setTimeout(fn,Math.min(t,50)),clearTimeout,setInterval,clearInterval,
 VknStreamDB:{all:async()=>[]},VknDurableStream:{},WebSocket:{OPEN:1,CONNECTING:0},navigator:{},
 node,gain,ac,src,tracks,client});
 vm.runInContext(read('offscreen.js'),c);
 vm.runInContext(`capture={tabId:1,sessionKey:'test'};stream={getTracks:()=>tracks};ctx=ac;source=src;processor=node;silent=gain;audioClient=client;asrActive=true;asrPhase='running';loraActive=${lora};durableClients.set('test',client);`,c);
 const run=s=>vm.runInContext(s,c);
 const send=m=>new Promise(resolve=>listeners[0]({...m,target:'offscreen'},{},resolve));
 return {c,run,send,stats,client,tracks,events};
}
test('local origin commands only append this exact extension; never grant all origins or change network bind',()=>{
 assert.equal(Origin.origin('a'.repeat(32)),'chrome-extension://'+'a'.repeat(32));
 const command=Origin.command('b'.repeat(32));
 assert.match(command,/GetEnvironmentVariable/);assert.match(command,/SetEnvironmentVariable/);
 assert.match(command,/chrome-extension:\/\/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/);
 assert.doesNotMatch(command,/chrome-extension:\/\/\*|OLLAMA_HOST|Stop-Process|taskkill/);
 assert.throws(()=>Origin.command('abc; exit'),/ID/);
});
test('local 403 at tags says source restriction and explicitly no API key',async()=>{
 const h=makeHarness({}, {fetch:async()=>new Response('',{status:403})});
 const r=await h.send({type:'VKN_AI_TEST'});assert.equal(r.ok,false);
 assert.match(r.error,/AI_LOCAL_ORIGIN_403/);assert.match(r.error,/不需要 API Key/);assert.match(r.error,/OLLAMA_ORIGINS/);
});
test('local chat 403 never prompts to buy or fill an API key, including stale saved credentials',async()=>{
 const h=makeHarness({vknAiConfig:{provider:'ollama',endpoint:'http://127.0.0.1:11434/v1/chat/completions',model:'qwen2.5:3b',apiKey:'OLD_SECRET'}},
 {fetch:async u=>u.endsWith('/api/tags')?new Response(JSON.stringify({models:[{name:'qwen2.5:3b'}]})):new Response('',{status:403})});
 const r=await h.send({type:'VKN_AI_TEST'});assert.match(r.error,/AI_LOCAL_ORIGIN_403/);assert.doesNotMatch(r.error,/OLD_SECRET/);
 for(const r of h.requests)assert.equal(r.opts.headers?.authorization,undefined);
});
test('local 401 differs from source 403 and custom provider auth errors remain separate',async()=>{
 const h=makeHarness({}, {fetch:async()=>new Response('',{status:401})});assert.match((await h.send({type:'VKN_AI_TEST'})).error,/AI_LOCAL_ACCESS_401/);
 const cloud=makeHarness({vknAiConfig:{provider:'custom',endpoint:'https://example.test/v1/chat/completions',model:'model',apiKey:'SECRET'}},{fetch:async()=>new Response('',{status:403})});
 const r=await cloud.send({type:'VKN_AI_TEST'});assert.match(r.error,/AI_HTTP_403/);assert.doesNotMatch(r.error,/SECRET|OLLAMA_ORIGINS/);
});
test('deep model request can be cancelled without affecting stored notebook',async()=>{
 let entered;const ready=new Promise(r=>entered=r);
 const h=makeHarness({'vkn:session:old':{aiMarkdown:'keep me'}},{fetch:async(u,o)=>{
   if(u.endsWith('/api/tags'))return new Response(JSON.stringify({models:[{name:'qwen2.5:3b'}]}));
   entered();return new Promise((_,reject)=>o.signal.addEventListener('abort',()=>reject(Error('aborted')),{once:true}));
 }});
 const run=h.send({type:'VKN_AI_GENERATE',requestId:'wanted',cues});await ready;
 const no=await h.send({type:'VKN_AI_CANCEL',requestId:'other'});assert.equal(no.data.cancelled,false);
 const yes=await h.send({type:'VKN_AI_CANCEL',requestId:'wanted'});assert.equal(yes.data.cancelled,true);
 const r=await run;assert.equal(r.ok,false);assert.match(r.error,/AI_CANCELLED/);assert.equal(h.state['vkn:session:old'].aiMarkdown,'keep me');
});
test('normal stop cuts input before awaiting tail, releases both tracks and enqueues finish',async()=>{
 const h=offlineHarness();const p=h.run('detachAsr()');
 assert.equal(h.stats.disconnected,1);assert.equal(h.run('asrActive'),false);
 const r=await p;assert.equal(r.running,false);assert.equal(r.tailConfirmed,true);
 assert.equal(h.stats.stopped,2);assert.equal(h.stats.finished,1);assert.equal(h.run('capture'),null);
});
test('unresponsive/suspended worklet still stops tracks and explicitly warns about unconfirmed tail',async()=>{
 const h=offlineHarness({ack:false});const r=await h.run('detachAsr()');
 assert.equal(r.tailConfirmed,false);assert.match(r.warning,/200毫秒/);assert.equal(h.stats.stopped,2);assert.equal(h.stats.finished,1);
});
test('stalled IndexedDB does not hold capture open, client remains for recovery',async()=>{
 const h=offlineHarness({stuckDisk:true});const r=await h.run('detachAsr()');
 assert.equal(r.running,false);assert.equal(h.stats.stopped,2);assert.equal(h.run('durableClients.size'),1);assert.equal(r.draining,true);
});
test('duplicate stop commands are idempotent and write only one terminal marker',async()=>{
 const h=offlineHarness();await h.run('Promise.all([detachAsr(),detachAsr()])');
 assert.equal(h.stats.finished,1);assert.equal(h.stats.stopped,2);
 await h.run('detachAsr()');assert.equal(h.stats.finished,1);
});
test('stopping ASR preserves a deliberately running LoRA stream; stopping all releases it',async()=>{
 const h=offlineHarness({lora:true});await h.run('detachAsr()');assert.equal(h.stats.stopped,0);
 await h.run('stopCapture()');assert.equal(h.stats.stopped,2);assert.equal(h.run('loraActive'),false);
});
test('a stale player transition waiting on disk cannot reopen audio after stop',async()=>{
 const h=offlineHarness();let release;h.client.chain=new Promise(r=>release=r);
 h.run('player.paused=false');const update=h.run('updatePlayer({time:11,paused:true,reset:true})');
 await new Promise(r=>setImmediate(r));await h.run('detachAsr()');release();await update;
 assert.equal(h.run('asrActive'),false);assert.equal(h.run('processor'),null);assert.equal(h.stats.stopped,2);
});
test('stop rejects a different-tab command rather than killing another user session',async()=>{
 const h=offlineHarness();const r=await h.send({type:'VKN_ASR_STOP',expectedTabId:2});assert.equal(r.ok,false);assert.equal(h.stats.stopped,0);
 await h.run('stopCapture()');
});
test('late getUserMedia success after stop immediately releases returned tracks',async()=>{
 const h=offlineHarness();await h.run('stopCapture()');h.stats.stopped=0;
 let accept;h.c.navigator.mediaDevices={getUserMedia:()=>new Promise(r=>accept=r)};
 const p=h.run("startCapture({tabId:1,sessionKey:'new',streamId:'id',enableAsr:true})");const rejection=assert.rejects(p,/CAPTURE_CANCELLED/);
 await new Promise(r=>setImmediate(r));await h.run('stopCapture()');accept({getTracks:()=>h.tracks});await rejection;
 assert.equal(h.stats.stopped,2);assert.equal(h.run('capture'),null);
});
test('stop invalidates pending worker start and bypasses serialized start queue',async()=>{
 let unblock;const calls=[];
 const chrome={runtime:{getURL:()=>'',getContexts:async()=>[{}],sendMessage:async m=>{calls.push(m);return {ok:true,data:{running:false,tabId:1}};}},
 storage:{local:{get:async()=>({})}},tabs:{onRemoved:{addListener(){}},sendMessage:async(_id,m)=>m.type==='VKN_ASR_CONTEXT'?new Promise(r=>unblock=r):undefined},
 action:{setBadgeText:async()=>{},setBadgeBackgroundColor:async()=>{}},offscreen:{createDocument:async()=>{}},tabCapture:{getMediaStreamId:async()=>''}};
 const ctx=vm.createContext({chrome,console,Promise,setTimeout,clearTimeout});vm.runInContext(read('asr-background.js'),ctx);
 const p=vm.runInContext('vknRequestAsrStart({id:1,url:"https://video.test"})',ctx);const rejection=assert.rejects(p,/CAPTURE_CANCELLED/);
 while(!unblock)await new Promise(r=>setImmediate(r));
 await vm.runInContext('vknStopAsr(1)',ctx);assert.ok(calls.some(m=>m.type==='VKN_ASR_STOP'));
 unblock({key:'test'});await rejection;assert.ok(!calls.some(m=>m.type==='VKN_ASR_START'));
});
test('finish waits for queued audio commit in background and uses its correct terminal timestamp',async()=>{
 let unblock;const packets=[];
 const db={put:async()=>{},packet:async(m,b)=>{packets.push(b);if(m.nextSeq===2)await new Promise(r=>unblock=r);}};
 const c=await VknDurableStream.create({sessionKey:'test'},{},async()=>{},()=>{},db);
 const pending=c.enqueue(new Int16Array([1,2]),7,8);const finish=c.finish();
 while(!unblock)await new Promise(r=>setImmediate(r));assert.equal(packets.length,1);unblock();await pending;await finish;
 assert.equal(packets.length,2);assert.equal(new DataView(packets[1]).getFloat64(8,true),8);assert.equal(new DataView(packets[1]).getUint32(24,true),2);
 await c.finish();assert.equal(packets.length,2);
});
test('UI offers independent stop while busy, no automatic subtitle collection after stop',()=>{
 const s=read('content.js');assert.match(s,/vkn-stop-all/);assert.match(s,/state\.stopRequested=stopping;if\(stopping\)state\.active=false/);
 assert.match(s,/state\.stopAllBusy=true;state\.stopRequested=true;state\.active=false/);assert.match(s,/VKN_AI_CANCEL/);
});
test('late worker pause/resume response after stop never announces recording again',async()=>{
 let release;const emitted=[];
 const chrome={runtime:{getURL:()=>'',getContexts:async()=>[{}],sendMessage:async m=>{
   if(m.type==='VKN_ASR_STATUS')return {ok:true,data:{running:true,tabId:1}};
   if(m.type==='VKN_ASR_PAUSE')return new Promise(r=>{release=r;});
   return {ok:true,data:{running:false,tabId:1}};
 }},tabs:{onRemoved:{addListener(){}},sendMessage:async(_id,m)=>{emitted.push(m);}},
 action:{setBadgeText:async()=>{}}};
 const ctx=vm.createContext({chrome,console,Promise,setTimeout,clearTimeout});vm.runInContext(read('asr-background.js'),ctx);
 const p=vm.runInContext('vknPauseAsr(true)',ctx);
 while(!release)await new Promise(r=>setImmediate(r));
 await vm.runInContext('vknStopAsr(1)',ctx);
 release({ok:true,data:{running:false,paused:false}});
 const result=await p;assert.equal(result.running,false);assert.equal(result.cancelled,true);
 assert.ok(!emitted.some(x=>x.running===true));
});
