'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const endpoint='http://127.0.0.1:11434/v1/chat/completions';

function rig(replies,api=endpoint,extra={}){
  const requests=[];
  const responses=[...replies];
  const ctx={URL,AbortController,TextDecoder,TextEncoder,setTimeout,clearTimeout,Error,console,
    requireAiPermission:async()=>new URL(api),
    throwIfCancelled:(signal)=>{if(signal?.aborted)throw Error('AI_CANCELLED：已经取消');},
    VknAiHttp:{describe:(r)=>'AI_HTTP_'+r.status+'：请求失败'},
    chrome:{runtime:{id:'a'.repeat(32)}},
    fetch:async (url,options)=>{
      requests.push({url,options,payload:JSON.parse(options.body)});
      const result=responses.shift();
      assert.ok(result,'unexpected extra model request');
      if(result.status)return {ok:false,status:result.status,headers:{get:()=>null}};
      if(result.type==='json')return new Response(JSON.stringify(result.data),{headers:{'content-type':'application/json'}});
      const parts=result.parts||[new TextEncoder().encode(result.text||'')];
      let offset=0;
      return {ok:true,headers:{get:()=>result.contentType||'text/event-stream'},
        body:{getReader:()=>({read:async()=>offset<parts.length?{value:parts[offset++],done:false}:{done:true},releaseLock(){}})}};
    },...extra};
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../extension/longform-background.js'),'utf8'),ctx);
  const call=(opts={})=>ctx.vknLongformStream({model:'qwen-test',endpoint:api,provider:api===endpoint?'ollama':'custom'},
    '只根据材料整理正文','合成测试内容',{maxTokens:500,...opts});
  return {call,requests};
}
const event=(obj)=>'data: '+JSON.stringify(obj)+'\n\n';
const delta=(content,finish_reason)=>({choices:[{delta:{content},finish_reason:finish_reason??null}]});
const final=(content='完整正文',reason='stop')=>({choices:[{message:{content},finish_reason:reason}]});

test('r27: final finish_reason=stop is a valid SSE completion without a [DONE] transport sentinel',async()=>{
  const r=rig([{text:event(delta('第一段'))+event(delta('第二段','stop'))}]);
  const x=await r.call();
  assert.equal(x.text,'第一段第二段');assert.equal(x.finishReason,'stop');assert.equal(x.complete,true);
  assert.equal(x.transport,'sse');assert.equal(r.requests.length,1);
});

test('r27: an EOF [DONE] frame without trailing blank line is parsed, not rejected',async()=>{
  const r=rig([{text:event(delta('完整回答'))+'data: [DONE]'}]);
  const x=await r.call();assert.equal(x.text,'完整回答');assert.equal(x.complete,true);
  assert.equal(r.requests.length,1);
});

test('r27: SSE parsing survives multibyte UTF-8, CRLF boundaries, and comments across network chunks',async()=>{
  const raw=Buffer.from(': heartbeat\r\n\r\n'+event(delta('中文🙂')).replace(/\n/g,'\r\n')+event(delta('句号。','stop')).replace(/\n/g,'\r\n'));
  const chunks=[];for(let i=0;i<raw.length;i+=7)chunks.push(raw.subarray(i,i+7));
  const r=rig([{parts:chunks}]);const x=await r.call();
  assert.equal(x.text,'中文🙂句号。');assert.equal(x.complete,true);
});

test('r27: local incomplete SSE retries only once using non-stream and never concatenates partial text',async()=>{
  const r=rig([{text:event(delta('不能保存的半截草稿'))},{type:'json',data:final('可靠的完整正文')}]);
  const x=await r.call();
  assert.equal(x.text,'可靠的完整正文');assert.equal(x.complete,true);
  assert.equal(x.transport,'json-recovered');assert.equal(r.requests.length,2);
  assert.deepEqual(r.requests.map(x=>x.payload.stream),[true,false]);
  assert.deepEqual(r.requests[0].payload.messages,r.requests[1].payload.messages);
  assert.equal(r.requests[0].payload.model,r.requests[1].payload.model);
});

