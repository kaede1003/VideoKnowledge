/* Offscreen context owns the consented tab A/V stream.
 * Audio to local ASR and optional video frames to local LoRA worker.
 */
'use strict';
const RATE = 16000;
const PACKET_SAMPLES = 9600; // 600 ms audio per WS packet
let capture = null;
let stream = null;
let ctx = null;
let source = null;
let processor = null;
let silent = null;
let sampleParts = [];
let sampleTotal = 0;
let player = {time:0, paused:false, rate:1, measuredAt:performance.now()};
let stopInProgress = false;
let captureEpoch=0,asrEpoch=0,loraEpoch=0;
let detachPromise=null,stopCapturePromise=null;
let asrPhase='idle';
function cancelled(){return Error('CAPTURE_CANCELLED：采集启动已取消');}
function releaseCaptureResources(){
  const oldStream=stream,oldCtx=ctx,oldSource=source,oldVideo=videoPreview;
  stream=null;ctx=null;source=null;videoPreview=null;frameCanvas=null;capture=null;videoCrop=null;
  try{oldSource?.disconnect();}catch{}
  try{oldStream?.getTracks().forEach(t=>{try{t.stop();}catch{}});}catch{}
  try{if(oldVideo){oldVideo.pause();oldVideo.srcObject=null;}}catch{}
  try{if(oldCtx)Promise.resolve(oldCtx.close()).catch(()=>{});}catch{}
}
function releaseIfIdle(){if(!asrActive&&!loraActive&&asrPhase==='idle')releaseCaptureResources();}

let asrActive = false;
let asrPaused = false;
let videoPreview = null;
let frameCanvas = null;
let frameTimer = null;
let loraConnection = null;
let loraActive = false;
let loraStopping = false;
let loraContext = null;
let loraPendingFrames = 0;
let videoCrop = null;


