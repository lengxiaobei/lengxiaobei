const state = {
  view: 'evolve',
  busy: false,
};

const titles = {
  evolve: ['自进化控制台', '学习其他 Agent 的长处，转成一次小步源码改进。'],
  lessons: ['Lessons', '查看已沉淀的 Agent 能力经验。'],
  runs: ['Runs', '查看每次自进化运行记录和结果。'],
  status: ['系统状态', '查看 Web、核心和健康检查状态。'],
};

document.addEventListener('DOMContentLoaded', () => {
  bindNavigation();
  bindActions();
  refreshAll();
});

function bindNavigation() {
  document.querySelectorAll('.nav-btn').forEach((button) => {
    button.addEventListener('click', () => {
      setView(button.dataset.view);
    });
  });

  document.getElementById('refresh-btn').addEventListener('click', refreshAll);
}

function bindActions() {
  document.getElementById('run-btn').addEventListener('click', () => runSelfEvolution(false));
  document.getElementById('learn-btn').addEventListener('click', learnOnly);
  document.getElementById('apply-btn').addEventListener('click', () => runSelfEvolution(true));
}

function setView(view) {
  state.view = view;
  document.querySelectorAll('.nav-btn').forEach((button) => {
    button.classList.toggle('active', button.dataset.view === view);
  });
  document.querySelectorAll('.view').forEach((section) => {
    section.classList.toggle('active', section.id === view);
  });
  const [title, subtitle] = titles[view] || titles.evolve;
  document.getElementById('view-title').textContent = title;
  document.getElementById('view-subtitle').textContent = subtitle;
  refreshAll();
}

async function runSelfEvolution(applyPending) {
  const topic = document.getElementById('topic').value.trim();
  const url = document.getElementById('url').value.trim();

  if (!applyPending && !topic) {
    setResult('请输入学习方向。', 'warn');
    return;
  }

  setBusy(true, applyPending ? 'applying pending' : 'running');
  try {
    const data = await postJSON('/api/self-evolve', {
      topic,
      url,
      apply_pending: applyPending,
    });
    setResult(JSON.stringify(data.result || data, null, 2), data.status === 'ok' ? 'ok' : 'warn');
    await refreshAll();
  } catch (error) {
    setResult(error.message, 'error');
  } finally {
    setBusy(false, 'idle');
  }
}

async function learnOnly() {
  const topic = document.getElementById('topic').value.trim();
  const url = document.getElementById('url').value.trim();

  if (!topic) {
    setResult('请输入学习方向。', 'warn');
    return;
  }

  setBusy(true, 'learning');
  try {
    const data = await postJSON('/api/learn-agent', { topic, url });
    setResult(JSON.stringify(data.lesson || data, null, 2), data.status === 'ok' ? 'ok' : 'warn');
    await refreshLessons();
  } catch (error) {
    setResult(error.message, 'error');
  } finally {
    setBusy(false, 'idle');
  }
}

async function refreshAll() {
  await Promise.allSettled([
    refreshLessons(),
    refreshRuns(),
    refreshStatus(),
  ]);
}

async function refreshLessons() {
  const data = await getJSON('/api/lessons');
  document.getElementById('lesson-count').textContent = String(data.count || 0);
  const list = document.getElementById('lesson-list');
  const lessons = data.lessons || [];
  if (!lessons.length) {
    list.innerHTML = '<div class="empty">还没有 lesson。</div>';
    return;
  }
  list.innerHTML = lessons.slice().reverse().map((lesson) => `
    <article class="item">
      <div class="item-row">
        <strong>${escapeHTML(lesson.capability || lesson.topic || '未命名能力')}</strong>
        <span class="pill">${escapeHTML(lesson.status || 'pending')}</span>
      </div>
      <p>${escapeHTML(lesson.pattern || '')}</p>
      <p class="muted">${escapeHTML(lesson.source || 'unknown')} · ${escapeHTML((lesson.suggested_files || []).join(', '))}</p>
    </article>
  `).join('');
}

async function refreshRuns() {
  const data = await getJSON('/api/runs');
  document.getElementById('run-count').textContent = String(data.count || 0);
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
        <span class="pill">${escapeHTML(run.status || 'unknown')}</span>
      </div>
      <p>${escapeHTML(run.goal || '')}</p>
      <p class="muted">${escapeHTML(run.target_file || '')}</p>
    </article>
  `).join('');
}

async function refreshStatus() {
  try {
    const [status, health] = await Promise.all([
      getJSON('/api/status'),
      getJSON('/api/health'),
    ]);
    document.getElementById('status-box').textContent = JSON.stringify(status, null, 2);
    document.getElementById('health-box').textContent = JSON.stringify(health, null, 2);
  } catch (error) {
    document.getElementById('health-box').textContent = error.message;
  }
}

async function getJSON(url) {
  const response = await fetch(url);
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data.error || `${response.status} ${response.statusText}`);
  }
  return data;
}

async function postJSON(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data.error || `${response.status} ${response.statusText}`);
  }
  return data;
}

function setBusy(busy, label) {
  state.busy = busy;
  document.getElementById('run-state').textContent = label;
  ['run-btn', 'learn-btn', 'apply-btn'].forEach((id) => {
    document.getElementById(id).disabled = busy;
  });
}

function setResult(content, tone) {
  const box = document.getElementById('result-box');
  box.textContent = content;
  box.dataset.tone = tone;
}

function escapeHTML(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}
