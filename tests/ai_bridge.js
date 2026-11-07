/* Test-only IPC bridge: production background code, mocked Chrome APIs/model. */
'use strict';
const {makeHarness}=require('./ai_harness.js');
const readline=require('node:readline');
let h=makeHarness();
(async()=>{
 for await(const line of readline.createInterface({input:process.stdin,crlfDelay:Infinity})){
  try{
   const q=JSON.parse(line);let data;
   if(q.op==='reset'){h=makeHarness({store:q.store||{},models:q.models,permission:q.permission});data=true;}
   else if(q.op==='get')data=await h.storage.get(q.key);
   else if(q.op==='set'){await h.storage.set(q.values);data=true;}
   else if(q.op==='send')data=await h.send(q.message);
   else if(q.op==='requests')data=h.requests.map(r=>({url:r.url,method:r.opts.method||'GET',body:r.opts.body?JSON.parse(r.opts.body):null}));
   else throw Error('unknown test operation');
   process.stdout.write(JSON.stringify({ok:true,data})+'\n');
  }catch(e){process.stdout.write(JSON.stringify({ok:false,error:e.message})+'\n');}
 }
})();
