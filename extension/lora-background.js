/* Optional LoRA dataset mode. Shares the same single tabCapture stream with ASR. */
'use strict';
const VKN_LORA_LOCAL='http://127.0.0.1:8765';
let vknLoraCurrent=null;
let vknLoraGeneration=0;
async function vknLoraLocal(path, payload){
  const ctrl=new AbortController();
  const seconds=15;
  const timer=setTimeout(()=>ctrl.abort(new Error('本地模型处理超时')),seconds*1000);
  try{
    const r=await fetch(VKN_LORA_LOCAL+path,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload),redirect:'error',signal:ctrl.signal});
    const result=await r.json().catch(()=>({}));
    if(!r.ok)throw Error(result.detail||'本地视觉服务 HTTP '+r.status);
    return result;
  }catch(e){
    if(ctrl.signal.aborted)throw Error(`本地视觉服务${seconds}秒内没有完成处理，请重启新版本地服务并检测连接；制定规则不再需要加载模型`);
    if(e instanceof TypeError)throw Error('无法连接本地视觉服务，请先运行 START_LOCAL_ASR.bat 并检查8765端口');
    throw e;
  }finally{clearTimeout(timer);}
}
async function vknLoraPlan(msg){
  const prompt=String(msg.prompt||'').trim();
  if(prompt.length<3||prompt.length>900)throw Error('请输入3~900字的画面筛选条件');
  return vknLoraLocal('/lora/plan',{prompt,previous:msg.previous||null});
}
async function vknLoraStart(msg,sender,streamPromise=null){
  const ticket=vknLoraGeneration;const check=()=>{if(ticket!==vknLoraGeneration)throw Error('CAPTURE_CANCELLED：画面采集启动已取消');};
  const tab=sender.tab;
  if(!tab?.id||!/^https:\/\//.test(tab.url||''))throw Error('请先打开视频网站');
  const context=await vknEnsureNotebook(tab.id);
  if(!context?.key)throw Error('当前页面没有视频');
  const existing=await vknStatus();check();
  if(existing.loraRunning || existing.loraProcessing)throw Error('已有LoRA采集或导出准备中的任务，请先完成');
  if(existing.captureRunning && existing.tabId!==tab.id)throw Error('本地采集正在其他标签页运行，请先停止');
  const plan=msg.rule;
  if(!plan?.prompt)throw Error('请先对AI说明需要什么画面并生成筛选方案');
  const config=await vknLoraLocal('/lora/session',{
    title:String(msg.title||tab.title||'视频').slice(0,300), url:tab.url,rule:plan
  });
  check();await vknEnsureOffscreen();check();
  let startedCapture=false;
  try{
    if(!existing.captureRunning){
      // User-triggered extension UI; tabCapture may require toolbar invocation on some Edge versions.
      if(!streamPromise)throw Error('请从网页按钮或Edge工具栏主动授权画面采集');
      const streamId=await streamPromise;check();
      await vknSendOffscreen('VKN_CAPTURE_START',{streamId,tabId:tab.id,sessionKey:context.key,
        player:{time:context.time||0,paused:context.paused,rate:context.rate||1},enableAsr:false});
      startedCapture=true;
    }
    check();await vknSendOffscreen('VKN_LORA_START',{sessionId:config.session_id,rule:config.rule});
    check();vknLoraCurrent={...config,tabId:tab.id,key:context.key};
    await chrome.storage.local.set({'vkn:lora-current':vknLoraCurrent});
    await chrome.action.setBadgeText({tabId:tab.id,text:'IMG'});
    await chrome.action.setBadgeBackgroundColor({tabId:tab.id,color:'#b08b35'});
    return {running:true,tabId:tab.id,session_id:config.session_id,rule:config.rule,save_dir:config.save_dir};
  }catch(e){
    if(startedCapture && ticket===vknLoraGeneration)await vknSendOffscreen('VKN_CAPTURE_STOP').catch(()=>{});
    throw e;
  }
}
async function vknLoraStop(){
  ++vknLoraGeneration;
  if(!await vknHasOffscreen())return {running:false,processing:false};
  const done=await vknDeadline(vknSendOffscreen('VKN_LORA_STOP'),6000,'采图停止未确认，请使用停止全部采集，或暂时禁用扩展。');
  if(vknLoraCurrent?.tabId){const status=await vknStatus();await chrome.action.setBadgeText({tabId:vknLoraCurrent.tabId,text:status.running?'REC':''}).catch(()=>{});}
  return done;
}
async function vknLoraStatus(){
  if(!vknLoraCurrent)vknLoraCurrent=(await chrome.storage.local.get('vkn:lora-current'))['vkn:lora-current']||null;
  const state=await vknStatus();
  return {running:!!state.loraRunning,processing:!!state.loraProcessing,session_id:vknLoraCurrent?.session_id||null,
    save_dir:vknLoraCurrent?.save_dir||null, tabId:vknLoraCurrent?.tabId||null, key:vknLoraCurrent?.key||null};
}
async function vknLoraExport(msg){
  if(!vknLoraCurrent)vknLoraCurrent=(await chrome.storage.local.get('vkn:lora-current'))['vkn:lora-current']||null;
  const session_id=String(msg.sessionId||vknLoraCurrent?.session_id||'');
  if(!/^[a-f0-9]{32}$/.test(session_id))throw Error('请先完成视频素材采集');
  const result=await vknLoraLocal('/lora/export-link',{session_id});
  // Locally generated unguessable capability URL, returned only to this extension.
  const id=await chrome.downloads.download({url:result.url,filename:'VideoKnowledge_LoRA_'+session_id.slice(0,8)+'.zip',saveAs:true});
  return {id,count:result.count,path:result.path};
}
