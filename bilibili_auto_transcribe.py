#!/usr/bin/env python3
"""命令行入口：支持 B 站 / YouTube 单视频文字稿提取。"""
from __future__ import annotations

import argparse
import sys
from typing import Iterable, List

from utils import (
    ProcessResult,
    VideoProcessingError,
    detect_platform,
    normalize_language_mode,
    process_bilibili_video,
    process_youtube_video,
)


def log(message: str) -> None:
    print(message, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="B 站 / YouTube 视频字幕提取")
    parser.add_argument("video", help="BV 号 / 视频链接")
    parser.add_argument("model", nargs="?", default="small", help="Whisper 模型名，默认 small")
    parser.add_argument(
        "--lang",
        choices=["auto", "zh", "en"],
        default="auto",
        help="输出语言：auto(默认)/zh/en",
    )
    parser.add_argument(
        "--include-collection",
        action="store_true",
        help="单个 B 站视频若属于合集，则自动导出合集内其余视频",
    )
    parser.add_argument(
        "--no-txt",
        action="store_true",
        help="仅生成 Markdown，不生成兼容 TXT",
    )
    args = parser.parse_args()

    raw_input = args.video
    model_name = args.model
    language_mode = normalize_language_mode(args.lang)

    platform = detect_platform(raw_input)
    if platform not in {"bilibili", "youtube"}:
        log("❌ 无法识别平台，目前仅支持 B 站和 YouTube。")
        sys.exit(1)

    log(f"🎬 正在处理 {platform} 视频…")

    try:
        if platform == "bilibili":
            results = process_bilibili_video(
                raw_input,
                model_name=model_name,
                logger=log,
                include_collection=args.include_collection,
                language_mode=language_mode,
                write_txt=not args.no_txt,
            )
        else:
            results = process_youtube_video(
                raw_input,
                model_name=model_name,
                logger=log,
                language_mode=language_mode,
                write_txt=not args.no_txt,
            )
        _report_success(results)
    except VideoProcessingError as exc:
        log(f"❌ {exc}")
        sys.exit(1)
    except Exception as exc:  # pragma: no cover
        log(f"❌ 未知错误：{exc}")
        sys.exit(1)


def _report_success(results: Iterable[ProcessResult]) -> None:
    results = list(results)
    if not results:
        log("⚠️ 未生成任何输出文件")
        return
    for res in results:
        log(f"✅ Markdown：{res.markdown_path}")
        if res.txt_path:
            log(f"📝 TXT：{res.txt_path}")
    log("✨ 完成")


if __name__ == "__main__":
    main()
