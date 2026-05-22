const { contextBridge, ipcRenderer } = require('electron');

const API_TIMEOUT = 30000;
const API_BASE = 'http://127.0.0.1:8088';
let requestIdCounter = 0;

// 检测当前是否运行在 http:// 环境（后端同源模式）
function isBackendMode() {
  return typeof window !== 'undefined' && window.location.protocol === 'http:';
}

// 暴露安全的 API 到渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  // 检测运行模式
  isBackendMode: () => isBackendMode(),
  getAPIBase: () => API_BASE,

  // API 请求：后端模式下直接 fetch，file:// 模式下走 IPC 代理
  apiRequest: (url, options = {}) => {
    if (isBackendMode()) {
      // 后端同源模式，直接 fetch
      return fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {}),
        },
      }).then(async (res) => {
        const text = await res.text();
        const data = text ? JSON.parse(text) : {};
        if (!res.ok) throw new Error(data.error || `${res.status} ${res.statusText}`);
        return data;
      });
    }

    // file:// 模式，走 IPC 代理
    return new Promise((resolve, reject) => {
      const id = ++requestIdCounter;
      const timer = setTimeout(() => {
        ipcRenderer.off(`api-response-${id}`, handler);
        reject(new Error('API 请求超时'));
      }, API_TIMEOUT);

      const handler = (_event, response) => {
        clearTimeout(timer);
        try {
          const data = JSON.parse(response.body);
          if (response.status >= 400 || (data.error && response.status === 0)) {
            reject(new Error(data.error || `请求失败 (${response.status})`));
          } else {
            resolve(data);
          }
        } catch (e) {
          reject(new Error(`响应解析失败: ${e.message}`));
        }
      };

      ipcRenderer.once(`api-response-${id}`, handler);
      ipcRenderer.send('api-request', {
        id,
        url,
        method: options.method || 'GET',
        body: options.body ? JSON.parse(options.body) : undefined,
      });
    });
  },

  // 系统信息
  getSystemInfo: () => {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        ipcRenderer.off('system-info-response', handler);
        reject(new Error('获取系统信息超时'));
      }, 5000);

      const handler = (_event, info) => {
        clearTimeout(timer);
        resolve(info);
      };

      ipcRenderer.once('system-info-response', handler);
      ipcRenderer.send('system-info');
    });
  }
});
