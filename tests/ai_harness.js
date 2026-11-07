'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function makeHarness(options={}){
  const root=options.extension||path.join(__dirname,'../extension');
  const state=structuredClone(options.store||{}),requests=[],listeners=[];
  function cloneSorted(v){if(Array.isArray(v))return v.map(cloneSorted);if(v&&typeof v==='object')return Object.fromEntries(Object.keys(v).sort().map(k=>[k,cloneSorted(v[k])]));return v;}
  const storage={
    async get(k){if(options.storageError)throw Error('storage unavailable');if(k==null)return cloneSorted(state);
      const keys=typeof k==='string'?[k]:Array.isArray(k)?k:Object.keys(k);const r={};
      for(const key of keys)if(Object.hasOwn(state,key))r[key]=cloneSorted(state[key]);return r;},
    async set(v){Object.assign(state,structuredClone(v));},async remove(k){for(const key of [].concat(k))delete state[key];},
    async setAccessLevel(){}
  };
  const noop={addListener(){}};
  const chrome={storage:{local:storage,onChanged:noop},runtime:{id:'a'.repeat(32),getURL:p=>'chrome-extension://'+'a'.repeat(32)+'/'+p,
    getManifest:()=>({version:'0.5.2'}),onInstalled:noop,onMessage:{addListener(fn){listeners.push(fn);}},openOptionsPage:async()=>{}},
    permissions:{contains:async()=>options.permission!==false},action:{onClicked:noop},tabs:{onRemoved:noop}};
  const mockFetch=async(url,opts={})=>{
    requests.push({url:String(url),opts});
    if(options.fetch)return options.fetch(String(url),opts);
    if(String(url).endsWith('/api/tags'))return new Response(JSON.stringify({models:(options.models||['qwen2.5:3b','qwen2.5:7b']).map(name=>({name}))}));
    return new Response(JSON.stringify({choices:[{message:{content:'## 知识文档\n\n[00:01] 测试内容；模型输出已模拟。'}}]}));
  };
  const ctx=vm.createContext({chrome,console,URL,URLSearchParams,AbortController,AbortSignal,setTimeout,clearTimeout,Promise,Response,fetch:mockFetch});
  ctx.importScripts=(...names)=>names.forEach(name=>vm.runInContext(fs.readFileSync(path.join(root,name),'utf8'),ctx,{filename:name}));
  vm.runInContext(fs.readFileSync(path.join(root,'background.js'),'utf8'),ctx,{filename:'background.js'});
  const send=message=>new Promise((resolve,reject)=>{
    try{const used=listeners.some(fn=>fn(message,{id:chrome.runtime.id,url:chrome.runtime.getURL('options.html')},resolve));
      if(!used)reject(Error('message not handled'));}catch(e){reject(e);}
  });
  return {ctx,state,requests,send,storage};
}
module.exports={makeHarness};
