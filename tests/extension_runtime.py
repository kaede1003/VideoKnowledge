"""Optional real MV3 smoke test via Chromium; requires Playwright + Chromium."""
from browser_support import browser_executable, screenshot_path
import pathlib, tempfile, os
from playwright.sync_api import sync_playwright
ROOT=pathlib.Path(__file__).resolve().parents[1]
EXT=ROOT/'extension'
with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
    context=p.chromium.launch_persistent_context(
      tmp,executable_path=browser_executable(),headless=(os.environ.get('VKN_HEADFUL')!='1'),
      args=['--no-sandbox','--disable-dev-shm-usage',f'--disable-extensions-except={EXT}',f'--load-extension={EXT}']
    )
    w=context.service_workers
    if not w:
      try:w=[context.wait_for_event('serviceworker',timeout=8000)]
      except Exception as e:
        print('SKIPPED: headless Chromium here did not start extension service workers; test manually in Edge.')
        context.close()
        raise SystemExit(2)
    source=w[0].url
    extid=source.split('/')[2]
    page=context.new_page()
    errors=[]
    page.on('pageerror', lambda err:errors.append(str(err)))
    page.goto(f'chrome-extension://{extid}/options.html')
    assert page.locator('h1').inner_text().startswith('视频知识笔记')
    page.locator('#preset').select_option('ollama')
    assert page.locator('#endpoint').input_value().startswith('http://127.0.0.1:11434')
    assert not errors,errors
    assert page.locator('#endpoint').input_value().startswith('http://127.0.0.1:11434')
    print('Actual MV3 load OK, extension ID=',extid,'options page working, JS errors=',errors)
    context.close()
