'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const C=require('../extension/core');
const {makeHarness}=require('./ai_harness');

const sid='a'.repeat(32),speaker=sid+':spk1';
const spanish='Si tuviéramos el recuerdo de todas las existencias, las almas eligen las experiencias que van a vivir.';
const cue=(i,text,extra={})=>({id:sid+':'+(i+1)+':0',time:i*6,end:i*6+5,text,original:text,language:'es',translationStatus:'needs_review',needsReview:true,
  source:'local-asr',speakerId:speaker,speakerLabel:'说话人1',speakerStatus:'estimated',contextEpoch:0,...extra});
const reply=content=>Response.json({choices:[{message:{content},finish_reason:'stop'}]});
function parseTagged(text,tag){const m=String(text).match(new RegExp('<'+tag+'>\\s*([\\s\\S]*?)\\s*</'+tag+'>'));if(!m)throw Error('translation payload tag missing');return JSON.parse(m[1]);}

// Core contract: only foreign source text is translated; completed Chinese ASR-side
// translations are reused, while suspect candidates are deliberately retranslated.
test('foreign transcript detection distinguishes raw, completed and Chinese source text',()=>{
 const raw=cue(0,spanish),turn=C.readingTurns([raw])[0];
 assert.equal(C.transcriptSourceLanguage(turn),'es');assert.equal(C.transcriptNeedsTranslation(turn),true);
 const done=cue(0,'这段内容已经翻译成中文。',{original:spanish,text:'这段内容已经翻译成中文。',translationStatus:'done',needsReview:false});
 assert.equal(C.transcriptNeedsTranslation(C.readingTurns([done])[0]),false);
 const chinese=cue(0,'这是一段中文原文。',{language:'zh',translationStatus:'off',needsReview:false});
 assert.equal(C.transcriptNeedsTranslation(C.readingTurns([chinese])[0]),false);
 const japanese=cue(0,'私たちはこの経験を選びます。',{language:'unknown',translationStatus:'off',needsReview:false});
 assert.equal(C.transcriptNeedsTranslation(C.readingTurns([japanese])[0]),true);
});

test('translation prompt binds each speaker turn ID and requests Simplified Chinese only',()=>{
 const turns=C.readingTurns([cue(0,spanish)]),p=C.transcriptTranslationPrompt(turns);
 assert.match(p.system,/简体中文/);assert.match(p.system,/不得总结、删减、合并/);
 const payload=parseTagged(p.user,'transcript_translation_data');
 assert.deepEqual(payload.turns.map(x=>x.id),['turn-0']);assert.equal(payload.turns[0].source_language,'es');assert.equal(payload.turns[0].text,spanish);
});

test('translation validator rejects untranslated Spanish, missing IDs and changed Arabic numerals',()=>{
 const source=C.readingTurns([cue(0,'Tengo 3 opciones y 2 preguntas.')]);
 assert.throws(()=>C.validateTranscriptTranslation(JSON.stringify({turns:[{id:'turn-0',text:'Tengo 3 opciones y 2 preguntas.'}]}),source),/AI_TRANSLATION_UNTRANSLATED/);
 assert.throws(()=>C.validateTranscriptTranslation(JSON.stringify({turns:[{id:'other',text:'我有3个选项和2个问题。'}]}),source),/AI_TRANSLATION_INVALID/);
 assert.throws(()=>C.validateTranscriptTranslation(JSON.stringify({turns:[{id:'turn-0',text:'我有4个选项和2个问题。'}]}),source),/AI_TRANSLATION_INVALID/);
 const valid=C.validateTranscriptTranslation(JSON.stringify({turns:[{id:'turn-0',text:'我有3个选项和2个问题。'}]}),source);
 assert.equal(valid.turns[0].translated,true);assert.equal(valid.turns[0].sourceText,source[0].text);
 const spelled=C.readingTurns([cue(0,'Tengo veinte opciones.')]);
 assert.doesNotThrow(()=>C.validateTranscriptTranslation(JSON.stringify({turns:[{id:'turn-0',text:'我有20个选项。'}]}),spelled));
});

