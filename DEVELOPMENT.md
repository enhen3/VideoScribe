# VideoScribe 开发者指南

> 快速上手开发文档 - 让你在5分钟内熟悉项目

## 📋 项目概览

**VideoScribe** 是一个 AI 驱动的视频转录工具，支持 Bilibili 和 YouTube 双平台。

- **语言**: Python 3.x
- **核心技术**: OpenAI Whisper, yt-dlp, Tkinter
- **版本**: v2.0
- **许可证**: MIT

---

## 🏗️ 项目架构

```
VideoScribe/
├── utils.py                         # ⭐ 核心引擎（1500+ 行）
├── bilibili_gui_transcriber.py     # 🖥️ GUI 应用（430 行）
├── bilibili_auto_transcribe.py     # 📟 CLI 单视频（90 行）
├── creator_batch_export.py         # 📦 CLI 批量导出（78 行）
├── install_requirements.sh         # 📦 依赖安装脚本
└── build_gui_app.sh                # 🔨 macOS App 打包脚本
```

### 核心模块 (utils.py)

**关键功能模块：**

| 功能 | 函数/类 | 行号参考 |
|------|---------|---------|
| 平台检测 | `detect_platform()` | ~230 |
| B站视频信息 | `_fetch_bilibili_view()` | ~350 |
| YouTube信息 | `_fetch_youtube_metadata()` | ~450 |
| 字幕下载 | `_download_bilibili_subtitle()` | ~550 |
| Whisper转录 | `_transcribe_with_whisper()` | ~750 |
| Markdown生成 | `_write_markdown()` | ~950 |
| 并发处理 | `_process_video_batch()` | ~1300 |
| B站视频处理 | `process_bilibili_video()` | ~1100 |
| YouTube处理 | `process_youtube_video()` | ~1200 |

**并发处理架构：**
- `_ThreadSafeLogger`: 线程安全日志类 (1244行)
- `_process_single_video()`: 单视频处理包装器 (1257行)
- `_process_video_batch()`: 批量并发调度 (1300行)
- 默认3线程，可配置1-8

---

## 🚀 快速开始

### 1. 克隆并设置环境

```bash
cd ~/VideoScribe
./install_requirements.sh

# 或手动安装
pip install requests yt-dlp openai-whisper pyyaml opencc-python-reimplemented
brew install ffmpeg
```

### 2. 测试各个入口

```bash
# GUI 测试
python3 bilibili_gui_transcriber.py

# CLI 单视频测试
python3 bilibili_auto_transcribe.py BV1xx411e7AS

# 批量测试
python3 creator_batch_export.py https://space.bilibili.com/123456 --limit 3
```

### 3. 打包 macOS App

```bash
# 确保有 Python 3.12
brew install python@3.12 python-tk@3.12

# 创建虚拟环境并安装依赖
python3.12 -m venv .venv-py312
.venv-py312/bin/pip install requests yt-dlp openai-whisper pyyaml opencc-python-reimplemented pyinstaller

# 打包
chmod +x build_gui_app.sh
./build_gui_app.sh

# 运行
open dist/VideoScribeApp.app
```

---

## 🔧 常用开发命令

### Git 操作

```bash
# 查看状态
git status

# 提交代码
git add .
git commit -m "feat: 添加新功能"
git push origin main

# 创建标签
git tag -a v2.1 -m "发布说明"
git push origin v2.1

# 查看日志
git log --oneline
```

### 测试功能

```bash
# 测试单个 B 站视频
python3 bilibili_auto_transcribe.py BV1ZqEEzyEC9

# 测试 YouTube 视频
python3 bilibili_auto_transcribe.py https://youtu.be/dQw4w9WgXcQ

# 测试多P视频
python3 bilibili_auto_transcribe.py BV1qkHrzHEh4

# 测试批量（限制3个）
python3 creator_batch_export.py https://space.bilibili.com/123456 --limit 3

# 测试并发
python3 creator_batch_export.py <链接> --max-workers 5
```

### 清理和重置

```bash
# 清理构建产物
rm -rf build/ dist/ .venv-py312/ *.spec

# 清理 Python 缓存
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null

# 清理临时文件
rm -f BV*.txt BV*.mp3 BV*.m4a

# 重新安装依赖
./install_requirements.sh
```

---

## 📁 输出目录

默认输出目录：`~/ViedoTextDownload/`

