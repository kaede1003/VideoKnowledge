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

test('short transcript refuses to publish raw foreign speech when translation output is invalid',async()=>{
 const h=makeHarness({fetch:async(url,opts)=>{
  if(url.endsWith('/api/tags'))return Response.json({models:[{name:'qwen2.5:3b'}]});
  const user=JSON.parse(opts.body).messages[1].content;
  if(user.includes('<transcript_translation_data>')){
   const data=parseTagged(user,'transcript_translation_data');
   return reply(JSON.stringify({turns:data.turns.map(t=>({id:t.id,text:t.text}))}));
  }
  throw Error('punctuation must not run after failed translation');
 }});
 const r=await h.send({type:'VKN_AI_GENERATE',cues:[cue(0,spanish)],writing:{mode:'transcript'}});
 assert.equal(r.ok,false);assert.match(r.error,/AI_TRANSLATION_UNTRANSLATED/);
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
 const first=await h.send({type:'VKN_AI_GENERATE',sessionKey:key,meta:{sessionKey:key},cues,writing:{mode:'transcript'}});
 assert.equal(first.ok,false);assert.match(first.error,/AI_HTTP_500/);assert.equal(translationCalls,2);
 const r=await h.send({type:'VKN_AI_GENERATE',sessionKey:key,meta:{sessionKey:key},cues,writing:{mode:'transcript'}});
 assert.equal(r.ok,true,r.error);assert.ok(translationCalls>2);assert.ok(translatedRows>10);assert.ok(punctuationCalls>=1);
 assert.match(r.data.markdown,/中文翻译内容/);assert.doesNotMatch(r.data.markdown,/hola mundo/);
 assert.match(r.data.audit.notes.join(' '),/翻译为简体中文/);assert.equal(r.data.coverage.covered,3);
});
