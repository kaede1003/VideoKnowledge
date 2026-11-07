"""Allowed about:blank DOM test. Real synthetic MediaStream/AudioContext tracks;
extension APIs, AudioWorklet protocol, IndexedDB, and model transport are mocked.
Native Edge/tabCapture and actual worklet inference are NOT exercised.
"""
from browser_support import browser_executable, screenshot_path
import pathlib
from playwright.sync_api import sync_playwright
ROOT=pathlib.Path(__file__).resolve().parents[1];EXT=ROOT/'extension'
SHIM=r'''if(!crypto.randomUUID)Object.defineProperty(crypto,'randomUUID',{value:()=> 'test-session-'+Math.random().toString(16).slice(2)});
window.testEvents=[];window.testListeners=[];window.memory=[];
window.chrome={runtime:{getURL:p=>p,sendMessage:async m=>{testEvents.push(m);return {ok:true};},onMessage:{addListener:f=>testListeners.push(f)}}};
window.sendControl=msg=>new Promise(resolve=>testListeners[0]({...msg,target:'offscreen'},{},resolve));
window.VknStreamDB={all:async()=>[]};
window.VknDurableStream={create:async(context,options,onEvent,onPressure)=>{
 const c={meta:{context,options,lastTime:0,closed:false},chain:Promise.resolve(),emergency:[],connect(){},
 enqueue(pcm,start,end,flag){this.chain=this.chain.then(()=>{memory.push({pcm:Array.from(pcm||[]),start,end,flag});this.meta.lastTime=end;if(flag===2)this.meta.closed=true;});return this.chain;},
 finish(){return this.chain.then(()=>this.enqueue(null,this.meta.lastTime,this.meta.lastTime,2));}};return c;
}};
window.WebSocket={OPEN:1,CONNECTING:0};
window.setupSynthetic=async()=>{
 const Native=window.AudioContext;window.generator=new Native();await generator.resume();const osc=generator.createOscillator(),out=generator.createMediaStreamDestination();
 osc.connect(out);osc.start();const canvas=document.createElement('canvas');canvas.width=320;canvas.height=180;
 canvas.getContext('2d').fillRect(0,0,320,180);const video=canvas.captureStream(10);
 window.synthetic=new MediaStream([...out.stream.getAudioTracks(),...video.getVideoTracks()]);
 if(!navigator.mediaDevices)Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{}});
 navigator.mediaDevices.getUserMedia=async()=>synthetic;
 window.AudioContext=function(){const c=new Native();return new Proxy(c,{get(target,key){if(key==='audioWorklet')return {addModule:async()=>{}};const v=Reflect.get(target,key,target);return typeof v==='function'?v.bind(target):v;}});};
 window.AudioWorkletNode=function(c){const node=c.createGain();node.port={onmessage:null,postMessage:m=>queueMicrotask(()=>node.port.onmessage?.({data:{type:'gated',id:m.id}}))};return node;};
};'''
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path=browser_executable(),headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--autoplay-policy=no-user-gesture-required'])
 for mode in ['normal','worklet_no_ack','disk_stall','pause_then_stop']:
  context=browser.new_context();page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.set_content('<html><head><title>synthetic capture test - mocks</title></head><body></body></html>');page.evaluate(SHIM)
  page.evaluate('setupSynthetic()');page.add_script_tag(path=str(EXT/'offscreen.js'))
  start=page.evaluate("sendControl({type:'VKN_ASR_START',tabId:1,sessionKey:'synthetic',streamId:'test',player:{time:1,paused:false,rate:1},options:{}})")
  assert start['ok'],start
  page.evaluate('feedPcm(new Int16Array([1,2,3,4]))')
  if mode=='worklet_no_ack':page.evaluate('processor.port.postMessage=()=>{}')
  if mode=='disk_stall':page.evaluate('()=>{audioClient.chain=new Promise(()=>{});}')
  if mode=='pause_then_stop':
   paused=page.evaluate("sendControl({type:'VKN_ASR_PAUSE'})");assert paused['ok'],paused
  stop=page.evaluate("sendControl({type:'VKN_ASR_STOP',expectedTabId:1})")
  assert stop['ok'] and stop['data']['running'] is False,stop
  states=page.evaluate('synthetic.getTracks().map(t=>t.readyState)');assert states==['ended','ended'],states
  if mode=='worklet_no_ack':assert stop['data']['tailConfirmed'] is False
  if mode!='disk_stall':
   page.wait_for_function('memory.some(x=>x.flag===2)')
   assert page.evaluate('memory.filter(x=>x.pcm.length).flatMap(x=>x.pcm)')==[1,2,3,4]
  assert not errors,errors
  print('PASS',mode,': real synthetic AV tracks ended; worklet/cache/model mocked',flush=True)
  context.close()
 browser.close()