```
~/ViedoTextDownload/
├── bilibili/
│   └── <UP主名>/
│       ├── BVxxxx_视频标题.md
│       └── BVxxxx-P01_分P标题.md
└── youtube/
    └── <频道名>/
        └── videoID_标题.md
```

**自定义输出目录：**
```bash
export TRANSCRIBE_OUTPUT_DIR=/path/to/output
```

---

## 🐛 常见问题和解决方案

### 1. GUI 不显示最新代码

**问题**: 修改了 `utils.py`，但 GUI 运行的还是旧代码

**原因**: Python 模块缓存

**解决**:
```bash
# 重启 GUI 进程
pkill -f "python.*bilibili_gui"
python3 bilibili_gui_transcriber.py
```

### 2. Whisper 下载慢

**问题**: 首次使用 Whisper 下载模型很慢

**解决**:
```bash
# 提前下载模型
python3 -m whisper --model small
```

模型存储位置: `~/.cache/whisper/`

### 3. B站接口 352 错误

**问题**: `Request is rejected by server (352)`

**解决**:
```bash
# 1. 导出浏览器 Cookie 到文本文件
# 2. 设置环境变量
export BILIBILI_COOKIE_FILE=/path/to/bilibili_cookie.txt
```

### 4. 并发处理报错

**问题**: 多线程处理时日志混乱或出错

**解决**: 检查 `_ThreadSafeLogger` 是否正确使用 Lock

### 5. macOS .app 打包问题 (Tcl/Tk 9.0.3 兼容性)

**问题**: 打包的 VideoScribeApp.app 无法运行，报错：
```
cannot use non-numeric floating-point value "NaN" as left operand of "*"
```

**原因**:
- Homebrew 在 2025-11-13 自动升级 Tcl/Tk 从 8.6 → 9.0.3
- PyInstaller 6.16.0 不完全支持 Tcl/Tk 9.0.3
- 存在已知的 NaN 缩放计算 Bug

**解决方案**:

**方案1: 使用 run_videoscribe.sh 脚本（推荐）**
```bash
# 直接运行脚本（无需打包）
./run_videoscribe.sh

# 或在 Finder 中双击 run_videoscribe.sh
```

**方案2: 等待上游修复（未来）**
- 等待 PyInstaller 完全支持 Tcl/Tk 9.0
- 或等待 Homebrew Tcl/Tk 9.0.3 修复 NaN bug

**方案3: 使用不同的打包工具（高级）**
```bash
# 尝试使用 py2app (macOS 专用)
pip install py2app
# 需要重写 setup.py 脚本
```

**临时验证命令**:
```bash
# 检查当前 Tcl/Tk 版本
python3.12 -c "import tkinter; print(f'Tcl: {tkinter.TclVersion}, Tk: {tkinter.TkVersion}')"

# 测试 GUI 是否能直接运行
.venv-py312/bin/python bilibili_gui_transcriber.py
```

---

## 🎯 关键设计决策

### 1. 并发架构

**为什么选择线程池而不是进程池？**
- Whisper 模型已经使用多进程
- 大部分时间消耗在 I/O（下载、API 调用）
- 线程池更轻量，资源占用小

**为什么默认3线程？**
- 平衡性能和资源：2.5-3x 速度提升
- 避免过多并发导致 API 限流
- Whisper CPU 密集，过多线程反而慢

### 2. 命名策略

**为什么代码文件名还是 `bilibili_*`？**
- 保持向后兼容
- 文件名说明了主要平台
- 避免大规模重构风险

**用户可见部分使用 VideoScribe：**
- App 名称、窗口标题
- 文档、README
- GitHub 仓库

### 3. Markdown 输出格式

**为什么使用 YAML Front Matter？**
- 便于解析和自动化
- 保存完整元信息
- 兼容各种 Markdown 工具

**为什么按时间段落分隔？**
```markdown
### [00:00:00 → 00:00:05]
文本内容...
```
- 便于定位和引用
- 保持时间轴信息
- 适合笔记和摘要

---

## 📝 开发工作流

### 添加新功能

1. **创建分支**
   ```bash
   git checkout -b feature/新功能名
   ```

2. **开发和测试**
   ```bash
   # 修改代码
   vim utils.py

   # 本地测试
   python3 bilibili_auto_transcribe.py <测试链接>
   ```

3. **提交代码**
   ```bash
   git add .
   git commit -m "feat: 添加XXX功能"
   git push origin feature/新功能名
   ```

4. **创建 Pull Request**
   - 访问 GitHub
   - 填写 PR 描述
   - 等待 Review

