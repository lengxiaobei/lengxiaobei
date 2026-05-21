#!/bin/bash
# 冷小北 — Rust 控制层/记忆层 (LEGACY — 已废弃)
# ==================================================
# Rust control_layer + memory_layer 已被 Python HybridMemory + MemoryTree 替代。
# 此脚本仅保留用于实验目的，不建议在生产中使用。
#
# 主启动方式: ./start.sh (Python-only)

set -e
cd "$(dirname "$0")"

echo "⚠️  此脚本使用已废弃的 Rust 控制层/记忆层"
echo "   推荐使用 ./start.sh 启动 Python 核心"
echo ""

# 编译
echo "--- 编译 Rust ---"
if [ -d "control_layer" ]; then
    (cd control_layer && cargo build --release 2>/dev/null) && echo "✅ control_layer" || echo "⚠️  control_layer 编译失败"
fi
if [ -d "memory_layer" ]; then
    (cd memory_layer && cargo build --release 2>/dev/null) && echo "✅ memory_layer" || echo "⚠️  memory_layer 编译失败"
fi

echo ""
echo "--- 启动 Rust 服务 ---"

if [ -f "memory_layer/target/release/memory_layer" ]; then
    memory_layer/target/release/memory_layer &
    MEM_PID=$!
    echo "✅ memory_layer PID=$MEM_PID (端口 8081)"
fi

if [ -f "control_layer/target/release/control_layer" ]; then
    control_layer/target/release/control_layer &
    CTRL_PID=$!
    echo "✅ control_layer PID=$CTRL_PID (端口 8082)"
fi

echo ""
echo "服务已启动。按 Ctrl+C 停止。"
trap "kill $MEM_PID $CTRL_PID 2>/dev/null; exit 0" INT TERM
wait