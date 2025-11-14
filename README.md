# VideoScribe - 视频转录助手

**Bilibili / YouTube 字幕·文字稿提取工具**

输入单个 **B 站 BV 号 / 链接** 或 **YouTube 视频链接**，即可自动生成结构化 Markdown 文字稿；若不存在官方字幕，会自动调用 OpenAI Whisper 进行转录。支持：

- 命令行单视频处理
- Tkinter GUI
- 批量导出某个 UP / 频道的全部视频
- 结构化 Markdown（含 YAML Front Matter + 时间轴段落）+ 兼容 TXT 纯文本

---

## 1. 环境准备

- macOS / Linux（推荐 macOS）
- Python 3.x（可通过 `brew install python` 安装）
- pip 可用
- Homebrew（用于安装 `ffmpeg`）
- 终端执行：

```bash
chmod +x install_requirements.sh
./install_requirements.sh
```

脚本会自动：

- `pip install --upgrade requests yt-dlp openai-whisper pyyaml opencc-python-reimplemented`
- `brew install ffmpeg`

---

## 2. 输出目录 & 文件结构

所有结果统一写入 `~/ViedoTextDownload/`（或 `TRANSCRIBE_OUTPUT_DIR` 指定的路径），按平台 / 上传者 / 视频归档：

```
~/ViedoTextDownload/
  bilibili/
    Super产品林木/
      BV1ZqEEzyEC9_看了上百份入行AI产品的简历，就这个最好.md
      BV1ZqEEzyEC9_看了上百份入行AI产品的简历，就这个最好.txt  # 兼容 TXT

  youtube/
    Marques_Brownlee/
      dQw4w9WgXcQ_Never_Gonna_Give_You_Up.md
```
- 默认写入 `~/ViedoTextDownload`；若需自定义，可设置 `TRANSCRIBE_OUTPUT_DIR=/path/to/dir`（兼容旧变量 `BILI_OUTPUT_DIR`）
- B 站多 P 视频会自动拆成 `BVxxxx-P01_标题.md`、`BVxxxx-P02_标题.md` 等多个 Markdown
- 若检测到输入链接带有 B 站合集/收藏 ID，可自动批量导出整个合集（可在 CLI/GUI 勾选开关）
- 英文音频会强制优先 English 字幕；若无英文字幕则使用 Whisper 英语转录，不会翻译成中文；中文音频默认转换为简体中文
- 兼容 TXT 文件在生成后会被立即删除，仅 Markdown 会被保留，方便后续整理

- Markdown 包含 YAML Front Matter、元信息、摘要占位、按时间顺序的正文：

```markdown
---
platform: youtube
video_id: dQw4w9WgXcQ
title: Never Gonna Give You Up
uploader: Rick Astley
upload_date: "1987-10-25"
source: official_subtitle
language: "Chinese"
original_language: "English"
duration: "00:03:32"
tags: []
processed_at: "2025-11-13"
---

# Never Gonna Give You Up

## 元信息（Metadata）
...

## 文本正文（按时间顺序）

### [00:00:00 → 00:00:05]
We're no strangers to love
```

- 文稿默认转换为简体中文；若视频判断为英文或手动 `--lang en`，则保持英文
- Whisper 识别完成后立即清理音频文件，节省磁盘空间
- 默认输出根目录：`~/ViedoTextDownload`；如需自定义：`export TRANSCRIBE_OUTPUT_DIR=/my/path`（CLI/GUI/批处理均生效，兼容旧变量 `BILI_OUTPUT_DIR`）
- 若批量导出 B 站空间出现 “Request is rejected by server (352)” 提示，请将浏览器登录后的 Cookie 保存到 `bilibili_cookie.txt`，并设置 `export BILIBILI_COOKIE_FILE=/path/to/bilibili_cookie.txt`；YouTube 同理可使用 `YOUTUBE_COOKIE_FILE`

---

## 3. 命令行单视频

```bash
# 最简单：单个视频 + 默认 small + 自动语言
python bilibili_auto_transcribe.py https://www.bilibili.com/video/BV1xx411e7AS

# 指定模型 / 语言 / 是否连带合集
python bilibili_auto_transcribe.py https://youtu.be/dQw4w9WgXcQ medium --lang en
python bilibili_auto_transcribe.py BV1c4i9YQEX8 --include-collection
python bilibili_auto_transcribe.py BV1xx411e7AS --no-txt
```

- 第 1 个参数：BV 号 / B 站链接 / YouTube 链接
- 第 2 个参数（可选）：Whisper 模型，`tiny`/`base`/`small`/`medium`/`large`，默认 `small`
- `--lang {auto,zh,en}`：自动 / 强制中文 / 强制英文输出（会影响字幕优先级与 Whisper 语言）
- `--include-collection`：若 B 站链接包含合集/收藏/分集信息，将同批导出整个合集（自动跳过当前 BV 以外的其他 BV）
- `--no-txt`：仅输出 Markdown（默认自动生成兼容 TXT 后立即删除）
- 提取完成后会列出所有 Markdown（若你仍保留 TXT，会在同一目录）

