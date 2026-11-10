'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const C=require('../extension/core'),I=require('../extension/speaker-identity');
const sid='a'.repeat(32),host=sid+':spk2',guest=sid+':spk1';
function cue(i,text,extra={}){return {id:sid+':'+i+':0',time:i*2,end:i*2+1.2,text,original:text,language:'es',translationStatus:'off',needsReview:false,contextEpoch:0,speakerStatus:'estimated',speakerId:host,source:'local-asr',...extra};}
const mixed='Sergio Marina, doctora y filosofía, terapeuta transpersonal, experto en estados expandidos de conciencia, lleva más de 20 años guiando数以千计的人已经康复了深入地整合身心灵。';

test('r26 mixed transcript with no clean original is repairable by bounded short source units',async()=>{
 const turns=[{id:'turn-0',text:mixed,records:[cue(0,mixed)]}],requests=[];
 const result=await C.translateTranscriptBatch(turns,async(rows,tries,{mode}={})=>{
   requests.push({text:rows[0].text,id:rows[0].id,mode});
   if(!rows[0].id.includes('repair-'))return JSON.stringify({turns:[]});
   const t=rows[0].text;
   const zh=/Sergio Marina/.test(t)?'塞尔吉奥·马里纳是一位哲学博士、超个人心理治疗师和意识扩展领域的专家。':
      /lleva más/.test(t)?'他拥有超过20年的指导经验。':
      /experto/.test(t)?'他是意识扩展领域的专家。':'这段话已经完整翻译。';
   return zh;
 },{allowSourceFallback:true});
 assert.equal(result.held.length,0,'short-unit repair should recover all foreign parts');
 assert.ok(requests.some(r=>r.id.includes('repair-')),'must attempt smaller units');
 assert.ok(requests.length<22,'bounded model calls');
 assert.match(result.turns[0].text,/塞尔吉奥/);
 assert.doesNotMatch(result.turns[0].text,/doctora y filosofía|guiando数/);
 assert.match(result.turns[0].text,/数以千计/);
});

test('r26 revives exhausted r25 fallback without discarding a verified peer',async()=>{
 const turns=[{id:'a',text:'hola mundo',records:[cue(0,'hola mundo')]},{id:'b',text:mixed,records:[cue(1,mixed)]}];
 let requested=[];
 const r=await C.translateTranscriptBatch(turns,async rows=>{requested.push(rows.map(x=>x.id));return JSON.stringify({turns:rows.map(x=>({id:x.id,text:x.id==='b'?'这是对塞尔吉奥的介绍，他拥有超过20年的实践经验，曾经指导众多人。':'你好，世界。'}))});},
   {previous:{strategyVersion:3,turns:[{id:'a',text:'你好，世界。'}],sourceFallbackIds:['b'],attempts:{b:4}},allowSourceFallback:true});
 assert.deepEqual(requested,[['b']]);assert.equal(r.held.length,0);
 assert.equal(r.turns[0].text,'你好，世界。');
});

test('r26 short unassigned prefix is joined to the next different speaker only across a natural boundary',()=>{
 const cues=[cue(0,'上一位采访者的介绍已经结束。',{speakerId:host,speakerLabel:'说话人2'}),
   cue(1,'我们',{speakerId:'',speakerStatus:'uncertain',speakerLabel:'',language:'zh',time:1.4,end:1.7}),
   cue(2,'以前讨论过类似的问题。',{speakerId:guest,speakerLabel:'说话人1',language:'zh',time:1.8,end:3})];
 const turns=C.readingTurns(cues);
 assert.equal(turns.length,2);
 assert.equal(turns[1].speakerId,guest);
 assert.match(turns[1].text,/^我们以前讨论过/);
 assert.doesNotMatch(turns[0].text,/我们/);
 const withReply=[cue(1,'嗯',{speakerId:'',speakerStatus:'uncertain',time:1.4,end:1.7}),cues[2]];
 assert.equal(C.readingTurns(withReply)[0].speakerId,'','independent acknowledgements must not be guessed');
});

