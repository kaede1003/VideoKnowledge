/* Caption validation is local only. Requests are bounded and cancellation is per tab. */
'use strict';
const vknCaptionJobs=new Map();
async function vknHandleCaptionMessage(msg,sender){
  if(sender.id!==chrome.runtime.id||!sender.tab?.id)throw Error('CAPTION_SENDER：仅允许本扩展的视频页调用');
  const id=sender.tab.id;
  if(msg.type==='VKN_CAPTION_CANCEL'){vknCaptionJobs.get(id)?.abort();return {cancelled:true};}
  if(msg.type==='VKN_CAPTION_CLOCK'){
    const s=await vknStatus();return s.tabId===id&&s.sessionKey===msg.key?s:{running:false};
  }
  if(!['VKN_CAPTION_FRAME','VKN_CAPTION_VALIDATE'].includes(msg.type))throw Error('CAPTION_ACTION');
  if(vknCaptionJobs.has(id))return {busy:true};
  // Give manual writing priority over extra vision inference. Audio capture never waits for this.
  if(msg.type==='VKN_CAPTION_FRAME'&&aiJobs.size)return {busy:true};
  const ctrl=new AbortController();vknCaptionJobs.set(id,ctrl);const timer=setTimeout(()=>ctrl.abort(),25000);
  try{
    let payload=msg.data,path='/caption-review/validate';
    if(msg.type==='VKN_CAPTION_FRAME'){
      const s=await vknStatus();
      if(!s.running||s.paused||s.tabId!==id||s.sessionKey!==msg.key)throw Error('CAPTION_NOT_RECORDING');
      const frames=await vknSendOffscreen('VKN_CAPTION_PAIR',{tabId:id,sessionKey:msg.key});
      if(ctrl.signal.aborted)throw Error('CAPTION_CANCELLED');
      payload=frames;path='/caption-review/frames';
    }
    const r=await fetch('http://127.0.0.1:8765'+path,{method:'POST',redirect:'error',signal:ctrl.signal,headers:{'content-type':'application/json'},body:JSON.stringify(payload)});
    if(!r.ok){let code='CAPTION_HTTP_'+r.status;try{code=String((await r.json()).detail||code).slice(0,250);}catch{}throw Error(code);}
    return await r.json();
  }catch(e){if(ctrl.signal.aborted)throw Error('CAPTION_CANCELLED_OR_TIMEOUT：字幕核对暂缓，听写继续保留');throw e;}
  finally{clearTimeout(timer);if(vknCaptionJobs.get(id)===ctrl)vknCaptionJobs.delete(id);}
}
