#!/bin/bash
# 冷小北统一启动脚本

# 进入项目根目录
cd "$(dirname "$0")"

echo "=== 冷小北启动脚本 ==="
echo ""

# 检查Rust是否安装
if ! command -v rustc &> /dev/null; then
    echo "❌ Rust未安装，请先安装Rust"
    echo "   安装命令: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    exit 1
fi

# 检查Python是否安装
if ! command -v python3 &> /dev/null; then
    echo "❌ Python未安装，请先安装Python 3.10+"
    exit 1
fi

# 检查依赖
if [ ! -d "venv" ]; then
    echo "⚠️ 虚拟环境未创建，正在创建..."
    python3 -m venv venv
    echo "✅ 虚拟环境创建成功"
fi

# 激活虚拟环境
echo "激活虚拟环境..."
source venv/bin/activate

# 安装Python依赖
echo "安装Python依赖..."
pip install -r requirements.txt

# 编译控制层
echo ""
echo "=== 编译控制层 ==="
cd control_layer
cargo build
if [ $? -eq 0 ]; then
    echo "✅ 控制层编译成功"
else
    echo "❌ 控制层编译失败"
    exit 1
fi
cd ..

# 编译记忆层
echo ""
echo "=== 编译记忆层 ==="
cd memory_layer
cargo build
if [ $? -eq 0 ]; then
    echo "✅ 记忆层编译成功"
else
    echo "❌ 记忆层编译失败"
    exit 1
fi
cd ..

# 启动控制层
echo ""
echo "=== 启动控制层 ==="
cd control_layer
target/debug/control_layer &
CONTROL_PID=$!
cd ..

# 等待控制层启动
sleep 2

# 启动记忆层
echo ""
echo "=== 启动记忆层 ==="
cd memory_layer
target/debug/memory_layer &
MEMORY_PID=$!
cd ..

# 等待记忆层启动
sleep 2

# 核心层由 Rust 控制层自动管理，无需单独启动
# 控制层会自动启动并监控 python3 -m src 进程

# 启动Web界面
echo ""
echo "=== 启动Web界面 ==="
if [ -f "lx_web.py" ]; then
    python3 lx_web.py &
    WEB_PID=$!
else
    echo "⚠️  lx_web.py 不存在，跳过Web界面启动"
    WEB_PID=""
fi

# 等待Web界面启动
sleep 2

echo ""
echo "=== 冷小北启动完成 ==="
echo "控制层 PID: $CONTROL_PID (管理核心层)"
echo "记忆层 PID: $MEMORY_PID"
echo "Web界面 PID: $WEB_PID"
echo ""
echo "控制层服务: http://localhost:8082"
echo "记忆层服务: http://localhost:8081"
echo "Web界面: http://localhost:5001"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 等待所有进程结束
wait $CONTROL_PID $MEMORY_PID ${WEB_PID:+"$WEB_PID"}
