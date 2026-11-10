"""Real Chromium DOM + actual background via Node VM; Chrome/capture/models are fixtures."""
from browser_support import browser_executable, screenshot_path
from pathlib import Path
import os, json, subprocess, threading
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1];EXT=ROOT/'extension'
bridge=subprocess.Popen(['node',str(ROOT/'tests/writing_bridge.js')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1)
lock=threading.Lock()
def rpc(q):
    with lock:
        bridge.stdin.write(json.dumps(q,ensure_ascii=False)+'\n');bridge.stdin.flush()
        line=bridge.stdout.readline()
        if not line:raise RuntimeError('bridge closed')
        r=json.loads(line)
        if not r['ok']:raise RuntimeError(r['error'])
        return r.get('data')
SHIM=r'''
window.__listeners=[];window.__running=false;window.__paused=false;window.__deepCalls=0;window.__defer=false;window.__requests=[];
window.chrome={runtime:{lastError:null,onMessage:{addListener(f){window.__listeners.push(f);}},sendMessage(m,reply){
if(window.__closing){if(reply)reply({ok:true,data:{saved:true}});else return Promise.resolve({ok:true,data:{saved:true}});return;}
window.__requests.push(m.type);
let data=null,local=true;
if(m.type==='VKN_GET_PLATFORM')data={kind:'none',message:'测试：不读取外部网站字幕'};
else if(m.type==='VKN_ASR_STATUS_QUERY')data={running:window.__running,paused:window.__paused,sessionKey:'web:'+location.origin+location.pathname,tabId:1};
else if(m.type==='VKN_ASR_START'){if(window.__defer){window.__startReply=reply;return;}window.__running=true;data={running:true,tabId:1};}
else if(m.type==='VKN_ASR_STOP_ALL'||m.type==='VKN_ASR_STOP'){window.__running=false;data={running:false,draining:true};}
else if(m.type==='VKN_ASR_PAUSE'){window.__paused=true;data={running:true,paused:true};}
else if(m.type==='VKN_ASR_RESUME'){window.__paused=false;data={running:true,paused:false};}
else if(m.type==='VKN_LORA_STATUS')data={running:false};
else if(m.type==='VKN_AI_GENERATE'&&window.__holdGenerate){window.__heldReply=reply;window.__deepCalls++;return;}
else {local=false;if(m.type==='VKN_AI_GENERATE')window.__deepCalls++;}
const p=local?Promise.resolve({ok:true,data}):window.bridgeRPC({op:'send',message:m});
if(reply){p.then(reply);return;}return p;
}},storage:{onChanged:{addListener(){}}}};
window.emitCue=(i,text)=>{const sid='d'.repeat(32),key='web:'+location.origin+location.pathname;
 const c={id:sid+':'+(i+1)+':0',revision:1,time:i*3+2,text:text||'测试发言 '+(i+1)+'：先保存资料，再核对观点。',source:'local-asr',speakerId:sid+':spk'+(i%2+1),speakerStatus:'estimated'};
 for(const f of window.__listeners)f({type:'VKN_ASR_EVENT',sessionKey:key,kind:'segment',data:c},{},()=>{});
};
'''
def load_page(browser,width=1365):
    p=browser.new_page(viewport={'width':width,'height':960},accept_downloads=True);p.expose_function('bridgeRPC',rpc)
    errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
    p.goto('about:blank');p.set_content('''<html lang="zh-CN"><head><title>对话节目 · 功能测试</title><style>body{background:#101824;color:#d7e2f0;font:16px system-ui;margin:0;padding:36px}h1{font-size:23px;font-weight:500}video{display:block;width:60vw;height:420px;background:#1a2a3b;border-radius:12px}p{max-width:750px;color:#93a8bc}</style></head><body><h1>对话节目：从记录到整理</h1><video></video><p>本页面、转写和模型输出均为模拟数据，用于界面与流程测试。</p></body></html>''')
    p.evaluate(SHIM)
    p.evaluate("""()=>{const original=Element.prototype.attachShadow;Element.prototype.attachShadow=function(o){return original.call(this,{...o,mode:'open'});};Object.defineProperty(document.querySelector('video'),'duration',{get:()=>240});}""")
    p.add_script_tag(path=str(EXT/'core.js'));p.add_script_tag(path=str(EXT/'content.js'))
    p.wait_for_timeout(600);p.locator('#vkn-bubble').click();return p,errors
try:
 with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=browser_executable(),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page,errors=load_page(browser)
    assert not page.locator('#vkn-transcript').evaluate('(e)=>e.open');assert not page.locator('#vkn-tools').evaluate('(e)=>e.open')
    page.evaluate('()=>{for(let i=0;i<45;i++)window.emitCue(i);}')
    expect(page.locator('#vkn-count')).to_have_text('45');assert page.locator('#vkn-live .note').count()==0
    page.wait_for_timeout(1300)
    saved=rpc({'op':'get','key':None});session=next(v for k,v in saved.items() if k.startswith('vkn:session:'))
    assert len(session['segments'])==45
    page.locator('#vkn-transcript > summary').click();expect(page.locator('#vkn-live .note')).to_have_count(30)
    page.locator('#vkn-load-more').click();expect(page.locator('#vkn-live .note')).to_have_count(45)
    page.locator('#vkn-transcript > summary').click();page.evaluate("emitCue(45,'新增记录，不得自动展开。')")
    assert not page.locator('#vkn-transcript').evaluate('(e)=>e.open');expect(page.locator('#vkn-live-count')).to_contain_text('46条')
    assert page.evaluate('window.__deepCalls')==0
    print('PASS folded view does not render or discard records; load older; incoming cue does not expand; persisted full source',flush=True)
    # Single-click capture, independent stop during start, pause/resume.
    page.locator('#vkn-asr').click();expect(page.locator('#vkn-record')).to_be_visible();page.locator('#vkn-record').click();expect(page.locator('#vkn-record')).to_contain_text('继续')
    page.locator('#vkn-record').click();expect(page.locator('#vkn-record')).to_contain_text('暂停');page.locator('#vkn-stop-all').click();expect(page.locator('#vkn-asr')).to_be_visible()
    page.evaluate('window.__defer=true');page.locator('#vkn-asr').click();expect(page.locator('#vkn-stop-all')).to_be_enabled();page.locator('#vkn-stop-all').click()
    page.evaluate("window.__startReply({ok:true,data:{running:true,tabId:1}});window.__defer=false")
    expect(page.locator('#vkn-asr')).to_be_visible();expect(page.locator('#vkn-asr')).to_be_enabled()
    print('PASS compact capture controls: one start, pause, resume, stop while starting; stale start ignored',flush=True)
    # Knowledge generation uses production background, saves history, opens result.
    page.locator('#vkn-ai').click();expect(page.locator('#vkn-preview')).to_contain_text('知识文档 · 模拟测试结果',timeout=10000)
    expect(page.locator('#vkn-generated')).to_contain_text('知识整理');assert page.evaluate('window.__deepCalls')==1
    page.locator('#vkn-view-report').click();assert page.evaluate('window.__deepCalls')==1
    page.locator('#vkn-mode').select_option('custom');page.locator('#vkn-requirements > summary').click();page.locator('#vkn-instructions').fill('按场景分段，保留角色对白，不增加剧情。')
    page.locator('#vkn-ai').click();expect(page.locator('#vkn-preview')).to_contain_text('自定义 · 模拟测试结果',timeout=10000)
    expect(page.locator('#vkn-document-picker option')).to_have_count(2)
    requests=rpc({'op':'requests'});assert '按场景分段' in next(x for x in reversed(requests) if x['body'])['body']['messages'][1]['content']
    page.locator('#vkn-requirements > summary').click();page.evaluate("()=>{for(const f of window.__listeners)f({type:'VKN_ASR_EVENT',sessionKey:'web:'+location.origin+location.pathname,kind:'drained',data:{}},{},()=>{});}");page.wait_for_timeout(1100);page.locator('#vkn-title').scroll_into_view_if_needed()
    page.locator('#vkn-panel').screenshot(path=str(screenshot_path('UI_V070_COMPACT.png')))
    print('PASS knowledge and custom prompts, source kept, two immutable results selectable',flush=True)
    page.locator('#vkn-mode').select_option('custom');page.locator('#vkn-requirements > summary').click();page.locator('#vkn-instructions').fill('用原创方式改写表达，但保留基础观点。');page.locator('#vkn-creative').check()
    page.locator('#vkn-ai').click();expect(page.locator('#vkn-generated')).to_contain_text('创作改写',timeout=10000)
    page.locator('#vkn-mode').select_option('transcript');assert not page.locator('#vkn-creative').is_checked();page.locator('#vkn-instructions').fill('保留问答顺序。')
    page.locator('#vkn-range-start').fill('00:05');page.locator('#vkn-range-end').fill('00:11');page.locator('#vkn-ai').click();expect(page.locator('#vkn-preview')).to_contain_text('测试发言 2',timeout=10000)
    expect(page.locator('#vkn-preview')).not_to_contain_text('测试发言 1：')
    expect(page.locator('#vkn-report-hint')).to_contain_text('3 条记录')
    page.locator('#vkn-mode').select_option('custom');expect(page.locator('#vkn-requirements')).to_have_js_property('open',True)
    page.locator('#vkn-instructions').fill('');n=page.evaluate('window.__deepCalls');page.locator('#vkn-ai').click();expect(page.locator('#vkn-status')).to_contain_text('自定义整理要求');assert page.evaluate('window.__deepCalls')==n
    page.locator('#vkn-instructions').fill('整理成中文问答稿，保留不同说话人的观点。');page.locator('#vkn-range-start').fill('');page.locator('#vkn-range-end').fill('');page.locator('#vkn-ai').click()
    expect(page.locator('#vkn-preview')).to_contain_text('自定义 · 模拟测试结果',timeout=10000);expect(page.locator('#vkn-document-picker option')).to_have_count(5)
    print('PASS three authoring modes and five generated documents, opt-in creative boundary, time range, missing instructions reject without call',flush=True)
    # Choosing previous output and exporting never invokes model or appends raw transcript.
    options=page.locator('#vkn-document-picker option');script_id=next(o.get_attribute('value') for o in options.all() if '自定义' in o.inner_text())
    before=page.evaluate('window.__deepCalls');page.locator('#vkn-document-picker').select_option(script_id);expect(page.locator('#vkn-preview')).to_contain_text('自定义 · 模拟测试结果')
    with page.expect_popup() as popup:page.locator('#vkn-read-full').click()
    doc=popup.value;expect(doc.locator('body')).to_contain_text('按用户要求整理');assert '测试发言 40' not in doc.locator('body').inner_text();doc.close()
    page.locator('#vkn-export-menu > summary').click()
    with page.expect_download() as d:page.locator('#vkn-md').click()
    path=Path(d.value.path());text=path.read_text(encoding='utf-8-sig');assert '自定义' in text and '测试发言 40' not in text
    assert page.evaluate('window.__deepCalls')==before
    page.wait_for_timeout(1200);session=next(v for k,v in rpc({'op':'get','key':None}).items() if k.startswith('vkn:session:'))
    assert len(session['documents'])==5 and len(session['segments'])==46 and session['activeDocumentId']==script_id
    print('PASS selected result full reader/export and history persisted without overwriting raw records',flush=True)
    # Failure and cancellation must not replace an existing output.
    rpc({'op':'failNext'});page.locator('#vkn-ai').click();expect(page.locator('#vkn-status')).to_contain_text('生成失败',timeout=10000)
    expect(page.locator('#vkn-preview')).to_contain_text('自定义 · 模拟测试结果');expect(page.locator('#vkn-document-picker option')).to_have_count(5)
    page.evaluate('window.__holdGenerate=true');page.locator('#vkn-ai').click();expect(page.locator('#vkn-ai-cancel')).to_be_visible();page.locator('#vkn-ai-cancel').click()
    page.evaluate("window.__heldReply({ok:true,data:{markdown:'不应保存的迟到输出',blocks:1}});window.__holdGenerate=false")
    expect(page.locator('#vkn-preview')).not_to_contain_text('迟到输出');expect(page.locator('#vkn-document-picker option')).to_have_count(5)
    assert not errors,errors
    print('PASS failure/cancellation/late output preserve old documents',flush=True)
    # Fold preferences, modes and current result survive reloading the content script page.
    page.locator('#vkn-tools > summary').click();page.locator('#vkn-stage-details > summary').click();page.locator('#vkn-summary-now').click();expect(page.locator('#vkn-summaries')).to_contain_text('离线摘录')
    page.locator('#vkn-speakers > summary').click();expect(page.locator('#vkn-speaker-list input')).to_have_count(0)
    expect(page.locator('#vkn-speaker-list')).to_contain_text('说话人1')
    expect(page.locator('#vkn-speaker-list')).to_contain_text('说话人2')
    page.locator('#vkn-tools > summary').click();page.wait_for_timeout(1300);page.evaluate('window.__closing=true');page.close()
    page,errors=load_page(browser);expect(page.locator('#vkn-document-picker option')).to_have_count(5);expect(page.locator('#vkn-preview')).to_contain_text('自定义 · 模拟测试结果')
    assert not page.locator('#vkn-transcript').evaluate('(e)=>e.open');assert not page.locator('#vkn-tools').evaluate('(e)=>e.open')
    print('PASS persisted selected result/form/collapse and optional stage/speaker tools',flush=True)
    for width in [1365,760,390]:
        page.set_viewport_size({'width':width,'height':960});page.locator('#vkn-title').scroll_into_view_if_needed()
        panel=page.locator('#vkn-panel');assert panel.evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
        assert page.locator('#vkn-mode').evaluate('(e)=>e.getBoundingClientRect().right<=innerWidth')
        page.locator('#vkn-panel').screenshot(path=str(screenshot_path(f'UI_V070_{width}.png')))
        print('PASS compact panel bounds',width,flush=True)
    assert not errors,errors;page.evaluate('window.__closing=true');browser.close()
finally:
    bridge.stdin.close();bridge.wait(timeout=5)
