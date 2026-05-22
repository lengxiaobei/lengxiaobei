/* ================================================================
 * 冷小北 前端 — Phase 2 升级版
 * 5 模块：对话 / 自进化 / 学习进度 / 执行情况 / 系统
 * SSE 实时事件总线
 * ================================================================ */

const state = {
  view: 'chat',
  busy: false,
  chatBusy: false,
  context: null,
  lastSyncAt: null,
  eventStreamPaused: false,
  eventFilter: '',
  loadedViews: new Set(),
  capColors: ['#14b8a6', '#0ea5e9', '#f59e0b', '#ec4899', '#8b5cf6', '#10b981', '#ef4444', '#f97316', '#6366f1', '#64748b'],
  countdownTimer: null,
  autonomyEta: null,
  autonomyEnabled: false,
};

const titles = {
  chat: ['对话工作台', '与冷小北对话，下方向或提问。'],
  evolve: ['自主进化', '自检、修复、验证、学习、落地的运行闭环。'],
  learning: ['学习进度', 'Lesson 生命周期、能力分布与学习时间轴。'],
  execution: ['执行情况', '后台循环、四大门面状态与实时事件流。'],
  system: ['系统上下文', '身份、关键文件、健康、模型配置、记忆 RAG、目标动机。'],
};

/* ================================================================
   工具函数
   ================================================================ */

function debounce(fn, delay) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

