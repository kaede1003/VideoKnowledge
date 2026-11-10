'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const C=require('../extension/ai-config.js');
const {makeHarness}=require('./ai_harness.js');
const cues=[{time:1,text:'第一点：需要记录事实。'},{time:8,text:'第二点：保留来源。'},{time:13,text:'第三点：核对结论。'}];
const generate={type:'VKN_AI_GENERATE',cues,meta:{title:'配置回归'}};
const local=C.DEFAULT_ENDPOINT;
test('unsaved default resolves locally, without enabling automatic AI or claiming saved',()=>{
 const r=C.resolve({});assert.equal(r.endpoint,local);assert.equal(r.model,'qwen2.5:3b');assert.equal(r.saved,false);assert.equal(r.autoSummary,false);
});
test('speech-only saved model is used for unconfigured deep summaries',()=>{
 assert.equal(C.resolve({vknSpeechConfig:{textModel:'qwen2.5:7b'}}).model,'qwen2.5:7b');
});
test('legacy explicit offline is preserved; no implicit local model is enabled',()=>{
 for(const vknAiConfig of [{endpoint:'',model:''},{provider:'offline'},{enabled:false}])assert.equal(C.resolve({vknAiConfig}).enabled,false);
});
test('custom provider, credentials and manual model choice are never replaced by speech settings',()=>{
 const raw={endpoint:'https://example.test/v1/chat/completions',model:'user-model',apiKey:'private-test-value'};
 const r=C.resolve({vknAiConfig:raw,vknSpeechConfig:{textModel:'qwen2.5:7b'}});
 assert.equal(r.endpoint,raw.endpoint);assert.equal(r.model,'user-model');assert.equal(r.apiKey,raw.apiKey);
});
test('incomplete custom provider is an error, not an implicit fallback',()=>{
 for(const raw of [{model:'user-model'},{endpoint:'https://example.test/api'},{provider:'custom',endpoint:local}])
  assert.throws(()=>C.resolve({vknAiConfig:raw}),/AI_CONFIG_INCOMPLETE/);
});
test('localhost and native Ollama paths are normalized to a compatible loopback chat endpoint',()=>{
 for(const endpoint of ['http://localhost:11434','http://localhost:11434/v1','http://localhost:11434/api/chat'])
  assert.equal(C.resolve({vknAiConfig:{endpoint,model:'qwen2.5:3b'}}).endpoint,local);
});
test('known local endpoint with omitted model uses the local speech setting',()=>{
 const r=C.resolve({vknAiConfig:{endpoint:'http://localhost:11434/v1/chat/completions'},vknSpeechConfig:{textModel:'qwen2.5:7b'}});
 assert.equal(r.model,'qwen2.5:7b');assert.equal(r.source,'saved-local-completed');
});
test('nonlocal HTTP and URL credentials are rejected',()=>{
 for(const endpoint of ['http://example.test/chat','https://user:pass@example.test/chat','file:///etc/passwd'])
  assert.throws(()=>C.resolve({vknAiConfig:{endpoint,model:'x'}}),/AI_CONFIG_URL/);
});
test('an explicit local provider cannot point to the cloud; local cloud-tag models are denied',()=>{
 assert.throws(()=>C.resolve({vknAiConfig:{provider:'ollama',endpoint:'https://example.test/chat',model:'x'}}),/AI_CONFIG_PROVIDER/);
 assert.throws(()=>C.resolve({vknSpeechConfig:{textModel:'some-model:cloud'}}),/AI_CONFIG_MODEL/);
});
test('public status contains neither credentials nor secret-bearing URL query strings',()=>{
 const r=C.publicStatus({vknAiConfig:{endpoint:'https://example.test/chat?token=hidden-query',model:'user',apiKey:'hidden-key'}});
 assert.ok(r.configured);assert.doesNotMatch(JSON.stringify(r),/hidden-query|hidden-key/);
});
test('invalid persisted configuration is not silently discarded',()=>{
 assert.equal(C.publicStatus({vknAiConfig:'invalid'}).configured,false);
 assert.throws(()=>C.resolve({vknAiConfig:'invalid'}),/AI_CONFIG_FORMAT/);
});
test('default deep-summary background message now reaches the model and returns a document',async()=>{
 const h=makeHarness();const r=await h.send(generate);assert.equal(r.ok,true,r.error);assert.match(r.data.markdown,/知识文档/);
 assert.equal(h.requests.length,2);assert.equal(JSON.parse(h.requests[1].opts.body).model,'qwen2.5:3b');
});
test('speech-only configuration drives an entire deep summary (the original failing path)',async()=>{
 const h=makeHarness({store:{vknSpeechConfig:{textModel:'qwen2.5:7b'}}});const r=await h.send(generate);
 assert.equal(r.ok,true,r.error);assert.equal(JSON.parse(h.requests[1].opts.body).model,'qwen2.5:7b');
});
test('explicit offline rejects deep generation before any network request',async()=>{
 const h=makeHarness({store:{vknAiConfig:{endpoint:'',model:''}}});const r=await h.send(generate);
 assert.equal(r.ok,false);assert.match(r.error,/AI_DISABLED/);assert.equal(h.requests.length,0);
});
test('current settings are re-read on every invocation; no stale model cache',async()=>{
 const h=makeHarness();await h.send(generate);
 await h.storage.set({vknAiConfig:C.stored(C.resolve({vknSpeechConfig:{textModel:'qwen2.5:7b'}}))});
 const r=await h.send(generate);assert.ok(r.ok);assert.equal(JSON.parse(h.requests.at(-1).opts.body).model,'qwen2.5:7b');
});
test('status does not probe models or send transcripts; returns resolved defaults',async()=>{
 const h=makeHarness();const r=await h.send({type:'VKN_AI_STATUS'});assert.ok(r.ok);assert.ok(r.data.configured);assert.equal(r.data.saved,false);assert.equal(h.requests.length,0);
});
test('permission denial is distinguished and no request is sent',async()=>{
 const h=makeHarness({permission:false});const r=await h.send(generate);assert.match(r.error,/AI_PERMISSION/);assert.equal(h.requests.length,0);
});
test('model missing is distinguished from empty settings; no inference request',async()=>{
 const h=makeHarness({models:['another-model']});const r=await h.send(generate);assert.match(r.error,/AI_MODEL_MISSING/);assert.equal(h.requests.length,1);
});
test('Ollama not running is distinguished from missing config and ASR 8765',async()=>{
 const h=makeHarness({fetch:async()=>{throw new TypeError('fetch failed');}});const r=await h.send(generate);assert.match(r.error,/AI_LOCAL_CONNECT/);assert.match(r.error,/8765/);
});
test('test endpoint executes inference, not just model-list discovery',async()=>{
 const h=makeHarness();const r=await h.send({type:'VKN_AI_TEST'});assert.ok(r.ok);assert.equal(r.data.verified,true);
 const post=JSON.parse(h.requests[1].opts.body);assert.equal(post.max_tokens,32);assert.equal(post.messages[1].content,'只回复：连接正常。');
 assert.equal(r.data.longformVerified,true);
 const streamed=JSON.parse(h.requests[2].opts.body);assert.equal(streamed.stream,true);assert.equal(streamed.max_tokens,48);
 assert.equal(streamed.messages[1].content,'只回复：长文接口正常。');
});
test('empty model output is not reported as verification success',async()=>{
 const h=makeHarness({fetch:async(url)=>new Response(JSON.stringify(url.endsWith('/api/tags')?{models:[{name:'qwen2.5:3b'}]}:{choices:[]}))});
 const r=await h.send({type:'VKN_AI_TEST'});assert.equal(r.ok,false);assert.match(r.error,/AI_EMPTY_REPLY/);
});
test('custom service HTTP rejection does not echo an API key or raw response',async()=>{
 const h=makeHarness({store:{vknAiConfig:{endpoint:'https://example.test/chat',model:'test',apiKey:'do-not-log'}},fetch:async()=>new Response('do-not-log',{status:401})});
 const r=await h.send(generate);assert.match(r.error,/AI_HTTP_401/);assert.doesNotMatch(r.error,/do-not-log/);
});
test('incremental summaries use exactly the same resolved local configuration',async()=>{
 const h=makeHarness({store:{vknSpeechConfig:{textModel:'qwen2.5:7b'}}});const r=await h.send({...generate,type:'VKN_AI_PERIODIC_SUMMARY'});
 assert.ok(r.ok,r.error);assert.equal(JSON.parse(h.requests[1].opts.body).model,'qwen2.5:7b');
});
test('storage read error is not mistaken for empty settings',async()=>{
 const h=makeHarness({storageError:true});const r=await h.send(generate);assert.match(r.error,/AI_STORAGE_READ/);assert.equal(h.requests.length,0);
});

