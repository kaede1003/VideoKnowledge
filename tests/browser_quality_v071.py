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
    page.evaluate("""()=>{window.emitQuality=(revision=1)=>{const c={id:'a'.repeat(32)+':10:0',revision,time:10,end:12,source:'local-asr',
      text:'It is not certain.',original:'It is not certain.',translation:'这是确定的。',translationStatus:'needs_review',needsReview:true,
      reviewReason:'测试数据：英文否定可能漏译',verificationStatus:'machine_unverified',qualityFlags:['translation_suspect']};
      for(const f of window.__listeners)f({type:'VKN_ASR_EVENT',sessionKey:'web:'+location.origin+location.pathname,kind:'segment',data:c},{},()=>{});
    };window.emitQuality();}""")
    expect(page.locator('#vkn-live-count')).to_contain_text('1条无法自动确认')
    assert not page.locator('#vkn-transcript').evaluate('(e)=>e.open')
    page.locator('#vkn-transcript > summary').click()
    expect(page.locator('#vkn-live .note > p')).to_contain_text('It is not certain.')
    page.locator('#vkn-live details > summary').click()
    expect(page.locator('#vkn-live details')).to_contain_text('译文：这是确定的。')
    page.once('dialog',lambda d:d.accept('这还不确定。（人工修订测试）'))
    page.locator('#vkn-live button',has_text='核对 / 修订').click()
    expect(page.locator('#vkn-live .note > p')).to_contain_text('这还不确定。')
    page.wait_for_timeout(1300)
    s=next(v for k,v in rpc({'op':'get','key':None}).items() if k.startswith('vkn:session:'))
    assert s['segments'][0]['original']=='It is not certain.'
    assert s['textOverrides']['a'*32+':10:0']['text'].startswith('这还不确定')
    page.evaluate('window.emitQuality(2)')
    expect(page.locator('#vkn-live .note > p')).to_contain_text('这还不确定。')
    page.locator('#vkn-transcript > summary').click()
    page.locator('#vkn-tools > summary').click()
    with page.expect_download() as download:page.locator('#vkn-export-audit').click()
    data=json.loads(Path(download.value.path()).read_text(encoding='utf-8-sig'))
    assert data['format']=='vkn-audit-1';assert data['segments'][0]['translation']=='这是确定的。'
    assert data['textOverrides']['a'*32+':10:0']['text'].startswith('这还不确定')
    print('PASS suspect candidate/source separation, human edit persists over incoming ASR, audit export JSON',flush=True)
    page.locator('#vkn-tools > summary').click()
    page.locator('#vkn-ai').click();expect(page.locator('#vkn-preview')).to_contain_text('模拟测试结果',timeout=10000)
    req=next(r for r in reversed(rpc({'op':'requests'})) if r['body'])['body']
    assert '这还不确定' in req['messages'][1]['content'];assert '这是确定的。' not in req['messages'][1]['content']
    page.locator('#vkn-transcript > summary').click();page.locator('#vkn-live details > summary').click();page.once('dialog',lambda d:d.accept());page.locator('#vkn-live button',has_text='撤销修订').click()
    expect(page.locator('#vkn-live .note > p')).to_contain_text('It is not certain.')
    page.locator('#vkn-transcript > summary').click();page.locator('#vkn-ai').click()
    expect(page.locator('#vkn-preview')).to_contain_text('模拟测试结果',timeout=10000)
    page.locator('#vkn-result-details > summary').click()
    expect(page.locator('#vkn-result-audit')).to_contain_text('1条需核查')
    expect(page.locator('#vkn-preview')).not_to_contain_text('资料待核对')
    page.wait_for_timeout(1100)
    s=next(v for k,v in rpc({'op':'get','key':None}).items() if k.startswith('vkn:session:'))
    assert s['documents'][-1]['reviewCount']==1
    print('PASS model input excludes suspect candidate, undo keeps raw, generated report keeps separate source/quality details',flush=True)
    for width in [1365,390]:
        page.set_viewport_size({'width':width,'height':960});page.locator('#vkn-title').scroll_into_view_if_needed()
        assert page.locator('#vkn-panel').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
        page.locator('#vkn-panel').screenshot(path=str(screenshot_path(f'UI_V071_COMPACT_{width}.png')))
    page.set_viewport_size({'width':1365,'height':960});page.locator('#vkn-transcript > summary').click()
    page.locator('#vkn-live details').evaluate('(e)=>e.open=true');page.locator('#vkn-title').scroll_into_view_if_needed()
    page.locator('#vkn-panel').screenshot(path=str(screenshot_path('UI_V071_REVIEW.png')))
    assert not errors,errors
    page.evaluate('window.__closing=true');browser.close()
finally:
    bridge.stdin.close();bridge.wait(timeout=5)