test('short transcript generation translates Spanish before punctuation and keeps speaker attribution',async()=>{
 let translationCalls=0,punctuationCalls=0;
 const h=makeHarness({fetch:async(url,opts)=>{
  if(url.endsWith('/api/tags'))return Response.json({models:[{name:'qwen2.5:3b'}]});
  const user=JSON.parse(opts.body).messages[1].content;
  if(user.includes('<transcript_translation_data>')){
   translationCalls++;const data=parseTagged(user,'transcript_translation_data');
   return reply(JSON.stringify({turns:data.turns.map(t=>({id:t.id,text:'如果我们记得所有生命历程，灵魂会选择自己将要经历的体验。'}))}));
  }
  if(user.includes('整理方式：文字稿')){
   punctuationCalls++;const payload=JSON.parse(user.slice(user.indexOf('{')));
   return reply(JSON.stringify({turns:payload.turns.map(t=>({id:t.id,text:t.text}))}));
  }
  throw Error('unexpected model request');
 }});
 const r=await h.send({type:'VKN_AI_GENERATE',cues:[cue(0,spanish)],writing:{mode:'transcript'}});
 assert.equal(r.ok,true,r.error);assert.equal(translationCalls,1);assert.equal(punctuationCalls,1);
 assert.match(r.data.markdown,/如果我们记得所有生命历程/);assert.doesNotMatch(r.data.markdown,/Si tuviéramos|las almas/);
 assert.match(r.data.markdown,/说话人1/);assert.match(r.data.audit.notes.join(' '),/翻译为简体中文/);
});

test('short transcript automatically preserves source with a visible audit note when AI cannot translate it',async()=>{
 const h=makeHarness({fetch:async(url,opts)=>{
  if(url.endsWith('/api/tags'))return Response.json({models:[{name:'qwen2.5:3b'}]});
  const user=JSON.parse(opts.body).messages[1].content;
  if(user.includes('<transcript_translation_data>')){
   const data=parseTagged(user,'transcript_translation_data');
   return reply(JSON.stringify({turns:data.turns.map(t=>({id:t.id,text:t.text}))}));
  }
  if(user.includes('<transcript_translation_single>'))return reply(spanish);
  if(user.includes('整理方式：文字稿')){
   const payload=JSON.parse(user.slice(user.indexOf('{')));
   return reply(JSON.stringify({turns:payload.turns.map(t=>({id:t.id,text:t.text}))}));
  }
  throw Error('unexpected request');
 }});
 const r=await h.send({type:'VKN_AI_GENERATE',cues:[cue(0,spanish)],writing:{mode:'transcript'}});
 assert.equal(r.ok,true,r.error);
 assert.match(r.data.markdown,/Si tuviéramos/);
 assert.match(r.data.audit.notes.join(' '),/保留对应原文/);
});

test('long transcript path translates bounded source units and resumes after a failed translation batch',async()=>{
 let translationCalls=0,punctuationCalls=0,translatedRows=0,failOnce=true;
 const key='yt:video-translation-long';
 const storeKey='vkn:session:'+encodeURIComponent(key);
 const h=makeHarness({store:{[storeKey]:{key,url:'https://www.youtube.com/watch?v=video-translation-long',segments:[]}},fetch:async(url,opts)=>{
  if(url.endsWith('/api/tags'))return Response.json({models:[{name:'qwen2.5:3b'}]});
  const user=JSON.parse(opts.body).messages[1].content;
  if(user.includes('<transcript_translation_data>')){
   translationCalls++;const data=parseTagged(user,'transcript_translation_data');
   if(failOnce&&translationCalls===2){failOnce=false;return new Response('temporary model error',{status:500});}
   translatedRows+=data.turns.length;
   return reply(JSON.stringify({turns:data.turns.map((t,i)=>({id:t.id,text:'这部分西班牙语的中文翻译内容。'}))}));
  }
  if(user.includes('整理方式：文字稿')){
   punctuationCalls++;const payload=JSON.parse(user.slice(user.indexOf('{')));
   return reply(JSON.stringify({turns:payload.turns.map(t=>({id:t.id,text:t.text}))}));
  }
  throw Error('unexpected longform model request');
 }});
 const longSpanish='hola mundo y la vida. '.repeat(240);
 const cues=[cue(0,longSpanish),cue(1,longSpanish),cue(2,longSpanish)];
 const run=async()=>{
  let r=await h.send({type:'VKN_AI_GENERATE',sessionKey:key,meta:{sessionKey:key},cues,writing:{mode:'transcript'}});
  let steps=0;
  while(r.ok&&r.data?.continuing){
   assert.ok(++steps<100,'the resumable request must converge');
   r=await h.send({type:'VKN_AI_GENERATE',requestId:r.data.requestId,sessionKey:key,resumeOnly:true});
  }
  return r;
 };
 const first=await run();
 assert.equal(first.ok,false);assert.match(first.error,/AI_HTTP_500/);assert.equal(translationCalls,2);
 const r=await run();
 assert.equal(r.ok,true,r.error);assert.ok(translationCalls>2);assert.ok(translatedRows>10);assert.ok(punctuationCalls>=1);
 assert.match(r.data.markdown,/中文翻译内容/);assert.doesNotMatch(r.data.markdown,/hola mundo/);
 assert.match(r.data.audit.notes.join(' '),/翻译为简体中文/);assert.equal(r.data.coverage.covered,3);
});