test('real loopback HTTP round-trip: resolved config -> tags -> chat -> knowledge markdown',async()=>{
 const http=require('node:http');const received=[];
 const server=http.createServer(async(req,res)=>{
   let raw='';for await(const chunk of req)raw+=chunk;
   received.push({method:req.method,url:req.url,body:raw?JSON.parse(raw):null});
   res.setHeader('content-type','application/json');
   res.end(JSON.stringify(req.url==='/api/tags'?{models:[{name:'qwen2.5:3b'}]}:
     {choices:[{message:{content:'## HTTP闭环测试\n[00:01] 保留证据。'}}]}));
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 try{
   const port=server.address().port;
   const h=makeHarness({fetch:(url,opts)=>fetch(url.replace('127.0.0.1:11434',`127.0.0.1:${port}`),opts)});
   const r=await h.send(generate);assert.equal(r.ok,true,r.error);assert.match(r.data.markdown,/HTTP闭环/);
   assert.equal(received[0].url,'/api/tags');assert.equal(received[1].url,'/v1/chat/completions');
   assert.equal(received[1].body.model,'qwen2.5:3b');assert.match(received[1].body.messages[1].content,/第一点/);
 }finally{await new Promise(resolve=>server.close(resolve));}
});

test('malformed response JSON is a service-response error, never configuration missing',async()=>{
 const h=makeHarness({fetch:async(url)=>url.endsWith('/api/tags')?
   new Response(JSON.stringify({models:[{name:'qwen2.5:3b'}]})):new Response('<html>not JSON</html>')});
 const r=await h.send(generate);assert.match(r.error,/AI_RESPONSE_FORMAT/);
});
