/* 0.10 replaces the retired filtering behavior. Old exclusion tests are intentionally
 * superseded, not counted as passes: no classification or exclusion may still run. */
'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const C=require('../extension/core'),{makeHarness}=require('./ai_harness');
const sid='f'.repeat(32),legacy={enabled:true,topic:'只保留主题',semantic:true};
function cue(text,i=1,extras={}){return {id:sid+':'+i+':0',revision:1,time:i*6,end:i*6+5,text,original:text,source:'local-asr',...extras};}
const rows=[cue('宪教设计的时候 '.repeat(19)),cue('嗯嗯嗯',2),cue('请上我们的官方网站报名。',3),cue('我不同意这个观点，需要举出反例。',4)];
test('filter switch cannot be revived by legacy saved settings',()=>{assert.deepEqual(C.normalizeFilter(legacy),{enabled:false,topic:'',semantic:false});});
test('all raw rows retained even with low score and old excludes',()=>{const data=rows.map(x=>({...x,filterOverride:'exclude',confidence:.1,needsReview:true})),copy=JSON.stringify(data),p=C.screeningCues(data,legacy);assert.equal(p.cues.length,4);assert.equal(p.stats.held,0);assert.equal(p.stats.excluded,0);assert.equal(JSON.stringify(data),copy);});
test('legacy optional semantic classifier has no eligible jobs',()=>assert.equal(C.makeFilterReviewBatch(rows,legacy).items.length,0));
test('legacy classifier endpoint refuses without network calls',async()=>{const h=makeHarness(),r=await h.send({type:'VKN_FILTER_REVIEW',cues:rows,filter:legacy});assert.equal(r.ok,false);assert.match(r.error,/FILTER_REMOVED/);assert.equal(h.requests.length,0);});
test('classification output cannot restore exclusion',()=>assert.deepEqual(C.validateFilterReview('{"items":[]}',{}),{}));
test('five writing modes keep all input records regardless of old filter flags',()=>{for(const mode of Object.keys(C.WRITING_MODES)){const p=C.prepareWriting(rows,{mode,instructions:mode==='custom'?'按顺序记录':'',filter:legacy});assert.equal(p.cues.length,4);assert.equal(p.screening?.excluded||0,0);}});
test('manual edits remain independent from retired selection flags',()=>{const c=rows[0],s={segments:[c],textOverrides:{[c.id]:{text:'人工核对文字。'}},filterOverrides:{[c.id]:'exclude'}};assert.equal(C.cuesWithSpeakers(s)[0].text,'人工核对文字。');});
test('legacy filtering choices remain in audit only',()=>{const s={segments:rows,filterOverrides:{[rows[0].id]:'exclude'}};assert.equal(C.auditExport(s).filterOverrides[rows[0].id],'exclude');assert.equal(C.cuesWithSpeakers(s).length,4);});
test('service writes preserve original data and inert legacy choices',async()=>{const h=makeHarness(),s={key:'yt:legacy',segments:rows,filterOverrides:{[rows[0].id]:'exclude'}};assert.equal((await h.send({type:'VKN_SAVE_SESSION',session:s})).ok,true);await h.ctx.vknPersistAsr({sessionKey:s.key,data:{...rows[0],revision:2}});const r=await h.send({type:'VKN_GET_SESSION',key:s.key});assert.equal(r.data.segments.length,4);assert.equal(r.data.filterOverrides[rows[0].id],'exclude');assert.equal(r.data.contentFilter.enabled,false);});
test('model generation receives advertising and uncertainty rather than filtering them out',async()=>{const h=makeHarness(),r=await h.send({type:'VKN_AI_GENERATE',cues:rows,writing:{filter:legacy},meta:{title:'fixture'}});assert.equal(r.ok,true,r.error);const text=h.requests.filter(x=>x.opts.body).map(x=>x.opts.body).join('');assert.match(text,/官方网站/);assert.match(text,/宪教设计/);});
test('UI has no filtering controls or periodic classifier scheduling',()=>{const s=fs.readFileSync('extension/content.js','utf8');for(const bad of ['vkn-filter-enabled','vkn-filter-semantic','maybeFilterReview','不纳入整理'])assert.equal(s.includes(bad),false,bad);});
test('scores remain diagnostics, not a rejection criterion',()=>{assert.equal(C.cleanCue(cue('例句',1,{confidence:null})).confidence,undefined);assert.equal(C.assessCue(cue('低分例句',2,{confidence:0}),legacy).action,'include');});
