'use strict';
const {test}=require('node:test'), assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),L=require('../extension/longform.js');
test('longform chunks preserve every cue id and respect input tokens including oversized records',()=>{
 const cues=Array.from({length:30},(_,i)=>({id:'seg-'+i,time:i*3,end:i*3+2,text:i===4?'长句'.repeat(2200):'常规词语'.repeat(15)}));
 const blocks=L.chunks(cues,c=>c.text,600);assert.ok(blocks.length>6);
 assert.ok(blocks.every(b=>b.tokens<=600), 'source token bounds enforced');
 assert.equal(L.coverage(cues.map(x=>x.id),blocks).covered,30);
});
test('continuation and fingerprint are source scoped, no duplicated overlap',()=>{
 assert.equal(L.joinContinuation('信息A——连续完整段落','完整段落和下一句'),'信息A——连续完整段落和下一句');
 const cues=[{id:'c1',time:0,text:'开头'}],o={mode:'knowledge'};
 assert.notEqual(L.fingerprint(cues,o,'model-a'),L.fingerprint([...cues,{id:'c2',time:1,text:'结尾'}],o,'model-a'));
 assert.notEqual(L.contentKey('video-A','f1'),L.contentKey('video-B','f1'));
});
function harness(){
 const storage=new Map(),session={key:'video-A',url:'https://example.com?v=video-A',segments:[]};let step=0,requests=[];
 const C={selectWritingCues:(c,w)=>({cues:c,options:{mode:w?.mode||'knowledge'},total:c.length,from:c[0].time,to:c[c.length-1].time}),
  transcriptLine:c=>`(${c.time}) ${c.text}`,readingTurns:cs=>cs,qualityCounts:()=>({review:0,manual:0}),
  writingPrompt:(w,meta,p)=>({system:'只用材料写正文',user:'正文材料：'+(p?.text||'')+(p?.phase||'')}),
  cleanReaderOutput:t=>({body:t}),pageKey:()=>session.key};
 const context={globalThis:{},VideoKnowledgeCore:C,VknLongform:L,validKey:k=>k==='video-A',loadSession:async()=>session,
  chrome:{storage:{local:{get:async key=>({[key]:storage.get(key)}),set:async data=>{for(const [k,v] of Object.entries(data))storage.set(k,structuredClone(v));}}}},
  requireAiPermission:async()=>new URL('http://127.0.0.1:11434/v1/chat/completions'),throwIfCancelled:()=>{},
  fetch:async(url,opts)=>{requests.push(JSON.parse(opts.body));let item=responses.shift();if(item instanceof Error)throw item;const frames=item||[{choices:[{delta:{content:'完成的内容'},finish_reason:'stop'}]}];
   const body=frames.map(x=>'data: '+JSON.stringify(x)+'\n\n').join('')+'data: [DONE]\n\n';
   return {ok:true,headers:{get:()=> 'text/event-stream'},body:{getReader:()=>{let given=false;return {read:async()=>given?{done:true}:((given=true),{done:false,value:new TextEncoder().encode(body)})};}}};},
  AbortController,TextDecoder,TextEncoder,URL,setTimeout,clearTimeout,Date,console,Error};
 let responses=[];vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'extension/longform-background.js'),'utf8'),context);
 return {context,storage,session,requests,send:xs=>{responses.push(...xs);}};
}
test('longform hierarchy saves checkpoints and only marks complete after verified chapters',async()=>{
 const h=harness(),cs=Array.from({length:7},(_,i)=>({id:'c'+i,time:i*10,end:i*10+2,text:'不同部分要完整保留：'.repeat(22)}));
 const result=await h.context.vknRunLongform(cs,{sessionKey:'video-A',title:'标题'},{writing:{mode:'knowledge'}},{model:'qwen2.5:3b'});
 assert.ok(result.markdown.includes('完成的内容'));assert.equal(result.coverage.covered,7);
 assert.ok([...h.storage.values()].some(v=>v?.completed===true));
 assert.ok(h.requests.length>2);
});
test('length cutoffs never mark full document and resume from partial saved chapter',async()=>{
 const h=harness(),cs=[{id:'c1',time:0,text:'一些长内容'}];
 const clipped={choices:[{delta:{content:'开头一段'},finish_reason:'length'}]},full={choices:[{delta:{content:'下一段完结'},finish_reason:'stop'}]};
 h.send(Array.from({length:7},()=>[clipped]));
 await assert.rejects(h.context.vknRunLongform(cs,{sessionKey:'video-A'},{writing:{mode:'knowledge'}},{model:'qwen2.5:3b'}),/AI_OUTPUT_TRUNCATED/);
 assert.ok([...h.storage.values()].some(v=>v?.completed===false&&Object.values(v?.continuations||{}).some(c=>c.text?.includes('开头一段'))));
 h.send([[full]]);
 const r=await h.context.vknRunLongform(cs,{sessionKey:'video-A'},{writing:{mode:'knowledge'}},{model:'qwen2.5:3b'});
 const finished=[...h.storage.values()].find(v=>v?.completed===true);
 assert.ok(finished.units['evidence-0'].text.includes('开头一段'));assert.ok(finished.units['evidence-0'].text.includes('下一段完结'));
 assert.equal(r.coverage.covered,1);
});
