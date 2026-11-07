"""Actual content DOM; simulated extension storage/audio. No YouTube/model calls."""
from browser_support import browser_executable, screenshot_path
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=browser_executable(),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    ctx=browser.new_context(viewport={'width':1200,'height':950})
    page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content('<html><head><title>Video A</title></head><body><h1>Video A</h1><video></video></body></html>')
    page.evaluate('''
    window.__fixtureUrl='https://www.youtube.com/watch?v=AAAAAAAAAAA';
    const attach=Element.prototype.attachShadow;Element.prototype.attachShadow=function(o){return attach.call(this,{...o,mode:'open'});};
    window.__ticks=[];window.setInterval=(fn,ms)=>{window.__ticks.push({fn,ms});return window.__ticks.length;};
    window.__sessions={};window.__gets={};window.__save=[];window.__listeners=[];window.__read=[];window.__defer=false;window.__failure=false;
    for(const letter of ['A','B','C']){const id=letter.repeat(11),key='yt:'+id;window.__sessions[key]={key,title:'Video '+letter,url:'https://www.youtube.com/watch?v='+id,segments:[],documents:[{id:'same-id',markdown:letter+' ONLY BODY。',options:{mode:'transcript'},createdAt:'2026-11-07T00:00:00Z'}],activeDocumentId:'same-id',summaries:[],pendingSummary:[]};}
    window.open=()=>({opener:null,document:{open(){},write(s){window.__read.push(s);},close(){}}});
    window.chrome={runtime:{lastError:null,onMessage:{addListener(f){__listeners.push(f);}},sendMessage(m,cb){let d={};
      if(m.type==='VKN_AI_STATUS')d={configured:true,autoSummary:false,summaryMinutes:5};
      else if(m.type==='VKN_GET_SESSION'){if(__defer){__gets[m.key]=cb;return;}if(__failure){cb({ok:false,error:'fixture load failure'});return;}d=structuredClone(__sessions[m.key]||null);}
      else if(m.type==='VKN_SAVE_SESSION'){__save.push(structuredClone(m.session));__sessions[m.session.key]=structuredClone(m.session);d={};}
      else if(m.type==='VKN_ASR_STATUS_QUERY')d={running:false};
      else if(m.type==='VKN_LORA_STATUS')d={};
      if(cb)cb({ok:true,data:d});else return Promise.resolve({ok:true,data:d});
    }},storage:{onChanged:{addListener(){}}}};
    ''')
    for f in ['core.js','caption-review.js']:page.add_script_tag(path=str(ROOT/'extension'/f))
    # Browser policy prohibits external test navigation; only location is a fixture.
    page.evaluate("src=>new Function('location',src)({get href(){return window.__fixtureUrl;}})",(ROOT/'extension/content.js').read_text())
    page.wait_for_timeout(150);page.locator('#vkn-bubble').click()
    expect(page.locator('#vkn-preview')).to_contain_text('A ONLY BODY')
    page.locator('#vkn-read-full').click();assert 'A ONLY BODY' in page.evaluate('__read.at(-1)')
    # Before the one-second polling tick, a reader click must not open A for B.
    page.evaluate("__fixtureUrl='https://www.youtube.com/watch?v=BBBBBBBBBBB';document.querySelector('h1').textContent='Video B';__defer=true;__read=[];document.querySelector('#vkn-embed-root').shadowRoot.querySelector('#vkn-read-full').click()")
    page.wait_for_timeout(40)
    assert not page.evaluate('__read'), 'REGRESSION: previous video reader opened during SPA change'
    # A B event arriving during B load cannot be appended to A.
    page.evaluate("for(const f of __ticks.filter(x=>x.ms===1000))f.fn();for(const f of __listeners)f({type:'VKN_ASR_EVENT',sessionKey:'yt:BBBBBBBBBBB',kind:'segment',data:{id:'b1',time:1,text:'B ONLY AUDIO',source:'local-asr'}},{},()=>{})")
    assert not page.locator('#vkn-result-section').is_visible()
    # Navigate again before B resolves: C must win, despite B's late reply.
    page.evaluate("__fixtureUrl='https://www.youtube.com/watch?v=CCCCCCCCCCC';document.querySelector('h1').textContent='Video C';for(const f of __ticks.filter(x=>x.ms===1000))f.fn()")
    page.wait_for_timeout(80)
    page.evaluate("__gets['yt:CCCCCCCCCCC']({ok:true,data:structuredClone(__sessions['yt:CCCCCCCCCCC'])})")
    page.wait_for_timeout(40)
    page.evaluate("__gets['yt:BBBBBBBBBBB']({ok:true,data:structuredClone(__sessions['yt:BBBBBBBBBBB'])})")
    page.wait_for_timeout(40)
    expect(page.locator('#vkn-title')).to_have_text('Video C')
    expect(page.locator('#vkn-preview')).to_contain_text('C ONLY BODY')
    page.locator('#vkn-read-full').click();reader=page.evaluate('__read.at(-1)')
    assert 'C ONLY BODY' in reader and 'A ONLY BODY' not in reader and 'B ONLY BODY' not in reader
    assert all(s['title']=='Video A' and not s['segments'] for s in page.evaluate('__save') if s['key']=='yt:AAAAAAAAAAA')
    # A failed load clears old content; never relabel previous material as current.
    page.evaluate("__defer=false;__failure=true;__fixtureUrl='https://www.youtube.com/watch?v=DDDDDDDDDDD';document.querySelector('h1').textContent='Video D';for(const f of __ticks.filter(x=>x.ms===1000))f.fn()")
    page.wait_for_timeout(80);assert not page.locator('#vkn-result-section').is_visible()
    page.evaluate("__read=[];document.querySelector('#vkn-embed-root').shadowRoot.querySelector('#vkn-read-full').click()")
    assert not page.evaluate('__read')
    # Returning to C retains its result and produces a reader snapshot with source.
    page.evaluate("__failure=false;__fixtureUrl='https://www.youtube.com/watch?v=CCCCCCCCCCC';document.querySelector('h1').textContent='Video C';for(const f of __ticks.filter(x=>x.ms===1000))f.fn()")
    page.wait_for_timeout(80);expect(page.locator('#vkn-preview')).to_contain_text('C ONLY BODY')
    page.locator('#vkn-read-full').click();reader=page.evaluate('__read.at(-1)')
    assert 'CCCCCCCCCCC' in reader and 'same-id' in reader
    page.locator('#vkn-panel').screenshot(path=str(screenshot_path('V0102_SOURCE_ISOLATION.png')))
    assert not errors, errors
    browser.close()
print('PASS actual content: immediate route guard, load isolation, B->C race, late event, failed load, equal-id/length preview and source-bound reader')
