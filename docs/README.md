# 冷小北 · Leng Xiaobei

数字生命体 — 自演化 AI Agent。轻内核、强治理、可插拔能力、主动记忆。

## 快速安装 (macOS)

```bash
git clone https://github.com/lengxiaobei/lengxiaobei.git
cd lengxiaobei
./install.sh
```

安装脚本会自动：创建虚拟环境 → 安装依赖 → 配置 launchd 开机自启 → 运行 `lx onboard` 引导。

## 使用

```bash
lx doctor           # 系统诊断
lx onboard          # 首次安装引导
lx daemon           # 启动守护进程 (后台常驻)
lx status           # 查看运行状态
lx version          # 版本信息
```

守护进程启动后：
- 健康检查: http://localhost:8000/health
- 日志: `tail -f logs/daemon.log`

launchd 管理:
```bash
launchctl unload ~/Library/LaunchAgents/com.lengxiaobei.daemon.plist  # 停止
launchctl load ~/Library/LaunchAgents/com.lengxiaobei.daemon.plist    # 启动
```

## 架构

```
lengxiaobei/
├── src/
│   ├── core.py              # 核心引擎 — 四 Facade 编排
│   ├── facade_memory.py     # MemoryFacade
│   ├── facade_reasoning.py  # ReasoningFacade
│   ├── facade_evolution.py  # EvolutionFacade
│   ├── facade_guardian.py   # GuardianFacade
│   ├── llm.py               # 多 provider 模型路由
│   ├── memory.py            # SQLite 记忆系统
│   ├── memory_tree.py       # 四层记忆树
│   ├── hybrid_memory.py     # SQLite + FAISS 混合记忆
│   ├── constitution.py      # 宪法治理
│   ├── cli.py               # CLI 入口 (lx 命令)
│   ├── doctor.py            # 系统诊断
│   ├── evolution/           # 进化引擎 (audit + curator + proposer + executor + verifier)
│   ├── kairos/              # KAIROS 守护 (heartbeat + events + scheduler + monitor + decision)
│   └── mcp/                 # MCP 协议支持
├── docs/                    # 设计文档
├── memory/                  # 记忆数据
├── install.sh               # macOS 一键安装
├── pyproject.toml           # Python 包配置
└── com.lengxiaobei.daemon.plist  # macOS launchd 服务
```

## LLM 配置

冷小北自动从 `~/.openclaw/openclaw.json` 读取 API Key。支持的 provider：

| Provider | 模型示例 |
|---|---|
| minimax | MiniMax-M2.7 |
| volcengine | doubao-seed-2.0-pro, deepseek-v3.2, ark-code-latest |
| bailian | qwen3.5-plus, qwen3-coder-plus, kimi-k2.5 |
| anthropic | claude-3-opus/sonnet/haiku |

配置格式 (`~/.openclaw/openclaw.json`):
```json
{
  "models": {
    "providers": {
      "minimax": {"apiKey": "sk-xxx"},
      "volcengine": {"apiKey": "xxx"}
    }
  }
}
```

运行 `lx doctor` 可检查各 provider 的 Key 是否就绪。

## 开发

```bash
pip install -e ".[dev]"     # 安装含开发依赖
pytest tests/ -q             # 运行测试
ruff check src/ tests/       # lint
```

## 项目理念

克制、诚实、简洁。宪法为本，代码为用。

详细设计方向见 [DESIGN_ROADMAP.md](DESIGN_ROADMAP.md)。