// r23: the model may return only 2 of 5 requested rows, or reorder them.
// Such replies must not force another request for rows already validated.
test('partial foreign-language batch preserves valid IDs and retries only missing rows',async()=>{
 const turns=Array.from({length:5},(_,i)=>({id:'turn-'+i,text:'Una frase en español '+i+'.',records:[cue(i,'Una frase en español '+i+'.')]}));
 const requests=[],saved=[];
 const response=rows=>JSON.stringify({turns:rows.map(x=>({id:x.id,text:'这是一句西班牙语内容 '+x.text.match(/\d+/)[0]+'。'}))});
 const result=await C.translateTranscriptBatch(turns,async rows=>{
   requests.push(rows.map(x=>x.id));
   if(requests.length===1){
     const all=JSON.parse(response(rows)).turns;
     return JSON.stringify({turns:[all[3],all[0],{id:'turn-2',text:'保留错误数字 123。'}]});
   }
   return response(rows);
 },{save:async s=>saved.push(s)});
 assert.deepEqual(requests[0],['turn-0','turn-1','turn-2','turn-3','turn-4']);
 assert.deepEqual(requests[1],['turn-1','turn-2','turn-4']);
 assert.equal(result.turns.length,5);
 assert.deepEqual(result.turns.map(x=>x.id),turns.map(x=>x.id));
 assert.ok(result.turns.every(x=>x.translated&&x.sourceText));
 assert.equal(saved.length,2);assert.deepEqual(saved[0].turns.map(x=>x.id),['turn-0','turn-3']);
});

test('translation shards resume after interruption and never request accepted IDs again',async()=>{
 const turns=[{id:'t1',text:'Hola uno',records:[]},{id:'t2',text:'Hola dos',records:[]}];
 let checkpoint,asked=[];
 await assert.rejects(()=>C.translateTranscriptBatch(turns,async rows=>{
   asked.push(rows.map(x=>x.id));
   if(asked.length===1)return JSON.stringify({turns:[{id:'t1',text:'中文第一句。'}]});
   throw Error('AI_CONTINUE_REQUIRED：worker slice finished');
 },{save:async state=>{checkpoint=state;}}),/AI_CONTINUE_REQUIRED/);
 assert.deepEqual(checkpoint.turns,[{id:'t1',text:'中文第一句。'}]);
 const resumed=await C.translateTranscriptBatch(turns,async rows=>{
   assert.deepEqual(rows.map(x=>x.id),['t2']);
   return JSON.stringify({turns:[{id:'t2',text:'中文第二句。'}]});
 },{previous:checkpoint,save:async state=>{checkpoint=state;}});
 assert.deepEqual(resumed.turns.map(x=>x.text),['中文第一句。','中文第二句。']);
 assert.deepEqual(checkpoint.turns.map(x=>x.id),['t1','t2']);
});

test('invalid JSON triggers smaller bounded retries and a permanently untranslated row never publishes',async()=>{
 const turns=Array.from({length:6},(_,i)=>({id:'t'+i,text:'Hola',records:[]}));
 const sizes=[];
 await assert.rejects(()=>C.translateTranscriptBatch(turns,async rows=>{
   sizes.push(rows.length);
   return '{"turns": ['; // a syntactically truncated response
 },{maxAttempts:4}),/AI_TRANSLATION_INVALID/);
 assert.deepEqual(sizes.slice(0,4),[6,4,2,1]);
 assert.equal(sizes.length,4,'cap model attempts per missing row');
});

