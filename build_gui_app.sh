#!/usr/bin/env bash
# 构建可双击运行的 GUI App（基于 PyInstaller）
set -euo pipefail

APP_NAME="${APP_NAME:-BilibiliTextApp}"

if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x ".venv-py312/bin/python" ]]; then
    PYTHON_BIN=".venv-py312/bin/python"
  elif command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="python3.12"
  else
    PYTHON_BIN="${PYTHON_BIN:-python3}"
  fi
fi

export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$PWD/.pyinstaller}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "未找到 Python，可通过设置 PYTHON_BIN=/path/to/python3 指定解释器"
  exit 1
fi

ADD_DATA_ARGS=()
WHISPER_ASSETS_DIR="$("$PYTHON_BIN" - <<'PY'
from pathlib import Path
try:
    import whisper
except Exception:
    print("")
else:
    path = Path(whisper.__file__).parent / "assets"
    print(path if path.exists() else "")
PY
)"
if [[ -n "$WHISPER_ASSETS_DIR" ]]; then
  ADD_DATA_ARGS+=(--add-data "${WHISPER_ASSETS_DIR}:whisper/assets")
else
  echo "⚠️ 未找到 whisper/assets 目录，打包后可能缺少模型资源"
fi

echo "==> 使用 $PYTHON_BIN 打包 GUI 到 dist/${APP_NAME}.app"
"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  "${ADD_DATA_ARGS[@]}" \
  bilibili_gui_transcriber.py

echo "✅ 打包完成，双击 dist/${APP_NAME}.app 即可运行图形界面"
