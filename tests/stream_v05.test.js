'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');const path=require('node:path');
const {VknDurableStream,vknPacket}=require('../extension/stream-client.js');const C=require('../extension/core.js');
function store(){const sessions=new Map(),packets=new Map();return {
 sessions,rawPackets:packets,
 async put(m){sessions.set(m.id,structuredClone(m));},
 async packet(m,b){packets.set(m.nextSeq-1,{id:m.id,seq:m.nextSeq-1,buffer:b.slice(0)});await this.put(m);},
 async ack(m,seq){for(const n of packets.keys())if(n<=seq)packets.delete(n);await this.put(m);},
 async packets(id,after,limit){return [...packets.values()].filter(x=>x.seq>after).sort((a,b)=>a.seq-b.seq).slice(0,limit);}
};}
// The production IndexedDB adapter is separate; this deterministic adapter tests transport ordering.
async function client(){const db=store(),events=[],warnings=[];const c=await VknDurableStream.create({sessionKey:'yt:test'}, {},async(k,d)=>events.push({k,d}),m=>warnings.push(m),db);return {c,db,events,warnings};}
const id='a'.repeat(32)+':10:0';
test('audio packet wire format has LE sequence, range, flags and all samples',()=>{
 const p=vknPacket(12,4,4.5,0,new Int16Array([100,-100]));const v=new DataView(p);
 assert.equal(v.getUint32(4,true),12);assert.equal(v.getFloat64(8,true),4);assert.equal(v.getInt16(30,true),-100);assert.equal(p.byteLength,32);
});
test('slow/offline recognition queues all packets rather than dropping',async()=>{
 const {c,db}=await client();for(let i=0;i<100;i++)await c.enqueue(new Int16Array(10),i*.6,(i+1)*.6);
 assert.equal(db.rawPackets.size,100);assert.equal(c.meta.nextSeq,101);assert.equal(c.meta.acked,0);
});
test('only durable ack releases prefix and invalid acknowledgement is rejected',async()=>{
 const {c,db}=await client();for(let i=0;i<5;i++)await c.enqueue(new Int16Array([1]),i,i+.5);
 await c.ack(3);assert.equal(db.rawPackets.size,2);assert.deepEqual([...db.rawPackets.keys()],[4,5]);
 await assert.rejects(c.ack(9),/不存在/);assert.equal(c.meta.acked,3);
});
test('storage failure retains emergency audio and signals backpressure',async()=>{
 const {c,warnings}=await client();c.db.packet=async()=>{throw Error('disk full');};
 await assert.rejects(c.enqueue(new Int16Array([7]),0,.1));assert.equal(c.emergency.length,1);assert.equal(c.meta.nextSeq,1);assert.equal(warnings.length,1);
});
test('result is saved before event cursor advances; retransmitted result is idempotent',async()=>{
 const {c,db,events}=await client();await c.receive({type:'segment',eventId:8,id,text:'你好'});
 assert.equal(events.length,1);assert.equal(db.sessions.get(c.meta.id).lastEvent,8);
 await c.receive({type:'segment',eventId:8,id,text:'你好'});assert.equal(events.length,1);
});
test('failed notebook persistence does not acknowledge result',async()=>{
 const {c,db}=await client();c.onEvent=async()=>{throw Error('storage unavailable');};
 await assert.rejects(c.receive({type:'segment',eventId:4,id,text:'保留'}));assert.equal(c.meta.lastEvent,0);assert.equal(db.sessions.get(c.meta.id).lastEvent,0);
});
test('stop is an ordered finish packet after last audio, not a 3.5 second discard',async()=>{
 const {c,db}=await client();await c.enqueue(new Int16Array([10]),0,.1);await c.enqueue(null,.1,.1,2);
 assert.equal(db.rawPackets.size,2);assert.equal(new DataView(db.rawPackets.get(2).buffer).getUint32(24,true),2);assert.equal(c.meta.closed,true);
 await assert.rejects(c.enqueue(new Int16Array([1]),.1,.2),/已结束/);
});
test('distinct repeated speech is retained while revised ID is replaced',()=>{
 const old={id,revision:1,time:10,text:'Use 3 samples.',original:'Use 3 samples.',language:'en',source:'local-asr'};
 const repeated={...old,id:'a'.repeat(32)+':20:0',time:11};
 const revised={...old,revision:2,text:'使用3个样本。',translation:'使用3个样本。',translationStatus:'done'};
 const rows=C.mergeCues([old,repeated],[revised]);assert.equal(rows.length,2);assert.equal(rows[0].original,'Use 3 samples.');assert.equal(rows[0].text,'使用3个样本。');
 const doc=C.buildDocumentMarkdown({title:'demo',url:'https://example.org/video',segments:rows});assert.match(doc,/识别原文（en，未做原音验证）/);assert.match(doc,/使用3个样本/);
});
test('first ASR start explicitly turns ASR on in shared capture',async()=>{
 const vm=require('node:vm'),fs=require('node:fs');let sent;
 const chrome={runtime:{getURL:()=>'',getContexts:async()=>[],sendMessage:async()=>({ok:true,data:{}})},storage:{local:{get:async()=>({})}},tabs:{onRemoved:{addListener(){}},sendMessage:async()=>({key:'yt:test',time:0})},action:{setBadgeText:async()=>{},setBadgeBackgroundColor:async()=>{}},offscreen:{createDocument:async()=>{}},tabCapture:{getMediaStreamId:async()=>''}};
 const ctx=vm.createContext({VideoKnowledgeCore:require('../extension/core.js'),chrome,console,Promise});vm.runInContext(fs.readFileSync(path.join(__dirname,'../extension/asr-background.js'),'utf8'),ctx);
 ctx.testSender=async(type,data)=>{sent={type,data};return {running:data.enableAsr};};
 vm.runInContext('vknSendOffscreen=testSender',ctx);
 const out=await vm.runInContext('vknStartAsr({id:1,url:"https://video.example"},Promise.resolve("capture"))',ctx);
 assert.equal(sent.data.enableAsr,true);assert.equal(out.running,true);
});

