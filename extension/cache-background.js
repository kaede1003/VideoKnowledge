/* Only the trusted extension library can list/delete cached videos. */
'use strict';
async function vknCacheRequest(path, body={}) {
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
  try {
    const r=await fetch('http://127.0.0.1:8765/media-cache/'+path, {method:'POST',redirect:'error',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});
    let data; try {data=await r.json();} catch {throw Error('VIDEO_SERVICE：本地服务未返回有效结果，请更新到0.8.0并重启。');}
    if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'VIDEO_SERVICE：本地视频缓存服务返回错误 '+r.status);
    return data;
  } catch(e) {
    if(controller.signal.aborted)throw Error('VIDEO_CONNECT_TIMEOUT：无法及时联系本地缓存服务，先启动0.8.0本地服务。');
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
    return vknCacheRequest('create',{url:sender.tab.url,title:String(msg.title||'视频').slice(0,240),consent:msg.consent===true});
  }
  if(sender.tab && !String(sender.url||'').startsWith(chrome.runtime.getURL('cache.html')))throw Error('VIDEO_SENDER：请在本扩展缓存管理页操作');
  if(sender.url!==chrome.runtime.getURL('cache.html'))throw Error('VIDEO_SENDER：仅允许本扩展缓存管理页');
  if(msg.type==='VKN_CACHE_LIST')return vknCacheRequest('list');
  if(!/^[a-f0-9]{32}$/.test(String(msg.id||'')))throw Error('VIDEO_ID：缓存编号无效');
  const action={VKN_CACHE_CANCEL:'cancel',VKN_CACHE_DELETE:'delete',VKN_CACHE_PLAY:'play'}[msg.type];
  if(!action)throw Error('VIDEO_ACTION：未知缓存操作');
  return vknCacheRequest(msg.id+'/'+action);
}