function escapeHTML(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatTimestamp(ts) {
  if (!ts) return '-';
  const d = new Date(ts > 1e12 ? ts : ts * 1000);
  return d.toLocaleString('zh-CN', { hour12: false });
}

function formatRelative(ts) {
  if (!ts) return '-';
  const seconds = Math.floor((Date.now() - (ts > 1e12 ? ts : ts * 1000)) / 1000);
  if (seconds < 60) return `${seconds}s 前`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m 前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h 前`;
  return `${Math.floor(seconds / 86400)}d 前`;
}

/* ================================================================
   Toast 通知
   ================================================================ */

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('toast-visible'));
  setTimeout(() => {
    toast.classList.remove('toast-visible');
    toast.addEventListener('transitionend', () => toast.remove());
  }, 3000);
}

/* ================================================================
   初始化
   ================================================================ */

document.addEventListener('DOMContentLoaded', () => {
  safeInit(bindNavigation, 'navigation');
  safeInit(bindActions, 'actions');
  safeInit(bindKeyboardShortcuts, 'keyboard');
  safeInit(bindExecutionActions, 'execution-actions');
  safeInit(bindEvolveExtras, 'evolve-extras');
  safeInit(bindMemorySearch, 'memory-search');
  refreshAllImmediate();
  setTimeout(connectEvents, 0);
  loadView(state.view);
  // 回放历史对话（在欢迎消息后追加）
  safeInit(replayChatHistory, 'chat-history-replay');
});

function safeInit(fn, name) {
  try {
    fn();
  } catch (error) {
    console.warn(`[init] ${name} failed`, error);
  }
}

function bindNavigation() {
  document.querySelectorAll('.nav-btn').forEach((button) => {
    button.addEventListener('click', () => setView(button.dataset.view));
  });
  document.getElementById('refresh-btn').addEventListener('click', () => {
    const btn = document.getElementById('refresh-btn');
    btn.style.transform = 'rotate(360deg)';
    setTimeout(() => { btn.style.transform = ''; }, 400);
    refreshAll();
    loadView(state.view, true);
  });
}

function bindActions() {
  document.getElementById('send-chat-btn').addEventListener('click', sendChat);
  document.getElementById('chat-input').addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendChat();
    }
  });
  document.getElementById('run-btn').addEventListener('click', () => runSelfEvolution(false));
  document.getElementById('learn-btn').addEventListener('click', learnOnly);
  document.getElementById('apply-btn').addEventListener('click', () => runSelfEvolution(true));
  document.getElementById('copy-result-btn').addEventListener('click', copyResult);
  document.querySelectorAll('.tool-btn').forEach((button) => {
    button.addEventListener('click', () => runLocalAction(button));
  });
  // 看板刷新
  const refreshKanbanBtn = document.getElementById('refresh-kanban-btn');
  if (refreshKanbanBtn) refreshKanbanBtn.addEventListener('click', () => loadLearningView(true));
  // 详情弹窗关闭
  const detailCloseBtn = document.getElementById('detail-close');
  if (detailCloseBtn) detailCloseBtn.addEventListener('click', () => {
    document.getElementById('lesson-detail-overlay').style.display = 'none';
  });
  const detailOverlay = document.getElementById('lesson-detail-overlay');
  if (detailOverlay) detailOverlay.addEventListener('click', (e) => {
    if (e.target === detailOverlay) detailOverlay.style.display = 'none';
  });
  // 记忆提炼按钮
  const refineAllBtn = document.getElementById('refine-all-btn');
  if (refineAllBtn) refineAllBtn.addEventListener('click', () => runRefine('all'));
  const refineEpisodeBtn = document.getElementById('refine-episode-btn');
  if (refineEpisodeBtn) refineEpisodeBtn.addEventListener('click', () => runRefine('raw_to_episode'));
  const refineKnowledgeBtn = document.getElementById('refine-knowledge-btn');
  if (refineKnowledgeBtn) refineKnowledgeBtn.addEventListener('click', () => runRefine('episode_to_knowledge'));
  const refineProfileBtn = document.getElementById('refine-profile-btn');
  if (refineProfileBtn) refineProfileBtn.addEventListener('click', () => runRefine('knowledge_to_profile'));
  const curatorRunBtn = document.getElementById('curator-run-btn');
  if (curatorRunBtn) curatorRunBtn.addEventListener('click', runCurator);
  const dreamBtn = document.getElementById('dream-btn');
  if (dreamBtn) dreamBtn.addEventListener('click', runDream);
  const evolveTickBtn = document.getElementById('evolve-tick-btn');
  if (evolveTickBtn) evolveTickBtn.addEventListener('click', () => runAutonomyFromEvolve('tick'));
  const evolveStartBtn = document.getElementById('evolve-start-btn');
  if (evolveStartBtn) evolveStartBtn.addEventListener('click', () => runAutonomyFromEvolve('start'));
  const evolveStopBtn = document.getElementById('evolve-stop-btn');
  if (evolveStopBtn) evolveStopBtn.addEventListener('click', () => runAutonomyFromEvolve('stop'));
}

function bindKeyboardShortcuts() {
  document.addEventListener('keydown', (event) => {
    if (event.metaKey || event.ctrlKey) {
      const viewMap = { '1': 'chat', '2': 'evolve', '3': 'learning', '4': 'execution', '5': 'system' };
      const view = viewMap[event.key];
      if (view) {
        event.preventDefault();
        setView(view);
        return;
      }
      if (event.key === 'r') {
        event.preventDefault();
        refreshAll();
        loadView(state.view, true);
      }
    }
  });
}

function bindExecutionActions() {
  const startBtn = document.getElementById('autonomy-start-btn');
  const stopBtn = document.getElementById('autonomy-stop-btn');
  const tickBtn = document.getElementById('autonomy-tick-btn');
  if (startBtn) startBtn.addEventListener('click', async () => {
    try { await postJSON('/api/autonomy/start', { interval_seconds: 300 }); showToast('循环已启动', 'ok'); }
    catch (e) { showToast('启动失败：' + e.message, 'error'); }
    loadExecutionView(true);
  });
  if (stopBtn) stopBtn.addEventListener('click', async () => {
    try { await postJSON('/api/autonomy/stop', {}); showToast('循环已停止', 'ok'); }
    catch (e) { showToast('停止失败：' + e.message, 'error'); }
    loadExecutionView(true);
  });
  if (tickBtn) tickBtn.addEventListener('click', async () => {
    try {
      tickBtn.disabled = true;
      await postJSON('/api/autonomy/tick', { direction: '手动触发' });
      showToast('tick 完成', 'ok');
    } catch (e) {
      showToast('tick 失败：' + e.message, 'error');
    } finally {
      tickBtn.disabled = false;
      loadExecutionView(true);
    }
  });

  const filter = document.getElementById('event-filter');
  if (filter) filter.addEventListener('input', (e) => { state.eventFilter = e.target.value.trim().toLowerCase(); });
  const pauseBtn = document.getElementById('event-pause-btn');
  if (pauseBtn) pauseBtn.addEventListener('click', () => {
    state.eventStreamPaused = !state.eventStreamPaused;
    pauseBtn.textContent = state.eventStreamPaused ? '继续' : '暂停';
  });
  const clearBtn = document.getElementById('event-clear-btn');
  if (clearBtn) clearBtn.addEventListener('click', () => {
    const stream = document.getElementById('event-stream');
    if (stream) stream.innerHTML = '';
  });
}

function bindEvolveExtras() {
  const btn = document.getElementById('preview-improvements-btn');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    try {
      const data = await getJSON('/api/evolve/improvements');
      renderImprovements(data);
    } catch (e) {
      showToast('预览失败：' + e.message, 'error');
    } finally {
      btn.disabled = false;
    }
  });
}

function bindMemorySearch() {
  const input = document.getElementById('memory-search-input');
  const btn = document.getElementById('memory-search-btn');
  if (input) input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); runMemorySearch(); }
  });
  if (btn) btn.addEventListener('click', runMemorySearch);
}

/* ================================================================
   视图切换 + 懒加载
   ================================================================ */

function setView(view) {
  state.view = view;
  document.querySelectorAll('.nav-btn').forEach((button) => {
    button.classList.toggle('active', button.dataset.view === view);
  });
  document.querySelectorAll('.view').forEach((section) => {
    section.classList.toggle('active', section.id === view);
  });
  const [title, subtitle] = titles[view] || titles.chat;
  document.getElementById('view-title').textContent = title;
  document.getElementById('view-subtitle').textContent = subtitle;
  loadView(view);
}

function loadView(view, force = false) {
  state.loadedViews.add(view);
  switch (view) {
    case 'chat': break;
    case 'evolve': loadEvolveView(); break;
    case 'learning': loadLearningView(); break;
    case 'execution': loadExecutionView(); break;
    case 'system': loadSystemView(); break;
  }
}

/* ================================================================
   全局刷新（context / metrics）
   ================================================================ */

const debouncedRefreshAll = debounce(refreshAllImmediate, 600);
async function refreshAll() { debouncedRefreshAll(); }

async function refreshAllImmediate() {
  setSyncState('syncing');
  const results = await Promise.allSettled([
    refreshContext(),
    refreshLessonsCount(),
    refreshRunsCount(),
  ]);
  const failed = results.some((r) => r.status === 'rejected');
  setSyncState(failed ? 'partial' : 'synced');
  if (failed && !state.context) {
    setHealthState('同步失败', false);
    const reason = results.find((r) => r.status === 'rejected')?.reason;
    setRuntimePath(reason?.message || '后端暂未返回运行环境');
  }
}

async function refreshContext() {
  const data = await getJSON('/api/agent-context');
  state.context = data.context;
  state.lastSyncAt = new Date();
  renderContext(data.context);
}

function renderContext(context) {
  if (!context) return;
  const identity = context.identity || {};
  const runtime = context.runtime || {};
  const health = context.health || {};
  const memory = context.memory || {};

  document.getElementById('identity-role').textContent = identity.role || '强进化型数字生命体';
  setHealthState(health.status === 'healthy' ? '后端已同步' : '后端异常', health.status === 'healthy');
  setRuntimePath(runtime.project_root || '未知项目路径');

  document.getElementById('fact-root').textContent = runtime.project_root || '-';
  document.getElementById('fact-memory').textContent = runtime.memory_dir || '-';
  document.getElementById('fact-chat').textContent = runtime.chat_route || '-';
  document.getElementById('fact-evolution').textContent = runtime.self_evolution_entry || '-';

  document.getElementById('metric-lessons').textContent = String(memory.lessons?.count || 0);
  document.getElementById('metric-runs').textContent = String(memory.runs?.count || 0);

  renderCapabilities(context.capabilities || []);
  renderBoundaries(context.boundaries || []);
  renderDocs(context.docs || []);
  renderFiles(context.key_files || []);
}

function renderCapabilities(capabilities) {
  const list = document.getElementById('capability-list');
  if (!capabilities.length) { list.innerHTML = '<div class="empty">未同步能力列表。</div>'; return; }
  list.innerHTML = capabilities.map((c) => `
    <div class="capability"><span>${escapeHTML(c.name)}</span><small>${escapeHTML(c.endpoint || '')}</small></div>
  `).join('');
}

function renderBoundaries(boundaries) {
  document.getElementById('boundary-list').innerHTML = boundaries.map((b) => `<li>${escapeHTML(b)}</li>`).join('');
}

function renderDocs(docs) {
  const list = document.getElementById('doc-list');
  if (!docs.length) { list.innerHTML = '<div class="empty">未读取到身份文档。</div>'; return; }
  list.innerHTML = docs.map((doc) => `
    <article class="doc-item">
      <div class="item-row">
        <strong>${escapeHTML(doc.path)}</strong>
        <span class="pill ${doc.exists ? '' : 'bad'}">${doc.exists ? 'loaded' : 'missing'}</span>
      </div>
      <p>${escapeHTML(doc.excerpt || '未读取到内容。')}</p>
    </article>
  `).join('');
}

function renderFiles(files) {
  const list = document.getElementById('file-list');
  if (!files.length) { list.innerHTML = '<div class="empty">未同步关键文件。</div>'; return; }
  list.innerHTML = files.map((f) => `
    <div class="file-row">
      <span>${escapeHTML(f.path)}</span>
      <strong class="${f.exists ? 'file-exists' : 'file-missing'}">${f.exists ? '存在' : '缺失'}</strong>
    </div>
  `).join('');
}

async function refreshLessonsCount() {
  try {
    const data = await getJSON('/api/lessons');
    document.getElementById('metric-lessons').textContent = String(data.count || 0);
  } catch (e) { /* ignore */ }
}

async function refreshRunsCount() {
  try {
    const data = await getJSON('/api/runs');
    document.getElementById('metric-runs').textContent = String(data.count || 0);
  } catch (e) { /* ignore */ }
}

/* ================================================================
   对话
   ================================================================ */

async function sendChat() {
  if (state.chatBusy) return;
  const input = document.getElementById('chat-input');
  const message = input.value.trim();
  if (!message) { input.focus(); return; }

  input.value = '';
  addChatMessage('user', message);
  const pending = addChatMessage('agent', '正在思考...', { pending: true });
  setChatBusy(true);

  try {
    const data = await postJSON('/api/chat', { message });
    const reply = data.reply || '我收到了，但没有返回内容。';
    const body = pending.querySelector('.message-body');
    body.textContent = reply;
    if (Array.isArray(data.tool_calls) && data.tool_calls.length) {
      const detail = document.createElement('details');
      detail.className = 'tool-trace';
      detail.innerHTML = `
        <summary>调用了 ${data.tool_calls.length} 个工具</summary>
        <pre>${escapeHTML(JSON.stringify(data.tool_results || data.tool_calls, null, 2))}</pre>
      `;
      pending.querySelector('.message-content').appendChild(detail);
    }
    // 真实回复到了，更新 localStorage 中最后一条 agent
    updateLastAgentMessage(reply);
    await refreshContext().catch(() => {});
  } catch (error) {
    pending.classList.add('error');
    const errMsg = `请求失败：${error.message}`;
    pending.querySelector('.message-body').textContent = errMsg;
    updateLastAgentMessage(errMsg);
    showToast('对话请求失败', 'error');
  } finally {
    setChatBusy(false);
    input.focus();
  }
}

async function runLocalAction(button) {
  const action = button.dataset.action;
  const path = button.dataset.path || '';
  const label = button.textContent.trim();

  button.disabled = true;
  const pending = addChatMessage('agent', `正在执行本地操作：${label}...`);
  pending.classList.add('tool-message');

  try {
    const data = await postJSON('/api/local-action', { action, path });
    pending.querySelector('.message-body').textContent = formatLocalActionResult(data);
    showToast(`${label} 完成`, 'ok');
  } catch (error) {
    pending.classList.add('error');
    pending.querySelector('.message-body').textContent = `本地操作失败：${error.message}`;
    showToast('本地操作失败', 'error');
  } finally {
    button.disabled = false;
  }
}

function formatLocalActionResult(data) {
  const title = data.title || data.action || '本地操作结果';
  const result = data.result || data;
  if (data.action === 'read_file') {
    return [
      `${title}`,
      `状态: ${result.status}`,
      `大小: ${result.size || 0} bytes`,
      result.truncated ? '注意: 内容已截断。' : '内容: ',
      '',
      result.content || '',
    ].join('\n');
  }
  if (data.action === 'model_config') {
    const providers = result.providers || {};
    const lines = Object.entries(providers).map(([name, info]) => {
      const ks = info.has_key ? '有 key' : '无 key';
      const models = (info.models || []).map((i) => i.id).join(', ');
      return `- ${name}: ${ks}; ${models}`;
    });
    return [
      '实时模型配置',
      `默认: ${result.configured_default || '-'}`,
      `启用: ${(result.enabled || []).join(', ')}`,
      `temperature: ${result.temperature}`,
      `max_tokens: ${result.max_tokens}`,
      `timeout: ${result.timeout} 秒`,
      `max_retries: ${result.max_retries}`,
      '',
      'Provider:',
      lines.join('\n'),
    ].join('\n');
  }
  return `${title}\n${JSON.stringify(result, null, 2)}`;
}

/* ================================================================
   自进化
   ================================================================ */

async function loadEvolveView() {
  try {
    const [autonomy, codeChanges] = await Promise.all([
      getJSON('/api/execution/autonomy'),
      getJSON('/api/code-changes?limit=8'),
    ]);
    renderEvolveLoop(autonomy.autonomy || {});
    renderEvolveChanges(codeChanges.changes || [], codeChanges.count || 0);
  } catch (e) {
    showToast('自进化状态加载失败：' + e.message, 'error');
  }
}

function renderEvolveLoop(autonomy) {
  state.autonomyEnabled = !!autonomy.enabled;
  const last = autonomy.last_result || {};
  const actions = last.actions || [];
  const types = new Set(actions.map((a) => a.type));

  const loopState = document.getElementById('evolve-loop-state');
  const lastStatus = document.getElementById('evolve-last-status');
  const tickCount = document.getElementById('evolve-tick-count');
  const nextTick = document.getElementById('evolve-next-tick');
  if (loopState) loopState.textContent = autonomy.enabled ? (autonomy.thread_alive ? '后台运行' : '启动中') : '手动';
  if (lastStatus) lastStatus.textContent = last.status ? `${last.status} · ${formatRelative(last.finished_at || last.started_at)}` : '-';
  if (tickCount) tickCount.textContent = String(autonomy.tick_count || 0);
  if (nextTick) nextTick.textContent = autonomy.next_tick_eta_seconds == null ? '--' : `${Math.max(0, Math.floor(autonomy.next_tick_eta_seconds))}s`;

  document.querySelectorAll('.loop-step').forEach((el) => {
    const step = el.dataset.step;
    const active =
      (step === 'check' && types.has('self_check')) ||
      (step === 'repair' && types.has('autonomous_repair')) ||
      (step === 'verify' && (types.has('post_lesson_verify') || types.has('post_evolution_verify')) ) ||
      (step === 'learn' && types.has('autonomous_learning')) ||
      (step === 'apply' && (types.has('apply_pending_lesson') || types.has('curator_evolution')));
    el.classList.toggle('active', active);
  });

  if (last && last.id) {
    setResult(JSON.stringify(last, null, 2), last.status === 'success' ? 'ok' : (last.status === 'failed' ? 'error' : 'warn'));
  }
}

function renderEvolveChanges(changes, total) {
  const count = document.getElementById('evolve-change-count');
  const list = document.getElementById('evolve-change-list');
  if (count) count.textContent = String(total || changes.length || 0);
  if (!list) return;
  if (!changes.length) {
    list.innerHTML = '<div class="empty">暂无源码改动记录。</div>';
    return;
  }
  list.innerHTML = changes.slice(0, 8).map((change) => {
    const files = Array.isArray(change.files) ? change.files : [];
    const fileLine = files.slice(0, 5).map((f) => `<span class="file-chip">${escapeHTML(f.path || '-')}</span>`).join('') || '<span class="muted">无文件差异</span>';
    const result = change.result_status || change.result?.status || '-';
    return `
      <article class="code-change-item compact-change">
        <header>
          <div>
            <strong>${escapeHTML(change.summary || change.trigger || change.id || '源码改动')}</strong>
            <small>${escapeHTML(change.actor || 'agent')} · ${formatRelative(change.created_at)}</small>
          </div>
          <span class="pill ${result === 'success' ? '' : 'bad'}">${escapeHTML(result)}</span>
        </header>
        <div class="code-change-files">${fileLine}</div>
      </article>
    `;
  }).join('');
}

async function runAutonomyFromEvolve(action) {
  const direction = document.getElementById('topic')?.value.trim() || '系统自检、修复真实 bug、验证并继续优化';
  setBusy(true, action);
  setResult(action === 'tick' ? '正在运行一轮自主闭环...' : '正在更新后台循环...', 'warn');
  try {
    let data;
    if (action === 'start') {
      data = await postJSON('/api/autonomy/start', { interval_seconds: 300 });
    } else if (action === 'stop') {
      data = await postJSON('/api/autonomy/stop', {});
    } else {
      data = await postJSON('/api/autonomy/tick', { direction });
    }
    const payload = data.result || data.autonomy || data;
    setResult(JSON.stringify(payload, null, 2), payload.status === 'failed' ? 'error' : 'ok');
    await loadEvolveView();
    if (state.view === 'execution') await loadExecutionView(true);
  } catch (error) {
    setResult(error.message, 'error');
    showToast('自主闭环执行失败', 'error');
  } finally {
    setBusy(false, 'idle');
  }
}

async function runSelfEvolution(applyPending) {
  const topic = document.getElementById('topic').value.trim();
  const url = document.getElementById('url').value.trim();
  if (!applyPending && !topic) { setResult('请输入学习方向。', 'warn'); return; }

  setBusy(true, applyPending ? 'applying' : 'running');
  setResult(applyPending ? '已发送应用 Pending 请求...' : '已发送自进化请求...', 'warn');
  try {
    const data = await postJSON('/api/self-evolve', { topic, url, apply_pending: applyPending });
    setResult(JSON.stringify(data.result || data, null, 2), data.status === 'ok' ? 'ok' : 'warn');
    showToast(applyPending ? 'Pending 已应用' : '自进化完成', data.status === 'ok' ? 'ok' : 'warn');
    loadLearningView(true);
  } catch (error) {
    setResult(error.message, 'error');
    showToast('自进化请求失败', 'error');
  } finally {
    setBusy(false, 'idle');
  }
}

async function learnOnly() {
  const topic = document.getElementById('topic').value.trim();
  const url = document.getElementById('url').value.trim();
  if (!topic) { setResult('请输入学习方向。', 'warn'); return; }

  setBusy(true, 'learning');
  setResult('正在提炼可学习能力...', 'warn');
  try {
    const data = await postJSON('/api/learn-agent', { topic, url });
    setResult(JSON.stringify(data.lesson || data, null, 2), data.status === 'ok' ? 'ok' : 'warn');
    showToast('Lesson 生成完成', data.status === 'ok' ? 'ok' : 'warn');
    loadLearningView(true);
  } catch (error) {
    setResult(error.message, 'error');
    showToast('学习请求失败', 'error');
  } finally {
    setBusy(false, 'idle');
  }
}

function renderImprovements(data) {
  const list = document.getElementById('improvements-list');
  const items = data.improvements || [];
  document.getElementById('improvements-count').textContent = String(items.length);
  if (!items.length) { list.innerHTML = '<div class="empty">当前没有待应用的改进。</div>'; return; }
  list.innerHTML = items.slice(0, 30).map((it, i) => `
    <article class="item">
      <div class="item-row">
        <strong>#${i + 1} ${escapeHTML((it && (it.title || it.issue || it.summary)) || '改进')}</strong>
        <span class="pill">${escapeHTML((it && (it.priority || it.level || '')) + '')}</span>
      </div>
      <pre class="output compact">${escapeHTML(JSON.stringify(it, null, 2).slice(0, 800))}</pre>
    </article>
  `).join('');
}

/* ================================================================
   学习进度视图 — 生命周期看板
   ================================================================ */

let _kanbanData = null;

async function loadLearningView(force = false) {
  try {
    const [kanban, caps, timeline] = await Promise.all([
      getJSON('/api/learning/kanban'),
      getJSON('/api/learning/capabilities'),
      getJSON('/api/learning/timeline?limit=50'),
    ]);
    _kanbanData = kanban;
    renderKanban(kanban);
    renderCapabilityDistribution(caps);
    renderLearningTimeline(timeline);
  } catch (e) {
    showToast('学习进度加载失败：' + e.message, 'error');
  }
}

function renderKanban(data) {
  const columns = data.columns || {};
  const stats = data.stats || {};
  const total = stats.total || 0;
  const totalEl = document.getElementById('kanban-total');
  if (totalEl) {
    // 显示总数 + 三档完成率
    const realRate = stats.real_completion_rate;
    const realN = stats.verified_and_real || 0;
    const degradedN = stats.verified_degraded || 0;
    const fakeN = stats.verified_but_fake || 0;
    const totalClaims = realN + degradedN + fakeN;
    if (totalClaims > 0) {
      const pct = Math.round((realRate || 0) * 100);
      const tone = pct >= 70 ? 'ok' : (pct >= 30 ? 'warn' : 'bad');
      totalEl.innerHTML = `${total}` +
        ` <span class="real-rate-pill" data-tone="${tone}" title="真完成 = LLM 写的真智能函数；降级 = fallback 占位；假完成 = 只追加元数据">` +
        `真 ${realN} / 降 ${degradedN} / 假 ${fakeN} (真率 ${pct}%)</span>`;
    } else {
      totalEl.textContent = String(total);
    }
  }

  // 把后端的 substantive + metadata_only + verified 合并显示策略：
  // - "已验证"列: 同时显示 substantive (真完成 ✓) 和 metadata_only (假完成 ⚠)
  // - failed 列同时显示 blocked
  const renderedColumns = {
    pending: columns.pending || [],
    learning: columns.learning || [],
    verified: [...(columns.substantive || []), ...(columns.metadata_only || [])],
    failed: [...(columns.failed || []), ...(columns.blocked || [])],
  };

  const statusList = ['pending', 'learning', 'verified', 'failed'];

  for (const status of statusList) {
    const cards = renderedColumns[status];
    const countEl = document.getElementById(`kanban-${status}-count`);
    if (countEl) countEl.textContent = String(cards.length);

    const listEl = document.getElementById(`kanban-${status}`);
    if (!listEl) continue;

    if (!cards.length) {
      listEl.innerHTML = '<div class="empty compact">空</div>';
      continue;
    }

    listEl.innerHTML = cards.map((card) => {
      const q = card.quality || {};
      // 质量徽章 — 三态：真完成 / 降级完成 / 假完成
      let qualityBadge = '';
      if (status === 'verified') {
        if (q.substantive === true) {
          const added = (q.added || []).length;
          const changed = (q.changed_funcs || []).length;
          const realF = (q.real_funcs || []).length;
          qualityBadge = `<span class="quality-badge real" title="真智能函数 ${realF} 个，新增/修改共 ${added + changed}">✓ 真完成</span>`;
        } else if (q.substantive === 'degraded') {
          const fbs = (q.fallback_funcs || []).join(', ');
          qualityBadge = `<span class="quality-badge degraded" title="占位函数: ${escapeHTML(fbs)} — LLM 主路径失败，走了 fallback">🟡 降级完成</span>`;
        } else if (q.substantive === false) {
          qualityBadge = `<span class="quality-badge fake" title="${escapeHTML(q.reason || '只追加元数据')}">⚠ 假完成</span>`;
        } else {
          qualityBadge = `<span class="quality-badge unknown" title="旧版数据，质量未知">? 未知</span>`;
        }
      }

      const targetFile = card.target_file ? `<small class="target-file">→ ${escapeHTML(card.target_file)}</small>` : '';

      return `
      <article class="kanban-card" data-lesson-id="${escapeHTML(card.id)}" onclick="showLessonDetail('${escapeHTML(card.id)}')">
        <div class="card-head">
          <strong>${escapeHTML(card.capability || card.topic || '未命名')}</strong>
          <span class="pill pill-${escapeHTML(card.status)}">${escapeHTML(card.status)}</span>
        </div>
        ${qualityBadge}
        <p>${escapeHTML((card.pattern || card.adaptation || '').slice(0, 100))}</p>
        ${targetFile}
        <div class="card-meta">
          <span>${escapeHTML(card.source || 'unknown')}</span>
          ${card.run_count > 0 ? `<span class="run-badge">${card.run_count} run</span>` : ''}
          <small>${formatRelative(card.created_at)}</small>
        </div>
        ${card.status === 'pending' ? '<button class="card-action-btn" onclick="event.stopPropagation();applyLessonFromKanban(\'' + escapeHTML(card.id) + '\')">应用</button>' : ''}
        ${card.status === 'failed' ? '<button class="card-action-btn retry" onclick="event.stopPropagation();applyLessonFromKanban(\'' + escapeHTML(card.id) + '\')">重试</button>' : ''}
      </article>
    `;
    }).join('');
  }
}

async function showLessonDetail(lessonId) {
  if (!_kanbanData) return;
  const columns = _kanbanData.columns || {};
  let card = null;
  for (const status of Object.keys(columns)) {
    card = columns[status].find((c) => c.id === lessonId);
    if (card) break;
  }
  if (!card) return;

  document.getElementById('detail-capability').textContent = card.capability || card.topic || '未命名';
  document.getElementById('detail-status-pill').textContent = card.status;
  document.getElementById('detail-status-pill').className = `pill pill-${card.status}`;
  document.getElementById('detail-source').textContent = card.source || '-';
  document.getElementById('detail-topic').textContent = card.topic || '-';
  document.getElementById('detail-evidence').textContent = card.evidence || '-';
  document.getElementById('detail-pattern').textContent = card.pattern || '-';
  document.getElementById('detail-adaptation').textContent = card.adaptation || '-';

  const filesList = document.getElementById('detail-files');
  filesList.innerHTML = (card.suggested_files || []).map((f) => `<li>${escapeHTML(f)}</li>`).join('') || '<li class="muted">无</li>';

  document.getElementById('detail-run-count').textContent = String(card.run_count || 0);
  const runsDiv = document.getElementById('detail-runs');
  if (card.run_count > 0 && card.timeline) {
    const runEvents = card.timeline.filter((t) => t.event === 'run');
    runsDiv.innerHTML = runEvents.map((r) => `
      <div class="run-item pill-${escapeHTML(r.status || 'unknown')}">
        <span class="run-status">${escapeHTML(r.status || '?')}</span>
        <span class="run-detail">${escapeHTML(r.detail || '')}</span>
        <small>${formatRelative(r.time)}</small>
      </div>
    `).join('');
  } else {
    runsDiv.innerHTML = '<div class="muted">暂无关联 Run</div>';
  }

  // 生命周期时间线
  const timelineDiv = document.getElementById('detail-timeline');
  if (card.timeline && card.timeline.length > 0) {
    timelineDiv.innerHTML = card.timeline.map((t) => {
      const icon = t.event === 'created' ? '1' : t.event === 'run' ? '2' : '3';
      const label = t.event === 'created' ? '创建' : t.event === 'run' ? `Run (${t.status || '?'})` : '应用';
      return `
        <div class="timeline-step">
          <div class="step-dot step-${t.event}">${icon}</div>
          <div class="step-content">
            <strong>${label}</strong>
            <p>${escapeHTML(t.detail || '')}</p>
            <small>${formatTimestamp(t.time)}</small>
          </div>
        </div>
      `;
    }).join('');
  } else {
    timelineDiv.innerHTML = '<div class="muted">无时间线记录</div>';
  }

  // 操作按钮
  const actionsDiv = document.getElementById('detail-actions');
  if (card.status === 'pending') {
    actionsDiv.innerHTML = '<button class="primary-btn" onclick="applyLessonFromKanban(\'' + escapeHTML(card.id) + '\');document.getElementById(\'lesson-detail-overlay\').style.display=\'none\'">应用此 Lesson</button>';
  } else if (card.status === 'failed') {
    actionsDiv.innerHTML = '<button class="primary-btn" onclick="applyLessonFromKanban(\'' + escapeHTML(card.id) + '\');document.getElementById(\'lesson-detail-overlay\').style.display=\'none\'">重试应用</button>';
  } else {
    actionsDiv.innerHTML = '';
  }

  document.getElementById('lesson-detail-overlay').style.display = 'flex';
}

async function applyLessonFromKanban(lessonId) {
  showToast('正在应用 Lesson...', 'info');
  try {
    const data = await postJSON('/api/learning/apply-lesson', { lesson_id: lessonId });
    showToast('Lesson 应用完成', 'ok');
    loadLearningView(true);
  } catch (e) {
    showToast('应用失败：' + e.message, 'error');
  }
}

function renderCapabilityDistribution(data) {
  const dist = data.distribution || [];
  const total = data.total_lessons || 0;
  document.getElementById('cap-total').textContent = String(total);
  document.getElementById('cap-center-count').textContent = String(total);

  const svg = document.getElementById('cap-donut');
  const legend = document.getElementById('cap-legend');

  if (!dist.length || total === 0) {
    svg.innerHTML = '<circle cx="100" cy="100" r="80" fill="none" stroke="#334155" stroke-width="20"/>';
    legend.innerHTML = '<li class="empty compact">还没有能力数据</li>';
    return;
  }

  const top = dist.slice(0, 8);
  const otherCount = dist.slice(8).reduce((s, i) => s + i.count, 0);
  if (otherCount > 0) top.push({ capability: '其他', count: otherCount });

  const sum = top.reduce((s, i) => s + i.count, 0) || 1;
  const cx = 100, cy = 100, r = 80, stroke = 24;
  const circumference = 2 * Math.PI * r;

  let offset = 0;
  const parts = top.map((item, idx) => {
    const frac = item.count / sum;
    const length = circumference * frac;
    const color = state.capColors[idx % state.capColors.length];
    const c = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${color}" stroke-width="${stroke}"
                  stroke-dasharray="${length.toFixed(2)} ${(circumference - length).toFixed(2)}"
                  stroke-dashoffset="${(-offset).toFixed(2)}" transform="rotate(-90 ${cx} ${cy})"/>`;
    offset += length;
    return c;
  });
  svg.innerHTML = parts.join('');

  legend.innerHTML = top.map((item, idx) => `
    <li><span class="dot" style="background:${state.capColors[idx % state.capColors.length]}"></span>
        <span class="cap-name">${escapeHTML(item.capability)}</span>
        <strong>${item.count}</strong></li>
  `).join('');
}

