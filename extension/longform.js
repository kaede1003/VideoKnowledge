/* Durable, bounded long-form writing plan. Sources are not modified or filtered. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.VknLongform=api;})(globalThis,function(){
 'use strict';
 const VERSION=3, INPUT_BUDGET=1550, MAP_OUTPUT=600, BODY_OUTPUT=1300;
 function estimateTokens(value){const s=String(value||'');let cjk=0,others=0;for(const ch of s){if(/[\u2e80-\u9fff\uf900-\ufaff]/.test(ch))cjk++;else others++;}return Math.ceil(cjk*1.45+others/2.8)+8;}
 function hash(value){let a=2166136261,b=0x9e3779b9;for(let i=0;i<value.length;i++){const k=value.charCodeAt(i);a=Math.imul(a^k,16777619);b=Math.imul(b^(k+i),2246822519);}return (a>>>0).toString(16).padStart(8,'0')+(b>>>0).toString(16).padStart(8,'0');}
 function fingerprint(cues,options,model,kind='longform'){
  let data=JSON.stringify([VERSION,kind,options,model,cues.length]);
  for(const c of cues)data+='|'+JSON.stringify([c.id||'',c.time,c.end??'',c.speakerId||'',c.text,c.original||'',c.translation||'',c.language||'',c.translationStatus||'',c.needsReview||false,c.manuallyEdited||false,c.manualText||'',c.contextText||'',c.captionReview?.text||'']);
  return hash(data)+'-'+cues.length+'-'+data.length;
 }
 function safeParts(line,budget){
  if(estimateTokens(line)<=budget)return [line];
  const result=[];let rest=line;
  while(rest){
   let lo=1,hi=rest.length,cut=1;
   while(lo<=hi){const mid=Math.floor((lo+hi)/2);if(estimateTokens(rest.slice(0,mid))<=budget){cut=mid;lo=mid+1;}else hi=mid-1;}
   if(cut<rest.length){const search=rest.slice(0,cut),m=[...search.matchAll(/[。！？；!?;\n，,。]/g)].pop();if(m?.index!=null&&m.index>=Math.floor(cut*.55))cut=m.index+m[0].length;}
   if(cut<rest.length&&/[\uD800-\uDBFF]/.test(rest[cut-1]))cut--;
   if(cut<1)cut=1;
   result.push(rest.slice(0,cut));rest=rest.slice(cut);
  }
  return result;
 }
 function chunks(cues,lineOf,budget=INPUT_BUDGET){
  if(!Number.isInteger(budget)||budget<60||budget>20000)throw Error('invalid input budget');
  const out=[];let text='',ids=[],start=0,end=0,pieces=0;
  const flush=()=>{if(text){out.push({index:out.length,text,ids,start,end,pieces,tokens:estimateTokens(text)});text='';ids=[];pieces=0;}};
  for(let i=0;i<cues.length;i++){
   const cue=cues[i],line=String(lineOf(cue)||''),parts=safeParts(line,budget-10),id=String(cue.id||'at-'+i),t=Number(cue.time)||0;
   for(const part of parts){if(text&&estimateTokens(text+'\n'+part)>budget)flush();if(!text)start=t;text+=(text?'\n':'')+part;end=Number.isFinite(Number(cue.end))?Number(cue.end):t;
    if(ids[ids.length-1]!==id)ids.push(id);pieces++;}
  }
  flush();return out;
 }
 function grouped(items,budget,field='text'){
  const out=[];let group=[],tokens=0;
  for(const item of items){const count=estimateTokens(item[field]);if(group.length&&tokens+count>budget){out.push(group);group=[];tokens=0;}
   group.push(item);tokens+=count;
  }if(group.length)out.push(group);return out;
 }
 // Pairwise fallback prevents one-output-per-input deadlocks when a model
 // produces long summaries that cannot be packed into a normal token group.
 // It does not discard any input item or bypass the final source coverage check.
 function paired(items){const out=[];for(let i=0;i<items.length;i+=2)out.push(items.slice(i,i+2));return out;}
 function reductionGroups(items,budget,field='text'){
  const groups=grouped(items,budget,field);
  return groups.length>=items.length&&items.length>1?paired(items):groups;
 }
 function continuationSafeGroups(items,budget,field='text'){
  // Never feed an arbitrary-size single section into the model: report to the
  // caller that compaction would exceed the model input budget.
  for(const item of items)if(estimateTokens(item[field])>budget)throw Error('AI_SYNTHESIS_INPUT_TOO_LARGE：模型返回的单个主题片段过长，已保存草稿，请使用更短的模型输出。');
  return reductionGroups(items,budget,field);
 }
 // Retry a clipped model response with smaller ORIGINAL input, not a growing
 // continuation tail. Split at a nearby sentence/line boundary where possible;
 // never drop characters, change cue IDs or split a surrogate pair.
 function splitForRetry(material,minTokens=180){
  const text=String(material||'');
  if(estimateTokens(text)<minTokens*2||text.length<2)return null;
  const mid=Math.floor(text.length/2),low=Math.max(1,Math.floor(text.length*.35)),high=Math.min(text.length-1,Math.ceil(text.length*.65));
  let cut=mid,best=Infinity;
  for(let i=low;i<=high;i++){
   if(/[\n。！？；!?;，,]/.test(text[i-1])){
    const distance=Math.abs(i-mid);
    if(distance<best){cut=i;best=distance;}
   }
  }
  if(/[\uD800-\uDBFF]/.test(text[cut-1]))cut--;
  if(cut<=0||cut>=text.length)return null;
  return [text.slice(0,cut),text.slice(cut)];
 }
 function fingerprintSnapshot(snapshot){return fingerprint(snapshot.cues,snapshot.writing,snapshot.model,snapshot.kind||'longform');}
 function contentKey(sessionKey,fp){return 'vkn:longform:'+hash(sessionKey)+'-'+fp;}
 function state(key,fp,mode,model,count){return {schema:VERSION,key,fp,mode,model,count,createdAt:new Date().toISOString(),updatedAt:new Date().toISOString(),phase:'prepare',units:{},chapters:{},hierarchy:{},consolidations:{},continuations:{},completed:false};}
 function checkState(s,{key,fp,mode,model,count}){return !!s&&s.schema===VERSION&&s.key===key&&s.fp===fp&&s.mode===mode&&s.model===model&&s.count===count&&!s.completed;}
 function continuationPrompt({system,user,previous,tail}){return {system,user:user+'\n<existing_written_tail context="only, do not repeat">\n'+String(tail||previous||'').slice(-550)+'\n</existing_written_tail>\n请从上一输出中断的位置继续，仅返回未输出的后续正文；不要重复开头或已完成句子。'};}
 function joinContinuation(before,after){const prev=String(before||''),next=String(after||'');if(!prev)return next;if(!next)return prev;
  let overlap=0;for(let n=Math.min(400,prev.length,next.length);n>=4;n--){if(prev.slice(-n)===next.slice(0,n)){overlap=n;break;}}
  return prev+next.slice(overlap);
 }
 function headingGlue(chapters){let out='';for(const item of chapters){const text=String(item||'').trim();if(!text)continue;out+=(out?'\n\n':'')+text;}return out.replace(/\n{4,}/g,'\n\n\n');}
 function coverage(expected,chunksDone){const have=new Map(),missing=[];for(const c of chunksDone)for(const id of c.ids||[])have.set(id,(have.get(id)||0)+1);for(const id of expected)if(!have.has(id))missing.push(id);return {total:expected.length,covered:expected.length-missing.length,missing};}
 return {VERSION,INPUT_BUDGET,MAP_OUTPUT,BODY_OUTPUT,estimateTokens,hash,fingerprint,safeParts,splitForRetry,chunks,grouped,paired,reductionGroups,continuationSafeGroups,fingerprintSnapshot,contentKey,state,checkState,continuationPrompt,joinContinuation,headingGlue,coverage};
});