test('r27: retry with finish_reason=length is still truncated, never promoted to successful content',async()=>{
  const r=rig([{text:event(delta('半截'))},{type:'json',data:final('截断内容','length')}]);
  const x=await r.call();assert.equal(x.complete,true);assert.equal(x.finishReason,'length');
});

test('r27: recovery fails safely when local non-stream request is rejected; no partial result returned',async()=>{
  const r=rig([{text:event(delta('不可信的部分'))},{status:500}]);
  await assert.rejects(r.call(),/AI_HTTP_500/);assert.equal(r.requests.length,2);
});

test('r27: custom remote providers are not retried automatically or charged twice',async()=>{
  const r=rig([{text:event(delta('不完整'))}], 'https://provider.example/v1/chat/completions');
  await assert.rejects(r.call(),/AI_STREAM_INCOMPLETE/);
  assert.equal(r.requests.length,1);
});

test('r27: an incomplete final JSON event is not trusted and can be recovered on local Ollama',async()=>{
  const brokenFrame='data: {"choices":[{"delta":{"content":"broken"';
  const r=rig([{text:event(delta('partial'))+brokenFrame},
    {type:'json',data:final('完整修复')}]);
  const x=await r.call();assert.equal(x.text,'完整修复');assert.equal(r.requests.length,2);
});

test('r27: streaming connection verification can disable non-stream recovery',async()=>{
  const r=rig([{text:event(delta('半截'))}]);
  await assert.rejects(r.call({allowNonStreamRecovery:false}),/AI_STREAM_INCOMPLETE/);
  assert.equal(r.requests.length,1);
});

test('r27: streaming server error and empty output cannot be accepted as complete',async()=>{
  const error=rig([{text:'data: '+JSON.stringify({error:'upstream private message'})+'\n\n'}]);
  await assert.rejects(error.call(),/AI_STREAM_ERROR/);assert.equal(error.requests.length,1);
  const empty=rig([{text:'data: [DONE]\n\n'}]);
  await assert.rejects(empty.call(),/AI_EMPTY_REPLY/);assert.equal(empty.requests.length,1);
});


test('r27: content_filter/tool_calls finishes cannot be published as completed prose',async()=>{
 const s=rig([{text:event(delta('partial','content_filter'))}]);
 await assert.rejects(s.call(),/AI_STREAM_FINISH_REASON/);assert.equal(s.requests.length,1);
 const j=rig([{type:'json',data:final('partial','tool_calls')}]);
 await assert.rejects(j.call(),/AI_RESPONSE_FINISH_REASON/);assert.equal(j.requests.length,1);
});

test('r27: an abruptly interrupted reader retries locally without trusting streamed partial bytes',async()=>{
 const api='http://127.0.0.1:11434/v1/chat/completions';
 const raw=event(delta('不可保存的断流正文'));
 const requests=[];let index=0;
 const ctx={URL,AbortController,TextDecoder,TextEncoder,setTimeout,clearTimeout,Error,console,
   requireAiPermission:async()=>new URL(api),throwIfCancelled:()=>{},
   chrome:{runtime:{id:'a'.repeat(32)}},VknAiHttp:{describe:r=>'AI_HTTP_'+r.status},
   fetch:async(u,opts)=>{
     requests.push(JSON.parse(opts.body));index++;
     if(index===1)return {ok:true,headers:{get:()=> 'text/event-stream'},body:{getReader:()=>({
       read:(()=>{let first=true;return async()=>{if(first){first=false;return {done:false,value:new TextEncoder().encode(raw)};}throw Error('socket closed');};})(),
       releaseLock(){} })}};
     return new Response(JSON.stringify(final('断流后成功重新生成的正文')),{headers:{'content-type':'application/json'}});
   }};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../extension/longform-background.js'),'utf8'),ctx);
 const x=await ctx.vknLongformStream({model:'local'},'系统','用户');
 assert.equal(x.text,'断流后成功重新生成的正文');assert.equal(requests.length,2);
});