function renderLearningTimeline(data) {
  const timeline = data.timeline || [];
  document.getElementById('timeline-count').textContent = String(data.count || timeline.length);
  const ol = document.getElementById('learning-timeline');
  if (!timeline.length) { ol.innerHTML = '<li class="empty compact">还没有学习记录。</li>'; return; }
  ol.innerHTML = timeline.map((l) => `
    <li class="timeline-item">
      <div class="dot pill-${escapeHTML(l.status || 'pending')}"></div>
      <div class="line"></div>
      <div class="content">
        <div class="item-row">
          <strong>${escapeHTML(l.capability || l.topic || '未命名')}</strong>
          <small>${formatTimestamp(l.created_at)}</small>
        </div>
        <p class="muted">${escapeHTML(l.source || 'unknown')}</p>
        ${l.why_good ? `<p><em>why:</em> ${escapeHTML(l.why_good)}</p>` : ''}
        ${l.adaptation ? `<p><em>adapt:</em> ${escapeHTML(l.adaptation)}</p>` : ''}
        ${l.applied_at ? `<small class="muted">applied: ${formatRelative(l.applied_at)}</small>` : ''}
      </div>
    </li>
  `).join('');
}

/* ================================================================
   执行情况视图
   ================================================================ */

async function loadExecutionView(force = false) {
  try {
    const [autonomy, facades, events, codeChanges] = await Promise.all([
      getJSON('/api/execution/autonomy'),
      getJSON('/api/execution/facades'),
      getJSON('/api/execution/events?limit=100'),
      getJSON('/api/code-changes?limit=20'),
    ]);
    renderAutonomyCard(autonomy.autonomy || {});
    renderFacadeGrid(facades.facades || {});
    renderCodeChanges(codeChanges.changes || [], codeChanges.count || 0);
    const stream = document.getElementById('event-stream');
    if (stream && stream.children.length === 0) {
      const list = (events.events || []).slice(-50);
      for (const ev of list) appendEventStreamItem(ev);
    }
  } catch (e) {
    showToast('执行情况加载失败：' + e.message, 'error');
  }
}

