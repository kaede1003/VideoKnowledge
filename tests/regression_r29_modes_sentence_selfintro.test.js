'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const C=require('../extension/core.js');
const I=require('../extension/speaker-identity.js');
const SID='a'.repeat(32);
const a=SID+':spk1',b=SID+':spk2';
const cue=(i,text,speakerId=a,extra={})=>({id:SID+':1:'+i,time:i*2,end:i*2+1.5,contextEpoch:0,speakerId,speakerStatus:'estimated',language:'zh',text,original:text,...extra});

test('r29 removes new novel and script modes but reads old documents unchanged',()=>{
 assert.deepEqual(Object.keys(C.WRITING_MODES),['knowledge','transcript','custom']);
 assert.equal(C.normalizeWriting({mode:'script'}).mode,'knowledge');
 assert.equal(C.normalizeWriting({mode:'novel'}).mode,'knowledge');
 const ui=fs.readFileSync(path.join(__dirname,'../extension/content.js'),'utf8');
 assert.doesNotMatch(ui,/<option value="(?:script|novel)">/);
 const old={key:'yt:x',title:'旧版',documents:[{id:'old-script',mode:'script',options:{mode:'script'},markdown:'## 第一幕\n\n旧剧本',createdAt:'2026-11-09'}]};
 assert.match(C.resultMarkdown(old),/剧本/);
 assert.match(C.resultMarkdown(old),/旧剧本/);
});

test('r29 self introduction names own voice in transcription without invoking another model',()=>{
 const turns=C.readingTurns([cue(0,'大家好，我是社长。'),cue(1,'今天我们开始讲述。'),cue(2,'另一位讲述者来解释。',b)]);
 const names=I.labelIntroducedSpeakers(turns);
 assert.equal(names[0].label,'社长');
 assert.equal(names[1].label,'说话人2');
 assert.match(C.formatTranscriptTurns(names),/\*\*社长\*\*/);
 assert.doesNotMatch(C.formatTranscriptTurns(names),/根据介绍推测/);
});

test('r29 self introduction extracts Chinese, English and Spanish names but not roles or third-person quotes',()=>{
 for(const [s,name] of [['大家好，我叫小雨，欢迎来到频道。','小雨'],['我的名字叫玛丽安。','玛丽安'],['我是主持人玛丽安，今天欢迎嘉宾。','玛丽安'],['Hi, my name is Sergio Marina.','Sergio Marina'],['Me llamo Sergio Marina.','Sergio Marina']])assert.equal(I.extractSelfIntroduction(s),name,s);
 for(const s of ['我是主持人。','我是一个普通人。','他说：“我叫小雨”。','主持人说我叫小雨。','我是来自地球的朋友。'])assert.equal(I.extractSelfIntroduction(s),'',s);
});

test('r29 deterministic self-naming emits evidence and does not rename other voice',()=>{
 const records=I.lines([cue(0,'大家好，我是社长。'),cue(1,'今天我们讲一些事。'),cue(2,'谢谢邀请。',b)]);
 const props=I.inferSelfIntroductions(records);
 assert.equal(props.length,1);
 assert.equal(props[0].speakerId,a);
 assert.equal(props[0].name,'社长');
 const accepted=I.validate(records,props).accepted;
 assert.equal(accepted.length,1);
 assert.equal(I.resolve({accepted,held:[]}).names[a],'社长');
 assert.equal(I.resolve({accepted,held:[]}).names[b],undefined);
});

test('r29 sentence reconciliation reconnects broken conditional clauses preserving every source word',()=>{
 const input='等军方拿出武器，再打不赢。行的话，再请另外一支力量救场。';
 const output=C.reconcileTranscriptSentenceFlow(input);
 assert.ok(!output.includes('不赢。行的话'),output);
 assert.equal(C.transcriptContentSignature(output),C.transcriptContentSignature(input));
 assert.equal(C.sentenceLines(output).length,1);
 assert.deepEqual(C.sentenceLines('如果。条件满足了，就开始。'),['如果，条件满足了，就开始。']);
});

test('r29 does not combine different people, questions or finished short acknowledgements',()=>{
 assert.deepEqual(C.sentenceLines('真的吗？是的。我们明天见。'),['真的吗？','是的。','我们明天见。']);
 const turns=C.readingTurns([cue(0,'就这样。'),cue(1,'的话我们继续。',b)]);
 const labeled=I.labelIntroducedSpeakers(turns);
 assert.equal(labeled.length,2);
 assert.match(C.formatTranscriptTurns(labeled),/就这样。[\s\S]*\*\*说话人2\*\*/);
});

test('r29 punctuation requests include adjacent unit context without exposing it as output rows',()=>{
 const turns=C.readingTurns([cue(0,'这是一句很长的话。还有后面的部分。')]);
 const units=C.punctuationUnits(turns,8);
 assert.ok(units.some(x=>x.contextBefore||x.contextAfter));
 const prompt=C.transcriptPunctuationPrompt(units.slice(1,2));
 assert.match(prompt.user,/context_before|context_after/);
 assert.match(prompt.system,/只修改.*text/);
});
