"""DOM smoke: retired authoring choices stay hidden; original source remains."""
from pathlib import Path
import ast,subprocess,json,threading
from playwright.sync_api import sync_playwright,expect
from browser_support import browser_executable
ROOT=Path(__file__).resolve().parents[1];EXT=ROOT/'extension'
tree=ast.parse((ROOT/'tests/browser_writing_v070.py').read_text(encoding='utf-8'))
SHIM=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SHIM' for t in n.targets))
bridge=subprocess.Popen(['node',str(ROOT/'tests/writing_bridge.js')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1)
lock=threading.Lock()
def rpc(q):
 with lock:
  bridge.stdin.write(json.dumps(q,ensure_ascii=False)+'\n');bridge.stdin.flush()
  result=json.loads(bridge.stdout.readline())
  if not result['ok']:raise RuntimeError(result['error'])
  return result['data']
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path=browser_executable(),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
  page=browser.new_page(viewport={'width':1365,'height':1000})
  page.expose_function('bridgeRPC',rpc)
  page.set_content('<html><head><title>合成视频</title></head><body><video></video></body></html>')
  page.evaluate(SHIM)
  page.evaluate('''()=>{const original=Element.prototype.attachShadow;Element.prototype.attachShadow=function(o){return original.call(this,{...o,mode:'open'});};}''')
  page.add_script_tag(path=str(EXT/'core.js'))
  page.add_script_tag(path=str(EXT/'content.js'))
  page.wait_for_timeout(550)
  page.locator('#vkn-bubble').click()
  opts=page.locator('#vkn-mode option').evaluate_all('(rows)=>rows.map(x=>x.value)')
  assert opts==['knowledge','transcript','custom'],opts
  page.locator('#vkn-mode').select_option('transcript')
  expect(page.locator('#vkn-mode-hint')).to_contain_text('翻译')
  page.locator('#vkn-mode').select_option('knowledge')
  expect(page.locator('#vkn-mode-hint')).to_contain_text('概念')
  page.locator('#vkn-mode').select_option('custom')
  expect(page.locator('#vkn-mode-hint')).to_contain_text('要求')
  assert not page.locator('#vkn-panel').evaluate('(e)=>e.scrollWidth>e.clientWidth+1')
  print('PASS three authoring choices; retired script/novel hidden; switching hints; no horizontal overflow',flush=True)
  page.evaluate('window.__closing=true');browser.close()
finally:
 bridge.stdin.close();bridge.wait(timeout=5)
