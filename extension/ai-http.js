/* Safe, shared HTTP error diagnostics for chat and long-form inference.
 * Do not echo upstream error bodies, API keys, URL queries or user prompts.
 */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  root.VknAiHttp=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  function requestId(response){
    for(const name of ['x-request-id','x-correlation-id']){
      let value='';try{value=response?.headers?.get?.(name)||'';}catch{}
      // Never use arbitrary header values as user-visible diagnostics.
      if(typeof value==='string'&&/^[A-Za-z0-9_.:-]{6,80}$/.test(value))return value;
    }
    return '';
  }
  function describe(response,cfg,stage='chat',extensionId=''){
    const status=Number(response?.status)||0;
    const local=VknAiConfig.isLocalOllama(cfg?.endpoint);
    const where=stage==='longform'?'长文整理流式 POST':'普通聊天 POST';
    const code='AI_HTTP_'+status;
    let message;
    if(status===401||status===403){
      if(local){
        message=VknLocalOrigin.error(status,extensionId);
        message+=' 当前拒绝的是本机11434的'+where+'，不是本地听写8765，也不表示视频长度超标。';
        message+=' 请在扩展设置的「阶段摘要与手动深度整理」运行“保存并验证实际推理”；它会检查与长文相同的请求方式。';
      }else{
        message=code+'：自定义摘要服务拒绝'+where+'（HTTP '+status+'）。';
        message+=' 请确认当前摘要接口的账号/令牌权限、模型访问资格、额度及服务自身的内容策略。';
        message+=' 进入原扩展设置页执行“保存并验证实际推理”；测试同样失败时应查看服务提供方的拒绝记录。';
        message+=' 403 是明确的服务端拒绝，缩小分块或无限重试不能保证解除。';
      }
    }else if(status===404){
      message=code+'：'+where+'的接口路径或模型不存在。请在摘要设置页确认聊天接口地址和模型名称。';
    }else if(status===413){
      message=code+'：'+where+'被服务端判定请求体过大；已保存检查点。请检查提供方输入容量或适当缩小整理范围。';
    }else if(status===429){
      message=code+'：'+where+'被限流或额度限制；本次没有自动重试，检查点仍在。请检查服务端额度/限制后再继续。';
    }else if(status>=500){
      message=code+'：'+where+'的服务端出错，检查点保留。请查看相应模型服务日志，并确认服务恢复后再续跑。';
    }else{
      message=code+'：'+where+'失败。请在摘要设置页核对服务地址、模型与授权；原文和旧结果保留。';
    }
    const id=requestId(response);
    if(id)message+=' 服务请求编号：'+id+'（可用于向服务提供方排查）。';
    return message;
  }
  return {describe,requestId};
});
