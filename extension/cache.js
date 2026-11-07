'use strict';
const $=id=>document.getElementById(id),stateNames={queued:'排队中',downloading:'下载中',processing:'合并音视频',ready:'已保存',failed:'失败',cancelled:'已取消',interrupted:'已中断',cleanup_failed:'清理待重试'};
let busy=false,playingId='';
const call=(type,args={})=>new Promise((resolve,reject)=>{chrome.runtime.sendMessage({type,...args},r=>{if(chrome.runtime.lastError)return reject(Error(chrome.runtime.lastError.message));if(!r?.ok)return reject(Error(r?.error||'缓存操作失败'));resolve(r.data);});});
const size=n=>(Number(n||0)/1024/1024).toFixed(1)+' MiB';
const date=t=>new Date(Number(t)*1000).toLocaleString('zh-CN');
function status(text,error=false){$('status').textContent=text;$('status').className=error?'error':'';}
function stopPlayer(){const v=$('player');v.pause();v.removeAttribute('src');v.load();$('playback').hidden=true;playingId='';}
function validPlayback(raw,id){const u=new URL(raw);if(u.origin!=='http://127.0.0.1:8765'||u.pathname!=='/media-cache/file/'+id||u.username||u.password)throw Error('本地播放地址无效');return u.toString();}
async function operate(row,action){try{
 if(action==='DELETE'&&!confirm('只删除该视频缓存，笔记保留。确定删除？'))return;
 if(action==='DELETE'&&playingId===row.id)stopPlayer();
 const r=await call('VKN_CACHE_'+action,{id:row.id});
 if(action==='PLAY'){$('playing-title').textContent=row.title;$('player').src=validPlayback(r.url,row.id);playingId=row.id;$('playback').hidden=false;$('playback').scrollIntoView({block:'start'});$('player').play().catch(()=>{});}
 else await refresh();
}catch(e){status(e.message,true);}}
async function refresh(){if(busy)return;busy=true;$('refresh').disabled=true;
 try{const r=await call('VKN_CACHE_LIST');$('directory').textContent='缓存目录：'+r.directory;$('items').replaceChildren();
 status(r.capabilities?.message||'已读取本地缓存');
 if(!r.items?.length){const p=document.createElement('p');p.textContent='尚无缓存。在视频面板中点击“保存视频（3天）”开始。';$('items').append(p);}
 for(const row of r.items||[]){const item=document.createElement('article');item.className='card';const title=document.createElement('h2');title.textContent=row.title;const info=document.createElement('p');const expired=Date.now()/1000>=row.expires;
 info.textContent=(expired?'已到期':stateNames[row.state]||row.state)+' · '+size(row.size)+(row.completed?' · 到期 '+date(row.expires):'');item.append(title,info);
 if(row.error){const err=document.createElement('p');err.className='error';err.textContent=row.error;item.append(err);}
 if(row.progress!=null&&row.state!=='ready'){const p=document.createElement('progress');p.max=1;p.value=row.progress;item.append(p);}
 const actions=document.createElement('div');for(const [name,label] of (['queued','downloading','processing'].includes(row.state)?[['CANCEL','取消下载']]:row.state==='ready'&&!expired?[['PLAY','本地播放'],['DELETE','删除缓存']]:[['DELETE','删除记录']])){const b=document.createElement('button');b.textContent=label;b.onclick=()=>operate(row,name);actions.append(b);}item.append(actions);$('items').append(item);
 if(playingId===row.id&&expired)stopPlayer();}
 }catch(e){status(e.message,true);}finally{busy=false;$('refresh').disabled=false;}}
$('refresh').onclick=refresh;$('close-player').onclick=stopPlayer;$('player').onerror=()=>status('本地播放失败：缓存可能已到期、播放许可过期，或浏览器不支持该编码。请刷新后重新播放。',true);
refresh();setInterval(()=>{if(!document.hidden)refresh();},5000);