test('valid translation rows are kept even when sibling returned unknown, duplicate or untranslated IDs',()=>{
 const turns=[{id:'a',text:'Hola',records:[]},{id:'b',text:'Adios',records:[]},{id:'c',text:'Gracias',records:[]}];
 const result=C.inspectTranscriptTranslation(JSON.stringify({turns:[
   {id:'a',text:'你好。'},{id:'a',text:'另一个版本。'},{id:'b',text:'中文 ' + 'Adios '.repeat(30)},{id:'c',text:'谢谢。'},
   {id:'other',text:'额外内容。'}
 ]}),turns);
 assert.deepEqual(result.turns.map(x=>x.id),['c']);
 assert.deepEqual(result.missing.map(x=>x.id),['a','b']);
 assert.match(result.reason,/duplicate_id|unknown_id/);
});

test('two-hour-style longform saves partial translation rows before an HTTP failure and resumes only missing IDs',async()=>{
 const key='yt:translation-partial-checkpoint',storeKey='vkn:session:'+encodeURIComponent(key);
 let seen=0,firstIds=[],secondIds=[],failOnce=true;
 const h=makeHarness({store:{[storeKey]:{key,url:'https://www.youtube.com/watch?v=translation-partial-checkpoint',segments:[]}},fetch:async(url,opts)=>{
   if(url.endsWith('/api/tags'))return Response.json({models:[{name:'qwen2.5:3b'}]});
   const user=JSON.parse(opts.body).messages[1].content;
   if(user.includes('<transcript_translation_data>')){
     seen++;
     const rows=parseTagged(user,'transcript_translation_data').turns;
     if(seen===1){
       assert.ok(rows.length>1,'first longform batch should have multiple turns');
       firstIds=rows.map(x=>x.id);
       return reply(JSON.stringify({turns:[{id:rows[0].id,text:'中文有效翻译。'}]}));
     }
     if(seen===2){secondIds=rows.map(x=>x.id);if(failOnce){failOnce=false;return new Response('',{status:500});}}
     return reply(JSON.stringify({turns:rows.map(x=>({id:x.id,text:'中文有效翻译。'}))}));
   }
   if(user.includes('整理方式：文字稿')){
     const rows=JSON.parse(user.slice(user.indexOf('{'))).turns;
     return reply(JSON.stringify({turns:rows.map(x=>({id:x.id,text:x.text}))}));
   }
   throw Error('unexpected model request');
 }});
 const big='hola '.repeat(190),cues=Array.from({length:22},(_,i)=>cue(i,i===0?big:'hola '.repeat(160),{speakerStatus:'overlap'}));
 async function run(){let r=await h.send({type:'VKN_AI_GENERATE',sessionKey:key,meta:{sessionKey:key},cues,writing:{mode:'transcript'}});let steps=0;
   while(r.ok&&r.data?.continuing){assert.ok(++steps<160,'bounded resume');r=await h.send({type:'VKN_AI_GENERATE',requestId:r.data.requestId,sessionKey:key,resumeOnly:true});}return r;}
 const failed=await run();assert.equal(failed.ok,false);assert.match(failed.error,/AI_HTTP_500/);
 assert.ok(firstIds[0]);assert.deepEqual(secondIds,firstIds.slice(1));
 const partial=Object.entries(h.state).find(([k])=>k.includes(':units:translation-0'))?.[1];
 assert.ok(partial);assert.equal(partial.turns.length,1);
 const done=await run();assert.equal(done.ok,true,done.error);
 assert.match(done.data.markdown,/中文有效翻译/);assert.doesNotMatch(done.data.markdown,/hola/);
 assert.equal(done.data.coverage.covered,cues.length);
});

// r24: the model may repeatedly fail to obey multi-row JSON, while a direct
// one-sentence translation request produces usable Chinese without IDs.
test('r24 translation automatically switches to single-utterance plain Chinese instead of stopping',async()=>{
 const turns=Array.from({length:8},(_,i)=>({id:'turn-'+i,text:'Tengo '+(i+10)+' preguntas.',records:[cue(i,'Tengo '+(i+10)+' preguntas.')]}));
 const calls=[];
 const out=await C.translateTranscriptBatch(turns,async(rows,attempt,request)=>{
   calls.push({ids:rows.map(r=>r.id),mode:request?.mode,attempt});
   if(request?.mode==='plain')return '我有'+rows[0].text.match(/\d+/)[0]+'个问题。';
   return JSON.stringify({turns:[]});
 },{allowSourceFallback:true,save:async()=>{}});
 assert.equal(out.held.length,0);
 assert.ok(calls.some(x=>x.mode==='plain'&&x.ids.length===1));
 assert.equal(out.turns.length,8);
 assert.ok(out.turns.every(t=>t.translated&&t.text.startsWith('我有')));
 assert.deepEqual(out.turns.map(t=>t.id),turns.map(t=>t.id));
});

