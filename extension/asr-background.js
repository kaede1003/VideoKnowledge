/* Local ASR orchestration loaded by the MV3 background service worker. */
'use strict';
let vknOffscreenCreating = null;
const VKN_OFFSCREEN_URL = chrome.runtime.getURL('offscreen.html');

async function vknHasOffscreen() {
  const contexts = await chrome.runtime.getContexts({
    contextTypes: ['OFFSCREEN_DOCUMENT'], documentUrls: [VKN_OFFSCREEN_URL]
  });
  return contexts.length > 0;
}
async function vknEnsureOffscreen() {
  if(await vknHasOffscreen())return;
  if(vknOffscreenCreating)return vknOffscreenCreating;
  vknOffscreenCreating=chrome.offscreen.createDocument({
    url:'offscreen.html',reasons:['USER_MEDIA'],
    justification:'用户主动允许后采集当前标签的音频用于本地听写，并可选采集视频画面制作LoRA样本'
  }).finally(()=>{vknOffscreenCreating=null;});
  return vknOffscreenCreating;
}
async function vknSendOffscreen(type,data={}) {
  const response=await chrome.runtime.sendMessage({...data,type,target:'offscreen'});
  if(!response?.ok)throw Error(response?.error||'离屏音视频处理失败');
  return response.data;
}
async function vknStatus() {
  if(!await vknHasOffscreen())return {running:false,tabId:null};
  try{return await vknSendOffscreen('VKN_ASR_STATUS');}
  catch{return {running:false,tabId:null};}
}
async function vknEnsureNotebook(tabId) {
  try{return await chrome.tabs.sendMessage(tabId,{type:'VKN_ASR_CONTEXT'});}catch(_){
    await chrome.scripting.executeScript({target:{tabId},files:['core.js','caption-review.js','content.js']});
    return await chrome.tabs.sendMessage(tabId,{type:'VKN_ASR_CONTEXT'});
  }
}
// A native action/command grants activeTab. A content-script click alone does NOT.
// Try an existing grant, otherwise offer the explicit tab+audio picker from the page.
let vknAsrSequence = Promise.resolve();
let vknAsrGeneration=0;
function vknDeadline(p,ms,message){let timer;return Promise.race([p,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(message)),ms);})]).finally(()=>clearTimeout(timer));}
function vknSerial(task){
  const current=vknAsrSequence.catch(()=>{}).then(task);
  vknAsrSequence=current.catch(()=>{});
  return current;
}
function vknClaimStream(tab){
  let p;try{p=Promise.resolve(chrome.tabCapture.getMediaStreamId({targetTabId:tab.id}));}catch(e){p=Promise.reject(e);}
  // A LoRA capture may already exist. Observe a rejected unused promise to avoid unhandled rejection.
  p.catch(()=>{});
  return p;
}
const vknCapturePickers=new Map();
const vknStartRequests=new Map();
function vknNeedsCaptureGrant(error){return /not.*(?:invok|grant)|activeTab|permission|user gesture|has not been invoked|未.*授.*权/i.test(String(error?.message||error));}
function vknNotifyCapture(tabId,message,extra={}){
  return chrome.tabs.sendMessage(tabId,{type:'VKN_ASR_STATE',starting:true,tabId,message,...extra}).catch(()=>{});
}
function vknChooseTabAudio(tab,ticket){
  if(!chrome.desktopCapture?.chooseDesktopMedia)throw Error('CAPTURE_GRANT：当前浏览器未提供共享选择器。请按 Alt+Shift+V 直接开始听写，或点击一次工具栏图标。');
  if(ticket!==vknAsrGeneration)throw Error('CAPTURE_CANCELLED：已取消授权');
  if(vknCapturePickers.has(tab.id))throw Error('CAPTURE_PENDING：请完成已打开的声音共享授权。');
  vknNotifyCapture(tab.id,'请选择当前视频所在的标签页，并勾选“共享标签页音频”。不会采集麦克风；取消即可退出。');
  return new Promise((resolve,reject)=>{
    let settled=false,requestId;
    const finish=(error,value)=>{if(settled)return;settled=true;clearTimeout(timer);vknCapturePickers.delete(tab.id);error?reject(error):resolve(value);};
    const cancel=()=>{try{if(requestId!==undefined)chrome.desktopCapture.cancelChooseDesktopMedia(requestId);}catch{}finish(Error('CAPTURE_CANCELLED：声音共享已取消，没有开始听写。'));};
    const timer=setTimeout(cancel,120000);
    vknCapturePickers.set(tab.id,{cancel});
    try{requestId=chrome.desktopCapture.chooseDesktopMedia(['tab','audio'],(id,options)=>{
      const last=chrome.runtime.lastError;
      if(settled)return;
      if(ticket!==vknAsrGeneration)return finish(Error('CAPTURE_CANCELLED：启动已取消，未采集声音。'));
      if(last)return finish(Error('CAPTURE_PICKER：'+last.message));
      if(!id)return finish(Error('CAPTURE_CANCELLED：已取消声音共享，没有开始听写。'));
      if(!options?.canRequestAudioTrack)return finish(Error('CAPTURE_NO_AUDIO：未勾选“共享标签页音频”，没有开始听写。请重新开始并选择当前视频标签和音频。'));
      finish(null,{streamId:id,mediaSource:'desktop'});
    });}catch(e){finish(Error('CAPTURE_PICKER：无法打开共享选择器，可按 Alt+Shift+V 直接启动。'+String(e.message||e)));}
  });
}
function vknCancelCapturePickers(tabId){for(const [id,p] of vknCapturePickers){if(!tabId||id===tabId)p.cancel();}}
async function vknStartAsr(tab, streamPromise,ticket=vknAsrGeneration,allowPicker=false){
  const check=()=>{if(ticket!==vknAsrGeneration)throw Error('CAPTURE_CANCELLED：本轮启动已被停止操作取消');};check();
  if(!tab?.id || !/^https?:\/\//i.test(tab.url||''))throw Error('请先打开普通视频网站标签页');
  const existing=await vknStatus();check();
  if(existing.running && existing.tabId===tab.id)
    return {running:true,paused:!!existing.paused,tabId:tab.id,sessionKey:existing.sessionKey};
  if(existing.captureRunning && existing.tabId!==tab.id)throw Error('另一个标签页正在采集，请先停止');
  const meta=await vknEnsureNotebook(tab.id);check();
  const options=VideoKnowledgeCore.speechOptions((await chrome.storage.local.get('vknSpeechConfig')).vknSpeechConfig||{});
  check();
  if(!meta?.key)throw Error('本页面未检测到视频播放器，请先打开或开始播放视频');
  if(existing.captureRunning && existing.tabId===tab.id){
    const joined=await vknSendOffscreen('VKN_ASR_ATTACH',{options});check();
    await chrome.action.setBadgeText({tabId:tab.id,text:'REC'});
    chrome.tabs.sendMessage(tab.id,{type:'VKN_ASR_STATE',running:true,paused:false,startedByUser:true,tabId:tab.id}).catch(()=>{});
    return {...joined,paused:false,tabId:tab.id,sessionKey:meta.key};
  }
  if(!streamPromise)throw Error('请在视频网站页面点击插件的开始按钮，或点击Edge工具栏插件图标授权');
  // Offscreen creation and media-ID permission are intentionally independent.
  // Do not open a WebSocket here: the stream is acquired first, then ASR connects once.
  const offscreenReady=vknEnsureOffscreen();
  let grant;
  try{grant={streamId:await streamPromise,mediaSource:'tab'};}
  catch(e){
    check();
    if(allowPicker&&vknNeedsCaptureGrant(e)){
      await offscreenReady;check();grant=await vknChooseTabAudio(tab,ticket);
    }else throw Error('CAPTURE_GRANT：'+String(e?.message||e)+'。可按 Alt+Shift+V 直接启动；页面开始按钮也支持共享授权。');
  }
  await offscreenReady;check();
  // Do not attach a chooser's late answer to a different video/session.
  const latest=await vknEnsureNotebook(tab.id);check();
  if(latest?.key!==meta.key)throw Error('CAPTURE_PAGE_CHANGED：授权期间视频已切换，本次没有开始；请在当前视频重新点击开始。');
  const {streamId,mediaSource}=grant;
  let started=false;
  try{
    const output=await vknSendOffscreen('VKN_ASR_START',{
      streamId,mediaSource,tabId:tab.id,sessionKey:meta.key,enableAsr:true,options,title:meta.title||tab.title||'',url:tab.url,
      player:{time:meta.time||0,paused:!!meta.paused,rate:meta.rate||1}
    });
    check();started=true;
    await chrome.action.setBadgeText({tabId:tab.id,text:'REC'});
    await chrome.action.setBadgeBackgroundColor({tabId:tab.id,color:'#2A9B77'});
    chrome.tabs.sendMessage(tab.id,{type:'VKN_ASR_STATE',running:true,paused:false,startedByUser:true,tabId:tab.id,message:'本地听写已启动'}).catch(()=>{});
    return {...output,paused:false};
  }catch(e){
    if(!started && ticket===vknAsrGeneration)await vknSendOffscreen('VKN_CAPTURE_STOP',{expectedTabId:tab.id}).catch(()=>{});
    throw e;
  }
}
async function vknStopAsr(expectedTabId,all=false){
  ++vknAsrGeneration;vknCancelCapturePickers(expectedTabId);
  if(all && typeof vknLoraGeneration!=='undefined')++vknLoraGeneration;
  if(!await vknHasOffscreen())return {running:false,paused:false,captureRunning:false,tabId:expectedTabId};
  const result=await vknDeadline(vknSendOffscreen(all?'VKN_CAPTURE_STOP':'VKN_ASR_STOP',{expectedTabId}),6000,
    'CAPTURE_STOP_UNCONFIRMED：6秒内未收到停止确认，请先暂停视频；必要时暂时禁用扩展以撤销采集。不要清空缓存或删除扩展。');
  const tabId=result?.tabId||expectedTabId;
  if(tabId){
    await chrome.action.setBadgeText({tabId,text:result?.loraRunning?'IMG':''}).catch(()=>{});
    chrome.tabs.sendMessage(tabId,{type:'VKN_ASR_STATE',running:false,paused:false,draining:!!result?.draining,tabId,
      message:result?.warning||'采集已停止；已缓存内容仍会补录/翻译，不是继续录音。'}).catch(()=>{});
  }
  return {...result,running:false,paused:false,tabId};
}
async function vknPauseAsr(pause,ticket=vknAsrGeneration){
  const stale=()=>ticket!==vknAsrGeneration;
  if(stale())return {running:false,paused:false,cancelled:true};
  const current=await vknStatus();
  if(stale())return {running:false,paused:false,cancelled:true};
  if(!current.running)throw Error('请先启动语音听写');
  const data=await vknSendOffscreen(pause?'VKN_ASR_PAUSE':'VKN_ASR_RESUME');
  // Stop takes priority over an earlier pause/resume reply; do not resurrect UI state.
  if(stale()||data?.running===false)return {...data,running:false,paused:false,cancelled:true};
  await chrome.action.setBadgeText({tabId:current.tabId,text:pause?'PAU':'REC'}).catch(()=>{});
  if(stale())return {running:false,paused:false,cancelled:true};
  chrome.tabs.sendMessage(current.tabId,{type:'VKN_ASR_STATE',running:true,paused:pause,tabId:current.tabId,
    message:pause?'语音听写已暂停':'语音听写已继续'}).catch(()=>{});
  return {...data,running:true,paused:pause,tabId:current.tabId};
}
function vknRequestAsrStart(tab,allowPicker=false){
  if(vknStartRequests.has(tab.id))return vknStartRequests.get(tab.id);
  const streamPromise=vknClaimStream(tab),ticket=vknAsrGeneration;
  const request=vknSerial(()=>vknStartAsr(tab,streamPromise,ticket,allowPicker));
  vknStartRequests.set(tab.id,request);
  request.finally(()=>{if(vknStartRequests.get(tab.id)===request)vknStartRequests.delete(tab.id);}).catch(()=>{});
  return request;
}
function vknToggleAsr(tab){
  if(vknStartRequests.has(tab.id))return vknStopAsr(tab.id,true);
  const streamPromise=vknClaimStream(tab),ticket=vknAsrGeneration;
  return vknStatus().then(current=>{
    if((current.running||current.phase==='starting') && current.tabId===tab.id)return vknStopAsr(tab.id);
    return vknSerial(()=>vknStartAsr(tab,streamPromise,ticket));
  });
}
function vknOnAction(tab){
  if(!tab?.id || !/^https?:\/\//i.test(tab.url||''))return;
  // The browser command _execute_action grants activeTab, just like the toolbar.
  vknNotifyCapture(tab.id,'正在启动当前视频听写…');
  vknToggleAsr(tab).catch(e=>{
    if(String(e?.message||e).startsWith('CAPTURE_CANCELLED'))return;
    chrome.tabs.sendMessage(tab.id,{type:'VKN_ASR_STATE',running:false,error:'语音操作失败：'+String(e?.message||e)}).catch(()=>{});
  });
  chrome.tabs.sendMessage(tab.id,{type:'VKN_OPEN'}).catch(()=>{});
}
function vknHandleAsrMessage(msg,sender){
  switch(msg.type){
    case 'VKN_ASR_STATUS_QUERY':
      // Prewarm blank offscreen page so the next user click can consume ID promptly.
      return vknEnsureOffscreen().then(()=>vknStatus());
    case 'VKN_ASR_START':
      if(!sender.tab?.id)throw Error('只能从视频网站内操作');
      return vknRequestAsrStart(sender.tab,true);
    case 'VKN_ASR_TOGGLE':
      if(!sender.tab?.id)throw Error('只能从视频网站内操作');
      return vknToggleAsr(sender.tab);
    case 'VKN_ASR_RETRY':return (async()=>{const opts=VideoKnowledgeCore.speechOptions((await chrome.storage.local.get('vknSpeechConfig')).vknSpeechConfig||{});await vknEnsureOffscreen();return vknSendOffscreen('VKN_ASR_RETRY',{sessionKey:msg.sessionKey,options:opts});})();
    case 'VKN_ASR_STOP':return vknStopAsr(sender.tab?.id);
    case 'VKN_ASR_STOP_ALL':return vknStopAsr(sender.tab?.id,true);
    case 'VKN_ASR_PAUSE':{const ticket=vknAsrGeneration;return vknSerial(()=>vknPauseAsr(true,ticket));}
    case 'VKN_ASR_RESUME':{const ticket=vknAsrGeneration;return vknSerial(()=>vknPauseAsr(false,ticket));}
    case 'VKN_ASR_EVENT': return (async()=>{
      if(sender.url!==VKN_OFFSCREEN_URL)throw Error('不允许转发来自网页的转写结果');
      const payload=msg.data||{};
      const current=await vknStatus();
      if(msg.kind==='segment')await vknPersistAsr(msg);
      if(msg.kind==='stopped')await chrome.action.setBadgeText({tabId:msg.tabId,text:current.loraRunning?'IMG':''}).catch(()=>{});
      chrome.tabs.sendMessage(msg.tabId,{type:'VKN_ASR_EVENT',tabId:msg.tabId,sessionKey:msg.sessionKey,
        kind:msg.kind,data:payload}).catch(()=>{});
      return {delivered:true};
    })();
    default:throw Error('未知语音识别指令');
  }
}
chrome.tabs.onRemoved.addListener(async tabId=>{
  vknCancelCapturePickers(tabId);
  try{const current=await vknStatus();if(current.captureRunning && current.tabId===tabId)await vknSendOffscreen('VKN_CAPTURE_STOP');}
  catch(_){/* tab already closed */}
});
