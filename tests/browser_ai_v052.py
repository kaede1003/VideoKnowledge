"""Actual settings DOM + actual background source in Node VM.
Chrome APIs and Ollama replies are simulated; this is NOT a native Edge test.
Run: python tests/browser_ai_v051.py
Requires Node.js, Playwright and Chromium (VKN_CHROMIUM may override path).
"""
from __future__ import annotations
from browser_support import browser_executable, screenshot_path
import json,os,pathlib,re,subprocess,threading
from playwright.sync_api import sync_playwright,expect
ROOT=pathlib.Path(__file__).resolve().parents[1]
EXT=ROOT/'extension'
bridge=subprocess.Popen(['node',str(ROOT/'tests/ai_bridge.js')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1)
lock=threading.Lock()
def rpc(q):
    with lock:
        bridge.stdin.write(json.dumps(q,ensure_ascii=False)+'\n');bridge.stdin.flush()
        line=bridge.stdout.readline()
        if not line:raise RuntimeError('Test bridge closed')
        result=json.loads(line)
        if not result['ok']:raise RuntimeError(result['error'])
        return result.get('data')
SHIM=r'''window.__changes=[];
window.chrome={
 runtime:{id:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',getManifest:()=>({version:'0.5.2'}),
  sendMessage:(message,reply)=>{const p=window.testBridge({op:'send',message});if(reply){p.then(reply);return;}return p;}},
 storage:{local:{get:key=>window.testBridge({op:'get',key}),
  set:async values=>{await window.testBridge({op:'set',values});const changes={};for(const [k,v] of Object.entries(values))changes[k]={newValue:v};for(const f of window.__changes)f(changes,'local');}},
  onChanged:{addListener:f=>window.__changes.push(f)}},
 permissions:{request:async()=>true,contains:async()=>true}
};'''
def load_page(browser,width=1365):
    p=browser.new_page(viewport={'width':width,'height':1000})
    p.expose_function('testBridge',rpc)
    errors=[];p.on('pageerror',lambda err:errors.append(str(err)))
    html=re.sub(r'<script\b[^>]*>.*?</script>','',(EXT/'options.html').read_text(),flags=re.S)
    html=re.sub(r'<link[^>]+stylesheet[^>]+>','',html)
    p.set_content(html)
    p.add_style_tag(path=str(EXT/'options.css'))
    p.evaluate(SHIM)
    p.add_script_tag(path=str(EXT/'local-origin.js'));p.add_script_tag(path=str(EXT/'ai-config.js'));p.add_script_tag(path=str(EXT/'options.js'))
    expect(p.locator('#save')).to_be_enabled()
    return p,errors
cues=[{'time':1,'text':'第一点记录事实。'},{'time':8,'text':'第二点保留证据。'},{'time':15,'text':'第三点核对结论。'}]
def generate():return rpc({'op':'send','message':{'type':'VKN_AI_GENERATE','cues':cues,'meta':{'title':'浏览器闭环'}}})
try:
 with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=browser_executable(),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    # UI default and backend default agree, even before a dedicated summary save.
    rpc({'op':'reset'})
    page,errors=load_page(browser)
    assert page.locator('#model').input_value()=='qwen2.5:3b'
    assert generate()['ok']
    assert rpc({'op':'get','key':'vknAiConfig'})=={}
    print('PASS UI defaults -> background resolver -> deep summary (mock model)',flush=True)
    # Saving speech alone must no longer leave the summary pipeline unconfigured.
    page.locator('#textModel').fill('qwen2.5:7b');page.locator('#saveSpeech').click()
    expect(page.locator('#speechStatus')).to_contain_text('听写设置已保存')
    expect(page.locator('#model')).to_have_value('qwen2.5:7b')
    assert generate()['ok'];assert rpc({'op':'requests'})[-1]['body']['model']=='qwen2.5:7b'
    print('PASS save speech only -> deep summary uses saved local text model',flush=True)
    # One click saves and verifies via production background, not an independent fake test function.
    page.locator('#useLocal').click();expect(page.locator('#status')).to_contain_text('后台短文本推理验证通过')
    config=rpc({'op':'get','key':'vknAiConfig'})['vknAiConfig']
    assert config['model']=='qwen2.5:7b' and config['provider']=='ollama'
    assert rpc({'op':'requests'})[-1]['body']['max_tokens']==32
    print('PASS one-click local repair -> persisted readback -> shared short inference',flush=True)
    page.locator('#model').fill('qwen2.5:3b')
    expect(page.locator('#summarySaveState')).to_contain_text('未保存')
    assert rpc({'op':'get','key':'vknAiConfig'})['vknAiConfig']['model']=='qwen2.5:7b'
    page.locator('#test').click();expect(page.locator('#status')).to_contain_text('后台短文本推理验证通过')
    assert rpc({'op':'get','key':'vknAiConfig'})['vknAiConfig']['model']=='qwen2.5:3b'
    assert rpc({'op':'requests'})[-1]['body']['model']=='qwen2.5:3b'
    print('PASS edited draft is not silently used; Save+Verify stores and uses the new value',flush=True)
    # Missing model is not mislabeled as empty configuration.
    page.locator('#model').fill('absent:3b');page.locator('#test').click()
    expect(page.locator('#status')).to_contain_text('AI_MODEL_MISSING')
    expect(page.locator('#status')).to_contain_text('设置已经保存')
    print('PASS missing model diagnostic and saved/not-saved distinction',flush=True)
    # Explicit offline stays offline after a reload and generates no model requests.
    page.locator('#preset').select_option('offline');page.locator('#save').click()
    expect(page.locator('#status')).to_contain_text('已保存离线模式')
    before=len(rpc({'op':'requests'}));assert 'AI_DISABLED' in generate()['error'];assert len(rpc({'op':'requests'}))==before
    assert not errors,errors;page.close()
    page,errors=load_page(browser);assert page.locator('#preset').input_value()=='offline';assert page.locator('#model').input_value()==''
    assert not errors,errors;page.close();print('PASS offline choice persists and blocks network use',flush=True)
    # Saving speech must not overwrite a deliberately saved custom summary service.
    cloud={'provider':'custom','endpoint':'https://example.test/v1/chat/completions','model':'chosen-model','apiKey':'test-secret','enabled':True}
    rpc({'op':'reset','store':{'vknAiConfig':cloud}})
    page,errors=load_page(browser)
    assert page.locator('#model').input_value()=='chosen-model'
    page.locator('#textModel').fill('qwen2.5:7b');page.locator('#saveSpeech').click()
    expect(page.locator('#speechStatus')).to_contain_text('已保存')
    assert rpc({'op':'get','key':'vknAiConfig'})['vknAiConfig']==cloud
    assert 'test-secret' not in page.locator('#effectiveConfig').inner_text()
    assert not errors,errors;page.close()
    print('PASS speech save preserves custom provider; runtime status omits secrets',flush=True)
    # Responsive layout regression after adding the repair/status controls.
    for width in [1365,760,390]:
        rpc({'op':'reset'})
        page,errors=load_page(browser,width)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'overflow at {width}'
        expect(page.locator('#apiKeyField')).to_be_hidden()
        expect(page.locator('#localOriginHelp')).to_be_visible()
        assert 'chrome-extension://'+'a'*32 in page.locator('#originCommand').input_value()
        page.locator('#summarySettings').screenshot(path=str(screenshot_path(f'OPTIONS_V052_{width}.png')))
        page.locator('#preset').select_option('custom')
        page.locator('#endpoint').fill('https://example.test/v1/chat/completions')
        expect(page.locator('#apiKeyField')).to_be_visible()
        boxes={k:page.locator('#'+k).bounding_box() for k in ['model','apiKey','show']}
        def overlap(a,b):return min(a['x']+a['width'],b['x']+b['width'])>max(a['x'],b['x'])+1 and min(a['y']+a['height'],b['y']+b['height'])>max(a['y'],b['y'])+1
        assert not overlap(boxes['model'],boxes['apiKey']);assert not overlap(boxes['apiKey'],boxes['show'])
        # Local and custom layouts are both checked. Screenshots above are local mode; no real model used.
        assert not errors,errors;page.close()
        print('PASS responsive layout',width,flush=True)
    browser.close()
finally:
    bridge.stdin.close();bridge.wait(timeout=5)
