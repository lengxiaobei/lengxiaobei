"""Dashboard HTML for the local Gateway console."""

DASHBOARD_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>冷小北 Gateway</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f2ed;
      --surface: #ffffff;
      --surface-2: #f8f7f4;
      --surface-3: #efede7;
      --text: #1f2428;
      --muted: #697077;
      --line: #dedbd2;
      --ink: #111827;
      --accent: #256f68;
      --accent-2: #8b3f5c;
      --warn: #ad6a00;
      --bad: #b42318;
      --ok: #16825d;
      --info: #315e9e;
      --shadow: 0 10px 28px rgba(20, 20, 20, .08);
      --radius: 8px;
    }
    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      letter-spacing: 0;
    }
    button, input, textarea, select { font: inherit; letter-spacing: 0; }
    button {
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--surface);
      color: var(--text);
      padding: 7px 10px;
      font-weight: 650;
      cursor: pointer;
    }
    button:hover { border-color: #b8b2a5; background: #fbfaf7; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
    button.primary:hover { background: #1e5c56; }
    button.danger { background: #fff5f3; border-color: #f2b8ad; color: var(--bad); }
    button.icon { width: 34px; padding: 0; display: inline-grid; place-items: center; }
    input, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--surface);
      color: var(--text);
      padding: 8px 10px;
      outline: none;
    }
    textarea { min-height: 116px; resize: vertical; }
    input:focus, textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(37, 111, 104, .14); }
    .shell { display: grid; grid-template-columns: 232px minmax(0, 1fr) 344px; min-height: 100vh; }
    .rail {
      border-right: 1px solid var(--line);
      background: #ece8df;
      padding: 14px;
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
    }
    .brand { display: flex; align-items: center; gap: 10px; padding: 4px 4px 14px; }
    .mark {
      width: 32px; height: 32px; border-radius: 7px;
      background:
        linear-gradient(135deg, rgba(37,111,104,.92), rgba(139,63,92,.9)),
        var(--accent);
      box-shadow: var(--shadow);
    }
    .brand strong { display: block; font-size: 15px; }
    .brand span { display: block; color: var(--muted); font-size: 12px; margin-top: 1px; }
    .nav { display: grid; gap: 4px; margin: 10px 0 18px; }
    .nav button {
      width: 100%;
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: transparent;
      border-color: transparent;
      text-align: left;
      color: #40464d;
    }
    .nav button.active { background: var(--surface); border-color: var(--line); color: var(--ink); box-shadow: 0 1px 0 rgba(0,0,0,.03); }
    .nav small { color: var(--muted); font-size: 11px; }
    .rail-block {
      border: 1px solid var(--line);
      background: rgba(255,255,255,.45);
      border-radius: var(--radius);
      padding: 10px;
      margin-top: 10px;
    }
    .rail-title { font-size: 11px; font-weight: 800; color: var(--muted); text-transform: uppercase; margin-bottom: 8px; }
    .kv { display: grid; gap: 7px; }
    .kv div { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; }
    .kv span { color: var(--muted); }
    .kv b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .main { padding: 16px; min-width: 0; }
    .topbar {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
      margin-bottom: 12px;
    }
    h1 { margin: 0; font-size: 22px; line-height: 1.2; }
    .subtitle { margin-top: 4px; color: var(--muted); }
    .toolbar { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
    .section { display: none; }
    .section.active { display: block; }
    .status-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
    .tile, .panel {
      border: 1px solid var(--line);
      background: var(--surface);
      border-radius: var(--radius);
      box-shadow: 0 1px 0 rgba(0,0,0,.03);
    }
    .tile { padding: 12px; min-height: 92px; }
    .tile-label { color: var(--muted); font-size: 12px; font-weight: 750; }
    .tile-value { margin-top: 8px; font-size: 23px; font-weight: 850; line-height: 1.1; }
    .tile-foot { margin-top: 6px; color: var(--muted); font-size: 12px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
    .layout { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(300px, .65fr); gap: 12px; align-items: start; }
    .panel { padding: 12px; margin-bottom: 12px; }
    .panel-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 10px; }
    .panel h2 { margin: 0; font-size: 15px; }
    .panel-sub { color: var(--muted); font-size: 12px; margin-top: 2px; }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; }
    .split { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .stack { display: grid; gap: 10px; }
    .list { display: grid; gap: 8px; }
    .row {
      border: 1px solid var(--line);
      background: var(--surface-2);
      border-radius: 7px;
      padding: 10px;
      min-width: 0;
    }
    .row-title { font-weight: 750; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .row-meta { color: var(--muted); font-size: 12px; margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .pill {
      display: inline-flex; align-items: center; gap: 6px;
      min-height: 24px;
      border-radius: 999px;
      border: 1px solid var(--line);
      padding: 3px 8px;
      background: var(--surface-2);
      color: var(--muted);
      font-size: 12px;
      font-weight: 750;
      white-space: nowrap;
    }
    .dot { width: 8px; height: 8px; border-radius: 999px; background: var(--warn); }
    .dot.ok { background: var(--ok); }
    .dot.bad { background: var(--bad); }
    .dot.info { background: var(--info); }
    .right {
      border-left: 1px solid var(--line);
      background: #f7f5ef;
      padding: 14px;
      height: 100vh;
      position: sticky;
      top: 0;
      overflow: auto;
    }
    pre, .console {
      margin: 0;
      max-height: 360px;
      overflow: auto;
      border-radius: 7px;
      border: 1px solid #292f36;
      background: #151a1f;
      color: #d5e3df;
      padding: 10px;
      font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .console.small { max-height: 220px; }
    .empty {
      border: 1px dashed var(--line);
      border-radius: 7px;
      background: var(--surface-2);
      color: var(--muted);
      padding: 18px;
      text-align: center;
      font-size: 13px;
    }
    .chat-log {
      height: 430px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--surface-2);
      padding: 10px;
      display: grid;
      align-content: start;
      gap: 8px;
    }
    .msg { max-width: 86%; border: 1px solid var(--line); border-radius: 8px; padding: 9px 10px; background: var(--surface); }
    .msg.user { justify-self: end; background: #e8f1ef; border-color: #bfd8d3; }
    .msg.assistant { justify-self: start; }
    .msg-role { font-size: 11px; font-weight: 800; color: var(--muted); margin-bottom: 4px; }
    .toast {
      position: fixed; right: 18px; bottom: 18px; z-index: 10;
      max-width: min(480px, calc(100vw - 32px));
      border: 1px solid #1f2937;
      border-radius: 8px;
      background: #151a1f;
      color: #fff;
      padding: 10px 12px;
      box-shadow: var(--shadow);
      transform: translateY(18px);
      opacity: 0;
      pointer-events: none;
      transition: .16s ease;
    }
    .toast.show { transform: translateY(0); opacity: 1; }
    @media (max-width: 1240px) {
      .shell { grid-template-columns: 220px minmax(0, 1fr); }
      .right { position: static; height: auto; grid-column: 1 / -1; border-left: 0; border-top: 1px solid var(--line); }
    }
    @media (max-width: 860px) {
      .shell { grid-template-columns: 1fr; }
      .rail { position: static; height: auto; }
      .main { padding: 12px; }
      .nav { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .status-grid, .layout, .split { grid-template-columns: 1fr; }
      .topbar { display: block; }
      .toolbar { justify-content: flex-start; margin-top: 10px; }
      .tile-value { font-size: 21px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="rail">
      <div class="brand">
        <div class="mark" aria-hidden="true"></div>
        <div><strong>冷小北</strong><span>Local Gateway</span></div>
      </div>
      <nav class="nav" aria-label="主导航">
        <button class="active" data-tab="overview">总览 <small>01</small></button>
        <button data-tab="chat">对话 <small>02</small></button>
        <button data-tab="autonomy">自治 <small>03</small></button>
        <button data-tab="learning">进化 <small>04</small></button>
        <button data-tab="memory">记忆 <small>05</small></button>
        <button data-tab="system">系统 <small>06</small></button>
      </nav>
      <div class="rail-block">
        <div class="rail-title">Gateway</div>
        <div class="kv">
          <div><span>HTTP</span><b id="railHttp">--</b></div>
          <div><span>Events</span><b id="railEvents">connecting</b></div>
          <div><span>PID</span><b id="railPid">--</b></div>
        </div>
      </div>
      <div class="rail-block">
        <div class="rail-title">Runtime</div>
        <div class="kv">
          <div><span>Python</span><b id="railPython">--</b></div>
          <div><span>Uptime</span><b id="railUptime">--</b></div>
          <div><span>Restart</span><b id="railRestart">idle</b></div>
        </div>
      </div>
    </aside>

    <main class="main">
      <div class="topbar">
        <div>
          <h1 id="pageTitle">Gateway 控制台</h1>
          <div class="subtitle" id="pageDesc">运行状态、自治循环、学习进化和记忆检索。</div>
        </div>
        <div class="toolbar">
          <button class="icon" id="refreshBtn" title="刷新">↻</button>
          <button id="healthBtn">健康检查</button>
          <button class="primary" data-action="tickAutonomy">手动 Tick</button>
        </div>
      </div>

      <section class="section active" id="overview">
        <div class="status-grid">
          <div class="tile"><div class="tile-label">Web</div><div class="tile-value" id="webState">--</div><div class="tile-foot" id="webFoot">等待刷新</div></div>
          <div class="tile"><div class="tile-label">自治</div><div class="tile-value" id="autonomyState">--</div><div class="tile-foot" id="tickText">未读取</div></div>
          <div class="tile"><div class="tile-label">Lessons</div><div class="tile-value" id="lessonCount">--</div><div class="tile-foot">经验沉淀</div></div>
          <div class="tile"><div class="tile-label">Runs</div><div class="tile-value" id="runCount">--</div><div class="tile-foot">进化记录</div></div>
        </div>
        <div class="layout">
          <div>
            <div class="panel">
              <div class="panel-head">
                <div><h2>Gateway Actions</h2><div class="panel-sub">常用运行操作</div></div>
                <span class="pill"><span class="dot" id="liveDot"></span><span id="liveText">连接中</span></span>
              </div>
              <div class="actions">
                <button class="primary" data-action="startAutonomy">启动自治</button>
                <button data-action="stopAutonomy">停止自治</button>
                <button data-action="loadPlan">学习计划</button>
                <button data-action="loadEvents">事件</button>
                <button data-action="loadModelConfig">模型</button>
              </div>
            </div>
            <div class="panel">
              <div class="panel-head"><div><h2>Recent Lessons</h2><div class="panel-sub">最新经验</div></div><button class="icon" data-action="loadLessons" title="刷新经验">↻</button></div>
              <div class="list" id="lessonsList"><div class="empty">暂无数据</div></div>
            </div>
          </div>
          <div class="panel">
            <div class="panel-head"><div><h2>Run Log</h2><div class="panel-sub">当前操作输出</div></div><button class="icon" data-action="clearOutput" title="清空">×</button></div>
            <pre id="output">等待操作...</pre>
          </div>
        </div>
      </section>

      <section class="section" id="chat">
        <div class="panel">
          <div class="panel-head"><div><h2>Chat Session</h2><div class="panel-sub">/api/chat</div></div><button class="icon" data-action="clearChat" title="清空对话">×</button></div>
          <div class="chat-log" id="chatLog"></div>
          <div class="stack" style="margin-top:10px">
            <textarea id="chatInput" placeholder="输入消息..."></textarea>
            <div class="actions"><button class="primary" data-action="sendChat">发送</button><button data-action="loadAgentContext">上下文</button></div>
          </div>
        </div>
      </section>

      <section class="section" id="autonomy">
        <div class="layout">
          <div class="panel">
            <div class="panel-head"><div><h2>Autonomy Control</h2><div class="panel-sub">循环参数</div></div></div>
            <div class="split">
              <input id="intervalInput" type="number" min="60" value="300" aria-label="循环间隔秒" />
              <input id="reasonInput" value="manual" aria-label="触发原因" />
            </div>
            <div style="height:10px"></div>
            <textarea id="directionInput">继续自主优化，优先修复真实使用问题</textarea>
            <div class="actions">
              <button class="primary" data-action="startAutonomy">启动</button>
              <button data-action="tickAutonomy">执行一次</button>
              <button class="danger" data-action="stopAutonomy">停止</button>
              <button data-action="loadAutonomyRuns">运行记录</button>
            </div>
          </div>
          <div class="panel"><div class="panel-head"><div><h2>Autonomy State</h2><div class="panel-sub">实时状态</div></div></div><pre id="autonomyOutput">未加载</pre></div>
        </div>
      </section>

      <section class="section" id="learning">
        <div class="layout">
          <div class="panel">
            <div class="panel-head"><div><h2>Self Evolution</h2><div class="panel-sub">小步进化</div></div></div>
            <textarea id="evolveTopic">参考 OpenClaw Gateway 控制台设计，改进冷小北前端的信息密度、连接反馈和操作闭环</textarea>
            <div class="actions"><button class="primary" data-action="selfEvolve">开始进化</button><button data-action="loadKanban">Kanban</button><button data-action="loadCapabilityCheck">能力检查</button></div>
          </div>
          <div class="panel">
            <div class="panel-head"><div><h2>Runs</h2><div class="panel-sub">最近进化</div></div><button class="icon" data-action="loadRuns" title="刷新运行">↻</button></div>
            <div class="list" id="runsList"><div class="empty">暂无数据</div></div>
          </div>
        </div>
      </section>

      <section class="section" id="memory">
        <div class="layout">
          <div class="panel">
            <div class="panel-head"><div><h2>Memory Search</h2><div class="panel-sub">长期记忆</div></div></div>
            <div class="split"><input id="memoryQuery" value="前端设计不合理 连接中" /><input id="memoryLimit" type="number" min="1" max="20" value="5" /></div>
            <div class="actions"><button class="primary" data-action="searchMemory">搜索</button><button data-action="loadMemoryIndex">索引</button><button data-action="runCurator">策展</button></div>
          </div>
          <div class="panel"><div class="panel-head"><div><h2>Memory Output</h2><div class="panel-sub">检索结果</div></div></div><pre id="memoryOutput">未搜索</pre></div>
        </div>
      </section>

      <section class="section" id="system">
        <div class="layout">
          <div class="panel">
            <div class="panel-head"><div><h2>System API</h2><div class="panel-sub">运行诊断</div></div></div>
            <div class="actions">
              <button data-action="loadRuntime">Runtime</button>
              <button data-action="loadStatus">Status</button>
              <button data-action="loadHealth">Health</button>
              <button data-action="loadModelConfig">Models</button>
              <button data-action="loadGoals">Goals</button>
              <button data-action="loadMotivations">Motivations</button>
              <button class="danger" data-action="restartRuntime">重启 Web</button>
            </div>
          </div>
          <div class="panel"><div class="panel-head"><div><h2>System Output</h2><div class="panel-sub">接口响应</div></div></div><pre id="systemOutput">未加载</pre></div>
        </div>
      </section>
    </main>

    <aside class="right">
      <div class="panel">
        <div class="panel-head"><div><h2>Live Channel</h2><div class="panel-sub">SSE /api/events</div></div><span class="pill"><span class="dot" id="eventDot"></span><span id="eventState">连接中</span></span></div>
        <div class="console small" id="eventLog">等待事件...</div>
      </div>
      <div class="panel">
        <div class="panel-head"><div><h2>Queue</h2><div class="panel-sub">最近操作</div></div></div>
        <div class="list" id="actionLog"><div class="empty">暂无操作</div></div>
      </div>
      <div class="panel">
        <div class="panel-head"><div><h2>Model</h2><div class="panel-sub">配置摘要</div></div><button class="icon" data-action="loadModelConfig" title="刷新模型">↻</button></div>
        <div class="console small" id="modelSummary">未加载</div>
      </div>
    </aside>
  </div>
  <div class="toast" id="toast"></div>

<script>
const $ = (id) => document.getElementById(id);
let busy = false;
let actionHistory = [];

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}
function formatTime(ts) {
  if (!ts) return '未知时间';
  const n = Number(ts);
  return new Date((n < 10000000000 ? n * 1000 : n)).toLocaleString();
}
function compact(value, max = 2600) {
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  return text.length > max ? `${text.slice(0, max)}\n...` : text;
}
function setOutput(target, data) {
  const el = typeof target === 'string' ? $(target) : target;
  el.textContent = compact(data);
}
function toast(message) {
  const el = $('toast');
  el.textContent = message;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2400);
}
function logAction(label, status) {
  actionHistory.unshift({ label, status, ts: Date.now() });
  actionHistory = actionHistory.slice(0, 6);
  $('actionLog').innerHTML = actionHistory.map(item => `<div class="row"><div class="row-title">${escapeHtml(item.label)}</div><div class="row-meta">${escapeHtml(item.status)} · ${formatTime(item.ts)}</div></div>`).join('');
}
async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options
  });
  let data;
  try { data = await res.json(); } catch (_) { data = { text: await res.text() }; }
  if (!res.ok) throw new Error(data.error || data.message || `${res.status} ${res.statusText}`);
  return data;
}
async function run(button, label, fn) {
  if (busy) return;
  busy = true;
  const old = button ? button.textContent : '';
  if (button) { button.disabled = true; button.textContent = '执行中'; }
  logAction(label, 'running');
  try {
    const data = await fn();
    logAction(label, 'ok');
    toast(`${label} 完成`);
    return data;
  } catch (err) {
    logAction(label, `failed: ${err.message}`);
    toast(`${label} 失败`);
    setOutput('output', { status: 'failed', error: err.message });
  } finally {
    if (button) { button.disabled = false; button.textContent = old; }
    busy = false;
  }
}
function renderList(el, items, mapper) {
  if (!items || !items.length) {
    el.innerHTML = '<div class="empty">暂无数据</div>';
    return;
  }
  el.innerHTML = items.map(mapper).join('');
}
function row(title, meta) {
  return `<div class="row"><div class="row-title">${escapeHtml(title)}</div><div class="row-meta">${escapeHtml(meta)}</div></div>`;
}
async function refreshAll() {
  const [runtime, status, autonomy, lessons, runs] = await Promise.allSettled([
    api('/api/runtime/status'),
    api('/api/status'),
    api('/api/autonomy/status'),
    api('/api/lessons?limit=6'),
    api('/api/runs?limit=6')
  ]);
  if (runtime.status === 'fulfilled') {
    const r = runtime.value;
    $('railPid').textContent = r.pid || '--';
    $('railPython').textContent = String(r.python || '').split('/').pop() || '--';
    $('railUptime').textContent = `${r.uptime || 0}s`;
    $('railRestart').textContent = r.restart?.pending ? 'pending' : 'idle';
    $('railHttp').textContent = location.host || 'local';
  }
  if (status.status === 'fulfilled') {
    $('webState').textContent = 'online';
    $('webFoot').textContent = `uptime ${status.value.uptime || 0}s`;
    $('liveDot').className = 'dot ok';
    $('liveText').textContent = '已连接';
  } else {
    $('webState').textContent = 'offline';
    $('liveDot').className = 'dot bad';
    $('liveText').textContent = '失败';
  }
  if (autonomy.status === 'fulfilled') {
    const a = autonomy.value.autonomy || autonomy.value;
    $('autonomyState').textContent = a.enabled ? 'running' : 'stopped';
    $('tickText').textContent = `tick ${a.tick_count || 0}`;
    setOutput('autonomyOutput', autonomy.value);
  }
  if (lessons.status === 'fulfilled') {
    $('lessonCount').textContent = lessons.value.count ?? (lessons.value.lessons || []).length;
    renderList($('lessonsList'), lessons.value.lessons || [], item => row(item.capability || item.topic || item.id || '未命名 lesson', `${item.status || 'unknown'} · ${formatTime(item.created_at)}`));
  }
  if (runs.status === 'fulfilled') {
    $('runCount').textContent = runs.value.count ?? (runs.value.runs || []).length;
    renderList($('runsList'), runs.value.runs || [], item => row(item.goal || item.topic || item.id || '未命名 run', `${item.status || 'unknown'} · ${formatTime(item.created_at)}`));
  }
}
function appendChat(role, content) {
  const log = $('chatLog');
  const el = document.createElement('div');
  el.className = `msg ${role}`;
  el.innerHTML = `<div class="msg-role">${role}</div><div>${escapeHtml(content)}</div>`;
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
}
const actions = {
  clearOutput: async () => { setOutput('output', ''); },
  clearChat: async () => { $('chatLog').innerHTML = ''; },
  loadRuntime: async () => setOutput('systemOutput', await api('/api/runtime/status')),
  loadStatus: async () => setOutput('systemOutput', await api('/api/status')),
  loadHealth: async () => setOutput('systemOutput', await api('/api/health')),
  loadGoals: async () => setOutput('systemOutput', await api('/api/goals')),
  loadMotivations: async () => setOutput('systemOutput', await api('/api/motivations')),
  loadAgentContext: async () => setOutput('output', await api('/api/agent-context')),
  loadModelConfig: async () => {
    const data = await api('/api/model-config');
    setOutput('systemOutput', data);
    setOutput('modelSummary', {
      default: data.config?.configured_default || data.configured_default,
      enabled: data.config?.enabled || data.enabled,
      providers: data.config?.providers || data.providers
    });
  },
  loadEvents: async () => setOutput('output', await api('/api/execution/events?limit=30')),
  loadLessons: async () => { setOutput('output', await api('/api/lessons?limit=20')); await refreshAll(); },
  loadRuns: async () => { setOutput('output', await api('/api/runs?limit=20')); await refreshAll(); },
  loadKanban: async () => setOutput('output', await api('/api/learning/kanban')),
  loadCapabilityCheck: async () => setOutput('output', await api('/api/learning/capability-check')),
  loadPlan: async () => setOutput('output', await api('/api/autonomy/learning-plan')),
  loadAutonomyRuns: async () => setOutput('autonomyOutput', await api('/api/autonomy/runs')),
  startAutonomy: async () => {
    const data = await api('/api/autonomy/start', { method: 'POST', body: JSON.stringify({ interval_seconds: Number($('intervalInput')?.value || 300) }) });
    setOutput('output', data); await refreshAll();
  },
  stopAutonomy: async () => {
    const data = await api('/api/autonomy/stop', { method: 'POST', body: '{}' });
    setOutput('output', data); await refreshAll();
  },
  tickAutonomy: async () => {
    const data = await api('/api/autonomy/tick', { method: 'POST', body: JSON.stringify({ reason: $('reasonInput')?.value || 'manual', direction: $('directionInput')?.value || '手动触发' }) });
    setOutput('output', data); await refreshAll();
  },
  selfEvolve: async () => setOutput('output', await api('/api/self-evolve', { method: 'POST', body: JSON.stringify({ topic: $('evolveTopic').value }) })),
  searchMemory: async () => setOutput('memoryOutput', await api('/api/memory/search', { method: 'POST', body: JSON.stringify({ query: $('memoryQuery').value, limit: Number($('memoryLimit').value || 5) }) })),
  loadMemoryIndex: async () => setOutput('memoryOutput', await api('/api/memory/index')),
  runCurator: async () => setOutput('memoryOutput', await api('/api/curator/run', { method: 'POST', body: '{}' })),
  sendChat: async () => {
    const message = $('chatInput').value.trim();
    if (!message) return;
    $('chatInput').value = '';
    appendChat('user', message);
    const data = await api('/api/chat', { method: 'POST', body: JSON.stringify({ message }) });
    appendChat('assistant', data.reply || data.response || JSON.stringify(data));
  },
  restartRuntime: async () => {
    if (!confirm('确认重启 Web 运行时？')) return;
    setOutput('systemOutput', await api('/api/runtime/restart', { method: 'POST', body: JSON.stringify({ reason: 'manual_dashboard_restart' }) }));
  }
};
document.querySelectorAll('[data-action]').forEach(btn => btn.addEventListener('click', () => run(btn, btn.textContent.trim() || btn.title || '操作', actions[btn.dataset.action])));
document.querySelectorAll('.nav button').forEach(btn => btn.addEventListener('click', () => {
  document.querySelectorAll('.nav button').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  btn.classList.add('active');
  $(btn.dataset.tab).classList.add('active');
  const titles = {
    overview: ['Gateway 控制台', '运行状态、自治循环、学习进化和记忆检索。'],
    chat: ['Chat Session', '本地 Agent 对话通道。'],
    autonomy: ['Autonomy', '自主循环控制与运行状态。'],
    learning: ['Evolution', '经验、看板和小步源码进化。'],
    memory: ['Memory', '长期记忆检索与策展。'],
    system: ['System', '运行时、模型、目标和健康检查。']
  };
  const t = titles[btn.dataset.tab] || titles.overview;
  $('pageTitle').textContent = t[0];
  $('pageDesc').textContent = t[1];
}));
$('refreshBtn').addEventListener('click', () => run($('refreshBtn'), '刷新', refreshAll));
$('healthBtn').addEventListener('click', () => run($('healthBtn'), '健康检查', actions.loadHealth));
function connectEvents() {
  try {
    const source = new EventSource('/api/events');
    source.onopen = () => {
      $('eventDot').className = 'dot ok';
      $('eventState').textContent = '已连接';
      $('railEvents').textContent = 'online';
      $('eventLog').textContent = ': connected';
    };
    source.onmessage = (event) => {
      const line = `${new Date().toLocaleTimeString()} ${event.data}`;
      $('eventLog').textContent = `${line}\n${$('eventLog').textContent}`.slice(0, 5000);
    };
    source.onerror = () => {
      $('eventDot').className = 'dot bad';
      $('eventState').textContent = '断开';
      $('railEvents').textContent = 'offline';
    };
  } catch (err) {
    $('eventDot').className = 'dot bad';
    $('eventState').textContent = '失败';
  }
}
connectEvents();
refreshAll().catch(err => setOutput('output', { status: 'failed', error: err.message }));
</script>
</body>
</html>'''
