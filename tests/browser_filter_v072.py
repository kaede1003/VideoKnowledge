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
    p.evaluate("""()=>{const original=window.setInterval;window.setInterval=(fn,ms)=>{if(ms===5000){window.__filterTick=fn;return -1;}return original(fn,ms);};}""")
    p.add_script_tag(path=str(EXT/'core.js'));p.add_script_tag(path=str(EXT/'content.js'))
    p.wait_for_timeout(600);p.locator('#vkn-bubble').click();return p,errors
try:
 with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=browser_executable(),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page,errors=load_page(browser)
    page.evaluate("""()=>{
      window.emitCue(0,'嘉宾并不同意这个观点，随后分享了自己的经历。');
      window.emitCue(1,'宪教设计的时候 '.repeat(18));
      window.emitCue(2,'请上我们的官方网站报名，完整说明都在网站。');
      window.emitCue(3,'不，不，不。这个问题还有另外一种解释。');
    }""")
    expect(page.locator('#vkn-filter-count')).to_contain_text('纳入2 · 待核对1 · 排除1')
    assert not page.locator('#vkn-transcript').evaluate('(e)=>e.open')
    assert not page.locator('#vkn-filter-details').evaluate('(e)=>e.open')
    assert not page.locator('#vkn-filter-semantic').is_checked()
    assert not any(x['body'] for x in rpc({'op':'requests'})), 'Default filter MUST NOT call model'
    page.locator('#vkn-ai').click()
    expect(page.locator('#vkn-preview')).to_contain_text('模拟测试结果',timeout=10000)
    expect(page.locator('#vkn-result-audit')).to_contain_text('2/4条纳入')
    req=next(r for r in reversed(rpc({'op':'requests'})) if r['body'])['body']
    assert '宪教设计的时候' not in req['messages'][1]['content']
    assert '官方网站报名' not in req['messages'][1]['content']
    assert '不同意' in req['messages'][1]['content']
    page.wait_for_timeout(1100)
    saved=next(v for k,v in rpc({'op':'get','key':None}).items() if k.startswith('vkn:session:'))
    assert len(saved['segments'])==4
    assert saved['documents'][-1]['screening']=={'enabled':True,'excluded':1,'held':1,'included':2,'total':4}
    print('PASS default no extra inference; original 4 records preserved, only 2 supplied as knowledge evidence',flush=True)
    page.locator('#vkn-filter-details > summary').click()
    page.locator('#vkn-filter-review .note',has_text='官方网站').get_by_role('button',name='纳入整理',exact=True).click()
    expect(page.locator('#vkn-filter-count')).to_contain_text('纳入3 · 待核对1 · 排除0')
    page.wait_for_timeout(1100)
    saved=next(v for k,v in rpc({'op':'get','key':None}).items() if k.startswith('vkn:session:'))
    assert list(saved['filterOverrides'].values())==['keep']
    page.locator('#vkn-filter-review .note',has_text='官方网站').get_by_role('button',name='恢复自动判断',exact=True).click()
    expect(page.locator('#vkn-filter-count')).to_contain_text('纳入2 · 待核对1 · 排除1')
    page.locator('#vkn-filter-enabled').uncheck()
    expect(page.locator('#vkn-filter-count')).to_have_text('已关闭')
    page.locator('#vkn-ai').click()
    expect(page.locator('#vkn-document-picker')).to_be_visible(timeout=10000)
    page.wait_for_timeout(400)
    req=next(r for r in reversed(rpc({'op':'requests'})) if r['body'])['body']
    assert '官方网站报名' in req['messages'][1]['content'] and '宪教设计的时候' in req['messages'][1]['content']
    page.locator('#vkn-filter-enabled').check()
    print('PASS include, revert, disable reversible; no destructive modification',flush=True)
    page.locator('#vkn-filter-topic').fill('只整理主要讨论，排除报名宣传')
    page.locator('#vkn-filter-topic').press('Tab')
    expect(page.locator('#vkn-filter-count')).to_contain_text('排除1')
    page.locator('#vkn-filter-details > summary').click()
    page.locator('#vkn-mode').select_option('transcript')
    page.locator('#vkn-ai').click()
    expect(page.locator('#vkn-preview')).to_contain_text('宪教设计的时候',timeout=10000)
    req=next(r for r in reversed(rpc({'op':'requests'})) if r['body'])['body']
    assert '宪教设计的时候' in req['messages'][1]['content']
    page.locator('#vkn-mode').select_option('knowledge')
    print('PASS transcript/narrative retains full source; knowledge resumes screening',flush=True)
    page.locator('#vkn-tools > summary').click()
    with page.expect_download() as download:page.locator('#vkn-export-audit').click()
    data=json.loads(Path(download.value.path()).read_text(encoding='utf-8-sig'))
    assert len(data['segments'])==4 and data['contentFilter']['enabled']
    page.locator('#vkn-tools > summary').click()
    for width in [1365,760,390]:
        page.set_viewport_size({'width':width,'height':960});page.locator('#vkn-title').scroll_into_view_if_needed()
        assert page.locator('#vkn-panel').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
        page.locator('#vkn-panel').screenshot(path=str(screenshot_path(f'UI_V072_FILTER_{width}.png')))
    page.set_viewport_size({'width':1365,'height':1100});page.locator('#vkn-filter-details > summary').click()
    page.locator('#vkn-filter-details').scroll_into_view_if_needed();page.locator('#vkn-panel').screenshot(path=str(screenshot_path('UI_V072_FILTER_REVIEW.png')))
    page.locator('#vkn-filter-semantic').check()
    page.locator('#vkn-asr').click()
    expect(page.locator('#vkn-stop-all')).to_be_visible()
    page.evaluate("() => {window.__clock=Date.now;window.__offset=61000;Date.now=()=>window.__clock()+window.__offset;}")
    page.evaluate('async()=>await window.__filterTick()')
    expect(page.locator('#vkn-filter-status')).to_contain_text('已完成本批主题判断')
    page.wait_for_timeout(1100)
    saved=next(v for k,v in rpc({'op':'get','key':None}).items() if k.startswith('vkn:session:'))
    assert len(saved['filterAssessments'])>0
    n=len([r for r in rpc({'op':'requests'}) if r['body']])
    page.evaluate('async()=>{window.__offset+=61000;await window.__filterTick();}')
    assert len([r for r in rpc({'op':'requests'}) if r['body']])==n
    page.locator('#vkn-stop-all').click()
    expect(page.locator('#vkn-asr')).to_be_visible()
    page.evaluate('async()=>{window.__offset+=61000;await window.__filterTick();}')
    assert len([r for r in rpc({'op':'requests'}) if r['body']])==n
    print('PASS optional classifier opt-in timer, actual worker routing, cache reuse and stop; local model mocked',flush=True)
    assert not errors,errors
    print('PASS full audit export and 1365/760/390px layout, no browser JS errors',flush=True)
    page.evaluate('window.__closing=true');browser.close()
finally:
    bridge.stdin.close();bridge.wait(timeout=5)
