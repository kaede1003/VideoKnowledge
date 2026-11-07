/* Caption validation is local only. Requests are bounded and cancellation is per tab. */
'use strict';
const vknCaptionJobs=new Map();
async function vknHandleCaptionMessage(msg,sender){
  if(sender.id!==chrome.runtime.id||!sender.tab?.id)throw Error('CAPTION_SENDER：仅允许本扩展的视频页调用');
  const id=sender.tab.id;
  if(msg.type==='VKN_CAPTION_CANCEL'){vknCaptionJobs.get(id)?.abort();return {cancelled:true};}
  if(msg.type==='VKN_CAPTION_CLOCK'){
    const s=await vknStatus();
    if(s.tabId!==id||s.sessionKey!==msg.key)return {running:false};
    if(typeof msg.sampleFrames==='boolean'){
      try{await vknSendOffscreen('VKN_CAPTION_BUFFER_CONFIG',{tabId:id,sessionKey:msg.key,enabled:msg.sampleFrames&&s.running&&!s.paused});}catch{}
    }
    return s;
  }
  if(!['VKN_CAPTION_FRAME','VKN_CAPTION_VALIDATE'].includes(msg.type))throw Error('CAPTION_ACTION');
  if(vknCaptionJobs.has(id))return {busy:true};
  // Give manual writing priority over extra vision inference. Audio capture never waits for this.
  if(msg.type==='VKN_CAPTION_FRAME'&&aiJobs.size)return {busy:true};
  const ctrl=new AbortController();vknCaptionJobs.set(id,ctrl);const timer=setTimeout(()=>ctrl.abort(),25000);
  try{
    let payload=msg.data,path='/caption-review/validate',sampling=null;
    if(msg.type==='VKN_CAPTION_FRAME'){
      const s=await vknStatus();
      if(!s.running||s.paused||s.tabId!==id||s.sessionKey!==msg.key)throw Error('CAPTION_NOT_RECORDING');
      const frames=await vknSendOffscreen('VKN_CAPTION_PAIR',{tabId:id,sessionKey:msg.key});
      if(ctrl.signal.aborted)throw Error('CAPTION_CANCELLED');
      sampling=frames.sampling;payload={frames:frames.frames};path='/caption-review/frames';
    }
    const r=await fetch('http://127.0.0.1:8765'+path,{method:'POST',redirect:'error',signal:ctrl.signal,headers:{'content-type':'application/json'},body:JSON.stringify(payload)});
    if(!r.ok){let code='CAPTION_HTTP_'+r.status;try{code=String((await r.json()).detail||code).slice(0,250);}catch{}throw Error(code);}
    const result=await r.json();if(sampling)result.sampling=sampling;return result;
  }catch(e){if(ctrl.signal.aborted)throw Error('CAPTION_CANCELLED_OR_TIMEOUT：字幕核对暂缓，听写继续保留');throw e;}
  finally{clearTimeout(timer);if(vknCaptionJobs.get(id)===ctrl)vknCaptionJobs.delete(id);}
}

// Re-evaluate saved evidence before taking the generation snapshot. This repairs
// older Latin candidates without replaying the video, but invents no unseen frames.
async function vknReviewStoredCaptions(cues,observations,options={}){
  const data=VknCaptions.cleanObservations(observations),reviews={},notes=[];
  if(!data.length)return {cues,reviews,notes};
  const eligible=cues.filter(c=>!c.manuallyEdited&&c.captionReview?.status!=='dismissed').map(c=>({cue:{...c,text:c.original||c.text},evidence:VknCaptions.evidenceFor(c,data)})).filter(x=>x.evidence.length);
  const total=Math.ceil(eligible.length/12);
  for(let i=0;i<eligible.length;i+=12){
    throwIfCancelled(options.signal);options.phaseProgress?.('核对已采字幕',i/12+1,total);
    const controller=new AbortController(),cancel=()=>controller.abort(),timer=setTimeout(cancel,7000);
    options.signal?.addEventListener('abort',cancel,{once:true});
    try{
      const r=await fetch('http://127.0.0.1:8765/caption-review/validate',{method:'POST',redirect:'error',signal:controller.signal,headers:{'content-type':'application/json'},body:JSON.stringify({items:eligible.slice(i,i+12)})});
      if(!r.ok)throw Error('CAPTION_VALIDATE_HTTP_'+r.status);
      const j=await r.json();if(!Array.isArray(j.reviews))throw Error('CAPTION_VALIDATE_FORMAT');
      for(const result of j.reviews){const source=eligible.slice(i,i+12).find(x=>x.cue.id===result.id)?.cue;if(!source||result.source!==String(source.original||source.text))continue;const clean=VideoKnowledgeCore.cleanCaptionReview({...result,checkedAt:new Date().toISOString()});if(clean)reviews[result.id]=clean;}
    }catch(e){throwIfCancelled(options.signal);notes.push('已存字幕复核未完成，保留原记录及已有修订；未采样历史画面不被补猜。');break;}
    finally{clearTimeout(timer);options.signal?.removeEventListener('abort',cancel);}
  }
  const revised=cues.map(c=>{const r=reviews[c.id];if(!r||c.manuallyEdited||c.captionReview?.status==='dismissed')return c;
    if(r.status==='applied')return {...c,captionReview:r,captionCorrected:true};
    if(c.captionCorrected&&r.reason.includes('冲突'))return {...c,captionReview:r,captionCorrected:false};
    return c;
  });
  const count=Object.values(reviews).filter(x=>x.status==='applied').length;
  if(count)notes.push('本次整理对已保存的字幕证据重新核对，采用 '+count+' 条局部修订。字幕并非原音或事实核验。');
  return {cues:revised,reviews,notes};
}