test('r24 irrecoverable translator outputs do not block the entire document or claim the source was translated',async()=>{
 const turns=[{id:'t1',text:'Tengo 3 preguntas.',records:[]},{id:'t2',text:'Tengo 7 preguntas.',records:[]}];
 let checkpoint,requests=0;
 const result=await C.translateTranscriptBatch(turns,async()=>{requests++;return '{"turns":[';},
   {allowSourceFallback:true,save:async v=>{checkpoint=v;}});
 assert.equal(result.turns.length,2);
 assert.equal(result.held.length,2);
 assert.deepEqual(result.turns.map(x=>x.text),turns.map(x=>'〔未译原文：'+x.text+'〕'));
 assert.ok(result.turns.every(x=>x.translated===false&&x.translationFallback===true));
 assert.deepEqual(checkpoint.sourceFallbackIds,['t1','t2']);
 assert.ok(requests<=8);
 const resumed=await C.translateTranscriptBatch(turns,async()=>{throw Error('completed fallback must be reused');},
   {allowSourceFallback:true,previous:checkpoint});
 assert.deepEqual(resumed.held.map(x=>x.id),['t1','t2']);
});

test('r24 old r23 maxed-out attempts are reset while retaining previously valid translations',async()=>{
 const turns=[{id:'a',text:'Hola.',records:[]},{id:'b',text:'Adios.',records:[]}];
 let called=[];
 const result=await C.translateTranscriptBatch(turns,async rows=>{called.push(rows.map(x=>x.id));return JSON.stringify({turns:rows.map(x=>({id:x.id,text:'再见。'}))});},
   {allowSourceFallback:true,previous:{turns:[{id:'a',text:'你好。'}],attempts:{a:4,b:4},ids:['a','b']}});
 assert.deepEqual(called,[['b']]);
 assert.deepEqual(result.turns.map(x=>x.text),['你好。','再见。']);
});

test('r24 plain-mode validator does not accept numerical hallucination as a Chinese translation',()=>{
 const turns=[{id:'turn-0',text:'Tengo 3 preguntas.',records:[]}];
 const bad=C.inspectTranscriptTranslation('我有4个问题。',turns,{mode:'plain'});
 assert.equal(bad.turns.length,0);assert.equal(bad.missing.length,1);
 const good=C.inspectTranscriptTranslation('翻译：我有3个问题。',turns,{mode:'plain'});
 assert.equal(good.turns.length,1);assert.equal(good.turns[0].translated,true);
});

test('r24 short video finishes with source retained when every translation request is invalid, no manual gate',async()=>{
 const h=makeHarness({fetch:async(url,opts)=>{
  if(url.endsWith('/api/tags'))return Response.json({models:[{name:'qwen2.5:3b'}]});
  const user=JSON.parse(opts.body).messages[1].content;
  if(user.includes('<transcript_translation_data>')||user.includes('<transcript_translation_single>'))return reply('{"turns":[');
  if(user.includes('整理方式：文字稿')){
    const rows=JSON.parse(user.slice(user.indexOf('{'))).turns;
    return reply(JSON.stringify({turns:rows.map(x=>({id:x.id,text:x.text}))}));
  }
  throw Error('unexpected request');
 }});
 const r=await h.send({type:'VKN_AI_GENERATE',cues:[cue(0,spanish)],writing:{mode:'transcript'}});
 assert.equal(r.ok,true,r.error);
 assert.match(r.data.markdown,/Si tuviéramos/);
 assert.match(r.data.audit.notes.join(' '),/自动补译|保留原文/);
 assert.doesNotMatch(r.data.audit.notes.join(' '),/已将 1 个外语文字片段逐条翻译/);
});

