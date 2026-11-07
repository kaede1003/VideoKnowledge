"""Real Chromium DOM; extension transport, diarization and LLM output are fixtures."""
from browser_support import browser_executable, screenshot_path
from pathlib import Path
import os
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
EXT=ROOT/'extension'
SHIM=r'''
window.__store={};window.__listeners=[];window.__deepCalls=0;window.__deepCues=[];
window.chrome={runtime:{lastError:null,onMessage:{addListener(f){window.__listeners.push(f);}},
sendMessage(m,reply){let data=null;
if(m.type==='VKN_GET_SESSION')data=window.__store[m.key]||null;
if(m.type==='VKN_SAVE_SESSION'){window.__store[m.session.key]=structuredClone(m.session);data={saved:true};}
if(m.type==='VKN_GET_PLATFORM')data={kind:'none',message:'测试：不读取外部字幕'};
if(m.type==='VKN_AI_STATUS')data={configured:true,autoSummary:true,summaryMinutes:5,model:'fixture',provider:'ollama',version:'0.6.0'};
if(m.type==='VKN_ASR_STATUS_QUERY')data={running:false};
if(m.type==='VKN_AI_GENERATE'){window.__deepCalls++;window.__deepCues=m.cues;data={markdown:'## 对话知识整理（测试输出）\n\n- [00:01] 主持人提出问题。\n- [00:04] 嘉宾作答。\n\n本画面为模拟数据，不是实际模型质量测试。',blocks:1};}
if(m.type==='VKN_AI_PERIODIC_SUMMARY'){window.__periodCues=m.cues;data={markdown:'## 阶段摘要（模拟）\n保留说话人归属',mode:'ai'};}
if(reply)reply({ok:true,data});else return Promise.resolve({ok:true,data});}},storage:{onChanged:{addListener(){}}}};
'''
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=browser_executable(),headless=True,args=['--no-sandbox'])
    context=browser.new_context(accept_downloads=True,viewport={'width':1400,'height':1000})
    page=context.new_page();page.set_default_timeout(6000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('about:blank');page.set_content('''<html><head><title>对话说话人测试</title><style>body{background:#10182a;color:white;font:18px Arial;padding:40px}video{width:760px;height:430px;background:#182e48}</style></head><body><h1>对话访谈 · 模拟场景</h1><video></video><p>页面、转写、角色和模型输出均为测试数据。</p></body></html>''')
    page.evaluate(SHIM)
    page.evaluate("""()=>{const f=Element.prototype.attachShadow;Element.prototype.attachShadow=function(o){return f.call(this,{...o,mode:'open'});};Object.defineProperty(document.querySelector('video'),'duration',{get:()=>240});}""")
    page.add_script_tag(path=str(EXT/'core.js'));page.add_script_tag(path=str(EXT/'content.js'))
    page.wait_for_timeout(1300);page.locator('#vkn-bubble').click()
    assert page.locator('#vkn-view-report').is_disabled()
    page.evaluate("""()=>{const sid='d'.repeat(32),key='web:'+location.origin+location.pathname;
    ['为什么需要缓存？','识别慢时先保存音频。','有什么风险？','需要留意磁盘空间。'].forEach((text,i)=>{
    const cue={id:sid+':'+(i+1)+':0',revision:1,time:1+i*3,text,source:'local-asr',language:'zh',speakerId:sid+':spk'+(i%2+1),speakerStatus:'estimated'};
    window.__listeners.forEach(f=>f({type:'VKN_ASR_EVENT',sessionKey:key,kind:'segment',data:cue},{},()=>{}));});}""")
    page.locator('#vkn-transcript > summary').click();page.locator('#vkn-tools > summary').click();page.locator('#vkn-stage-details > summary').click()
    expect(page.locator('#vkn-live')).to_contain_text('说话人1');expect(page.locator('#vkn-live')).to_contain_text('说话人2')
    page.locator('#vkn-speakers > summary').click()
    names=page.locator('#vkn-speaker-list input');names.nth(0).fill('主持人');page.locator('#vkn-speaker-list button').nth(0).click()
    names.nth(1).fill('嘉宾');page.locator('#vkn-speaker-list button').nth(1).click();page.locator('#vkn-title').click()
    expect(page.locator('#vkn-live')).to_contain_text('主持人');expect(page.locator('#vkn-live')).to_contain_text('嘉宾')
    page.locator('#vkn-summary-now').click();page.wait_for_timeout(250)
    assert page.evaluate("window.__periodCues.some(c=>c.speakerLabel==='主持人')")
    assert page.evaluate('window.__deepCalls')==0
    page.locator('#vkn-ai').click();page.wait_for_timeout(300)
    expect(page.locator('#vkn-preview')).to_contain_text('对话知识整理');assert page.locator('#vkn-doc').inner_text()=='AI'
    assert page.evaluate("window.__deepCues.some(c=>c.speakerLabel==='嘉宾')")
    assert page.evaluate('window.__deepCalls')==1
    page.locator('#vkn-view-report').click();assert page.evaluate('window.__deepCalls')==1
    page.wait_for_timeout(200)
    heading=page.locator('#vkn-report-heading').bounding_box();panel=page.locator('#vkn-panel').bounding_box()
    assert panel['y'] < heading['y'] < panel['y']+panel['height'], (heading,panel)
    page.screenshot(path=str(screenshot_path('REPORT_LOCATION_V060.png')))
    with page.expect_popup() as popup:
        page.locator('#vkn-read-full').click()
    doc=popup.value;expect(doc.locator('body')).to_contain_text('对话知识整理');expect(doc.locator('body')).to_contain_text('主持人')
    assert page.evaluate('window.__deepCalls')==1;doc.close()
    page.locator('#vkn-live').scroll_into_view_if_needed()
    page.on('dialog',lambda dialog:dialog.accept('0'))
    page.locator('#vkn-live .speaker').first.click()
    expect(page.locator('#vkn-live .speaker').first).to_contain_text('待确认')
    page.wait_for_timeout(1100)
    assert page.evaluate("Object.keys(Object.values(window.__store)[0].speakerOverrides).length") ==1
    page.screenshot(path=str(screenshot_path('SPEAKERS_V060.png')))
    assert not errors,errors
    print('PASS: speaker labels -> manual names -> periodic/deep prompt -> automatic result navigation -> full document window -> manual correction persisted; all acoustic/model output is fixture data.')
    browser.close()
