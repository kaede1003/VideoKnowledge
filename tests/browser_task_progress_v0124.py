"""Chromium DOM fixture for longform stage progress; not a real Edge/Ollama job."""
from browser_support import browser_executable, screenshot_path
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1];EXT=ROOT/'extension'
SHIM=r'''
window.__listeners=[];window.__generate=null;window.__requests=[];
window.chrome={runtime:{lastError:null,onMessage:{addListener(fn){window.__listeners.push(fn)}},sendMessage(m,cb){
 window.__requests.push(m.type);
 if(m.type==='VKN_AI_GENERATE'){window.__generate={m,cb};return;}
 let data=null;
 if(m.type==='VKN_GET_SESSION')data=null;
 else if(m.type==='VKN_SAVE_SESSION')data={count:m.session.segments.length};
 else if(m.type==='VKN_AI_STATUS')data={configured:true,model:'local',provider:'ollama',summaryMinutes:5};
 else if(m.type==='VKN_ASR_STATUS_QUERY')data={running:false,paused:false};
 else if(m.type==='VKN_LORA_STATUS')data={running:false};
 else if(m.type==='VKN_AI_CANCEL')data={cancelled:true};
 if(typeof cb==='function')cb({ok:true,data});
}},storage:{onChanged:{addListener(){}}}};
window.sendProgress=(phase,index,total,round)=>{
 if(!window.__generate)throw Error('No active longform generation');
 const requestId=window.__generate.m.requestId;
 for(const fn of window.__listeners)fn({type:'VKN_WRITING_PROGRESS',requestId,phase,index,total,round},{},()=>{});
};
window.addCue=()=>{
 const key='web:'+location.origin+location.pathname;
 for(const fn of window.__listeners)fn({type:'VKN_ASR_EVENT',sessionKey:key,kind:'segment',data:{id:'e'.repeat(32)+':1:0',revision:1,time:10,end:13,text:'案例和独立论据。',source:'local-asr'}},{},()=>{});
};
'''
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path=browser_executable(),headless=True,args=['--no-sandbox','--disable-dev-shm-usage']);page=browser.new_page(viewport={'width':1120,'height':820});errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('about:blank');page.set_content('''<html lang="zh"><head><title>合成访谈视频</title></head><body><h1>合成访谈视频</h1><video></video></body></html>''')
 page.evaluate(SHIM)
 page.evaluate('''()=>{let attach=Element.prototype.attachShadow;Element.prototype.attachShadow=function(o){return attach.call(this,{...o,mode:'open'})}}''')
 page.add_script_tag(path=str(EXT/'core.js'));page.add_script_tag(path=str(EXT/'content.js'))
 page.wait_for_timeout(600);page.locator('#vkn-bubble').click();page.evaluate('addCue()')
 expect(page.locator('#vkn-ai')).to_be_enabled(timeout=4000)
 page.locator('#vkn-ai').click();expect(page.locator('#vkn-task-progress')).to_be_visible(timeout=2500)
 expect(page.locator('#vkn-task-stage-number')).to_have_text('准备中')
 page.evaluate("sendProgress('汇总全局主题',55,148,1)")
 expect(page.locator('#vkn-task-stage-number')).to_have_text('阶段 2 / 4')
 assert '合成访谈视频' in page.locator('#vkn-task-video').get_attribute('title')
 expect(page.locator('#vkn-task-count')).to_contain_text('已完成 54 / 148 批')
 expect(page.locator('#vkn-task-percent')).to_contain_text('36%')
 assert page.locator('#vkn-task-meter').evaluate('(e)=>e.value')==54
 page.wait_for_timeout(350)
 page.locator('#vkn-task-progress').screenshot(path=str(screenshot_path('UI_V0124_TASK_PROGRESS.png')))
 page.evaluate("sendProgress('汇总全局主题',1,148,1)")
 expect(page.locator('#vkn-task-count')).to_contain_text('54 / 148')
 page.evaluate("sendProgress('汇总全局主题',1,50,2)")
 expect(page.locator('#vkn-task-stage')).to_contain_text('第 2 轮')
 assert page.locator('#vkn-task-meter').evaluate('(e)=>e.value')==0
 page.locator('#vkn-close').click();expect(page.locator('#vkn-bubble')).to_contain_text('AI整理中')
 page.locator('#vkn-bubble').click();expect(page.locator('#vkn-task-progress')).to_be_visible()
 page.locator('#vkn-ai-cancel').click();expect(page.locator('#vkn-task-progress')).to_be_hidden()
 assert not errors,errors
 browser.close()
print('PASS task progress: per-stage percent, stable replay, hierarchy round, collapse/reopen and cancel')
