"""Actual settings DOM and production options.js; HTTP, extension storage, and Ollama are mocked.

This verifies headers on both ASR config calls. Not a native Edge/Windows test.
"""
from __future__ import annotations
import pathlib
import re
from playwright.sync_api import sync_playwright, expect
from browser_support import browser_executable

ROOT=pathlib.Path(__file__).resolve().parents[1]
EXT=ROOT/'extension'

SHIM=r'''(() => {
  const id='a'.repeat(32);
  const saved={};
  window.__asrCalls=[];
  window.chrome={
    runtime:{id, getManifest:()=>({version:'0.11.2'}),
      sendMessage:async()=>({ok:true,data:{configured:true,model:'qwen2.5:3b',endpoint:'http://127.0.0.1:11434/v1/chat/completions',source:'default-local',version:'0.11.2'}})},
    storage:{local:{get:async keys=>{
      const names=Array.isArray(keys)?keys:[keys];
      return Object.fromEntries(names.filter(k=>k in saved).map(k=>[k,saved[k]]));
    },set:async obj=>Object.assign(saved,obj)}, onChanged:{addListener:()=>{}}},
    permissions:{request:async()=>true,contains:async()=>true}
  };
  window.fetch=async (url,options={})=>{
    if (!url.endsWith('/asr/config')) throw Error('Unexpected test fetch: '+url);
    window.__asrCalls.push({url,method:options.method||'GET',headers:options.headers||{},body:options.body||null});
    if ((options.method||'GET')==='POST') return {
      ok:true,status:200,json:async()=>({selected:'ollama17',model:'frozenlab/qwen3-asr:1.7b'})};
    return {ok:true,status:200,json:async()=>({
      next_profile:'ollama17',next_model:'frozenlab/qwen3-asr:1.7b',
      active_profile:'legacy',active_model:'base',restart_required:true,
      installed_ollama_asr_models:['frozenlab/qwen3-asr:1.7b'],ollama_reachable:true
    })};
  };
})();'''

with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=browser_executable(),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page=browser.new_page(viewport={'width':760,'height':900})
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    html=re.sub(r'<script\b[^>]*>.*?</script>','',(EXT/'options.html').read_text(encoding='utf-8'),flags=re.S)
    html=re.sub(r'<link[^>]+stylesheet[^>]+>','',html)
    page.set_content(html)
    page.add_style_tag(path=str(EXT/'options.css'))
    page.evaluate(SHIM)
    for name in ['local-origin.js','ai-config.js','options.js']:
        page.add_script_tag(path=str(EXT/name))
    expect(page.locator('#asrStatus')).to_contain_text('当前运行')
    page.locator('#refreshAsr').click()
    expect(page.locator('#asrStatus')).to_contain_text('下次启动')
    page.locator('#saveAsrProfile').click()
    expect(page.locator('#asrStatus')).to_contain_text('已保存')
    calls=page.evaluate('window.__asrCalls')
    assert len(calls)>=3,calls
    assert any(c['method']=='POST' for c in calls),calls
    for c in calls:
        assert c['headers'].get('X-VKN-Extension-ID')=='a'*32,c
    assert not errors,errors
    page.close();browser.close()
print('PASS: production Edge settings GET + POST send extension identity header and render success')
