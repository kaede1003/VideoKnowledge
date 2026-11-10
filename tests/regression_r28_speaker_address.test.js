'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const I=require('../extension/speaker-identity'),C=require('../extension/core');
const SID='d'.repeat(32),host=SID+':spk3',guest=SID+':spk2',other=SID+':spk4';
const bio='Sergio Marina, doctora y filosofía, terapeuta transpersonal, experto en estados expandidos de conciencia.';
function turn(id,speakerId,text,start,end,label='说话人3'){
 return {id,speakerId,text,start,end,label,records:[],cueIds:[id],trusted:true};
}
function cue(i,speakerId,text,time=i*3){return {id:SID+':'+i+':0',speakerId,speakerStatus:'estimated',text,original:text,time,end:time+1.5,language:'zh',contextEpoch:0};}

test('r28 identifies both the biographical guest and the directly addressed host; display uses names without editorial suffix',()=>{
 const turns=[turn('0',host,bio,0,5,'说话人3'),
  turn('1',guest,'很高兴来到这里。',5.2,7,'说话人2'),
  turn('2',guest,'真的，非常感谢你，玛丽安，还有你可亲可爱的丈夫。',8,11,'说话人2'),
  turn('3',host,'谢谢你，我们从这里开始。',11.3,13,'说话人3')];
 const labeled=I.labelIntroducedSpeakers(turns);
 assert.equal(labeled[0].label,'玛丽安');
 assert.equal(labeled[1].label,'Sergio Marina');
 assert.equal(labeled[2].label,'Sergio Marina');
 assert.equal(labeled[3].label,'玛丽安');
 assert.doesNotMatch(C.formatTranscriptTurns(labeled),/根据介绍推测|说话人3/);
 assert.equal(turns[0].label,'说话人3','original turns are not mutated');
});

test('r28 refuses ambiguous vocative attribution and simple third-person references',()=>{
 const ambiguous=[turn('0',host,'上一句话。',0,3),turn('1',guest,'谢谢你，玛丽安。',3.1,4.5),
   turn('2',other,'让我说句话。',5,7,'说话人4')];
 assert.equal(I.labelIntroducedSpeakers(ambiguous)[0].label,'说话人3');
 const third=[turn('0',guest,'玛丽安去年出版了新书。',0,4),turn('1',host,'是这样。',4.1,6)];
 assert.equal(I.labelIntroducedSpeakers(third)[1].label,'说话人3');
});

test('r28 identity records admit an addressed interlocutor, not the speaker saying the name',()=>{
 const cues=[cue(0,host,bio,0),cue(1,guest,'很高兴来到这里。',2),
  cue(2,guest,'真的，非常感谢你，玛丽安，还有你可亲可爱的丈夫。',4),
  cue(3,host,'谢谢你，我们开始吧。',6)];
 const rows=I.lines(cues),addressed=I.inferAddressedNames(rows);
 assert.equal(addressed.length,1);
 assert.equal(addressed[0].speakerId,host);
 assert.equal(addressed[0].name,'玛丽安');
 assert.equal(I.validate(rows,addressed).accepted.length,1);
 const resolved=I.resolve({accepted:I.validate(rows,addressed).accepted,held:[]});
 assert.equal(resolved.names[host],'玛丽安');
 assert.equal(resolved.names[guest],undefined);
 assert.equal(C.cleanSpeakerEvidence({[host]:resolved.evidence[host]})[host].basis,'direct_address');
});

test('r28 translation prompt leakage is rejected and not reused from old completed checkpoints',async()=>{
 const source={id:'turn-0',text:'Gracias por estar aquí. 20 años.',records:[cue(1,guest,'Gracias por estar aquí. 20 años.') ]};
 const leaked='请把下面标签内的发言准确翻译成自然、完整的简体中文。不要抄原文、不要输出语言名称、不要附加说明。专有姓名可以保留原文，数字保持不变。20';
 const malformed=C.inspectTranscriptTranslation(JSON.stringify({turns:[{id:source.id,text:leaked}]}),[source]);
 assert.equal(malformed.turns.length,0);
 let calls=0;
 const r=await C.translateTranscriptBatch([source],async()=>{calls++;return JSON.stringify({turns:[{id:source.id,text:'感谢你来到这里。我已经有20年的经验。'}]});},{previous:{strategyVersion:4,turns:[{id:source.id,text:leaked}],attempts:{[source.id]:0}}});
 assert.equal(calls,1);
 assert.match(r.turns[0].text,/感谢你/);
 assert.doesNotMatch(r.turns[0].text,/标签内|不要抄原文/);
});

test('r28 legacy inferred label no longer prints explanatory tail',()=>{
 const md=C.formatTranscriptTurns([turn('t',guest,'这段话在字幕里。',1,2,'Sergio Marina（根据介绍推测）')]);
 assert.match(md,/\*\*Sergio Marina\*\*/);
 assert.doesNotMatch(md,/根据介绍推测/);
});

