"""Production DOM, synthetic ASR/Chrome bridge; no real Edge capture/model/network video."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from browser_support import browser_executable, screenshot_path
ROOT=Path(__file__).resolve().parents[1];EXT=ROOT/'extension'
SHIM=r'''
window.__calls=[];window.__saved={};window.__listeners=[];window.__running=false;window.__paused=false;
window.chrome={runtime:{lastError:null,onMessage:{addListener(f){window.__listeners.push(f);}},sendMessage(m,reply){window.__calls.push(m);let data={};
 if(m.type==='VKN_GET_SESSION')data=window.__saved[m.key]||null;
 if(m.type==='VKN_SAVE_SESSION'){window.__saved[m.session.key]=structuredClone(m.session);data={saved:true};}
 if(m.type==='VKN_AI_STATUS')data={configured:true,enabled:true,provider:'ollama',model:'qwen2.5:3b',summaryMinutes:5,autoSummary:false,version:'0.8.0'};
 if(m.type==='VKN_ASR_STATUS_QUERY')data={running:window.__running,paused:window.__paused};
 if(m.type==='VKN_ASR_START'){window.__running=true;data={running:true,tabId:1};}
 if(m.type==='VKN_ASR_STOP_ALL'){window.__running=false;data={running:false,draining:true};}
 if(m.type==='VKN_ASR_PAUSE'){window.__paused=true;data={running:true,paused:true};}
 if(m.type==='VKN_ASR_RESUME'){window.__paused=false;data={running:true,paused:false};}
 if(m.type==='VKN_CACHE_CREATE')data={id:'c'.repeat(32),state:'queued'};
 if(m.type==='VKN_CACHE_OPEN')data={opened:true};
 if(m.type==='VKN_AI_GENERATE')data={markdown:'## 整理结果（测试数据）\n\n[00:01] 已保留主持人与其他说话人的不同观点。\n\n## 听写短语校对记录\n\n本页只是界面测试，未调用真实模型。',mode:'knowledge',model:'fixture',blocks:1,cueCount:m.cues.length};
 const response={ok:true,data};if(reply){reply(response);return;}return Promise.resolve(response);
}},storage:{onChanged:{addListener(){}}}};
window.emitCue=(i,text)=>{const sid='d'.repeat(32),key='web:'+location.origin+location.pathname;
 const c={id:sid+':'+(i+1)+':0',revision:1,time:3*i+1,text,original:text,source:'local-asr',speakerId:sid+':spk'+(i%2+1),speakerStatus:'estimated'};
 for(const f of window.__listeners)f({type:'VKN_ASR_EVENT',sessionKey:key,kind:'segment',data:c},{},()=>{});
};
'''
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=browser_executable(),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page=browser.new_page(viewport={'width':1365,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content('<html><head><title>功能测试 · 非真实节目</title></head><body style="background:#172737"><h1>对话节目 · 测试数据</h1><video style="width:600px;height:300px"></video><div class="caption-text">这段网页字幕不应自动录入</div></body></html>')
    page.evaluate(SHIM);page.evaluate("() => {const original=Element.prototype.attachShadow;Element.prototype.attachShadow=function(o){return original.call(this,{...o,mode:'open'});};}")
    page.add_script_tag(path=str(EXT/'core.js'));page.add_script_tag(path=str(EXT/'content.js'));page.wait_for_timeout(1300);page.locator('#vkn-bubble').click()
    expect(page.locator('#vkn-count')).to_have_text('0');assert not any(m['type']=='VKN_GET_PLATFORM' for m in page.evaluate('window.__calls'))
    for selector in ['#vkn-fetch','#vkn-enable-cc','#vkn-caption-toggle']:expect(page.locator(selector)).to_have_count(0)
    expect(page.locator('#vkn-context-review')).to_be_checked();assert not page.locator('#vkn-transcript').evaluate('(e)=>e.open')
    page.locator('#vkn-asr').click();expect(page.locator('#vkn-record')).to_be_visible();page.locator('#vkn-record').click();expect(page.locator('#vkn-record')).to_have_text('继续听写');page.locator('#vkn-record').click();expect(page.locator('#vkn-record')).to_have_text('暂停听写')
    page.evaluate("window.emitCue(0,'大家好，我是本期主持人，欢迎收听今天的讨论。');window.emitCue(1,'我觉得需要先保留原话，再讨论怎样整理。');")
    page.locator('#vkn-tools > summary').click();page.locator('#vkn-speakers > summary').click();expect(page.locator('#vkn-speaker-list input')).to_have_count(0);expect(page.locator('#vkn-speaker-list')).to_contain_text('主持人 · 说话人1');expect(page.locator('#vkn-speaker-list')).to_contain_text('说话人2')
    page.locator('#vkn-tools > summary').click()
    page.on('dialog',lambda d:d.accept());page.locator('#vkn-video-cache').click();expect(page.locator('#vkn-cache-hint')).to_contain_text('下载队列');page.locator('#vkn-cache-library').click();assert any(m['type']=='VKN_CACHE_OPEN' for m in page.evaluate('window.__calls'))
    page.locator('#vkn-ai').click();expect(page.locator('#vkn-preview')).to_contain_text('测试数据');call=[m for m in page.evaluate('window.__calls') if m['type']=='VKN_AI_GENERATE'][-1];assert call['writing']['correctPhrases'] is True;assert call['cues'][0]['speakerLabel']=='主持人 · 说话人1'
    page.locator('#vkn-stop-all').click();expect(page.locator('#vkn-asr')).to_be_visible()
    for width in [1365,760,390]:
        page.set_viewport_size({'width':width,'height':1000});page.locator('#vkn-title').scroll_into_view_if_needed();assert page.locator('#vkn-panel').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
        page.locator('#vkn-panel').screenshot(path=str(screenshot_path(f'UI_V080_{width}.png')))
    assert not errors,errors
    print('PASS speech-only DOM, auto-role evidence, cache actions, correction option, stop/pause and 3 widths (synthetic Chrome/ASR)')
    # Cache management page uses real production JS, fixture metadata only.
    page=browser.new_page(viewport={'width':1000,'height':900});page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content((EXT/'cache.html').read_text().replace('<script src="cache.js"></script>','').replace('<link rel="stylesheet" href="cache.css">',''));page.add_style_tag(path=str(EXT/'cache.css'))
    page.evaluate(r'''()=>{window.__rows=[{id:'c'.repeat(32),title:'本地缓存测试（合成数据）',state:'ready',size:1048576,completed:Date.now()/1000,expires:Date.now()/1000+259200}];window.chrome={runtime:{lastError:null,sendMessage(m,r){let data={};if(m.type==='VKN_CACHE_LIST')data={directory:'测试缓存目录',capabilities:{message:'测试元数据，未下载实际视频'},items:window.__rows};if(m.type==='VKN_CACHE_DELETE')window.__rows=[];r({ok:true,data});}}};}''')
    page.add_script_tag(path=str(EXT/'cache.js'));expect(page.locator('.card')).to_have_count(1);expect(page.locator('.card')).to_contain_text('到期');page.screenshot(path=str(screenshot_path('CACHE_V080.png')))
    page.on('dialog',lambda d:d.accept());page.get_by_role('button',name='删除缓存',exact=True).click();expect(page.locator('.card')).to_have_count(0);assert not errors,errors
    print('PASS cache library metadata, expiry display and explicit deletion (fixture only)')
    browser.close()
