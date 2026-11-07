/* Durable audio outbox. Ack follows server SQLite commit; events follow browser save.
   No user audio leaves loopback. Reload may lose the last unpersisted worklet frame. */
'use strict';
const VknStreamDB = (()=>{
  let opening;
  function db(){return opening ||= new Promise((resolve,reject)=>{
    const r=indexedDB.open('vkn-stream-v5',1);
    r.onupgradeneeded=()=>{r.result.createObjectStore('sessions',{keyPath:'id'});r.result.createObjectStore('packets',{keyPath:['id','seq']});};
    r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);
  });}
  async function tx(stores,mode,fn){const d=await db();return new Promise((resolve,reject)=>{
    const t=d.transaction(stores,mode);let value;
    t.oncomplete=()=>resolve(typeof value==='function'?value():value);t.onerror=()=>reject(t.error);t.onabort=()=>reject(t.error||Error('本地缓存事务失败'));
    try{value=fn(t);}catch(e){t.abort();reject(e);}
  });}
  const range=(id,a=0,b=4294967295)=>IDBKeyRange.bound([id,a],[id,b]);
  return {
    async all(){return tx(['sessions'],'readonly',t=>{const r=t.objectStore('sessions').getAll();return ()=>r.result;});},
    async meta(id){return tx(['sessions'],'readonly',t=>{const r=t.objectStore('sessions').get(id);return ()=>r.result;});},
    put(meta){return tx(['sessions'],'readwrite',t=>t.objectStore('sessions').put(structuredClone(meta)));},
    packet(meta,buffer){const copy=structuredClone(meta);return tx(['sessions','packets'],'readwrite',t=>{
      t.objectStore('sessions').put(copy);t.objectStore('packets').put({id:copy.id,seq:copy.nextSeq-1,buffer});});},
    async packets(id,after,limit=32){return tx(['packets'],'readonly',t=>{const r=t.objectStore('packets').getAll(range(id,after+1),limit);return ()=>r.result;});},
    ack(meta,seq){const copy=structuredClone(meta);return tx(['packets','sessions'],'readwrite',t=>{
      t.objectStore('packets').delete(range(copy.id,0,seq));t.objectStore('sessions').put(copy);});}
  };
})();
function vknPacket(seq,start,end,flag,pcm){
  const raw=new ArrayBuffer(28+(pcm?.byteLength||0)),v=new DataView(raw);
  for(let i=0;i<4;i++)v.setUint8(i,'VKN5'.charCodeAt(i));
  v.setUint32(4,seq,true);v.setFloat64(8,start,true);v.setFloat64(16,end,true);v.setUint32(24,flag,true);
  if(pcm)new Int16Array(raw,28).set(pcm);return raw;
}
class VknDurableStream {
  constructor(meta,onEvent,onPressure,db=VknStreamDB){
    this.db=db;
    this.meta=meta;this.onEvent=onEvent;this.onPressure=onPressure;this.socket=null;
    this.ready=false;this.disabled=false;this.sending=false;this.sent=meta.acked||0;
    this.chain=Promise.resolve();this.events=Promise.resolve();this.emergency=[];this.timer=null;this.heartbeat=null;this.pauseSendUntil=0;
    this.reconnectAttempts=0;this.lastProbeAt=0;this.lastReceivedAt=0;this.handshakeTimer=null;
    this.lastStats={pendingSeconds:0,textPending:0,textFailed:0};this.retryRequested=false;this.awaitingRetry=false;
  }
  static async create(context,options,onEvent,onPressure,db=VknStreamDB){
    const meta={id:crypto.randomUUID().replaceAll('-',''),context,options,nextSeq:1,acked:0,lastEvent:0,lastTime:0,closed:false,complete:false,created:Date.now()};
    await db.put(meta);return new VknDurableStream(meta,onEvent,onPressure,db);
  }
  serialize(fn){const p=this.chain.then(fn);this.chain=p.catch(()=>{});return p;}
  async enqueue(pcm,start,end,flag=0){
    if(this.meta.closed)throw Error('当前听写已结束');
    const copy=pcm?new Int16Array(pcm):null;
    return this.serialize(async()=>{
      if(this.emergency.length){
        this.emergency.push({pcm:copy,start,end,flag});
        this.onPressure('前一段音频尚未写入缓存，新音频按序保留在内存；请暂停视频，修复磁盘空间后重试。');
        throw Error('仍有未落盘音频，暂停采集并重试缓存');
      }
      const old=structuredClone(this.meta),buf=vknPacket(this.meta.nextSeq++,Math.max(0,start),Math.max(start,end),flag,copy);
      this.meta.lastTime=end;if(flag===1)this.meta.captureBoundary=this.meta.nextSeq-1;if(flag===2)this.meta.closed=true;
      try{await this.db.packet(this.meta,buf);}catch(e){
        Object.assign(this.meta,old);this.emergency.push({pcm:copy,start,end,flag});
        this.onPressure('浏览器磁盘缓存写入失败，已要求暂停视频；未落盘尾段仅保留在内存，勿关闭页面。'+e.message);
        throw e;
      }
      if(this.meta.nextSeq-1-this.meta.acked>2400)this.onPressure('本地服务未确认音频已超过约24分钟，暂停视频以保护缓存，请恢复本地服务后重试');
      this.pump();
    });
  }
  finish(){
    if(this.finishPromise)return this.finishPromise;
    this.finishing=true;
    this.finishPromise=this.chain.catch(()=>{}).then(()=>{
      if(this.meta.closed)return;
      return this.enqueue(null,this.meta.lastTime||0,this.meta.lastTime||0,2);
    });
    this.finishPromise.catch(()=>{});return this.finishPromise;
  }
  notify(kind,data){try{return Promise.resolve(this.onEvent(kind,data)).catch(()=>{});}catch{return Promise.resolve();}}
  reconnectDelay(){return Math.min(30000,1500*Math.pow(2,Math.min(this.reconnectAttempts++,5)));}
  async diagnoseDisconnect(detail){
    if(Date.now()-this.lastProbeAt<30000 || typeof fetch!=='function')return;
    this.lastProbeAt=Date.now();
    const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),3500);
    let diagnostic={...detail,service:'unreachable'};
    try{
      const r=await fetch('http://127.0.0.1:8765/health',{signal:ctrl.signal,redirect:'error',cache:'no-store'});
      const h=await r.json();
      if(!r.ok||h.service!=='vkn-asr')diagnostic.service='wrong_service';
      else diagnostic={...diagnostic,service:'reachable',version:h.version,bootId:h.boot_id||'',workers:h.runtime?.workers||{}};
    }catch{ /* A probe timeout isn't proof of a crash: it can be an overloaded loop. */ }
    finally{clearTimeout(timer);}
    await this.serialize(async()=>{this.meta.transportDiagnostic=diagnostic;await this.db.put(this.meta);}).catch(()=>{});
    if(this.disabled||this.ready)return;
    const explanation=diagnostic.service==='reachable'?'本地服务仍可响应，正在恢复语音连接。':
      diagnostic.service==='wrong_service'?'8765端口响应的不是当前听写服务，请检查是否启动错了程序。':
      '暂时无法联系本地服务，可能退出、繁忙或连接被阻止；请查看服务窗口及日志，不要清空缓存。';
    await this.notify('warning',{message:explanation+' 未确认音频保留。',transport:diagnostic});
  }
  connect(){
    if(this.disabled||this.socket?.readyState===0||this.socket?.readyState===1)return;
    clearTimeout(this.timer);
    const ws=new WebSocket('ws://127.0.0.1:8765/asr');this.socket=ws;this.ready=false;this.sent=this.meta.acked||0;
    this.lastReceivedAt=Date.now();
    const current=()=>this.socket===ws;
    let localCause='';
    const timeout=setTimeout(()=>{if(current()&&!this.ready){localCause='HELLO_TIMEOUT';try{ws.close(4001,'hello timeout');}catch{}}},12000);
    this.handshakeTimer=timeout;
    ws.onopen=()=>{
      if(!current()||this.disabled){ws.close();return;}
      ws.send(JSON.stringify({type:'hello',sessionId:this.meta.id,videoKey:this.meta.context.sessionKey,
        options:this.meta.options,lastEvent:this.meta.lastEvent||0}));
      clearInterval(this.heartbeat);this.heartbeat=setInterval(()=>{
        if(!current()||ws.readyState!==1)return;
        if(Date.now()-this.lastReceivedAt>45000){localCause='HEARTBEAT_TIMEOUT';ws.close(4002,'heartbeat timeout');return;}
        try{ws.send('ping');}catch{ws.close();}
      },15000);
    };
    ws.onmessage=e=>{
      if(!current())return;
      this.lastReceivedAt=Date.now();
      this.events=this.events.then(async()=>{if(current())await this.receive(JSON.parse(e.data));}).catch(async err=>{
        if(!current())return;
        localCause='RESULT_PERSIST_FAILED';
        await this.notify('warning',{message:'结果保存失败，将重连重放；未确认音频保留：'+String(err.message||err)});
        ws.close();
      });
    };
    ws.onerror=()=>{};
    ws.onclose=event=>{
      clearTimeout(timeout);
      // A late close from an old socket must not disable the new connection.
      if(!current())return;
      if(this.awaitingRetry)this.retryRequested=true;
      clearInterval(this.heartbeat);this.socket=null;this.ready=false;
      if(this.disabled)return;
      const detail={time:Date.now(),code:Number(event?.code||1006),clean:!!event?.wasClean,cause:localCause||'TRANSPORT_CLOSED'};
      this.notify('warning',{message:'语音连接中断（代码'+detail.code+'），缓存保留，正在自动重连；不等于已确认服务崩溃。',transport:detail});
      this.diagnoseDisconnect(detail).catch(()=>{});
      this.timer=setTimeout(()=>this.connect(),Math.max(this.reconnectDelay(),this.pauseSendUntil-Date.now()));
    };
  }
  async receive(m){
    if(m.type==='ready'){if(m.protocol!==5){this.disabled=true;this.onPressure('扩展与服务音频协议不匹配，请同时升级插件和本地服务');this.socket.close();}return;}
    if(m.type==='hello'){
      if(m.received<this.meta.acked){this.disabled=true;this.onPressure('服务端缓存记录缺失；已确认音频不在浏览器，停止本轮以避免假装补齐');this.socket.close();return;}
      await this.ack(m.received);clearTimeout(this.handshakeTimer);this.ready=true;this.reconnectAttempts=0;this.sent=m.received;this.sendRetry();this.pump();
      await this.notify('status',{message:'语音连接已建立，按最后确认位置继续处理；已有缓存和笔记保留。'});return;
    }
    if(m.type==='ack'){await this.ack(m.seq);this.pump();return;}
    if(m.type==='backpressure'){
      this.pauseSendUntil=Date.now()+5000;this.sent=Number.isInteger(m.received)?Math.max(this.meta.acked,m.received):this.meta.acked;this.onPressure(m.message);setTimeout(()=>this.pump(),5100);return;
    }
    if(m.type==='error'&&m.retryable){
      await this.notify('warning',{message:m.message||'本地连接暂不可用，缓存保留并自动重试'});
      this.socket?.close();return;
    }
    if(m.type==='error'&&m.fatal){this.disabled=true;this.onPressure(m.message);this.socket?.close();return;}
    if(m.type==='pong')return;
    if(m.type==='retry_ack'){this.awaitingRetry=false;return;}
    if(m.eventId && m.eventId<=this.meta.lastEvent)return;
    if(m.type==='segment')await this.onEvent('segment',m);
    else if(m.type==='progress'){
      this.lastStats=m;await this.onEvent('progress',{...m,unacknowledged:this.meta.nextSeq-1-this.meta.acked});
      if(m.pendingSeconds>180)this.onPressure('识别落后超过3分钟，已暂停视频保护完整性。待队列追上后手动继续视频。');
      if(m.finished && !m.textPending && !this.awaitingRetry && !this.retryRequested && this.meta.closed && this.meta.acked===this.meta.nextSeq-1){
        await this.serialize(async()=>{this.meta.complete=!m.textFailed;await this.db.put(this.meta);});
        await this.onEvent('drained',{message:m.textFailed?'已完成转写，部分译文/纠错失败；原文已保存，可重试':'已缓存音频及文字处理已完成',textFailed:m.textFailed});
        this.disabled=true;this.socket?.close();
      }
    }else if(m.type==='done')await this.onEvent('status',{message:m.message});
    else if(m.message)await this.onEvent('warning',{message:m.message});
    if(m.eventId)await this.serialize(async()=>{this.meta.lastEvent=m.eventId;await this.db.put(this.meta);});
  }
  ack(seq){return this.serialize(async()=>{
    if(seq<this.meta.acked)return;
    if(seq>=this.meta.nextSeq)throw Error('服务确认了不存在的序号');
    const previous=this.meta.acked;this.meta.acked=seq;
    try{await this.db.ack(this.meta,seq);}catch(e){this.meta.acked=previous;throw e;}
  });}
  async pump(){
    if(this.sending||!this.ready||this.disabled||this.socket?.readyState!==1||Date.now()<this.pauseSendUntil)return;
    this.sending=true;
    try{
      const rows=await this.db.packets(this.meta.id,this.sent,32);
      for(const row of rows){
        if(!this.ready||this.socket?.readyState!==1||this.socket.bufferedAmount>256000||this.sent-this.meta.acked>=32)break;
        this.socket.send(row.buffer);this.sent=row.seq;
      }
    }catch(e){this.onPressure('读取缓存失败：'+e.message);}
    finally{this.sending=false;}
    if(this.ready && this.sent<this.meta.nextSeq-1)setTimeout(()=>this.pump(),100);
  }
  sendRetry(){
    if(!this.retryRequested||!this.ready||this.socket?.readyState!==1)return;
    this.awaitingRetry=true;
    this.socket.send(JSON.stringify({type:'retry',options:this.meta.options}));
    this.retryRequested=false;
  }
  async retry(options){
    await this.serialize(async()=>{
      // Keep old and new emergency packets in order until each durable write succeeds.
      while(this.emergency.length){
        const item=this.emergency[0],old=structuredClone(this.meta);
        const buf=vknPacket(this.meta.nextSeq++,Math.max(0,item.start),Math.max(item.start,item.end),item.flag,item.pcm);
        this.meta.lastTime=item.end;if(item.flag===2)this.meta.closed=true;
        try{await this.db.packet(this.meta,buf);}catch(e){Object.assign(this.meta,old);throw e;}
        this.emergency.shift();
      }
      this.meta.options=options||this.meta.options;this.meta.complete=false;
      await this.db.put(this.meta);
    });
    this.disabled=false;this.retryRequested=true;this.awaitingRetry=true;
    this.connect();this.sendRetry();this.pump();
  }
}

if(typeof module==='object' && module.exports)module.exports={VknDurableStream,vknPacket};
