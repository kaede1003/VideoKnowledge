'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const C=require('../extension/core.js');

test('progress is a truthful per-phase batch bar, not a fabricated overall ETA',()=>{
  const s=C.writingTaskProgress(null,{phase:'汇总全局主题',index:55,total:148,round:1},'knowledge');
  assert.equal(s.stageIndex,2);assert.equal(s.stageTotal,4);
  assert.equal(s.done,54);assert.equal(s.total,148);
  assert.equal(s.percent,36);assert.equal(s.round,1);
});
test('same-phase replayed cached checkpoints cannot rewind progress',()=>{
  const old=C.writingTaskProgress(null,{phase:'取材和证据索引',index:55,total:148},'knowledge');
  const replay=C.writingTaskProgress(old,{phase:'取材和证据索引',index:1,total:148},'knowledge');
  assert.equal(replay.index,55);assert.equal(replay.percent,old.percent);
  const newer=C.writingTaskProgress(replay,{phase:'汇总全局主题',index:1,total:8},'knowledge');
  assert.equal(newer.stageIndex,2);
  const stale=C.writingTaskProgress(newer,{phase:'取材和证据索引',index:100,total:148},'knowledge');
  assert.equal(stale.stageIndex,2);
});
test('real additional hierarchy round is explicit rather than a mysterious jump',()=>{
  const round1=C.writingTaskProgress(null,{phase:'汇总全局主题',round:1,index:15,total:15},'knowledge');
  const round2=C.writingTaskProgress(round1,{phase:'汇总全局主题',round:2,index:1,total:5},'knowledge');
  assert.equal(round2.round,2);assert.equal(round2.index,1);assert.equal(round2.done,0);
  assert.equal(C.writingTaskProgress(round2,{phase:'汇总全局主题',round:1,index:15,total:15},'knowledge').round,2);
});
test('invalid numbers cannot produce NaN or false 100 percent',()=>{
 const s=C.writingTaskProgress(null,{phase:'分章节编写正文',index:500,total:0,round:-1},'knowledge');
 assert.equal(s.total,1);assert.equal(s.index,1);assert.equal(s.done,0);assert.equal(s.percent,0);
});
test('transcript uses its own two stages and no knowledge-only labels',()=>{
 const a=C.writingTaskProgress(null,{phase:'翻译外语文字稿',index:1,total:12},'transcript');
 const b=C.writingTaskProgress(a,{phase:'中文文字稿断句与发言合并',index:3,total:12},'transcript');
 assert.deepEqual([a.stageIndex,b.stageIndex,a.stageTotal,b.stageTotal],[1,2,2,2]);
});

test('Edge toolbar badge identifies the active video and clears after a completed job',async()=>{
  const {makeHarness}=require('./ai_harness');
  const h=makeHarness({tabId:17,fetch:async(url)=>{
    if(url.endsWith('/api/tags'))return Response.json({models:[{name:'qwen2.5:3b'}]});
    return Response.json({choices:[{message:{content:'# 整理结果\n\n完整测试内容。'},finish_reason:'stop'}]});
  }});
  const r=await h.send({type:'VKN_AI_GENERATE',requestId:'ui-job-1',cues:[{
    id:'e'.repeat(32)+':1:0',time:0,end:2,text:'完整的中文节目内容。',language:'zh',source:'local-asr'
  }],writing:{mode:'knowledge'},meta:{title:'节目甲：长视频测试'}});
  assert.equal(r.ok,true,r.error);
  assert.ok(h.actionCalls.some(c=>c.method==='setBadgeText'&&c.tabId===17&&c.text==='AI'));
  assert.ok(h.actionCalls.some(c=>c.method==='setTitle'&&c.title.includes('节目甲：长视频测试')));
  assert.equal(h.actionCalls.filter(c=>c.method==='setBadgeText').at(-1).text,'');
});