function renderAutonomyCard(autonomy) {
  state.autonomyEnabled = !!autonomy.enabled;
  state.autonomyEta = autonomy.next_tick_eta_seconds;

  const pill = document.getElementById('autonomy-state-pill');
  if (pill) {
    pill.textContent = autonomy.enabled ? (autonomy.thread_alive ? 'running' : 'starting') : 'idle';
    pill.dataset.tone = autonomy.enabled ? 'ok' : 'idle';
  }

  document.getElementById('autonomy-tick-count').textContent = String(autonomy.tick_count || 0);
  document.getElementById('autonomy-interval').textContent =
    autonomy.interval_seconds ? `${autonomy.interval_seconds}s` : '-';
  document.getElementById('autonomy-thread').textContent =
    autonomy.thread_alive ? '存活' : '休眠';

  const last = autonomy.last_result;
  document.getElementById('autonomy-last-status').textContent =
    last ? `${last.status || '-'} · ${formatRelative(last.finished_at || last.started_at)}` : '-';

  updateAutonomyCountdown();
  if (!state.countdownTimer) {
    state.countdownTimer = setInterval(updateAutonomyCountdown, 1000);
  }
}

function updateAutonomyCountdown() {
  const el = document.getElementById('autonomy-eta');
  if (!el) return;
  if (!state.autonomyEnabled || state.autonomyEta == null) {
    el.textContent = '--';
    return;
  }
  state.autonomyEta = Math.max(0, state.autonomyEta - 1);
  el.textContent = String(Math.floor(state.autonomyEta));
}