test('a pending disk failure keeps later packets in emergency order',async()=>{
 const {c,db}=await client();const save=db.packet.bind(db);db.packet=async()=>{throw Error('disk full');};
 await assert.rejects(c.enqueue(new Int16Array([7]),0,.1));
 db.packet=save;await assert.rejects(c.enqueue(new Int16Array([8]),.1,.2));
 assert.equal(db.rawPackets.size,0);assert.equal(c.emergency.length,2);
 c.connect=()=>{};await c.retry();assert.equal(c.emergency.length,0);
 assert.deepEqual([...db.rawPackets.values()].map(r=>new DataView(r.buffer).getInt16(28,true)),[7,8]);
});
test('failed acknowledgement storage restores previous ack',async()=>{
 const {c,db}=await client();await c.enqueue(new Int16Array([1]),0,.1);
 db.ack=async()=>{throw Error('disk full');};await assert.rejects(c.ack(1));assert.equal(c.meta.acked,0);
});
test('retry on a finished session does not close before retry is acknowledged',async()=>{
 const {c,db}=await client();await c.enqueue(null,0,0,2);await c.ack(1);
 c.connect=()=>{};await c.retry({translate:true});const sent=[];
 c.socket={readyState:1,send:x=>sent.push(x),close(){}};
 await c.receive({type:'hello',received:1});assert.equal(JSON.parse(sent[0]).type,'retry');
 await c.receive({type:'progress',finished:true,textPending:0,textFailed:1});assert.equal(c.disabled,false);
 await c.receive({type:'retry_ack'});assert.equal(c.awaitingRetry,false);
 await c.receive({type:'progress',finished:true,textPending:1,textFailed:0});assert.equal(c.disabled,false);
});