test('r28 translated Chinese vocative is anchored to its actual text, not an untranslatable Spanish original',()=>{
 const rows=I.lines([cue(0,host,bio,0),cue(1,guest,'在这里见到大家很开心。',2),
  {...cue(2,guest,'非常感谢你，玛丽安，还有你的丈夫。',4),original:'Quiero agradecer a todos los que nos acompañan.'},
  cue(3,host,'谢谢。',6)]);
 const addressed=I.inferAddressedNames(rows);
 assert.equal(addressed[0]?.name,'玛丽安');
 assert.equal(I.validate(rows,addressed).accepted.length,1);
});

test('r28 automatic speaker identity persists named host and guest when the model server is unavailable',async()=>{
 const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),L=require('../extension/longform');
 const source=fs.readFileSync(path.join(__dirname,'../extension/identity-background.js'),'utf8');
 const session={speakerNames:{},speakerEvidence:{},speakerCandidates:[],captionObservations:[],segments:[
  cue(0,host,bio,0),cue(1,guest,'Es un placer estar aquí.',2),cue(2,guest,'真的，非常感谢你，玛丽安，还有你可亲可爱的丈夫。',4),
  cue(3,host,'谢谢，你也辛苦了。',6)]};
 const storage=new Map(),scope={globalThis:{},validKey:()=>true,loadSession:async()=>session,
  writeSession:async s=>Object.assign(session,s),notebookWrite:async fn=>fn(),
  VideoKnowledgeCore:{cuesWithSpeakers:()=>session.segments},VknSpeakerIdentity:I,VknLongform:L,
  VknCaptions:{cleanObservations:v=>v||[],evidenceFor:()=>[]},readAiConfig:async()=>({endpoint:'http://127.0.0.1:11434/v1/chat/completions'}),
  VknAiConfig:{isLocalOllama:()=>true},askModel:async()=>{throw Error('AI_HTTP_500: offline');},
  chrome:{storage:{local:{get:async k=>({[k]:storage.get(k)}),set:async v=>{for(const [key,x] of Object.entries(v))storage.set(key,x);}}}},
  Date,Map,JSON,Error,console};
 vm.createContext(scope);vm.runInContext(source,scope);
 const result=await scope.vknIdentifySpeakers('yt:test');
 assert.equal(session.speakerNames[host],'玛丽安');
 assert.equal(session.speakerNames[guest],'Sergio Marina');
 assert.equal(session.speakerEvidence[host].basis,'direct_address');
 assert.equal(result.updated,2);
 const prior=storage.get('vkn:identity:'+L.hash('yt:test'));
 assert.equal(prior.schema,6);
});

test('r28 end-to-end transcript displays interview host and guest names with no guessed suffix',async()=>{
 const {makeHarness}=require('./ai_harness');
 const source=[cue(0,host,bio,0),
  {...cue(1,guest,'很高兴来到这里。',2),language:'zh'},
  {...cue(2,guest,'真的，非常感谢你，玛丽安，还有你可亲可爱的丈夫。',8),language:'zh'},
  {...cue(3,host,'谢谢，我们从这里开始。',10),language:'zh'}];
 const reply=text=>Response.json({choices:[{message:{content:text},finish_reason:'stop'}]});
 const h=makeHarness({fetch:async(url,opts)=>{
  if(url.endsWith('/api/tags'))return Response.json({models:[{name:'qwen2.5:3b'}]});
  const prompt=JSON.parse(opts.body).messages[1].content;
  if(prompt.includes('<transcript_translation_data>')){
   const rows=JSON.parse(prompt.match(/<transcript_translation_data>\s*([\s\S]*?)\s*<\/transcript_translation_data>/)[1]).turns;
   return reply(JSON.stringify({turns:rows.map(r=>({id:r.id,text:'塞尔吉奥·马里纳是一位哲学博士和超个人心理治疗师。'}))}));
  }
  if(prompt.includes('整理方式：文字稿')){
   const rows=JSON.parse(prompt.slice(prompt.indexOf('{'))).turns;
   return reply(JSON.stringify({turns:rows.map(r=>({id:r.id,text:r.text}))}));
  }
  throw Error('unexpected prompt: '+prompt.slice(0,100));
 }});
 const result=await h.send({type:'VKN_AI_GENERATE',cues:source,writing:{mode:'transcript'}});
 assert.equal(result.ok,true,result.error);
 assert.match(result.data.markdown,/\*\*玛丽安\*\*/);
 assert.match(result.data.markdown,/\*\*Sergio Marina\*\*/);
 assert.doesNotMatch(result.data.markdown,/根据介绍推测|请把下面标签内的发言/);
 assert.match(result.data.markdown,/真的，非常感谢你，玛丽安/);
});

test('r28 a general thank-you response is not misread as a Chinese personal name',()=>{
 assert.equal(I.directAddress('谢谢，你也辛苦了。'),'');
 assert.equal(I.directAddress('谢谢，我们一起开始。'),'');
 assert.equal(I.directAddress('谢谢，朋友。'),'');
 assert.equal(I.directAddress('谢谢，导演。'),'');
 assert.equal(I.directAddress('Gracias por participar.'),'');
 assert.equal(I.directAddress('Gracias, Mariana, eres increíble.'),'Mariana');
 assert.equal(I.directAddress('谢谢，玛丽安，还有你的丈夫。'),'玛丽安');
 assert.equal(I.directAddress('玛丽安出版了一本书。'),'');
});
