"""Synthetic Chromium DOM: audio group -> local role metadata -> readable UI.
No actual ASR, role LLM, voice identity or platform content is inferred here.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from browser_support import browser_executable
ROOT=Path(__file__).resolve().parents[1]
EXT=ROOT/'extension'
SHIM=r'''
window.__store={};window.__listeners=[];window.__roleCalls=0;
window.chrome={runtime:{lastError:null,onMessage:{addListener(fn){window.__listeners.push(fn)}},
sendMessage(m,callback){let data={};
 if(m.type==='VKN_GET_SESSION')data=window.__store[m.key]||null;
 else if(m.type==='VKN_SAVE_SESSION'){window.__store[m.session.key]=structuredClone(m.session);data={saved:true};}
 else if(m.type==='VKN_AI_STATUS')data={configured:true,autoSummary:false,summaryMinutes:5,provider:'ollama',model:'qwen2.5:3b',version:'0.12.1'};
 else if(m.type==='VKN_ASR_STATUS_QUERY')data={running:false};
 else if(m.type==='VKN_IDENTIFY_SPEAKERS'){window.__roleCalls++;
  const s=window.__store[m.sessionKey];if(s){s.speakerRoles={...s.speakerRoles};
   for(const [n,role,label] of [[1,'narrator','剧情旁白'],[2,'system','系统播报'],[3,'character','剧情角色']]){
    const id='a'.repeat(32)+':spk'+n;
    const records=s.segments.filter(x=>x.speakerId===id);
    s.speakerRoles[id]={role,label,confidence:'estimated',basis:'dialogue_context',cueIds:records.map(x=>x.id),quotes:records.map(x=>x.original),time:records[0]?.time||0,reason:'模拟的两个时间片段均支持该类别'};
   }
   data={roleUpdated:3,roleChecked:3,updated:0};}
 }
 if(callback){callback({ok:true,data});return;}
 return Promise.resolve({ok:true,data});
}},storage:{onChanged:{addListener(){}}}};
window.__realSetTimeout=window.setTimeout;
window.setTimeout=(fn,ms,...args)=>window.__realSetTimeout(fn,ms===18000?250:ms,...args);
'''
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path=browser_executable(),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
 page=browser.new_page(viewport={'width':1250,'height':950});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.set_content('<html><head><title>三类音色角色演示</title></head><body><video></video></body></html>')
 page.evaluate(SHIM)
 page.evaluate('''()=>{const old=Element.prototype.attachShadow;Element.prototype.attachShadow=function(o){return old.call(this,{...o,mode:'open'});};}''')
 page.add_script_tag(path=str(EXT/'core.js'));page.add_script_tag(path=str(EXT/'content.js'))
 page.wait_for_timeout(1000);page.locator('#vkn-bubble').click()
 page.evaluate('''()=>{
 const prefix='a'.repeat(32),key='web:'+location.origin+location.pathname;
 const lines=[
 ['少年推开门，走进了安静的客厅。',1],['系统提示：任务已经更新。',2],['你为什么来到这里？',3],
 ['与此同时，屋外的天空突然暗了。',1],['宿主当前获得十点经验值。',2],['因为我要寻找自己的家人。',3]];
 lines.forEach(([text,who],i)=>{
 const item={id:prefix+':1:'+(i+1),revision:1,time:1+i*4,text,original:text,speakerId:prefix+':spk'+who,speakerStatus:'estimated',source:'local-asr'};
 for(const f of window.__listeners)f({type:'VKN_ASR_EVENT',sessionKey:key,kind:'segment',data:item},{},()=>{});
 });}''')
 expect(page.locator('#vkn-count')).to_have_text('6')
 page.wait_for_function('window.__roleCalls>=1',timeout=8000)
 page.locator('#vkn-tools > summary').click()
 page.locator('#vkn-speakers > summary').click()
 expect(page.locator('#vkn-speaker-list')).to_contain_text('剧情旁白')
 expect(page.locator('#vkn-speaker-list')).to_contain_text('系统播报')
 expect(page.locator('#vkn-speaker-list')).to_contain_text('剧情角色')
 page.locator('#vkn-transcript > summary').click()
 expect(page.locator('#vkn-live')).to_contain_text('剧情旁白')
 assert not errors, errors
 print('PASS: role labels saved by mocked background, automatically refreshed and displayed without user naming (synthetic audio/LLM).')
 browser.close()
