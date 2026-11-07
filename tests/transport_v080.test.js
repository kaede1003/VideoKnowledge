'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function setup(){
 let now=100000;const timers=[],intervals=[],all=[],events=[],saved=[],packets=[];
 class WS{constructor(){this.readyState=0;this.sent=[];this.bufferedAmount=0;all.push(this);}send(x){this.sent.push(x);}close(code=1000){this.readyState=3;this.onclose?.({code,wasClean:code===1000});}open(){this.readyState=1;this.onopen();}}
 const env={module:{exports:{}},console,Promise,JSON,Number,Math,Error,DataView,ArrayBuffer,Int16Array,structuredClone,
 WebSocket:WS,AbortController,Date:{now:()=>now},setTimeout:(f,ms)=>{const x={f,ms};timers.push(x);return x;},clearTimeout:x=>{if(x)x.off=true;},
 setInterval:(f,ms)=>{const x={f,ms};intervals.push(x);return x;},clearInterval:x=>{if(x)x.off=true;}};
 vm.createContext(env);vm.runInContext(fs.readFileSync(path.join(__dirname,'../extension/stream-client.js'),'utf8'),env);
 const db={put:async m=>saved.push(structuredClone(m)),ack:async()=>{},packets:async()=>packets};
 const meta={id:'a'.repeat(32),context:{sessionKey:'yt:fixture'},options:{},nextSeq:1,acked:0,lastEvent:0,closed:false};
 const c=new env.module.exports.VknDurableStream(meta,async(k,d)=>events.push({k,d}),()=>{},db);
 return {c,timers,intervals,all,events,saved,env,advance:ms=>now+=ms};
}
test('hello timeout remains active after TCP/WebSocket open',async()=>{
 const h=setup();h.c.connect();const ws=h.all[0];ws.open();
 const handshake=h.timers.find(t=>t.ms===12000);assert.ok(!handshake.off);handshake.f();
 assert.equal(ws.readyState,3);assert.equal(h.c.disabled,false);assert.ok(h.timers.some(x=>x.ms===1500));
});
test('successful hello cancels handshake deadline and resets reconnect attempts',async()=>{
 const h=setup();h.c.reconnectAttempts=3;h.c.connect();h.all[0].open();
 await h.c.receive({type:'hello',received:0});assert.equal(h.c.ready,true);assert.equal(h.c.reconnectAttempts,0);
 assert.equal(h.timers.find(t=>t.ms===12000).off,true);
});
test('late close from an old socket cannot clear a replacement connection',async()=>{
 const h=setup();h.c.connect();const old=h.all[0];old.open();old.close(1006);
 h.c.connect();const newer=h.all[1];newer.open();await h.c.receive({type:'hello',received:0});
 old.onclose({code:1006});assert.equal(h.c.socket,newer);assert.equal(h.c.ready,true);
});
test('retryable busy session does not permanently disable replay',async()=>{
 const h=setup();h.c.connect();h.all[0].open();await h.c.receive({type:'error',fatal:false,retryable:true,code:'SESSION_BUSY',message:'fixture busy'});
 assert.equal(h.c.disabled,false);assert.equal(h.c.meta.acked,0);assert.ok(h.timers.some(t=>t.ms===1500));
});
test('no server heartbeat closes transport without deleting outbox',async()=>{
 const h=setup();h.c.connect();h.all[0].open();await h.c.receive({type:'hello',received:0});h.advance(46000);
 h.intervals.find(t=>t.ms===15000).f();assert.equal(h.all[0].readyState,3);assert.equal(h.c.meta.acked,0);
 assert.ok(h.events.some(e=>e.d?.transport?.cause==='HEARTBEAT_TIMEOUT'));
});
test('backoff is bounded and fatal protocol errors still stop transmission',async()=>{
 const h=setup();assert.equal(h.c.reconnectDelay(),1500);for(let n=0;n<12;n++)h.c.reconnectDelay();assert.equal(h.c.reconnectDelay(),30000);
 h.c.connect();h.all[0].open();await h.c.receive({type:'error',fatal:true,message:'bad sequence'});assert.equal(h.c.disabled,true);
});
test('health probe distinguishes reachable service and never includes audio',async()=>{
 const h=setup();h.env.fetch=async()=>({ok:true,json:async()=>({service:'vkn-asr',version:'0.8.0',boot_id:'fixture',runtime:{workers:{asr:{phase:'waiting'}}},cache:'secretpath'})});
 await h.c.diagnoseDisconnect({code:1006,time:100000});assert.equal(h.c.meta.transportDiagnostic.service,'reachable');
 assert.equal(JSON.stringify(h.c.meta.transportDiagnostic).includes('secretpath'),false);
});
