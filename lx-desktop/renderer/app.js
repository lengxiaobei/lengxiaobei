// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', function() {
  // 初始化标签页切换
  initTabs();
  
  // 初始化对话功能
  initChat();
  
  // 初始化代码分析功能
  initAnalyze();
  
  // 初始化代码生成功能
  initGenerate();
  
  // 初始化架构优化功能
  initOptimize();
  
  // 初始化系统监控
  initMonitor();
});

// 初始化标签页切换
function initTabs() {
  const navItems = document.querySelectorAll('.nav-item');
  const tabContents = document.querySelectorAll('.tab-content');
  
  navItems.forEach(item => {
    item.addEventListener('click', function() {
      // 移除所有激活状态
      navItems.forEach(i => i.classList.remove('active'));
      tabContents.forEach(c => c.style.display = 'none');
      
      // 激活当前标签
      this.classList.add('active');
      const tabId = this.getAttribute('data-tab');
      document.getElementById(tabId).style.display = 'block';
    });
  });
}

// 初始化对话功能
function initChat() {
  const chatInput = document.getElementById('chat-input');
  const sendBtn = document.getElementById('send-btn');
  const chatContainer = document.getElementById('chat-container');
  
  // 发送按钮点击事件
  sendBtn.addEventListener('click', sendMessage);
  
  // 输入框回车事件
  chatInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
      sendMessage();
    }
  });
  
  function sendMessage() {
    const message = chatInput.value.trim();
    if (message) {
      // 添加用户消息
      addMessage('user', message);
      chatInput.value = '';
      
      // 模拟 AI 回复
      setTimeout(() => {
        addMessage('bot', `我收到了你的消息: ${message}`);
      }, 1000);
    }
  }
  
  function addMessage(type, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}-message`;
    messageDiv.innerHTML = `<p>${content}</p>`;
    chatContainer.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }
}

// 初始化代码分析功能
function initAnalyze() {
  const analyzeBtn = document.getElementById('analyze-btn');
  const analyzeFile = document.getElementById('analyze-file');
  const analyzeResult = document.getElementById('analyze-result');
  
  analyzeBtn.addEventListener('click', async function() {
    const file = analyzeFile.value.trim();
    if (file) {
      analyzeResult.innerHTML = '<div class="loading">分析中...</div>';
      
      try {
        const response = await electronAPI.sendMcpRequest({
          id: Date.now().toString(),
          method: 'analyzeCode',
          params: { file: file }
        });
        
        if (response.result && response.result.success) {
          const analysis = response.result.analysis;
          analyzeResult.innerHTML = `
            <div class="alert alert-success">分析成功</div>
            <div class="code-container">
              <pre>文件: ${analysis.file_path}<br>
行数: ${analysis.lines}<br>
函数数: ${analysis.functions}<br>
类数: ${analysis.classes}<br>
导入数: ${analysis.imports}<br>
潜在问题: ${analysis.potential_issues.join(', ')}
              </pre>
            </div>
          `;
        } else {
          analyzeResult.innerHTML = `<div class="alert alert-danger">分析失败: ${response.result.message}</div>`;
        }
      } catch (error) {
        analyzeResult.innerHTML = `<div class="alert alert-danger">错误: ${error.error}</div>`;
      }
    } else {
      analyzeResult.innerHTML = '<div class="alert alert-warning">请输入文件路径</div>';
    }
  });
}

// 初始化代码生成功能
function initGenerate() {
  const generateBtn = document.getElementById('generate-btn');
  const generatePrompt = document.getElementById('generate-prompt');
  const generateResult = document.getElementById('generate-result');
  
  generateBtn.addEventListener('click', async function() {
    const prompt = generatePrompt.value.trim();
    if (prompt) {
      generateResult.innerHTML = '<div class="loading">生成中...</div>';
      
      try {
        const response = await electronAPI.sendMcpRequest({
          id: Date.now().toString(),
          method: 'generateCode',
          params: { prompt: prompt }
        });
        
        if (response.result && response.result.success) {
          generateResult.innerHTML = `
            <div class="alert alert-success">生成成功</div>
            <div class="code-container">
              <pre>${response.result.code}</pre>
            </div>
          `;
        } else {
          generateResult.innerHTML = `<div class="alert alert-danger">生成失败: ${response.result.message}</div>`;
        }
      } catch (error) {
        generateResult.innerHTML = `<div class="alert alert-danger">错误: ${error.error}</div>`;
      }
    } else {
      generateResult.innerHTML = '<div class="alert alert-warning">请输入生成提示</div>';
    }
  });
}

// 初始化架构优化功能
function initOptimize() {
  const optimizeBtn = document.getElementById('optimize-btn');
  const optimizeProject = document.getElementById('optimize-project');
  const optimizeResult = document.getElementById('optimize-result');
  
  optimizeBtn.addEventListener('click', async function() {
    const project = optimizeProject.value.trim();
    if (project) {
      optimizeResult.innerHTML = '<div class="loading">优化中...</div>';
      
      try {
        const response = await electronAPI.sendMcpRequest({
          id: Date.now().toString(),
          method: 'optimizeArchitecture',
          params: { project: project }
        });
        
        if (response.result && response.result.success) {
          const recommendations = response.result.recommendations;
          let recommendationsHtml = '';
          recommendations.forEach((rec, index) => {
            recommendationsHtml += `<li>${rec}</li>`;
          });
          
          optimizeResult.innerHTML = `
            <div class="alert alert-success">优化成功</div>
            <div class="code-container">
              <h5>优化建议:</h5>
              <ul>${recommendationsHtml}</ul>
            </div>
          `;
        } else {
          optimizeResult.innerHTML = `<div class="alert alert-danger">优化失败: ${response.result.message}</div>`;
        }
      } catch (error) {
        optimizeResult.innerHTML = `<div class="alert alert-danger">错误: ${error.error}</div>`;
      }
    } else {
      optimizeResult.innerHTML = '<div class="alert alert-warning">请输入项目路径</div>';
    }
  });
}

// 初始化系统监控
function initMonitor() {
  const systemInfoDiv = document.getElementById('system-info');
  const mcpStatusDiv = document.getElementById('mcp-status');
  
  // 获取系统信息
  electronAPI.getSystemInfo().then(info => {
    systemInfoDiv.innerHTML = `
      <p>平台: ${info.platform}</p>
      <p>应用版本: ${info.version}</p>
      <p>Electron版本: ${info.electron}</p>
    `;
  });
  
  // 测试 MCP 服务器连接
  testMcpConnection();
  
  function testMcpConnection() {
    electronAPI.sendMcpRequest({
      id: Date.now().toString(),
      method: 'health'
    }).then(response => {
      if (response.result) {
        mcpStatusDiv.innerHTML = `<p class="text-success">✅ 连接正常</p>`;
      } else {
        mcpStatusDiv.innerHTML = `<p class="text-danger">❌ 连接失败</p>`;
      }
    }).catch(error => {
      mcpStatusDiv.innerHTML = `<p class="text-danger">❌ 连接失败: ${error.error}</p>`;
    });
  }
}
