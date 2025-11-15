# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VideoScribe is a Python-based video transcription tool that extracts subtitles and generates Markdown transcripts from Bilibili and YouTube videos. When official subtitles are unavailable, it uses OpenAI Whisper for automatic speech recognition.

**Key capabilities:**
- Single video processing (CLI & GUI)
- Batch processing of creator channels/playlists
- Multi-part video support (Bilibili)
- Concurrent processing (3-8 threads)
- Bilingual support (Chinese/English with auto-detection)

## Development Commands

### Setup & Installation
```bash
# Install dependencies
./install_requirements.sh

# Manual installation
pip install requests yt-dlp openai-whisper pyyaml opencc-python-reimplemented
brew install ffmpeg
```

### Testing
```bash
# Test GUI
python3 bilibili_gui_transcriber.py

# Test single video
python3 bilibili_auto_transcribe.py BV1ZqEEzyEC9
python3 bilibili_auto_transcribe.py https://youtu.be/dQw4w9WgXcQ

# Test batch processing
python3 creator_batch_export.py https://space.bilibili.com/123456 --limit 3

# Test with custom parameters
python3 bilibili_auto_transcribe.py BV1xx411e7AS medium --lang en
python3 creator_batch_export.py <URL> --max-workers 5 --model medium
```

### Running GUI Without Building

```bash
# Quick start - no packaging required
chmod +x run_videoscribe.sh
./run_videoscribe.sh

# Or directly
python3 bilibili_gui_transcriber.py
```

### Building macOS App (Optional)

```bash
# Requires Python 3.12
brew install python@3.12 python-tk@3.12

# Setup virtual environment
python3.12 -m venv .venv-py312
.venv-py312/bin/pip install requests yt-dlp openai-whisper pyyaml opencc-python-reimplemented pyinstaller

# Build
chmod +x build_gui_app.sh
./build_gui_app.sh

# Output: dist/VideoScribeApp.app

# Note: Due to Tcl/Tk 9.0.3 compatibility issues with PyInstaller,
# using run_videoscribe.sh is currently more reliable than the .app bundle
```

### Cleanup
```bash
# Clean build artifacts
rm -rf build/ dist/ .venv-py312/ *.spec

# Clean Python cache
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null

# Clean temporary files
rm -f BV*.txt BV*.mp3 BV*.m4a
```

## Architecture

### Core Module Structure

**utils.py** (1500+ lines) - Core engine containing all business logic:
- Platform detection and URL parsing
- Video metadata extraction (Bilibili API, yt-dlp)
- Subtitle download and parsing
- Whisper transcription
- Markdown generation with YAML front matter
- Concurrent batch processing with ThreadPoolExecutor

**Entry Points:**
- `bilibili_gui_transcriber.py` - Tkinter GUI (430 lines)
- `bilibili_auto_transcribe.py` - CLI for single videos (90 lines)
- `creator_batch_export.py` - CLI for batch processing (78 lines)

### Key Processing Functions (utils.py)

**Single Video Processing:**
- `process_bilibili_video()` - Main entry for Bilibili videos (~842)
- `process_youtube_video()` - Main entry for YouTube videos (~1074)

**Batch Processing:**
- `export_creator_videos()` - Process all videos from a creator (~1477)
- `export_bilibili_collection_videos()` - Process Bilibili playlists/collections (~1526)
- `_process_video_batch()` - Concurrent batch processor with ThreadPoolExecutor (~1392)
- `_process_single_video()` - Thread-safe wrapper for single video (~1349)

**Bilibili-specific:**
- `_fetch_bilibili_view()` - Get video metadata via API (~523)
- `_fetch_bilibili_subtitle_entry()` - Get subtitle metadata (~537)
- `_download_bilibili_subtitle_segments()` - Download and parse subtitles (~563)
- `fetch_bilibili_videos_via_api()` - Get all videos from creator space (~644)
- `fetch_bilibili_ugc_season_videos()` - Get collection/series videos (~739)
- `fetch_bilibili_fav_videos()` - Get favorites list (~769)
- `fetch_bilibili_series_videos()` - Get series list (~814)
- `_collect_bilibili_pages()` - Extract all parts (分P) from video (~693)
- `detect_bilibili_collection()` - Detect collection type from URL (~622)

**YouTube-specific:**
- `_extract_youtube_info()` - Get video info via yt-dlp (~1126)
- `_download_youtube_subtitles()` - Download subtitles in preferred language (~1058)
- `_fetch_creator_video_urls_ytdlp()` - Get all videos from channel (~1264)

