/* Options and the background use the same config resolver and model test path. */
'use strict';
const $=id=>document.getElementById(id);
const status=(msg,bad=false)=>{$('status').textContent=msg;$('status').style.color=bad?'#ff9e9e':'#a9dff9';};
let summaryDirty=false,summaryBusy=false,verificationId=null;
const summaryFields=['preset','endpoint','model','apiKey','autoSummary','summaryMinutes'];
const summaryButtons=['save','test','useLocal'];
function markDirty(){
  summaryDirty=true;
  $('summarySaveState').textContent='有未保存的修改。点击「保存」或「保存并验证」后，深度整理才使用修改后的配置。';
}
function updateDisabled(){
  const offline=$('preset').value==='offline';
  for(const id of summaryButtons)$(id).disabled=summaryBusy;
  for(const id of summaryFields)$(id).disabled=summaryBusy||(offline&&['endpoint','model','apiKey','autoSummary'].includes(id));
  const local=$('preset').value==='ollama'||VknAiConfig.isLocalOllama($('endpoint').value);
  $('apiKeyField').hidden=local||offline;$('localOriginHelp').hidden=!local||offline;
  $('apiKey').disabled=summaryBusy||local||offline;
  $('show').disabled=summaryBusy||local||offline;
}
function setBusy(value){summaryBusy=value;updateDisabled();}
async function readStore(){return chrome.storage.local.get(['vknAiConfig','vknSpeechConfig']);}
function fillSummary(store){
  const c=VknAiConfig.resolve(store);
  $('preset').value=c.provider;
  $('endpoint').value=c.endpoint;$('model').value=c.model;$('apiKey').value=c.apiKey;
  $('autoSummary').checked=c.autoSummary;$('summaryMinutes').value=String(c.summaryMinutes);
  summaryDirty=false;
  $('summarySaveState').textContent=c.saved?'已读取保存的摘要设置。连接状态需要单独验证。':
    '尚未单独保存摘要设置：后台当前使用本机默认配置 / 已保存的听写文字模型，不会自动选择云端。';
  updateDisabled();
}
async function refreshEffective(){
  try{
    const r=await chrome.runtime.sendMessage({type:'VKN_AI_STATUS'});
    if(!r?.ok)throw Error(r?.error||'扩展后台无响应');
    const c=r.data;
    const source={'default-local':'本机默认值','speech-local':'复用已保存的听写文字模型','saved':'已保存的摘要设置',
      'saved-local-completed':'已保存的本机地址＋文字模型','saved-offline':'已保存的离线模式'}[c.source]||c.source;
    $('effectiveConfig').textContent=c.configured?
      '深度整理实际读取：'+c.model+'\n接口：'+c.endpoint+'\n配置来源：'+source+'。此处不代表已完成连接或推理验证。':
      '深度整理尚未启用：'+(c.error||source);
    const id=chrome.runtime.id||'';
    $('runtimeInfo').textContent='扩展版本 '+c.version+(id?' · 扩展 ID '+id:'')+' · 说话人功能需要本地听写服务 0.6.0';
  }catch(e){$('effectiveConfig').textContent='读取后台配置失败：'+e.message+'。请在扩展管理页重新加载此扩展。';}
}
function configFromForm(){
  const provider=$('preset').value;
  const raw={provider,enabled:provider!=='offline',endpoint:$('endpoint').value.trim(),model:$('model').value.trim(),
    apiKey:$('apiKey').value.trim(),autoSummary:$('autoSummary').checked,summaryMinutes:Number($('summaryMinutes').value)};
  if(provider==='offline'){raw.endpoint='';raw.model='';raw.apiKey='';raw.autoSummary=false;}
  if(provider==='custom'&&(!raw.endpoint||!raw.model))throw Error('自定义摘要接口需要同时填写地址和模型名称；不会自动切换到本地或其他服务。');
  return VknAiConfig.resolve({vknAiConfig:raw,vknSpeechConfig:{textModel:$('textModel').value.trim()}});
}
function requestPermission(u){
  // Start this in the direct click handler, before awaiting storage/network work.
  return chrome.permissions.request({origins:[u.protocol+'//'+u.hostname+'/*']});
}
async function saveSummaryForm(){
  const cfg=configFromForm();
  if(cfg.enabled&&!await requestPermission(VknAiConfig.endpoint(cfg.endpoint)))
    throw Error('AI_PERMISSION：未获得该接口访问授权，旧配置未改变，也不会发送字幕。');
  const saved=VknAiConfig.stored(cfg);
  await chrome.storage.local.set({vknAiConfig:saved});
  const checked=(await chrome.storage.local.get('vknAiConfig')).vknAiConfig;
  if(!checked||Object.keys(saved).some(k=>checked[k]!==saved[k]))throw Error('AI_STORAGE_VERIFY：保存后读回的配置不一致。请关闭其他设置页，再重新保存。');
  fillSummary({vknAiConfig:checked});
  $('summarySaveState').textContent='✓ 摘要配置已保存，并已读回核对。';
  await refreshEffective();
  return cfg;
}
async function saveAndVerify(){
  let didSave=false;
  setBusy(true);status('正在保存摘要配置并准备验证…');
  try{
    const cfg=await saveSummaryForm();didSave=true;
    if(!cfg.enabled){status('已保存离线模式：不会调用模型。实时记录、离线阶段摘录和导出仍可使用。');return;}
    status('✓ 摘要设置已保存。正在通过与深度整理相同的后台路径执行短文本推理；首次加载模型可能较慢。\n此测试只发送“连接正常”的测试提示，不发送视频笔记。');
    verificationId='verify-'+Date.now();$('cancelTest').hidden=false;
    const r=await chrome.runtime.sendMessage({type:'VKN_AI_TEST',requestId:verificationId});
    if(!r?.ok)throw Error(r?.error||'AI_TEST_CHANNEL：后台未返回测试结果。请重新加载原扩展后重试。');
    status('✓ 摘要配置已保存，后台短文本推理验证通过。\n模型：'+r.data.model+'\n模型回复：'+r.data.reply+'\n现在可返回视频面板，点击“AI 深度整理”。该检测不保证长视频的整理质量或速度。');
  }catch(e){status((didSave?'设置已经保存，但推理验证失败：':'配置未保存：')+e.message,true);}
  finally{verificationId=null;$('cancelTest').hidden=true;setBusy(false);}
}
$('cancelTest').addEventListener('click',async()=>{
  try{const r=await chrome.runtime.sendMessage({type:'VKN_AI_CANCEL',kind:'test',requestId:verificationId});if(!r?.ok)throw Error(r?.error||'后台未回应');status(r.data.message);}
  catch(e){status('取消未确认：'+e.message,true);}
});
$('preset').addEventListener('change',()=>{
  if($('preset').value==='ollama'){
    $('endpoint').value=VknAiConfig.DEFAULT_ENDPOINT;
    $('model').value=$('textModel').value.trim()||VknAiConfig.DEFAULT_MODEL;
    $('apiKey').value='';
  }
  if($('preset').value==='offline')$('autoSummary').checked=false;
  markDirty();updateDisabled();
});
for(const id of summaryFields){$(id).addEventListener('input',markDirty);$(id).addEventListener('change',markDirty);}
$('show').addEventListener('click',()=>{const x=$('apiKey');x.type=x.type==='password'?'text':'password';$('show').textContent=x.type==='password'?'显示':'隐藏';});
$('save').addEventListener('click',async()=>{
  setBusy(true);status('正在保存摘要配置并读回核对…');
  try{const cfg=await saveSummaryForm();status(cfg.enabled?'✓ 摘要设置已保存并读回核对。尚未进行推理验证；可点击“保存并验证实际推理”。':'✓ 已保存离线模式，不会调用模型。');}
  catch(e){status('保存失败：'+e.message,true);}finally{setBusy(false);}
});
$('test').addEventListener('click',saveAndVerify);
$('useLocal').addEventListener('click',()=>{
  $('preset').value='ollama';$('endpoint').value=VknAiConfig.DEFAULT_ENDPOINT;
  $('model').value=$('textModel').value.trim()||VknAiConfig.DEFAULT_MODEL;$('apiKey').value='';
  markDirty();return saveAndVerify();
});
setBusy(true);
(async()=>{
  try{const store=await readStore();fillSummary(store);await refreshEffective();}
  catch(e){status('读取摘要设置失败：'+e.message,true);$('summarySaveState').textContent='配置未能加载。可使用一键修复保存本机配置；不会删除原有笔记。';}
  finally{setBusy(false);}
})();
if(chrome.storage.onChanged)chrome.storage.onChanged.addListener((changes,area)=>{
  if(area==='local'&&(changes.vknAiConfig||changes.vknSpeechConfig))refreshEffective();
});

