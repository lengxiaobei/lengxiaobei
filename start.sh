#!/bin/bash
# 冷小北启动脚本 (Python-only)
# Rust control_layer / memory_layer 已降级为可选，见 legacy_start_rust.sh

set -e
cd "$(dirname "$0")"

echo "=== 冷小北启动 ==="
echo ""

# ---- Python 环境 ----
if ! command -v python3 &> /dev/null; then
    echo "❌ 需要 Python 3.10+"
    exit 1
fi

PYTHON=$(command -v python3)

# 虚拟环境 (可选)
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "✅ 虚拟环境已激活"
fi

# 依赖检查
if [ -f "requirements.txt" ]; then
    if ! python3 -c "import yaml" 2>/dev/null; then
        echo "⚠️  安装依赖..."
        pip install -r requirements.txt --quiet
    fi
fi

echo "✅ Python 环境就绪"
echo ""

# ---- 运行诊断 ----
echo "--- 系统诊断 ---"
python3 -m src.doctor --quick 2>/dev/null || echo "⚠️  doctor 不可用，跳过"

# ---- 启动核心 ----
echo ""
echo "--- 启动冷小北核心 ---"
python3 -m src.core &
CORE_PID=$!
sleep 2

# ---- 健康检查 ----
echo ""
echo "--- 健康检查 ---"
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ 核心健康检查通过 (端口 8000)"
else
    echo "⚠️  健康检查端点尚未就绪（核心可能在启动中）"
fi

echo ""
echo "=== 冷小北启动完成 ==="
echo "核心 PID: $CORE_PID"
echo "健康检查: http://localhost:8000/health"
echo ""

trap "echo ''; echo '正在停止...'; kill $CORE_PID 2>/dev/null; exit 0" INT TERM
wait $CORE_PID