/* Caption evidence only: no platform downloads, no independent subtitle transcript. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.VknCaptions=api;})(globalThis,function(){
  'use strict';
  const clean=t=>String(t||'').replace(/<\/?(?:b|i|u|c|v|ruby|rt|lang|span)[^>]*>/gi,'').replace(/[\u200b-\u200d\ufeff]/g,'').replace(/\s+/g,' ').trim();
  const hash=t=>{let h=2166136261;for(const ch of String(t)){h=Math.imul(h^ch.charCodeAt(0),16777619);}return (h>>>0).toString(16);};
  function observation(x){
    if(!x||typeof x!=='object'||!/^([a-f0-9]{32})$/.test(String(x.stream||'')))return null;
    const text=clean(x.text),start=Number(x.start),end=Number(x.end),epoch=Number(x.epoch);
    if(!text||text.length>1200||!Number.isFinite(start)||start<0||!Number.isFinite(end)||end<start||end-start>30||!Number.isInteger(epoch)||epoch<0)return null;
    if(!['track','visible','frame'].includes(x.source))return null;
    return {id:String(x.id||('cap-'+hash(x.stream+'|'+epoch+'|'+start+'|'+text))).slice(0,120),stream:x.stream,epoch,text,start,end,source:x.source,
      language:String(x.language||'unknown').slice(0,20),kind:String(x.kind||'unknown').slice(0,30),samples:Math.max(1,Math.min(200,Number(x.samples)||1)),
      seenSpan:Math.max(0,Math.min(30,Number(x.seenSpan)||0)),frameHashes:Array.isArray(x.frameHashes)?x.frameHashes.map(String).slice(0,2):[]};
  }
  function cleanObservations(xs){return (Array.isArray(xs)?xs:[]).map(observation).filter(Boolean).slice(-6000);}
  function mergeObservations(xs,add){const map=new Map(cleanObservations(xs).map(o=>[o.id,o]));for(const o of cleanObservations(add))map.set(o.id,o);return [...map.values()].slice(-6000);}
  function visible(el,video){
    if(!el||el.closest?.('#vkn-embed-root'))return false;
    const r=el.getBoundingClientRect(),v=video.getBoundingClientRect(),style=getComputedStyle(el);
    return r.width>0&&r.height>0&&style.display!=='none'&&style.visibility!=='hidden'&&Number(style.opacity)!==0
      &&r.right>v.left&&r.left<v.right&&r.bottom>v.top&&r.top<v.bottom;
  }
  function readVisible(video,doc=document){
    const t=Number(video?.currentTime);if(!video||!Number.isFinite(t)||video.paused||video.seeking)return [];
    const out=[];
    for(const tr of Array.from(video.textTracks||[])){
      if(!['subtitles','captions'].includes(tr.kind)||!['showing','hidden'].includes(tr.mode))continue;
      for(const c of Array.from(tr.activeCues||[])){
        if(c.startTime>t||c.endTime<t||c.endTime-c.startTime>30)continue;
        const text=clean(c.text);if(text)out.push({text,start:c.startTime,end:c.endTime,source:'track',language:tr.language||'unknown',kind:/auto|自动|自動/i.test(tr.label)?'automatic':'unknown'});
      }
    }
    if(out.length)return out.slice(0,4);
    // Scope to dedicated subtitle elements inside the video rectangle, never comments/danmaku.
    for(const selector of ['.ytp-caption-window-container .ytp-caption-segment','.bpx-player-subtitle-panel-text','.bilibili-player-video-subtitle-panel-text']){
      const nodes=Array.from(doc.querySelectorAll(selector)).filter(el=>visible(el,video));
      if(nodes.length){const text=clean(nodes.map(el=>el.textContent).join(' '));if(text&&text.length<=1200)return [{text,start:t,end:t,source:'visible',language:'unknown',kind:'unknown'}];}
    }
    return [];
  }
  function evidenceFor(cue,observations){
    if(!cue?.id||cue.manuallyEdited||!Number.isFinite(cue.end)||cue.end<cue.time)return [];
    const sid=cue.id.split(':')[0],epoch=Number(cue.contextEpoch||0);
    return cleanObservations(observations).filter(o=>o.stream===sid&&o.epoch===epoch&&o.end>=cue.time-.25&&o.start<=cue.end+.25).sort((a,b)=>a.start-b.start).slice(0,24);
  }
  function fingerprint(c,evidence){return hash(JSON.stringify([c.original||c.text,c.contextEpoch,c.time,c.end,evidence.map(x=>[x.id,x.samples,x.end,x.text])]));}
  return {clean,hash,observation,cleanObservations,mergeObservations,readVisible,evidenceFor,fingerprint};
});
