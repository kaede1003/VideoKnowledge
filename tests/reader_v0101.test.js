'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const C=require('../extension/core');
const long='这是用于测试的合成文字我们首先保留所有原始信息然后按照发言人的顺序呈现但是不应该把没有标点的长段落直接当作排版完成因此还要检查每个句子的边界并且保护英文名称与数字信息';
test('long unchanged unpunctuated answer is not completed punctuation',()=>{
 const t={id:'turn-0',text:long};const r=C.validateTranscriptPunctuation(JSON.stringify({turns:[t]}),[t]);assert.equal(r.held.length,1);
});
test('one wrong row must not discard punctuation from valid rows',()=>{
 const ts=[{id:'a',text:'先保存原文'},{id:'b',text:'再生成结果'}];
 const r=C.validateTranscriptPunctuation(JSON.stringify({turns:[{id:'a',text:'先保存原文。'}]}),ts);
 assert.equal(r.turns[0].text,'先保存原文。');assert.equal(r.held.length,1);
});
const {PairBuffer}=require('../extension/caption-buffer');
const {makeHarness}=require('./ai_harness');
const reply=x=>Response.json({choices:[{message:{content:JSON.stringify(x)},finish_reason:'stop'}]});
const plain=s=>s.replace(/[\s，,。.;；:：！!？?、“”‘’「」『』（）()…]/g,'');
test('small punctuation units retain every source character and version',()=>{
 const text=('保留Anthropic与Claude Sonnet 5.5的名称以及数字3.14和178.6。').repeat(35);
 const ts=[{id:'a',text}],u=C.punctuationUnits(ts);assert.ok(u.length>1);assert.equal(u.map(x=>x.text).join(''),text);
 const merged=C.mergePunctuationUnits(ts,u);assert.equal(plain(merged[0].text),plain(text));assert.equal(merged.length,1);
});
test('partial invalid response preserves already punctuated good row',()=>{
 const ts=[{id:'a',text:'我们保留所有信息'},{id:'b',text:'不会删除原始数据'}];
 const r=C.validateTranscriptPunctuation(JSON.stringify({turns:[{id:'a',text:'我们保留所有信息。'},{id:'b',text:'会删除原始数据。'}]}),ts);
 assert.equal(r.turns[0].text,'我们保留所有信息。');assert.equal(r.turns[1].text,ts[1].text);assert.equal(r.held.length,1);
});
test('anchor repair inserts only punctuation without retyping names',()=>{
 const t={id:'a',text:'我们今天讨论Cloud Sonet的表现但是仍需保留原始数据所以结论不能凭空猜测'};
 const r=C.validatePunctuationRepair(JSON.stringify({turns:[{id:'a',edits:[{after:'Cloud Sonet的表现',punct:'，'},{after:'仍需保留原始数据',punct:'。'},{after:'结论不能凭空猜测',punct:'。'}]}]}),[t]);
 assert.equal(r.held.length,0);assert.equal(plain(r.turns[0].text),plain(t.text));assert.match(r.turns[0].text,/表现，但是/);
});
test('anchor retry cannot invent source or split a decimal/version',()=>{
 const t={id:'a',text:'这里显示Claude Sonnet 5.5模型的输出'};
 for(const after of ['不存在的文本','Sonnet 5','这里显示Clau']){
  const r=C.validatePunctuationRepair(JSON.stringify({turns:[{id:'a',edits:[{after,punct:'。'}]}]}),[t]);assert.equal(r.held.length,1);assert.equal(r.turns[0].text,t.text);
 }
});
test('duplicate ambiguous anchor never guessed',()=>{
 const t={id:'a',text:'这是一段文字这是一段文字'};
 const r=C.validatePunctuationRepair(JSON.stringify({turns:[{id:'a',edits:[{after:'这是一段文字',punct:'。'}]}]}),[t]);assert.equal(r.held.length,1);
});
test('fallback readable layout retains every word, digit and negation',()=>{
 const t={id:'a',text:long+'但是Claude Sonnet 5.5不能变成6.0并且3.14是数字'};
 const r=C.fallbackTranscriptLayout(t);assert.equal(plain(r.text),plain(t.text));assert.match(r.text,/[，。]/);assert.equal(r.punctuationFallback,true);
 assert.ok(r.text.split('\n').every(x=>x.length<=120));
});
test('only changed spelling is rejected but punctuation is retried separately',async()=>{
 let count=0;
 const original='这里讨论Cloud Sonet的文本处理能力但是不能更改原始说法所以原文要保留并且数字5.5不得随意修改';
 const h=makeHarness({fetch:async(u,o)=>{
  if(u.endsWith('/api/tags'))return Response.json({models:[{name:'qwen2.5:3b'}]});count++;
  const body=JSON.parse(o.body),t=JSON.parse(body.messages[1].content.slice(body.messages[1].content.indexOf('{'))).turns[0];
  assert.equal(body.response_format.type,'json_schema');
  if(count===1)return reply({turns:[{id:t.id,text:original.replace('Cloud Sonet','Claude Sonnet')+'。'}]});
  return reply({turns:[{id:t.id,edits:[{after:'文本处理能力',punct:'，'},{after:'不能更改原始说法',punct:'。'},{after:'数字5.5不得随意修改',punct:'。'}]}]});
 }});
 const r=await h.send({type:'VKN_AI_GENERATE',cues:[{time:0,text:original}],writing:{mode:'transcript',correctPhrases:false}});
 assert.equal(r.ok,true,r.error);assert.equal(count,2);assert.match(r.data.markdown,/能力，但是/);assert.match(r.data.markdown,/Cloud Sonet/);assert.doesNotMatch(r.data.markdown,/Claude/);
});
test('generation rechecks stored subtitles and uses correction before punctuation',async()=>{
 const sid='b'.repeat(32),original='这里讨论Cloud Sonet的文本处理能力以及Anthrope的模型接口';
 const fixed='这里讨论Claude Sonnet的文本处理能力以及Anthropic的模型接口';
 const cue={id:sid+':1:0',time:0,end:5,contextEpoch:0,text:original,original,language:'zh'};let checks=0;
 const evidence={id:'e',stream:sid,epoch:0,start:1,end:2,source:'visible',samples:2,seenSpan:1,text:fixed};
 const h=makeHarness({fetch:async(u,o)=>{
  if(u.endsWith('/api/tags'))return Response.json({models:[{name:'qwen2.5:3b'}]});
  if(u.includes('caption-review/validate')){checks++;return Response.json({reviews:[{id:cue.id,source:original,text:fixed,status:'applied',evidence:fixed,reason:'synthetic fixture'}]});}
  const body=JSON.parse(o.body),turn=JSON.parse(body.messages[1].content.slice(body.messages[1].content.indexOf('{'))).turns[0];assert.equal(turn.text,fixed);
  return reply({turns:[{id:turn.id,text:fixed+'。'}]});
 }});
 const r=await h.send({type:'VKN_AI_GENERATE',cues:[cue],meta:{captionObservations:[evidence]},writing:{mode:'transcript',correctPhrases:false}});
 assert.equal(r.ok,true,r.error);assert.equal(checks,1);assert.match(r.data.markdown,/Claude Sonnet/);assert.equal(cue.original,original);assert.equal(r.data.captionReviews[cue.id].source,original);
});
const frames=(t=0,epoch=0)=>[{stream:'s',epoch,time:t,image:'data:image/jpeg;base64,abc'},{stream:'s',epoch,time:t+.5,image:'data:image/jpeg;base64,def'}];
test('frame buffer holds multiple pairs while model is busy, bounded and ordered',()=>{
 const b=new PairBuffer({maxPairs:2});b.push(frames(1));b.push(frames(3));b.push(frames(5));assert.equal(b.status().queued,2);assert.equal(b.status().dropped,1);assert.equal(b.take('s',0,6)[0].time,3);assert.equal(b.take('s',0,6)[0].time,5);
});
test('frame buffer refuses cross-epoch/stale/oversize images and clears on stop',()=>{
 const b=new PairBuffer({maxBytes:300,maxAge:5});b.push(frames(1));assert.equal(b.take('s',1,2),null);b.push(frames(3));assert.equal(b.take('s',0,20),null);
 const f=frames(4);f[0].image='x'.repeat(500);assert.equal(b.push(f),false);b.clear();assert.equal(b.status().bytes,0);assert.equal(b.status().queued,0);
});
test('frame buffer switches sessions instead of mixing timelines',()=>{const b=new PairBuffer();b.push(frames(1));b.push(frames(2,1));assert.equal(b.status().queued,1);assert.equal(b.take('s',1,3)[0].epoch,1);});