try{$('originCommand').value=VknLocalOrigin.command(chrome.runtime.id);}catch(e){$('originCopyStatus').textContent=e.message;}
$('copyOrigin').addEventListener('click',async()=>{
  try{await navigator.clipboard.writeText($('originCommand').value);$('originCopyStatus').textContent='已复制。请在 PowerShell 执行，完整退出并重新启动 Ollama 后再验证。命令不会自动停止任何进程。';}
  catch{$('originCommand').closest('details').open=true;$('originCommand').focus();$('originCommand').select();$('originCopyStatus').textContent='浏览器未允许复制，请手动复制选中的命令。';}
});
$('endpoint').addEventListener('input',updateDisabled);

const speechStatus=(text,bad=false)=>{$('speechStatus').textContent=text;$('speechStatus').style.color=bad?'#ffb9aa':'#b2e1fa';};
$('saveSpeech').addEventListener('click',async()=>{
  try{
    const textModel=$('textModel').value.trim();
    if(!/^[a-zA-Z0-9_.:/-]{1,100}$/.test(textModel)||/cloud/i.test(textModel))throw Error('请填写本地模型名，不支持cloud模型');
    // Automatic mode may be saved before optional models are installed. Missing
    // acoustic components degrade to unassigned text, not a failed settings save.
    await chrome.storage.local.set({vknSpeechConfig:{language:$('speechLanguage').value,chunkSeconds:Number($('chunkSeconds').value),translate:$('translate').checked,correct:$('correct').checked,speakerMode:$('diarize').checked?'auto':'off',diarize:$('diarize').checked,maxSpeakers:Number($('maxSpeakers').value),hotwords:$('hotwords').value.trim().slice(0,600),textModel}});
    speechStatus('✓ 听写设置已保存。下一轮听写生效。若尚未单独配置摘要，深度整理会复用这个本地文字模型；已有自定义摘要设置不变。');
    await refreshEffective();
    if(!summaryDirty){const s=await readStore();if(!VknAiConfig.resolve(s).saved)fillSummary(s);}
  }catch(e){speechStatus('保存失败：'+e.message,true);}
});
$('diagnose').addEventListener('click',async()=>{
  $('diagnose').disabled=true;speechStatus('正在检测本地服务与模型列表（不会加载模型）…');
  try{
    const r=await fetch('http://127.0.0.1:8765/diagnostics',{method:'POST',signal:AbortSignal.timeout(12000),redirect:'error'});
    const j=await r.json();if(!r.ok)throw Error('请启动0.6.0听写服务；HTTP '+r.status);
    const models=j.ollama.models||[],text=$('textModel').value.trim();
    const has=m=>models.includes(m)||(!m.includes(':')&&models.includes(m+':latest'));
    speechStatus('ASR 服务 '+j.asr.version+' / '+j.asr.model+' / '+j.asr.device+' / '+(j.asr.loaded?'已加载':'首次识别时加载')+'\n'+
      '说话人区分：'+(j.asr.speaker_diarization?.message||'旧服务不支持，请更新本地服务至0.6.0')+'\n'+
      'Ollama：'+(j.ollama.ok?'已连接':j.ollama.error||'无法连接')+'\n'+
      '文字模型 '+text+'：'+(has(text)?'已安装':'未安装，请执行 ollama pull '+text)+'\n'+
      '视觉模型 qwen2.5vl:3b：'+(has('qwen2.5vl:3b')?'已安装':'未安装，请执行 ollama pull qwen2.5vl:3b')+'\n'+
      '运行中：'+((j.ollama.running||[]).map(x=>x.name+'（显存 '+Math.round((x.size_vram||0)/1024/1024)+' MB）').join('、')||'暂无，首次使用会加载')+'\n'+
      '仅验证连接和安装状态，不代表模型推理质量或速度已验证。');
  }catch(e){speechStatus('本地诊断失败：'+e.message+'。请关闭旧服务后运行 START_LOCAL_ASR.bat。',true);}
  finally{$('diagnose').disabled=false;}
});
(async()=>{
  const c=(await chrome.storage.local.get('vknSpeechConfig')).vknSpeechConfig||{};
  $('speechLanguage').value=c.language||'auto';$('chunkSeconds').value=String([6,12,18].includes(Number(c.chunkSeconds))?c.chunkSeconds:12);$('translate').checked=c.translate!==false;$('correct').checked=c.correct===true;
  $('diarize').checked=c.speakerMode!=='off';$('maxSpeakers').value=String(c.maxSpeakers||8);
  $('textModel').value=c.textModel||'qwen2.5:3b';$('hotwords').value=c.hotwords||'';
})().catch(e=>speechStatus('读取听写设置失败：'+e.message,true));