function sendEvent(kind, data={}) {
  const context = kind.startsWith('lora_') ? (loraContext || capture) : capture;
  if (!context) return;
  chrome.runtime.sendMessage({type:'VKN_ASR_EVENT',target:'background',
    tabId:context.tabId, sessionKey:context.sessionKey, kind, data}).catch(()=>{});
}
function setPlayer(meta={}) {
  if (!Number.isFinite(Number(meta.time)) || Number(meta.time)<0) return;
  player = {time:Number(meta.time),paused:!!meta.paused,
    rate:Math.max(0.1,Math.min(4,Number(meta.rate)||1)),measuredAt:performance.now()};
}
function currentMediaTime() {
  if (player.paused) return player.time;
  return player.time + Math.max(0,performance.now()-player.measuredAt)/1000*player.rate;
}
function asView(pieces, length) {
  const bytes=new Int16Array(length);let offset=0;
  for(const part of pieces){bytes.set(part,offset);offset+=part.length;}
  return bytes;
}
let audioClient=null;
let audioOptions={};
const durableClients=new Map();
let sampleStart=null;
let sampleEnd=0;
const workletWaiters=new Map();
let playerTransition=Promise.resolve();
function emitDurable(context,kind,data){
  return chrome.runtime.sendMessage({type:'VKN_ASR_EVENT',target:'background',...context,kind,data}).then(r=>{
    if(!r?.ok)throw Error(r?.error||'扩展尚未保存识别结果');
  });
}
let pressureTime=0;
function onPressure(context,message){
  if(Date.now()-pressureTime<3000)return;pressureTime=Date.now();
  emitDurable(context,'pressure',{message}).catch(()=>{});
}
async function restoreStreams(){
  for(const m of await VknStreamDB.all()){
    if(m.complete || durableClients.has(m.id))continue;
    const client=new VknDurableStream(m,(kind,data)=>emitDurable(m.context,kind,data),text=>onPressure(m.context,text));
    durableClients.set(m.id,client);
    if(!m.closed)await client.enqueue(null,m.lastTime||0,m.lastTime||0,2);
    client.connect();
  }
}
const restoreReady=restoreStreams().catch(e=>console.error('缓存恢复失败',e));
function clearPending(){sampleParts=[];sampleTotal=0;sampleStart=null;}
function flushPending(){
  if(!sampleTotal || !audioClient)return;
  const pcm=asView(sampleParts,sampleTotal),start=sampleStart,end=Math.max(start,sampleEnd),client=audioClient;
  clearPending();client.enqueue(pcm,start,end).catch(e=>onPressure(client.meta.context,e.message));
}
function feedPcm(incoming){
  if(!audioClient || !incoming?.length || player.paused || asrPaused)return;
  const end=currentMediaTime();
  if(sampleStart===null)sampleStart=Math.max(0,end-incoming.length/RATE*player.rate);
  sampleEnd=end;sampleParts.push(incoming);sampleTotal+=incoming.length;
  if(sampleTotal>=PACKET_SAMPLES)flushPending();
}
async function gateWorklet(paused,node=processor){
  if(!node)return true;
  const id=crypto.randomUUID();
  return new Promise(resolve=>{
    const timer=setTimeout(()=>{workletWaiters.delete(id);resolve(false);},800);
    workletWaiters.set(id,()=>{clearTimeout(timer);resolve(true);});
    try{node.port.postMessage({type:'gate',paused,id});}
    catch{clearTimeout(timer);workletWaiters.delete(id);resolve(false);}
  });
}
async function attachAsr(options){
  if(!capture||!ctx||!source)throw Error('未建立标签音频流');
  if(asrActive)return {running:true,tabId:capture.tabId,sessionKey:capture.sessionKey};
  const ticket=++asrEpoch,context={...capture},localCtx=ctx,localSource=source;
  const check=()=>{if(ticket!==asrEpoch||ctx!==localCtx||!capture)throw cancelled();};
  asrPhase='starting';
  try{
    if(detachPromise)await detachPromise;check();
    await restoreReady;check();audioOptions=options||audioOptions||{};
    await localCtx.audioWorklet.addModule(chrome.runtime.getURL('audio-processor.js'));check();
    const client=await VknDurableStream.create(context,audioOptions,(kind,data)=>emitDurable(context,kind,data),text=>onPressure(context,text));
    durableClients.set(client.meta.id,client);client.connect();
    if(ticket!==asrEpoch||ctx!==localCtx||!capture){client.finish().catch(e=>onPressure(context,e.message));throw cancelled();}
    audioClient=client;
    processor=new AudioWorkletNode(localCtx,'vkn-speech-processor');
    silent=localCtx.createGain();silent.gain.value=0;
    const node=processor;
    node.port.onmessage=event=>{
      if(event.data instanceof Int16Array){if(processor===node)feedPcm(event.data);}
      else if(event.data?.type==='gated'){workletWaiters.get(event.data.id)?.();workletWaiters.delete(event.data.id);}
    };
    asrPaused=false;asrActive=true;asrPhase='running';
    localSource.connect(processor);processor.connect(silent);silent.connect(localCtx.destination);
    sendEvent('started',{streamSessionId:client.meta.id,contextEpoch:client.meta.captureBoundary||0,message:'音频缓存采集已启动；本地模型首次加载时文字会稍后补齐'});
    return {running:true,phase:asrPhase,tabId:capture.tabId,sessionKey:capture.sessionKey};
  }catch(e){if(ticket===asrEpoch)asrPhase='idle';throw e;}
}
function detachAsr(){
  ++asrEpoch;
  if(detachPromise)return detachPromise;
  const node=processor,gain=silent,localSource=source,client=audioClient,context=capture?{...capture}:client?.meta.context;
  asrActive=false;asrPhase='stopping';
  // First cut off NEW input. Existing tail messages may still be flushed below.
  try{if(node)localSource?.disconnect(node);}catch{}
  if(!node&&!client){asrPaused=false;asrPhase='idle';releaseIfIdle();return Promise.resolve({running:false,draining:false,tabId:context?.tabId});}
  detachPromise=(async()=>{
    let confirmed=true;
    try{
      confirmed=await gateWorklet(true,node);
      flushPending();
    }finally{
      try{node?.disconnect();}catch{};if(node)node.port.onmessage=null;
      try{gain?.disconnect();}catch{}
      if(processor===node)processor=null;if(silent===gain)silent=null;
      if(audioClient===client)audioClient=null;
      asrPaused=false;asrActive=false;asrPhase='idle';clearPending();
      releaseIfIdle();
      // Neither a slow IndexedDB write nor a disconnected model can hold capture open.
      if(client)client.finish().catch(e=>onPressure(context,'采集已停止，但尾段未完整落盘；保留内存缓存，请勿关闭浏览器，释放磁盘空间后重试。'+e.message));
    }
    const warning=confirmed?'':'音频工作线程未确认最后不足200毫秒的尾缓冲，可能缺失这部分；已停止采集，其余已缓存内容保留。';
    if(context)emitDurable(context,'stopped',{running:false,draining:!!client,tailConfirmed:confirmed,message:warning||'采集已停止，缓存尾段仍会补录/翻译；不是继续录音。'}).catch(()=>{});
    return {running:false,paused:false,draining:!!client,tailConfirmed:confirmed,warning,loraRunning:loraActive,tabId:context?.tabId};
  })().finally(()=>{detachPromise=null;});
  return detachPromise;
}
async function setAsrPaused(paused){
  if(!asrActive)throw Error('语音识别尚未启动');
  if(asrPaused===paused)return {running:true,paused};
  const ticket=asrEpoch,node=processor,client=audioClient;
  if(paused){
    try{source?.disconnect(node);}catch{}
    const confirmed=await gateWorklet(true,node);
    if(ticket!==asrEpoch||!asrActive)return {running:false,paused:false};
    flushPending();asrPaused=true;asrPhase='paused';
    client.chain.then(()=>client.enqueue(null,client.meta.lastTime,client.meta.lastTime,1)).catch(e=>onPressure(client.meta.context,e.message));
    if(!confirmed)sendEvent('warning',{message:'已暂停采集，但最后不足200毫秒尾缓冲未获确认；已缓存内容保留。'});
  }else{
    clearPending();
    const confirmed=await gateWorklet(false,node);
    if(ticket!==asrEpoch||!asrActive)return {running:false,paused:false};
    if(!confirmed)throw Error('音频工作线程未响应，仍保持暂停；请停止后重新开始。');
    asrPaused=false;asrPhase='running';source.connect(node);
  }
  sendEvent('asr_pause_state',{streamSessionId:client.meta.id,contextEpoch:client.meta.captureBoundary||0,paused,message:paused?'已暂停新音频，已缓存内容继续补齐':'已继续采集音频'});
  return {running:true,paused};
}
async function updatePlayer(msg){
  const ticket=asrEpoch;
  const transition=asrActive && (msg.reset||player.paused!==!!msg.paused||Math.abs(player.rate-(Number(msg.rate)||1))>.01);
  if(transition){
    const client=audioClient;const confirmed=await gateWorklet(true);
    if(ticket!==asrEpoch||!asrActive)return;
    flushPending();await client.chain;
    if(ticket!==asrEpoch||!asrActive)return;
    await client.enqueue(null,client.meta.lastTime,client.meta.lastTime,1);
    if(!confirmed)sendEvent('warning',{message:'播放状态变化时音频尾段未确认；请核对该处转写。'});
  }
  if(ticket!==asrEpoch)return;
  setPlayer(msg);
  if(audioClient)sendEvent('caption_clock',{streamSessionId:audioClient.meta.id,contextEpoch:audioClient.meta.captureBoundary||0});
  if(transition && asrActive && !asrPaused)await gateWorklet(false);
}
async function startCapture(message){
  const ticket=++captureEpoch;
  if(stopCapturePromise)await stopCapturePromise;
  if(ticket!==captureEpoch)throw cancelled();
  if(capture)throw Error('已有采集流，请先停止当前采集');
  const check=()=>{if(ticket!==captureEpoch)throw cancelled();};
  capture={tabId:message.tabId,sessionKey:message.sessionKey,title:message.title||'',url:message.url||''};
  setPlayer(message.player);clearPending();
  let acquired=null;
  try{
    const mediaSource=message.mediaSource==='desktop'?'desktop':'tab';
    acquired=await navigator.mediaDevices.getUserMedia({
      audio:{mandatory:{chromeMediaSource:mediaSource,chromeMediaSourceId:message.streamId}},
      video:{mandatory:{chromeMediaSource:mediaSource,chromeMediaSourceId:message.streamId}}
    });
    if(ticket!==captureEpoch){acquired.getTracks().forEach(t=>t.stop());throw cancelled();}
    if(!acquired.getAudioTracks?.().length){acquired.getTracks().forEach(t=>t.stop());throw Error('CAPTURE_NO_AUDIO：没有得到共享音轨，没有开始听写。');}
    stream=acquired;ctx=new AudioContext();source=ctx.createMediaStreamSource(stream);
    if(mediaSource==='tab')source.connect(ctx.destination); // tabCapture suppresses native audio; desktop sharing does not
    await ctx.resume();check();
    videoPreview=document.createElement('video');videoPreview.muted=true;videoPreview.playsInline=true;videoPreview.autoplay=true;
    videoPreview.srcObject=new MediaStream(stream.getVideoTracks());
    try{await videoPreview.play();}catch{}check();frameCanvas=document.createElement('canvas');
    if(message.enableAsr)await attachAsr(message.options);check();
    acquired.getTracks().forEach(track=>track.addEventListener('ended',()=>{
      if(ticket===captureEpoch&&!stopInProgress)stopCapture(true).catch(()=>{});
    },{once:true}));
    return {running:asrActive,captureRunning:true,tabId:capture.tabId,sessionKey:capture.sessionKey};
  }catch(e){
    if(ticket===captureEpoch){sendEvent('warning',{message:'标签页音视频采集失败：'+String(e.message||e)});await stopCapture(false);}
    throw e;
  }
}
function frameToJpeg(){
  if(!videoPreview||!frameCanvas||videoPreview.readyState<2 || !videoPreview.videoWidth)return null;
  const crop=(videoCrop && videoCrop.width>0.2 && videoCrop.height>0.2) ? videoCrop : {x:0,y:0,width:1,height:1};
  const sx=Math.floor(videoPreview.videoWidth*crop.x),sy=Math.floor(videoPreview.videoHeight*crop.y);
  const sw=Math.floor(videoPreview.videoWidth*crop.width),sh=Math.floor(videoPreview.videoHeight*crop.height);
  const width=Math.min(960,sw);
  const height=Math.round(sh*width/sw);
  if(height<100)return null;
  frameCanvas.width=width;frameCanvas.height=height;
  const c=frameCanvas.getContext('2d',{willReadFrequently:false});
  c.drawImage(videoPreview,sx,sy,sw,sh,0,0,width,height);
  // Local JPEG only; no upload to remote providers.
  return frameCanvas.toDataURL('image/jpeg',0.81);
}
// Only the already-consented live tab stream; never capture another tab/window.
function captionFrame(){
  if(!asrActive||asrPaused||player.paused||!audioClient||!videoPreview||videoPreview.readyState<2)return null;
  // Do not fall back to the whole browser viewport: the video must be fully visible.
  const crop=videoCrop;if(!crop||crop.partial||crop.width<.15||crop.height<.15)return null;
  const w=videoPreview.videoWidth,h=videoPreview.videoHeight;if(!w||!h)return null;
  const sx=Math.floor(w*(crop.x+crop.width*.06)),sy=Math.floor(h*(crop.y+crop.height*.62)),sw=Math.floor(w*crop.width*.88),sh=Math.floor(h*crop.height*.34);
  const canvas=document.createElement('canvas');canvas.width=Math.min(1280,sw);canvas.height=Math.round(sh*canvas.width/sw);
  if(canvas.width<220||canvas.height<48)return null;
  canvas.getContext('2d').drawImage(videoPreview,sx,sy,sw,sh,0,0,canvas.width,canvas.height);
  return {time:currentMediaTime(),image:canvas.toDataURL('image/jpeg',.9),stream:audioClient.meta.id,epoch:audioClient.meta.captureBoundary||0};
}
async function captureCaptionPair(msg){
  if(!capture||capture.tabId!==msg.tabId||capture.sessionKey!==msg.sessionKey)throw Error('CAPTION_CAPTURE_TARGET');
  const ticket=asrEpoch,a=captionFrame();if(!a)throw Error('CAPTION_NO_FRAME：请让播放器完整可见；未采集网页其他区域');
  await new Promise(r=>setTimeout(r,450));
  if(ticket!==asrEpoch||!capture||capture.sessionKey!==msg.sessionKey)throw Error('CAPTION_CANCELLED');
  const b=captionFrame();if(!b||a.stream!==b.stream||a.epoch!==b.epoch||b.time<=a.time||b.time-a.time>2)throw Error('CAPTION_FRAME_CHANGED');
  return {frames:[a,b]};
}

