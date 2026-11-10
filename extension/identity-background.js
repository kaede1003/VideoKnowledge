/* Optional, local-only inference of character names grounded in timestamped speech/subtitles. */
'use strict';
const vknIdentityRunning=new Map();
const vknRoleCheckVersion=3;
async function vknClassifySpeakerRoles(sessionKey,cfg,snapshot,cues,options={}){
 // Voice identity originates in local acoustic embeddings; only role semantics
 // are inferred here. Never infer personal identity or use a remote API.
 const R=typeof VknSpeakerRole!=='undefined'?VknSpeakerRole:null;
 if(!R)return {roleUpdated:0,roleChecked:0};
 const groups=R.sample(cues);
 if(!groups.length)return {roleUpdated:0,roleChecked:0};
 const stateKey='vkn:roles:'+VknLongform.hash(sessionKey);
 const rawState=(await chrome.storage.local.get(stateKey))[stateKey];
 const checked=rawState?.version===vknRoleCheckVersion&&rawState.checked&&typeof rawState.checked==='object'?rawState.checked:{};
 const pending=groups.filter(group=>{
   const hash=VknLongform.hash(JSON.stringify(group.examples));
   const old=checked[group.speakerId];
   return !old || (old.hash!==hash && group.turnCount>=old.turnCount+3);
 });
 if(!pending.length)return {roleUpdated:0,roleChecked:0};
 let analyzed=0;const roles=[],held=[];
 for(const batch of R.batches(pending).slice(0,3)){
   if(options.signal?.aborted)break;
   const req=R.prompt(batch,{title:snapshot.title});let parsed;
   try{parsed=R.parse(await askModel(cfg,req.system,req.user,{signal:options.signal,maxTokens:1250,timeoutMs:45000}));}
   catch{break;}
   const value=R.validate(batch,parsed);
   roles.push(...value.accepted);held.push(...value.held);
   for(const entry of batch)checked[entry.speakerId]={hash:VknLongform.hash(JSON.stringify(entry.examples)),turnCount:entry.turnCount};
   analyzed+=batch.length;
 }
 if(!analyzed)return {roleUpdated:0,roleChecked:0};
 const resolved=R.resolve({accepted:roles,held},snapshot.speakerRoles||{});
 await notebookWrite(async()=>{
   const current=await loadSession(sessionKey);if(!current)return;
   const existing=VideoKnowledgeCore.cleanSpeakerRoles(current.speakerRoles||{});
   const merged={...existing};let acceptedCount=0;
   for(const [id,item] of Object.entries(resolved.roles)){
     if(!existing[id]||existing[id].role!==item.role||item.cueIds?.length>(existing[id].cueIds?.length||0)||(!existing[id].displayName&&item.displayName)){
       merged[id]=item;acceptedCount++;
     }
   }
   await writeSession({...current,speakerRoles:merged,speakerRoleCandidates:[...(current.speakerRoleCandidates||[]),...resolved.candidates].slice(-60)});
 });
 await chrome.storage.local.set({[stateKey]:{version:vknRoleCheckVersion,checked:Object.fromEntries(Object.entries(checked).slice(-200))}});
 return {roleUpdated:roles.length,roleChecked:analyzed};
}
async function vknIdentifySpeakers(sessionKey,options={}){
 if(!validKey(sessionKey))throw Error('VIDEO_ID_INVALID：视频标识无效。');
 if(vknIdentityRunning.has(sessionKey))return {busy:true};
 const operation=(async()=>{
  const C=VideoKnowledgeCore,I=VknSpeakerIdentity;
  const snapshot=await loadSession(sessionKey);if(!snapshot)return {updated:0,reason:'没有当前视频笔记'};
  let cfg;try{cfg=await readAiConfig();}catch{return {updated:0,reason:'文字模型尚未设置'};}
  if(!VknAiConfig.isLocalOllama(cfg.endpoint))return {updated:0,reason:'自动角色姓名推理只使用本地Ollama，未发送到远端'};
  const observations=VknCaptions.cleanObservations(snapshot.captionObservations);
  // Attach admissible synchronized caption labels BEFORE filtering for identity
  // candidates. A speaker may say a plain greeting while their name appears on
  // screen, so text-keyword-only filtering silently misses the strongest clue.
  const cues=C.cuesWithSpeakers(snapshot).map(c=>{
    const matched=VknCaptions.evidenceFor(c,observations).filter(o=>
      !['automatic','translated'].includes(o.kind) && Number(o.samples||0)>=2 &&
      Number(o.seenSpan||0)>=.25);
    const proof=matched.map(o=>o.text).filter(Boolean).join(' | ').slice(0,240);
    if(!proof)return c;
    return {...c,captionReview:{...(c.captionReview||{}),evidence:
      [c.captionReview?.evidence,proof].filter(Boolean).join(' | ').slice(0,240)}};
  });
  const roleResult=await vknClassifySpeakerRoles(sessionKey,cfg,snapshot,cues,options).catch(()=>({roleUpdated:0,roleChecked:0}));
  const records=I.lines(cues);
  if(!records.length)return {updated:0,...roleResult,reason:'尚未发现带可靠声音归属的姓名候选片段'};
  const stateKey='vkn:identity:'+VknLongform.hash(sessionKey);
  const prior=(await chrome.storage.local.get(stateKey))[stateKey];
  const checked=(prior?.schema===6 && prior?.checked && typeof prior.checked==='object')?prior.checked:{};
  const pending=records.filter(x=>checked[x.cueId]!==VknLongform.hash(JSON.stringify([x.text,x.original,x.subtitle,x.speakerId,x.contextBefore,x.contextAfter])));
  if(!pending.length)return {updated:0,...roleResult,checked:records.length,reason:'已有姓名证据均已检查'};
  const batches=I.groups(pending);let analyzed=0,accepted=[],held=[];
  for(let i=0;i<Math.min(batches.length,3);i++){
    if(options.signal?.aborted)break;
    const batch=batches[i],prompt=I.prompt(batch);let raw;
    try{raw=await askModel(cfg,prompt.system,prompt.user,{signal:options.signal,maxTokens:1000,timeoutMs:45000});}
    catch(e){if(/AI_(?:INFERENCE_TIMEOUT|OUTPUT_TRUNCATED|CONNECTION|HTTP_|EMPTY_REPLY|RESPONSE_FORMAT)/.test(String(e?.message||'')))break;throw e;}
    let checked;try{checked=I.validate(batch,I.parse(raw));}catch{break;}
    accepted.push(...checked.accepted);held.push(...checked.held);analyzed+=batch.length;
  }
  // This proof can be extracted from clearly adjacent biography/response
  // even when the model failed, returned no candidates or is unavailable.
  const selfIntroduced=I.validate(records,I.inferSelfIntroductions(records)).accepted;
  const biography=I.validate(records,I.inferBiographyNames(records)).accepted;
  const addressed=I.validate(records,I.inferAddressedNames(records)).accepted;
  if(!analyzed&&!selfIntroduced.length&&!biography.length&&!addressed.length)return {updated:0,...roleResult,reason:'本地模型未完成姓名推理；下次保留重新检查'};
  accepted.push(...selfIntroduced,...biography,...addressed);
  const combined=[...(snapshot.speakerCandidates||[]),...held];
  const result=I.resolve({accepted,held:combined},snapshot.speakerNames||{});
  await notebookWrite(async()=>{
    const current=await loadSession(sessionKey);if(!current)return;
    const names={...current.speakerNames},evid={...(current.speakerEvidence||{})};
    for(const [id,name] of Object.entries(result.names)){
      if(names[id]&&names[id]!==name)continue;
      names[id]=name;if(result.evidence[id])evid[id]=result.evidence[id];
    }
    // Only metadata; no raw cue, document or cache mutation.
    await writeSession({...current,speakerNames:names,speakerEvidence:evid,speakerCandidates:[...(current.speakerCandidates||[]),...result.suggestions].slice(-100)});
  });
  for(const rec of pending.filter(rec=>pending.indexOf(rec)<analyzed||selfIntroduced.some(b=>b.cueId===rec.cueId)||biography.some(b=>b.cueId===rec.cueId)))checked[rec.cueId]=VknLongform.hash(JSON.stringify([rec.text,rec.original,rec.subtitle,rec.speakerId,rec.contextBefore,rec.contextAfter]));
  const safe=Object.fromEntries(Object.entries(checked).slice(-2500));
  await chrome.storage.local.set({[stateKey]:{schema:6,checked:safe}});
  return {updated:Object.keys(result.evidence).length,...roleResult,checked:analyzed,total:pending.length};
 })();
 vknIdentityRunning.set(sessionKey,operation);try{return await operation;}finally{vknIdentityRunning.delete(sessionKey);}
}
