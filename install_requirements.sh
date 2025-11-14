#!/usr/bin/env bash
# 使用前若无执行权限，请运行：chmod +x install_requirements.sh
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "未找到可用的 Python，请先在系统中安装 Python3。"
    exit 1
  fi
fi

echo "==> 使用 $PYTHON_BIN 安装 Python 依赖 (requests / yt-dlp / openai-whisper / pyyaml / opencc-python-reimplemented)"
$PYTHON_BIN -m pip install --upgrade pip
$PYTHON_BIN -m pip install --upgrade requests yt-dlp openai-whisper pyyaml opencc-python-reimplemented

echo "==> 确认 ffmpeg 是否可用"
if command -v brew >/dev/null 2>&1; then
  brew install ffmpeg
else
  echo "⚠️ 未检测到 Homebrew，请手动安装 ffmpeg (https://ffmpeg.org)"
fi

echo "安装完成"
