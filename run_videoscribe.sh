#!/bin/bash
# VideoScribe GUI 启动脚本

# 进入项目目录
cd "$(dirname "$0")"

# 优先使用虚拟环境，否则尝试 Python 3.12，最后使用系统 Python
if [ -f ".venv-py312/bin/python3" ]; then
    PYTHON=".venv-py312/bin/python3"
    echo "🐍 使用虚拟环境: .venv-py312"
elif command -v python3.12 &> /dev/null; then
    PYTHON="python3.12"
    echo "🐍 使用 Python 3.12"
else
    PYTHON="python3"
    echo "🐍 使用系统 Python"
fi

# 检查依赖
$PYTHON -c "import requests" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ 错误：缺少依赖包"
    echo "请运行: ./install_requirements.sh"
    exit 1
fi

# 启动 GUI
echo "🚀 正在启动 VideoScribe..."
$PYTHON bilibili_gui_transcriber.py

# 如果程序异常退出，保持终端打开
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ VideoScribe 异常退出"
    echo "按任意键关闭..."
    read -n 1
fi