test('r26 introduces Sergio from the biography to the following interviewee, not the narrator',()=>{
 const intro='Sergio Marina, doctora y filosofía, terapeuta transpersonal, experto en estados expandidos de conciencia, lleva más de 20 años guiando personas.';
 assert.equal(I.biographicalIntroduction(intro),'Sergio Marina');
 const cues=[cue(0,intro,{speakerId:host}),cue(1,'Estamos aquí para compartir nuestras experiencias.',{speakerId:guest})];
 const records=I.lines(cues),candidate=I.inferBiographyNames(records);
 assert.equal(candidate.length,1);
 assert.equal(candidate[0].speakerId,guest);
 assert.equal(candidate[0].name,'Sergio Marina');
 assert.equal(I.validate(records,candidate).accepted.length,1);
 const turns=C.readingTurns(cues);
 const labeled=I.labelIntroducedSpeakers(turns);
 assert.match(labeled[1].label,/Sergio Marina/);
 assert.notEqual(labeled[0].label,labeled[1].label);
 assert.equal(I.biographicalIntroduction('Sergio Marina publicó un libro el año pasado.'),'');
 assert.deepEqual(I.inferBiographyNames(I.lines([cue(0,'Sergio Marina publicó un libro.',{speakerId:host}),cues[1]])),[]);
});

test('r26 fragment-repair checkpoint resumes without repeating a verified Spanish clause',async()=>{
 const {text}=C.transcriptRepairPieces(mixed)[0],turns=[{id:'t1',text:mixed,records:[cue(0,mixed)]}];
 let saved,acceptedFirst=0,asked=[];
 await assert.rejects(()=>C.translateTranscriptBatch(turns,async rows=>{
   asked.push(rows[0].id);
   if(rows[0].id==='t1')return JSON.stringify({turns:[]});
   if(rows[0].id==='t1-repair-0'){acceptedFirst++;return '塞尔吉奥·马里纳是一位哲学博士，也是超个人心理治疗师和意识扩展领域的专家。';}
   throw Error('AI_CONTINUE_REQUIRED：暂停，检查点保留');
 },{allowSourceFallback:true,maxAttempts:1,save:async x=>{saved=x;}}),/AI_CONTINUE_REQUIRED/);
 assert.equal(saved.strategyVersion,4);assert.equal(saved.repair.t1.done[0].valid,true);
 const resumed=await C.translateTranscriptBatch(turns,async rows=>{
   assert.equal(rows[0].id,'t1-repair-1');
   return '他已经拥有超过20年的指导经验。';
 },{previous:saved,allowSourceFallback:true,maxAttempts:1,save:async x=>{saved=x;}});
 assert.equal(acceptedFirst,1);assert.equal(resumed.held.length,0);
 assert.doesNotMatch(resumed.turns[0].text,/guiando|doctora y/);
 assert.match(resumed.turns[0].text,/数以千计/);
});