async function startLora(msg){
  if(!capture || !videoPreview)throw Error('未启动视频采集流');
  if(loraActive || loraStopping)throw Error('上一轮画面采集尚未结束');
  if(!/^[a-f0-9]{32}$/.test(msg.sessionId||''))throw Error('LoRA任务标识无效');
  const ticket=++loraEpoch;
  const interval=Math.max(1,Math.min(20,Number(msg.rule?.interval_seconds)||4));
  loraContext={tabId:capture.tabId,sessionKey:capture.sessionKey};
  loraPendingFrames=0;
  const socket=new WebSocket('ws://127.0.0.1:8765/lora/stream/'+msg.sessionId);
  loraConnection=socket;
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{socket.close();reject(Error('本地视觉模型采集通道连接超时'));},6500);
    socket.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});
    socket.addEventListener('error',()=>{clearTimeout(timer);reject(Error('本地视觉采集服务连接失败'));},{once:true});
  });
  if(ticket!==loraEpoch||!capture){socket.close();throw cancelled();}
  socket.addEventListener('message',event=>{
    let m;try{m=JSON.parse(event.data);}catch{return;}
    if(m.type==='accepted')sendEvent('lora_frame',{entry:m.entry,status:m.status});
    else if(m.type==='error')sendEvent('lora_error',{message:m.message,status:m.status});
    else if(m.type==='status'||m.type==='limit'||m.type==='ready')sendEvent('lora_status',{status:m.status,limit:m.type==='limit'});
    else if(m.type==='stopped'){
      sendEvent('lora_stopped',{status:m.status});
      loraStopping=false;loraActive=false;releaseIfIdle();
      socket.close(1000,'complete');loraConnection=null;
    }
  });
  socket.addEventListener('close',()=>{
    if(loraConnection===socket){
      if(loraActive)sendEvent('lora_error',{message:'视觉采集连接断开，部分画面可能未处理'});
      loraActive=false;loraStopping=false;loraConnection=null;
      if(frameTimer){clearInterval(frameTimer);frameTimer=null;}
      releaseIfIdle();
    }
  });
  loraActive=true;
  frameTimer=setInterval(()=>{
    if(!loraActive || player.paused || socket.readyState!==WebSocket.OPEN)return;
    if(socket.bufferedAmount>2_000_000){loraPendingFrames++;return;}
    try{
      const image=frameToJpeg();
      if(image)socket.send(JSON.stringify({type:'frame',time:currentMediaTime(),image}));
    }catch(e){sendEvent('lora_error',{message:'画面截取失败：'+e.message});}
  },interval*1000);
  sendEvent('lora_status',{message:'开始按要求采样，正在等待视觉模型评估'});
  return {running:true,session_id:msg.sessionId,interval_seconds:interval};
}
async function stopLora(){
  ++loraEpoch;
  if(frameTimer){clearInterval(frameTimer);frameTimer=null;}
  const wasActive=loraActive;loraActive=false;
  if(wasActive && loraConnection?.readyState===WebSocket.OPEN){
    loraStopping=true;
    try{loraConnection.send(JSON.stringify({type:'stop'}));}
    catch{loraStopping=false;try{loraConnection.close();}catch{}loraConnection=null;}
    sendEvent('lora_status',{running:false,processing:loraStopping,message:'画面采集已停止；已排队候选仍在评估，不再获取新图。'});
  }else if(loraConnection?.readyState===WebSocket.CONNECTING){
    try{loraConnection.close();}catch{}loraConnection=null;loraStopping=false;
  }
  releaseIfIdle();
  return {running:false,processing:loraStopping};
}
function stopCapture(){
  ++captureEpoch;++loraEpoch;
  if(stopCapturePromise)return stopCapturePromise;
  stopInProgress=true;
  const context=capture?{...capture}:null;
  stopCapturePromise=(async()=>{
    try{
      // Detach first, before any queue, network or model awaits.
      const tail=detachAsr();
      await stopLora();
      const result=await tail;
      return {...result,running:false,captureRunning:false,loraRunning:false,loraProcessing:loraStopping,tabId:context?.tabId||result.tabId};
    }finally{releaseCaptureResources();stopInProgress=false;}
  })().finally(()=>{stopCapturePromise=null;});
  return stopCapturePromise;
}
chrome.runtime.onMessage.addListener((msg,_sender,reply)=>{
  if(msg?.target!=='offscreen')return false;
  (async()=>{
    if(['VKN_CAPTURE_STOP','VKN_ASR_STOP','VKN_LORA_STOP'].includes(msg.type)&&msg.expectedTabId&&capture?.tabId&&capture.tabId!==msg.expectedTabId)throw Error('另一个标签页正在采集，请在该标签页停止');
    switch(msg.type){
      case 'VKN_CAPTION_PAIR':return await captureCaptionPair(msg);
      case 'VKN_ASR_PREPARE':await restoreReady;return {ready:true};
      case 'VKN_CAPTURE_START':return await startCapture(msg);
      case 'VKN_CAPTURE_STOP':return await stopCapture(false);
      case 'VKN_ASR_ATTACH':return await attachAsr(msg.options);
      case 'VKN_ASR_PAUSE':return setAsrPaused(true);
      case 'VKN_ASR_RESUME':return setAsrPaused(false);
      case 'VKN_LORA_START':return await startLora(msg);
      case 'VKN_LORA_STOP':return await stopLora();
      case 'VKN_ASR_START':return await startCapture({...msg,enableAsr:true});
      case 'VKN_ASR_STOP':{if(!loraActive)++captureEpoch;return await detachAsr();}
      case 'VKN_ASR_RETRY':{for(const client of durableClients.values()){if(client.meta.context.sessionKey===msg.sessionKey)await client.retry(msg.options);}return {ok:true};}
      case 'VKN_ASR_STATUS':return {running:asrActive,phase:asrPhase,streamSessionId:audioClient?.meta.id||'',contextEpoch:audioClient?.meta.captureBoundary||0,stopping:!!detachPromise||!!stopCapturePromise,paused:asrPaused,draining:[...durableClients.values()].some(x=>(x.meta.closed||x.finishing)&&!x.disabled),captureRunning:!!capture,loraRunning:loraActive,loraProcessing:loraStopping,tabId:capture?.tabId||null,sessionKey:capture?.sessionKey||null};
      case 'VKN_ASR_PLAYER_STATE':
        if(capture && capture.tabId===msg.tabId && capture.sessionKey===msg.sessionKey){
          playerTransition=playerTransition.catch(()=>{}).then(()=>updatePlayer(msg));
          await playerTransition;
          if(msg.crop && [msg.crop.x,msg.crop.y,msg.crop.width,msg.crop.height].every(x=>Number.isFinite(Number(x))) &&
             msg.crop.x>=0 && msg.crop.y>=0 && msg.crop.width>0 && msg.crop.height>0 &&
             msg.crop.x+msg.crop.width<=1.01 && msg.crop.y+msg.crop.height<=1.01){videoCrop=msg.crop;}
        }
        return {ok:true};
      default:throw Error('未知本地采集指令');
    }
  })().then(value=>reply({ok:true,data:value}),err=>reply({ok:false,error:String(err?.message||err)}));
  return true;
});
