'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const E=path.join(__dirname,'../extension');
const tick=()=>new Promise(r=>setImmediate(r));
async function until(f){for(let i=0;i<100;i++){if(f())return;await tick();}throw Error('fixture condition not reached');}
function harness({grant='denied',status={},noPicker=false,syncThrow=false}={}){
 const messages=[],events=[],pickers=[],cancelled=[],removed=[];let contexts=1,metaCount=0,key='test-video';
 const state={running:false,captureRunning:false,tabId:null,...status};
 const chrome={
  runtime:{getURL:p=>'chrome-extension://'+'a'.repeat(32)+'/'+p,lastError:null,getContexts:async()=>contexts?[{}]:[],sendMessage:async m=>{
   messages.push(m);if(m.type==='VKN_ASR_STATUS')return {ok:true,data:{...state}};
   if(m.type==='VKN_ASR_START'||m.type==='VKN_ASR_ATTACH'){Object.assign(state,{running:true,captureRunning:true,tabId:1,sessionKey:key});return {ok:true,data:{...state}};}
   if(m.type==='VKN_CAPTURE_STOP'||m.type==='VKN_ASR_STOP'){Object.assign(state,{running:false,captureRunning:false});return {ok:true,data:{...state}};}
   return {ok:true,data:{}};
  }},
  storage:{local:{get:async()=>({})}},
  tabs:{sendMessage:async(id,m)=>{events.push({id,...m});if(m.type==='VKN_ASR_CONTEXT'){metaCount++;return {key,time:1,paused:false};}},onRemoved:{addListener:f=>removed.push(f)}},
  action:{setBadgeText:async()=>{},setBadgeBackgroundColor:async()=>{}},
  scripting:{executeScript:async()=>{}},offscreen:{createDocument:async()=>{contexts=1;}},
  tabCapture:{getMediaStreamId:()=>{if(syncThrow)throw Error('Extension has not been invoked for this tab');if(grant==='allowed')return Promise.resolve('native-id');return Promise.reject(Error(grant==='denied'?'Extension has not been invoked for this tab':'device is busy'));}},
  desktopCapture:noPicker?undefined:{chooseDesktopMedia:(sources,callback)=>{pickers.push({sources,callback});return pickers.length;},cancelChooseDesktopMedia:id=>cancelled.push(id)}
 };
 const c=vm.createContext({chrome,console,Promise,setTimeout,clearTimeout,VideoKnowledgeCore:{speechOptions:()=>({})}});
 vm.runInContext(fs.readFileSync(path.join(E,'asr-background.js'),'utf8'),c);
 const tab={id:1,url:'https://www.youtube.com/watch?v=example'};
 const run=s=>vm.runInContext(s,c);c.tab=tab;
 return {c,run,messages,events,pickers,cancelled,removed,state,chrome,setKey:v=>key=v,metaCount:()=>metaCount};
}
test('new permission offers only browser tabs+audio and native action shortcut',()=>{
 const m=JSON.parse(fs.readFileSync(path.join(E,'manifest.json')));assert.ok(m.permissions.includes('desktopCapture'));
 assert.equal(m.commands._execute_action.suggested_key.default,'Alt+Shift+V');
 assert.ok(!m.host_permissions.includes('<all_urls>'));
});
test('page start without activeTab opens chooser and starts once with desktop source',async()=>{
 const h=harness();const p=h.run('vknRequestAsrStart(tab,true)');await until(()=>h.pickers.length);
 assert.deepEqual([...h.pickers[0].sources],['tab','audio']);assert.ok(!h.messages.some(m=>m.type==='VKN_ASR_START'));
 h.pickers[0].callback('picked-id',{canRequestAudioTrack:true});assert.equal((await p).running,true);
 const starts=h.messages.filter(m=>m.type==='VKN_ASR_START');assert.equal(starts.length,1);assert.equal(starts[0].mediaSource,'desktop');assert.equal(starts[0].enableAsr,true);
 assert.ok(h.events.some(e=>e.startedByUser===true));
});
test('already authorized tab start does not show chooser',async()=>{
 const h=harness({grant:'allowed'});await h.run('vknRequestAsrStart(tab,true)');assert.equal(h.pickers.length,0);
 assert.equal(h.messages.find(m=>m.type==='VKN_ASR_START').mediaSource,'tab');
});
test('duplicate page clicks share a single pending chooser and promise',async()=>{
 const h=harness();const p=h.run('vknRequestAsrStart(tab,true)');const q=h.run('vknRequestAsrStart(tab,true)');assert.equal(p,q);
 await until(()=>h.pickers.length);assert.equal(h.pickers.length,1);h.pickers[0].callback('id',{canRequestAudioTrack:true});await Promise.all([p,q]);
 assert.equal(h.messages.filter(m=>m.type==='VKN_ASR_START').length,1);
});
test('user cancellation starts neither audio nor WebSocket',async()=>{
 const h=harness();const p=h.run('vknRequestAsrStart(tab,true)');const rejection=assert.rejects(p,/CAPTURE_CANCELLED/);await until(()=>h.pickers.length);
 h.pickers[0].callback('',{});await rejection;assert.ok(!h.messages.some(m=>m.type==='VKN_ASR_START'));assert.equal(h.run('vknCapturePickers.size'),0);
});
test('audio checkbox unchecked refuses silent recording explicitly',async()=>{
 const h=harness();const p=h.run('vknRequestAsrStart(tab,true)');const rejection=assert.rejects(p,/CAPTURE_NO_AUDIO/);await until(()=>h.pickers.length);
 h.pickers[0].callback('id',{canRequestAudioTrack:false});await rejection;assert.ok(!h.messages.some(m=>m.type==='VKN_ASR_START'));
});
test('stop cancels chooser immediately; late selection cannot restart capture',async()=>{
 const h=harness();const p=h.run('vknRequestAsrStart(tab,true)');const rejection=assert.rejects(p,/CAPTURE_CANCELLED/);await until(()=>h.pickers.length);
 await h.run('vknStopAsr(1,true)');await rejection;assert.deepEqual(h.cancelled,[1]);h.pickers[0].callback('late-id',{canRequestAudioTrack:true});await tick();
 assert.ok(!h.messages.some(m=>m.type==='VKN_ASR_START'));assert.equal(h.run('vknStartRequests.size'),0);
});
test('changing video while chooser is open does not attach audio to the wrong session',async()=>{
 const h=harness();const p=h.run('vknRequestAsrStart(tab,true)');const rejection=assert.rejects(p,/CAPTURE_PAGE_CHANGED/);await until(()=>h.pickers.length);
 h.setKey('another-video');h.pickers[0].callback('id',{canRequestAudioTrack:true});await rejection;assert.ok(!h.messages.some(m=>m.type==='VKN_ASR_START'));
});
test('closing source tab cancels the chooser',async()=>{
 const h=harness();const p=h.run('vknRequestAsrStart(tab,true)');const rejection=assert.rejects(p,/CAPTURE_CANCELLED/);await until(()=>h.pickers.length);
 await h.removed[0](1);await rejection;assert.deepEqual(h.cancelled,[1]);
});
test('synchronous permission exceptions also use explicit picker',async()=>{
 const h=harness({syncThrow:true});const p=h.run('vknRequestAsrStart(tab,true)');await until(()=>h.pickers.length);h.pickers[0].callback('id',{canRequestAudioTrack:true});assert.equal((await p).running,true);
});
test('non-permission capture failure is not disguised as a permission problem',async()=>{
 const h=harness({grant:'device'});await assert.rejects(h.run('vknRequestAsrStart(tab,true)'),/device is busy/);assert.equal(h.pickers.length,0);
});
test('unsupported picker preserves keyboard instruction and does not claim success',async()=>{
 const h=harness({noPicker:true});await assert.rejects(h.run('vknRequestAsrStart(tab,true)'),/Alt\+Shift\+V/);assert.ok(!h.messages.some(m=>m.type==='VKN_ASR_START'));
});
test('existing ASR returns its state rather than creating a second stream',async()=>{
 const h=harness({status:{running:true,captureRunning:true,tabId:1}});assert.equal((await h.run('vknRequestAsrStart(tab,true)')).running,true);assert.equal(h.pickers.length,0);assert.ok(!h.messages.some(m=>m.type==='VKN_ASR_START'));
});
test('a different tab already capturing is not replaced',async()=>{
 const h=harness({status:{running:true,captureRunning:true,tabId:2}});await assert.rejects(h.run('vknRequestAsrStart(tab,true)'),/另一个标签/);assert.equal(h.pickers.length,0);
});
test('offscreen acquisition uses selected media source, no microphone fallback or duplicate desktop playback',()=>{
 const s=fs.readFileSync(path.join(E,'offscreen.js'),'utf8');assert.match(s,/chromeMediaSource:mediaSource/);assert.match(s,/mediaSource==='tab'/);assert.match(s,/getAudioTracks/);assert.doesNotMatch(s,/getUserMedia\(\{\s*audio:true/);
});
test('native shortcut/action cancels a pending page chooser instead of queuing another capture',async()=>{
 const h=harness();const p=h.run('vknRequestAsrStart(tab,true)');const rejection=assert.rejects(p,/CAPTURE_CANCELLED/);await until(()=>h.pickers.length);
 await h.run('vknToggleAsr(tab)');await rejection;assert.deepEqual(h.cancelled,[1]);assert.equal(h.pickers.length,1);assert.ok(!h.messages.some(m=>m.type==='VKN_ASR_START'));
});