**Core Utilities:**
- `_transcribe_with_whisper()` - Audio transcription with Whisper (~458)
- `_download_audio()` - Download audio using yt-dlp (~498)
- `generate_markdown()` - Create structured Markdown output (~299)
- `parse_subtitle_text()` - Parse WebVTT/SRT format (~376)
- `_ThreadSafeLogger` - Thread-safe logging for concurrent operations (~1336)
- `ensure_output_dir()` - Create platform/uploader directory structure (~278)
- `download_text()` - Fetch subtitle content from URL (~418)

**Language Processing:**
- `should_prefer_english()` - Determine language preference based on content (~249)
- `normalize_text()` - Clean and optionally convert to simplified Chinese (~195)
- `to_simplified()` - Traditional to simplified Chinese conversion (~184)
- `looks_like_english()` - Detect English content by ASCII ratio (~216)
- `contains_chinese()` - Check for CJK characters (~234)
- `is_chinese_lang()` / `is_english_language()` - Language code validation (~202, ~209)

### Output Format

Files are saved to `~/ViedoTextDownload/` (configurable via `TRANSCRIBE_OUTPUT_DIR`):

```
~/ViedoTextDownload/
├── bilibili/
│   └── {uploader_name}/
│       ├── {BVID}_{title}.md
│       └── {BVID}-P01_{title}.md  # Multi-part videos
└── youtube/
    └── {channel_name}/
        └── {video_id}_{title}.md
```

Each Markdown file contains:
- YAML front matter with metadata (platform, video_id, title, uploader, upload_date, source, language, duration, tags, processed_at)
- Video metadata section
- Timestamped transcript segments in format: `### [HH:MM:SS → HH:MM:SS]`

### Concurrent Processing Architecture

Default: 5 worker threads (configurable 1-8, increased from 3 to 5 for better performance)
- Uses `ThreadPoolExecutor` for I/O-bound operations
- `_ThreadSafeLogger` with Lock for safe concurrent logging (~1336)
- Sequential fallback for 1-2 videos or when disabled via `--no-concurrent`
- Designed for API calls and downloads (not Whisper CPU usage)
- Higher default (5) significantly improves speed for subtitle-based processing
- Can be controlled via `--max-workers N` flag (1-8 range enforced)

## Important Implementation Details

### Language Detection & Processing

The tool uses multi-level language detection with the following priority (utils.py:249 `should_prefer_english()`):
1. **Explicit user choice** via `--lang` flag (auto/zh/en) - highest priority
2. **Audio language detection**:
   - YouTube: Uses `audio_language` or `language` field from yt-dlp (~1195)
   - Bilibili: Infers from video tags (e.g., "English", "英语", "中文") (~882)
   - Passed as `audio_language` parameter to `should_prefer_english()`
3. **Content analysis**: `looks_like_english()` checks ASCII ratio in title/description (~216)
4. **Fallback**: Platform-specific defaults

For English content: prefer English subtitles, use Whisper with `language="en"`
For Chinese content: prefer Chinese subtitles, convert traditional to simplified, use Whisper with `language="zh"`

### Skip Existing Files

Both `process_bilibili_video()` and `process_youtube_video()` check if output Markdown file already exists before processing:
- Checks at utils.py:~930 (Bilibili) and utils.py:~1170 (YouTube)
- Logs with `⏭️ 跳过已存在：{filename}` message
- Avoids re-downloading audio and re-transcribing
- Significantly speeds up batch re-runs
- Can be controlled via `skip_existing` parameter in `generate_markdown()` (~299)

### Multi-Part Video Handling

Bilibili videos can have multiple parts (分P). The code:
- Detects all parts via `_collect_bilibili_pages()`
- Processes each part separately with unique CID
- Generates separate Markdown files: `{BVID}-P01_title.md`, `{BVID}-P02_title.md`, etc.
- Full title format: `{original_title}｜P{num} {part_title}`

### Collection/Playlist Processing

When `--include-collection` is used or batch processing:
- Auto-detects collection type: favorites (`fav`), series (`series`), UGC season (`ugc_series`)
- Fetches all video URLs from collection
- Processes concurrently (default 3 threads)
- Skips the original video to avoid duplication

### Subtitle Priority

**IMPORTANT**: Official subtitles are ALWAYS prioritized over Whisper transcription to save time.

