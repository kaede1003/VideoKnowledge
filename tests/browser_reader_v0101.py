"""Render production caption validation / punctuation / HTML with synthetic sources.
Not native Edge tabCapture, not OCR accuracy, not real model inference.
"""
from pathlib import Path
import json,sys
from playwright.sync_api import sync_playwright
from browser_support import browser_executable,screenshot_path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from server.caption_review import validate
sid='b'*32
raw='这里讨论Cloud Sonet的文本处理能力但是我们仍需保留原始数据然后把Anthrope的接口结果放在一起进行比较最后再分别说明各个系统的输出差异这段文字仅供软件功能回归测试使用'
caption=raw.replace('Cloud Sonet','Claude Sonnet').replace('Anthrope','Anthropic')
cue=dict(id=sid+':1:0',time=1.,end=12.,contextEpoch=0,language='zh',text=raw,original=raw,source='local-asr',speakerId=sid+':spk1',speakerStatus='estimated')
obs=dict(id='fixture',stream=sid,epoch=0,start=3.,end=5.,source='visible',samples=3,seenSpan=1.,text=caption,kind='unknown')
review=validate({'items':[{'cue':cue,'evidence':[obs]}]})['reviews'][0]
assert review['status']=='applied'
with sync_playwright() as p:
    b=p.chromium.launch(executable_path=browser_executable(),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page=b.new_page(viewport={'width':1200,'height':860});page.set_content('<html lang="zh-CN"><head><meta charset="utf-8"></head><body></body></html>')
    page.add_script_tag(path=str(ROOT/'extension/core.js'))
    result=page.evaluate('''({cue,review})=>{const C=VideoKnowledgeCore,session={title:'字幕拼写与断句回归 · 合成测试',segments:[cue],captionReviews:{[cue.id]:review}};
      const ts=C.readingTurns(C.cuesWithSpeakers(session));
      const text=ts[0].text.replace('文本处理能力','文本处理能力，').replace('保留原始数据','保留原始数据。').replace('进行比较','进行比较。').replace('输出差异','输出差异。')+'。';
      const checked=C.validateTranscriptPunctuation(JSON.stringify({turns:[{id:ts[0].id,text}]}),ts);
      if(checked.held.length)throw Error('fixture punctuation rejected');
      const d=C.cleanDocument({id:'fixture',markdown:C.formatTranscriptTurns(checked.turns),options:{mode:'transcript'}});
      return {html:C.resultHtml(session,d),markdown:d.markdown,raw:session.segments[0].original};}''',dict(cue=cue,review=review))
    assert 'Cloud Sonet' not in result['markdown'] and 'Claude Sonnet' in result['markdown'] and 'Anthropic' in result['markdown']
    assert result['raw']==raw
    page.set_content(result['html']);assert page.locator('br').count()>=3
    assert 'AI认为' not in page.inner_text('body')
    page.evaluate('''()=>{const n=document.createElement('p');n.textContent='验证说明：字幕与模型回复是合成测试数据；实际产品校验与导出代码运行。不是对原视频内容的核实。';n.style.cssText='font-size:13px;color:#52677d;border-top:1px solid #ddd;padding-top:20px';document.querySelector('main')?.append(n);}''')
    for width in [1200,760,390]:
        page.set_viewport_size({'width':width,'height':860})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.screenshot(path=str(screenshot_path(f'V0101_READER_{width}.png')),full_page=True)
    b.close()
print('PASS real Python caption validator -> production JS display -> punctuation validator -> HTML sentence lines; synthetic caption/model reply, raw preserved')
