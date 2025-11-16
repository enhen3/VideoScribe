#!/usr/bin/env python3
"""共享工具：平台识别、元信息抓取、字幕/音频处理、Markdown 生成等。"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    try:  # pragma: no cover
        from urllib3.exceptions import NotOpenSSLWarning
    except Exception:
        NotOpenSSLWarning = None  # type: ignore

if NotOpenSSLWarning:
    warnings.filterwarnings("ignore", category=NotOpenSSLWarning)

import requests
import yaml

try:
    from yt_dlp import YoutubeDL
except ImportError:  # pragma: no cover
    YoutubeDL = None  # type: ignore

try:
    from opencc import OpenCC
except ImportError:  # pragma: no cover
    OpenCC = None  # type: ignore

try:
    import whisper
except ImportError:  # pragma: no cover
    whisper = None  # type: ignore


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
BILIBILI_VIEW_API = "https://api.bilibili.com/x/web-interface/view"
BILIBILI_SUBTITLE_API = "https://api.bilibili.com/x/player/v2"
PREFERRED_LANGS = ["zh-Hans", "zh", "zh-Hant", "yue"]
ENGLISH_LANGS = ["en", "en-us", "en-gb"]

# 并发处理配置
DEFAULT_MAX_WORKERS = 5  # 默认并发数（优化：提高并发以加快字幕下载）
MAX_WORKERS_LIMIT = 8  # 最大并发数限制
ENABLE_CONCURRENT = True  # 默认启用并发
FAV_LIST_RE = re.compile(r"/list/ml(\d+)")
FAV_QUERY_KEYS = ("fid", "media_id", "mlid")
SERIES_LIST_RE = re.compile(r"/list/series/(\d+)")
LANGUAGE_AUTO = "auto"
LANGUAGE_ZH = "zh"
LANGUAGE_EN = "en"
LANGUAGE_CHOICES = {LANGUAGE_AUTO, LANGUAGE_ZH, LANGUAGE_EN}
def _resolve_output_root() -> Path:
    env_path = os.getenv("TRANSCRIBE_OUTPUT_DIR") or os.getenv("BILI_OUTPUT_DIR")
    if env_path:
        path = Path(env_path).expanduser()
        if not path.is_absolute():
            path = Path.home() / path
        return path
    return Path.home() / "ViedoTextDownload"


DEFAULT_OUTPUT_ROOT = _resolve_output_root()
EXTRA_BIN_DIRS = (
    "/opt/homebrew/bin",
    "/usr/local/bin",
    str(Path.home() / "Library/Python/3.9/bin"),
    str(Path.home() / ".local/bin"),
)
DEFAULT_LANGUAGE = "Chinese"
TIMECODE_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}:\d{2}(?:[.,]\d{3})?)\s*-->\s*(?P<end>\d{1,2}:\d{2}:\d{2}(?:[.,]\d{3})?)"
)
TAG_RE = re.compile(r"<[^>]+>")


class VideoProcessingError(Exception):
    """统一处理异常。"""


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class VideoMeta:
    platform: str
    video_id: str
    title: str
    uploader: str
    upload_date: str
    source: str
    url: str
    duration: str
    processed_at: str
    language: str = DEFAULT_LANGUAGE
    original_language: str = "unknown"
    tags: List[str] = field(default_factory=list)


@dataclass
class ProcessResult:
    platform: str
    markdown_path: Path
    txt_path: Optional[Path]
    meta: VideoMeta


if OpenCC:
    _CC = OpenCC("t2s")
else:
    _CC = None


def ensure_extra_path() -> None:
    path_parts = os.environ.get("PATH", "").split(os.pathsep) if os.environ.get("PATH") else []
    changed = False
    for directory in EXTRA_BIN_DIRS:
        if directory and directory not in path_parts:
            path_parts.append(directory)
            changed = True
    if changed:
        os.environ["PATH"] = os.pathsep.join(part for part in path_parts if part)


def ensure_ffmpeg_available() -> None:
    ensure_extra_path()
    if shutil.which("ffmpeg"):
        return
    raise VideoProcessingError(
        "未检测到 ffmpeg，可通过 `brew install ffmpeg` 安装，或设置 PATH / TRANSCRIBE_OUTPUT_DIR。"
    )


def _maybe_log(logger: Optional[Callable[[str], None]], message: str) -> None:
    if logger:
        logger(message)


def detect_platform(text: str) -> Optional[str]:
    """根据输入判断平台。"""
    lowered = text.lower()
    if "bilibili.com" in lowered or "b23.tv" in lowered or re.search(r"bv[0-9a-z]+", lowered, re.I):
        return "bilibili"
    if "youtube.com" in lowered or "youtu.be" in lowered:
        return "youtube"
    return None


def slugify(value: str, fallback: str = "video") -> str:
    value = re.sub(r"[\\/:*?\"<>|]+", "_", value)
    value = re.sub(r"\s+", "_", value)
    value = value.strip("._")
    return value or fallback


def format_timestamp(seconds: Optional[float]) -> str:
    if seconds is None:
        return "unknown"
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def to_simplified(text: str) -> str:
    if not text:
        return ""
    if _CC is None:
        return text
    try:
        return _CC.convert(text)
    except Exception:  # pragma: no cover
        return text


def normalize_text(text: str, convert_to_simplified: bool = True) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return ""
    return to_simplified(cleaned) if convert_to_simplified else cleaned


def is_chinese_lang(value: Optional[str]) -> bool:
    if not value:
        return False
    lower = value.lower()
    return lower.startswith(("zh", "chinese", "yue"))


def is_english_language(value: Optional[str]) -> bool:
    if not value:
        return False
    lower = value.lower()
    return lower.startswith("en") or "english" in lower


def looks_like_english(text: Optional[str]) -> bool:
    if not text:
        return False
    ascii_letters = sum(ch.isalpha() and ch.isascii() for ch in text)
    cjk_letters = sum(_contains_cjk_char(ch) for ch in text)
    if ascii_letters == 0:
        return False
    total_letters = ascii_letters + cjk_letters
    if total_letters == 0:
        total_letters = len(text)
    ratio = ascii_letters / max(total_letters, 1)
    return ratio >= 0.6 and cjk_letters < ascii_letters / 2


def _contains_cjk_char(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def contains_chinese(text: Optional[str]) -> bool:
    if not text:
        return False
    return any(_contains_cjk_char(ch) for ch in text)


def normalize_language_mode(mode: Optional[str]) -> str:
    if not mode:
        return LANGUAGE_AUTO
    normalized = mode.strip().lower()
    if normalized not in LANGUAGE_CHOICES:
        return LANGUAGE_AUTO
    return normalized


def should_prefer_english(language_mode: str, texts: Iterable[Optional[str]], fallback: bool = False, audio_language: Optional[str] = None) -> bool:
    """判断是否应该优先使用英文。

    优先级：
    1. 用户明确指定语言（--lang en/zh）
    2. 音频语言信息（audio_language 参数）
    3. 文本内容分析（标题、描述等）
    4. fallback 默认值
    """
    normalized = normalize_language_mode(language_mode)
    if normalized == LANGUAGE_EN:
        return True
    if normalized == LANGUAGE_ZH:
        return False

    # 如果有音频语言信息，优先使用
    if audio_language:
        if is_english_language(audio_language):
            return True
        if is_chinese_lang(audio_language):
            return False

    # 分析文本内容
    for text in texts:
        if looks_like_english(text):
            return True
    return fallback


def ensure_output_dir(platform: str, uploader: str, root: Path = DEFAULT_OUTPUT_ROOT) -> Path:
    uploader_slug = slugify(uploader or "unknown_creator", "unknown_creator")
    path = root / platform / uploader_slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def segments_to_plain_text(segments: List[Segment]) -> str:
    return "\n".join(seg.text for seg in segments if seg.text).strip()


def write_legacy_txt(segments: List[Segment], output_dir: Path, base_name: str) -> Path:
    txt_path = output_dir / f"{base_name}.txt"
    content = segments_to_plain_text(segments)
    if content:
        txt_path.write_text(content + "\n", encoding="utf-8")
    else:
        txt_path.write_text("", encoding="utf-8")
    return txt_path


def generate_markdown(meta: VideoMeta, segments: List[Segment], output_dir: Path, skip_existing: bool = True) -> Path:
    """根据模板生成 Markdown 文件。"""
    filename = f"{meta.video_id}_{slugify(meta.title)}.md"
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / filename

    # 检查文件是否已存在
    if skip_existing and md_path.exists():
        return md_path
    metadata = {
        "platform": meta.platform,
        "video_id": meta.video_id,
        "title": meta.title,
        "uploader": meta.uploader,
        "upload_date": meta.upload_date,
        "source": meta.source,
        "language": meta.language,
        "original_language": meta.original_language,
        "duration": meta.duration,
        "tags": meta.tags or [],
        "processed_at": meta.processed_at,
    }
    front_matter = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).strip()
    lines: List[str] = [
        "---",
        front_matter,
        "---",
        "",
        f"# {meta.title}",
        "",
        "## 元信息（Metadata）",
        "",
        f"- 平台：{meta.platform}",
        f"- 视频链接：{meta.url}",
        f"- 视频 ID：{meta.video_id}",
        f"- 上传者：{meta.uploader}",
        f"- 上传时间：{meta.upload_date}",
        f"- 字幕来源：{meta.source}",
        f"- 处理时间：{meta.processed_at}",
        f"- 视频时长：{meta.duration}",
        "",
        "---",
        "",
        "## 视频摘要（可留空）",
        "（供未来 AI 自动总结）",
        "",
        "---",
        "",
        "## 文本正文（按时间顺序）",
        "",
    ]

    # 去除重复的字幕片段
    deduplicated_segments = deduplicate_segments(segments)

    for segment in deduplicated_segments:
        start_ts = format_timestamp(segment.start)
        end_ts = format_timestamp(segment.end)
        text = segment.text.strip()
        if not text:
            continue
        lines.append(f"### [{start_ts} → {end_ts}]")
        lines.append(text)
        lines.append("")

    final_md_path = output_dir / filename
    final_md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return final_md_path


def parse_timestamp_to_seconds(value: str) -> float:
    value = value.replace(",", ".")
    parts = value.split(":")
    parts = [float(part) for part in parts]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    hours, minutes, seconds = parts
    return hours * 3600 + minutes * 60 + seconds


def parse_subtitle_text(text: str) -> List[Segment]:
    segments: List[Segment] = []
    start: Optional[float] = None
    end: Optional[float] = None
    buffer: List[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            if start is not None and buffer:
                combined = TAG_RE.sub("", " ".join(buffer)).strip()
                if combined:
                    segments.append(Segment(start=start, end=end or (start + 1), text=combined))
            start = end = None
            buffer = []
            continue

        match = TIMECODE_RE.match(line)
        if match:
            if start is not None and buffer:
                combined = TAG_RE.sub("", " ".join(buffer)).strip()
                if combined:
                    segments.append(Segment(start=start, end=end or (start + 1), text=combined))
            start = parse_timestamp_to_seconds(match.group("start"))
            end = parse_timestamp_to_seconds(match.group("end"))
            buffer = []
            continue

        if line.startswith("NOTE"):
            continue
        if line.isdigit():
            continue
        buffer.append(line)

    if start is not None and buffer:
        combined = TAG_RE.sub("", " ".join(buffer)).strip()
        if combined:
            segments.append(Segment(start=start, end=end or (start + 1), text=combined))

    return segments


def deduplicate_segments(segments: List[Segment]) -> List[Segment]:
    """去除重复和重叠的字幕片段。

    YouTube 自动生成的字幕经常有重叠，每个新片段都包含前一个片段的部分内容。
    这个函数会移除：
    1. 开始时间=结束时间的片段（通常是不完整的片段）
    2. 文本完全被其他时间重叠的片段包含的较短片段
    3. 完全重复的片段
    """
    if not segments:
        return []

    # 第一步：移除无效片段（空文本或时间点相同的片段）
    valid_segments = []
    for seg in segments:
        text = seg.text.strip()
        # 跳过空文本或开始时间=结束时间的片段
        if not text or seg.start == seg.end:
            continue
        valid_segments.append(Segment(start=seg.start, end=seg.end, text=text))

    if not valid_segments:
        return []

    # 第二步：按开始时间和文本长度排序（同一时间段，较长的文本在前）
    sorted_segments = sorted(valid_segments, key=lambda seg: (seg.start, -len(seg.text)))

    # 第三步：去除冗余片段
    result = []
    for seg in sorted_segments:
        is_redundant = False

        # 检查是否被已经添加的片段包含
        for existing in result:
            # 检查时间是否重叠
            time_overlap = not (seg.end <= existing.start or seg.start >= existing.end)

            # 如果时间重叠，且当前片段的文本被已存在的片段完全包含，则视为冗余
            if time_overlap and seg.text in existing.text and len(seg.text) < len(existing.text):
                is_redundant = True
                break

            # 如果文本完全相同，也视为冗余（即使时间略有不同）
            if seg.text == existing.text:
                is_redundant = True
                break

        if not is_redundant:
            result.append(seg)

    # 按开始时间重新排序后返回
    return sorted(result, key=lambda seg: seg.start)


def download_text(url: str) -> str:
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise VideoProcessingError(f"字幕下载失败：{exc}") from exc
    resp.encoding = resp.encoding or "utf-8"
    return resp.text


def _require_ytdlp() -> None:
    if YoutubeDL is None:
        raise VideoProcessingError("未检测到 yt-dlp，请先运行安装脚本。")


def _require_whisper() -> None:
    if whisper is None:
        raise VideoProcessingError("未安装 openai-whisper，请先运行安装脚本。")


def _fmt_upload_date_from_epoch(epoch: Optional[int]) -> str:
    if not epoch:
        return "unknown"
    try:
        return datetime.utcfromtimestamp(epoch).strftime("%Y-%m-%d")
    except Exception:  # pragma: no cover
        return "unknown"


def _fmt_upload_date_from_str(date_str: Optional[str]) -> str:
    if not date_str:
        return "unknown"
    if re.fullmatch(r"\d{8}", date_str):
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return date_str


ensure_extra_path()


def _transcribe_with_whisper(
    audio_path: Path,
    model_name: str,
    convert_to_simplified: bool,
    logger: Optional[Callable[[str], None]],
    language_code: Optional[str] = "zh",
) -> List[Segment]:
    _require_whisper()
    _maybe_log(logger, "🧠 正在使用 Whisper 转录音频…")
    try:
        model = whisper.load_model(model_name)
    except Exception as exc:  # pragma: no cover
        raise VideoProcessingError(f"Whisper 模型加载失败：{exc}") from exc
    try:
        kwargs = {"language": language_code} if language_code else {}
        result = model.transcribe(str(audio_path), **kwargs)
    except Exception as exc:  # pragma: no cover
        raise VideoProcessingError(f"Whisper 识别失败：{exc}") from exc

    segments_data = result.get("segments") or []
    if not segments_data:
        text = normalize_text(result.get("text", ""), convert_to_simplified)
        if not text:
            raise VideoProcessingError("Whisper 未返回任何文本")
        return [Segment(start=0.0, end=0.0, text=text)]

    segments: List[Segment] = []
    for seg in segments_data:
        raw_text = seg.get("text", "").strip()
        text = normalize_text(raw_text, convert_to_simplified)
        if not text:
            continue
        start = float(seg.get("start") or 0.0)
        end = float(seg.get("end") or start)
        segments.append(Segment(start=start, end=end, text=text))
    if not segments:
        raise VideoProcessingError("Whisper 未返回任何文本")
    return segments


def _download_audio(video_url: str, output_dir: Path, base_name: str, logger: Optional[Callable[[str], None]]) -> Path:
    _require_ytdlp()
    ensure_ffmpeg_available()
    outtmpl = str(output_dir / f"{base_name}.%(ext)s")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
    }
    _maybe_log(logger, "⏬ 正在下载音频…")
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            downloaded = Path(ydl.prepare_filename(info))
            if not downloaded.exists():
                raise VideoProcessingError("音频文件未生成，可能是下载被中断")
            return downloaded
    except VideoProcessingError:
        raise
    except Exception as exc:
        raise VideoProcessingError(f"音频下载失败：{exc}") from exc


def _fetch_bilibili_view(bvid: str) -> Dict:
    try:
        resp = requests.get(
            BILIBILI_VIEW_API, params={"bvid": bvid}, headers={"User-Agent": USER_AGENT}, timeout=15
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise VideoProcessingError(f"无法访问 B 站接口：{exc}") from exc
    data = resp.json().get("data")
    if not data:
        raise VideoProcessingError("无法获取 B 站视频信息")
    return data


def _fetch_bilibili_subtitle_entry(bvid: str, cid: str, prefer_english: bool, allow_fallback: bool = True) -> Optional[Dict]:
    try:
        resp = requests.get(
            BILIBILI_SUBTITLE_API,
            params={"bvid": bvid, "cid": cid},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise VideoProcessingError(f"无法访问 B 站字幕接口：{exc}") from exc
    subtitles = resp.json().get("data", {}).get("subtitle", {}).get("subtitles") or []
    if not subtitles:
        return None

    langs = ENGLISH_LANGS if prefer_english else PREFERRED_LANGS + ENGLISH_LANGS
    for lang in langs:
        for item in subtitles:
            lan = (item.get("lan") or "").lower()
            if lan == lang.lower():
                return item
    if allow_fallback and subtitles:
        return subtitles[0]
    return None


def _download_bilibili_subtitle_segments(entry: Dict, convert_to_simplified: bool) -> List[Segment]:
    url = entry.get("subtitle_url")
    if not url:
        return []
    if url.startswith("//"):
        url = "https:" + url
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise VideoProcessingError(f"下载 B 站字幕失败：{exc}") from exc
    items = resp.json()
    segments: List[Segment] = []
    for item in items:
        text = normalize_text(item.get("content", ""), convert_to_simplified=convert_to_simplified)
        if not text:
            continue
        start = float(item.get("from") or 0.0)
        end = float(item.get("to") or start)
        segments.append(Segment(start=start, end=end, text=text))
    return segments


def _extract_bvid(value: str) -> str:
    match = re.search(r"(BV[0-9A-Za-z]+)", value, re.I)
    if not match:
        raise VideoProcessingError("无法解析 BV 号，请确认输入")
    return match.group(1)


def _extract_bilibili_mid(url: str) -> Optional[str]:
    match = re.search(r"space\.bilibili\.com/(\d+)", url)
    if match:
        return match.group(1)
    if url.isdigit():
        return url
    return None


def _resolve_bilibili_mid(url: str) -> Optional[str]:
    mid = _extract_bilibili_mid(url)
    if mid:
        return mid
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    match = re.search(r'"mid"\s*:\s*(\d+)', resp.text)
    if match:
        return match.group(1)
    return None


def _resolve_series_mid(series_id: str) -> Optional[str]:
    url = f"https://www.bilibili.com/list/series/{series_id}"
    return _resolve_bilibili_mid(url)


def detect_bilibili_collection(url: str) -> Optional[Tuple[str, str]]:
    if not url:
        return None
    match = FAV_LIST_RE.search(url)
    if match:
        return ("fav", match.group(1))
    match = SERIES_LIST_RE.search(url)
    if match:
        return ("series", match.group(1))
    parsed = urlparse(url)
    qs = parse_qs(parsed.query or "")
    for key in FAV_QUERY_KEYS:
        if key in qs and qs[key]:
            return ("fav", qs[key][0])
    if "series_id" in qs and qs["series_id"]:
        return ("series", qs["series_id"][0])
    for candidate in ("collection_id", "sid", "season_id", "playlist_id"):
        if candidate in qs and qs[candidate]:
            return ("ugc_series", qs[candidate][0])
    return None


def fetch_bilibili_videos_via_api(mid: str, logger: Optional[Callable[[str], None]] = None) -> List[str]:
    """调用 B 站空间 API 获取 UP 主所有 BV 号。"""
    urls: List[str] = []
    ps = 50
    pn = 1
    while True:
        params = {
            "mid": mid,
            "ps": ps,
            "tid": 0,
            "pn": pn,
            "order": "pubdate",
            "jsonp": "json",
        }
        try:
            resp = requests.get(
                "https://api.bilibili.com/x/space/arc/search",
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise VideoProcessingError(f"拉取 B 站视频列表失败：{exc}") from exc

        data = resp.json().get("data") or {}
        vlist = data.get("list", {}).get("vlist") or []
        if not vlist:
            break

        for item in vlist:
            bvid = item.get("bvid")
            if not bvid:
                continue
            urls.append(f"https://www.bilibili.com/video/{bvid}")

        total = data.get("page", {}).get("count") or 0
        if len(urls) >= total:
            break
        pn += 1

        # 防止无限循环
        if pn > 200:
            _maybe_log(logger, "⚠️ 视频数量超过 10000，提前停止")
            break

    return urls


def _collect_bilibili_pages(view_data: Dict) -> List[Dict]:
    pages = view_data.get("pages") or []
    if pages:
        return pages
    cid = view_data.get("cid")
    if not cid:
        return []
    return [
        {
            "cid": cid,
            "page": 1,
            "part": view_data.get("title"),
            "duration": view_data.get("duration"),
        }
    ]


def _detect_collection_from_video_input(raw_value: str, bvid: str) -> Optional[Tuple[str, str]]:
    info = detect_bilibili_collection(raw_value)
    if info:
        return info
    season_id = _fetch_ugc_season_id(bvid)
    if season_id:
        return ("ugc_series", season_id)
    return None


def _fetch_ugc_season_id(bvid: str) -> Optional[str]:
    try:
        resp = requests.get(
            "https://api.bilibili.com/x/web-interface/view/detail",
            params={"bvid": bvid},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return None
    data = resp.json().get("data", {}).get("View", {})
    season = data.get("ugc_season") or {}
    season_id = season.get("id") or season.get("season_id")
    if season_id:
        return str(season_id)
    return None


def fetch_bilibili_ugc_season_videos(season_id: str, logger: Optional[Callable[[str], None]] = None) -> Tuple[List[str], str]:
    """解析 ugc_season 数据，返回合集内所有 BV。"""
    try:
        resp = requests.get(
            "https://api.bilibili.com/x/web-interface/view/detail",
            params={"season_id": season_id},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise VideoProcessingError(f"拉取合集详情失败：{exc}") from exc

    data = resp.json().get("data", {})
    view_data = data.get("View") or {}
    season = view_data.get("ugc_season") or {}
    sections = season.get("sections") or []
    title = season.get("title") or season.get("name") or f"合集{season_id}"
    urls: List[str] = []
    for section in sections:
        for episode in section.get("episodes") or []:
            bvid = episode.get("bvid")
            if not bvid:
                continue
            urls.append(f"https://www.bilibili.com/video/{bvid}")
    if not urls:
        raise VideoProcessingError("合集内未找到任何视频")
    return urls, title


def fetch_bilibili_fav_videos(media_id: str, logger: Optional[Callable[[str], None]] = None) -> Tuple[List[str], str]:
    """获取收藏夹全部 BV。"""
    urls: List[str] = []
    title = f"收藏夹{media_id}"
    pn = 1
    ps = 20
    while True:
        params = {
            "media_id": media_id,
            "pn": pn,
            "ps": ps,
            "platform": "web",
            "order": "mtime",
        }
        try:
            resp = requests.get(
                "https://api.bilibili.com/x/v3/fav/resource/list",
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise VideoProcessingError(f"拉取收藏夹失败：{exc}") from exc

        data = resp.json().get("data") or {}
        info = data.get("info") or {}
        if info.get("title"):
            title = info["title"]
        medias = data.get("medias") or []
        if not medias:
            break
        for item in medias:
            bvid = item.get("bvid") or item.get("id")
            if not bvid:
                continue
            if not str(bvid).lower().startswith("bv"):
                continue
            urls.append(f"https://www.bilibili.com/video/{bvid}")
        if not data.get("has_more"):
            break
        pn += 1
    return urls, title


def fetch_bilibili_series_videos(series_id: str, logger: Optional[Callable[[str], None]] = None) -> Tuple[List[str], str]:
    """获取合集(系列)全部 BV。"""
    mid = _resolve_series_mid(series_id)
    if not mid:
        raise VideoProcessingError("无法解析合集所属 UP 主，可能链接无效")

    urls: List[str] = []
    title = f"合集{series_id}"
    pn = 1
    ps = 100
    while True:
        params = {
            "mid": mid,
            "series_id": series_id,
            "only_normal": "true",
            "pn": pn,
            "ps": ps,
        }
        try:
            resp = requests.get(
                "https://api.bilibili.com/x/series/archives",
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise VideoProcessingError(f"拉取合集列表失败：{exc}") from exc

        data = resp.json().get("data") or {}
        meta = data.get("meta") or {}
        if meta.get("name"):
            title = meta["name"]
        archives = data.get("archives") or []
        if not archives:
            break
        for archive in archives:
            bvid = archive.get("bvid")
            if not bvid:
                continue
            urls.append(f"https://www.bilibili.com/video/{bvid}")
        if len(archives) < ps:
            break
        pn += 1
        if pn > 200:
            _maybe_log(logger, "⚠️ 合集视频数量较多，已提前停止")
            break
    return urls, title


def process_bilibili_video(
    value: str,
    model_name: str = "small",
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    write_txt: bool = True,
    logger: Optional[Callable[[str], None]] = None,
    include_collection: bool = False,
    language_mode: str = LANGUAGE_AUTO,
) -> List[ProcessResult]:
    """处理 B 站视频；若存在分 P，全部导出。"""
    language_mode = normalize_language_mode(language_mode)
    bvid = _extract_bvid(value)
    view_data = _fetch_bilibili_view(bvid)
    uploader = view_data.get("owner", {}).get("name") or "未知UP主"
    upload_date = _fmt_upload_date_from_epoch(view_data.get("pubdate"))
    base_duration = format_timestamp(view_data.get("duration"))
    output_dir = ensure_output_dir("bilibili", uploader, output_root)

    # 尝试从标签或描述中推断音频语言
    audio_lang_hint = None
    tags = view_data.get("tags") or []
    for tag in tags:
        tag_lower = str(tag).lower()
        if "english" in tag_lower or "英语" in tag_lower:
            audio_lang_hint = "en"
            break
        if "中文" in tag_lower or "chinese" in tag_lower:
            audio_lang_hint = "zh"
            break

    prefer_english = should_prefer_english(
        language_mode,
        [
            view_data.get("title"),
            view_data.get("desc"),
            view_data.get("dynamic"),
        ],
        fallback=False,
        audio_language=audio_lang_hint,
    )

    pages = _collect_bilibili_pages(view_data)
    if not pages:
        raise VideoProcessingError("未找到可处理的分 P 或 CID")

    total_pages = len(pages)
    results: List[ProcessResult] = []
    video_title = view_data.get("title") or bvid
    base_url = f"https://www.bilibili.com/video/{bvid}"

    for idx, page in enumerate(pages, start=1):
        cid = page.get("cid")
        if not cid:
            continue
        page_number = page.get("page") or idx
        part_title = page.get("part") or f"P{page_number}"
        duration = format_timestamp(page.get("duration")) if page.get("duration") else base_duration
        full_title = video_title
        if total_pages > 1:
            full_title = f"{video_title}｜P{page_number:02d} {part_title}"
        page_url = f"{base_url}?p={page_number}"
        video_id = bvid if total_pages == 1 else f"{bvid}-P{page_number:02d}"

        # 检查文件是否已存在
        expected_filename = f"{video_id}_{slugify(full_title)}.md"
        expected_path = output_dir / expected_filename
        if expected_path.exists():
            _maybe_log(logger, f"⏭️ 跳过已存在：{expected_filename}")
            meta = VideoMeta(
                platform="bilibili",
                video_id=video_id,
                title=full_title,
                uploader=uploader,
                upload_date=upload_date,
                source="skipped",
                url=page_url,
                duration=duration,
                processed_at=datetime.now().strftime("%Y-%m-%d"),
                original_language="Unknown",
                language="Unknown",
            )
            results.append(ProcessResult(platform="bilibili", markdown_path=expected_path, txt_path=None, meta=meta))
            continue

        segments: List[Segment] = []
        subtitle_entry = _fetch_bilibili_subtitle_entry(
            bvid,
            str(cid),
            prefer_english=prefer_english,
            allow_fallback=not prefer_english,
        )
        source = "official_subtitle"
        text_language = "English" if prefer_english else DEFAULT_LANGUAGE
        if subtitle_entry:
            subtitle_lang = subtitle_entry.get("lan") or "unknown"
            convert_flag = is_chinese_lang(subtitle_lang)
            text_language = DEFAULT_LANGUAGE if convert_flag else "English"
            _maybe_log(logger, f"📄 找到官方字幕（{subtitle_lang}），跳过音频转录")
            segments = _download_bilibili_subtitle_segments(
                subtitle_entry,
                convert_to_simplified=convert_flag,
            )
        else:
            _maybe_log(logger, f"⚠️ 未找到官方字幕，将使用 Whisper 转录音频")

        audio_path: Optional[Path] = None
        if not segments:
            source = "whisper"
            convert_flag = not prefer_english
            text_language = DEFAULT_LANGUAGE if convert_flag else "English"
            audio_path = _download_audio(page_url, output_dir, video_id, logger)
            try:
                whisper_lang = "en" if prefer_english else "zh"
                segments = _transcribe_with_whisper(
                    audio_path,
                    model_name,
                    convert_to_simplified=convert_flag,
                    logger=logger,
                    language_code=whisper_lang,
                )
            finally:
                if audio_path and audio_path.exists():
                    audio_path.unlink(missing_ok=True)

        if not segments:
            raise VideoProcessingError(f"分 P {page_number} 未能获取字幕或识别文本")

        meta = VideoMeta(
            platform="bilibili",
            video_id=video_id,
            title=full_title,
            uploader=uploader,
            upload_date=upload_date,
            source=source,
            url=page_url,
            duration=duration,
            processed_at=datetime.now().strftime("%Y-%m-%d"),
            original_language="English" if prefer_english else "Chinese",
            language=text_language,
        )

        markdown_path = generate_markdown(meta, segments, output_dir)
        txt_path = None
        if write_txt:
            legacy_path = write_legacy_txt(segments, output_dir, f"{meta.video_id}_{slugify(meta.title)}")
            try:
                legacy_path.unlink()
            except FileNotFoundError:
                pass
        results.append(ProcessResult(platform="bilibili", markdown_path=markdown_path, txt_path=txt_path, meta=meta))

    if include_collection:
        collection_info = _detect_collection_from_video_input(value, bvid)
        if collection_info:
            coll_type, coll_id = collection_info
            try:
                if coll_type == "fav":
                    urls, title = fetch_bilibili_fav_videos(coll_id, logger=logger)
                elif coll_type == "series":
                    urls, title = fetch_bilibili_series_videos(coll_id, logger=logger)
                else:
                    urls, title = fetch_bilibili_ugc_season_videos(coll_id, logger=logger)
                urls = [url for url in urls if _extract_bvid(url) != bvid]
                if urls:
                    _maybe_log(logger, f"📚 检测到合集《{title}》，共 {len(urls)} 个额外视频，自动处理…")
                    extra_results, failures = _process_video_batch(
                        urls,
                        model_name=model_name,
                        output_root=output_root,
                        language_mode=language_mode,
                        include_collection=False,
                        logger=logger,
                        write_txt=write_txt,
                    )
                    if failures:
                        _maybe_log(logger, f"⚠️ 合集内部分视频处理失败：{failures[:2]}")
                    results.extend(extra_results)
                else:
                    _maybe_log(logger, "⚠️ 合集中没有额外可处理的视频")
            except VideoProcessingError as exc:
                _maybe_log(logger, f"⚠️ 合集处理失败：{exc}")
        else:
            _maybe_log(logger, "ℹ️ 未检测到合集信息，仅处理当前视频。")

    return results


def _normalize_youtube_url(value: str) -> str:
    lowered = value.strip()
    if lowered.startswith("http"):
        return lowered
    return f"https://www.youtube.com/watch?v={lowered}"


def _download_youtube_subtitles(
    video_url: str,
    temp_dir: Path,
    prefer_english: bool,
    allow_fallback: bool,
    logger: Optional[Callable[[str], None]],
) -> Tuple[List[Segment], Optional[str]]:
    _require_ytdlp()
    # 根据 prefer_english 调整语言优先级（优化：优先下载匹配语言的字幕）
    if prefer_english:
        requested_langs = list(dict.fromkeys(ENGLISH_LANGS + PREFERRED_LANGS))
    else:
        requested_langs = list(dict.fromkeys(PREFERRED_LANGS + ENGLISH_LANGS))
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitlesformat": "vtt",
        "subtitleslangs": requested_langs,
        "outtmpl": str(temp_dir / "%(id)s"),
    }
    _maybe_log(logger, "尝试下载 YouTube 字幕…")
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([video_url])
    except Exception as e:
        # 允许部分下载失败（例如请求不存在的语言），只要有任何字幕下载成功即可
        _maybe_log(logger, f"字幕下载时出现错误（将尝试使用已下载的字幕）: {str(e)[:100]}")

    vtt_files = list(temp_dir.glob("*.vtt"))
    lang_map: Dict[str, Path] = {}
    for file in vtt_files:
        parts = file.name.split(".")
        lang = parts[-2] if len(parts) >= 3 else "unknown"
        lang_map[lang] = file

    lang_priority = ENGLISH_LANGS if prefer_english else requested_langs
    fallback_langs: List[str] = []
    if not prefer_english or allow_fallback:
        fallback_langs = [lang for lang in requested_langs if lang not in lang_priority]

    checked_langs = list(dict.fromkeys(lang_priority + fallback_langs))
    for lang in checked_langs:
        file = None
        for key, value in lang_map.items():
            if key.lower() == lang.lower():
                file = value
                break
        if not file:
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        segments = parse_subtitle_text(text)
        if not segments:
            continue
        convert_flag = is_chinese_lang(lang)
        normalized_segments = [
            Segment(seg.start, seg.end, normalize_text(seg.text, convert_flag)) for seg in segments
        ]
        return normalized_segments, lang

    return [], None


def _extract_youtube_info(video_url: str) -> Dict:
    _require_ytdlp()
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except Exception as exc:
        raise VideoProcessingError(f"无法获取 YouTube 视频信息：{exc}") from exc
    if not info:
        raise VideoProcessingError("无法获取 YouTube 视频信息")
    return info


def process_youtube_video(
    value: str,
    model_name: str = "small",
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    write_txt: bool = True,
    logger: Optional[Callable[[str], None]] = None,
    language_mode: str = LANGUAGE_AUTO,
) -> List[ProcessResult]:
    """处理 YouTube 单视频。"""
    language_mode = normalize_language_mode(language_mode)
    video_url = _normalize_youtube_url(value)
    info = _extract_youtube_info(video_url)
    video_id = info.get("id") or re.search(r"v=([\w-]+)", video_url)
    if isinstance(video_id, re.Match):
        video_id = video_id.group(1)
    if not video_id:
        raise VideoProcessingError("无法解析 YouTube 视频 ID")

    uploader = info.get("uploader") or info.get("channel") or "Unknown Channel"
    upload_date = _fmt_upload_date_from_str(info.get("upload_date"))
    duration = format_timestamp(info.get("duration"))
    original_language = info.get("language") or info.get("original_language") or "unknown"
    output_dir = ensure_output_dir("youtube", uploader, output_root)

    video_title = info.get("title") or video_id
    # 检查文件是否已存在
    expected_filename = f"{video_id}_{slugify(video_title)}.md"
    expected_path = output_dir / expected_filename
    if expected_path.exists():
        _maybe_log(logger, f"⏭️ 跳过已存在：{expected_filename}")
        meta = VideoMeta(
            platform="youtube",
            video_id=video_id,
            title=video_title,
            uploader=uploader,
            upload_date=_fmt_upload_date_from_str(info.get("upload_date")),
            source="skipped",
            url=info.get("webpage_url") or video_url,
            duration=duration,
            processed_at=datetime.now().strftime("%Y-%m-%d"),
            original_language=original_language,
            language="Unknown",
        )
        return [ProcessResult(platform="youtube", markdown_path=expected_path, txt_path=None, meta=meta)]

    # YouTube 提供更准确的语言信息
    audio_lang = info.get("audio_language") or info.get("language") or original_language

    prefer_english = should_prefer_english(
        language_mode,
        [
            info.get("title"),
            info.get("description"),
        ],
        fallback=is_english_language(original_language),
        audio_language=audio_lang,
    )

    segments: List[Segment] = []
    subtitle_lang: Optional[str] = None
    convert_flag = True
    text_language = DEFAULT_LANGUAGE
    with tempfile.TemporaryDirectory() as tmp_dir:
        segments, subtitle_lang = _download_youtube_subtitles(
            video_url,
            Path(tmp_dir),
            prefer_english=prefer_english,
            allow_fallback=not prefer_english,
            logger=logger,
        )
    if segments:
        convert_flag = is_chinese_lang(subtitle_lang)
        text_language = DEFAULT_LANGUAGE if convert_flag else "English"
        _maybe_log(logger, f"📄 找到官方字幕（{subtitle_lang}），跳过音频转录")
    else:
        _maybe_log(logger, f"⚠️ 未找到官方字幕，将使用 Whisper 转录音频")
    source = "official_subtitle" if segments else "whisper"

    audio_path: Optional[Path] = None
    if not segments:
        convert_flag = not prefer_english
        audio_path = _download_audio(video_url, output_dir, video_id, logger)
        try:
            whisper_lang = "en" if prefer_english else "zh"
            segments = _transcribe_with_whisper(
                audio_path,
                model_name,
                convert_to_simplified=convert_flag,
                logger=logger,
                language_code=whisper_lang,
            )
            text_language = DEFAULT_LANGUAGE if convert_flag else "English"
        finally:
            if audio_path and audio_path.exists():
                audio_path.unlink(missing_ok=True)

    if not segments:
        raise VideoProcessingError("未能获取到任何字幕或识别文本")

    meta = VideoMeta(
        platform="youtube",
        video_id=video_id,
        title=info.get("title") or video_id,
        uploader=uploader,
        upload_date=upload_date,
        source=source,
        url=info.get("webpage_url") or video_url,
        duration=duration,
        processed_at=datetime.now().strftime("%Y-%m-%d"),
        original_language="English" if prefer_english else original_language,
        language=text_language,
        tags=info.get("tags") or [],
    )

    markdown_path = generate_markdown(meta, segments, output_dir)
    txt_path = None
    if write_txt:
        legacy_path = write_legacy_txt(segments, output_dir, f"{meta.video_id}_{slugify(meta.title)}")
        try:
            legacy_path.unlink()
        except FileNotFoundError:
            pass
    return [ProcessResult(platform="youtube", markdown_path=markdown_path, txt_path=txt_path, meta=meta)]


def _normalize_youtube_channel_url(url: str) -> str:
    """规范化 YouTube 频道 URL，确保获取所有视频而不只是精选内容。"""
    # 移除 /featured, /streams, /shorts 等后缀，使用主页或 /videos
    # 主页会获取所有内容（包括 shorts、播放列表等）
    url = url.rstrip('/')

    # 替换特定页面为主页（会获取更多内容）
    for suffix in ['/featured', '/streams', '/shorts', '/playlists', '/community', '/about']:
        if url.endswith(suffix):
            url = url[:-len(suffix)]
            break

    return url


def _fetch_creator_video_urls_ytdlp(
    channel_url: str,
    platform: str,
    cookie_file: Optional[Path] = None,
) -> List[str]:
    """使用 yt-dlp 获取博主全部视频 URL。"""
    _require_ytdlp()

    # 对于 YouTube，规范化 URL 以获取所有视频
    if platform == "youtube":
        channel_url = _normalize_youtube_channel_url(channel_url)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",  # 提取播放列表中的所有项
        "force_generic_extractor": False,
        "playlistend": None,  # 不限制播放列表结束位置
        "ignoreerrors": True,  # 忽略单个视频错误，继续处理其他视频
    }
    if cookie_file and cookie_file.exists():
        opts["cookiefile"] = str(cookie_file)
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
    except Exception as exc:
        text = str(exc)
        if "Rejected by server (352)" in text:
            hint = (
                "B 站限制访问，请先在浏览器登录后导出 Cookie 到 bilibili_cookie.txt，"
                "并设置环境变量 BILIBILI_COOKIE_FILE 指向该文件。"
            )
            raise VideoProcessingError(f"{text}。{hint}") from exc
        raise VideoProcessingError(f"无法获取创作者视频列表：{exc}") from exc

    if not info:
        return []

    urls: List[str] = []

    def _walk_entries(entry: Dict) -> Iterable[Dict]:
        entries = entry.get("entries") or []
        for item in entries:
            if not item:
                continue
            if item.get("_type") == "playlist":
                yield from _walk_entries(item)
            else:
                yield item

    for entry in _walk_entries(info) if info.get("entries") else []:
        video_url = entry.get("webpage_url") or entry.get("url") or entry.get("id")
        if not video_url:
            continue
        if not video_url.startswith("http"):
            if platform == "youtube":
                video_url = f"https://www.youtube.com/watch?v={video_url}"
            else:
                video_url = f"https://www.bilibili.com/video/{video_url}"
        urls.append(video_url)

    # fallback：当 info 本身是 flat 列表
    if not urls and info.get("webpage_url"):
        entry_url = info.get("webpage_url")
        if entry_url:
            urls.append(entry_url)

    # 去重保持顺序
    seen = set()
    unique_urls: List[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        unique_urls.append(url)
    return unique_urls


class _ThreadSafeLogger:
    """线程安全的日志包装器"""

    def __init__(self, logger: Optional[Callable[[str], None]]):
        self.logger = logger
        self.lock = Lock()

    def log(self, message: str) -> None:
        if self.logger:
            with self.lock:
                self.logger(message)


def _process_single_video(
    video_url: str,
    model_name: str,
    output_root: Path,
    language_mode: str,
    include_collection: bool,
    write_txt: bool,
    logger: Optional[Callable[[str], None]],
) -> Tuple[Optional[List[ProcessResult]], Optional[str]]:
    """处理单个视频（用于并发）"""
    try:
        platform = detect_platform(video_url) or ("youtube" if "youtu" in video_url else "bilibili")
        if platform == "bilibili":
            processed = process_bilibili_video(
                video_url,
                model_name=model_name,
                output_root=output_root,
                logger=logger,
                include_collection=include_collection,
                language_mode=language_mode,
                write_txt=write_txt,
            )
        elif platform == "youtube":
            processed = process_youtube_video(
                video_url,
                model_name=model_name,
                output_root=output_root,
                logger=logger,
                language_mode=language_mode,
                write_txt=write_txt,
            )
        else:
            raise VideoProcessingError("无法识别视频平台")

        if not isinstance(processed, list):
            processed = [processed]
        return processed, None
    except VideoProcessingError as exc:
        return None, f"{video_url} -> {exc}"
    except Exception as exc:  # pragma: no cover
        return None, f"{video_url} -> 未知错误：{exc}"


def _process_video_batch(
    video_urls: List[str],
    model_name: str,
    output_root: Path,
    language_mode: str = LANGUAGE_AUTO,
    include_collection: bool = False,
    write_txt: bool = True,
    logger: Optional[Callable[[str], None]] = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    enable_concurrent: bool = ENABLE_CONCURRENT,
) -> Tuple[List[ProcessResult], List[str]]:
    """批量处理视频，支持并发处理"""
    if not video_urls:
        raise VideoProcessingError("未获取到任何视频，可能链接无效或不可访问")

    successful: List[ProcessResult] = []
    skipped_existing: List[ProcessResult] = []  # 已存在的文件
    failures: List[str] = []
    total = len(video_urls)

    # 限制最大并发数
    max_workers = min(max(1, max_workers), MAX_WORKERS_LIMIT)

    # 如果只有1-2个视频或禁用并发，使用顺序处理
    if total <= 2 or not enable_concurrent:
        _maybe_log(logger, f"共获取 {total} 个视频，开始顺序处理…")
        for idx, video_url in enumerate(video_urls, start=1):
            _maybe_log(logger, f"==> 正在处理 {idx}/{total}：{video_url}")
            processed, error = _process_single_video(
                video_url, model_name, output_root, language_mode, include_collection, write_txt, logger
            )
            if processed:
                # 检查是否是已存在的文件
                is_existing = all(p.meta.source == "skipped" for p in processed)
                if is_existing:
                    skipped_existing.extend(processed)
                    last_path = processed[-1].markdown_path.name if processed else "unknown"
                    _maybe_log(logger, f"   ⏭️ 已存在：{last_path}")
                else:
                    successful.extend(processed)
                    last_path = processed[-1].markdown_path.name if processed else "unknown"
                    _maybe_log(logger, f"   ✅ 完成：{last_path}")
            else:
                failures.append(error or f"{video_url} -> 未知错误")
                _maybe_log(logger, f"   ⚠️ 跳过：{error}")
    else:
        # 并发处理
        _maybe_log(logger, f"共获取 {total} 个视频，开始并发处理（{max_workers} 线程）…")
        safe_logger = _ThreadSafeLogger(logger)
        completed_count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_url = {
                executor.submit(
                    _process_single_video,
                    url,
                    model_name,
                    output_root,
                    language_mode,
                    include_collection,
                    write_txt,
                    safe_logger.log,
                ): url
                for url in video_urls
            }

            # 处理完成的任务
            for future in as_completed(future_to_url):
                video_url = future_to_url[future]
                completed_count += 1

                try:
                    processed, error = future.result()
                    if processed:
                        # 检查是否是已存在的文件
                        is_existing = all(p.meta.source == "skipped" for p in processed)
                        last_path = processed[-1].markdown_path.name if processed else "unknown"
                        if is_existing:
                            skipped_existing.extend(processed)
                            safe_logger.log(f"⏭️ [{completed_count}/{total}] 已存在：{last_path}")
                        else:
                            successful.extend(processed)
                            safe_logger.log(f"✅ [{completed_count}/{total}] 完成：{last_path}")
                    else:
                        failures.append(error or f"{video_url} -> 未知错误")
                        safe_logger.log(f"⚠️ [{completed_count}/{total}] 跳过：{error}")
                except Exception as exc:  # pragma: no cover
                    error_msg = f"{video_url} -> 执行异常：{exc}"
                    failures.append(error_msg)
                    safe_logger.log(f"⚠️ [{completed_count}/{total}] 异常：{exc}")

    # 显示详细统计
    _maybe_log(logger, "")
    _maybe_log(logger, "=" * 60)
    _maybe_log(logger, f"📊 批量处理完成统计：")
    _maybe_log(logger, f"   总视频数：{total}")
    _maybe_log(logger, f"   ✅ 新处理：{len(successful)}")
    _maybe_log(logger, f"   ⏭️ 已存在（跳过）：{len(skipped_existing)}")
    _maybe_log(logger, f"   ⚠️ 失败/错误：{len(failures)}")
    _maybe_log(logger, "=" * 60)

    # 合并成功和已跳过的结果返回
    all_results = successful + skipped_existing
    return all_results, failures


def export_creator_videos(
    creator_url: str,
    model_name: str = "small",
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    limit: int = 0,
    language_mode: str = LANGUAGE_AUTO,
    logger: Optional[Callable[[str], None]] = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    enable_concurrent: bool = ENABLE_CONCURRENT,
) -> Tuple[List[ProcessResult], List[str]]:
    """批量导出创作者全部视频，支持并发处理，返回成功结果与失败原因。"""
    platform = detect_platform(creator_url or "")
    if platform not in {"bilibili", "youtube"}:
        raise VideoProcessingError("无法识别平台，目前仅支持 B 站和 YouTube")

    bilibili_cookie = Path(os.getenv("BILIBILI_COOKIE_FILE", "bilibili_cookie.txt")).expanduser()
    youtube_cookie = Path(os.getenv("YOUTUBE_COOKIE_FILE", "youtube_cookie.txt")).expanduser()
    cookie_file = bilibili_cookie if platform == "bilibili" else youtube_cookie
    if not cookie_file.exists():
        cookie_file = None

    resolved_mid = _resolve_bilibili_mid(creator_url) if platform == "bilibili" else None
    video_urls: List[str] = []
    if platform == "bilibili" and resolved_mid:
        try:
            video_urls = fetch_bilibili_videos_via_api(resolved_mid, logger=logger)
        except VideoProcessingError as exc:
            _maybe_log(logger, f"⚠️ 官方 API 获取失败：{exc}，尝试 yt-dlp…")

    if not video_urls:
        video_urls = _fetch_creator_video_urls_ytdlp(creator_url, platform, cookie_file=cookie_file)
    if not video_urls:
        raise VideoProcessingError("未获取到任何视频，可能是主页不可访问或无公开视频")

    if limit and limit > 0:
        video_urls = video_urls[:limit]

    return _process_video_batch(
        video_urls,
        model_name,
        output_root,
        language_mode=language_mode,
        include_collection=False,
        logger=logger,
        max_workers=max_workers,
        enable_concurrent=enable_concurrent,
    )


def export_bilibili_collection_videos(
    collection_url: str,
    model_name: str = "small",
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    limit: int = 0,
    language_mode: str = LANGUAGE_AUTO,
    logger: Optional[Callable[[str], None]] = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    enable_concurrent: bool = ENABLE_CONCURRENT,
) -> Tuple[List[ProcessResult], List[str]]:
    info = detect_bilibili_collection(collection_url)
    if not info:
        # 允许用户直接粘贴合集中的单个 BV 链接
        try:
            bvid = _extract_bvid(collection_url)
        except VideoProcessingError as exc:
            raise VideoProcessingError("无法识别 B 站合集/收藏夹链接") from exc
        inferred = _detect_collection_from_video_input(collection_url, bvid)
        if not inferred:
            # 检查是否为多P视频（不是合集，而是单个视频的多个分P）
            try:
                view_data = _fetch_bilibili_view(bvid)
                pages_count = len(view_data.get("pages", []))
                if pages_count > 1:
                    _maybe_log(logger, f"⚠️ 检测到这是一个多分P视频（共{pages_count}个分P），非合集。自动切换到单视频处理模式...")
                    results = process_bilibili_video(
                        collection_url,
                        model_name=model_name,
                        output_root=output_root,
                        logger=logger,
                        include_collection=False,
                        language_mode=language_mode,
                        write_txt=True,
                    )
                    return results, []
            except Exception:
                pass
            raise VideoProcessingError("无法识别 B 站合集/收藏夹链接，请确认链接是否正确")
        info = inferred
    coll_type, coll_id = info

    if coll_type == "fav":
        video_urls, title = fetch_bilibili_fav_videos(coll_id, logger=logger)
    elif coll_type == "series":
        video_urls, title = fetch_bilibili_series_videos(coll_id, logger=logger)
    else:
        video_urls, title = fetch_bilibili_ugc_season_videos(coll_id, logger=logger)

    if not video_urls:
        raise VideoProcessingError("合集内未找到任何视频，或访问受限")

    if limit and limit > 0:
        video_urls = video_urls[:limit]

    _maybe_log(logger, f"合集《{title}》共 {len(video_urls)} 个视频。")
    return _process_video_batch(
        video_urls,
        model_name,
        output_root,
        language_mode=language_mode,
        include_collection=False,
        logger=logger,
        max_workers=max_workers,
        enable_concurrent=enable_concurrent,
    )