function renderFacadeGrid(facades) {
  const labels = {
    guardian: 'Guardian 守护',
    memory: 'Memory 记忆',
    evolution: 'Evolution 进化',
    reasoning: 'Reasoning 推理',
  };
  const grid = document.getElementById('facade-grid');
  if (!grid) return;
  grid.innerHTML = Object.entries(labels).map(([key, label]) => {
    const f = facades[key] || {};
    const loaded = f.loaded;
    const items = Object.entries(f)
      .filter(([k]) => k !== 'loaded' && k !== 'error')
      .map(([k, v]) => {
        const ok = v === true || v === 'healthy' || (typeof v === 'string' && v.length);
        const display = typeof v === 'boolean' ? (v ? '✓' : '✗') : escapeHTML(String(v));
        return `<div class="facade-item"><span>${escapeHTML(k)}</span><strong class="${ok ? 'ok' : 'bad'}">${display}</strong></div>`;
      }).join('');
    return `
      <div class="facade-card ${loaded ? '' : 'facade-cold'}">
        <header>
          <strong>${escapeHTML(label)}</strong>
          <span class="pill ${loaded ? '' : 'bad'}">${loaded ? 'loaded' : 'cold'}</span>
        </header>
        ${f.error ? `<p class="bad">${escapeHTML(f.error)}</p>` : items || '<div class="empty compact">无详情</div>'}
      </div>
    `;
  }).join('');
}

