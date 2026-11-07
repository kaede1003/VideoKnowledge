'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const ext=path.join(__dirname,'..','extension');
const read=f=>fs.readFileSync(path.join(ext,f),'utf8');
const Core=require(path.join(ext,'core.js'));

test('stage summaries retain timestamps and transcript, but deep report is manual and separate',()=>{
  const ss={title:'示例',url:'https://www.youtube.com/watch?v=ab12',createdAt:'2026-11-06T04:00:00Z',
    segments:[{time:12,text:'第一阶段我们要理解模型基础的原理',source:'local-asr'},
      {time:51,text:'例如数据集必须避免未来信息泄漏',source:'local-asr'}],
    summaries:[{start:12,end:51,mode:'ai',markdown:'- [00:12] 模型需要验证',count:2}],aiMarkdown:''};
  const text=Core.buildDocumentMarkdown(ss);
  assert.match(text,/定时阶段摘要/);
  assert.match(text,/第一阶段/);
  assert.match(text,/\[00:51\]\(https:\/\/www.youtube.com\/watch\?v=ab12&t=51s\)/);
  assert.match(text,/全部已收集文本/);
  assert.doesNotMatch(text,/AI 结构化知识文档/);
  ss.aiMarkdown='# 这是手动产生的深入报告';
  assert.match(Core.buildDocumentMarkdown(ss),/AI 结构化知识文档/);
});

test('offline incremental excerpt clearly states non-AI mode and keeps citation times',()=>{
  const cues=[{time:9,text:'第一步做数据收集并核对完整性',source:'local-asr'},
    {time:20,text:'第二步用统计方法分析信号强弱',source:'local-asr'}];
  const md=Core.buildOfflinePeriodSummary(cues,{url:'https://www.bilibili.com/video/BV1x'});
  assert.match(md,/未调用语言模型/);
  assert.match(md,/\[00:09\]/);
  assert.equal(Core.cueIdentity(cues[0]),Core.cueIdentity({...cues[0]}));
});

test('ASR start claims tab stream synchronously, before asynchronous status queries', async()=>{
  let captureCalls=0;
  const ctx={Promise,console,setTimeout,clearTimeout,
    chrome:{runtime:{getURL:()=> 'chrome-extension://test/offscreen.html',getContexts:async()=>[],sendMessage:async()=>({ok:true,data:{}})},
      tabs:{onRemoved:{addListener(){}},sendMessage:async()=>({})},
      scripting:{executeScript:async()=>{}},
      tabCapture:{getMediaStreamId(){captureCalls++;return Promise.resolve('fake-id');}},
      action:{setBadgeText:async()=>{},setBadgeBackgroundColor:async()=>{}},
      offscreen:{createDocument:async()=>{}}}};
  vm.createContext(ctx);
  vm.runInContext(read('asr-background.js'),ctx);
  // Override the slow parts; only check the click sequence.
  vm.runInContext('vknStartAsr=async (_tab, streamPromise)=>({running:true,id:await streamPromise})',ctx);
  const result=vm.runInContext('vknRequestAsrStart({id:12,url:"https://www.youtube.com/watch?v=x"})',ctx);
  assert.equal(captureCalls,1,'tabCapture must be called before the first await');
  assert.equal((await result).id,'fake-id');
});

test('ASR pause and resume use distinct explicit commands, not a toggle',()=>{
  const s=read('content.js'),bg=read('asr-background.js'),offs=read('offscreen.js');
  assert.ok(s.includes("call(state.asrPaused?'VKN_ASR_RESUME':'VKN_ASR_PAUSE')"));
  assert.ok(s.includes("stopping?'VKN_ASR_STOP':'VKN_ASR_START'"));
  assert.ok(bg.includes("case 'VKN_ASR_PAUSE'"));
  assert.ok(bg.includes("case 'VKN_ASR_RESUME'"));
  assert.ok(offs.includes('if(!audioClient || !incoming?.length || player.paused || asrPaused)return;'));
  assert.ok(offs.includes("return {running:asrActive,phase:asrPhase"));
});

test('LoRA plan returns quickly without waiting for inference, abort results actionable',async()=>{
  let timeoutMs=0;
  const ctrl=new AbortController();
  const ctx={AbortController,console,
    setTimeout(fn,ms){timeoutMs=ms;return setTimeout(fn,0);},clearTimeout,
    fetch(_url,opts){return new Promise((resolve,reject)=>{
      opts.signal.addEventListener('abort',()=>reject(Error('signal is aborted without reason')),{once:true});
    });},
    chrome:{}};
  vm.createContext(ctx);
  vm.runInContext(read('lora-background.js'),ctx);
  await assert.rejects(vm.runInContext("vknLoraLocal('/lora/plan',{prompt:'提取清晰的人物图像'})",ctx),/15秒内没有完成处理/);
  assert.equal(timeoutMs,15000);
});

test('never auto-generates a complete deep document',()=>{
 const code=read('content.js');
 assert.ok(code.includes("$('vkn-ai').addEventListener('click',()=>runAi(false))"));
 assert.ok(!code.includes('maybeAutoAi()'));
 assert.ok(code.includes('maybePeriodicSummary()'));
});
