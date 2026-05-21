#!/bin/bash
# 冷小北 macOS 一键安装脚本
# ============================
# 用法: curl -fsSL https://raw.githubusercontent.com/lengxiaobei/lengxiaobei/main/install.sh | bash
# 或:   ./install.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.lengxiaobei.daemon.plist"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

echo ""
echo -e "${GREEN}🦞 冷小北 macOS 安装脚本${NC}"
echo "============================"
echo ""

# ---- 1. 检查 Python ----
echo -n "检查 Python 3.10+ ... "
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        ok=$("$cmd" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; echo $?)
        if [ "$ok" -eq 0 ]; then
            PYTHON="$cmd"
            echo -e "${GREEN}$($PYTHON --version 2>&1)${NC}"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "${RED}未找到 Python 3.10+。请先安装: brew install python3${NC}"
    exit 1
fi

# ---- 2. 虚拟环境 ----
echo -n "创建虚拟环境 ... "
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    "$PYTHON" -m venv "$PROJECT_ROOT/venv"
    echo -e "${GREEN}完成${NC}"
else
    echo -e "${GREEN}已存在${NC}"
fi

source "$PROJECT_ROOT/venv/bin/activate"
PIP="$PROJECT_ROOT/venv/bin/pip"

# ---- 3. 安装依赖 ----
echo "安装 Python 依赖 ..."
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet -e "$PROJECT_ROOT"
echo -e "${GREEN}依赖安装完成${NC}"

# ---- 4. 创建必要目录 ----
mkdir -p "$PROJECT_ROOT/memory"
mkdir -p "$PROJECT_ROOT/logs"
mkdir -p "$PROJECT_ROOT/assessment"
mkdir -p "$PROJECT_ROOT/learning"
echo -e "${GREEN}目录结构就绪${NC}"

# ---- 5. LLM 配置提示 ----
echo ""
echo -e "${YELLOW}--- LLM API Key 配置 ---${NC}"
OC_CONFIG="$HOME/.openclaw/openclaw.json"
if [ -f "$OC_CONFIG" ]; then
    echo -e "${GREEN}✅ 检测到 OpenClaw 配置，冷小北将自动读取 API Key${NC}"
else
    echo "冷小北需要至少一个 LLM provider 的 API Key 才能运行。"
    echo "支持的 provider: minimax / volcengine / bailian / anthropic"
    echo ""
    echo "配置方式: 创建 $OC_CONFIG，格式如下:"
    echo '{ "models": { "providers": { "minimax": { "apiKey": "sk-xxx" } } } }'
    echo ""
fi

# ---- 6. 安装 launchd 服务 ----
echo -e "${YELLOW}--- 安装后台服务 ---${NC}"
mkdir -p "$LAUNCH_AGENTS"

PLIST_SRC="$PROJECT_ROOT/$PLIST_NAME"
PLIST_DST="$LAUNCH_AGENTS/$PLIST_NAME"

if [ -f "$PLIST_SRC" ]; then
    # 替换路径占位符
    sed "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" "$PLIST_SRC" > "$PLIST_DST"
    echo -e "${GREEN}✅ plist 已安装到 $PLIST_DST${NC}"

    # 卸载旧版本（如果存在）
    launchctl unload "$PLIST_DST" 2>/dev/null || true

    # 加载
    launchctl load "$PLIST_DST"
    echo -e "${GREEN}✅ 后台服务已加载 (开机自启)${NC}"
else
    echo -e "${YELLOW}⚠️  plist 文件不存在，跳过后台服务安装${NC}"
fi

# ---- 7. 运行 onboard 引导 ----
echo ""
echo -e "${YELLOW}--- 运行安装引导 ---${NC}"
"$PROJECT_ROOT/venv/bin/python3" -m src.cli onboard

echo ""
echo -e "${GREEN}============================${NC}"
echo -e "${GREEN}🦞 冷小北安装完成！${NC}"
echo ""
echo "  守护进程状态: lx status"
echo "  系统诊断:     lx doctor"
echo "  查看日志:     tail -f $PROJECT_ROOT/logs/daemon.log"
echo ""
echo "  launchd 管理:"
echo "    停止: launchctl unload $PLIST_DST"
echo "    启动: launchctl load $PLIST_DST"
echo "    状态: launchctl list | grep lengxiaobei"
echo ""
