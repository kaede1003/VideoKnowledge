'use strict';
const {test}=require('node:test'), assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),L=require('../extension/longform.js');
test('longform chunks preserve every cue id and respect input tokens including oversized records',()=>{
 const cues=Array.from({length:30},(_,i)=>({id:'seg-'+i,time:i*3,end:i*3+2,text:i===4?'长句'.repeat(2200):'常规词语'.repeat(15)}));
 const blocks=L.chunks(cues,c=>c.text,600);assert.ok(blocks.length>6);
 assert.ok(blocks.every(b=>b.tokens<=600), 'source token bounds enforced');
 assert.equal(L.coverage(cues.map(x=>x.id),blocks).covered,30);
});
test('longform checkpoint fingerprint changes when source language or translation status changes',()=>{
 const base={id:'cue-1',time:0,text:'Hola mundo',original:'Hola mundo',language:'es',translationStatus:'needs_review'};
 const fp=L.fingerprint([base],{mode:'transcript'},'model');
 assert.notEqual(fp,L.fingerprint([{...base,language:'zh'}],{mode:'transcript'},'model'));
 assert.notEqual(fp,L.fingerprint([{...base,translationStatus:'done'}],{mode:'transcript'},'model'));
});
test('continuation and fingerprint are source scoped, no duplicated overlap',()=>{
 assert.equal(L.joinContinuation('信息A——连续完整段落','完整段落和下一句'),'信息A——连续完整段落和下一句');
 const cues=[{id:'c1',time:0,text:'开头'}],o={mode:'knowledge'};
 assert.notEqual(L.fingerprint(cues,o,'model-a'),L.fingerprint([...cues,{id:'c2',time:1,text:'结尾'}],o,'model-a'));
 assert.notEqual(L.contentKey('video-A','f1'),L.contentKey('video-B','f1'));
});
function harness(generateReply){
 const storage=new Map(),session={key:'video-A',url:'https://example.com?v=video-A',segments:[]};let step=0,requests=[];
 const C={selectWritingCues:(c,w)=>({cues:c,options:{mode:w?.mode||'knowledge'},total:c.length,from:c[0].time,to:c[c.length-1].time}),
  transcriptLine:c=>`(${c.time}) ${c.text}`,readingTurns:cs=>cs,qualityCounts:()=>({review:0,manual:0}),
  writingPrompt:(w,meta,p)=>({system:'只用材料写正文',user:'正文材料：'+(p?.text||'')+(p?.phase||'')}),
  knowledgeSynthesisPrompt:(meta,material)=>({system:'FINAL_KNOWLEDGE_SYNTHESIS_DEDUP',user:String(material||'')}),
  cleanReaderOutput:t=>({body:t}),pageKey:()=>session.key};
 const context={globalThis:{},VideoKnowledgeCore:C,VknLongform:L,validKey:k=>k==='video-A',loadSession:async()=>session,
  chrome:{runtime:{id:'a'.repeat(32)},storage:{local:{get:async key=>Object.fromEntries((Array.isArray(key)?key:[key]).filter(k=>storage.has(k)).map(k=>[k,storage.get(k)])),set:async data=>{for(const [k,v] of Object.entries(data))storage.set(k,structuredClone(v));}}}},
  requireAiPermission:async()=>new URL('http://127.0.0.1:11434/v1/chat/completions'),throwIfCancelled:()=>{},
  fetch:async(url,opts)=>{requests.push(JSON.parse(opts.body));let item=responses.shift();if(item instanceof Error)throw item;if(item?.status)return {ok:false,status:item.status,headers:{get:()=>null}};
   if(item?.json)return {ok:true,headers:{get:()=> 'application/json'},json:async()=>item.json};
   const generated=generateReply?generateReply(requests.at(-1),requests.length):'完成的内容';
   const value=typeof generated==='string'?{text:generated,finishReason:'stop'}:generated;
   const frames=item||[{choices:[{delta:{content:value.text},finish_reason:value.finishReason||'stop'}]}];
   const body=item?.rawSse!==undefined?item.rawSse:frames.map(x=>'data: '+JSON.stringify(x)+'\n\n').join('')+'data: [DONE]\n\n';
   return {ok:true,headers:{get:()=> 'text/event-stream'},body:{getReader:()=>{let given=false;return {read:async()=>given?{done:true}:((given=true),{done:false,value:new TextEncoder().encode(body)})};}}};},
  VknAiHttp:{describe:(r)=>'AI_HTTP_'+r.status+'：长文被拒绝'},chromeRuntime:{id:'a'.repeat(32)},
  AbortController,TextDecoder,TextEncoder,URL,setTimeout,clearTimeout,Date,console,Error};
 let responses=[];vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'extension/longform-background.js'),'utf8'),context);
 return {context,storage,session,requests,send:xs=>{responses.push(...xs);}};
}
test('longform hierarchy saves checkpoints and only marks complete after verified chapters',async()=>{
 const h=harness(),cs=Array.from({length:7},(_,i)=>({id:'c'+i,time:i*10,end:i*10+2,text:'不同部分要完整保留：'.repeat(22)}));
 const result=await h.context.vknRunLongform(cs,{sessionKey:'video-A',title:'标题'},{writing:{mode:'knowledge'}},{model:'qwen2.5:3b'});
 assert.ok(result.markdown.includes('完成的内容'));assert.equal(result.coverage.covered,7);
 const finished=[...h.storage.values()].find(v=>v?.completed===true);assert.ok(finished);assert.equal(finished.sharded,true);assert.ok([...h.storage.keys()].some(k=>k.includes(':item:')&&k.includes(':chapters:chapter-')));assert.equal(L.VERSION,3);
 assert.ok(h.requests.length>2);assert.ok(h.requests.some(x=>JSON.stringify(x).includes('FINAL_KNOWLEDGE_SYNTHESIS_DEDUP')));
});
test('truncated responses are never published: smallest source falls back safely after restart',async()=>{
 const h=harness(()=>({text:'UNTRUSTED_INCOMPLETE_DRAFT',finishReason:'length'})),cs=[{id:'c1',time:0,text:'一些长内容（完整来源必须保留）。'.repeat(24)}];
 const clipped={choices:[{delta:{content:'UNTRUSTED_INCOMPLETE_DRAFT'},finish_reason:'length'}]};
 h.send([[clipped]]);
 await assert.rejects(h.context.vknRunLongform(cs,{sessionKey:'video-A'},{writing:{mode:'knowledge'},stepBudget:1},{model:'qwen2.5:3b'}),/AI_CONTINUE_REQUIRED/);
 const partial=[...h.storage.entries()].find(([k])=>k.includes(':continuations:evidence-0'))?.[1];
 assert.equal(partial.split,true);assert.equal(partial.done,false);
 const result=await h.context.vknRunLongform(cs,{sessionKey:'video-A'},{writing:{mode:'knowledge'}},{model:'qwen2.5:3b'});
 const evidence=[...h.storage.entries()].find(([k])=>k.includes(':units:evidence-0'))?.[1];
 assert.match(evidence.text,/一些长内容/);assert.doesNotMatch(result.markdown,/UNTRUSTED_INCOMPLETE_DRAFT/);
 const expected=L.chunks(cs,c=>`(${c.time}) ${c.text}`,900)[0].text;
 assert.equal(evidence.text,expected,'all fallback branches reconstruct exact source without removing spaces or numbers');
 assert.equal(result.coverage.covered,1);
 assert.match(result.audit.notes.join(' '),/保底/);
});

