"""Optional Chromium smoke test. Requires `pip install playwright` and Chromium."""
from browser_support import browser_executable, screenshot_path
import http.server
import os
import pathlib
import threading
import time
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXT = ROOT / 'extension'
SCREENSHOT = screenshot_path('UI_PREVIEW.png')

class Silent(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

os.chdir(ROOT)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Silent)
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=browser_executable(),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        ctx=browser.new_context(accept_downloads=True,viewport={'width':1365,'height':850})
        page=ctx.new_page();page.set_default_timeout(6000)
        errors=[]
        page.on('pageerror',lambda err:errors.append(str(err)))
        page.add_init_script('''
        window.__mockStorage = {};
        window.__runtimeListeners=[];window.__mockAsrRunning=false;window.__mockAsrPaused=false;window.__manualDeepCalls=0;
        window.chrome = {
          runtime: {lastError:null,sendMessage: (message,reply) => {
             let data=null;
             if(message.type==='VKN_GET_SESSION') data=window.__mockStorage[message.key]||null;
             else if(message.type==='VKN_SAVE_SESSION'){window.__mockStorage[message.session.key]=structuredClone(message.session);data={count:message.session.segments.length};}
             else if(message.type==='VKN_GET_PLATFORM') data={kind:'none',message:'浏览器模拟：暂无平台字幕'};
             else if(message.type==='VKN_AI_STATUS') data={configured:true,autoSummary:false,summaryMinutes:5,model:'qwen2.5:3b',provider:'ollama',source:'default-local',saved:false,version:'0.5.2'};
             else if(message.type==='VKN_ASR_STATUS_QUERY') data={running:window.__mockAsrRunning,paused:window.__mockAsrPaused,tabId:1,sessionKey:'web:'+location.origin+location.pathname};
             else if(message.type==='VKN_ASR_START'){window.__mockAsrRunning=true;window.__mockAsrPaused=false;data={running:true,paused:false,tabId:1};}
             else if(message.type==='VKN_ASR_STOP'){window.__mockAsrRunning=false;data={running:false,paused:false,tabId:1};}
             else if(message.type==='VKN_ASR_PAUSE'){window.__mockAsrPaused=true;data={running:true,paused:true,tabId:1};}
             else if(message.type==='VKN_ASR_RESUME'){window.__mockAsrPaused=false;data={running:true,paused:false,tabId:1};}
             else if(message.type==='VKN_AI_GENERATE'){window.__manualDeepCalls++;data={markdown:'## 手动深度整理\\n\\n人工触发测试',blocks:1};} 
             else if(message.type==='VKN_AI_PERIODIC_SUMMARY') return reply({ok:false,error:'AI阶段功能未启用'});
             if(typeof reply==='function')reply({ok:true,data});
             else return Promise.resolve({ok:true,data});
          },onMessage:{addListener(cb){window.__runtimeListeners.push(cb);} }},
          storage:{onChanged:{addListener(){}}}
        };
        ''')
        page.goto('about:blank')
        page.set_content('''<!doctype html><html lang="zh-CN"><head><title>演示视频 | 本地测试</title>
        <style>body{background:#0e1729;color:#fff;font-family:Arial;padding:40px;margin:0}main{max-width:920px;margin:auto}video{width:700px;height:400px;background:linear-gradient(90deg,#17415b,#1d386a);border-radius:20px}.caption-text{position:absolute;top:390px;left:310px;font-size:22px;padding:8px 18px;background:#000a;border-radius:8px}</style>
        </head><body><main><h1>演示：从信息到知识</h1><video></video><div class="caption-text">第一步：理解什么是概念。</div><p>模拟视频播放场景；测试插件自动采集字幕。</p></main></body></html>''')
        page.evaluate('''() => {
          const original=Element.prototype.attachShadow;
          Element.prototype.attachShadow=function(options){return original.call(this,{...options,mode:'open'});};
          Object.defineProperty(document.querySelector('video'),'currentTime',{configurable:true,get:()=>window.fakeTime||4});
          Object.defineProperty(document.querySelector('video'),'duration',{configurable:true,get:()=>180});
        }''')
        page.add_script_tag(path=str(EXT/'core.js'))
        page.add_script_tag(path=str(EXT/'content.js'))
        page.wait_for_timeout(1300)
        page.evaluate("document.querySelector('#vkn-embed-root').shadowRoot.querySelector('#vkn-bubble').click()")
        page.wait_for_timeout(1100)
        page.evaluate("() => {window.fakeTime=11;document.querySelector('.caption-text').textContent='第二步：我们用实例说明抽象概念的重要性。'}")
        page.wait_for_timeout(1600)
        cue_count=page.evaluate("document.querySelector('#vkn-embed-root').shadowRoot.querySelector('#vkn-count').textContent")
        assert int(cue_count)>=2, cue_count
        # Simulated ASR event: content should extract without waiting for a manual summarization click.
        page.evaluate('''() => {
          const k='web:'+location.origin+location.pathname;
          for(const fn of window.__runtimeListeners) fn({type:'VKN_ASR_EVENT',sessionKey:k,tabId:1,
            kind:'segment',data:{time:52,text:'第三步，通过数据示例展示核心原则',seq:1}}, {}, ()=>{});
        }''')
        page.wait_for_timeout(200)
        page.locator('#vkn-transcript > summary').click()
        page.locator('#vkn-tools > summary').click()
        page.locator('#vkn-stage-details > summary').click()
        live=page.evaluate("document.querySelector('#vkn-embed-root').shadowRoot.querySelector('#vkn-live').textContent")
        assert '核心原则' in live, live
        assert page.evaluate('window.__manualDeepCalls')==0,'Deep report must not auto run'
        # Advance the simulated wall clock by 6 minutes to verify automatic stage summarization.
        page.evaluate('''() => {const clock=Date.now.bind(Date); Date.now=()=>clock()+360000;}''')
        page.wait_for_timeout(1150)
        summary=page.evaluate("document.querySelector('#vkn-embed-root').shadowRoot.querySelector('#vkn-summaries').textContent")
        assert '离线摘录' in summary,summary
        assert page.evaluate('window.__manualDeepCalls')==0,'Automatic periodic summaries must not trigger deep reporting'
        # Additional incoming transcription may be summarized manually, without waiting 5 more minutes.
        page.evaluate('''() => {
          const k='web:'+location.origin+location.pathname;
          for(const fn of window.__runtimeListeners) fn({type:'VKN_ASR_EVENT',sessionKey:k,tabId:1,
            kind:'segment',data:{time:79,text:'第四步，使用实例证明阶段摘要的效果',seq:2}}, {}, ()=>{});
        }''')
        page.evaluate("document.querySelector('#vkn-embed-root').shadowRoot.querySelector('#vkn-summary-now').click()")
        page.wait_for_timeout(200)
        summary=page.evaluate("document.querySelector('#vkn-embed-root').shadowRoot.querySelector('#vkn-summaries').textContent")
        assert '第四步' in summary,summary
        page.evaluate("document.querySelector('#vkn-embed-root').shadowRoot.querySelector('#vkn-asr').click()")
        page.wait_for_timeout(200)
        pause=page.locator('#vkn-embed-root').locator('button#vkn-record')
        # Shadow-root locators are handled automatically by Playwright.
        assert '暂停语音听写' in pause.inner_text()
        pause.click()
        page.wait_for_timeout(200)
        assert '继续语音听写' in pause.inner_text()
        pause.click()
        page.wait_for_timeout(200)
        assert '暂停语音听写' in pause.inner_text()
        page.evaluate("document.querySelector('#vkn-embed-root').shadowRoot.querySelector('#vkn-ai').click()")
        page.wait_for_timeout(200)
        assert page.evaluate('window.__manualDeepCalls')==1
        page.evaluate("document.querySelector('#vkn-embed-root').shadowRoot.querySelector('#vkn-md').click()")
        page.wait_for_timeout(450)
        page.evaluate("document.querySelector('#vkn-embed-root').shadowRoot.querySelector('#vkn-lora-details').open=true")
        page.screenshot(path=str(SCREENSHOT))
        assert not errors,errors
        print(f'Smoke OK: {cue_count} captions, ASR live excerpt, stage summary, mocked pause/resume, manual deep report; screenshot: {SCREENSHOT}')
        browser.close()
finally:
    server.shutdown()
