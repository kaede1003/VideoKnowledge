"""Real cache-page DOM, synthetic service/permission replies; no account/network access."""
from browser_support import browser_executable, screenshot_path
from pathlib import Path
import re
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'extension/cache.html').read_text()
html=re.sub(r'<link[^>]+>|<script[^>]*src="cache.js"[^>]*></script>','',html)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=browser_executable(),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page=browser.new_page(viewport={'width':1200,'height':950});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    consent={'allow':False};dialogs=[]
    def dialog(d):
        dialogs.append(d.message)
        if consent['allow']:d.accept()
        else:d.dismiss()
    page.on('dialog',dialog)
    page.set_content(html);page.add_style_tag(path=str(ROOT/'extension/cache.css'))
    page.evaluate('''
    window.__calls=[];window.__permissions=[];window.__granted=false;window.__error='';window.__intervals=[];
    window.setInterval=(f,n)=>{__intervals.push(f);return 1;};
    window.chrome={runtime:{lastError:null,sendMessage(m,cb){__calls.push(m);if(m.type==='VKN_CACHE_LIST'){cb({ok:true,data:{directory:'SYNTHETIC local cache',capabilities:{login_transfer:true,version:'fixture',ejs_version:'fixture',javascript_runtime:'fixture',ffmpeg:true,message:'合成缓存界面测试；未运行真实下载或读取账号'},items:[{id:'a'.repeat(32),url:'https://www.youtube.com/watch?v=abcdefghijk',title:'合成测试视频 · 下载失败不代表已保存',state:'failed',created:1,expires:Date.now()/1000+1000,size:20971520,progress:0.8,error:'VIDEO_NO_FORMATS：测试错误，仅用于界面测试'}]}});}else{cb(__error?{ok:false,error:__error}:{ok:true,data:{id:'b'.repeat(32),state:'queued'}});}}},permissions:{request:async x=>{__permissions.push(x);return __granted;},remove:async x=>{__permissions.push({remove:x});return true;}}};
    ''')
    page.add_script_tag(path=str(ROOT/'extension/cache.js'))
    expect(page.locator('.card')).to_have_count(1)
    expect(page.locator('progress')).to_have_count(0)
    expect(page.locator('.card')).to_contain_text('传输字节数不代表已保存')
    # Anonymous retry does not ask permissions or send a consent/session value.
    page.get_by_role('button',name='重新下载（不使用登录）',exact=True).click()
    assert page.evaluate('__calls.some(x=>x.type==="VKN_CACHE_RETRY")')
    assert page.evaluate('__permissions.length')==0
    page.evaluate('__calls=[]')
    login=page.get_by_role('button',name='授权本次使用YouTube登录重试',exact=True)
    login.click();assert dialogs and '仅这一次' in dialogs[-1]
    assert page.evaluate('__permissions.length')==0
    assert not page.evaluate('__calls.some(x=>x.type==="VKN_CACHE_RETRY_LOGIN")')
    # Denying the optional browser permission also avoids authenticated requests.
    consent['allow']=True;login.click();expect(page.locator('#status')).to_contain_text('未授权')
    assert page.evaluate('__permissions.length')==1
    assert not page.evaluate('__calls.some(x=>x.type==="VKN_CACHE_RETRY_LOGIN")')
    page.evaluate('__granted=true');login.click()
    assert page.evaluate('__calls.some(x=>x.type==="VKN_CACHE_RETRY_LOGIN"&&x.consent===true)')
    # No cookie values are ever in this page's test messages.
    assert not page.evaluate('__calls.some(x=>x.youtube_cookies)')
    page.get_by_role('button',name='撤销登录访问权限').click()
    expect(page.locator('#status')).to_contain_text('已撤销')
    page.evaluate('__error="VIDEO_HTTP_429：平台限制请求"')
    page.get_by_role('button',name='重新下载（不使用登录）',exact=True).click()
    expect(page.locator('#status')).to_contain_text('VIDEO_HTTP_429')
    for width in [1200,760,390]:
        page.set_viewport_size({'width':width,'height':1100})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width
    page.screenshot(path=str(screenshot_path('V0102_CACHE_CONSENT.png')),full_page=True)
    assert not errors,errors
    browser.close()
print('PASS cache DOM: failed state, anonymous retry, per-attempt confirmation, denied/allowed permission, revoke, explicit errors, narrow layout; no real account/download')
