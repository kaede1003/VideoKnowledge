"""Production content/core/background DOM workflow. Chrome, audio and models are fixtures."""
from pathlib import Path
import ast, json, subprocess, threading
from playwright.sync_api import sync_playwright, expect
from browser_support import browser_executable, screenshot_path
ROOT=Path(__file__).resolve().parents[1]; EXT=ROOT/'extension'
# Reuse only test bootstrap definitions; importing the old file would execute its tests.
tree=ast.parse((ROOT/'tests/browser_writing_v070.py').read_text())
SHIM=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SHIM' for t in n.targets))
bridge=subprocess.Popen(['node',str(ROOT/'tests/writing_bridge.js')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1)
lock=threading.Lock()
def rpc(q):
    with lock:
        bridge.stdin.write(json.dumps(q,ensure_ascii=False)+'\n');bridge.stdin.flush()
        r=json.loads(bridge.stdout.readline())
        if not r['ok']:raise RuntimeError(r['error'])
        return r.get('data')
try:
 with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=browser_executable(),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page=browser.new_page(viewport={'width':1365,'height':1000},accept_downloads=True);errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)));page.expose_function('bridgeRPC',rpc)
    page.set_content('''<html lang="zh-CN"><head><title>把记录整理成文章 · 演示数据</title></head><body style="margin:0;padding:32px;background:#142233;color:#d9e6f5;font:18px system-ui"><h1>对话记录 · 合成示例</h1><video style="width:700px;height:390px;background:#1c3549;border-radius:20px"></video><p>这里是自动化界面测试，不是原视频或真实模型结果。</p></body></html>''')
    page.evaluate(SHIM)
    page.evaluate('''()=>{const attach=Element.prototype.attachShadow;Element.prototype.attachShadow=function(o){return attach.call(this,{...o,mode:'open'});};Object.defineProperty(navigator,'clipboard',{value:{writeText:async x=>window.__copied=x},configurable:true});}''')
    page.add_script_tag(path=str(EXT/'core.js'));page.add_script_tag(path=str(EXT/'content.js'));page.wait_for_timeout(650);page.locator('#vkn-bubble').click()
    page.evaluate('''()=>{const sid='b'.repeat(32),key='web:'+location.origin+location.pathname;
      const rows=[[1,4,1,'先把零散的记录'],[4.3,7,1,'合并为完整发言。'],[7.2,11,1,'然后按句子换行。'],[12,15,2,'这样会丢失原文吗？'],[16,20,1,'不会，原文仍然保留。']];
      rows.forEach(([time,end,speaker,text],i)=>{const data={id:sid+':'+(i+1)+':0',revision:1,time,end,text,original:text,source:'local-asr',speakerId:sid+':spk'+speaker,speakerStatus:'estimated',contextEpoch:1};for(const f of window.__listeners)f({type:'VKN_ASR_EVENT',sessionKey:key,kind:'segment',data},{},()=>{});});
    }''')
    expect(page.locator('#vkn-count')).to_have_text('5');assert not page.locator('#vkn-transcript').evaluate('(e)=>e.open')
    page.locator('#vkn-transcript > summary').click();expect(page.locator('#vkn-live .note')).to_have_count(3)
    turn=page.locator('#vkn-live .note').last
    expect(turn.locator(':scope > p')).to_have_text('先把零散的记录合并为完整发言。\n然后按句子换行。')
    expect(turn.locator('details > summary')).to_contain_text('3条');assert not turn.locator('details').evaluate('(e)=>e.open')
    turn.locator('details > summary').click();expect(turn.locator('.source-cue')).to_have_count(3)
    turn.locator('details > summary').click()
    print('PASS five original records -> three alternating turns; same speaker merged, sources collapsed, no loss',flush=True)
    page.locator('#vkn-transcript > summary').click();page.locator('#vkn-mode').select_option('transcript');page.locator('#vkn-ai').click()
    expect(page.locator('#vkn-preview')).to_contain_text('先把零散的记录合并为完整发言。',timeout=15000)
    body=page.locator('#vkn-preview').inner_text()
    assert '然后按句子换行。' in body and '这样会丢失原文吗？' in body and '不会，原文仍然保留。' in body
    assert body.count('说话人1')==2 and body.count('说话人2')==1
    for forbidden in ['整理分段','AI分析','需核对','校对记录','模拟测试结果']:
        assert forbidden not in body,forbidden
    assert not page.locator('#vkn-result-details').evaluate('(e)=>e.open')
    page.locator('#vkn-result-details > summary').click();expect(page.locator('#vkn-result-audit')).to_contain_text('发言定位')
    expect(page.locator('#vkn-result-audit')).to_contain_text('3条来源记录')
    page.locator('#vkn-result-details > summary').click()
    page.locator('#vkn-export-menu > summary').click();page.locator('#vkn-copy').click()
    expect(page.locator('#vkn-status')).to_contain_text('已复制');assert '然后按句子换行。' in page.evaluate('window.__copied')
    for button,suffix in [('vkn-txt','.txt'),('vkn-md','.md'),('vkn-html','.html')]:
        if not page.locator('#vkn-export-menu').evaluate('(e)=>e.open'):page.locator('#vkn-export-menu > summary').click()
        with page.expect_download() as d:page.locator('#'+button).click()
        text=Path(d.value.path()).read_text(encoding='utf-8-sig');assert '先把零散的记录合并为完整发言。' in text
        assert all(x not in text for x in ['整理分段','AI分析','听写短语校对记录'])
    with page.expect_popup() as popup:page.locator('#vkn-read-full').click()
    doc=popup.value;expect(doc.locator('body')).to_contain_text('然后按句子换行。');assert doc.locator('br').count()>=1
    doc.screenshot(path=str(screenshot_path('V090_TRANSCRIPT_READER.png')),full_page=True);doc.close()
    print('PASS transcript actual worker punctuation validation -> clean preview/copy/TXT/Markdown/HTML/full reader',flush=True)
    if page.locator('#vkn-export-menu').evaluate('(e)=>e.open'):page.locator('#vkn-export-menu > summary').click()
    page.wait_for_timeout(1200)
    saved=next(v for k,v in rpc({'op':'get','key':None}).items() if k.startswith('vkn:session:'))
    assert len(saved['segments'])==5 and len(saved['documents'][-1]['audit']['turns'])==3
    page.locator('#vkn-tools > summary').click()
    with page.expect_download() as d:page.locator('#vkn-export-audit').click()
    audit=json.loads(Path(d.value.path()).read_text(encoding='utf-8-sig'));assert len(audit['segments'])==5
    assert len(audit['documents'][-1]['audit']['turns'])==3
    page.locator('#vkn-tools > summary').click()
    # Native action state notification is allowed to begin a new user-started session after stop.
    page.locator('#vkn-asr').click();page.locator('#vkn-stop-all').click()
    page.evaluate('''()=>{window.__running=true;for(const f of window.__listeners)f({type:'VKN_ASR_STATE',running:true,paused:false,startedByUser:true,tabId:1,message:'快捷键启动（模拟）'},{},()=>{});}''')
    expect(page.locator('#vkn-record')).to_be_visible();page.locator('#vkn-stop-all').click();expect(page.locator('#vkn-asr')).to_be_enabled()
    print('PASS source/audit retained; action/shortcut restart after stop updates content controls (message fixture)',flush=True)
    for width in [1365,760,390]:
        page.set_viewport_size({'width':width,'height':1080});page.locator('#vkn-title').scroll_into_view_if_needed()
        assert page.locator('#vkn-panel').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
        page.locator('#vkn-panel').screenshot(path=str(screenshot_path(f'V090_CLEAN_PANEL_{width}.png')))
    page.set_viewport_size({'width':1365,'height':1080});page.locator('#vkn-transcript > summary').click();page.locator('#vkn-title').scroll_into_view_if_needed()
    page.locator('#vkn-panel').screenshot(path=str(screenshot_path('V090_GROUPED_LIVE.png')))
    assert not errors,errors
    page.evaluate('window.__closing=true');browser.close()
finally:
    bridge.stdin.close();bridge.wait(timeout=5)
