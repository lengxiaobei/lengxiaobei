#!/bin/bash
# 冷小北 Web 启动脚本 (Python-only)

set -e
cd "$(dirname "$0")"

echo "=== 冷小北 Web 启动 ==="
echo ""

if ! command -v python3 &> /dev/null; then
    echo "需要 Python 3.10+"
    exit 1
fi

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "虚拟环境已激活"
fi

if [ -f "requirements.txt" ]; then
    if ! python3 -c "import flask" 2>/dev/null; then
        echo "安装依赖..."
        pip install -r requirements.txt --quiet
    fi
fi

LX_WEB_HOST="${LX_WEB_HOST:-0.0.0.0}"
LX_WEB_PORT="${LX_WEB_PORT:-8088}"
export LX_WEB_HOST LX_WEB_PORT

echo "--- 系统诊断 ---"
python3 -m src.doctor --quick 2>/dev/null || echo "doctor 不可用，跳过"

echo ""
echo "--- 启动 Web 服务 ---"
echo "地址: http://127.0.0.1:${LX_WEB_PORT}"
python3 -m lx_web.app &
WEB_PID=$!

sleep 2

echo ""
echo "--- 健康检查 ---"
if curl -sf "http://127.0.0.1:${LX_WEB_PORT}/api/status" > /dev/null 2>&1; then
    echo "Web 健康检查通过 (端口 ${LX_WEB_PORT})"
else
    echo "Web 健康检查端点尚未就绪（服务可能仍在启动中）"
fi

echo ""
echo "=== 冷小北 Web 启动完成 ==="
echo "Web PID: $WEB_PID"
echo "Web: http://127.0.0.1:${LX_WEB_PORT}"
echo ""

trap "echo ''; echo '正在停止...'; kill $WEB_PID 2>/dev/null; exit 0" INT TERM
wait $WEB_PID
