'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const C=require('../extension/core.js'),{makeHarness}=require('./ai_harness');
const sid='d'.repeat(32),a=sid+':spk1',b=sid+':spk2';
const cues=[{id:sid+':1:0',revision:1,time:1,text:'问题是什么',speakerId:a,speakerStatus:'estimated',source:'local-asr'},
{id:sid+':1:1',revision:1,time:3,text:'这是答案',speakerId:b,speakerStatus:'estimated',source:'local-asr'},
{id:sid+':2:0',revision:1,time:5,text:'继续追问',speakerId:a,speakerStatus:'estimated',source:'local-asr'}];
const session={key:'yt:sample',title:'测试对话',url:'https://www.youtube.com/watch?v=sample',segments:cues,speakerNames:{[a]:'主持人',[b]:'嘉宾'},speakerOverrides:{}};
test('speaker fields survive durable cue sanitization and later translation revisions',()=>{
 const incoming={...cues[0],revision:2,text:'中文译文',translation:'中文译文',original:'original'};
 const out=C.mergeCues(cues,[incoming]);assert.equal(out[0].speakerId,a);assert.equal(out[0].text,'中文译文');
});
test('speaker names and per-line correction project without mutating original cues',()=>{
 const s={...session,speakerOverrides:{[cues[0].id]:b}};
 const out=C.cuesWithSpeakers(s);assert.equal(out[0].speakerLabel,'嘉宾');assert.equal(out[0].speakerStatus,'manual');assert.equal(cues[0].speakerId,a);
});
test('unknown override is retained, not filled by best guess',()=>{
 const out=C.cuesWithSpeakers({...session,speakerOverrides:{[cues[0].id]:''}});assert.equal(out[0].speakerLabel,'说话人待确认');
});
test('distinct recording IDs do not imply same voice',()=>{
 const s={segments:[...cues,{...cues[0],time:12,id:'e'.repeat(32)+':1:0',speakerId:'e'.repeat(32)+':spk1'}]};
 assert.equal(C.speakerCatalog(s).length,3);
});
test('export has named dialogue, original transcript and existing deep report',()=>{
 const md=C.buildDocumentMarkdown({...session,aiMarkdown:'## 对话观点\n示例整理'});
 assert.match(md,/【主持人】(?:\[[^\]]+\] )?问题是什么/);assert.match(md,/【嘉宾】(?:\[[^\]]+\] )?这是答案/);assert.match(md,/AI 结构化知识文档/);
});
test('speaker names cannot inject executable HTML',()=>{
 const html=C.buildHtmlDocument({...session,speakerNames:{[a]:'<img src=x onerror=alert(1)>'}});
 assert.ok(!html.includes('<img'));assert.equal(C.cleanSpeakerNames({'__proto__':'bad','invalid':'bad'})['invalid'],undefined);
});
test('speaker aliases and overrides actually persist through background save/load',async()=>{
 const h=makeHarness();const s={...session,speakerOverrides:{[cues[0].id]:b}};
 let r=await h.send({type:'VKN_SAVE_SESSION',session:s});assert.equal(r.ok,true);
 r=await h.send({type:'VKN_GET_SESSION',key:s.key});assert.equal(r.data.speakerNames[a],'主持人');assert.equal(r.data.speakerOverrides[cues[0].id],b);
});
test('deep report request contains speaker labels and attribution constraint',async()=>{
 const h=makeHarness();let r=await h.send({type:'VKN_AI_GENERATE',cues:C.cuesWithSpeakers(session),meta:{title:'对话'}});assert.equal(r.ok,true);
 const body=JSON.parse(h.requests.find(x=>x.opts.method==='POST').opts.body);
 assert.match(body.messages[0].content,/不把不同人的观点合为共识/);assert.match(body.messages[1].content,/【主持人】/);
});
test('periodic summary also carries labels',async()=>{
 const h=makeHarness();let r=await h.send({type:'VKN_AI_PERIODIC_SUMMARY',cues:C.cuesWithSpeakers(session),meta:{title:'对话'}});assert.equal(r.ok,true);
 const body=JSON.parse(h.requests.find(x=>x.opts.method==='POST').opts.body);assert.match(body.messages[1].content,/【嘉宾】/);
});
test('view report is a navigation action, not a new model request',()=>{
 const text=fs.readFileSync(path.join(__dirname,'../extension/content.js'),'utf8');
 assert.match(text,/vkn-view-report'\)\.addEventListener\('click',jumpToReport\)/);assert.match(text,/render\(\);jumpToReport\(\)/);
 assert.ok(!text.includes('C.cuesWithSpeakers(captured,snapshot)')); // regression: undefined variable in periodic path
});