function renderCodeChanges(changes, total) {
  const count = document.getElementById('code-change-count');
  if (count) count.textContent = String(total || changes.length || 0);

  const list = document.getElementById('code-change-list');
  if (!list) return;
  if (!changes.length) {
    list.innerHTML = '<div class="empty">暂无源码改动记录。</div>';
    return;
  }

  list.innerHTML = changes.map((change) => {
    const files = Array.isArray(change.files) ? change.files : [];
    const changed = files.slice(0, 6);
    const fileLine = changed.length
      ? changed.map((f) => `<span class="file-chip">${escapeHTML(f.path || '-')}</span>`).join('')
      : '<span class="muted">无文件差异</span>';
    const result = change.result_status || change.result?.status || '-';
    const verification = change.verification?.status || change.result?.verification?.status || '';
    const diffPreview = changed
      .map((f) => String(f.diff || '').split('\n').slice(0, 16).join('\n'))
      .filter(Boolean)
      .join('\n\n');

    return `
      <article class="code-change-item">
        <header>
          <div>
            <strong>${escapeHTML(change.summary || change.trigger || change.id || '源码改动')}</strong>
            <small>${escapeHTML(change.actor || 'agent')} · ${formatRelative(change.created_at)}</small>
          </div>
          <span class="pill ${result === 'success' ? '' : 'bad'}">${escapeHTML(result)}</span>
        </header>
        <div class="code-change-files">${fileLine}</div>
        ${verification ? `<p class="muted">验证：${escapeHTML(verification)}</p>` : ''}
        ${diffPreview ? `<pre class="diff-preview">${escapeHTML(diffPreview)}</pre>` : ''}
      </article>
    `;
  }).join('');
}

function appendEventStreamItem(event) {
  if (state.eventStreamPaused) return;
  const stream = document.getElementById('event-stream');
  if (!stream) return;
  const filter = state.eventFilter;
  if (filter && !String(event.event_type || '').toLowerCase().includes(filter)) return;

  const li = document.createElement('li');
  const source = event.source || 'system';
  li.className = `event-item source-${source}`;
  const time = formatTimestamp(event.timestamp);
  const data = event.data ? JSON.stringify(event.data) : '';
  li.innerHTML = `
    <span class="event-time">${time}</span>
    <span class="event-type">${escapeHTML(event.event_type || '')}</span>
    <span class="event-source">${escapeHTML(source)}</span>
    <span class="event-data" title="${escapeHTML(data)}">${escapeHTML(data.slice(0, 160))}</span>
  `;
  stream.appendChild(li);
  while (stream.children.length > 200) stream.removeChild(stream.firstChild);
  stream.scrollTop = stream.scrollHeight;
}

/* ================================================================
   系统视图
   ================================================================ */

async function loadSystemView() {
  await Promise.allSettled([
    refreshSystemStatus(),
    loadGoals(),
    loadMotivations(),
  ]);
}

async function refreshSystemStatus() {
  try {
    const [status, health, modelConfig] = await Promise.all([
      getJSON('/api/status'),
      getJSON('/api/health'),
      getJSON('/api/model-config'),
    ]);
    document.getElementById('status-box').textContent = JSON.stringify(status, null, 2);
    document.getElementById('health-box').textContent = JSON.stringify(health, null, 2);
    document.getElementById('model-box').textContent = JSON.stringify(modelConfig.model_config || modelConfig, null, 2);
  } catch (error) {
    document.getElementById('health-box').textContent = error.message;
    document.getElementById('model-box').textContent = error.message;
  }
}