test('persistent length cutoffs for a two-hour source end with bounded split/fallback rather than 32 continuations',async()=>{
 // Approximately two hours of video timestamps; this is a synthetic model
 // that NEVER signals completion, not a claim about real summarization quality.
 const h=harness(()=>({text:'TRUNCATED_ONLY_UNSAFE',finishReason:'length'}));
 const cs=Array.from({length:30},(_,i)=>({id:'clip-'+i,time:i*240,end:i*240+9,text:'独立来源'+i+'：不可删掉的具体例证和不同观点。'.repeat(14)}));
 const opts={writing:{mode:'knowledge'},stepBudget:1},cfg={model:'always-length'};
 let result,steps=0;
 while(!result&&steps<600){
  try{result=await h.context.vknRunLongform(cs,{sessionKey:'video-A'},opts,cfg);}
  catch(e){assert.match(String(e.message),/AI_CONTINUE_REQUIRED/);}
  steps++;
 }
 assert.ok(result,'clipped model must not cause endless retries');
 assert.equal(result.coverage.total,30);assert.equal(result.coverage.covered,30);
 assert.match(result.markdown,/不可删掉的具体例证/);
 assert.doesNotMatch(result.markdown,/TRUNCATED_ONLY_UNSAFE/);
 assert.match(result.audit.notes.join(' '),/模型持续输出截断/);
 assert.ok(h.requests.length<600,'model calls are bounded by source-splitting stages');
 const completed=[...h.storage.values()].find(v=>v?.completed===true);
 assert.equal(completed.phase,'done');
 assert.ok((completed.fallbackTags||[]).length>0);
});

