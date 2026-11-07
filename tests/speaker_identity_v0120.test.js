'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),I=require('../extension/speaker-identity.js'),L=require('../extension/longform.js');
const SID='a'.repeat(32)+':spk0';
test('a direct self-introduction maps to voice while quoted narrative remains only a candidate',()=>{
 const rs=[{cueId:'a',speakerId:SID,text:'我叫小雨，是这里的向导。',original:'我叫小雨，是这里的向导。',subtitle:'',time:1},
  {cueId:'b',speakerId:SID,text:'小雨说她的情况非常复杂。',original:'小雨说她的情况非常复杂。',subtitle:'',time:2}];
 const result=I.validate(rs,[{cueId:'a',speakerId:SID,name:'小雨',quote:'我叫小雨',basis:'self_intro'},
  {cueId:'b',speakerId:SID,name:'小雨',quote:'小雨说她的情况非常复杂。',basis:'self_intro'}]);
 assert.equal(result.accepted.length,1);assert.equal(result.held.length,1);
 assert.equal(I.resolve(result,{}).names[SID],'小雨');
});
test('one repeated caption cue cannot become two independent evidences',()=>{
 const one={cueId:'a',speakerId:SID,name:'小雨',quote:'小雨：大家好',basis:'caption_label'};
 assert.equal(I.resolve({accepted:[],held:[one,{...one}]},{}).names[SID],undefined);
 const two={...one,cueId:'b',time:4};assert.equal(I.resolve({accepted:[],held:[one,two]},{}).names[SID],'小雨');
});
test('new cue can be checked without rescanning previously examined cues',async()=>{
 const session={speakerNames:{},speakerEvidence:{},speakerCandidates:[],captionObservations:[],segments:[]};const store=new Map();let calls=0;
 const context={globalThis:{},validKey:()=>true,loadSession:async()=>session,writeSession:async x=>{Object.assign(session,x)},notebookWrite:async fn=>fn(),
  VideoKnowledgeCore:{cuesWithSpeakers:()=>session.segments},VknSpeakerIdentity:I,VknLongform:L,
  VknCaptions:{cleanObservations:x=>x||[],evidenceFor:()=>[]},readAiConfig:async()=>({endpoint:'http://127.0.0.1:11434/v1/chat/completions'}),
  VknAiConfig:{isLocalOllama:()=>true},askModel:async()=>{calls++;return JSON.stringify({candidates:[]});},
  chrome:{storage:{local:{get:async k=>({[k]:store.get(k)}),set:async x=>{for(const [k,v] of Object.entries(x))store.set(k,v);}}}},
  console,Map,JSON,Error,Date};vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'extension/identity-background.js'),'utf8'),context);
 const push=(n)=>session.segments.push({id:'c'+n,speakerId:SID,speakerStatus:'estimated',time:n,original:'我叫小雨'+n,text:'我叫小雨'+n});
 push(1);await context.vknIdentifySpeakers('video-A');assert.equal(calls,1);
 await context.vknIdentifySpeakers('video-A');assert.equal(calls,1);
 push(2);await context.vknIdentifySpeakers('video-A');assert.equal(calls,2);
});
test('caption-only named dialogue is examined, and two distinct stable cues can name one voice',async()=>{
 const session={speakerNames:{},speakerEvidence:{},speakerCandidates:[],captionObservations:[],segments:[]};const storage=new Map();let calls=0;
 const context={globalThis:{},validKey:()=>true,loadSession:async()=>session,writeSession:async x=>Object.assign(session,x),notebookWrite:async fn=>fn(),
  VideoKnowledgeCore:{cuesWithSpeakers:()=>session.segments},VknSpeakerIdentity:I,VknLongform:L,
  VknCaptions:{cleanObservations:x=>x||[],evidenceFor:()=>[{text:'小雨：你好',samples:2,seenSpan:.8,kind:'original',source:'frame'}]},
  readAiConfig:async()=>({endpoint:'http://127.0.0.1:11434/v1/chat/completions'}),VknAiConfig:{isLocalOllama:()=>true},
  askModel:async()=>{calls++;const c=session.segments.at(-1);return JSON.stringify({candidates:[{speakerId:SID,cueId:c.id,name:'小雨',quote:'小雨：你好',basis:'caption_label'}]});},
  chrome:{storage:{local:{get:async key=>({[key]:storage.get(key)}),set:async obj=>{for(const [k,v] of Object.entries(obj))storage.set(k,v);}}}},
  console,JSON,Error,Map,Date};vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'extension/identity-background.js'),'utf8'),context);
 session.segments=[{id:'cue1',speakerId:SID,speakerStatus:'estimated',time:1,text:'你好',original:'你好'}];
 await context.vknIdentifySpeakers('video');assert.equal(calls,1);assert.equal(session.speakerNames[SID],undefined);
 session.segments.push({id:'cue2',speakerId:SID,speakerStatus:'estimated',time:4,text:'你好',original:'你好'});
 await context.vknIdentifySpeakers('video');assert.equal(calls,2);assert.equal(session.speakerNames[SID],'小雨');
});
