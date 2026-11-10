/* Video Knowledge Notebook — content script; works without API keys. */
(() => {
  'use strict';
  if (window.__VIDEO_KNOWLEDGE_NOTEBOOK_LOADED__) return;
  window.__VIDEO_KNOWLEDGE_NOTEBOOK_LOADED__ = true;
  const C=globalThis.VideoKnowledgeCore;
  if(!C) return;
  const $=id=>shadow.getElementById(id);
  const host=document.createElement('div');host.id='vkn-embed-root';
  host.style.cssText='all:initial;position:fixed;display:block;right:10px;top:64px;bottom:auto;left:auto;width:max-content;max-width:calc(100vw - 20px);height:auto;min-height:0;z-index:2147483645;pointer-events:none;contain:layout style;';
  const shadow=host.attachShadow({mode:'closed'});
  const style=document.createElement('style');
  style.textContent=`
  *{box-sizing:border-box}button,input,select{font:inherit}a{color:#8bc8ff;text-decoration:none}
  .outer{font:13px/1.5 system-ui,-apple-system,'Microsoft YaHei',sans-serif;color:#e9eff9;pointer-events:auto}
  .bubble{margin-left:auto;display:flex;align-items:center;justify-content:center;gap:6px;min-width:56px;height:48px;padding:0 13px;border-radius:18px;background:linear-gradient(145deg,#2476ad,#16426e);color:#fff;border:1px solid #80b5df77;box-shadow:0 8px 30px #0005;cursor:pointer;font-size:15px;font-weight:700}
  .bubble small{font-size:10px;font-weight:500}
  .panel{width:min(410px,calc(100vw - 32px));height:min(78vh,750px);max-height:850px;background:#101b2beF;border:1px solid #486380;border-radius:18px;box-shadow:0 14px 46px #0008;overflow:hidden;display:flex;flex-direction:column;backdrop-filter:blur(16px)}
  .panel[hidden],.bubble[hidden],[hidden]{display:none!important}
  header{display:flex;align-items:center;gap:9px;padding:12px 12px 10px;background:#142843;border-bottom:1px solid #33465e}
  .logo{background:#2b88cb55;width:34px;height:34px;display:grid;place-items:center;font-size:20px;border-radius:10px}
  .headtitle{flex:1;min-width:0}.headtitle strong{font-size:14px;display:block}.headtitle small{color:#9fb6d0;font-size:11px}
  .close{background:transparent;border:none;color:#c6d6ea;font-size:20px;cursor:pointer;padding:0 5px}
  .body{padding:13px;overflow-y:auto;flex:1;scrollbar-color:#526a83 #101b2b;scrollbar-width:thin}
  .video{margin:0;font-size:13px;line-height:1.45;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:650}
  .muted{color:#9cb0c7;font-size:11px}.status{margin:10px 0;padding:9px 10px;background:#1a3046;border:1px solid #36516a;border-radius:9px;color:#cbd9e9;font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}
  .status.error{border-color:#c87563;color:#ffd6d1;background:#3d232a}.status.ok{border-color:#518c8b;background:#1d363d}
  .row{display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin:8px 0}.btn{border:1px solid #45617e;background:#24415e;color:#eff6ff;padding:7px 10px;border-radius:9px;cursor:pointer;font-size:12px;transition:background .15s}.btn:hover{background:#335a80}.btn.primary{background:#267ab2;border-color:#3d9bd0}.btn.primary:hover{background:#328fc9}.btn:disabled{opacity:.45;cursor:not-allowed}
  .statbar{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:10px 0}.stat{background:#1c3046;border:1px solid #334b64;padding:8px;border-radius:10px;text-align:center}.stat strong{font-size:17px;display:block}.stat small{font-size:10px;color:#a8bed4}
  h3{font-size:12px;margin:15px 0 7px;color:#a7d6ff;font-weight:700}h3 .tag{font-size:10px;color:#9db4ca;font-weight:400}
  .notes{display:flex;flex-direction:column;gap:7px}.note{background:#1b2d41;padding:9px 10px;border:1px solid #314862;border-radius:9px;color:#e1eaf3;font-size:12px;line-height:1.55;overflow-wrap:anywhere}.note time{color:#80c6fc;font-variant-numeric:tabular-nums;font-size:11px;margin-right:8px}.note p{margin:4px 0 0}.speaker{display:inline-block;border:1px solid #526984;background:#14283e;color:#b8defc;border-radius:5px;margin:0 5px;padding:1px 5px;font-size:10px;cursor:pointer}.speaker-edit{display:flex;gap:6px;margin:8px 0}.speaker-edit select,.speaker-edit input{min-width:0;background:#122337;color:#e8f1fb;border:1px solid #45617e;border-radius:6px;padding:6px;flex:1}.speaker-list{max-height:180px;overflow:auto}
  .preview{color:#dce6f3;font-size:12px;line-height:1.65;background:#1b2a3d;border:1px solid #31445c;border-radius:10px;padding:12px;max-height:330px;overflow:auto;overflow-wrap:anywhere}.preview h1{font-size:18px}.preview h2{font-size:16px;color:#b3d9ff}.preview h3{font-size:14px;color:#bedfff}.preview h4,.preview h5{font-size:13px}.preview ul{padding-left:20px}.preview li{margin:6px 0}.preview p{margin:5px 0}.preview blockquote{border-left:3px solid #488cbe;margin:9px 0;padding-left:10px;color:#c7d6e7}
  .details{margin:12px 0;border-top:1px solid #34485f;padding-top:9px}details summary{cursor:pointer;color:#afc8e0;font-size:12px}details p{margin:8px 0;color:#9fb5cd;font-size:11px}
  .footer{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;border-top:1px solid #314862;background:#14263c;font-size:10px;color:#91a9c1}
  .hint{font-size:11px;color:#9caec2;padding:5px 0}
  textarea.lora-input{width:100%;min-height:82px;resize:vertical;border:1px solid #4a6885;color:#e2efff;background:#162b42;border-radius:9px;padding:10px;line-height:1.5;font-size:12px;font-family:inherit}
  .lora-plan{font-size:11px;line-height:1.6;color:#c9d9ed;white-space:pre-wrap;background:#1b2a3c;border:1px solid #344c68;border-radius:9px;padding:9px;margin-top:6px;max-height:180px;overflow:auto}
  .lora-info{font-size:11px;color:#a5c9e9;margin-top:8px;white-space:pre-wrap}
  .lora-banner{background:#2b2834;border:1px solid #73604d;padding:8px;border-radius:9px;font-size:11px;color:#f0d8b7}
  .summary-card{background:#1a3046;border:1px solid #3d5876;border-radius:9px;padding:10px;margin:7px 0}
  .summary-card .summary-title{font-size:11px;color:#93c6f4;margin-bottom:6px;font-weight:700}
  .summary-card .summary-body{font-size:12px;line-height:1.6;overflow-wrap:anywhere}
  .inline-tag{font-size:10px;color:#a9bacb}

  :focus-visible{outline:2px solid #89c8f2;outline-offset:2px}
  .panel{width:min(390px,calc(100vw - 24px));height:min(82vh,800px);border-radius:14px;background:#111c2b}
  header{background:#182739;padding:10px 14px}.headtitle strong{font-size:15px}.headtitle small.version{display:inline;font-size:10px;margin-left:6px;color:#8298ac;font-weight:400}
  .body{padding:14px}.bubble{min-width:52px;height:42px;border-radius:12px;background:#234e70;font-size:13px}
  .icon-btn{border:0;background:transparent;color:#b8cadd;cursor:pointer;padding:4px 6px;font-size:17px}.close{font-size:24px;padding:0 3px}
  .meta-line{display:flex;align-items:center;gap:12px;font-size:11px;color:#97aec4;margin:5px 0 10px}.meta-line b{font-weight:500;color:#bcd2e5}
  .row{gap:6px}.btn{font-size:12px;padding:7px 10px;border-radius:7px}.btn.danger{border-color:#825e63;background:#3b2d38}.capture-row{margin:6px 0}
  .status{font-size:11px;padding:7px 9px;line-height:1.5;margin:8px 0;max-height:110px;overflow:auto;white-space:normal}
  .section-label{display:block;font-size:12px;color:#b9cce0;margin-bottom:7px;font-weight:600}
  select,input[type=text],input:not([type]),textarea{font:inherit;box-sizing:border-box;min-width:0;max-width:100%}
  select{width:100%;border:1px solid #3b5269;background:#192b3e;color:#e5eef8;border-radius:7px;padding:9px 10px;font-size:13px}
  .compose{border-top:1px solid #2d4157;padding-top:12px;margin-top:12px}.mode-hint{margin:6px 0}.compose-actions{margin-bottom:4px}
  .sub-details{border-top:1px solid #293d52;margin-top:10px;padding-top:8px}.sub-details>summary{font-size:11px;line-height:1.7}
  details p{margin:8px 0}.sub-details textarea{margin-top:8px;min-height:76px}
  .check-line{display:flex;align-items:flex-start;gap:7px;margin:10px 0;color:#b7cada;font-size:11px}.check-line input{flex:none;margin:2px 0 0}
  .range-row{display:flex;gap:10px;margin:8px 0}.range-row label{flex:1;font-size:11px;color:#a7bed3;min-width:0}.range-row input{display:block;width:100%;border:1px solid #3b5269;background:#162738;color:#e6eff9;border-radius:6px;padding:7px;margin-top:4px}
  .result-section{margin-top:15px;border-top:1px solid #2d4157;padding-top:10px}.result-heading{display:flex;justify-content:space-between;gap:8px;align-items:center;min-width:0}.result-heading h3{margin:0;font-size:12px}.result-heading span{font-size:10px;overflow-wrap:anywhere}
  #vkn-report-hint{font-size:10px;margin:4px 0}.preview{max-height:170px;border:1px solid #2e4157;background:#172638;padding:12px;font-size:12px}.preview .empty{color:#8199b0;text-align:center;margin:14px 0}.preview h1{font-size:17px}.preview h2{font-size:15px}
  #vkn-document-picker{margin:8px 0;font-size:12px}.result-actions{align-items:flex-start}.export-menu{position:relative}.export-menu>summary{display:block;font-size:12px;border:1px solid #45617e;padding:7px 10px;border-radius:7px;list-style:none;background:#24415e;color:#eff6ff}.export-menu .row{position:absolute;z-index:5;right:0;width:170px;background:#182a3e;border:1px solid #40576d;padding:8px;border-radius:8px;box-shadow:0 6px 20px #0006}
  #vkn-live{max-height:300px;overflow:auto;margin-top:8px}.note{font-size:12px;padding:8px}.details{margin:12px 0 0;padding-top:10px}.details>summary{font-size:12px;font-weight:500}.details>summary .muted{font-weight:400;margin-left:5px}.hint{font-size:11px}
  .sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}.footer{padding:7px 12px;font-size:10px;background:#162538}
  @media(max-width:440px){.panel{width:calc(100vw - 20px)}.body{padding:9px}}
  /* 0.10: content-sized panel, one bounded scroll owner. No fixed empty footer area. */
  .panel{height:auto;max-height:calc(100dvh - 84px);min-height:0;isolation:isolate}
  header,.footer{flex:0 0 auto}.body{flex:0 1 auto;min-height:0;max-height:calc(100dvh - 170px);overflow:auto;overscroll-behavior:contain;overflow-anchor:none}
  .result-section{flex:none;min-height:0}.preview{min-height:0;max-height:240px;overscroll-behavior:contain}
  #vkn-result-audit{max-height:260px;overflow:auto;overflow-wrap:anywhere}
  .export-menu .row{position:static;margin:6px 0 0;width:auto;max-width:100%;box-shadow:none}
  .note.continuation{border-top-style:dashed}.source-cue{margin:8px 0}.source-cue p{overflow-wrap:anywhere}
  /* A fixed-size, dedicated progress panel: no more jumping one-line status. */
  .task-progress{min-height:156px;margin-top:10px;padding:11px 12px;border:1px solid #41617c;border-radius:10px;background:#192c40;overflow:hidden}
  .task-progress-top{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:12px;font-weight:650;color:#e2f1ff}
  .task-progress-phase-number{flex:none;white-space:nowrap;font-size:11px;color:#9fbed7;font-weight:500;font-variant-numeric:tabular-nums}
  .task-progress-video{margin:5px 0 8px;color:#aec4da;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .task-progress-line{display:flex;gap:8px;justify-content:space-between;align-items:center;min-width:0;margin-bottom:6px}
  .task-progress-phase{font-size:12px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#f0f7ff;font-weight:600}
  .task-progress-percent{white-space:nowrap;font-variant-numeric:tabular-nums;font-size:11px;color:#99ccf5}
  .task-progress-meter{display:block;width:100%;height:12px;border:0;border-radius:8px;overflow:hidden;background:#0b1b2d;accent-color:#49a5e1}
  .task-progress-meter::-webkit-progress-bar{background:#0b1b2d;border-radius:8px}
  .task-progress-meter::-webkit-progress-value{background:linear-gradient(90deg,#318acc,#64c3f0);border-radius:8px;transition:width .18s ease-out}
  .task-progress-meter::-moz-progress-bar{background:#57b7e9;border-radius:8px}
  .task-progress-count{font-size:11px;margin-top:7px;color:#c6daec;font-variant-numeric:tabular-nums;min-height:1.5em}
  .task-progress-note{font-size:10px;margin-top:3px;color:#879fb5;line-height:1.35}
  @media(max-height:520px){.panel{max-height:calc(100dvh - 30px)}.body{max-height:calc(100dvh - 112px)}}
  `;
  shadow.appendChild(style);
  const wrap=document.createElement('div');wrap.className='outer';
  wrap.innerHTML=`    <button class="bubble" id="vkn-bubble" title="打开视频笔记">笔记</button>
    <section class="panel" id="vkn-panel" hidden aria-label="视频笔记">
      <header><div class="headtitle"><strong>视频笔记 <small class="version">0.12.0</small></strong></div><button id="vkn-settings" class="icon-btn" title="模型与听写设置" aria-label="设置">⚙</button><button class="close" id="vkn-close" aria-label="收起面板，不停止采集" title="收起面板，不停止采集">×</button></header>
      <div class="body">
        <h2 class="video" id="vkn-title">正在检测视频…</h2>
        <div class="meta-line"><span><b id="vkn-count">0</b> 条记录</span><span id="vkn-time">00:00</span><span id="vkn-doc" hidden>本地</span><span id="vkn-source" hidden></span></div>
        <div class="row capture-row">
          <button id="vkn-asr" class="btn primary">开始听写</button><button id="vkn-record" class="btn" hidden>暂停</button><button id="vkn-stop-all" class="btn danger" hidden title="停止新音频和画面采集；已缓存内容继续处理">停止采集</button>
        </div>
        <div class="row"><button id="vkn-video-cache" class="btn" title="下载有权保存的视频到本地，完成后72小时自动清理">保存视频（3天）</button><button id="vkn-cache-library" class="btn">本地缓存</button></div><p id="vkn-cache-hint" class="muted" hidden></p>
        <div class="status" id="vkn-status" role="status" aria-live="polite">点击开始听写；首次可在弹窗选择当前视频标签并共享声音。</div>
        <details id="vkn-transcript" class="details"><summary>实时记录 <span class="muted" id="vkn-live-count">0条 · 点击展开</span></summary>
          <p class="muted">同一人的连续发言合并展示，按句换行；原始碎片与校对项可展开查看。</p>
          <div class="notes" id="vkn-live"></div><button id="vkn-load-more" class="btn" hidden>加载更早记录</button>
        </details>
        <section class="compose" aria-label="内容整理">
          <label class="section-label" for="vkn-mode">整理成</label>
          <select id="vkn-mode" aria-label="整理方式"><option value="knowledge">知识文档</option><option value="transcript">文字稿</option><option value="custom">按我的要求</option></select>
          <p class="muted mode-hint" id="vkn-mode-hint">提炼概念、要点和依据，保留来源。</p>
          <details id="vkn-requirements" class="sub-details"><summary>补充要求 / 范围 <span class="muted" id="vkn-request-count">可选</span></summary>
            <label for="vkn-instructions" class="sr-only">补充整理要求</label>
            <textarea id="vkn-instructions" class="lora-input" maxlength="4000" rows="3" placeholder="例如：按场景整理，保留角色对白，不增加剧情。"></textarea>
            <label id="vkn-creative-label" class="check-line" hidden><input type="checkbox" id="vkn-creative">允许创作性润色（结果标记为改写）</label>
            <div class="range-row"><label>从<input id="vkn-range-start" placeholder="不限制" aria-label="整理开始时间"></label><label>到<input id="vkn-range-end" placeholder="不限制" aria-label="整理结束时间"></label></div>
            <p class="muted">默认使用全部已记录文字；范围填写分:秒或时:分:秒。按每条记录的开始时间筛选。</p>
          </details>
          <label class="check-line"><input type="checkbox" id="vkn-context-review" checked>整理前检查同音短语（原文保留）</label>
          <label class="check-line"><input type="checkbox" id="vkn-caption-enabled" checked>对照视频字幕纠错（原文保留）</label>
          <details id="vkn-caption-details" class="sub-details"><summary>字幕校对 <span class="muted" id="vkn-caption-count"></span></summary>
            <label class="check-line"><input type="checkbox" id="vkn-caption-frames" checked>无可读字幕时采样字幕画面，仅发到本机视觉模型</label>
            <p>优先核对当前显示的字幕；画面字幕需 qwen2.5vl:3b。只做对齐的局部纠词，不把翻译字幕当原话。没有可靠依据时仍用听写。</p>
            <p id="vkn-caption-status" class="muted" role="status">等待开始听写。</p>
          </details>
          <div class="row compose-actions"><button id="vkn-ai" class="btn primary">生成整理</button><button id="vkn-ai-cancel" class="btn" hidden>取消生成</button><button id="vkn-view-report" class="btn" disabled>查看结果</button></div>
          <section class="task-progress" id="vkn-task-progress" aria-label="整理任务进度" hidden>
            <div class="task-progress-top"><span>AI 正在整理笔记</span><span class="task-progress-phase-number" id="vkn-task-stage-number">准备中</span></div>
            <div class="task-progress-video" id="vkn-task-video" title="正在整理的视频"></div>
            <div class="task-progress-line"><span class="task-progress-phase" id="vkn-task-stage" role="status" aria-live="polite">准备模型连接</span><span class="task-progress-percent" id="vkn-task-percent">—</span></div>
            <progress class="task-progress-meter" id="vkn-task-meter" max="1" aria-label="当前阶段批次进度"></progress>
            <div class="task-progress-count" id="vkn-task-count">正在连接文字模型…</div>
            <div class="task-progress-note">进度条只统计当前阶段已完成的批次；跨章节合并可能有多轮，暂不估算总耗时。</div>
          </section>
        </section>
        <section id="vkn-result-section" class="result-section" aria-label="整理结果" hidden>
          <div class="result-heading"><h3 id="vkn-report-heading">整理结果</h3><span class="muted" id="vkn-generated">尚未生成</span></div>
          <label class="sr-only" for="vkn-document-picker">选择已保存的整理结果</label><select id="vkn-document-picker" hidden></select>
          <div id="vkn-report-hint" class="hint">听写或导入文字后，选择一种方式生成。</div>
          <article class="preview" id="vkn-preview"><p class="empty">你的整理结果会显示在这里。</p></article>
          <details id="vkn-result-details" class="sub-details" hidden><summary>来源与校对详情</summary><div id="vkn-result-audit" class="muted"></div></details>
          <div class="row result-actions"><button id="vkn-read-full" class="btn" disabled>完整阅读</button><button id="vkn-copy" class="btn" disabled>复制</button>
            <details id="vkn-export-menu" class="export-menu"><summary>导出 ▾</summary><div class="row"><button id="vkn-md" class="btn" disabled>Markdown</button><button id="vkn-html" class="btn" disabled>HTML</button><button id="vkn-txt" class="btn" disabled>TXT</button></div></details>
          </div>
        </section>
        <details id="vkn-tools" class="details"><summary>更多工具</summary>
          <div class="row"><button id="vkn-import" class="btn">导入已有 SRT / VTT 文件</button></div>
          <input type="file" accept=".srt,.vtt,text/vtt" id="vkn-file" hidden>
          <div class="row"><button id="vkn-retry" class="btn">重试翻译</button><button id="vkn-local-help" class="btn">安装帮助</button><button id="vkn-export-notebook" class="btn">导出全部笔记 / 原文</button><button id="vkn-export-audit" class="btn">导出核查 JSON</button></div>
          <details id="vkn-stage-details" class="sub-details"><summary>阶段摘要 <span class="muted" id="vkn-summary-tag">每5分钟</span></summary><p id="vkn-summary-hint" class="hint"></p><button id="vkn-summary-now" class="btn">立即生成阶段摘要</button><div id="vkn-summaries"></div></details>
          <details id="vkn-highlights-details" class="sub-details"><summary>本地关键句摘录</summary><div class="notes" id="vkn-highlights"></div></details>
          <details class="sub-details" id="vkn-speakers"><summary>自动识别声音与剧情角色</summary><p>默认由本地模型根据整段对话及视频字幕自动给每组声音分配内容身份，例如主持人、嘉宾、旁白或剧情人物，无需逐条审核。明确自报或被介绍的姓名可以自动绑定；无法从声音或台词得知的真实姓名不会编造。</p><p class="muted" id="vkn-speaker-hint">有新记录后自动分析；身份称呼自动应用，无法证明的真实姓名仍不强猜。</p><div class="speaker-list" id="vkn-speaker-list"></div></details>
          <details class="sub-details" id="vkn-lora-details"><summary>LoRA 图片采集</summary>
            <p>输入画面要求，保存后主动开始采图。视觉筛选需本地模型，默认关闭。</p>
            <textarea id="vkn-lora-prompt" class="lora-input" maxlength="900" placeholder="只保留清晰完整的单人全身镜头，每4秒一帧，最多80张。"></textarea>
            <div class="row"><button id="vkn-lora-reset" class="btn">新建规则</button><button id="vkn-lora-plan-btn" class="btn primary">保存要求</button><button id="vkn-lora-start" class="btn">开始采图</button><button id="vkn-lora-stop" class="btn">停止采图</button></div>
            <div id="vkn-lora-plan" class="lora-plan">尚未保存筛选要求。</div><div id="vkn-lora-info" class="lora-info"></div><div class="row"><button id="vkn-lora-export" class="btn">导出 LoRA ZIP</button></div>
            <p>仅使用有训练授权的素材。不会绕过受保护画面，自动标注需复核。</p>
          </details>
          <details class="sub-details"><summary>状态与数据管理</summary><div id="vkn-asr-hint" class="hint"></div><div id="vkn-ai-config-hint" class="hint"></div><div id="vkn-import-hint" class="hint">仅听写当前视频声音，不自动读取网页字幕；先运行 START_LOCAL_ASR.bat。</div>
            <p>折叠和隐藏不会停止采集。点击停止后，已录入的缓存仍可能补录、翻译。原始记录与多份整理结果分别保存；生成只在手动点击时运行。</p>
            <button id="vkn-open-report" class="btn">新窗口阅读结果</button><button id="vkn-clear" class="btn danger">清空本视频数据</button>
          </details>
        </details>
      </div>
      <div class="footer"><span id="vkn-privacy">本地保存 · 手动整理</span><span id="vkn-save-status">未保存</span></div>
    </section>
`;
  shadow.appendChild(wrap);
  (document.documentElement||document.body).appendChild(host);

  const state={navigationEpoch:0,navigationPending:false,liveLimit:30,progress:null,aiMode:'knowledge',taskSaving:false,stopRequested:false,stopAllBusy:false,asrActionId:0,loraActionId:0,aiRequestId:null,asrDraining:false,session:null,key:'',full:[],active:true,open:false,lastFullKey:'',lastPageUrl:'',video:null,settings:{},fetching:false,working:false,summaryBusy:false,summaryStartedAt:0,summaryNote:'',lastAiCount:0,lastAiAt:0,saveTimer:null,refreshTimer:null,queued:[],lastTick:0,tips:'',lastError:'',source:'live',switching:false,lastSettingsRead:0,lastAsrStatusRead:0,cueIndex:null,liveRevision:0,speakerRevision:0,renderedLiveKey:'',speakerLabelCache:null,speakerLabelVersion:-1,qualityCache:null,saveFirstAt:0,streamPaintTimer:null,asrRunning:false,asrPaused:false,asrBusy:false,asrNote:'',loraRunning:false,loraProcessing:false,loraBusy:false,loraRule:null,loraId:null,loraTabId:null,loraStatus:null,loraNote:'',loraPlanError:''};
  const call = (type,args={}) => new Promise((resolve,reject)=>{
    const limit={'VKN_ASR_START':15000,'VKN_ASR_STOP':9000,'VKN_ASR_STOP_ALL':10000,'VKN_ASR_STATUS_QUERY':4000,'VKN_ASR_PAUSE':6000,'VKN_ASR_RESUME':6000,'VKN_LORA_STOP':9000}[type];
    const timer=limit?setTimeout(()=>reject(Error('操作未在时限内确认。请暂停视频，再点「停止全部采集」；必要时暂时禁用扩展。')),limit):null;
    try { chrome.runtime.sendMessage({type,...args},response=>{
      clearTimeout(timer);
      if(chrome.runtime.lastError)return reject(Error(chrome.runtime.lastError.message));
      if(!response?.ok)return reject(Error(response?.error||'插件后台操作失败'));
      resolve(response.data);
    });} catch(e){clearTimeout(timer);reject(e);}
  });
  function getKey(){return C.pageKey(location.href,!!document.querySelector('video'));}
  function currentSession(){
    const key=getKey();
    if(key!==state.key){void switchVideo(key);return null;}
    if(state.switching||state.navigationPending||!state.session||state.session.key!==key)return null;
    return state.session;
  }
  function getVideo(){
    const all=[...document.querySelectorAll('video')];
    if(!all.length)return null;
    all.sort((a,b)=>((b.paused?0:100000)+(b.clientWidth*b.clientHeight))-((a.paused?0:100000)+(a.clientWidth*a.clientHeight)));
    return all[0];
  }
  function getTitle(){
    const sels=['h1.ytd-watch-metadata yt-formatted-string','h1.video-title','h1.video-title-v2','h1 .video-title','h1'];
    for(const sel of sels){const t=C.normalizeWhitespace(document.querySelector(sel)?.textContent||'');if(t.length>=3&&t.length<250)return t;}
    return C.normalizeWhitespace(document.querySelector('meta[property="og:title"]')?.content||document.title).replace(/\s*[-|_]\s*(YouTube|哔哩哔哩|bilibili).*$/i,'')||'未命名视频';
  }
  function newSession(key){return {v:1,key,title:getTitle(),url:location.href,createdAt:new Date().toISOString(),updatedAt:'',duration:0,segments:[],aiMarkdown:'',aiGeneratedAt:'',aiCueCount:0,summaries:[],pendingSummary:[],speakerNames:{},speakerEvidence:{},speakerCandidates:[],speakerRoles:{},speakerRoleCandidates:[],speakerOverrides:{},textOverrides:{},documents:[],activeDocumentId:'',writing:C.normalizeWriting({correctPhrases:true}),captionOptions:{enabled:true,frames:true},captionObservations:[],captionReviews:{},viewPreferences:{}};}
  async function persistSnapshot(s){
    if(!s)return false;
    try{await call('VKN_SAVE_SESSION',{session:structuredClone(s)});return true;}
    catch(e){if(state.session===s)$('vkn-save-status').textContent='保存失败：'+e.message.slice(0,38);return false;}
  }
  async function saveNow(){
    clearTimeout(state.saveTimer);state.saveTimer=null;state.saveFirstAt=0;
    const s=currentSession();if(!s)return false;
    const saved=await persistSnapshot(s);
    if(saved&&state.session===s)$('vkn-save-status').textContent='已自动保存';
    return saved;
  }
  function scheduleSave(){
    $('vkn-save-status').textContent='保存中…';clearTimeout(state.saveTimer);
    if(!state.saveFirstAt)state.saveFirstAt=Date.now();
    // Large notebooks should not be cloned/serialized for every ASR packet.
    // Force a durable flush even during an uninterrupted high-rate stream.
    const elapsed=Date.now()-state.saveFirstAt;
    state.saveTimer=setTimeout(saveNow,Math.max(0,Math.min(state.asrRunning?3200:900,12000-elapsed)));
  }
  function invalidateLive(speakers=false){
    state.liveRevision++;state.qualityCache=null;
    if(speakers){state.speakerRevision++;state.speakerLabelCache=null;}
  }
  function renderStreamSoon(){
    if(state.streamPaintTimer)return;
    state.streamPaintTimer=setTimeout(()=>{state.streamPaintTimer=null;render();},130);
  }
  function speakerLabels(){
    if(state.speakerLabelCache&&state.speakerLabelVersion===state.speakerRevision)return state.speakerLabelCache;
    const labels=new Map(C.speakerCatalog(state.session||{}).map(x=>[x.id,x.label]));
    state.speakerLabelCache=labels;state.speakerLabelVersion=state.speakerRevision;
    return labels;
  }
  function showStatus(msg,style=''){$('vkn-status').textContent=msg;$('vkn-status').className='status '+style;}
  function renderTaskProgress(){
    const running=!!state.working,p=state.progress,task=$('vkn-task-progress'),bubble=$('vkn-bubble');
    task.hidden=!running;
    const text=(id,value)=>{const el=$(id);if(el.textContent!==value)el.textContent=value;};
    const bubbleLabel=running?'笔记 · AI整理中':'笔记';
    if(bubble.textContent!==bubbleLabel)bubble.textContent=bubbleLabel;
    bubble.title=running?'正在整理：'+(state.session?.title||'当前视频')+'（收起不会停止任务）':'打开视频笔记';
    if(!running)return;
    const videoTitle=state.session?.title||'当前视频';
    text('vkn-task-video','视频：'+videoTitle);
    $('vkn-task-video').title=videoTitle; // Full title on hover when the line is ellipsized.
    const meter=$('vkn-task-meter');
    if(state.taskSaving){
      text('vkn-task-stage-number','保存结果');text('vkn-task-stage','正在保存知识文档');
      text('vkn-task-count','模型处理已结束，正在保存本视频的整理结果…');
      text('vkn-task-percent','最后一步');
      meter.removeAttribute('value');return;
    }
    if(!p){
      text('vkn-task-stage-number','准备中');text('vkn-task-stage','正在连接文字模型');
      text('vkn-task-count','模型响应后会显示当前阶段和正在处理的批次');
      text('vkn-task-percent','—');meter.removeAttribute('value');return;
    }
    text('vkn-task-stage-number',`阶段 ${p.stageIndex} / ${p.stageTotal}`);
    text('vkn-task-stage',p.phase+(p.round>1?` · 第 ${p.round} 轮`:(p.phase==='汇总全局主题'||p.phase==='跨章节主题合并与去重')?' · 第 1 轮':''));
    text('vkn-task-count',`已完成 ${p.done} / ${p.total} 批 · 正在处理第 ${p.index} 批`);
    text('vkn-task-percent',p.percent+'% · 本阶段');
    // Avoid restarting native progress-bar animation during unrelated ASR
    // updates while this model batch is still running.
    if(meter.max!==p.total)meter.max=p.total;
    if(!meter.hasAttribute('value')||meter.value!==p.done)meter.value=p.done;
    meter.setAttribute('aria-valuetext',`${p.phase}，本轮已完成 ${p.done} / ${p.total} 批`);
  }
  function setOpen(open){state.open=!!open;$('vkn-panel').hidden=!state.open;$('vkn-bubble').hidden=state.open;if(open)render();}
  async function switchVideo(key){
    if(key===state.key&&(state.switching||state.session))return;
    const epoch=++state.navigationEpoch,previous=state.session;
    const pageUrl=location.href;
    // Detach synchronously, before storage/network awaits. A cannot masquerade as B.
    clearTimeout(state.saveTimer);state.saveTimer=null;state.saveFirstAt=0;
    clearTimeout(state.streamPaintTimer);state.streamPaintTimer=null;
    state.cueIndex=null;state.speakerLabelCache=null;state.speakerLabelVersion=-1;
    state.liveRevision++;state.speakerRevision++;state.renderedLiveKey='';state.qualityCache=null;
    clearTimeout(speakerRefreshTimer);speakerRefreshTimer=null;
    speakerRoleHint='有新记录后自动结合前后对话命名内容角色；无需人工审批。';
    state.session=null;state.key=key;state.switching=true;state.navigationPending=false;
    if(state.loraRunning||state.loraBusy)call('VKN_LORA_STOP').catch(()=>{});
    if(state.asrRunning||state.asrBusy)call('VKN_ASR_STOP').catch(()=>{});
    if(state.aiRequestId)call('VKN_AI_CANCEL',{requestId:state.aiRequestId}).catch(()=>{});
    state.aiRequestId=null;state.working=false;state.taskSaving=false;state.summaryBusy=false;
    state.asrActionId++;state.loraActionId++;state.asrRunning=false;state.asrBusy=false;state.asrPaused=false;
    state.loraRunning=false;state.loraBusy=false;state.loraProcessing=false;state.stopRequested=true;
    state.asrDraining=false;state.asrNote='';state.lastTick=0;state.lastAsrStatusRead=0;
    resetCaptionRuntime();
    state.liveLimit=30;state.progress=null;state.taskSaving=false;state.lastFullKey='';state.full=[];state.lastError='';state.tips='';state.source='live';state.queued=[];state.summaryStartedAt=0;state.summaryNote='';
    host.style.display=key?'block':'none';render();
    try{
      // Old snapshot always saves under its own key, never under the new page key.
      if(previous)await persistSnapshot(previous);
      const loaded=key?await call('VKN_GET_SESSION',{key}):null;
      if(epoch!==state.navigationEpoch)return;
      if(getKey()!==key){void switchVideo(getKey());return;}
      if(loaded&&(loaded.key!==key||(loaded.url&&C.pageKey(loaded.url)!==key)))throw Error('SESSION_SOURCE_MISMATCH：载入记录与当前视频不符，已阻止显示旧材料。');
      state.session=key?(loaded||newSession(key)):null;
      if(state.session){
        state.session.title=getTitle();state.session.url=pageUrl;
        state.session.summaries ||= [];state.session.pendingSummary ||= [];
        state.lastAiCount=Number(state.session.aiCueCount)||0;
        const d=Date.parse(state.session.aiGeneratedAt);state.lastAiAt=Number.isFinite(d)?d:0;
        if(state.session.segments.some(c=>c.speakerId))scheduleSpeakerRefresh();
      }
      applyWritingControls();
    }catch(e){if(epoch===state.navigationEpoch){state.session=null;state.lastError='无法载入当前视频记录：'+e.message;}}
    finally{if(epoch===state.navigationEpoch){state.switching=false;render();}}
  }
  // Role inference is incremental and optional: it must never block live ASR
  // or submit audio to the text model. Saving first prevents stale snapshots.
  let speakerCheckBusy=false,speakerRefreshTimer=null;
  let speakerRoleHint='有新记录后自动结合前后对话命名内容角色；无需人工审批。';
  const lastSpeakerCheck=new Map();
  async function refreshSpeakerRoles(force=false){
    const snapshot=currentSession();if(!snapshot||speakerCheckBusy)return;
    const trusted=(snapshot.segments||[]).filter(c=>c.speakerId&&['estimated','manual'].includes(c.speakerStatus)).length;
    if(trusted<(force?1:4))return;
    if(!force&&Date.now()-(lastSpeakerCheck.get(snapshot.key)||0)<45000)return;
    speakerCheckBusy=true;
    speakerRoleHint='正在自动推断各个声音的内容身份与视频中明确出现的姓名…';
    if($('vkn-speakers').open)renderSpeakers();
    try{
      if(!await saveNow()||currentSession()!==snapshot)return;
      lastSpeakerCheck.set(snapshot.key,Date.now());
      const result=await call('VKN_IDENTIFY_SPEAKERS',{sessionKey:snapshot.key});
      if(currentSession()!==snapshot)return;
      speakerRoleHint=result.roleUpdated?`已为 ${result.roleUpdated} 组声音自动分配内容身份；无需确认，可展开查看依据。`:
        (result.reason||'目前无法明确匹配更多声音，已自动保留已识别的身份。');
      if(result.updated||result.roleUpdated){
        const fresh=await call('VKN_GET_SESSION',{key:snapshot.key});
        if(currentSession()!==snapshot||!fresh)return;
        snapshot.speakerNames={...snapshot.speakerNames,...fresh.speakerNames};
        snapshot.speakerEvidence={...snapshot.speakerEvidence,...fresh.speakerEvidence};
        snapshot.speakerCandidates=fresh.speakerCandidates||snapshot.speakerCandidates;
        snapshot.speakerRoles={...snapshot.speakerRoles,...fresh.speakerRoles};
        snapshot.speakerRoleCandidates=fresh.speakerRoleCandidates||snapshot.speakerRoleCandidates;
        invalidateLive(true);scheduleSave();render();
      }else if($('vkn-speakers').open)renderSpeakers();
    }catch(e){if(currentSession()===snapshot){speakerRoleHint='角色分析暂不可用，可能是本地文字模型未就绪；原始听写仍保留。';if($('vkn-speakers').open)renderSpeakers();console.warn('Automatic speaker role analysis deferred:',String(e?.message||e));}}
    finally{speakerCheckBusy=false;}
  }
  function scheduleSpeakerRefresh(){
    if(speakerRefreshTimer)return;
    speakerRefreshTimer=setTimeout(()=>{speakerRefreshTimer=null;void refreshSpeakerRoles(false);},18000);
  }
  function append(items){
    if(!currentSession()||!items?.length||(!state.active&&!items.some(x=>x.source==='local-asr')))return;
    const current=state.session;
    const merged=C.mergeLiveCues(current.segments,items,state.cueIndex);
    state.cueIndex=merged.index;
    if(!merged.changed)return;
    current.segments=merged.cues;current.pendingSummary ||= [];
    // Pending drafts keep the newest revision without an O(pending * all cues)
    // search for every ASR packet.
    const changedIds=new Set(items.map(x=>x.id).filter(Boolean));
    const newById=new Map([...changedIds].map(id=>[id,merged.cues[merged.index.get(id)]]).filter(x=>x[1]));
    current.pendingSummary=current.pendingSummary.map(x=>x.id?(newById.get(x.id)||x):x);
    current.pendingSummary.push(...merged.fresh);
    if(merged.fresh.length&&!state.summaryStartedAt)state.summaryStartedAt=Date.now();
    const known=state.speakerLabelCache;
    const newSpeaker=!!known && items.some(c=>c.speakerId&&!known.has(c.speakerId));
    invalidateLive(newSpeaker);scheduleSave();renderStreamSoon();
    if(merged.fresh.some(c=>c.speakerId))scheduleSpeakerRefresh();
    checkCaptionMatches().catch(()=>{});
  }
  const boundVideos=new WeakSet();
  function bindVideoEvents(v){
    if(!v||boundVideos.has(v))return;boundVideos.add(v);
    for(const type of ['play','pause','seeking','seeked','ratechange','ended'])v.addEventListener(type,()=>{
      if(['pause','seeking','seeked','ratechange','ended'].includes(type)){pauseCaptionWork();caption.stream='';}
      if((!state.asrRunning&&!state.loraRunning)||getVideo()!==v)return;
      chrome.runtime.sendMessage({type:'VKN_ASR_PLAYER_STATE',target:'offscreen',tabId:state.asrTabId||state.loraTabId,sessionKey:state.key,
        time:Number(v.currentTime)||0,paused:v.paused,rate:v.playbackRate||1,reset:['seeking','seeked','ratechange','ended'].includes(type)}).catch(()=>{});
    });
  }
  function onTick(){
    const key=getKey();
    if(key!==state.key){switchVideo(key);return;}
    if(state.switching||state.navigationPending||!state.session)return;
    const v=getVideo();state.video=v;bindVideoEvents(v);
    state.session.title=getTitle();
    if(v){
      const now=Number(v.currentTime)||0;
      if(Number.isFinite(v.duration))state.session.duration=Math.round(v.duration);
      $('vkn-time').textContent=C.formatTime(now);
      if(state.asrRunning || state.loraRunning){
        const area=v.getBoundingClientRect();
        const crop={x:Math.max(0,area.left)/Math.max(1,innerWidth),y:Math.max(0,area.top)/Math.max(1,innerHeight),
          width:Math.max(0,Math.min(innerWidth,area.right)-Math.max(0,area.left))/Math.max(1,innerWidth),
          height:Math.max(0,Math.min(innerHeight,area.bottom)-Math.max(0,area.top))/Math.max(1,innerHeight),partial:area.left<0||area.top<0||area.right>innerWidth||area.bottom>innerHeight};
        chrome.runtime.sendMessage({type:'VKN_ASR_PLAYER_STATE',target:'offscreen',tabId:state.asrTabId||state.loraTabId,sessionKey:state.key,
          time:now,paused:!!v.paused,rate:Number(v.playbackRate)||1,crop,
          reset:Number.isFinite(state.lastTick)&&Math.abs(now-state.lastTick)>5}).catch(()=>{});
      }
      state.lastTick=now;
    }
    if(Date.now()-state.lastSettingsRead>60000){state.lastSettingsRead=Date.now();refreshSettings();}
    maybePeriodicSummary();
    if(Date.now()-state.lastAsrStatusRead>8000 && !state.asrBusy){
      state.lastAsrStatusRead=Date.now();
      call('VKN_ASR_STATUS_QUERY').then(data=>{
        if(!data || !state.key)return;
        const active=!!data.running && data.sessionKey===state.key;
        if(state.asrRunning!==active || (active && state.asrPaused!==!!data.paused)){
          state.asrRunning=active;state.asrPaused=active&&!!data.paused;render();
        }
      }).catch(()=>{});
    }
  }
  function maybePeriodicSummary(){
    const ss=state.session;
    if(!ss || !state.active || state.summaryBusy || state.working || !(ss.pendingSummary||[]).length)return;
    if(!state.summaryStartedAt)state.summaryStartedAt=Date.now();
    const min=[2,3,5,10,15].includes(Number(state.settings.summaryMinutes))?Number(state.settings.summaryMinutes):5;
    if(Date.now()-state.summaryStartedAt>=min*60_000 && ss.pendingSummary.length>=2)runPeriodicSummary(false);
  }
  async function runPeriodicSummary(manual=false){
    const ss=state.session;
    if(!ss || state.summaryBusy)return;
    pauseCaptionWork();
    const snapshot=(ss.pendingSummary||[]).slice(0,120);
    if(!snapshot.length){if(manual)showStatus('当前没有新的转写文本需要阶段总结。');return;}
    state.summaryBusy=true;state.summaryNote='';state.summaryStartedAt=Date.now();render();
    let mode='offline',md='';
    try{
      if(state.settings.autoSummary && state.settings.configured && snapshot.length>=2){
        try{
          const answer=await call('VKN_AI_PERIODIC_SUMMARY',{cues:C.cuesWithSpeakers(ss,snapshot),meta:{title:ss.title,url:ss.url,filter:C.normalizeFilter(ss.contentFilter)}});
          md=answer.markdown;mode='ai';
        }catch(e){
          state.summaryNote='AI阶段摘要未成功（'+e.message+'），已改为离线摘录。';
        }
      }
      if(!md)md=C.buildOfflinePeriodSummary(C.cuesWithSpeakers(ss,snapshot),{title:ss.title,url:ss.url,filter:C.normalizeFilter(ss.contentFilter)});
      if(state.session!==ss||getKey()!==ss.key)return;
      const sorted=C.sortedCues(snapshot);
      ss.summaries||=[];
      ss.summaries.push({start:sorted[0].time,end:sorted[sorted.length-1].time,
        markdown:md,mode,createdAt:new Date().toISOString(),count:snapshot.length});
      // Keep earlier stage summaries; do not silently trim long videos.
      const done=new Set(snapshot.map(C.cueIdentity));
      ss.pendingSummary=(ss.pendingSummary||[]).filter(c=>!done.has(C.cueIdentity(c)));
      if(!state.summaryNote)state.summaryNote=mode==='ai'?'已生成新的AI阶段摘要':'已生成新的本地阶段摘录';
      scheduleSave();
      if(manual)showStatus(state.summaryNote,'ok');
    }catch(e){
      state.summaryNote='阶段摘要处理失败：'+e.message;
      if(manual)showStatus(state.summaryNote,'error');
    }finally{state.summaryBusy=false;render();}
  }
  function renderLive(){
    const el=$('vkn-live');
    if(!$('vkn-transcript').open){el.replaceChildren();state.renderedLiveKey='';return;}
    const ss=state.session,all=ss?.segments||[];
    const renderKey=[ss?.key,state.liveRevision,state.speakerRevision,state.liveLimit].join('|');
    if(state.renderedLiveKey===renderKey)return;
    const previousScroll=el.scrollTop,opened=new Set([...el.querySelectorAll('details[open]')].map(x=>x.dataset.cue));el.replaceChildren();
    // Only convert the tail needed to fill the visible page. Earlier records
    // remain in the notebook/export; 'load more' progressively widens the tail.
    let windowSize=Math.max(120,state.liveLimit*5),start=0,turns=[];
    if(all.length){
      do{
        start=Math.max(0,all.length-windowSize);
        turns=C.readingTurns(C.cuesWithSpeakers(ss,all.slice(start),speakerLabels()));
        if(start===0||turns.length>state.liveLimit+1)break;
        windowSize=Math.min(all.length,windowSize*2);
      }while(true);
    }
    state.renderedLiveKey=renderKey;
    if(!all.length){const span=document.createElement('div');span.className='hint';span.textContent='暂无转写。语音结果完成后自动合并为发言段落。';el.appendChild(span);return;}
    const batch=document.createDocumentFragment();
    for(const turn of turns.slice(-state.liveLimit).reverse()){
      const div=document.createElement('div');div.className='note';
      const a=document.createElement('a');a.href=C.tsUrl(state.session.url,turn.start);a.target='_blank';a.rel='noopener noreferrer';
      a.textContent=C.formatTime(turn.start)+(turn.end>turn.start?'–'+C.formatTime(turn.end):'');div.appendChild(a);
      if(turn.label){const badge=document.createElement('span');badge.className='speaker';badge.textContent=turn.label;badge.title='自动声音分组；归属不确定时不合并。';div.appendChild(badge);}
      const p=document.createElement('p');p.style.whiteSpace='pre-wrap';p.textContent=C.sentenceLines(turn.text).join('\n');div.appendChild(p);
      const d=document.createElement('details');d.className='muted';d.dataset.cue=turn.cueIds[0];d.open=opened.has(d.dataset.cue);
      const h=document.createElement('summary');const risks=turn.records.filter(C.cueNeedsReview).length;
      h.textContent='来源与校对（'+turn.records.length+'条'+(risks?'，有疑点':'')+'）';d.appendChild(h);
      const populateSources=()=>{if(d.dataset.loaded)return;d.dataset.loaded='1';
      for(const c of turn.records){
        const item=document.createElement('div');item.className='source-cue';
        const time=document.createElement('a');time.href=C.tsUrl(state.session.url,c.time);time.target='_blank';time.rel='noopener noreferrer';time.textContent=C.formatTime(c.time);item.appendChild(time);
        const source=document.createElement('p');source.style.whiteSpace='pre-wrap';
        source.textContent='原始识别：'+(c.original||c.text)+(c.translation?'\n译文：'+c.translation:'')+(c.corrected?'\n纠词候选：'+c.corrected:'')+(c.manuallyEdited?'\n人工修订：'+c.manualText:'')+(c.captionReview?'\n字幕依据：'+c.captionReview.evidence+'\n字幕校对：'+c.captionReview.reason:'');item.appendChild(source);
        if(c.captionReview?.status==='applied'){const undo=document.createElement('button');undo.className='speaker';undo.textContent='撤销字幕修订';undo.addEventListener('click',()=>{state.session.captionReviews[c.id]={...c.captionReview,status:'dismissed',text:c.original||c.text};invalidateLive();scheduleSave();render();});item.appendChild(undo);}
        const notes=[c.reviewReason,c.textError,c.speakerReason,c.captionReview?.reason].filter(Boolean);
        if(notes.length){const note=document.createElement('p');note.textContent=notes.join('；');item.appendChild(note);}
        if(c.id){const edit=document.createElement('button');edit.className='speaker';edit.textContent=c.manuallyEdited?'编辑人工修订':'核对 / 修订';edit.addEventListener('click',()=>correctText(c));item.appendChild(edit);
          if(c.manuallyEdited){const reset=document.createElement('button');reset.className='speaker';reset.textContent='撤销修订';reset.addEventListener('click',()=>{if(!confirm('撤销这条人工修订，恢复机器记录？原始识别不变。'))return;delete state.session.textOverrides[c.id];invalidateLive();scheduleSave();render();});item.appendChild(reset);}}
        d.appendChild(item);
      }
      };
      d.addEventListener('toggle',()=>{if(d.open)populateSources();});
      if(d.open)populateSources();
      div.appendChild(d);batch.appendChild(div);
    }
    el.appendChild(batch);
    $('vkn-load-more').hidden=start===0&&turns.length<=state.liveLimit;el.scrollTop=previousScroll;
  }

  function correctText(cue){
    if(!state.session||!cue.id)return;
    const value=prompt('请先点击时间戳核对原视频。输入这条记录的正确原话或中文译文；原始识别与机器译文保留。不要仅凭语句通顺猜改。',cue.manualText||cue.text);
    if(value===null)return;
    if(!value.trim()||value.trim().length>6000){state.lastError='修订不能为空，且不得超过6000字符。';render();return;}
    state.session.textOverrides ||= {};state.session.textOverrides[cue.id]={text:value.trim(),updatedAt:new Date().toISOString()};
    state.tips='已保存人工修订，原始识别保留。旧摘要/结果未重写，请按需重新生成。';state.lastError='';invalidateLive();scheduleSave();render();
  }
  function renderSpeakers(){
    const el=$('vkn-speaker-list');el.replaceChildren();
    $('vkn-speaker-hint').textContent=speakerRoleHint;
    const catalog=C.speakerCatalog(state.session||{});
    if(!catalog.length){el.textContent='等待自动声音分组，无需手工命名。首次请运行 INSTALL_SPEAKER_MODEL.bat 并重启本地服务。多人抢话或声音不足时可能暂不归属；旧字幕没有原音，不能凭文字补出声音。';return;}
    for(const speaker of catalog){
      const row=document.createElement('div');row.className='note';
      const label=document.createElement('strong');label.textContent=speaker.label;
      const info=document.createElement('p');info.className='muted';info.textContent=speaker.reason;
      row.append(label,info);
      if(speaker.evidence){const q=document.createElement('p');q.textContent='['+C.formatTime(speaker.evidenceTime)+'] 原话依据：'+speaker.evidence;row.append(q);}
      el.append(row);
    }
  }
  function correctSpeaker(cue){
    const list=C.speakerCatalog(state.session||{});
    const answer=window.prompt('更正这条记录的说话人（不会改动原文）：\n0：待确认\n'+list.map((x,i)=>(i+1)+'：'+x.label).join('\n'),'0');
    if(answer===null||!/^\d+$/.test(answer.trim()))return;
    const n=Number(answer);if(n<0||n>list.length)return;
    state.session.speakerOverrides ||= {};state.session.speakerOverrides[cue.id]=n?list[n-1].id:'';
    invalidateLive(true);scheduleSave();render();
  }
  function jumpToReport(){
    state.open=true;$('vkn-panel').hidden=false;$('vkn-bubble').hidden=true;
    const body=shadow.querySelector('.body'),target=$('vkn-report-heading');
    if(body&&target){const delta=target.getBoundingClientRect().top-body.getBoundingClientRect().top;body.scrollTop=Math.max(0,body.scrollTop+delta-8);}
    $('vkn-preview').scrollTop=0;
  }
  function openFullReport(){
    const ss=currentSession();if(!ss){showStatus('正在切换或载入当前视频，未打开旧视频的材料。');return;}
    const selected=C.activeDocument(ss);if(!selected)return;
    try{
      // Freeze precisely the displayed selection before opening the new window.
      const snapshot=structuredClone({key:ss.key,title:ss.title,url:ss.url}),doc=structuredClone(selected);
      const html=C.resultHtml(snapshot,doc);
      const win=window.open('','_blank');
      if(!win){showStatus('新窗口被浏览器阻止，可使用网页 HTML 导出。','error');return;}
      win.opener=null;win.document.open();win.document.write(html);win.document.close();
    }catch(e){showStatus(e.message,'error');}
  }
  function renderPeriodSummaries(){
    const el=$('vkn-summaries');el.replaceChildren();
    const rows=state.session?.summaries||[];
    if(!rows.length){const span=document.createElement('div');span.className='hint';span.textContent='阶段摘要尚未生成；也可以点击“立即生成阶段摘要”。';el.appendChild(span);return;}
    for(const item of rows.slice(-6).reverse()){
      const card=document.createElement('div');card.className='summary-card';
      const title=document.createElement('div');title.className='summary-title';
      title.textContent=`${C.formatTime(item.start)}–${C.formatTime(item.end)} · ${item.mode==='ai'?'AI总结':'离线摘录'}`;
      const body=document.createElement('div');body.className='summary-body';
      body.innerHTML=C.markdownToSafeHtml(String(item.markdown||'').slice(0,7000));
      card.append(title,body);el.appendChild(card);
    }
  }
  function renderHighlights(){
    const el=$('vkn-highlights');el.replaceChildren();
    const cues=C.cuesWithSpeakers(state.session||{});
    if(!cues.length){const v=document.createElement('div');v.className='hint';v.textContent='暂无记录。点击“开始本地语音听写”，开始从声音记录。';el.appendChild(v);return;}
    // Prioritize key statements from the latest 6 minutes, without claiming semantic accuracy.
    const t=cues[cues.length-1].time;
    const nearby=cues.filter(x=>x.time>=t-360).slice(-110);
    const refs=C.buildLocalMarkdown(nearby,{title:state.session.title,url:state.session.url,filter:state.session.contentFilter});
    const lines=refs.split('\n').filter(l=>l.startsWith('- [')).slice(-5);
    for(const line of lines){
      const m=line.match(/^- \[([^\]]+)\]\([^)]*\)\s*(.*)$/);
      const div=document.createElement('div');div.className='note';
      const tim=document.createElement('time');tim.textContent=m?.[1]||'';div.appendChild(tim);
      const txt=document.createElement('span');txt.textContent=m?.[2]||line.replace(/^- /,'');div.appendChild(txt);
      el.appendChild(div);
    }
  }
  function render(){
    const s=state.session;
    $('vkn-privacy').textContent=state.settings.autoSummary&&state.settings.configured?'自动阶段摘要 · 手动全文整理':'本地保存 · 手动整理';
    $('vkn-title').textContent=s?.title||'等待视频页面';
    $('vkn-source').textContent=s?'文本来源：'+(state.asrRunning?'本地语音识别':state.source)+' · '+C.formatTime(s.duration||0)+'时长':'请打开一个视频';
    $('vkn-count').textContent=String(s?.segments?.length||0);
    $('vkn-doc').textContent=s?.aiMarkdown?'AI':'本地';
    $('vkn-record').hidden=!state.asrRunning;
    $('vkn-record').textContent=state.asrPaused?'继续听写':'暂停听写';
    $('vkn-record').disabled=state.asrBusy;
    $('vkn-summary-now').disabled=state.summaryBusy || !s || !(s.pendingSummary||[]).length;
    $('vkn-summary-now').textContent=state.summaryBusy?'正在生成阶段摘要…':'📝 立即生成阶段摘要';
    $('vkn-summary-tag').textContent=`每${state.settings.summaryMinutes||5}分钟 · ${state.settings.autoSummary&&state.settings.configured?'AI':'离线摘录'}`;
    $('vkn-summary-hint').textContent=`每${state.settings.summaryMinutes||5}分钟对新转写生成阶段${state.settings.autoSummary&&state.settings.configured?'AI总结':'离线摘录'}。深度整理全文仅手动触发。${state.summaryNote||''}`;
    $('vkn-ai-cancel').hidden=!state.working;
    $('vkn-stop-all').hidden=!(state.asrRunning||state.asrBusy||state.loraRunning||state.loraBusy||state.stopAllBusy);
    $('vkn-asr').hidden=state.asrRunning;
    $('vkn-stop-all').disabled=state.stopAllBusy;
    $('vkn-stop-all').textContent=state.stopAllBusy?'正在停止采集…':'停止采集';
    $('vkn-asr').disabled=state.asrBusy || state.stopAllBusy || !s;
    $('vkn-asr').textContent=state.asrBusy?'操作中…':state.asrRunning?'⏹ 停止语音听写':'开始听写';
    $('vkn-asr-hint').textContent=state.asrRunning ? (state.asrPaused?'● 听写已暂停，点击“继续语音听写”即可恢复；不会停止视频播放。':'● 正在听写；分批识别，默认约12秒音频加重叠与推理时间；文字先保存；可独立暂停/继续。') : (state.stopRequested?'⏹ 新音频记录已停止。已缓存音频/译文可能仍在补录；需要继续时手动开始。':'无字幕也可使用。先运行 START_LOCAL_ASR.bat；如网页按钮无法授权，请单击Edge工具栏插件图标启动。');
    $('vkn-lora-start').disabled=state.loraBusy || !s || !state.loraRule || state.loraRunning || state.loraProcessing;
    $('vkn-lora-stop').disabled=state.stopAllBusy || (!state.loraRunning&&!state.loraBusy);
    $('vkn-lora-stop').textContent='⏹ 停止采图';
    $('vkn-lora-plan-btn').disabled=state.loraBusy || state.loraRunning;
    $('vkn-lora-export').disabled=state.loraBusy || !state.loraId || state.loraRunning || state.loraProcessing;
    if(!state.loraRule)$('vkn-lora-plan').textContent=state.loraPlanError?'规则制定失败：'+state.loraPlanError:'尚无规则。输入要求后保存，无需等待模型加载。';
    if(state.loraRule){
      $('vkn-lora-plan').textContent=(state.loraPlanError?'⚠ 上次修改失败：'+state.loraPlanError+'\n原有规则仍然有效。\n':'')+'要求历史（冲突时最后一条优先）：'+(state.loraRule.instructions||[state.loraRule.prompt]).map((x,i)=>(i+1)+'. '+x).join('\n')+'\n采样间隔：'+state.loraRule.interval_seconds+'秒；上限：'+state.loraRule.max_frames+'张；视觉模型：'+state.loraRule.model;
    }
    if(state.loraRunning) {
      const info=state.loraStatus||{};
      $('vkn-lora-info').textContent='● 正在采图。采样 '+(info.captured||0)+' 帧，已保存 '+(info.accepted||0)+' 张，模型拒绝 '+(info.rejected||0)+'，重复 '+(info.duplicated||0)+'，跳过 '+(info.skipped||0)+'。'+state.loraNote;
    } else if(state.loraProcessing){
      $('vkn-lora-info').textContent='⏹ 采图已停止；仅处理已排队图片，完成后可导出。'+state.loraNote;
    } else if(!state.loraStatus){$('vkn-lora-info').textContent=state.loraNote||'实际筛图需本地 qwen2.5vl:3b；规则保存不需要模型。';
    } else if(state.loraStatus){
      $('vkn-lora-info').textContent='已结束：有效训练候选 '+(state.loraStatus.accepted||0)+' 张。'+state.loraNote;
    }
    $('vkn-ai').disabled=state.working || !s || !(s.segments||[]).length;
    $('vkn-ai').textContent=state.working?'生成中…':'生成整理';
    for(const id of ['vkn-mode','vkn-instructions','vkn-creative','vkn-range-start','vkn-range-end','vkn-context-review'])$(id).disabled=state.working;
    renderTaskProgress();
    const ac=state.settings;
    $('vkn-ai-config-hint').textContent=ac.configured?
      `深度整理 ${ac.version||''}：${ac.provider==='ollama'?'本地 Ollama':'自定义接口'} / ${ac.model||''} · ${ac.saved?'使用已保存的摘要配置':'复用本地默认 / 听写文字模型'}`:
      (ac.error||'深度整理配置尚未就绪，请打开模型设置。');
    if(!s){
      renderResult();$('vkn-live').replaceChildren();$('vkn-summaries').replaceChildren();$('vkn-highlights').replaceChildren();$('vkn-speaker-list').replaceChildren();
      $('vkn-live-count').textContent='0条';
      showStatus(state.lastError||(state.switching?'正在载入当前视频记录…':'当前页面没有可识别的视频'),state.lastError?'error':'');return;
    }
    if(state.lastError)showStatus(state.lastError,'error');
    else if(state.working)showStatus('正在生成'+C.WRITING_MODES[formWriting().mode]+'，可取消；原始记录和旧结果保留。');
    else if(state.asrRunning&&state.asrPaused)showStatus('听写已暂停 · '+s.segments.length+'条已保留。');
    else if(state.asrRunning)showStatus('正在听写 · '+s.segments.length+'条记录。'+(state.asrNote.includes('缓存')?state.asrNote:''),'ok');
    else if(state.asrDraining)showStatus('采集已停止，缓存仍在补录 / 翻译。');
    else if(state.tips)showStatus(state.tips,'ok');
    else if(state.stopRequested||!state.active)showStatus('已停止采集 · 已有记录保留。');
    else if(s.segments.length)showStatus('已记录 '+s.segments.length+' 条，可选择方式生成整理。','ok');
    else showStatus('先启动本地服务，再开始听写；或在更多工具中导入字幕。');
    const revision=state.liveRevision;
    if(!state.qualityCache||state.qualityCache.revision!==revision){
      const q=C.qualityCounts(s.segments);
      for(const id of Object.keys(s.textOverrides||{})){
        const idx=state.cueIndex?.get(id),c=idx===undefined?s.segments.find(x=>x.id===id):s.segments[idx];
        if(c&&!c.manuallyEdited){q.manual++;if(C.cueNeedsReview(c))q.review--;}
      }
      state.qualityCache={revision,value:q};
    }
    const q=state.qualityCache.value;
    $('vkn-live-count').textContent=s.segments.length+'条'+(q.review?' · '+q.review+'条无法自动确认':'')+($('vkn-transcript').open?'':' · 点击展开');
    renderCaptionStatus();
    if(!state.open)return;
    renderLive();
    if($('vkn-tools').open){
      if($('vkn-highlights-details').open)renderHighlights();
      if($('vkn-stage-details').open)renderPeriodSummaries();
      if($('vkn-speakers').open)renderSpeakers();
    }
    renderResult();
  }
  function formWriting(){return C.normalizeWriting({mode:$('vkn-mode').value,correctPhrases:$('vkn-context-review').checked,instructions:$('vkn-instructions').value,creative:$('vkn-creative').checked,start:$('vkn-range-start').value,end:$('vkn-range-end').value,filter:state.session?.contentFilter||C.normalizeFilter()});}
  function applyWritingControls(){
    const o=C.normalizeWriting(state.session?.writing);$('vkn-context-review').checked=state.session?.writing?.correctPhrases!==false;$('vkn-mode').value=o.mode;$('vkn-instructions').value=o.instructions;
    $('vkn-creative').checked=o.creative;$('vkn-range-start').value=o.start;$('vkn-range-end').value=o.end;
    const prefs=state.session?.viewPreferences||{};
    $('vkn-transcript').open=!!prefs.live;$('vkn-tools').open=!!prefs.tools;$('vkn-requirements').open=!!prefs.requirements||o.mode==='custom';
    applyCaptionControls();updateWritingHint();
  }
  function updateWritingHint(){
    const o=formWriting();
    const hints={knowledge:'提炼概念、要点和依据，保留来源。',transcript:'外语发言自动翻译为简体中文，按说话人整理标点和段落；原始听写保留，不做摘要。',custom:'填写你的要求，再生成对应的正文。'};
    $('vkn-mode-hint').textContent=hints[o.mode];$('vkn-creative-label').hidden=o.mode!=='custom';
    $('vkn-request-count').textContent=o.instructions.trim()?'已填写':o.mode==='custom'?'请填写':'可选';
  }
  function rememberWriting(){
    if(!state.session)return;
    state.session.writing=formWriting();updateWritingHint();scheduleSave();
  }
  function renderResult(){
    const s=(!state.switching&&!state.navigationPending&&state.session?.key===getKey())?state.session:null,docs=C.documentHistory(s||{}),d=C.activeDocument(s||{}),picker=$('vkn-document-picker');
    $('vkn-result-section').hidden=!d;
    const signature=(s?.key||'')+'|'+docs.map(x=>C.documentSignature(s,x)).join('|');
    if(picker.dataset.signature!==signature){
      picker.replaceChildren();
      for(let i=docs.length-1;i>=0;i--){const x=docs[i],option=document.createElement('option');option.value=x.id;
        option.textContent=C.writingModeTitle(x.mode)+(x.options.creative?' · 改写':'')+' · '+(x.createdAt?new Date(x.createdAt).toLocaleString('zh-CN'):'旧版结果')+' · #'+(i+1);picker.appendChild(option);}
      picker.dataset.signature=signature;
    }
    picker.hidden=docs.length<2;if(d)picker.value=d.id;
    for(const id of ['vkn-view-report','vkn-read-full','vkn-md','vkn-html','vkn-txt','vkn-copy','vkn-open-report'])$(id).disabled=!d;
    const preview=$('vkn-preview'),signature2=C.documentSignature(s||{},d);
    if(preview.dataset.signature!==signature2){
      preview.innerHTML=d?C.markdownToSafeHtml(d.markdown.slice(0,26000)):'<p class="empty">你的整理结果会显示在这里。</p>';
      preview.dataset.signature=signature2;
    }
    $('vkn-result-details').hidden=!d;
    const audit=$('vkn-result-audit');if(audit.dataset.signature!==signature2){audit.innerHTML=d?C.markdownToSafeHtml(C.resultAuditMarkdown(d)):'';audit.dataset.signature=signature2;}
    $('vkn-generated').textContent=d?C.writingModeTitle(d.mode)+(d.options.creative?' · 创作改写':' · 忠实整理'):'尚未生成';
    const fresh=d?Math.max(0,(s?.segments?.length||0)-d.totalAtGeneration):0;
    $('vkn-report-hint').textContent=d?(d.legacy?'已保留旧版结果；范围请参照正文。':`本次使用 ${d.cueCount} 条记录 · ${C.formatTime(d.start)}–${C.formatTime(d.end)}。`)+(fresh?` 新增 ${fresh} 条未纳入本次结果。`:'')+(d.markdown.length>26000?' 预览只显示前26000字符，完整阅读 / 导出可看全部。':''):'听写或导入文字后，选择一种方式生成。';
  }

  async function runAi(auto=false){
    if(state.working||!currentSession())return;
    pauseCaptionWork();
    const captured=state.session,snapshot=C.cuesWithSpeakers(captured),writing=formWriting();
    let plan;try{plan=C.selectWritingCues(snapshot,writing);}catch(e){state.lastError=e.message;render();return;}
    if(C.documentHistory(captured).length>=100){state.lastError='本视频已有100份结果，请先导出备份，再另建视频笔记；旧结果不会被自动覆盖。';render();return;}
    captured.writing=writing;
    const requestId='deep-'+Date.now()+'-'+Math.random().toString(36).slice(2);state.aiRequestId=requestId;
    state.working=true;state.aiMode=writing.mode;state.progress=null;state.taskSaving=false;state.lastError='';render();
    try {
      await refreshSettings();if(state.aiRequestId!==requestId)return;
      if(!state.settings.configured)throw Error(state.settings.error||'AI_CONFIG_STATUS：请在设置页验证模型连接。');
      let res=await call('VKN_AI_GENERATE',{requestId,sessionKey:captured.key,cues:snapshot,writing,meta:{title:captured.title,url:captured.url,captionObservations:captured.captionOptions?.enabled===false?[]:(CP?.cleanObservations(captured.captionObservations)||[])}});
      let slices=0;
      while(res?.continuing){
        if(state.session!==captured||getKey()!==captured.key||state.aiRequestId!==requestId)return;
        if(++slices>4000)throw Error('AI_STEP_LIMIT：处理批次超过安全上限；已保存检查点，请重新点击生成继续。');
        // Retain the last actual model-request stage across worker slices.
        // Return to the browser event loop between short MV3 worker jobs.
        await new Promise(resolve=>setTimeout(resolve,0));
        if(state.aiRequestId!==requestId)return;
        res=await call('VKN_AI_GENERATE',{requestId,sessionKey:captured.key,resumeOnly:true});
      }
      if(state.session!==captured||getKey()!==captured.key||state.aiRequestId!==requestId)return;
      for(const [id,review] of Object.entries(res.captionReviews||{})){
        const raw=state.session.segments.find(c=>c.id===id),old=state.session.captionReviews?.[id];
        if(!raw||review.source!==String(raw.original||raw.text)||old?.status==='dismissed'||state.session.textOverrides?.[id])continue;
        const clean=C.cleanCaptionReview(review);if(clean&&!(old?.status==='applied'&&clean.status==='agrees')){state.session.captionReviews||={};state.session.captionReviews[id]=clean;}
      }
      state.taskSaving=true;renderTaskProgress();
      const doc=C.cleanDocument({id:'doc-'+requestId,sourceKey:captured.key,sourceUrl:captured.url,sourceTitle:captured.title,markdown:res.markdown,options:writing,createdAt:new Date().toISOString(),
        cueCount:res.cueCount??plan.cues.length,totalAtGeneration:snapshot.length,start:res.start??plan.from,end:res.end??plan.to,blocks:res.blocks,model:res.model||state.settings.model,audit:res.audit,phraseReview:res.phraseReview,screening:res.screening,reviewCount:res.reviewCount,manualCount:res.manualCount});
      if(!doc)throw Error('模型没有返回可保存的正文。');
      captured.documents=C.documentHistory(captured);captured.documents.push(doc);C.activateDocument(captured,doc.id);
      state.lastAiAt=Date.now();state.lastAiCount=captured.segments.length;
      const saved=await saveNow();if(state.session!==captured||getKey()!==captured.key||state.aiRequestId!==requestId)return;state.tips=C.WRITING_MODES[writing.mode]+(saved?'已生成并保存，旧结果和原文保留。':'已生成，但自动保存失败，请立即导出备份。');
      state.working=false;state.taskSaving=false;state.progress=null;render();jumpToReport();
    }catch(e){
      if(state.session!==captured||getKey()!==captured.key||state.aiRequestId!==requestId||String(e.message).includes('AI_CANCELLED')){return;}
      state.lastError='生成失败：'+e.message+'。原始记录与旧结果保留。';
    }finally{if(state.aiRequestId===requestId){state.aiRequestId=null;state.working=false;state.taskSaving=false;state.progress=null;}render();}
  }
  function downloadFile(text,mime,name){
    const blob=new Blob(['\uFEFF',text],{type:mime});const link=document.createElement('a');const href=URL.createObjectURL(blob);link.href=href;link.download=name;link.style.display='none';shadow.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(href),60000);
  }
  function exportDoc(type){
    if(!currentSession()||!C.activeDocument(state.session))return;
    const ss=state.session,d=C.activeDocument(ss),data=type==='html'?C.resultHtml(ss):type==='txt'?C.resultText(ss):C.resultMarkdown(ss);
    const name=(ss.title||'视频')+'_'+C.writingModeTitle(d.mode)+(d.options.creative?'_改写':'')+'_'+d.id.slice(-8);
    downloadFile(data,type==='html'?'text/html;charset=utf-8':type==='txt'?'text/plain;charset=utf-8':'text/markdown;charset=utf-8',
      C.makeFilename(name,type).replace('_知识笔记.','.'));
    $('vkn-export-menu').open=false;showStatus('当前整理结果已交给浏览器下载。','ok');
  }
  async function loadFile(file){
    const captured=currentSession();if(!file||!captured)return;
    if(file.size>4_000_000){showStatus('字幕文件超过4MB，请使用较小文件','error');return;}
    const text=await file.text();if(currentSession()!==captured){showStatus('已切换视频，未将字幕导入其他视频。');return;}const cues=C.parseSrtVtt(text);
    if(!cues.length){showStatus('未解析到字幕：请选择标准SRT或VTT文件','error');return;}
    const prev=state.session.segments.length;
    append(cues);showStatus(`成功导入 ${state.session.segments.length-prev} 条字幕（去重后）。`,'ok');
  }
  async function refreshSettings(){
    try {state.settings=await call('VKN_AI_STATUS');}catch(e){state.settings={configured:false,auto:false,error:'AI_CONFIG_STATUS：'+e.message};}
  }
  $('vkn-mode').addEventListener('change',()=>{
    if($('vkn-mode').value==='custom')$('vkn-requirements').open=true;
    if($('vkn-mode').value!=='custom')$('vkn-creative').checked=false;
    rememberWriting();render();
  });
  for(const id of ['vkn-instructions','vkn-creative','vkn-range-start','vkn-range-end'])$(id).addEventListener(id==='vkn-creative'?'change':'input',rememberWriting);
  for(const [id,key] of [['vkn-transcript','live'],['vkn-tools','tools'],['vkn-requirements','requirements']])$(id).addEventListener('toggle',()=>{
    if(state.session){state.session.viewPreferences ||= {};state.session.viewPreferences[key]=$(id).open;scheduleSave();if(id==='vkn-transcript')renderLive();}
    render();
  });
  for(const id of ['vkn-stage-details','vkn-highlights-details'])$(id).addEventListener('toggle',render);
  $('vkn-speakers').addEventListener('toggle',()=>{
    render();if($('vkn-speakers').open)void refreshSpeakerRoles(true);
  });
  $('vkn-video-cache').addEventListener('click',async()=>{
    if(!currentSession())return;
    const cacheSession=state.session,cacheUrl=location.href;
    const allowed=confirm('仅保存你有权下载的公开视频；本次匿名下载，不读取登录信息、不处理受保护视频。\n视频完成后保留72小时，到期自动清理本地缓存；笔记不删除。\n默认最高720p、单个视频不超过4GiB。是否开始？');
    if(!allowed)return;
    const button=$('vkn-video-cache'),hint=$('vkn-cache-hint');button.disabled=true;hint.hidden=false;hint.textContent='正在提交本地下载任务…';
    try{const job=await call('VKN_CACHE_CREATE',{title:cacheSession.title,sourceUrl:cacheUrl,consent:true});
      if(state.session!==cacheSession||getKey()!==cacheSession.key)return;
      hint.textContent=job.state==='ready'?'该视频已有本地缓存。点击“本地缓存”播放；不会延长到期时间。':'已加入本地下载队列；在“本地缓存”中查看进度或取消。不影响听写。';
    }catch(e){if(state.session===cacheSession&&getKey()===cacheSession.key)hint.textContent=e.message;}finally{button.disabled=false;}
  });
  $('vkn-cache-library').addEventListener('click',async()=>{try{await call('VKN_CACHE_OPEN');}catch(e){$('vkn-cache-hint').hidden=false;$('vkn-cache-hint').textContent=e.message;}});
  $('vkn-load-more').addEventListener('click',()=>{state.liveLimit+=50;renderLive();});
  $('vkn-document-picker').addEventListener('change',()=>{if(currentSession()){C.activateDocument(state.session,$('vkn-document-picker').value);scheduleSave();render();}});
  $('vkn-txt').addEventListener('click',()=>exportDoc('txt'));
  $('vkn-export-audit').addEventListener('click',()=>{if(currentSession())downloadFile(JSON.stringify(C.auditExport(state.session),null,2),'application/json;charset=utf-8',C.makeFilename(state.session.title+'_核查','json'));});
  $('vkn-export-notebook').addEventListener('click',()=>{
    if(!currentSession())return;
    let data=C.buildDocumentMarkdown(state.session);
    const docs=C.documentHistory(state.session);if(docs.length>1){data+='\n\n---\n\n## 已保存的全部整理版本\n\n'+docs.map(d=>C.resultMarkdown(state.session,d)).join('\n\n---\n\n');}
    downloadFile(data,'text/markdown;charset=utf-8',C.makeFilename(state.session.title+'_全部笔记','md'));
  });
  $('vkn-retry').addEventListener('click',async()=>{
    try{await call('VKN_ASR_RETRY',{sessionKey:state.key});state.asrNote='已请求重新识别缓存音频；请先确认 Ollama 语音模型能正常识别短音频。';render();}
    catch(e){showStatus(e.message,'error');}
  });
  $('vkn-lora-reset').addEventListener('click',()=>{if(state.loraRunning||state.loraBusy)return;state.loraRule=null;state.loraPlanError='';state.loraNote='已新建空规则，请输入完整条件';render();});
  $('vkn-lora-plan-btn').addEventListener('click',async()=>{
    const prompt=$('vkn-lora-prompt').value.trim();
    if(!prompt){$('vkn-lora-plan').textContent='请先描述你需要的视频画面。';return;}
    if(state.loraBusy)return;
    state.loraBusy=true;state.loraNote='正在保存筛选要求（无需加载模型）…';render();
    $('vkn-lora-plan').textContent='正在保存规则；实际图片筛选将在开始采图后运行…';
    try{
      const ans=await call('VKN_LORA_PLAN',{prompt,previous:state.loraRule});
      if(!ans?.plan?.prompt)throw Error('本地服务未返回有效筛选条件');
      state.loraRule=ans.plan;state.loraPlanError='';
      $('vkn-lora-prompt').value='';
      state.loraNote=ans.explanation||'';
      $('vkn-lora-details').open=true;
      $('vkn-lora-info').textContent='✅ 规则已经更新。还可以输入补充/修改要求；确认后点击“开始采图”。';
    }catch(e){state.loraNote=e.message;state.loraPlanError=e.message;$('vkn-lora-plan').textContent='规则制定失败：'+e.message+'。请在设置页检测服务版本，并确认新版本地服务已重新启动。';}
    finally{state.loraBusy=false;render();}
  });
  $('vkn-lora-start').addEventListener('click',async()=>{
    if(!state.loraRule)return;
    if(!window.confirm('将从此刻起采集当前视频画面并在本机生成LoRA候选素材。请确认你拥有训练使用授权。继续吗？'))return;
    const ticket=++state.loraActionId;state.loraBusy=true;render();
    try{
      const data=await call('VKN_LORA_START',{rule:state.loraRule,title:getTitle()});
      if(ticket!==state.loraActionId)return;
      state.loraRunning=true;state.loraId=data.session_id;state.loraTabId=data.tabId;state.loraNote='采样已开始，开始播放视频即可筛选。';
    }catch(e){if(ticket===state.loraActionId)state.loraNote='启动采样失败：'+e.message;}
    finally{if(ticket===state.loraActionId)state.loraBusy=false;render();}
  });
  $('vkn-lora-stop').addEventListener('click',async()=>{
    ++state.loraActionId;state.loraBusy=true;render();
    try{
      const data=await call('VKN_LORA_STOP');
      state.loraRunning=false;state.loraProcessing=!!data.processing;
      state.loraNote='已停止获取新画面，等待本地模型完成排队检查。';
    }catch(e){state.loraNote='停止失败：'+e.message;}
    finally{state.loraBusy=false;render();}
  });
  $('vkn-lora-export').addEventListener('click',async()=>{
    state.loraBusy=true;render();
    try{
      const ret=await call('VKN_LORA_EXPORT',{sessionId:state.loraId});
      state.loraNote='已请求保存ZIP，内含 '+ret.count+' 张图片、同名TXT标注及时间戳。请在下载对话框选择位置。';
    }catch(e){state.loraNote='导出失败：'+e.message;}
    finally{state.loraBusy=false;render();}
  });
  $('vkn-bubble').addEventListener('click',()=>setOpen(true));
  $('vkn-asr').addEventListener('click',async()=>{
    if(state.asrBusy||state.stopAllBusy)return;
    const stopping=state.asrRunning,ticket=++state.asrActionId;
    state.stopRequested=stopping;if(stopping)state.active=false;
    state.asrBusy=true;state.lastError='';render();
    try{
      const result=await call(stopping?'VKN_ASR_STOP':'VKN_ASR_START');
      if(ticket!==state.asrActionId)return;
      state.asrRunning=!!result.running;state.asrPaused=!!result.paused;state.asrDraining=!!result.draining;
      if(state.asrRunning){state.active=true;state.stopRequested=false;}
      state.asrTabId=result.tabId||state.asrTabId;
      state.asrNote=result.warning||(state.asrRunning?'采集已启动，正在等待本地识别…':'采集已停止；缓存仍会补录/翻译，不再获取新音频。');
    }catch(e){
      if(ticket!==state.asrActionId)return;
      state.lastError='语音操作未完成：'+e.message;
      if(!stopping){state.stopRequested=true;state.active=false;call('VKN_ASR_STOP').catch(()=>{});}
    }finally{if(ticket===state.asrActionId)state.asrBusy=false;render();}
  });
  $('vkn-stop-all').addEventListener('click',async()=>{
    if(state.stopAllBusy)return;
    ++state.asrActionId;++state.loraActionId;
    state.stopAllBusy=true;state.stopRequested=true;state.active=false;state.lastError='';render();
    try{
      const result=await call('VKN_ASR_STOP_ALL');
      state.asrRunning=false;state.asrPaused=false;state.asrDraining=!!result.draining;
      state.loraRunning=false;state.loraProcessing=!!result.loraProcessing;
      state.asrNote=result.warning||'已停止新音频和新画面采集；已有缓存仍会补齐。';
      state.loraNote=state.loraProcessing?'采图已停止，已排队图片仍在处理。':'画面采集已停止。';
    }catch(e){state.lastError='停止未确认：'+e.message;}
    finally{state.asrBusy=false;state.loraBusy=false;state.stopAllBusy=false;render();}
  });
  $('vkn-local-help').addEventListener('click',()=>{
    window.alert('本地语音识别使用方法：\n1. 解压完整安装包或在原目录覆盖升级包。\n2. 安装Python 3.11（64位）。\n3. 双击 START_LOCAL_ASR.bat，首次安装依赖和下载模型时需联网。\n4. 保持命令窗口开启，返回视频页面点开始，选择当前标签并共享声音；也可按 Alt+Shift+V 直接开始。\n5. 详细知识文档可配置本地Ollama，在设置中选择本地模型。');
  });
  $('vkn-close').addEventListener('click',()=>setOpen(false));
  $('vkn-record').addEventListener('click',async()=>{
    if(state.asrBusy)return;
    if(!state.asrRunning){state.active=!state.active;render();return;}
    state.asrBusy=true;state.lastError='';render();
    try{const result=await call(state.asrPaused?'VKN_ASR_RESUME':'VKN_ASR_PAUSE');
      state.asrPaused=!!result.paused;state.asrRunning=!!result.running;state.asrNote=state.asrPaused?'已暂停':'正在识别';
    }catch(e){state.lastError='暂停/继续听写失败：'+e.message;}finally{state.asrBusy=false;render();}
  });
  $('vkn-summary-now').addEventListener('click',()=>runPeriodicSummary(true));
  $('vkn-ai').addEventListener('click',()=>runAi(false));
  $('vkn-ai-cancel').addEventListener('click',async()=>{
    const requestId=state.aiRequestId;if(!requestId)return;
    state.aiRequestId=null;state.working=false;state.taskSaving=false;state.lastError='';state.tips='正在取消本次深度整理；已保存文档不变。';render();
    try{const result=await call('VKN_AI_CANCEL',{requestId});state.tips=result.message;}
    catch(e){state.lastError='取消确认失败：'+e.message+'。不会采用这一轮迟到的输出。';}
    render();
  });
  $('vkn-settings').addEventListener('click',()=>call('VKN_OPEN_OPTIONS').catch(e=>showStatus(e.message,'error')));
  $('vkn-view-report').addEventListener('click',jumpToReport);
  $('vkn-open-report').addEventListener('click',openFullReport);
  $('vkn-read-full').addEventListener('click',openFullReport);
  $('vkn-md').addEventListener('click',()=>exportDoc('md'));
  $('vkn-html').addEventListener('click',()=>exportDoc('html'));
  $('vkn-copy').addEventListener('click',async()=>{
    const ss=currentSession();if(!ss)return;
    const str=C.resultText(ss);
    try {await navigator.clipboard.writeText(str);showStatus('文档已复制到剪贴板','ok');}
    catch {showStatus('复制失败。可使用Markdown下载按钮保存。','error');}
  });
  $('vkn-context-review').addEventListener('change',rememberWriting);
  $('vkn-import').addEventListener('click',()=>$('vkn-file').click());
  $('vkn-file').addEventListener('change',async e=>{try{await loadFile(e.target.files?.[0]);}catch(err){showStatus('文件读取失败：'+err.message,'error');}e.target.value='';});
  $('vkn-clear').addEventListener('click',async()=>{
    if(!state.session||!window.confirm('确定清空本视频已采集的全部文字记录和AI文档吗？此操作不能撤销。'))return;
    if(state.working){showStatus('请先取消生成，再清空数据。','error');return;}
    if(state.asrRunning||state.asrDraining){showStatus('请先停止听写并等待缓存处理结束，再清空记录。','error');return;}
    await call('VKN_CLEAR_SESSION',{key:state.key});
    state.session.captionObservations=[];state.session.captionReviews={};resetCaptionRuntime();
    state.session.documents=[];state.session.activeDocumentId='';state.session.speakerNames={};state.session.speakerEvidence={};state.session.speakerCandidates=[];state.session.speakerRoles={};state.session.speakerRoleCandidates=[];state.session.speakerOverrides={};state.session.textOverrides={};state.session.segments=[];state.session.aiMarkdown='';state.session.aiGeneratedAt='';state.session.aiCueCount=0;state.session.summaries=[];state.session.pendingSummary=[];state.summaryStartedAt=0;state.lastAiCount=0;state.lastError='';
    scheduleSave();render();
  });
  chrome.runtime.onMessage.addListener((msg,sender,reply)=>{
    if(msg?.type==='VKN_WRITING_PROGRESS'&&msg.requestId===state.aiRequestId){
      state.progress=C.writingTaskProgress(state.progress,msg,state.aiMode);
      // Do not re-render all stored cues, speakers and document previews on
      // every status event. Only update the dedicated task panel.
      renderTaskProgress();reply({ok:true});
    }
    if(msg?.type==='VKN_TOGGLE'){setOpen(!state.open);reply({ok:true});}
    if(msg?.type==='VKN_OPEN'){setOpen(true);reply({ok:true});}
    if(msg?.type==='VKN_ASR_CONTEXT'){
      const v=getVideo();
      reply({key:getKey(),title:getTitle(),time:Number(v?.currentTime)||0,
        paused:!!v?.paused,rate:Number(v?.playbackRate)||1});
    }
    if(msg?.type==='VKN_ASR_STATE'){
      if(msg.starting){state.stopRequested=false;state.asrBusy=true;state.lastError='';state.asrNote=msg.message||'等待采集授权';render();reply({ok:true});return;}
      if(msg.startedByUser){state.stopRequested=false;state.asrBusy=false;state.lastError='';}
      if(msg.running&&state.stopRequested){reply({ok:true});return;}
      state.asrRunning=!!msg.running;state.asrPaused=!!msg.paused;
      if(!msg.running){pauseCaptionWork();caption.stream='';state.asrBusy=false;state.active=false;state.stopRequested=true;state.asrDraining=!!msg.draining;state.asrNote=msg.message||'采集已停止';}
      if(msg.error){state.lastError=msg.error;state.asrBusy=false;}
      if(msg.tabId)state.asrTabId=msg.tabId;
      if(state.asrRunning){state.active=true;state.asrNote=msg.message||'本地语音识别正在运行';}
      if(msg.kind!=='segment')render();reply({ok:true});
    }
    if(msg?.type==='VKN_ASR_EVENT'){
      if(!currentSession()||msg.sessionKey!==state.session.key){reply({ok:false,ignored:true});return;}
      const data=msg.data||{};
      if(!state.stopRequested&&['caption_clock','started','asr_pause_state'].includes(msg.kind))captionClock(data);
      if(msg.tabId)state.asrTabId=msg.tabId;
      if(msg.kind==='lora_status'){
        state.loraStatus=data.status||state.loraStatus;
        if(data.running===false)state.loraRunning=false;
        if(typeof data.processing==='boolean')state.loraProcessing=data.processing;
        if(data.message)state.loraNote=data.message;
        if(data.limit)state.loraNote='达到最大样本数量，请点击停止后导出';
      }else if(msg.kind==='lora_frame'){
        state.loraStatus=data.status||state.loraStatus;
        state.loraNote='最新采集：'+(data.entry?.caption||'');
      }else if(msg.kind==='lora_error'){
        state.loraStatus=data.status||state.loraStatus;
        state.loraNote=data.message||'视觉模型发生异常';
      }else if(msg.kind==='lora_stopped'){
        state.loraRunning=false;state.loraProcessing=false;
        state.loraStatus=data.status||state.loraStatus;
        state.loraNote='本轮采样已经处理完毕，可以导出ZIP。';
      }else if(msg.kind==='started'){
        if(state.stopRequested){reply({ok:true});return;}
        state.asrRunning=true;state.asrPaused=false;state.asrNote=data.message||'正在识别';state.source='local-asr';
      }else if(msg.kind==='asr_pause_state'){
        if(state.stopRequested){reply({ok:true});return;}
        state.asrPaused=!!data.paused;state.asrRunning=true;state.asrNote=data.message||'';
      }else if(msg.kind==='stopped'){
        pauseCaptionWork();caption.stream='';
        state.active=false;state.stopRequested=true;state.asrDraining=!!data.draining;state.asrRunning=false;state.asrPaused=false;state.asrNote=data.message||'听写结束';
      }else if(msg.kind==='progress'){
        state.asrNote=(state.asrRunning?'':'采集已停止，正在补录缓存：')+`缓存待识别 ${Number(data.pendingSeconds)||0} 秒 · 未确认音频 ${Number(data.unacknowledged)||0} 包 · 翻译/纠错 ${Number(data.textPending)||0} 条`;
        if(data.error)state.asrNote+=' · '+data.error;
      }else if(msg.kind==='pressure'){
        getVideo()?.pause();state.asrNote=data.message||'缓存积压，已请求暂停视频';state.lastError=state.asrNote;
      }else if(msg.kind==='status'||msg.kind==='drained'){
        if(msg.kind==='drained')state.asrDraining=false;
        state.asrNote=data.message||'';
      }else if(msg.kind==='warning'){
        state.asrNote=data.message||'本地识别提示';
      }else if(msg.kind==='segment'){
        const t=Number(data.time),content=String(data.text||'').trim();
        if(Number.isFinite(t) && t>=0 && content && content.length<=6000){
          state.source='local-asr';append([{...data,time:t,text:content,source:'local-asr'}]);
        }
      }
      render();reply({ok:true});
    }
  });
  chrome.storage.onChanged.addListener((changes,area)=>{
    if(area==='local'&&changes.vknAiConfig)refreshSettings();
  });

  // Subtitle evidence is supplemental to immutable ASR. No subtitle-only recording.
  const CP=globalThis.VknCaptions;
  const caption={generation:0,stream:'',epoch:0,active:new Map(),checks:new Map(),busy:false,lastClock:0,lastNative:0,nextFrame:0,nextCheck:0,message:'等待开始听写。',serial:0};
  function pauseCaptionWork(){caption.generation++;caption.active.clear();call('VKN_CAPTION_CANCEL').catch(()=>{});}
  function resetCaptionRuntime(){pauseCaptionWork();caption.stream='';caption.epoch=0;caption.checks.clear();caption.lastClock=0;caption.lastNative=0;caption.nextFrame=0;caption.nextCheck=0;caption.message='等待开始听写。';}
  function captionClock(data){
    if(!data?.streamSessionId||!/^[a-f0-9]{32}$/.test(data.streamSessionId))return;
    const epoch=Number(data.contextEpoch)||0;
    if(data.streamSessionId!==caption.stream||epoch!==caption.epoch){caption.active.clear();caption.generation++;}
    caption.stream=data.streamSessionId;caption.epoch=epoch;
  }
  function applyCaptionControls(){
    const o=state.session?.captionOptions||{};$('vkn-caption-enabled').checked=o.enabled!==false;$('vkn-caption-frames').checked=o.frames!==false;
  }
  function renderCaptionStatus(){
    const ss=state.session;if(!ss)return;
    const reviews=Object.values(ss.captionReviews||{}),n=reviews.filter(x=>x.status==='applied').length;
    const evidence=(ss.captionObservations||[]).length,candidates=reviews.filter(x=>x.status==='candidate').length;
    $('vkn-caption-count').textContent='已读 '+evidence+' 条 · 修订 '+n+' 条'+(candidates?' · 候选 '+candidates+' 条':'');
    $('vkn-caption-status').textContent=ss.captionOptions?.enabled===false?'字幕辅助校对已关闭，继续保留听写。':caption.message;
  }
  function rememberCaptionOptions(){
    if(!state.session)return;
    state.session.captionOptions={enabled:$('vkn-caption-enabled').checked,frames:$('vkn-caption-frames').checked};
    pauseCaptionWork();caption.nextFrame=0;call('VKN_CAPTION_CLOCK',{key:state.key,sampleFrames:state.session.captionOptions.enabled&&state.session.captionOptions.frames}).catch(()=>{});caption.message='设置已保存；只核对本轮录制中采到的字幕。';scheduleSave();renderCaptionStatus();
  }
  function storeCaptionEvidence(rows){
    const ss=state.session;if(!ss||!CP||!rows.length)return;
    const previous=(ss.captionObservations||[]).length;
    ss.captionObservations=CP.mergeObservations(ss.captionObservations,rows);
    if(previous>=6000)caption.message='字幕证据达到6000条上限，保留近期证据；原始听写和已采用修订不删。';
    scheduleSave();
  }
  async function checkCaptionMatches(){
    const ss=state.session;if(!ss||!CP||caption.busy||state.working||Date.now()<caption.nextCheck||ss.captionOptions?.enabled===false)return;
    const ready=[];
    // The ASR can lag behind playback; use timestamped evidence rather than current subtitle.
    for(const c of C.cuesWithSpeakers(ss).slice(-600)){
      if(c.manuallyEdited||ss.captionReviews?.[c.id]?.status==='dismissed')continue;
      const evidence=CP.evidenceFor(c,ss.captionObservations);if(!evidence.length)continue;
      const fingerprint=CP.fingerprint(c,evidence);if(caption.checks.get(c.id)===fingerprint)continue;
      ready.push({cue:{...c,text:c.original||c.text},evidence,fingerprint});if(ready.length>=12)break;
    }
    if(!ready.length)return;
    const generation=caption.generation;caption.busy=true;caption.nextCheck=Date.now()+1800;
    try{
      const data=await call('VKN_CAPTION_VALIDATE',{data:{items:ready.map(({cue,evidence})=>({cue,evidence}))}});
      if(generation!==caption.generation||state.session!==ss||data?.busy)return;
      ss.captionReviews ||= {};
      for(const r of data.reviews||[]){const c=ready.find(x=>x.cue.id===r.id);if(!c||r.source!==String(c.cue.original||c.cue.text))continue;
        const original=ss.segments.find(x=>x.id===r.id);if(!original||(original.original||original.text)!==r.source)continue;
        const old=ss.captionReviews[r.id];
        // Preserve an accepted edit unless a later check explicitly reports conflict.
        if(old?.status==='applied'&&r.status==='agrees')continue;
        const cleaned=C.cleanCaptionReview({...r,checkedAt:new Date().toISOString()});if(cleaned)ss.captionReviews[r.id]=cleaned;
      }
      ready.forEach(x=>caption.checks.set(x.cue.id,x.fingerprint));
      caption.message=data.phonetic_available?'已对齐同时间字幕；中文同音与英文拼写分别校验，原文保留。':'字幕已取得，英文拼写可独立核对；中文拼音组件未就绪，中文候选未自动采用。';
      invalidateLive();scheduleSave();render();
    }catch(e){if(generation===caption.generation){caption.message='字幕核对暂缓：'+e.message+'。听写不受影响。';caption.nextFrame=Date.now()+30000;caption.nextCheck=Date.now()+30000;}}
    finally{caption.busy=false;renderCaptionStatus();}
  }
  async function captionTick(){
    const ss=state.session,v=getVideo();
    if(!ss||!CP||ss.captionOptions?.enabled===false||!state.asrRunning||state.asrPaused||state.stopRequested||!v||v.paused||v.seeking)return;
    if(Date.now()-caption.lastClock>2500){caption.lastClock=Date.now();const gen=caption.generation;
      call('VKN_CAPTION_CLOCK',{key:state.key,sampleFrames:ss.captionOptions?.frames!==false&&Date.now()-caption.lastNative>=2500}).then(r=>{if(gen===caption.generation&&state.session===ss&&state.asrRunning&&!state.stopRequested&&!v.seeking)captionClock(r);}).catch(()=>{});
    }
    if(!caption.stream)return;
    const now=Number(v.currentTime),rows=CP.readVisible(v),keys=new Set();
    for(const r of rows){
      const k=caption.stream+'|'+caption.epoch+'|'+r.source+'|'+r.text+'|'+(r.source==='track'?r.start:'');keys.add(k);
      let old=caption.active.get(k);
      if(!old){old={...r,id:'caption-'+Date.now()+'-'+(++caption.serial),stream:caption.stream,epoch:caption.epoch,samples:0,seenSpan:0,firstSeen:now};caption.active.set(k,old);}
      old.samples++;old.seenSpan=Math.max(0,now-old.firstSeen);
      if(r.source!=='track')old.end=now;
      if(old.end-old.start<=30)storeCaptionEvidence([old]);
      caption.lastNative=Date.now();caption.message='已读取当前字幕，等待对应听写后对齐校正。';
    }
    for(const k of caption.active.keys())if(!keys.has(k))caption.active.delete(k);
    if(!caption.busy)await checkCaptionMatches();
    if(state.session!==ss||caption.busy||state.working||state.summaryBusy||state.loraRunning||ss.captionOptions?.frames===false||Date.now()<caption.nextFrame||Date.now()-caption.lastNative<2500)return;
    const generation=caption.generation;caption.busy=true;caption.nextFrame=Date.now()+2500;
    try{
      const result=await call('VKN_CAPTION_FRAME',{key:state.key});
      if(generation!==caption.generation||state.session!==ss||!state.asrRunning||state.stopRequested||state.asrPaused)return;
      if(result.busy){caption.message='视觉模型有其他任务，暂用语音听写。';caption.nextFrame=Date.now()+5000;return;}
      storeCaptionEvidence(result.observations||[]);
      caption.message=result.observations?.length?'已采样画面字幕，待对应听写对齐；图片未保存。':'本次画面未读到清晰字幕，继续语音听写。';
      if(result.sampling?.dropped)caption.message+=' 画面队列落后，累计跳过 '+result.sampling.dropped+' 组采样；没有字幕覆盖的内容未校正。';
      if(result.sampling?.queued)caption.message+=' 待核对 '+result.sampling.queued+' 组。';
      caption.nextFrame=Date.now()+(result.sampling?.queued?500:result.observations?.length?2000:4000);
    }catch(e){if(generation===caption.generation){caption.message='画面核对暂缓：'+e.message+'。听写继续。';caption.nextFrame=Date.now()+45000;}}
    finally{caption.busy=false;renderCaptionStatus();}
  }
  for(const id of ['vkn-caption-enabled','vkn-caption-frames'])$(id).addEventListener('change',rememberCaptionOptions);

  // SPA navigation events supplement polling; action guards cover the interval before events.
  function routeChanged(){if(getKey()!==state.key)void switchVideo(getKey());}
  document.addEventListener('yt-navigate-finish',()=>{state.navigationPending=false;routeChanged();render();});
  window.addEventListener('popstate',routeChanged);
  async function init(){
    await refreshSettings();
    host.style.display='none';
    await switchVideo(getKey());
    try{const asr=await call('VKN_ASR_STATUS_QUERY');
      const key=getKey();
      if(asr.running && key && asr.sessionKey===key){captionClock(asr);state.asrRunning=true;state.asrPaused=!!asr.paused;state.asrTabId=asr.tabId;state.source='local-asr';}
      const lora=await call('VKN_LORA_STATUS');
      if(lora.session_id && lora.key===key){state.loraRunning=!!lora.running;state.loraProcessing=!!lora.processing;state.loraId=lora.session_id;state.loraTabId=lora.tabId;}
    }catch(_){}
    setInterval(onTick,1000);
    setInterval(()=>captionTick().catch(()=>{}),500);
    window.addEventListener('pagehide',()=>{if(state.session)saveNow();});
  }
  init().catch(e=>showStatus('初始化失败：'+e.message,'error'));
})();