test('r24 resumable long transcript accepts automatic single-row repair after repeated incomplete JSON',async()=>{
 const key='yt:r24-automatic-translation',storeKey='vkn:session:'+encodeURIComponent(key);
 let calls=0,plain=0;
 const h=makeHarness({store:{[storeKey]:{key,url:'https://www.youtube.com/watch?v=r24-automatic-translation',segments:[]}},fetch:async(url,opts)=>{
  if(url.endsWith('/api/tags'))return Response.json({models:[{name:'qwen2.5:3b'}]});
  const user=JSON.parse(opts.body).messages[1].content;
  if(user.includes('<transcript_translation_data>')){calls++;return reply(JSON.stringify({turns:[]}));}
  if(user.includes('<transcript_translation_single>')){calls++;plain++;return reply('这是该段发言的中文翻译，保留完整含义。');}
  if(user.includes('整理方式：文字稿')){
   const rows=JSON.parse(user.slice(user.indexOf('{'))).turns;
   return reply(JSON.stringify({turns:rows.map(t=>({id:t.id,text:t.text}))}));
  }
  throw Error('unexpected model request');
 }});
 const cues=[cue(0,'hola mucho texto. '.repeat(3),{readingBoundary:true}),cue(1,'hola mucho texto. '.repeat(3),{readingBoundary:true}),cue(2,'hola mucho texto. '.repeat(3),{readingBoundary:true}),
  cue(3,'这是一段原本已经用中文记录的视频内容。'.repeat(400),{language:'zh',translationStatus:'off',needsReview:false,readingBoundary:true})];
 let r=await h.send({type:'VKN_AI_GENERATE',sessionKey:key,meta:{sessionKey:key},cues,writing:{mode:'transcript'}});
 let steps=0;
 while(r.ok&&r.data?.continuing){
  assert.ok(++steps<240,'resumable translation should terminate with finite requests');
  r=await h.send({type:'VKN_AI_GENERATE',requestId:r.data.requestId,sessionKey:key,resumeOnly:true});
 }
 assert.equal(r.ok,true,r.error);
 assert.ok(plain>0);assert.ok(calls>=plain);
 assert.match(r.data.markdown,/中文翻译/);
 assert.doesNotMatch(r.data.markdown,/hola mucho/);
 assert.equal(r.data.coverage.covered,4);
 assert.doesNotMatch(r.data.audit.notes.join(' '),/无可用中文译文/);
});

test('r24 long transcript completes with audited original sentences if translator never produces Chinese',async()=>{
 const key='yt:r24-foreign-source-retained',storeKey='vkn:session:'+encodeURIComponent(key);
 const h=makeHarness({store:{[storeKey]:{key,url:'https://www.youtube.com/watch?v=r24-foreign-source-retained',segments:[]}},fetch:async(url,opts)=>{
  if(url.endsWith('/api/tags'))return Response.json({models:[{name:'qwen2.5:3b'}]});
  const user=JSON.parse(opts.body).messages[1].content;
  if(user.includes('<transcript_translation_data>'))return reply('{"turns":[');
  if(user.includes('<transcript_translation_single>'))return reply('Hola:');
  if(user.includes('整理方式：文字稿')){
   const rows=JSON.parse(user.slice(user.indexOf('{'))).turns;
   return reply(JSON.stringify({turns:rows.map(t=>({id:t.id,text:t.text}))}));
  }
  throw Error('unexpected request');
 }});
 const cues=[cue(0,'hola mundo. '.repeat(3),{readingBoundary:true}),cue(1,'hola mundo. '.repeat(3),{readingBoundary:true}),
  cue(2,'这段中文不需要翻译。'.repeat(400),{language:'zh',translationStatus:'off',needsReview:false,readingBoundary:true})];
 let r=await h.send({type:'VKN_AI_GENERATE',sessionKey:key,meta:{sessionKey:key},cues,writing:{mode:'transcript'}});
 let steps=0;
 while(r.ok&&r.data?.continuing){
  assert.ok(++steps<200,'retry and fallback must be finite');
  r=await h.send({type:'VKN_AI_GENERATE',requestId:r.data.requestId,sessionKey:key,resumeOnly:true});
 }
 assert.equal(r.ok,true,r.error);
 assert.match(r.data.markdown,/hola mundo/);
 assert.match(r.data.audit.notes.join(' '),/无可用中文译文/);
 assert.equal(r.data.coverage.covered,3);
});

// r25 regression: the reported real-world failure contains an entire Spanish
// introduction followed by a Chinese suffix. r24 counted Han characters and
// incorrectly accepted it as a completed translation.
const sergioSpanish='Sergio Marina, doctora y filosofía, terapeuta transpersonal, experto en estados expandidos de conciencia, lleva más de 20 años guiando a miles de personas.';
const sergioMixed='Sergio Marina, doctora y filosofía, terapeuta transpersonal, experto en estados expandidos de conciencia, lleva más de 20 años guiando数以千计的人已经康复了深邃地整合身心灵。';
const sergioChinese='塞尔吉奥·马里纳（Sergio Marina）是一位哲学博士、超个人心理治疗师，也是意识扩展状态方面的专家，已有超过20年指导数千人的经验。';