---

## 4. GUI

```bash
python bilibili_gui_transcriber.py
```

**界面功能：**
- 输入框可粘贴单个 B 站 / YouTube 视频、UP 主主页、B 站合集/收藏夹链接
- "模式"提供：单个视频 / 创作者主页批量 / 合集/收藏夹批量，可一键切换
- 选择 Whisper 模型（默认 `small`）与"输出语言"：自动 / 仅中文 / 仅英文
- "单个视频"模式可勾选"自动检测合集/分 P"，适合一键导出 B 站英文合集或多 P 视频
- **并发控制**：批量模式支持设置并发数（1-8 线程）和启用/禁用开关，推荐 3-5 线程
- 点击"🚀 开始处理"即可，彩色日志实时输出处理进度
- 日志实时输出 【平台检测 / 字幕&Whisper / 进度】，完成后弹窗展示 Markdown / TXT 路径

**GUI v2.0 特性：**
- 🎨 现代化界面设计（800x550 可调整窗口）
- 🌈 彩色日志系统（成功/错误/警告/信息自动着色）
- 🔔 状态指示器（就绪/处理中/完成/失败）
- 💡 动态提示（根据模式自动更新使用建议）
- ⚡ 并发处理（批量模式支持多线程加速）

### 打包 macOS `.app`
1. `brew install python@3.12 python-tk@3.12`
2. `python3.12 -m venv .venv-py312 && .venv-py312/bin/pip install requests yt-dlp openai-whisper pyyaml opencc-python-reimplemented pyinstaller`
3. `chmod +x build_gui_app.sh && ./build_gui_app.sh`
4. 双击 `dist/BilibiliTextApp.app` 即可运行（首次需在“隐私与安全性”允许）

---

## 5. 批量导出创作者全部视频

```bash
python creator_batch_export.py <UP主页或频道主页链接> [--model small] [--limit 50] [--max-workers 3]
```

示例：

```bash
# 默认并发（3 线程）
python creator_batch_export.py https://space.bilibili.com/1234567

# 自定义并发数（推荐 3-5）
python creator_batch_export.py https://www.youtube.com/@MarquesBrownlee --model medium --max-workers 5

# 禁用并发（顺序处理）
python creator_batch_export.py https://www.bilibili.com/list/ml123456 --no-concurrent

# 完整配置
python creator_batch_export.py https://space.bilibili.com/123456 \
  --model medium \
  --max-workers 5 \
  --limit 20 \
  --lang auto
```

**功能特性：**
- 自动识别平台并获取全部视频列表，可通过 `--lang` 为整批指定输出语言偏好
- 支持 B 站合集/收藏夹链接（`list/ml...`、`list/series/...`），也可继续传入 UP 主主页
- **并发处理**：默认使用 3 线程并发，大幅提升批量处理速度（可通过 `--max-workers` 调整 1-8，或 `--no-concurrent` 禁用）
- 每个视频调用相同的单视频处理逻辑，错误自动跳过
- 控制台会实时输出 `✅ [3/42] 完成：xxx.md` 的并发进度
- 若遇 "Request is rejected by server (352)"，请将浏览器登录后的 Cookie 写入文本文件并设置 `BILIBILI_COOKIE_FILE=/path/to/file`（YouTube 使用 `YOUTUBE_COOKIE_FILE`）

**并发参数：**
- `--max-workers N`：设置并发线程数（1-8），默认 3
- `--no-concurrent`：禁用并发，使用顺序处理
- 推荐：`small` 模型用 3-5 线程，`large` 模型用 2-3 线程

---

## 6. 运行机制（概览）

1. B 站若检测到分 P，会逐 P 生成 Markdown；若链接携带合集/收藏 ID，可自动扩展至整个合集
2. 优先尝试官方字幕（B 站 JSON、YouTube `.vtt/.srt`），并根据语言偏好优先取英文或中文
3. 若字幕缺失，下载音频并用 Whisper 转录；中文模式自动转简体，英文模式保持英文
4. 生成 Markdown + 兼容 TXT（随后删除 TXT 与音频临时文件）

---

## 7. 常见问题

- `ModuleNotFoundError`：重新执行 `./install_requirements.sh`
- `yt-dlp` / `ffmpeg` 未找到：确认它们在 `PATH`，或通过 Homebrew 安装
- B 站接口异常：可能视频受限或网络波动，稍后重试
- Whisper 首次下载模型较慢，可提前执行 `python -m whisper --model small`

祝你使用愉快，欢迎扩展更多自动化工作流！ 🎉
