'use strict';
const $=id=>document.getElementById(id),stateNames={queued:'排队中',downloading:'下载中',processing:'合并音视频',ready:'已保存',failed:'失败',cancelled:'已取消',interrupted:'已中断',cleanup_failed:'清理待重试'};
let busy=false,operationPending=false,playingId='';
const call=(type,args={})=>new Promise((resolve,reject)=>{chrome.runtime.sendMessage({type,...args},r=>{if(chrome.runtime.lastError)return reject(Error(chrome.runtime.lastError.message));if(!r?.ok)return reject(Error(r?.error||'缓存操作失败'));resolve(r.data);});});
const size=n=>(Number(n||0)/1024/1024).toFixed(1)+' MiB';
const date=t=>new Date(Number(t)*1000).toLocaleString('zh-CN');
function status(text,error=false){$('status').textContent=text;$('status').className=error?'error':'';}
function stopPlayer(){const v=$('player');v.pause();v.removeAttribute('src');v.load();$('playback').hidden=true;playingId='';}
function validPlayback(raw,id){const u=new URL(raw);if(u.origin!=='http://127.0.0.1:8765'||u.pathname!=='/media-cache/file/'+id||u.username||u.password)throw Error('本地播放地址无效');return u.toString();}
async function operate(row,action){if(operationPending)return;operationPending=true;try{
 if(action==='RETRY_LOGIN'){
   if(!confirm(`仅这一次：把当前Edge配置中的YouTube站点会话发送给本机127.0.0.1下载器，再由下载器用于向YouTube请求。
不读取其他网站或密码，不保存Cookie文件；权限可在本页撤销。
使用账号下载存在平台限流或封号风险，且仍不保证可下载。仅保存你有权保存的内容，不处理DRM/会员/私有视频。
是否授权本次重试？`))return;
   // Invoke permissions.request directly within this button's user gesture.
   const granted=await chrome.permissions.request({permissions:['cookies']});
   if(!granted){status('未授权登录访问，匿名下载仍可使用。');return;}
   status('已授权本次YouTube会话重试；不会保存登录信息。');
 }

 if(action==='DELETE'&&!confirm('只删除该视频缓存，笔记保留。确定删除？'))return;
 if(action==='DELETE'&&playingId===row.id)stopPlayer();
 const r=await call('VKN_CACHE_'+action,{id:row.id,...(action==='RETRY_LOGIN'?{consent:true}:{})});
 if(action==='PLAY'){$('playing-title').textContent=row.title;$('player').src=validPlayback(r.url,row.id);playingId=row.id;$('playback').hidden=false;$('playback').scrollIntoView({block:'start'});$('player').play().catch(()=>{});}
 else await refresh();
}catch(e){status(e.message,true);}finally{operationPending=false;}}
async function refresh(){if(busy)return;busy=true;$('refresh').disabled=true;
 try{const r=await call('VKN_CACHE_LIST');$('directory').textContent='缓存目录：'+r.directory;$('items').replaceChildren();
 status(r.capabilities?.message||'已读取本地缓存');
 const cap=r.capabilities||{};$('components').textContent='下载组件 '+(cap.version||'未知')+' · EJS '+(cap.ejs_version||'未检测到')+' · JavaScript '+(cap.javascript_runtime||'未检测到')+' · FFmpeg '+(cap.ffmpeg?'可用':'未检测到');
 if(!r.items?.length){const p=document.createElement('p');p.textContent='尚无缓存。在视频面板中点击“保存视频（3天）”开始。';$('items').append(p);}
 for(const row of r.items||[]){const item=document.createElement('article');item.className='card';const title=document.createElement('h2');title.textContent=row.title;const info=document.createElement('p');const expired=Date.now()/1000>=row.expires;
 info.textContent=(expired?'已到期':stateNames[row.state]||row.state)+' · '+size(row.size)+(row.completed?' · 到期 '+date(row.expires):'');item.append(title,info);
 if(row.error){const err=document.createElement('p');err.className='error';err.textContent=row.error;item.append(err);}
 if(row.progress!=null&&['queued','downloading','processing'].includes(row.state)){const p=document.createElement('progress');p.max=1;p.value=row.progress;item.append(p);}
 const actions=document.createElement('div');actions.className='actions';let choices=(['queued','downloading','processing'].includes(row.state)?[['CANCEL','取消下载']]:row.state==='ready'&&!expired?[['PLAY','本地播放'],['DELETE','删除缓存']]:[['RETRY','重新下载（不使用登录）'],['DELETE','删除记录']]);
 if(['failed','interrupted','cancelled'].includes(row.state)&&/^https:\/\/(?:www\.|m\.)?youtube\.com\//.test(row.url)&&r.capabilities?.login_transfer)choices.unshift(['RETRY_LOGIN','授权本次使用YouTube登录重试']);
 for(const [name,label] of choices){const b=document.createElement('button');b.textContent=label;b.onclick=()=>operate(row,name);actions.append(b);}if(['failed','interrupted','cancelled'].includes(row.state)){const p=document.createElement('p');p.className='hint';p.textContent='传输字节数不代表已保存；此次未生成可用视频。';item.append(p);}item.append(actions);$('items').append(item);
 if(playingId===row.id&&expired)stopPlayer();}
 }catch(e){status(e.message,true);}finally{busy=false;$('refresh').disabled=false;}}
$('revoke-login').onclick=async()=>{try{await chrome.permissions.remove({permissions:['cookies']});status('已撤销后续登录读取权限。已提交的下载如需停止，请点击该任务的取消下载。');}catch{status('权限撤销失败，可在Edge扩展管理页查看。',true);}};
$('refresh').onclick=refresh;$('close-player').onclick=stopPlayer;$('player').onerror=()=>status('本地播放失败：缓存可能已到期、播放许可过期，或浏览器不支持该编码。请刷新后重新播放。',true);
refresh();setInterval(()=>{if(!document.hidden&&!operationPending)refresh();},5000);
