'use strict';
// Synthetic 2h ASR feed: behavior/data-integrity only, not a claim about Windows FPS.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const C=require('../extension/core.js');
const sid='a'.repeat(32);
test('incremental two-hour ASR stream appends 3600 records without losing revisions',()=>{
 let cues=[],byId=new Map();
 for(let i=0;i<3600;i++){
   const datum={id:`${sid}:${i}:0`,time:i*2,end:i*2+1,text:`第${i}条关于主题和例证的发言`,original:`第${i}条关于主题和例证的发言`,revision:1,source:'local-asr'};
   const merged=C.mergeLiveCues(cues,[datum],byId);
   cues=merged.cues;byId=merged.index;
   assert.equal(merged.fresh.length,1);
 }
 assert.equal(cues.length,3600);
 assert.equal(byId.get(`${sid}:3599:0`),3599);
 const revised={...cues[1000],text:'修订后的原句',revision:2};
 const updated=C.mergeLiveCues(cues,[revised],byId);
 assert.equal(updated.cues.length,3600);
 assert.equal(updated.fresh.length,0);
 assert.equal(updated.cues[1000].text,'修订后的原句');
 assert.equal(updated.cues[3599].text,'第3599条关于主题和例证的发言');
});
test('pure metadata notices are not counted as forced human review; semantic risks still are',()=>{
 const metaOnly={id:`${sid}:1:0`,time:0,text:'普通听写',needsReview:true,qualityFlags:['word_timestamps_missing','correction_suggestion']};
 const severe={id:`${sid}:2:0`,time:2,text:'否定词冲突',needsReview:true,qualityFlags:['translation_suspect']};
 assert.equal(C.cueNeedsReview(metaOnly),false);
 assert.equal(C.cueNeedsReview(severe),true);
 assert.deepEqual(C.qualityCounts([metaOnly,severe]),{review:1,manual:0,total:2});
});