test('r25 rejects a long Spanish passage with a small Chinese suffix, but allows Sergio Marina as a proper name',()=>{
 const turn={id:'sergio',text:sergioSpanish,records:[cue(0,sergioSpanish)]};
 const bad=C.inspectTranscriptTranslation(JSON.stringify({turns:[{id:'sergio',text:sergioMixed}]}),[turn]);
 assert.deepEqual(bad.turns,[]);assert.equal(bad.missing.length,1);assert.match(bad.reason,/untranslated/);
 const good=C.inspectTranscriptTranslation(JSON.stringify({turns:[{id:'sergio',text:sergioChinese}]}),[turn]);
 assert.equal(good.turns.length,1);assert.equal(good.missing.length,0);
 const tooShort=C.inspectTranscriptTranslation(JSON.stringify({turns:[{id:'long',text:'已翻译。'}]}),
  [{id:'long',text:'En esta situación diferentes personas consideran varias posibilidades y también ofrecen diferentes argumentos y experiencias para entender cómo funciona la conciencia y por qué cambian nuestras decisiones en distintos momentos de la vida cotidiana.',records:[]}]);
 assert.deepEqual(tooShort.turns,[]);
});

test('r25 recovers immutable ASR original when a done-marked Chinese candidate is visibly mixed',()=>{
 const asr=cue(0,sergioMixed,{original:sergioSpanish,text:sergioMixed,translationStatus:'done',needsReview:false});
 const chosen=C.transcriptInputCues([asr]);
 assert.equal(asr.text,sergioMixed,'source cue remains immutable');
 assert.equal(chosen[0].text,sergioSpanish);
 assert.equal(chosen[0].translationStatus,'needs_review');
 const turn=C.readingTurns(chosen)[0];
 assert.equal(turn.text,sergioSpanish);assert.equal(C.transcriptNeedsTranslation(turn),true);
 const correctlyDone=cue(0,sergioChinese,{original:sergioSpanish,text:sergioChinese,translationStatus:'done',needsReview:false});
 assert.equal(C.transcriptInputCues([correctlyDone])[0],correctlyDone);
 assert.equal(C.transcriptNeedsTranslation(C.readingTurns([correctlyDone])[0]),false);
});

test('r25 discards r24 mixed-language cached successes and retries r24 source fallbacks automatically',async()=>{
 const turns=[{id:'sergio',text:sergioSpanish,records:[cue(0,sergioSpanish)]},
              {id:'other',text:'Tengo 3 preguntas.',records:[cue(1,'Tengo 3 preguntas.')]}];
 const calls=[];
 const result=await C.translateTranscriptBatch(turns,async rows=>{
   calls.push(rows.map(x=>x.id));
   return JSON.stringify({turns:rows.map(row=>({id:row.id,text:row.id==='sergio'?sergioChinese:'我有3个问题。'}))});
 },{allowSourceFallback:true,previous:{strategyVersion:2,
      turns:[{id:'sergio',text:sergioMixed}],sourceFallbackIds:['other'],attempts:{sergio:4,other:4}}});
 assert.deepEqual(calls,[['sergio','other']]);
 assert.deepEqual(result.held,[]);
 assert.equal(result.turns[0].text,sergioChinese);
 assert.equal(result.turns[1].text,'我有3个问题。');
});

test('r25 never glues a foreign fallback and a Chinese unit into the same word',()=>{
 const original={id:'speaker-turn',text:'guiando a miles de personas y otras experiencias',label:'说话人2'};
 const units=[{...original,id:'speaker-turn-part-0',parentId:'speaker-turn',charStart:0,text:'guiando a miles de personas',translated:false},
   {...original,id:'speaker-turn-part-1',parentId:'speaker-turn',charStart:26,text:'许多人得到了指导。',translated:true}];
 const merged=C.mergePunctuationUnits([original],units);
 assert.match(merged[0].text,/personas\n许多人/);
 assert.doesNotMatch(merged[0].text,/personas许多人/);
});