test('r26 real short transcript generator labels the introduced voice and merges the orphan prefix',async()=>{
 const {makeHarness}=require('./ai_harness');
 const source='Sergio Marina, doctora y filosofía, terapeuta transpersonal, experto en estados expandidos de conciencia, lleva más de 20 años guiando a miles de personas.';
 const transcript=[
  cue(0,source,{speakerId:host,speakerLabel:'说话人2',end:1.2}),
  cue(1,'我们',{speakerId:'',speakerStatus:'uncertain',speakerLabel:'',language:'zh',time:1.4,end:1.7}),
  cue(2,'曾经谈论过关于意识的问题。',{speakerId:guest,speakerLabel:'说话人1',language:'zh',time:1.8,end:3.3})
 ];
 const reply=text=>Response.json({choices:[{message:{content:text},finish_reason:'stop'}]});
 const h=makeHarness({fetch:async(url,options)=>{
  if(url.endsWith('/api/tags'))return Response.json({models:[{name:'qwen2.5:3b'}]});
  const user=JSON.parse(options.body).messages[1].content;
  if(user.includes('<transcript_translation_data>')){
   const rows=JSON.parse(user.match(/<transcript_translation_data>\s*([\s\S]*?)\s*<\/transcript_translation_data>/)[1]).turns;
   return reply(JSON.stringify({turns:rows.map(r=>({id:r.id,text:'塞尔吉奥·马里纳是一位哲学博士、超个人心理治疗师和意识扩展领域的专家，拥有超过20年的指导经验，曾帮助数千人。'}))}));
  }
  if(user.includes('整理方式：文字稿')){
   const rows=JSON.parse(user.slice(user.indexOf('{'))).turns;
   return reply(JSON.stringify({turns:rows.map(r=>({id:r.id,text:r.text}))}));
  }
  throw Error('unexpected model call');
 }});
 const r=await h.send({type:'VKN_AI_GENERATE',cues:transcript,writing:{mode:'transcript'}});
 assert.equal(r.ok,true,r.error);
 assert.match(r.data.markdown,/\*\*Sergio Marina\*\*/);
 assert.match(r.data.markdown,/我们曾经谈论过/);
 assert.doesNotMatch(r.data.markdown,/doctora y filosofía/);
 assert.equal((r.data.markdown.match(/我们/g)||[]).length,1);
});

test('r26 biographical guest name is persisted even when the local naming model fails',async()=>{
 const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),L=require('../extension/longform');
 const src=fs.readFileSync(path.join(__dirname,'../extension/identity-background.js'),'utf8');
 const session={speakerNames:{},speakerEvidence:{},speakerCandidates:[],captionObservations:[],segments:[
   cue(0,'Sergio Marina, doctora y filosofía, terapeuta transpersonal y experto en estados expandidos de conciencia.',{speakerId:host}),
   cue(1,'Es un placer estar aquí y compartir esta experiencia.',{speakerId:guest})
 ]};
 const store=new Map(),scope={globalThis:{},validKey:()=>true,loadSession:async()=>session,
   writeSession:async s=>Object.assign(session,s),notebookWrite:async fn=>fn(),
   VideoKnowledgeCore:{cuesWithSpeakers:()=>session.segments},VknSpeakerIdentity:I,VknLongform:L,
   VknCaptions:{cleanObservations:v=>v||[],evidenceFor:()=>[]},readAiConfig:async()=>({endpoint:'http://127.0.0.1:11434/v1/chat/completions'}),
   VknAiConfig:{isLocalOllama:()=>true},askModel:async()=>{throw Error('AI_HTTP_500: model unavailable');},
   chrome:{storage:{local:{get:async k=>({[k]:store.get(k)}),set:async v=>{for(const [k,x] of Object.entries(v))store.set(k,x);}}}},
   Date,Map,JSON,Error,console};
 vm.createContext(scope);vm.runInContext(src,scope);
 const result=await scope.vknIdentifySpeakers('yt:test');
 assert.equal(session.speakerNames[guest],'Sergio Marina');
 assert.equal(session.speakerNames[host],undefined,'the introducer is not the guest');
 assert.equal(result.updated,1);
});

test('r26 a genuinely unavailable translation remains explicitly annotated without a manual approval gate',async()=>{
 const turns=[{id:'t',text:mixed,records:[cue(0,mixed)]}];let calls=0;
 const result=await C.translateTranscriptBatch(turns,async()=>{calls++;return 'Sergio Marina ...';},{maxAttempts:1,allowSourceFallback:true});
 assert.ok(calls<=7,'at most one ordinary request and six bounded fragment requests');
 assert.equal(result.turns[0].translated,false);
 assert.equal(result.held.length,1);
 assert.match(result.turns[0].text,/〔未译原文：/);
 assert.match(result.turns[0].text,/Sergio Marina/);
 assert.doesNotMatch(result.turns[0].text,/^Sergio Marina/);
});