### 修复 Bug

1. **重现问题**
   ```bash
   # 使用相同的测试用例
   python3 bilibili_auto_transcribe.py <问题链接>
   ```

2. **定位代码**
   ```bash
   # 搜索相关代码
   grep -rn "关键词" utils.py
   ```

3. **修复并测试**
   ```bash
   # 修改代码后测试
   python3 bilibili_auto_transcribe.py <问题链接>
   ```

4. **提交修复**
   ```bash
   git commit -m "fix: 修复XXX问题 (Fixes #123)"
   ```

---

## 🔍 代码导航快速参考

### 核心入口函数

```python
# B站单视频处理入口
process_bilibili_video(video_input, model_name, ...)
  → _fetch_bilibili_view()  # 获取视频信息
  → _download_bilibili_subtitle()  # 尝试下载字幕
  → _transcribe_with_whisper()  # 无字幕时转录
  → _write_markdown()  # 生成 Markdown

# YouTube 视频处理入口
process_youtube_video(video_url, model_name, ...)
  → _fetch_youtube_metadata()
  → _download_youtube_subtitle()
  → _transcribe_with_whisper()
  → _write_markdown()

# 批量处理入口
export_creator_videos(creator_url, ...)
  → _get_creator_video_urls()  # 获取视频列表
  → _process_video_batch()  # 并发处理
    → _process_single_video()  # 单个处理

# 并发批处理
_process_video_batch(video_urls, max_workers=3, ...)
  → ThreadPoolExecutor
  → _process_single_video() × N  # 并发执行
```

---

## 📊 性能优化建议

### 当前性能指标

- 单视频（有字幕）: ~30秒
- 单视频（Whisper small）: ~5分钟
- 批量10个视频（3线程）: ~18分钟
- 并发提升: 2.5-3x

### 优化方向

1. **缓存机制** (未实现)
   - 缓存视频元信息
   - 避免重复下载

2. **断点续传** (未实现)
   - 记录处理进度
   - 失败后可恢复

3. **更智能的并发** (已实现部分)
   - ✅ 自动检测视频数量调整并发数
   - ⏳ 根据 CPU 核心数动态调整
   - ⏳ 区分 I/O 和 CPU 密集任务

---

## 🎨 GUI 架构

### 组件结构

```python
class BilibiliTranscriberApp:
    __init__()
        → _build_widgets()  # 构建界面
            → 输入框
            → 设置区（模式/模型/语言/并发）
            → 按钮区（开始/清空/状态）
            → 日志区

    start_process()
        → run_task() in thread
            → _run_single() / _run_creator() / _run_collection()

    log()  # 彩色日志输出
    _update_status()  # 更新状态指示器
```

### 界面尺寸

- 窗口: 800x550（可调整）
- 日志字体: Courier New 9pt
- 按钮: 标准 ttk 样式

---

## 📦 依赖说明

```python
requests         # HTTP 请求（B站API、下载）
yt-dlp          # YouTube 下载和元信息
openai-whisper  # AI 语音转录
pyyaml          # YAML Front Matter
opencc-python-reimplemented  # 简繁转换
pyinstaller     # macOS App 打包（开发依赖）
```

**系统依赖：**
- `ffmpeg`: 音频处理（Whisper 需要）
- `python-tk`: GUI 支持（macOS 通常内置）

---

## 🔗 有用的链接

- **GitHub**: https://github.com/enhen3/VideoScribe
- **Issues**: https://github.com/enhen3/VideoScribe/issues
- **Releases**: https://github.com/enhen3/VideoScribe/releases

**参考文档：**
- OpenAI Whisper: https://github.com/openai/whisper
- yt-dlp: https://github.com/yt-dlp/yt-dlp
- Bilibili API: (非官方，需逆向分析)

---

## ✅ 下次打开项目时的 Checklist

1. [ ] 阅读 `更新日志.md` 了解最新变化
2. [ ] 查看 GitHub Issues 了解待修复的问题
3. [ ] 运行 `git log --oneline` 查看最近提交
4. [ ] 测试基本功能是否正常
5. [ ] 检查依赖是否需要更新

**快速测试命令：**
```bash
# 测试 GUI
python3 bilibili_gui_transcriber.py

# 测试单视频
python3 bilibili_auto_transcribe.py BV1ZqEEzyEC9

# 查看帮助
python3 creator_batch_export.py --help
```

---

**最后更新**: 2025-11-14
**维护者**: @enhen3
**版本**: v2.0
