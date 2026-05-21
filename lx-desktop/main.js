const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

// 全局变量
let mainWindow;
let mcpServer;

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

  // 加载主界面
  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  // 开发模式下打开开发者工具
  if (process.argv.includes('--dev')) {
    mainWindow.webContents.openDevTools();
  }

  // 窗口关闭时的处理
  mainWindow.on('closed', function () {
    mainWindow = null;
  });
}

// 启动 MCP 服务器
function startMcpServer() {
  const mcpServerPath = path.join(__dirname, '..', 'src', 'mcp_server.py');
  
  if (fs.existsSync(mcpServerPath)) {
    mcpServer = spawn('python3', [mcpServerPath], {
      stdio: ['pipe', 'pipe', 'pipe']
    });

    mcpServer.stdout.on('data', (data) => {
      console.log('MCP Server:', data.toString());
    });

    mcpServer.stderr.on('data', (data) => {
      console.error('MCP Server Error:', data.toString());
    });

    mcpServer.on('close', (code) => {
      console.log(`MCP Server exited with code ${code}`);
    });

    console.log('MCP Server started');
  } else {
    console.error('MCP Server not found at:', mcpServerPath);
  }
}

// 停止 MCP 服务器
function stopMcpServer() {
  if (mcpServer) {
    mcpServer.kill();
    mcpServer = null;
    console.log('MCP Server stopped');
  }
}

// 应用就绪时的处理
app.on('ready', () => {
  createWindow();
  startMcpServer();
});

// 所有窗口关闭时的处理
app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') {
    stopMcpServer();
    app.quit();
  }
});

// macOS 应用激活时的处理
app.on('activate', function () {
  if (mainWindow === null) {
    createWindow();
  }
});

// 处理渲染进程的请求
ipcMain.on('mcp-request', (event, request) => {
  if (mcpServer) {
    // 发送请求到 MCP 服务器
    mcpServer.stdin.write(JSON.stringify(request) + '\n');
    
    // 读取响应
    let response = '';
    const responseHandler = (data) => {
      response += data.toString();
      if (response.includes('\n')) {
        mcpServer.stdout.off('data', responseHandler);
        try {
          const parsedResponse = JSON.parse(response.trim());
          event.reply('mcp-response', parsedResponse);
        } catch (error) {
          event.reply('mcp-error', { error: 'Failed to parse response' });
        }
      }
    };
    
    mcpServer.stdout.on('data', responseHandler);
  } else {
    event.reply('mcp-error', { error: 'MCP Server not running' });
  }
});

// 处理系统信息请求
ipcMain.on('system-info', (event) => {
  const systemInfo = {
    platform: process.platform,
    version: app.getVersion(),
    electron: process.versions.electron
  };
  event.reply('system-info-response', systemInfo);
});