async function loadGoals() {
  try {
    const data = await getJSON('/api/goals');
    const list = document.getElementById('goal-list');
    document.getElementById('goal-count').textContent = String(data.count || 0);
    const goals = data.goals || [];
    if (!goals.length) { list.innerHTML = '<div class="empty">' + escapeHTML(data.note || '暂无目标') + '</div>'; return; }
    list.innerHTML = goals.slice(0, 50).map((g) => `
      <article class="item">
        <div class="item-row">
          <strong>${escapeHTML(g.title || g.id || '未命名')}</strong>
          <span class="pill">${escapeHTML(g.status || '')}</span>
        </div>
        <p>${escapeHTML((g.description || '').slice(0, 200))}</p>
      </article>
    `).join('');
  } catch (e) {
    document.getElementById('goal-list').innerHTML = `<div class="empty bad">${escapeHTML(e.message)}</div>`;
  }
}

async function loadMotivations() {
  try {
    const data = await getJSON('/api/motivations');
    const list = document.getElementById('motivation-list');
    document.getElementById('motivation-count').textContent = String(data.count || 0);
    const items = data.motivations || [];
    if (!items.length) { list.innerHTML = '<div class="empty">' + escapeHTML(data.note || '暂无动机') + '</div>'; return; }
    list.innerHTML = items.slice(0, 50).map((m) => `
      <article class="item">
        <div class="item-row">
          <strong>${escapeHTML(m.description || m.id || '未命名')}</strong>
          <span class="pill">${escapeHTML(m.motivation_type || '')}</span>
        </div>
        <p>强度: ${escapeHTML(String(m.intensity ?? '-'))}</p>
      </article>
    `).join('');
  } catch (e) {
    document.getElementById('motivation-list').innerHTML = `<div class="empty bad">${escapeHTML(e.message)}</div>`;
  }
}

async function runMemorySearch() {
  const input = document.getElementById('memory-search-input');
  const sel = document.getElementById('memory-search-type');
  const query = input.value.trim();
  const resultsEl = document.getElementById('memory-search-results');
  if (!query) { showToast('请输入查询', 'warn'); return; }

  const stateEl = document.getElementById('memory-search-state');
  stateEl.textContent = 'searching';
  stateEl.dataset.tone = 'warn';

  try {
    const data = await postJSON('/api/memory/search', {
      query,
      limit: 10,
      mem_type: sel.value || null,
    });
    stateEl.textContent = `${data.count || 0} hits`;
    stateEl.dataset.tone = 'ok';
    const results = data.results || [];
    if (!results.length) { resultsEl.innerHTML = '<div class="empty">没有命中结果。</div>'; return; }
    resultsEl.innerHTML = results.map((r, i) => `
      <article class="item">
        <div class="item-row">
          <strong>#${i + 1} ${escapeHTML(r.name || r.id || r.role || '记忆条目')}</strong>
          <span class="pill">${escapeHTML(String(r.type || r.role || ''))}</span>
        </div>
        <p>${escapeHTML(String(r.content || r.text || '').slice(0, 400))}</p>
        <small class="muted">${formatRelative(r.created_at || r.timestamp)} · score: ${escapeHTML(String(r.score ?? r._score ?? '-'))}</small>
      </article>
    `).join('');
  } catch (e) {
    stateEl.textContent = 'failed';
    stateEl.dataset.tone = 'bad';
    resultsEl.innerHTML = `<div class="empty bad">${escapeHTML(e.message)}</div>`;
  }
}

/* ================================================================
   SSE 实时事件订阅
   ================================================================ */

let eventSource = null;
let eventReconnectDelay = 1000;

function setLiveState(label, ok) {
  const dot = document.getElementById('live-dot');
  const lbl = document.getElementById('live-label');
  if (dot) dot.classList.toggle('ok', !!ok);
  if (lbl) lbl.textContent = '实时通道：' + label;
}

function getEventSourceURL(path) {
  if (typeof window !== 'undefined' && window.location.protocol === 'http:') return path;
  const apiBase = window.electronAPI && window.electronAPI.getAPIBase && window.electronAPI.getAPIBase();
  return apiBase ? new URL(path, apiBase).toString() : path;
}

function connectEvents() {
  if (eventSource) try { eventSource.close(); } catch (e) {}

  if (typeof EventSource === 'undefined') {
    setLiveState('不支持', false);
    return;
  }

  try {
    eventSource = new EventSource(getEventSourceURL('/api/events'));
  } catch (e) {
    setLiveState('不支持', false);
    return;
  }

  eventSource.addEventListener('open', () => {
    eventReconnectDelay = 1000;
    setLiveState('已连接', true);
    setSyncState('live');
  });

  eventSource.addEventListener('message', (ev) => {
    try { dispatchSSE(JSON.parse(ev.data)); } catch (e) {}
  });

  const known = [
    'autonomy.tick.started', 'autonomy.tick.finished', 'autonomy.curator.scanned',
    'evolution.completed', 'chat.tool.started', 'chat.tool.finished',
    'tool.failed', 'memory.updated', 'code.changed', 'test.failed',
    'budget.warning', 'user.idle', 'error.escalated', 'health.degraded',
    'kairos.awake',
  ];
  known.forEach((type) => {
    eventSource.addEventListener(type, (ev) => {
      try { dispatchSSE(JSON.parse(ev.data)); } catch (e) {}
    });
  });

  eventSource.addEventListener('error', () => {
    setLiveState('重连中...', false);
    try { eventSource.close(); } catch (e) {}
    setTimeout(connectEvents, eventReconnectDelay);
    eventReconnectDelay = Math.min(eventReconnectDelay * 2, 15000);
  });
}

function dispatchSSE(event) {
  appendEventStreamItem(event);
  const handler = sseHandlers[event.event_type];
  if (handler) try { handler(event.data || {}, event); } catch (e) { /* ignore */ }
}

const sseHandlers = {
  'autonomy.tick.started': (data) => {
    showToast(`autonomy 启动 · ${data.reason || ''}`, 'info');
    setBusy(true, 'autonomy');
  },
  'autonomy.tick.finished': (data) => {
    setBusy(false, 'idle');
    const tone = data.status === 'success' ? 'ok' : (data.status === 'failed' ? 'error' : 'warn');
    showToast(`autonomy 完成 · ${data.status || ''} (${data.elapsed_seconds || '-'}s)`, tone);
    if (state.view === 'execution') loadExecutionView(true);
    if (state.view === 'learning') loadLearningView(true);
    refreshLessonsCount();
    refreshRunsCount();
  },
  'evolution.completed': () => {
    refreshLessonsCount();
    refreshRunsCount();
  },
  'chat.tool.started': (data) => {
    if (state.view !== 'chat') return;
    const log = document.getElementById('chat-log');
    if (!log) return;
    const last = log.lastElementChild;
    if (last && last.classList.contains('chat-message') && last.classList.contains('agent')) {
      let trace = last.querySelector('.tool-live');
      if (!trace) {
        trace = document.createElement('div');
        trace.className = 'tool-live';
        last.querySelector('.message-content').appendChild(trace);
      }
      const span = document.createElement('span');
      span.className = 'tool-live-step';
      span.textContent = `▶ ${data.tool}`;
      trace.appendChild(span);
    }
  },
  'chat.tool.finished': (data) => {
    if (state.view !== 'chat') return;
    const log = document.getElementById('chat-log');
    if (!log) return;
    const last = log.lastElementChild;
    if (last) {
      const trace = last.querySelector('.tool-live');
      if (trace) {
        const span = document.createElement('span');
        span.className = 'tool-live-step ok';
        span.textContent = `✓ ${data.tool} (${data.elapsed_seconds}s)`;
        trace.appendChild(span);
      }
    }
  },
  'tool.failed': (data) => {
    if (state.view === 'chat') {
      const log = document.getElementById('chat-log');
      const last = log && log.lastElementChild;
      if (last) {
        const trace = last.querySelector('.tool-live');
        if (trace) {
          const span = document.createElement('span');
          span.className = 'tool-live-step bad';
          span.textContent = `✗ ${data.tool}`;
          trace.appendChild(span);
        }
      }
    }
  },
  'memory.updated': () => {
    refreshLessonsCount();
    refreshRunsCount();
    if (state.view === 'learning') loadLearningView(true);
  },
};

