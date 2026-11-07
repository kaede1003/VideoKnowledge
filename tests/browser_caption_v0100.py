"""Real DOM/production content+core, actual pure Python validator; Chrome/audio/LLM are fixtures."""
from pathlib import Path
import ast,json,subprocess,threading,sys
from playwright.sync_api import sync_playwright,expect
from browser_support import browser_executable,screenshot_path
ROOT=Path(__file__).resolve().parents[1];EXT=ROOT/'extension';sys.path.insert(0,str(ROOT))
from server.caption_review import validate
BASE=ast.parse((ROOT/'tests/browser_writing_v070.py').read_text())
SHIM=next(ast.literal_eval(n.value) for n in BASE.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SHIM' for t in n.targets))
SHIM=SHIM.replace("if(m.type==='VKN_GET_PLATFORM')", "if(m.type==='VKN_CAPTION_VALIDATE'){const p=window.validateCaption(m.data).then(data=>({ok:true,data}));if(reply){p.then(reply);return;}return p;}\nelse if(m.type==='VKN_CAPTION_CLOCK')data={running:window.__running,streamSessionId:'b'.repeat(32),contextEpoch:window.__epoch};\nelse if(m.type==='VKN_CAPTION_FRAME')data={observations:[],warning:'fixture: vision not run'};\nelse if(m.type==='VKN_CAPTION_CANCEL')data={cancelled:true};\nelse if(m.type==='VKN_GET_PLATFORM')")
bridge=subprocess.Popen(['node',str(ROOT/'tests/writing_bridge.js')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1)
lock=threading.Lock()
def rpc(q):
    with lock:
        bridge.stdin.write(json.dumps(q,ensure_ascii=False)+'\n');bridge.stdin.flush();line=bridge.stdout.readline()
        if not line:raise RuntimeError('bridge closed')
        r=json.loads(line)
        if not r['ok']:raise RuntimeError(r['error'])
        return r.get('data')
def validator(data):return validate(data,checker=lambda a,b:(a,b)==('位置','未知'))
try:
 with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=browser_executable(),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page=browser.new_page(viewport={'width':1365,'height':960},accept_downloads=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.expose_function('bridgeRPC',rpc);page.expose_function('validateCaption',validator)
    page.set_content('''<html lang="zh-CN"><head><title>字幕校对与完整发言 · 合成测试</title></head><body style="margin:0;background:#142233;color:#d9e6f5;font:18px system-ui;min-height:2000px"><h1 style="margin:25px">字幕校对 · 合成测试数据</h1><div style="position:relative;margin-left:25px;width:700px;height:390px"><video style="width:700px;height:390px;background:#1c3549;border-radius:20px"></video><div class="ytp-caption-window-container" style="position:absolute;bottom:35px;left:55px"><span class="ytp-caption-segment" style="background:#000b;color:white;padding:8px">人们很害怕未知的事情</span></div></div><p style="margin-left:25px">字幕与听写均为合成输入；不是模型准确率演示。</p></body></html>''')
    page.evaluate(SHIM)
    page.evaluate('''()=>{window.__time=1;window.__epoch=0;window.__videoPaused=false;const v=document.querySelector('video');Object.defineProperty(v,'currentTime',{get:()=>window.__time});Object.defineProperty(v,'duration',{get:()=>180});Object.defineProperty(v,'paused',{get:()=>window.__videoPaused});const old=Element.prototype.attachShadow;Element.prototype.attachShadow=function(o){return old.call(this,{...o,mode:'open'});};window.emit=(seq,time,end,text,speaker=1,status='estimated')=>{const sid='b'.repeat(32),data={id:sid+':'+seq+':0',revision:1,time,end,text,original:text,language:'zh',source:'local-asr',speakerId:sid+':spk'+speaker,speakerStatus:status,contextEpoch:window.__epoch};for(const f of window.__listeners)f({type:'VKN_ASR_EVENT',sessionKey:'web:'+location.origin+location.pathname,kind:'segment',data},{},()=>{});};}''')
    page.add_script_tag(path=str(EXT/'core.js'));page.add_script_tag(path=str(EXT/'caption-review.js'))
    source=(EXT/'content.js').read_text().replace('setInterval(()=>captionTick().catch(()=>{}),500);','window.__captionTick=captionTick;')
    page.add_script_tag(content=source);page.wait_for_timeout(650);page.locator('#vkn-bubble').click()
    assert page.locator('#vkn-filter-enabled').count()==0 and page.locator('#vkn-filter-details').count()==0
    assert page.locator('#vkn-result-section').is_hidden()
    page.locator('#vkn-asr').click();page.evaluate('async()=>{await window.__captionTick();}');page.wait_for_timeout(60)
    page.evaluate('async()=>{await window.__captionTick();window.__time=1.8;await window.__captionTick();}')
    page.evaluate("emit(1,1,3,'人们很害怕位置的事情')")
    page.wait_for_timeout(2100);page.evaluate('async()=>await window.__captionTick()')
    page.locator('#vkn-transcript > summary').click();expect(page.locator('#vkn-live')).to_contain_text('人们很害怕未知的事情')
    expect(page.locator('#vkn-caption-count')).to_contain_text('1')
    page.wait_for_timeout(1300);saved=next(v for k,v in rpc({'op':'get','key':None}).items() if k.startswith('vkn:session:'))
    assert saved['segments'][0]['original']=='人们很害怕位置的事情' and saved['captionReviews'][saved['segments'][0]['id']]['status']=='applied'
    assert len(saved['segments'])==1 and len(saved['captionObservations'])==1
    page.locator('#vkn-caption-details > summary').click();page.locator('#vkn-panel .body').evaluate('(e)=>e.scrollTop=0');page.locator('#vkn-panel').screenshot(path=str(screenshot_path('V0100_CAPTION_REVIEW.png')));page.locator('#vkn-caption-details > summary').click()
    print('PASS real caption DOM -> timestamp evidence -> production Python short-edit validator -> corrected display; raw ASR and one-row identity retained',flush=True)
    # Adjacent one-character tail and a different speaker must produce two turns, never an orphan tail or merged speakers.
    page.evaluate("emit(2,3.2,4,'啊',1,'unknown');emit(3,5,7,'我们先保留原始的声音。',2)")
    expect(page.locator('#vkn-live .note')).to_have_count(2)
    expect(page.locator('#vkn-live .note').last.locator(':scope > p')).to_contain_text('未知的事情啊')
    assert '不纳入整理' not in page.locator('#vkn-live').inner_text()
    page.locator('#vkn-live .note').last.locator('details > summary').click()
    page.locator('#vkn-live button').filter(has_text='撤销字幕修订').click()
    expect(page.locator('#vkn-live .note').last.locator(':scope > p')).to_contain_text('位置的事情啊')
    print('PASS short fragment joined without changing source attribution; speaker turn boundary and reversible subtitle edit preserved',flush=True)
    page.locator('#vkn-transcript > summary').click()
    # Generation must not change body scroll height / scroll position, nor reserve a blank result block while working.
    page.evaluate('window.__holdGenerate=true;window.scrollTo(0,300)')
    before=page.evaluate('({y:scrollY,height:document.body.scrollHeight})')
    page.locator('#vkn-ai').click();expect(page.locator('#vkn-ai-cancel')).to_be_visible()
    assert page.locator('#vkn-result-section').is_hidden()
    assert page.evaluate('({y:scrollY,height:document.body.scrollHeight})')==before
    page.evaluate("window.__heldReply({ok:true,data:{markdown:'# 完整文章\\n\\n这是合成测试的整理正文，不是原视频。',mode:'knowledge',cueCount:3}});window.__holdGenerate=false")
    expect(page.locator('#vkn-preview')).to_contain_text('这是合成测试的整理正文')
    assert page.evaluate('({y:scrollY,height:document.body.scrollHeight})')==before
    for width in [1365,760,390]:
        page.set_viewport_size({'width':width,'height':960})
        assert page.locator('#vkn-panel').evaluate('(e)=>{const r=e.getBoundingClientRect();return e.scrollWidth<=e.clientWidth+1&&r.bottom<=innerHeight&&r.height<innerHeight-50}')
        assert page.locator('#vkn-embed-root').evaluate('(e)=>Math.abs(e.getBoundingClientRect().height-e.shadowRoot.getElementById("vkn-panel").getBoundingClientRect().height)<2')
        page.locator('#vkn-panel .body').evaluate('(e)=>e.scrollTop=0')
        page.locator('#vkn-panel').screenshot(path=str(screenshot_path(f'V0100_COMPACT_{width}.png')))
    print('PASS absent-result/generating/completed layouts; fixed root does not enlarge document; result navigation scrolls only panel; 3 viewport widths',flush=True)
    # Failed/cancelled generation keeps the last result and does not create another empty element.
    rpc({'op':'failNext'});page.locator('#vkn-ai').click();expect(page.locator('#vkn-status')).to_contain_text('失败',timeout=15000)
    expect(page.locator('#vkn-preview')).to_contain_text('这是合成测试的整理正文')
    page.evaluate('window.__holdGenerate=true');page.locator('#vkn-ai').click();page.locator('#vkn-ai-cancel').click()
    expect(page.locator('#vkn-preview')).to_contain_text('这是合成测试的整理正文')
    page.evaluate("window.__heldReply({ok:true,data:{markdown:'迟到的错误结果'}});window.__holdGenerate=false")
    expect(page.locator('#vkn-preview')).not_to_contain_text('迟到')
    # Stop: no new caption or frame requests. Existing late results must not revive capture.
    page.locator('#vkn-stop-all').click();n=page.evaluate("window.__requests.filter(x=>x==='VKN_CAPTION_VALIDATE'||x==='VKN_CAPTION_FRAME').length")
    page.evaluate('async()=>{window.__time=10;await window.__captionTick();}')
    assert page.evaluate("window.__requests.filter(x=>x==='VKN_CAPTION_VALIDATE'||x==='VKN_CAPTION_FRAME').length")==n
    assert 'VKN_FILTER_REVIEW' not in page.evaluate('window.__requests')
    print('PASS failure/cancel retain prior result; stop blocks future caption sampling; retired filtering never called',flush=True)
    assert not errors,errors
    page.evaluate('window.__closing=true');browser.close()
finally:
    bridge.stdin.close();bridge.wait(timeout=5)
