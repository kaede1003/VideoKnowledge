"""Real Chromium AudioWorklet + synthetic AV tracks + actual IndexedDB.
Not Edge/tabCapture permission, not a real ASR/model test. Network is stubbed.
"""
from browser_support import browser_executable, screenshot_path
import http.server,threading,pathlib,functools,json
from playwright.sync_api import sync_playwright
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
BASE=f'http://127.0.0.1:{server.server_port}/extension/'
SHIM=r'''window.testEvents=[];window.testListeners=[];
window.chrome={runtime:{getURL:p=>new URL(p,location.href).href,
 sendMessage:async m=>{testEvents.push(m);return {ok:true};},onMessage:{addListener:f=>testListeners.push(f)}}};
window.WebSocket=class{static OPEN=1;static CONNECTING=0;constructor(){this.readyState=0;this.bufferedAmount=0;}send(){}close(){this.readyState=3;this.onclose?.();}};
window.sendControl=msg=>new Promise(resolve=>testListeners[0]({...msg,target:'offscreen'},{},resolve));
window.setupSynthetic=async()=>{
 window.generator=new AudioContext();await generator.resume();const osc=generator.createOscillator(),out=generator.createMediaStreamDestination();
 osc.connect(out);osc.start();const canvas=document.createElement('canvas');canvas.width=320;canvas.height=180;
 const c=canvas.getContext('2d');c.fillRect(0,0,320,180);const video=canvas.captureStream(10);
 window.synthetic=new MediaStream([...out.stream.getAudioTracks(),...video.getVideoTracks()]);
 navigator.mediaDevices.getUserMedia=async()=>synthetic;
};'''
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=browser_executable(),headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--autoplay-policy=no-user-gesture-required'])
  for mode in ['normal','worklet_unresponsive','disk_stall','pause_then_stop']:
   context=browser.new_context();page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.add_init_script(SHIM);page.goto(BASE+'offscreen.html');page.evaluate('setupSynthetic()')
   start=page.evaluate("sendControl({type:'VKN_ASR_START',tabId:1,sessionKey:'synthetic',streamId:'test',player:{time:1,paused:false,rate:1},options:{}})")
   assert start['ok'],start
   page.wait_for_timeout(700)
   if mode=='worklet_unresponsive': page.evaluate('processor.port.postMessage=()=>{}')
   if mode=='disk_stall': page.evaluate('audioClient.chain=new Promise(()=>{})')
   if mode=='pause_then_stop':
    paused=page.evaluate("sendControl({type:'VKN_ASR_PAUSE'})");assert paused['ok'],paused
   stop=page.evaluate("sendControl({type:'VKN_ASR_STOP',expectedTabId:1})")
   assert stop['ok'] and stop['data']['running'] is False,stop
   states=page.evaluate('synthetic.getTracks().map(t=>t.readyState)')
   assert states==['ended','ended'],(mode,states)
   assert page.evaluate('asrActive') is False
   if mode=='worklet_unresponsive':assert stop['data']['tailConfirmed'] is False
   if mode!='disk_stall':
    page.wait_for_function('audioClient===null && [...durableClients.values()].every(c=>c.meta.closed)')
    rows=page.evaluate('VknStreamDB.all()');assert rows[0]['closed'],rows
   assert not errors,errors
   print('PASS',mode,': real synthetic MediaStream tracks ended; cached tail preserved or explicitly warned; no real model',flush=True)
   context.close()
  browser.close()
finally: server.shutdown()