/* ================================================================
   HTTP Helpers — 同时支持浏览器直接访问和 Electron 桌面端
   ================================================================ */

function _useElectronAPI() {
  return typeof window !== 'undefined' && window.electronAPI && window.electronAPI.apiRequest;
}

async function getJSON(url) {
  if (_useElectronAPI()) {
    return window.electronAPI.apiRequest(url);
  }
  const response = await fetch(url);
  const text = await response.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (e) {
      // 后端返回了非 JSON（通常是 HTML 错误页）— 给出可读错误
      const snippet = text.slice(0, 80).replace(/\s+/g, ' ');
      throw new Error(`GET ${url} 返回非 JSON (${response.status}): ${snippet}…`);
    }
  }
  if (!response.ok) throw new Error(data.error || `${response.status} ${response.statusText}`);
  return data;
}

async function postJSON(url, body) {
  if (_useElectronAPI()) {
    return window.electronAPI.apiRequest(url, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (e) {
      const snippet = text.slice(0, 80).replace(/\s+/g, ' ');
      throw new Error(`POST ${url} 返回非 JSON (${response.status}): ${snippet}…`);
    }
  }
  if (!response.ok) throw new Error(data.error || `${response.status} ${response.statusText}`);
  return data;
}

/* ================================================================
   UI State Helpers
   ================================================================ */

function setBusy(busy, label) {
  state.busy = busy;
  const el = document.getElementById('run-state');
  if (el) el.textContent = label;
  ['run-btn', 'learn-btn', 'apply-btn', 'evolve-tick-btn', 'evolve-start-btn', 'evolve-stop-btn'].forEach((id) => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = busy;
  });
}

function setChatBusy(busy) {
  state.chatBusy = busy;
  document.getElementById('send-chat-btn').disabled = busy;
  document.getElementById('chat-input').disabled = busy;
}

function setResult(content, tone) {
  const box = document.getElementById('result-box');
  if (!box) return;
  box.textContent = content;
  box.dataset.tone = tone;
}

function setSyncState(label) {
  const pill = document.getElementById('sync-state');
  if (!pill) return;
  pill.textContent = label;
  pill.dataset.tone = label;
}

function setHealthState(label, ok) {
  const healthLabel = document.getElementById('health-label');
  const healthDot = document.getElementById('health-dot');
  if (healthLabel) healthLabel.textContent = label;
  if (healthDot) healthDot.classList.toggle('ok', !!ok);
}

function setRuntimePath(label) {
  const runtimePath = document.getElementById('runtime-path');
  if (runtimePath) runtimePath.textContent = label;
}

async function copyResult() {
  const text = document.getElementById('result-box').textContent;
  try {
    await navigator.clipboard.writeText(text);
    showToast('已复制到剪贴板', 'ok');
    const btn = document.getElementById('copy-result-btn');
    btn.textContent = '已复制';
    setTimeout(() => { btn.textContent = '复制'; }, 1200);
  } catch {
    showToast('复制失败：浏览器未允许剪贴板权限', 'error');
  }
}

function addChatMessage(role, content, opts = {}) {
  const log = document.getElementById('chat-log');
  const message = document.createElement('div');
  message.className = `chat-message ${role}`;

  if (role === 'agent') {
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.innerHTML = '<svg viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="16" fill="#14b8a6"/><path d="M11 13c0-1 .5-2.5 2.5-2.5S16 12 16 13" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/><path d="M16 13c0-1 .5-2.5 2.5-2.5S21 12 21 13" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/><path d="M13 20c0 0 1.2 2.5 3 2.5s3-2.5 3-2.5" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/></svg>';
    message.appendChild(avatar);
  }

  const contentDiv = document.createElement('div');
  contentDiv.className = 'message-content';

  const roleEl = document.createElement('div');
  roleEl.className = 'message-role';
  roleEl.textContent = role === 'user' ? '你' : '冷小北';

  const body = document.createElement('div');
  body.className = 'message-body';
  body.textContent = content;

  contentDiv.append(roleEl, body);
  message.appendChild(contentDiv);
  log.appendChild(message);
  log.scrollTop = log.scrollHeight;

  // 自动持久化（pending/replay 消息不重复存）
  if (!opts.skipPersist) {
    persistChatMessage({ role, content, ts: Date.now(), pending: !!opts.pending });
  }
  return message;
}

/* ================================================================
   对话历史持久化（localStorage，最多 100 条）
   ================================================================ */

const CHAT_HISTORY_KEY = 'lx_chat_history_v1';
const CHAT_HISTORY_LIMIT = 100;

function loadChatHistory() {
  try {
    const raw = localStorage.getItem(CHAT_HISTORY_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr : [];
  } catch (e) {
    return [];
  }
}

function persistChatMessage(msg) {
  try {
    const history = loadChatHistory();
    // pending 状态的消息（"正在思考..."）先不存，等真实回复来再覆盖
    if (msg.pending) return;
    history.push(msg);
    while (history.length > CHAT_HISTORY_LIMIT) history.shift();
    localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(history));
  } catch (e) { /* localStorage 满了或被禁，忽略 */ }
}

function updateLastAgentMessage(content) {
  try {
    const history = loadChatHistory();
    // 找最后一条 agent，更新内容
    for (let i = history.length - 1; i >= 0; i--) {
      if (history[i].role === 'agent') {
        history[i].content = content;
        history[i].ts = Date.now();
        localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(history));
        return;
      }
    }
    // 没找到就追加
    persistChatMessage({ role: 'agent', content, ts: Date.now() });
  } catch (e) { /* ignore */ }
}

function replayChatHistory() {
  const history = loadChatHistory();
  if (!history.length) return;
  const log = document.getElementById('chat-log');
  if (!log) return;

  // 在欢迎消息后追加历史标记 + 历史消息
  const divider = document.createElement('div');
  divider.className = 'chat-divider';
  divider.innerHTML = `<span>—— 历史对话 (${history.length}) ——</span>`;
  log.appendChild(divider);

  for (const msg of history) {
    addChatMessage(msg.role, msg.content, { skipPersist: true });
  }

  const liveDivider = document.createElement('div');
  liveDivider.className = 'chat-divider live';
  liveDivider.innerHTML = `<span>—— 当前会话 ——</span>`;
  log.appendChild(liveDivider);
}

function clearChatHistory() {
  try {
    localStorage.removeItem(CHAT_HISTORY_KEY);
    showToast('对话历史已清空', 'ok');
    const log = document.getElementById('chat-log');
    // 保留首条欢迎消息
    while (log.children.length > 1) log.removeChild(log.lastChild);
  } catch (e) {
    showToast('清空失败：' + e.message, 'error');
  }
}

// 暴露到全局，方便用户在 devtools console 或后续 UI 按钮触发
if (typeof window !== 'undefined') {
  window.lxClearChatHistory = clearChatHistory;
  window.lxLoadChatHistory = loadChatHistory;
}
