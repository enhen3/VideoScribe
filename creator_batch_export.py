#!/usr/bin/env python3
"""批量导出某个 UP/频道全部视频的文字稿。"""
from __future__ import annotations

import argparse
import sys
from typing import List

from utils import (
    VideoProcessingError,
    detect_bilibili_collection,
    detect_platform,
    export_bilibili_collection_videos,
    export_creator_videos,
)


def log(msg: str) -> None:
    print(msg, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="批量导出 B 站/YouTube 创作者主页或合集的全部视频文字稿")
    parser.add_argument("creator_url", help="UP 主主页 / 合集链接 或 YouTube 频道主页")
    parser.add_argument("--model", default="small", help="Whisper 模型名，默认 small")
    parser.add_argument("--limit", type=int, default=0, help="最多处理的视频数量（0 表示全部）")
    parser.add_argument(
        "--lang",
        choices=["auto", "zh", "en"],
        default="auto",
        help="输出语言偏好：auto/zh/en",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=3,
        help="并发处理线程数（1-8），默认 3",
    )
    parser.add_argument(
        "--no-concurrent",
        action="store_true",
        help="禁用并发处理，使用顺序处理",
    )
    args = parser.parse_args()

    platform = detect_platform(args.creator_url)
    if platform not in {"bilibili", "youtube"}:
        log("❌ 无法识别平台，目前仅支持 B 站和 YouTube。")
        sys.exit(1)

    collection_info = detect_bilibili_collection(args.creator_url) if platform == "bilibili" else None

    # 并发配置
    max_workers = max(1, min(args.max_workers, 8))  # 限制在 1-8 范围内
    enable_concurrent = not args.no_concurrent

    try:
        if collection_info:
            results, failures = export_bilibili_collection_videos(
                args.creator_url,
                model_name=args.model,
                language_mode=args.lang,
                limit=args.limit,
                logger=log,
                max_workers=max_workers,
                enable_concurrent=enable_concurrent,
            )
        else:
            results, failures = export_creator_videos(
                args.creator_url,
                model_name=args.model,
                language_mode=args.lang,
                limit=args.limit,
                logger=log,
                max_workers=max_workers,
                enable_concurrent=enable_concurrent,
            )
    except VideoProcessingError as exc:
        log(f"❌ {exc}")
        sys.exit(1)
    except Exception as exc:  # pragma: no cover
        log(f"❌ 未知错误：{exc}")
        sys.exit(1)

    log("=== 汇总 ===")
    log(f"成功 {len(results)} 个：")
    for item in results:
        msg = f" - {item.meta.title} ({item.meta.video_id}) -> {item.markdown_path}"
        log(msg)
    log(f"失败 {len(failures)} 个：")
    for fail in failures:
        log(f" - {fail}")


if __name__ == "__main__":
    main()