test('a clipped oversized source splits and merges completed smaller model answers',async()=>{
 const h=harness(req=>{
  const input=req.messages[1].content;
  if(input.includes('evidence')&&input.length>450)return {text:'CLIPPED_NOT_FINAL',finishReason:'length'};
  return {text:'## 小主题\n完整的局部论据',finishReason:'stop'};
 });
 const cs=[{id:'c1',time:0,end:8,text:'支持证据、独立细节与例外条件。'.repeat(36)}];
 const r=await h.context.vknRunLongform(cs,{sessionKey:'video-A'},{writing:{mode:'knowledge'}},{model:'adaptive'});
 assert.equal(r.coverage.covered,1);
 const evidence=[...h.storage.entries()].find(([k])=>k.includes(':units:evidence-0'))?.[1];
 assert.ok(evidence.text.includes('完整的局部论据'));assert.doesNotMatch(evidence.text,/CLIPPED_NOT_FINAL/);
 assert.ok(h.requests.length>=3,'one oversized input must be retried as smaller independent inputs');
 const root=[...h.storage.entries()].find(([k])=>k.endsWith(':continuations:evidence-0'))?.[1];
 assert.equal(root.done,true);assert.equal(root.degraded,false);
});

test('HTTP 413 adaptively splits source, while HTTP 403 remains an authorization error',async()=>{
 const h=harness(),cs=[{id:'c1',time:0,end:8,text:'不同来源的具体事实。'.repeat(50)}];
 h.send([{status:413}]);
 const r=await h.context.vknRunLongform(cs,{sessionKey:'video-A'},{writing:{mode:'knowledge'}},{model:'synthetic'});
 assert.equal(r.coverage.covered,1);
 assert.ok(h.requests.length>1,'size-rejected input should be subdivided without changing the provider');
});

test('r21 attempt-32 unfinished shard is archived and automatically rebuilt from source',async()=>{
 const h=harness(),cs=[{id:'c1',time:0,end:4,text:'可恢复的原始主题'}],cfg={model:'synthetic'};
 const fp=L.fingerprint(cs,{mode:'knowledge'},cfg.model,'knowledge'),key=L.contentKey('video-A',fp);
 const prior=L.state('video-A',fp,'knowledge',cfg.model,1);prior.runKey='r21';prior.sharded=true;
 h.storage.set(key,structuredClone(prior));
 const shard=key+':item:'+L.hash('r21')+':continuations:evidence-0';
 h.storage.set(shard,{text:'旧版本截断的文字',attempt:32,done:false});
 const result=await h.context.vknRunLongform(cs,{sessionKey:'video-A'},{writing:{mode:'knowledge'}},cfg);
 assert.equal(result.coverage.covered,1);
 assert.equal(h.storage.get(shard+':r21-incomplete').attempt,32);
 assert.equal(h.storage.get(shard).done,true);
 assert.equal(h.storage.get(shard).strategy,'adaptive-source-v1');
});

test('adaptive splitter preserves exact text including source punctuation and emoji',()=>{
 const text='来源证据：'+('甲，乙。🙂下一句！'.repeat(150));
 const halves=L.splitForRetry(text,190);
 assert.equal(halves.join(''),text);
 assert.ok(halves.every(part=>part&&![...part].includes('\uFFFD')));
 assert.equal(L.splitForRetry('极短的证据',190),null);
});

