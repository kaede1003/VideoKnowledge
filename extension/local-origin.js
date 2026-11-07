/* Explicit opt-in Ollama origin configuration. Never widens listen addresses. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.VknLocalOrigin=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  function origin(id){if(!/^[a-p]{32}$/.test(String(id||'')))throw Error('扩展 ID 无效，请从本扩展设置页复制');return 'chrome-extension://'+id;}
  function command(id){const value=origin(id);return [
    "$origin = '"+value+"'",
    "$values = @([Environment]::GetEnvironmentVariable('OLLAMA_ORIGINS','Machine'), [Environment]::GetEnvironmentVariable('OLLAMA_ORIGINS','User'), $env:OLLAMA_ORIGINS)",
    "$items = @(($values -join ',').Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })",
    "$merged = (@($items + $origin | Select-Object -Unique) -join ',')",
    "[Environment]::SetEnvironmentVariable('OLLAMA_ORIGINS', $merged, 'User')",
    "$env:OLLAMA_ORIGINS = $merged",
    "Write-Host 'Saved this extension origin. Quit Ollama from the system tray, then reopen it from Start. No API key is required.'"
  ].join('\r\n');}
  function error(status,id){
    const who=/^[a-p]{32}$/.test(String(id||''))?origin(id):'本扩展';
    if(status===403)return 'AI_LOCAL_ORIGIN_403：本机 Ollama 拒绝此扩展请求（HTTP 403）。本地模型不需要 API Key。请在设置页复制「仅允许本扩展访问」命令，将 '+who+' 加入 OLLAMA_ORIGINS 后完整退出并重新启动 Ollama。若仍报错，请检查代理或安全软件；403 本身不能唯一确定原因。';
    return 'AI_LOCAL_ACCESS_'+status+'：本机11434拒绝访问。标准本机 Ollama 不需要 API Key，请检查该端口是否被代理或其他程序占用。不要为此填入云端密钥。';
  }
  return {origin,command,error};
});
