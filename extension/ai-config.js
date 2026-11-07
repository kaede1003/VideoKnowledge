/* Shared summary configuration. No I/O, no secret-bearing status fields. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  root.VknAiConfig=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const DEFAULT_ENDPOINT='http://127.0.0.1:11434/v1/chat/completions';
  const DEFAULT_MODEL='qwen2.5:3b';
  const text=x=>typeof x==='string'?x.trim():'';
  const owns=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
  const minutes=v=>[2,3,5,10,15].includes(Number(v))?Number(v):5;
  function endpoint(raw){
    let u;try{u=new URL(text(raw));}catch{throw Error('AI_CONFIG_URL：摘要接口地址无效，请在设置的「阶段摘要与手动深度整理」中修改。');}
    if(u.protocol!=='https:'&&!(u.protocol==='http:'&&['localhost','127.0.0.1'].includes(u.hostname)))
      throw Error('AI_CONFIG_URL：只允许 HTTPS 接口或本机 localhost / 127.0.0.1 的 HTTP 接口。');
    if(u.username||u.password||u.hash)throw Error('AI_CONFIG_URL：接口地址不能包含用户名、密码或 # 片段。');
    // Only normalize the known local Ollama endpoint; do not rewrite cloud/provider URLs.
    if(['localhost','127.0.0.1'].includes(u.hostname)&&u.protocol==='http:'&&u.port==='11434'){
      u.hostname='127.0.0.1';
      if(['/','/v1','/v1/','/api/chat'].includes(u.pathname))u.pathname='/v1/chat/completions';
    }
    return u;
  }
  function isLocalOllama(raw){
    try{const u=new URL(raw);return u.protocol==='http:'&&['localhost','127.0.0.1'].includes(u.hostname)&&u.port==='11434';}
    catch{return false;}
  }
  function localModel(raw){
    const m=text(raw);
    if(!/^[A-Za-z0-9_.:/-]{1,120}$/.test(m)||/cloud/i.test(m))
      throw Error('AI_CONFIG_MODEL：本地摘要需要已下载的本地文字模型，例如 qwen2.5:3b；不能使用 cloud 模型名。');
    return m;
  }
  function resolve(store={}){
    const raw=store.vknAiConfig;
    if(raw!=null&&(typeof raw!=='object'||Array.isArray(raw)))throw Error('AI_CONFIG_FORMAT：已保存的摘要配置格式异常，请用设置页的一键修复按钮重新保存；不会删除笔记。');
    const cfg=raw||{},speech=store.vknSpeechConfig||{};
    const common={schemaVersion:1,auto:false,summaryMinutes:minutes(cfg.summaryMinutes),autoSummary:cfg.autoSummary===true,savedAt:text(cfg.savedAt)};
    const ep=text(cfg.endpoint),m=text(cfg.model),key=text(cfg.apiKey);
    // Legacy explicit empty pair represented OFFLINE. Never silently enable it.
    const legacyOffline=owns(cfg,'endpoint')&&owns(cfg,'model')&&!ep&&!m&&cfg.provider!=='ollama'&&cfg.enabled!==true;
    if(cfg.provider==='offline'||cfg.enabled===false||legacyOffline)
      return {...common,enabled:false,provider:'offline',endpoint:'',model:'',apiKey:'',autoSummary:false,source:'saved-offline',saved:true};
    const speechModel=text(speech.textModel)||DEFAULT_MODEL;
    if(!ep&&!m&&!key){
      return {...common,enabled:true,provider:'ollama',endpoint:DEFAULT_ENDPOINT,model:localModel(speechModel),apiKey:'',
        source:text(speech.textModel)?'speech-local':'default-local',saved:false};
    }
    // A partial custom setting is not permission to choose another destination.
    if(!ep&&cfg.provider!=='ollama')throw Error('AI_CONFIG_INCOMPLETE：摘要模型已保存，但接口地址为空。请保存摘要设置；不会自动切换其他服务。');
    const u=endpoint(ep||DEFAULT_ENDPOINT),local=isLocalOllama(u.toString());
    if(cfg.provider==='ollama'&&!local)throw Error('AI_CONFIG_PROVIDER：已选择本地 Ollama，但接口地址不是本机 11434。请修改地址或明确选择自定义接口。');
    if(!m&&(!local||cfg.provider==='custom'))throw Error('AI_CONFIG_INCOMPLETE：摘要接口已保存，但模型名称为空。请在摘要设置中补齐并保存。');
    const model=local?localModel(m||speechModel):m;
    return {...common,enabled:true,provider:local?'ollama':'custom',endpoint:u.toString(),model,
      apiKey:local?'':key,source:!m?'saved-local-completed':'saved',saved:true};
  }
  function stored(cfg){
    return {schemaVersion:1,enabled:cfg.enabled,provider:cfg.provider,endpoint:cfg.endpoint,model:cfg.model,
      apiKey:cfg.apiKey||'',auto:false,autoSummary:cfg.enabled&&cfg.autoSummary===true,
      summaryMinutes:minutes(cfg.summaryMinutes),savedAt:new Date().toISOString()};
  }
  function publicStatus(store,version='0.5.1'){
    try{
      const c=resolve(store);
      const u=c.endpoint?new URL(c.endpoint):null;
      return {configured:c.enabled,model:c.model,provider:c.provider,endpoint:u?u.origin+u.pathname:'',source:c.source,saved:c.saved,
        autoSummary:c.autoSummary,summaryMinutes:c.summaryMinutes,version,
        error:c.enabled?'':'AI_DISABLED：你已选择离线模式；需要深度整理时，请在设置中明确启用本地模型或自定义接口。'};
    }catch(e){return {configured:false,model:'',provider:'invalid',endpoint:'',source:'invalid',saved:true,autoSummary:false,
      summaryMinutes:minutes(store?.vknAiConfig?.summaryMinutes),version,error:String(e.message||e)};}
  }
  function requireEnabled(cfg){if(!cfg.enabled)throw Error('AI_DISABLED：摘要已设为离线模式。请打开设置，点击「一键使用本地文字模型并验证」，或明确保存自定义接口。');return cfg;}
  return {DEFAULT_ENDPOINT,DEFAULT_MODEL,endpoint,isLocalOllama,localModel,resolve,stored,publicStatus,requireEnabled};
});