test('two-hour knowledge source runs in bounded resumable steps, sharded checkpoints, and retains source coverage',async()=>{
 // 180 synthetic records, one every 40 seconds, represent two hours of speech.
 // This tests orchestration and durability, NOT a real model's summary quality.
 const h=harness(req=>{
  const system=req.messages[0].content;
  if(system.includes('FINAL_KNOWLEDGE_SYNTHESIS_DEDUP'))return '## 核心主题\n'+'补充背景与独立论据。'.repeat(66);
  if(req.messages[1].content.includes('evidence'))return '原始证据、例子和不同意见。'.repeat(42);
  return '## 当前论点\n'+'上下文、论据与例外条件。'.repeat(66);
 });
 const cs=Array.from({length:180},(_,i)=>({id:'synthetic-'+i,time:i*40,end:i*40+8,text:'本次观点的事实依据、反例以及争议。'.repeat(15)+i}));
 const cfg={model:'synthetic-llm'},meta={sessionKey:'video-A',title:'两小时测试'},options={writing:{mode:'knowledge'},stepBudget:1};
 let result=null,steps=0,partial=0;
 while(!result&&steps<800){
  try{result=await h.context.vknRunLongform(cs,meta,options,cfg);}
  catch(e){assert.match(String(e.message),/AI_CONTINUE_REQUIRED/);partial++;}
  steps++;
 }
 assert.ok(result,'longform should converge from saved checkpoints');
 assert.ok(partial>15,'must run as many bounded worker messages rather than one unbounded task');
 assert.equal(result.coverage.total,180);assert.equal(result.coverage.covered,180);
 assert.ok(result.markdown.includes('核心主题')||result.markdown.includes('当前论点'));
 const metaValues=[...h.storage.values()].filter(v=>v?.schema===3&&v?.sharded);
 assert.ok(metaValues.some(v=>v.completed));
 assert.ok(metaValues.every(v=>JSON.stringify(v).length<4000),'the metadata key must never expand with all chapter text');
 assert.ok([...h.storage.keys()].some(k=>k.includes('consolidations:synthesis2-')),'thematic merging executed');
});

test('legacy r19 monolithic checkpoint is migrated safely and its evidence is reused',async()=>{
 const h=harness(),cs=[{id:'c1',time:0,end:5,text:'旧取材内容'}],cfg={model:'synthetic-llm'};
 const fp=L.fingerprint(cs,{mode:'knowledge'},cfg.model,'knowledge'),key=L.contentKey('video-A',fp);
 const prior=L.state('video-A',fp,'knowledge',cfg.model,1);
 prior.units['evidence-0']={text:'上一轮保留的取材证据',ids:['c1'],start:0,end:5};
 h.storage.set(key,structuredClone(prior));
 const r=await h.context.vknRunLongform(cs,{sessionKey:'video-A'},{writing:{mode:'knowledge'}},cfg);
 assert.equal(r.coverage.covered,1);
 assert.equal(h.storage.get(key).sharded,true);
 assert.ok(!h.storage.get(key).units,'metadata should no longer contain the old large unit map');
 assert.ok([...h.storage.values()].some(v=>v?.text==='上一轮保留的取材证据'));
 assert.ok(!h.requests.some(req=>req.messages[1].content.includes('evidence')),'do not repeat already durable evidence');
});

test('pair reduction never drops a source and safeguards a one-item-per-group deadlock',()=>{
 const items=Array.from({length:17},(_,i)=>({text:'主题内容'.repeat(750),ids:['source-'+i]}));
 const grouped=L.reductionGroups(items,1000);
 assert.equal(grouped.length,9);
 assert.deepEqual(grouped.flatMap(group=>group.flatMap(x=>x.ids)),items.flatMap(x=>x.ids));
});

test('a rejected longform POST keeps partial checkpoints but does not publish a completed document',async()=>{
 const h=harness(),cs=[{id:'c1',time:0,end:5,text:'来自原视频的完整句子'}];
 h.send([{status:403}]);
 await assert.rejects(h.context.vknRunLongform(cs,{sessionKey:'video-A'},{writing:{mode:'knowledge'}},{model:'qwen2.5:3b'}),/AI_HTTP_403/);
 const metadata=[...h.storage.values()].find(v=>v?.schema===3&&v?.sharded);
 assert.ok(metadata);assert.equal(metadata.completed,false);assert.equal(metadata.phase,'paused');
 assert.match(metadata.error,/AI_HTTP_403/);
 assert.ok(![...h.storage.values()].some(v=>v?.completed===true),'403 must not be converted into success');
 // A later click is allowed to resume from the same provenance-scoped checkpoint.
 const done=await h.context.vknRunLongform(cs,{sessionKey:'video-A'},{writing:{mode:'knowledge'}},{model:'qwen2.5:3b'});
 assert.equal(done.coverage.covered,1);
});

