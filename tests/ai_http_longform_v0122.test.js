'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {makeHarness}=require('./ai_harness.js');
const LOCAL='http://127.0.0.1:11434/v1/chat/completions';
const TAGS={models:[{name:'qwen2.5:3b'}]};
const success=()=>new Response(JSON.stringify({choices:[{message:{content:'连接正常'}}]}),
  {headers:{'content-type':'application/json'}});
function choose(url,opts,response){
 if(url.endsWith('/api/tags'))return new Response(JSON.stringify(TAGS));
 const body=JSON.parse(opts.body);
 return body.stream?response:success();
}
test('AI_TEST performs both the normal chat and real stream:true longform POST with the same endpoint',async()=>{
 const h=makeHarness({fetch:async(url,opts)=>choose(url,opts,success())});
 const r=await h.send({type:'VKN_AI_TEST'});
 assert.equal(r.ok,true,r.error);assert.equal(r.data.verified,true);assert.equal(r.data.longformVerified,true);
 assert.equal(r.data.longformTransport,'json');
 assert.deepEqual(h.requests.map(x=>x.url),[LOCAL.replace('/v1/chat/completions','/api/tags'),LOCAL,LOCAL]);
 const bodies=h.requests.slice(1).map(x=>JSON.parse(x.opts.body));
 assert.equal(bodies[0].stream,false);assert.equal(bodies[1].stream,true);
 assert.equal(bodies[1].max_tokens,48);
 assert.equal(bodies[0].model,bodies[1].model);
});
test('local Ollama POST 403 after a successful short chat is never marked verified; no key or prompt leakage',async()=>{
 const h=makeHarness({store:{vknAiConfig:{provider:'ollama',endpoint:LOCAL,model:'qwen2.5:3b',apiKey:'SHOULD_NOT_LEAK'}},
   fetch:async(url,opts)=>choose(url,opts,new Response('sensitive private upstream body',{status:403}))});
 const r=await h.send({type:'VKN_AI_TEST'});
 assert.equal(r.ok,false);
 assert.match(r.error,/AI_LOCAL_ORIGIN_403/);assert.match(r.error,/长文整理流式 POST/);
 assert.match(r.error,/OLLAMA_ORIGINS/);assert.doesNotMatch(r.error,/SHOULD_NOT_LEAK|sensitive private upstream body|买.*API Key/);
 assert.equal(h.requests.length,3);
 for(const request of h.requests)assert.equal(request.opts.headers?.authorization,undefined);
});
test('custom provider HTTP 403 at stream:true reports service refusal with no content, credentials, query or body',async()=>{
 const endpoint='https://example.test/v1/chat/completions?token=super-secret-query';
 const h=makeHarness({store:{vknAiConfig:{provider:'custom',endpoint,model:'custom-model',apiKey:'super-secret-key'}},
   fetch:async(url,opts)=>choose(url,opts,new Response('super-secret-upstream-body',{status:403,
     headers:{'x-request-id':'req-32ABCD908761'}}))});
 const r=await h.send({type:'VKN_AI_TEST'});
 assert.equal(r.ok,false);assert.match(r.error,/AI_HTTP_403/);assert.match(r.error,/自定义摘要服务/);
 assert.match(r.error,/req-32ABCD908761/);
 assert.doesNotMatch(r.error,/super-secret-key|super-secret-query|super-secret-upstream-body|OLLAMA_ORIGINS/);
 assert.equal(h.requests.length,2, 'custom service has no local tags request');
 assert.equal(h.requests[0].opts.headers.authorization,'Bearer super-secret-key');
 assert.equal(h.requests[1].opts.headers.authorization,'Bearer super-secret-key');
 assert.equal(JSON.parse(h.requests[1].opts.body).stream,true);
});
test('longform stream succeeds on event-stream and verifies parsed transport',async()=>{
 const event='data: '+JSON.stringify({choices:[{delta:{content:'长文请求正常'},finish_reason:'stop'}]})+'\n\n'+'data: [DONE]\n\n';
 const h=makeHarness({fetch:async(url,opts)=>choose(url,opts,
   new Response(event,{headers:{'content-type':'text/event-stream'}}))});
 const r=await h.send({type:'VKN_AI_TEST'});
 assert.equal(r.ok,true,r.error);assert.equal(r.data.longformTransport,'sse');
});
test('longform 413, 429 and 500 give actionable, status-specific diagnostics without retry storms',async()=>{
 for(const status of [413,429,500]){
   const h=makeHarness({fetch:async(url,opts)=>choose(url,opts,new Response('',{status}))});
   const r=await h.send({type:'VKN_AI_TEST'});
   assert.equal(r.ok,false);assert.match(r.error,new RegExp('AI_HTTP_'+status));
   assert.equal(h.requests.length,3, 'at most one longform POST per failed test');
 }
});

test('r27: connection probe does not report streaming verified if it works only by non-stream recovery',async()=>{
 const partial='data: '+JSON.stringify({choices:[{delta:{content:'半截测试回复'}}]})+'\n\n';
 const h=makeHarness({fetch:async(url,opts)=>choose(url,opts,
   new Response(partial,{headers:{'content-type':'text/event-stream'}}))});
 const r=await h.send({type:'VKN_AI_TEST'});
 assert.equal(r.ok,false);assert.match(r.error,/AI_STREAM_INCOMPLETE/);
 assert.equal(h.requests.length,3,'settings stream verification must not silently retry stream:false');
 assert.equal(JSON.parse(h.requests[2].opts.body).stream,true);
});

test('r27: connection probe recognizes explicit finish_reason=stop without [DONE]',async()=>{
 const terminal='data: '+JSON.stringify({choices:[{delta:{content:'长文接口正常'},finish_reason:'stop'}]})+'\n\n';
 const h=makeHarness({fetch:async(url,opts)=>choose(url,opts,
   new Response(terminal,{headers:{'content-type':'text/event-stream'}}))});
 const r=await h.send({type:'VKN_AI_TEST'});
 assert.equal(r.ok,true,r.error);assert.equal(r.data.longformVerified,true);
 assert.equal(r.data.longformTransport,'sse');assert.equal(h.requests.length,3);
});
