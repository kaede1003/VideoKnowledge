'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {makeHarness}=require('./ai_harness.js');

test('toolbar task badge is tab scoped, names the source video, and clears only matching request',async()=>{
 const h=makeHarness(),changes=[];
 const action=h.ctx.chrome.action;
 action.setBadgeText=async args=>changes.push({kind:'text',...args});
 action.setBadgeBackgroundColor=async args=>changes.push({kind:'color',...args});
 action.setTitle=async args=>changes.push({kind:'title',...args});
 h.ctx.vknStartWritingBadge(2,'a','采访视频 A');
 h.ctx.vknStartWritingBadge(3,'b','视频 B');
 h.ctx.vknWritingBadgePhase(2,'a','汇总全局主题',55,148,2);
 assert.ok(changes.some(x=>x.kind==='text'&&x.tabId===2&&x.text==='AI'));
 assert.ok(changes.some(x=>x.kind==='title'&&x.tabId===2&&x.title.includes('采访视频 A')&&x.title.includes('第2轮')));
 assert.equal(h.ctx.vknClearWritingBadge(2,'wrong-request'),false,'old request must not clear a new task');
 assert.equal(h.ctx.vknClearWritingBadge(2,'a'),true);
 assert.ok(changes.some(x=>x.kind==='text'&&x.tabId===2&&x.text===''));
 assert.equal(changes.filter(x=>x.kind==='text'&&x.tabId===3&&x.text==='').length,0);
 assert.equal(h.ctx.vknClearWritingBadge(3,'b'),true);
});
test('cancel between longform worker slices clears the toolbar ghost task',async()=>{
 const h=makeHarness(),updates=[];
 h.ctx.chrome.action.setBadgeText=async x=>updates.push(x);
 h.ctx.vknStartWritingBadge(5,'job-5','模拟视频');
 const out=h.ctx.cancelAiJob({type:'VKN_AI_CANCEL',requestId:'job-5'}, {tab:{id:5},url:'https://youtube.com/watch?v=a'});
 assert.equal(out.cancelled,true);assert.equal(updates.at(-1).text,'');
});
