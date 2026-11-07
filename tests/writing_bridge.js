/* Test-only: actual production worker in a Node VM, fixture models/Chrome APIs. */
'use strict';
const {makeHarness}=require('./ai_harness'),readline=require('node:readline');
let fail=false;
const h=makeHarness({fetch:async(url,opts)=>{
  if(url.endsWith('/health'))return Response.json({context_review:{available:false}});
  if(url.endsWith('/api/tags'))return new Response(JSON.stringify({models:[{name:'qwen2.5:3b'}]}));
  if(fail){fail=false;return new Response('unavailable',{status:503});}
  const text=JSON.parse(opts.body).messages[1].content;
  if(JSON.parse(opts.body).messages[0].content.includes('文字稿断句编辑')){
    const batch=JSON.parse(text.slice(text.indexOf('{')));
    return Response.json({choices:[{finish_reason:'stop',message:{content:JSON.stringify({turns:batch.turns.map(t=>({id:t.id,text:/[。！？.!?]$/.test(t.text)?t.text:t.text+'。'}))})}}]});
  }
  if(JSON.parse(opts.body).messages[0].content.includes('主题分类器')){
    const batch=JSON.parse(text);return new Response(JSON.stringify({choices:[{message:{content:JSON.stringify({items:batch.items.map(x=>({key:x.key,label:'supporting',certainty:'high',evidence:x.text.slice(0,20),reason:'模拟分类：主题背景'}))})}}]}));
  }
  let title='知识文档',body='### 核心要点\n\n- [00:02] 先保存原始声音，模型再按顺序处理。\n- [00:05] 不同说话人的观点分别记录，保留来源。';
  if(text.includes('整理方式：剧本')){title='剧本';body='### 场景一 · 场地未交代\n\n[00:02] 说话人1：为什么要先保存声音？\n\n[00:05] 说话人2：这样识别较慢时，也可以继续排队处理。';}
  else if(text.includes('整理方式：小说')){title='小说';body='“为什么要先保存声音？”他问。\n\n对方解释，先保存声音，后续才能按顺序处理。两人的对话围绕如何减少遗漏展开。[00:02–00:05]';}
  else if(text.includes('整理方式：文字稿')){title='文字稿';body='[00:02] 说话人1：为什么要先保存声音？\n\n[00:05] 说话人2：这样识别较慢时，也可以继续排队处理。';}
  else if(text.includes('整理方式：自定义')){title='自定义';body='### 按用户要求整理\n\n[00:02] 问：怎样避免遗漏？\n\n[00:05] 答：先缓存原始声音，再按顺序分析。';}
  return new Response(JSON.stringify({choices:[{finish_reason:'stop',message:{content:'## '+title+' · 模拟测试结果\n\n'+body+'\n\n> 本页转写与模型输出均为测试数据，不代表真实识别或生成质量。'}}]}));
}});
(async()=>{for await(const line of readline.createInterface({input:process.stdin,crlfDelay:Infinity})){
  try{const q=JSON.parse(line);let data;
    if(q.op==='send')data=await h.send(q.message);
    else if(q.op==='get')data=await h.storage.get(q.key);
    else if(q.op==='set'){await h.storage.set(q.values);data=true;}
    else if(q.op==='requests')data=h.requests.map(r=>({url:r.url,body:r.opts.body?JSON.parse(r.opts.body):null}));
    else if(q.op==='failNext'){fail=true;data=true;}
    else throw Error('unknown op');
    process.stdout.write(JSON.stringify({ok:true,data})+'\n');
  }catch(e){process.stdout.write(JSON.stringify({ok:false,error:e.message})+'\n');}
}})();