// ASR is a server-wide engine.  Never change it mid-session or claim a profile
// was activated before the operator restarts this project's local service.
const asrStatus=(msg,bad=false)=>{const el=$('asrStatus');el.textContent=msg;el.style.color=bad?'#ffb9aa':'#b2e1fa';};
const asrRequestHeaders=()=>({'X-VKN-Extension-ID':chrome.runtime.id});
async function refreshAsr(){
  try{
    const response=await fetch('http://127.0.0.1:8765/asr/config',{method:'GET',headers:asrRequestHeaders(),redirect:'error',signal:AbortSignal.timeout(10000)});
    if(!response.ok){
      const info=await response.json().catch(()=>null);
      throw Error('HTTP '+response.status+(info?.detail?' / '+info.detail:''));
    }
    const state=await response.json();
    const names=state.installed_ollama_asr_models||[];
    $('installedAsrModels').replaceChildren(...names.map(name=>{const el=document.createElement('option');el.value=name;return el;}));
    const next=state.next_profile;
    $('asrProfile').value=['legacy','ollama17'].includes(next)?next:'qwen17';
    $('ollamaAsrModel').value=next==='ollama17'?state.next_model:(names.includes('frozenlab/qwen3-asr:1.7b')?'frozenlab/qwen3-asr:1.7b':names[0]||'frozenlab/qwen3-asr:1.7b');
    asrStatus('当前运行：'+state.active_profile+' / '+state.active_model+'\n下次启动：'+next+' / '+state.next_model+
      (state.restart_required?'\n设置已保存，但必须重启本地服务才会生效。':'\n当前与下次启动配置一致。')+
      '\nOllama：'+(state.ollama_reachable?'已连接':'未连接')+'；已发现的ASR模型：'+(names.join('、')||'无'));
  }catch(error){asrStatus('本地ASR配置读取失败：'+error.message+'。先确认8765端口正在运行当前服务；若为403，请检查扩展来源授权或是否加载了旧版插件。',true);}
}
$('refreshAsr').addEventListener('click',refreshAsr);
$('saveAsrProfile').addEventListener('click',async()=>{
  const b=$('saveAsrProfile');b.disabled=true;
  asrStatus('正在校验本地模型。首次装载可能较慢；不发送视频或笔记，当前服务继续使用旧引擎。');
  try{
    const chosen=$('asrProfile').value;
    if(!['legacy','ollama17'].includes(chosen))throw Error('原生Qwen请使用INSTALL_ALL安装和切换');
    const model=$('ollamaAsrModel').value.trim();
    const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),210000);
    let response;
    try{response=await fetch('http://127.0.0.1:8765/asr/config',{method:'POST',headers:{'Content-Type':'application/json',...asrRequestHeaders()},
      body:JSON.stringify({profile:chosen,model:chosen==='ollama17'?model:undefined}),redirect:'error',signal:controller.signal});}
    finally{clearTimeout(timeout);}
    const data=await response.json();
    if(!response.ok)throw Error(data.detail||'HTTP '+response.status);
    asrStatus('已保存：'+data.selected+(data.model?' / '+data.model:'')+'。请停止当前听写，运行STOP_LOCAL_ASR.bat后重启START_LOCAL_ASR.bat。旧音频与笔记未修改。');
  }catch(error){asrStatus('没有切换引擎：'+error.message+'。旧配置与记录保留。',true);}
  finally{b.disabled=false;}
});
refreshAsr();
