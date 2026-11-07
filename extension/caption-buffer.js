/* Small, bounded, volatile buffer for already-authorized subtitle crops.
 * No filesystem, network, model calls, permission acquisition or audio dependency.
 */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.VknCaptionBuffer=api;})(globalThis,function(){
 'use strict';
 class PairBuffer{
  constructor({maxPairs=24,maxBytes=12*1024*1024,maxAge=60}={}){this.maxPairs=maxPairs;this.maxBytes=maxBytes;this.maxAge=maxAge;this.clear();}
  clear(){this.queue=[];this.bytes=0;this.dropped=0;this.sampled=0;this.context='';}
  push(frames){
   if(!Array.isArray(frames)||frames.length!==2)return false;
   const [a,b]=frames;if(!a||!b||a.stream!==b.stream||a.epoch!==b.epoch||!Number.isFinite(a.time)||!Number.isFinite(b.time)||b.time-a.time<.1||b.time-a.time>2||typeof a.image!=='string'||typeof b.image!=='string')return false;
   const context=a.stream+'|'+a.epoch;if(this.context!==context){this.clear();this.context=context;}
   const bytes=(a.image.length+b.image.length)*2; // Conservative JS string estimate.
   this.sampled++;if(bytes>this.maxBytes){this.dropped++;return false;}
   this.queue.push({frames,bytes});this.bytes+=bytes;
   while(this.queue.length>this.maxPairs||this.bytes>this.maxBytes||b.time-this.queue[0].frames[1].time>this.maxAge)this.drop();
   return true;
  }
  drop(){const p=this.queue.shift();if(p){this.bytes-=p.bytes;this.dropped++;}}
  take(stream,epoch,time){
   while(this.queue.length){const {frames}=this.queue[0];if(frames[0].stream!==stream||frames[0].epoch!==epoch||time-frames[1].time>this.maxAge){this.drop();continue;}
    const p=this.queue.shift();this.bytes-=p.bytes;return p.frames;
   }return null;
  }
  status(){return {queued:this.queue.length,bytes:this.bytes,sampled:this.sampled,dropped:this.dropped,oldest:this.queue[0]?.frames[0].time??null};}
 }
 return {PairBuffer};
});