**Bilibili (utils.py:~950):**
1. Attempts to fetch official subtitles via `_fetch_bilibili_subtitle_entry()` (~537)
2. If `prefer_english=True`: English subtitles → Chinese subtitles → Whisper (en)
3. If `prefer_english=False`: Chinese subtitles → English subtitles → Whisper (zh)
4. Logs `📄 找到官方字幕` or `⚠️ 未找到官方字幕` to inform user

**YouTube (utils.py:~1200):**
1. Attempts to download subtitles via `_download_youtube_subtitles()` (~1058)
2. Requests multiple languages via yt-dlp
3. Prioritizes based on `prefer_english` flag
4. Falls back to Whisper only if no subtitles available
5. Logs `📄 找到官方字幕` or `⚠️ 未找到官方字幕` to inform user

**Whisper is only invoked when `if not segments:` (no official subtitles found)**

### Cookie Support for Private Content

For restricted Bilibili/YouTube content:
- Set `BILIBILI_COOKIE_FILE` or `YOUTUBE_COOKIE_FILE` environment variables
- Export browser cookies to text file
- yt-dlp uses cookies for authenticated requests

## Environment Variables

- `TRANSCRIBE_OUTPUT_DIR` or `BILI_OUTPUT_DIR` - Custom output directory (default: `~/ViedoTextDownload`)
- `BILIBILI_COOKIE_FILE` - Path to Bilibili cookie file for restricted content
- `YOUTUBE_COOKIE_FILE` - Path to YouTube cookie file for restricted content

## Dependencies

**Required:**
- `requests` - HTTP requests for Bilibili API
- `yt-dlp` - YouTube/Bilibili video downloading and metadata extraction
- `openai-whisper` - AI speech transcription
- `pyyaml` - YAML front matter serialization
- `opencc-python-reimplemented` - Traditional to Simplified Chinese conversion
- `ffmpeg` - Audio processing (system dependency)

**Development:**
- `pyinstaller` - macOS .app packaging

## Common Issues

**Bilibili API 352 Error:**
- Server rejection, usually for batch operations
- Solution: Export browser cookies after login, set `BILIBILI_COOKIE_FILE` env var

**Whisper First-Time Slow Download:**
- Models download to `~/.cache/whisper/`
- Pre-download: `python3 -m whisper --model small`

**Module Cache Issues:**
- If changes to `utils.py` don't reflect in GUI
- Kill process: `pkill -f "python.*bilibili_gui"`
- Restart: `python3 bilibili_gui_transcriber.py` or `./run_videoscribe.sh`

**PyInstaller App Bundle Issues:**
- Known issue with Tcl/Tk 9.0.3 and PyInstaller 6.16.0
- Error: "cannot use non-numeric floating-point value 'NaN'"
- Solution: Use `./run_videoscribe.sh` instead of building .app
- Alternative: Wait for PyInstaller to fully support Tcl/Tk 9.0+

## Code Style & Naming

**File Naming:**
- Python files still use `bilibili_*` prefix for backward compatibility
- User-facing elements (app name, window title, docs) use "VideoScribe"

**Naming Conventions:**
- Public API functions: descriptive names (`process_bilibili_video`, `export_creator_videos`)
- Internal helpers: underscore prefix (`_fetch_bilibili_view`, `_download_audio`)
- Thread-safe wrappers: `_ThreadSafeLogger` class
- Error handling: custom `VideoProcessingError` exception

## Testing Strategy

Always test these scenarios when making changes:
1. Single Bilibili video with official subtitles
2. Single YouTube video requiring Whisper
3. Bilibili multi-part video (分P)
4. Batch processing with `--limit 3`
5. Collection/playlist processing
6. Both Chinese and English content
7. Concurrent processing with different `--max-workers` values
8. Skip existing files behavior (re-run same video)
9. GUI via `run_videoscribe.sh`

## Recent Changes (Uncommitted)

**Performance Optimization:**
- Increased default `--max-workers` from 3 to 5 for faster batch processing
- Updated in both `utils.py:DEFAULT_MAX_WORKERS` and `creator_batch_export.py`

**Enhanced Language Detection:**
- Added audio language inference from Bilibili video tags
- `should_prefer_english()` now accepts `audio_language` parameter
- Checks tags for "English", "英语", "中文", "Chinese" keywords

**Improved File Skipping:**
- `generate_markdown()` now has `skip_existing` parameter
- Both Bilibili and YouTube processors check for existing files early
- Prevents unnecessary re-processing in batch operations
