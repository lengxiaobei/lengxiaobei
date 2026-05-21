const { contextBridge, ipcRenderer } = require('electron');

// 暴露安全的 API 到渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  // MCP 服务器通信
  sendMcpRequest: (request) => {
    return new Promise((resolve, reject) => {
      ipcRenderer.send('mcp-request', request);
      
      const responseHandler = (event, response) => {
        ipcRenderer.off('mcp-response', responseHandler);
        ipcRenderer.off('mcp-error', errorHandler);
        resolve(response);
      };
      
      const errorHandler = (event, error) => {
        ipcRenderer.off('mcp-response', responseHandler);
        ipcRenderer.off('mcp-error', errorHandler);
        reject(error);
      };
      
      ipcRenderer.on('mcp-response', responseHandler);
      ipcRenderer.on('mcp-error', errorHandler);
    });
  },
  
  // 系统信息
  getSystemInfo: () => {
    return new Promise((resolve) => {
      ipcRenderer.send('system-info');
      ipcRenderer.once('system-info-response', (event, info) => {
        resolve(info);
      });
    });
  }
});
