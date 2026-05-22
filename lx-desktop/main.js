const { app, BrowserWindow, ipcMain, session } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');

// 后端 API 地址（lx_web.py 默认端口 8088）
const API_BASE = process.env.LX_API_URL || 'http://localhost:8088';

// 全局变量
let mainWindow;
let backendProcess;

// 创建主窗口
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1000,
    height: 700,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    },
    title: '冷小北',
    icon: path.join(__dirname, 'assets', 'icon.png')
  });

  // 拦截 /api/* 请求，代理到后端 lx_web.py
  mainWindow.webContents.session.webRequest.onBeforeRequest(
    { urls: ['file:///api/*'] },
    (details, callback) => {
      const apiPath = new URL(details.url).pathname;
      proxyRequest(apiPath, details.method, details.uploadData)
        .then((result) => callback({ redirectURL: result }))
        .catch(() => callback({}));
    }
  );

  // 加载主界面 — 优先从后端加载（同源，API 直接可用）
  loadFrontend();

  // 开发模式下打开开发者工具
  if (process.argv.includes('--dev')) {
    mainWindow.webContents.openDevTools();
  }

  // 窗口关闭时的处理
  mainWindow.on('closed', function () {
    mainWindow = null;
  });
}

// 加载前端：优先从后端加载（API 同源可用），回退到本地文件
function loadFrontend() {
  const tryBackend = (timeoutMs = 3000) => {
    return new Promise((resolve, reject) => {
      const req = http.get(`${API_BASE}/`, (res) => {
        if (res.statusCode === 200) {
          resolve(true);
        } else {
          reject(new Error(`后端返回 ${res.statusCode}`));
        }
        res.resume();
      });
      req.on('error', reject);
      req.setTimeout(timeoutMs, () => { req.destroy(); reject(new Error('后端连接超时')); });
    });
  };

  const deadline = Date.now() + 25000;
  const waitForBackend = () => {
    tryBackend(1500).then(() => {
      console.log(`从后端加载前端: ${API_BASE}`);
      mainWindow.loadURL(`${API_BASE}/`);
    }).catch((error) => {
      if (Date.now() < deadline) {
        console.log(`等待后端启动: ${error.message}`);
        setTimeout(waitForBackend, 1000);
        return;
      }
      console.log('后端未启动，从本地文件加载（API 请求将通过 IPC 代理）');
      mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
    });
  };

  waitForBackend();
}

// 启动后端 lx_web.py
function startBackend() {
  const webPyPath = path.join(__dirname, '..', 'lx_web.py');

  if (fs.existsSync(webPyPath)) {
    const port = process.env.LX_WEB_PORT || '8088';
    backendProcess = spawn('python3', [webPyPath], {
      cwd: path.join(__dirname, '..'),
      env: { ...process.env, LX_WEB_PORT: port },
      stdio: ['pipe', 'pipe', 'pipe']
    });

    backendProcess.stdout.on('data', (data) => {
      console.log('[lx_web]', data.toString().trim());
    });

    backendProcess.stderr.on('data', (data) => {
      console.error('[lx_web err]', data.toString().trim());
    });

    backendProcess.on('close', (code) => {
      console.log(`lx_web.py 退出，code=${code}`);
      backendProcess = null;
    });

    console.log(`后端 lx_web.py 启动中 (端口 ${port})...`);
  } else {
    console.log('lx_web.py 不存在，跳过后端启动（请确保后端已手动运行）');
  }
}

// 停止后端
function stopBackend() {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
    console.log('后端已停止');
  }
}

// 代理 API 请求到后端（用于 file:// 模式下的回退）
async function proxyRequest(apiPath, method, uploadData) {
  return new Promise((resolve, reject) => {
    const url = new URL(apiPath, API_BASE);
    const options = {
      hostname: url.hostname,
      port: url.port,
      path: url.pathname + url.search,
      method: method,
      headers: { 'Content-Type': 'application/json' },
    };

    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => {
        // 返回 data: URL 让渲染进程拿到 JSON
        const dataUrl = `data:application/json;charset=utf-8,${encodeURIComponent(body)}`;
        resolve(dataUrl);
      });
    });

    req.on('error', reject);
    req.setTimeout(30000, () => { req.destroy(); reject(new Error('代理请求超时')); });

    if (uploadData && uploadData.length > 0) {
      const body = Buffer.concat(uploadData.map(d => d.bytes)).toString();
      req.write(body);
    }
    req.end();
  });
}

// 应用就绪时的处理
app.on('ready', () => {
  startBackend();
  // 等后端启动后再创建窗口
  setTimeout(createWindow, 2000);
});

// 所有窗口关闭时的处理
app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') {
    stopBackend();
    app.quit();
  }
});

// macOS 应用激活时的处理
app.on('activate', function () {
  if (mainWindow === null) {
    createWindow();
  }
});

// 应用退出时清理
app.on('before-quit', () => {
  stopBackend();
});

// 处理渲染进程的 API 请求（IPC 方式，用于 file:// 模式回退）
ipcMain.on('api-request', (event, { id, url, method, body }) => {
  const fullUrl = new URL(url, API_BASE);
  const options = {
    hostname: fullUrl.hostname,
    port: fullUrl.port,
    path: fullUrl.pathname + fullUrl.search,
    method: method || 'GET',
    headers: { 'Content-Type': 'application/json' },
  };

  const req = http.request(options, (res) => {
    let data = '';
    res.on('data', (chunk) => { data += chunk; });
    res.on('end', () => {
      event.reply(`api-response-${id}`, {
        status: res.statusCode,
        body: data,
      });
    });
  });

  req.on('error', (err) => {
    event.reply(`api-response-${id}`, {
      status: 0,
      body: JSON.stringify({ error: err.message }),
    });
  });

  req.setTimeout(30000, () => {
    req.destroy();
    event.reply(`api-response-${id}`, {
      status: 0,
      body: JSON.stringify({ error: '请求超时' }),
    });
  });

  if (body) req.write(JSON.stringify(body));
  req.end();
});

// 处理系统信息请求
ipcMain.on('system-info', (event) => {
  const systemInfo = {
    platform: process.platform,
    version: app.getVersion(),
    electron: process.versions.electron,
    apiBase: API_BASE,
  };
  event.reply('system-info-response', systemInfo);
});