test('resumed long-form batches emit progress only for actual model calls, never replay cached stages',async()=>{
 const h=harness();const cues=Array.from({length:8},(_,i)=>({id:'b'+i,time:i*50,end:i*50+10,text:'这是一段包含不同案例的完整原始访谈。'.repeat(12)}));
 const progress=[],opts={writing:{mode:'knowledge'},stepBudget:1,phaseProgress:(...parts)=>progress.push(parts)};
 try{await h.context.vknRunLongform(cues,{sessionKey:'video-A'},opts,{model:'test-progress'});}catch(e){assert.match(e.message,/AI_CONTINUE_REQUIRED/);}
 assert.deepEqual(progress.map(x=>[x[0],x[1]]),[['取材和证据索引',1]],'first request must announce only its real in-flight work');
 progress.length=0;
 try{await h.context.vknRunLongform(cues,{sessionKey:'video-A'},opts,{model:'test-progress'});}catch(e){assert.match(e.message,/AI_CONTINUE_REQUIRED/);}
 assert.deepEqual(progress.map(x=>[x[0],x[1]]),[['取材和证据索引',2]],'checkpoint reread must not replay index=1 or announce unstarted index=3');
});


test('r27: unfinished SSE plus failed non-stream recovery keeps checkpoint paused; identical job safely resumes',async()=>{
 const h=harness(),cs=[{id:'c1',time:0,end:5,text:'全量可恢复的原始证据和相关观点。'}],opts={writing:{mode:'knowledge'}},cfg={model:'qwen2.5:3b'};
 h.send([{rawSse:'data: '+JSON.stringify({choices:[{delta:{content:'HALF_DRAFT_NOT_FINAL'}}]})+'\n\n'},{status:500}]);
 await assert.rejects(h.context.vknRunLongform(cs,{sessionKey:'video-A'},opts,cfg),/AI_HTTP_500/);
 const metadata=[...h.storage.values()].find(v=>v?.schema===3&&v?.sharded);
 assert.ok(metadata);assert.equal(metadata.completed,false);assert.equal(metadata.phase,'paused');
 assert.ok(![...h.storage.values()].some(x=>x?.completed===true));
 assert.ok(![...h.storage.values()].some(x=>x?.text==='HALF_DRAFT_NOT_FINAL'));
 // User reopens the same source/model/range: previous completed shards survive,
 // and only the unfinished stage is requested again.
 const completed=await h.context.vknRunLongform(cs,{sessionKey:'video-A'},opts,cfg);
 assert.equal(completed.coverage.covered,1);
 assert.doesNotMatch(completed.markdown,/HALF_DRAFT_NOT_FINAL/);
});

test('r27: longform checkpoint uses only recovered non-stream text, not the interrupted draft',async()=>{
 const h=harness(),cs=[{id:'c1',time:0,end:5,text:'完整来源必须覆盖。'}],opts={writing:{mode:'knowledge'}},cfg={model:'qwen2.5:3b'};
 h.send([{rawSse:'data: '+JSON.stringify({choices:[{delta:{content:'PARTIAL_DRAFT'}}]})+'\n\n'},
         {json:{choices:[{message:{content:'完整证据已恢复'},finish_reason:'stop'}]}}]);
 const completed=await h.context.vknRunLongform(cs,{sessionKey:'video-A'},opts,cfg);
 assert.equal(completed.coverage.covered,1);
 assert.doesNotMatch(completed.markdown,/PARTIAL_DRAFT/);
 assert.ok([...h.storage.values()].some(x=>x?.text==='完整证据已恢复'));
 assert.equal(h.requests[0].stream,true);assert.equal(h.requests[1].stream,false);
});
