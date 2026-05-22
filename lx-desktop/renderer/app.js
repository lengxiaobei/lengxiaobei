const state = {
  view: 'chat',
  busy: false,
  chatBusy: false,
  context: null,
  lastSyncAt: null,
};

const titles = {
  chat: ['对话工作台', '与冷小北对话，下方向或提问。'],
  evolve: ['自进化', '把学习方向转成 Lesson、源码改进、验证记录。'],
  memory: ['记忆与记录', '查看 Agent 学到的能力与每次自进化运行结果。'],
  system: ['系统上下文', '查看冷小北当前知道的身份、路径、关键文件和后端健康。'],
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

/* ================================================================
   Toast 通知
   ================================================================ */

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  // 触发入场动画
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
  bindNavigation();
  bindActions();
  bindKeyboardShortcuts();
  refreshAll();
});

function bindNavigation() {
  document.querySelectorAll('.nav-btn').forEach((button) => {
    button.addEventListener('click', () => setView(button.dataset.view));
  });
  document.getElementById('refresh-btn').addEventListener('click', () => {
    const btn = document.getElementById('refresh-btn');
    btn.style.transform = 'rotate(360deg)';
    setTimeout(() => { btn.style.transform = ''; }, 400);
    refreshAll();
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
}

function bindKeyboardShortcuts() {
  document.addEventListener('keydown', (event) => {
    // Ctrl/Cmd + 数字键切换视图
    if (event.metaKey || event.ctrlKey) {
      const viewMap = { '1': 'chat', '2': 'evolve', '3': 'memory', '4': 'system' };
      const view = viewMap[event.key];
      if (view) {
        event.preventDefault();
        setView(view);
        return;
      }
      // Ctrl/Cmd + R 刷新
      if (event.key === 'r') {
        event.preventDefault();
        refreshAll();
        return;
      }
    }
  });
}

/* ================================================================
   视图切换
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
  refreshAll();
}

/* ================================================================
   数据刷新（带防抖）
   ================================================================ */

const debouncedRefreshAll = debounce(refreshAllImmediate, 800);

async function refreshAll() {
  debouncedRefreshAll();
}

async function refreshAllImmediate() {
  setSyncState('syncing');
  const results = await Promise.allSettled([
    refreshContext(),
    refreshLessons(),
    refreshRuns(),
    refreshStatus(),
  ]);
  const failed = results.some((result) => result.status === 'rejected');
  setSyncState(failed ? 'partial' : 'synced');
  if (failed) {
    const errorCount = results.filter((r) => r.status === 'rejected').length;
    showToast(`${errorCount} 项数据同步失败`, 'error');
  }
}

async function refreshContext() {
  const data = await getJSON('/api/agent-context');
  state.context = data.context;
  state.lastSyncAt = new Date();
  renderContext(data.context);
}

function renderContext(context) {
  const identity = context.identity || {};
  const runtime = context.runtime || {};
  const health = context.health || {};
  const memory = context.memory || {};

  document.getElementById('identity-role').textContent = identity.role || '强进化型数字生命体';
  document.getElementById('health-label').textContent = health.status === 'healthy' ? '后端已同步' : '后端异常';
  document.getElementById('health-dot').classList.toggle('ok', health.status === 'healthy');
  document.getElementById('runtime-path').textContent = runtime.project_root || '未知项目路径';

  document.getElementById('fact-root').textContent = runtime.project_root || '-';
  document.getElementById('fact-memory').textContent = runtime.memory_dir || '-';
  document.getElementById('fact-chat').textContent = runtime.chat_route || '-';
  document.getElementById('fact-evolution').textContent = runtime.self_evolution_entry || '-';

  const lessonCount = memory.lessons?.count || 0;
  const runCount = memory.runs?.count || 0;
  document.getElementById('metric-lessons').textContent = String(lessonCount);
  document.getElementById('metric-runs').textContent = String(runCount);

  renderCapabilities(context.capabilities || []);
  renderBoundaries(context.boundaries || []);
  renderDocs(context.docs || []);
  renderFiles(context.key_files || []);
}

function renderCapabilities(capabilities) {
  const list = document.getElementById('capability-list');
  if (!capabilities.length) {
    list.innerHTML = '<div class="empty">未同步能力列表。</div>';
    return;
  }
  list.innerHTML = capabilities.map((capability) => `
    <div class="capability">
      <span>${escapeHTML(capability.name)}</span>
      <small>${escapeHTML(capability.endpoint || '')}</small>
    </div>
  `).join('');
}

function renderBoundaries(boundaries) {
  const list = document.getElementById('boundary-list');
  list.innerHTML = boundaries.map((boundary) => `<li>${escapeHTML(boundary)}</li>`).join('');
}

function renderDocs(docs) {
  const list = document.getElementById('doc-list');
  if (!docs.length) {
    list.innerHTML = '<div class="empty">未读取到身份文档。</div>';
    return;
  }
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
  if (!files.length) {
    list.innerHTML = '<div class="empty">未同步关键文件。</div>';
    return;
  }
  list.innerHTML = files.map((file) => `
    <div class="file-row">
      <span>${escapeHTML(file.path)}</span>
      <strong class="${file.exists ? 'file-exists' : 'file-missing'}">${file.exists ? '存在' : '缺失'}</strong>
    </div>
  `).join('');
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
  const pending = addChatMessage('agent', '正在思考...');
  setChatBusy(true);

  try {
    const data = await postJSON('/api/chat', { message });
    const body = pending.querySelector('.message-body');
    body.textContent = data.reply || '我收到了，但没有返回内容。';
    await refreshContext().catch(() => {});
  } catch (error) {
    pending.classList.add('error');
    pending.querySelector('.message-body').textContent = `请求失败：${error.message}`;
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
    await refreshAll();
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
    const content = result.content || '';
    return [
      `${title}`,
      `状态: ${result.status}`,
      `大小: ${result.size || 0} bytes`,
      result.truncated ? '注意: 内容已截断。' : '内容: ',
      '',
      content,
    ].join('\n');
  }

  if (data.action === 'model_config') {
    const providers = result.providers || {};
    const providerLines = Object.entries(providers).map(([name, info]) => {
      const keyState = info.has_key ? '有 key' : '无 key';
      const models = (info.models || []).map((item) => item.id).join(', ');
      return `- ${name}: ${keyState}; ${models}`;
    });
    return [
      '实时模型配置',
      `默认模型: ${result.configured_default || '-'}`,
      `启用模型: ${(result.enabled || []).join(', ')}`,
      `temperature: ${result.temperature}`,
      `max_tokens: ${result.max_tokens}`,
      `timeout: ${result.timeout} 秒`,
      `max_retries: ${result.max_retries}`,
      '',
      'Provider:',
      providerLines.join('\n'),
    ].join('\n');
  }

  return `${title}\n${JSON.stringify(result, null, 2)}`;
}

/* ================================================================
   自进化
   ================================================================ */

async function runSelfEvolution(applyPending) {
  const topic = document.getElementById('topic').value.trim();
  const url = document.getElementById('url').value.trim();

  if (!applyPending && !topic) {
    setResult('请输入学习方向。', 'warn');
    return;
  }

  setBusy(true, applyPending ? 'applying' : 'running');
  setResult(applyPending ? '已发送应用 Pending 请求...' : '已发送自进化请求...', 'warn');
  try {
    const data = await postJSON('/api/self-evolve', {
      topic,
      url,
      apply_pending: applyPending,
    });
    setResult(JSON.stringify(data.result || data, null, 2), data.status === 'ok' ? 'ok' : 'warn');
    await refreshAll();
    showToast(applyPending ? 'Pending 已应用' : '自进化完成', data.status === 'ok' ? 'ok' : 'warn');
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
    await refreshAll();
    showToast('Lesson 生成完成', data.status === 'ok' ? 'ok' : 'warn');
  } catch (error) {
    setResult(error.message, 'error');
    showToast('学习请求失败', 'error');
  } finally {
    setBusy(false, 'idle');
  }
}

/* ================================================================
   数据刷新 — Lessons / Runs / Status
   ================================================================ */

async function refreshLessons() {
  const data = await getJSON('/api/lessons');
  document.getElementById('lesson-count').textContent = String(data.count || 0);
  document.getElementById('metric-lessons').textContent = String(data.count || 0);
  const list = document.getElementById('lesson-list');
  const lessons = data.lessons || [];
  if (!lessons.length) {
    list.innerHTML = '<div class="empty">还没有 Lesson。可以在"自进化"页先生成一条。</div>';
    return;
  }
  list.innerHTML = lessons.slice().reverse().map((lesson) => `
    <article class="item">
      <div class="item-row">
        <strong>${escapeHTML(lesson.capability || lesson.topic || '未命名能力')}</strong>
        <span class="pill pill-${escapeHTML(lesson.status || 'pending')}">${escapeHTML(lesson.status || 'pending')}</span>
      </div>
      <p>${escapeHTML(lesson.pattern || lesson.summary || '')}</p>
      <p class="muted">${escapeHTML(lesson.source || 'unknown')} · ${escapeHTML((lesson.suggested_files || []).join(', '))}</p>
    </article>
  `).join('');
}

async function refreshRuns() {
  const data = await getJSON('/api/runs');
  document.getElementById('run-count').textContent = String(data.count || 0);
  document.getElementById('metric-runs').textContent = String(data.count || 0);
  const list = document.getElementById('run-list');
  const runs = data.runs || [];
  if (!runs.length) {
    list.innerHTML = '<div class="empty">还没有运行记录。</div>';
    return;
  }
  list.innerHTML = runs.slice().reverse().map((run) => `
    <article class="item">
      <div class="item-row">
        <strong>${escapeHTML(run.topic || run.goal || '自进化运行')}</strong>
        <span class="pill pill-${escapeHTML(run.status || 'unknown')}">${escapeHTML(run.status || 'unknown')}</span>
      </div>
      <p>${escapeHTML(run.goal || run.error || '')}</p>
      <p class="muted">${escapeHTML(run.target_file || run.timestamp || '')}</p>
    </article>
  `).join('');
}

async function refreshStatus() {
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
  const data = text ? JSON.parse(text) : {};
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
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) throw new Error(data.error || `${response.status} ${response.statusText}`);
  return data;
}

/* ================================================================
   UI State Helpers
   ================================================================ */

function setBusy(busy, label) {
  state.busy = busy;
  document.getElementById('run-state').textContent = label;
  ['run-btn', 'learn-btn', 'apply-btn'].forEach((id) => {
    document.getElementById(id).disabled = busy;
  });
}

function setChatBusy(busy) {
  state.chatBusy = busy;
  document.getElementById('send-chat-btn').disabled = busy;
  document.getElementById('chat-input').disabled = busy;
}

function setResult(content, tone) {
  const box = document.getElementById('result-box');
  box.textContent = content;
  box.dataset.tone = tone;
}

function setSyncState(label) {
  const pill = document.getElementById('sync-state');
  pill.textContent = label;
  pill.dataset.tone = label;
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

function addChatMessage(role, content) {
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
  return message;
}
