/* Only the trusted extension library can list/delete cached videos. */
'use strict';
async function vknCacheRequest(path, body={}) {
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
  try {
    const r=await fetch('http://127.0.0.1:8765/media-cache/'+path, {method:'POST',redirect:'error',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});
    let data; try {data=await r.json();} catch {throw Error('VIDEO_SERVICE：本地服务未返回有效结果，请更新到0.11.0并重启。');}
    if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'VIDEO_SERVICE：本地视频缓存服务返回错误 '+r.status);
    return data;
  } catch(e) {
    if(controller.signal.aborted)throw Error('VIDEO_CONNECT_TIMEOUT：无法及时联系本地缓存服务，先启动0.11.0本地服务。');
    if(String(e.message).startsWith('VIDEO_'))throw e;
    throw Error('VIDEO_CONNECT：无法连接本地缓存服务127.0.0.1:8765，请启动新版服务。');
  } finally {clearTimeout(timer);}
}
async function vknHandleCacheMessage(msg,sender) {
  if(sender.id!==chrome.runtime.id)throw Error('VIDEO_SENDER：不允许外部请求');
  if(msg.type==='VKN_CACHE_OPEN') {
    await chrome.tabs.create({url:chrome.runtime.getURL('cache.html')});return {opened:true};
  }
  if(msg.type==='VKN_CACHE_CREATE') {
    // Never accept an arbitrary network target from a website/message.
    if(!sender.tab?.id)throw Error('VIDEO_SOURCE：请从正在观看的视频页面发起下载');
    const tab=chrome.tabs?.get?await chrome.tabs.get(sender.tab.id):sender.tab;
    if(msg.sourceUrl&&VideoKnowledgeCore.pageKey(msg.sourceUrl)!==VideoKnowledgeCore.pageKey(tab.url))throw Error('VIDEO_SOURCE_CHANGED：已切换视频，请重新点击保存');
    return vknCacheRequest('create',{url:tab.url,title:String(msg.title||'视频').slice(0,240),consent:msg.consent===true});
  }
  if(sender.tab && !String(sender.url||'').startsWith(chrome.runtime.getURL('cache.html')))throw Error('VIDEO_SENDER：请在本扩展缓存管理页操作');
  if(sender.url!==chrome.runtime.getURL('cache.html'))throw Error('VIDEO_SENDER：仅允许本扩展缓存管理页');
  if(msg.type==='VKN_CACHE_LIST')return vknCacheRequest('list');
  if(!/^[a-f0-9]{32}$/.test(String(msg.id||'')))throw Error('VIDEO_ID：缓存编号无效');
  if(msg.type==='VKN_CACHE_RETRY_LOGIN'){if(msg.consent!==true)throw Error('VIDEO_AUTH_CONSENT：本次未授权使用登录状态');return vknYoutubeSessionForRetry(msg.id);}
  const action={VKN_CACHE_RETRY:'retry',VKN_CACHE_CANCEL:'cancel',VKN_CACHE_DELETE:'delete',VKN_CACHE_PLAY:'play'}[msg.type];
  if(!action)throw Error('VIDEO_ACTION：未知缓存操作');
  return vknCacheRequest(msg.id+'/'+action);
}

// Only called from the trusted cache page, after a per-attempt confirmation.
// Never return cookie values to the content script/UI or persist them in storage.
async function vknYoutubeSessionForRetry(id){
  const list=await vknCacheRequest('list');
  if(!list.capabilities?.login_transfer)throw Error('VIDEO_UPGRADE：本地服务需要更新至0.11.0，尚未读取登录状态。');
  const row=list.items?.find(x=>x.id===id);if(!row)throw Error('VIDEO_NOT_FOUND：缓存任务不存在');
  const u=new URL(row.url);
  if(u.protocol!=='https:'||!['www.youtube.com','youtube.com','m.youtube.com','youtu.be'].includes(u.hostname))throw Error('VIDEO_AUTH_SCOPE：本次登录仅用于YouTube');
  if(!await chrome.permissions.contains({permissions:['cookies']}))throw Error('VIDEO_AUTH_PERMISSION：尚未授予本次登录访问权限');
  if(!chrome.cookies?.getAll)throw Error('VIDEO_AUTH_PERMISSION：当前浏览器不支持读取授权会话');
  let raw=await chrome.cookies.getAll({domain:'youtube.com'});
  const allowed=new Set(['youtube.com','.youtube.com','www.youtube.com','.www.youtube.com','m.youtube.com','.m.youtube.com']);
  const cookies=raw.filter(c=>allowed.has(c.domain)&&!c.partitionKey&&(!c.expirationDate||c.expirationDate>Date.now()/1000))
    .map(c=>({name:c.name,value:c.value,domain:c.domain,path:c.path||'/',secure:!!c.secure,httpOnly:!!c.httpOnly,hostOnly:!!c.hostOnly,...(c.expirationDate?{expirationDate:c.expirationDate}:{})}));
  raw=null;
  if(!cookies.length||!cookies.some(c=>['SAPISID','__Secure-1PAPISID','__Secure-3PAPISID','SID','LOGIN_INFO'].includes(c.name)))throw Error('VIDEO_AUTH_EMPTY：同一Edge配置中未找到YouTube登录会话，请先登录；无痕和其他浏览器配置不共用。');
  if(cookies.length>128||JSON.stringify(cookies).length>65536)throw Error('VIDEO_AUTH_SIZE：登录数据超过单次传输上限');
  try{return await vknCacheRequest(id+'/retry',{login_consent:true,youtube_cookies:cookies});}
  finally{cookies.length=0;}
}