test('r25 short transcript automatically rejects a partly Spanish AI response and completes a full Chinese retry',async()=>{
 let attempts=0;
 const h=makeHarness({fetch:async(url,opts)=>{
   if(url.endsWith('/api/tags'))return Response.json({models:[{name:'qwen2.5:3b'}]});
   const user=JSON.parse(opts.body).messages[1].content;
   if(user.includes('<transcript_translation_data>')||user.includes('<transcript_translation_single>')){
     assert.match(user,/a miles de personas/,'retry from full original source');
     attempts++;
     return reply(JSON.stringify({turns:[{id:'turn-0',text:attempts===1?sergioMixed:sergioChinese}]}));
   }
   if(user.includes('整理方式：文字稿')){
     const rows=JSON.parse(user.slice(user.indexOf('{'))).turns;
     return reply(JSON.stringify({turns:rows.map(r=>({id:r.id,text:r.text}))}));
   }
   throw Error('unexpected test request');
 }});
 const c=cue(0,sergioMixed,{original:sergioSpanish,translationStatus:'done',needsReview:false});
 const out=await h.send({type:'VKN_AI_GENERATE',cues:[c],writing:{mode:'transcript'}});
 assert.equal(out.ok,true,out.error);assert.equal(attempts,2);
 assert.match(out.data.markdown,/塞尔吉奥·马里纳/);
 assert.doesNotMatch(out.data.markdown,/doctora y filosofía|guiando数/);
});

test('r25 longform regenerates old punctuation shards after a cached r24 translation is repaired',async()=>{
 const key='yt:r25-transcript-repair',storeKey='vkn:session:'+encodeURIComponent(key);
 let repairEnabled=false,translationCalls=0,punctuationCalls=0;
 const h=makeHarness({store:{[storeKey]:{key,url:'https://www.youtube.com/watch?v=r25-transcript-repair',segments:[]}},fetch:async(url,opts)=>{
   if(url.endsWith('/api/tags'))return Response.json({models:[{name:'qwen2.5:3b'}]});
   const user=JSON.parse(opts.body).messages[1].content;
   if(user.includes('<transcript_translation_data>')||user.includes('<transcript_translation_single>')){
     translationCalls++;
     if(user.includes('<transcript_translation_single>'))return reply(repairEnabled?sergioChinese:sergioMixed);
     const rows=parseTagged(user,'transcript_translation_data').turns;
     return reply(JSON.stringify({turns:rows.map(r=>({id:r.id,text:repairEnabled?sergioChinese:sergioMixed}))}));
   }
   if(user.includes('整理方式：文字稿')){
     punctuationCalls++;
     const rows=JSON.parse(user.slice(user.indexOf('{'))).turns;
     return reply(JSON.stringify({turns:rows.map(r=>({id:r.id,text:r.text}))}));
   }
   throw Error('unexpected longform request');
 }});
 const c=cue(0,sergioMixed,{original:sergioSpanish,translationStatus:'done',needsReview:false,readingBoundary:true});
 const chinese=cue(1,'下面是完全使用中文记录的原始语音资料，其中包含明确的停顿和句子。'.repeat(160),
   {language:'zh',translationStatus:'off',needsReview:false,readingBoundary:true,speakerStatus:'overlap',speakerId:''});
 const cues=[c,chinese];
 async function run(){
   let r=await h.send({type:'VKN_AI_GENERATE',sessionKey:key,meta:{sessionKey:key},cues,writing:{mode:'transcript'}});
   let steps=0;
   while(r.ok&&r.data?.continuing){assert.ok(++steps<100,'bounded longform continuation');
     r=await h.send({type:'VKN_AI_GENERATE',requestId:r.data.requestId,sessionKey:key,resumeOnly:true});}
   return r;
 }
 const first=await run();assert.equal(first.ok,true,first.error);
 assert.match(first.data.markdown,/doctora y filosofía/);
 const translations=Object.keys(h.state).filter(k=>k.endsWith(':units:translation-0'));
 const punct=Object.keys(h.state).filter(k=>k.endsWith(':units:punct-0'));
 assert.equal(translations.length,1);assert.equal(punct.length,1);
 assert.match(h.state[punct[0]].turns[0].text,/doctora y filosofía/);
 // Simulate the exact r24 persisted schema and previously approved partial row.
 h.state[translations[0]].strategyVersion=2;
 h.state[translations[0]].turns=[{id:'turn-0',text:sergioMixed}];
 const previousPunctuationCalls=punctuationCalls;
 repairEnabled=true;
 const second=await run();assert.equal(second.ok,true,second.error);
 assert.match(second.data.markdown,/塞尔吉奥·马里纳/);
 assert.doesNotMatch(second.data.markdown,/doctora y filosofía/);
 assert.ok(punctuationCalls>previousPunctuationCalls,'stale punctuation must regenerate');
 assert.ok(translationCalls>=5);
});
