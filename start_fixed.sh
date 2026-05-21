#!/bin/bash
# 冷小北修复启动脚本

cd "$(dirname "$0")"

echo "=== 冷小北修复启动脚本 ==="
echo ""

# 停止现有进程
echo "停止现有进程..."
pkill -f "control_layer" 2>/dev/null
pkill -f "memory_layer" 2>/dev/null
pkill -f "python3.*src.core" 2>/dev/null

sleep 2

# 检查端口占用
echo "检查端口占用..."
if lsof -i :8080 > /dev/null 2>&1; then
    echo "⚠️  端口8080被占用，正在清理..."
    lsof -ti :8080 | xargs kill -9 2>/dev/null
fi

if lsof -i :8081 > /dev/null 2>&1; then
    echo "⚠️  端口8081被占用，正在清理..."
    lsof -ti :8081 | xargs kill -9 2>/dev/null
fi

if lsof -i :8082 > /dev/null 2>&1; then
    echo "⚠️  端口8082被占用，正在清理..."
    lsof -ti :8082 | xargs kill -9 2>/dev/null
fi

sleep 2

# 启动记忆层
echo ""
echo "=== 启动记忆层 (端口8081) ==="
cd memory_layer
if [ -f "target/debug/memory_layer" ]; then
    target/debug/memory_layer > /tmp/memory_layer.log 2>&1 &
    MEMORY_PID=$!
    echo "✅ 记忆层启动成功，PID: $MEMORY_PID"
else
    echo "❌ 记忆层二进制文件不存在"
    exit 1
fi
cd ..

sleep 3

# 检查记忆层是否启动成功
if curl -s -X POST http://localhost:8081/api/memory/search -H 'Content-Type: application/json' -d '{"query":"test","limit":1}' > /dev/null 2>&1; then
    echo "✅ 记忆层健康检查通过"
else
    echo "❌ 记忆层健康检查失败"
    echo "查看日志: tail -f /tmp/memory_layer.log"
    exit 1
fi

# 启动控制层
echo ""
echo "=== 启动控制层 (端口8082) ==="
cd control_layer
if [ -f "target/debug/control_layer" ]; then
    target/debug/control_layer > /tmp/control_layer.log 2>&1 &
    CONTROL_PID=$!
    echo "✅ 控制层启动成功，PID: $CONTROL_PID"
else
    echo "❌ 控制层二进制文件不存在"
    exit 1
fi
cd ..

sleep 3

# 检查控制层是否启动成功
if curl -s http://localhost:8082/api/status > /dev/null 2>&1; then
    echo "✅ 控制层健康检查通过"
else
    echo "❌ 控制层健康检查失败"
    echo "查看日志: tail -f /tmp/control_layer.log"
    exit 1
fi

# Python核心由控制层自动管理，无需单独启动
# 如需独立运行核心: python3 -m src.core
if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo ""
echo "=== 系统状态检查 ==="
echo "1. 记忆层: http://localhost:8081/api/memory/search"
curl -s -X POST http://localhost:8081/api/memory/search -H 'Content-Type: application/json' -d '{"query":"test","limit":1}' | python3 -m json.tool 2>/dev/null || echo "无法获取记忆层状态"

echo ""
echo "2. 控制层: http://localhost:8082/api/status"
curl -s http://localhost:8082/api/status | python3 -m json.tool 2>/dev/null || echo "无法获取控制层状态"

echo ""
echo "=== 冷小北修复启动完成 ==="
echo "记忆层 PID: $MEMORY_PID (端口: 8081)"
echo "控制层 PID: $CONTROL_PID (端口: 8082, 管理Python核心)"
echo ""
echo "日志文件:"
echo "  - 记忆层: /tmp/memory_layer.log"
echo "  - 控制层: /tmp/control_layer.log"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 等待中断信号
trap "echo ''; echo '正在停止服务...'; kill $MEMORY_PID $CONTROL_PID 2>/dev/null; exit 0" INT TERM

wait