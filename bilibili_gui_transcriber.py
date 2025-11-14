#!/usr/bin/env python3
"""Tkinter 图形界面：支持 B 站 / YouTube 视频文字稿提取。"""
from __future__ import annotations

import threading
import tkinter as tk
from typing import List
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from utils import (
    DEFAULT_MAX_WORKERS,
    ENABLE_CONCURRENT,
    LANGUAGE_AUTO,
    ProcessResult,
    VideoProcessingError,
    detect_bilibili_collection,
    detect_platform,
    export_bilibili_collection_videos,
    export_creator_videos,
    normalize_language_mode,
    process_bilibili_video,
    process_youtube_video,
)


class BilibiliTranscriberApp:
    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        master.title("🎬 VideoScribe - 视频转录助手 v2.0")
        master.geometry("800x550")
        master.resizable(True, True)

        # 设置样式
        style = ttk.Style()
        style.theme_use('default')
        style.configure('TButton', padding=6, relief="flat", background="#4A90E2")
        style.configure('TCombobox', padding=3)

        self._build_widgets()

    def _build_widgets(self) -> None:
        pad = 12

        # === 输入区域 ===
        input_frame = tk.LabelFrame(self.master, text=" 🔗 视频链接 ", font=("Arial", 10, "bold"), padx=pad, pady=pad)
        input_frame.pack(fill=tk.X, padx=pad, pady=(pad, 5))

        self.entry_var = tk.StringVar()
        entry = tk.Entry(input_frame, textvariable=self.entry_var, font=("Arial", 10), relief="solid", bd=1)
        entry.pack(fill=tk.X, ipady=4)
        entry.bind('<Return>', lambda e: self.start_process())

        # === 设置区域 ===
        settings_frame = tk.LabelFrame(self.master, text=" ⚙️ 处理设置 ", font=("Arial", 10, "bold"), padx=pad, pady=pad)
        settings_frame.pack(fill=tk.X, padx=pad, pady=5)

        # 第一行：模式和模型
        row1 = tk.Frame(settings_frame)
        row1.pack(fill=tk.X, pady=3)

        tk.Label(row1, text="模式：", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 5))
        self.mode_var = tk.StringVar(value="单个视频")
        self.mode_options = {
            "📹 单个视频": "single",
            "👤 创作者批量": "creator",
            "📚 合集批量": "collection",
        }
        mode_box = ttk.Combobox(
            row1,
            textvariable=self.mode_var,
            values=list(self.mode_options.keys()),
            state="readonly",
            width=16,
            font=("Arial", 9)
        )
        mode_box.current(0)
        mode_box.pack(side=tk.LEFT, padx=(0, 15))
        mode_box.bind('<<ComboboxSelected>>', self._on_mode_change)

        tk.Label(row1, text="Whisper 模型：", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 5))
        self.model_var = tk.StringVar(value="small")
        model_box = ttk.Combobox(
            row1,
            textvariable=self.model_var,
            values=["tiny", "base", "small", "medium", "large"],
            width=10,
            state="readonly",
            font=("Arial", 9)
        )
        model_box.pack(side=tk.LEFT, padx=(0, 15))

        tk.Label(row1, text="输出语言：", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 5))
        self.lang_var = tk.StringVar(value="自动")
        self.lang_options = {
            "自动": LANGUAGE_AUTO,
            "中文": "zh",
            "英文": "en",
        }
        lang_box = ttk.Combobox(
            row1,
            textvariable=self.lang_var,
            values=list(self.lang_options.keys()),
            state="readonly",
            width=8,
            font=("Arial", 9)
        )
        lang_box.current(0)
        lang_box.pack(side=tk.LEFT)

        # 第二行：选项
        row2 = tk.Frame(settings_frame)
        row2.pack(fill=tk.X, pady=3)

        self.include_collection_var = tk.BooleanVar(value=True)
        self.collection_check = tk.Checkbutton(
            row2,
            text="单个视频自动处理合集/分P",
            variable=self.include_collection_var,
            font=("Arial", 9)
        )
        self.collection_check.pack(side=tk.LEFT)

        # 并发配置
        tk.Label(row2, text="并发数：", font=("Arial", 9)).pack(side=tk.LEFT, padx=(15, 5))
        self.concurrent_var = tk.IntVar(value=DEFAULT_MAX_WORKERS)
        concurrent_spinbox = tk.Spinbox(
            row2,
            from_=1,
            to=8,
            textvariable=self.concurrent_var,
            width=5,
            font=("Arial", 9),
            state="readonly"
        )
        concurrent_spinbox.pack(side=tk.LEFT)

        self.enable_concurrent_var = tk.BooleanVar(value=ENABLE_CONCURRENT)
        concurrent_check = tk.Checkbutton(
            row2,
            text="启用并发",
            variable=self.enable_concurrent_var,
            font=("Arial", 9),
            command=self._on_concurrent_toggle
        )
        concurrent_check.pack(side=tk.LEFT, padx=(5, 0))

        # 提示标签
        self.hint_label = tk.Label(
            row2,
            text="💡 提示：多P视频会自动拆分为多个文件",
            font=("Arial", 9),
            fg="#666"
        )
        self.hint_label.pack(side=tk.LEFT, padx=(15, 0))

        # === 按钮区域 ===
        button_frame = tk.Frame(self.master)
        button_frame.pack(fill=tk.X, padx=pad, pady=5)

        self.start_button = tk.Button(
            button_frame,
            text="🚀 开始处理",
            command=self.start_process,
            font=("Arial", 11, "bold"),
            bg="#4CAF50",
            fg="white",
            activebackground="#45a049",
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2"
        )
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))

        self.clear_button = tk.Button(
            button_frame,
            text="🗑️ 清空日志",
            command=self._clear_log,
            font=("Arial", 10),
            bg="#f44336",
            fg="white",
            activebackground="#da190b",
            relief="flat",
            padx=15,
            pady=6,
            cursor="hand2"
        )
        self.clear_button.pack(side=tk.LEFT)

        # 状态指示器
        self.status_label = tk.Label(
            button_frame,
            text="⚪ 就绪",
            font=("Arial", 10, "bold"),
            fg="#4CAF50"
        )
        self.status_label.pack(side=tk.RIGHT, padx=10)

        # === 日志区域 ===
        log_frame = tk.LabelFrame(self.master, text=" 📋 处理日志 ", font=("Arial", 10, "bold"), padx=pad, pady=pad)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=pad, pady=(5, pad))

        self.log_box = ScrolledText(
            log_frame,
            state=tk.DISABLED,
            wrap=tk.WORD,
            font=("Courier New", 9),
            bg="#f5f5f5",
            relief="solid",
            bd=1
        )
        self.log_box.pack(fill=tk.BOTH, expand=True)

        # 配置日志颜色标签
        self.log_box.tag_configure("success", foreground="#4CAF50", font=("Courier New", 9, "bold"))
        self.log_box.tag_configure("error", foreground="#f44336", font=("Courier New", 9, "bold"))
        self.log_box.tag_configure("warning", foreground="#FF9800", font=("Courier New", 9, "bold"))
        self.log_box.tag_configure("info", foreground="#2196F3", font=("Courier New", 9, "bold"))

    def _on_mode_change(self, event=None) -> None:
        """当模式改变时更新提示"""
        mode = self.mode_options.get(self.mode_var.get(), "single")
        hints = {
            "single": "💡 提示：多P视频会自动拆分为多个文件",
            "creator": "💡 提示：批量处理建议启用并发（3-5线程）",
            "collection": "💡 提示：批量处理建议启用并发（3-5线程）"
        }
        self.hint_label.config(text=hints.get(mode, ""))

    def _on_concurrent_toggle(self) -> None:
        """当并发开关切换时更新提示"""
        if self.enable_concurrent_var.get():
            workers = self.concurrent_var.get()
            self.log(f"✅ 已启用并发处理（{workers} 线程）")
        else:
            self.log("⚪ 已禁用并发处理，将使用顺序处理")

    def _clear_log(self) -> None:
        """清空日志"""
        self.log_box.config(state=tk.NORMAL)
        self.log_box.delete("1.0", tk.END)
        self.log_box.config(state=tk.DISABLED)
        self.log("日志已清空")

    def log(self, message: str) -> None:
        """带颜色的日志输出"""
        def _append() -> None:
            self.log_box.config(state=tk.NORMAL)

            # 根据消息前缀选择颜色标签
            tag = None
            if message.startswith("✅") or "成功" in message or "完成" in message:
                tag = "success"
            elif message.startswith("❌") or "失败" in message or "错误" in message:
                tag = "error"
            elif message.startswith("⚠️") or "警告" in message or "检测到" in message:
                tag = "warning"
            elif message.startswith(("🎬", "📚", "📦", "🧠", "⏬", "ℹ️")):
                tag = "info"

            if tag:
                self.log_box.insert(tk.END, message + "\n", tag)
            else:
                self.log_box.insert(tk.END, message + "\n")

            self.log_box.see(tk.END)
            self.log_box.config(state=tk.DISABLED)

        self.master.after(0, _append)

    def _update_status(self, status: str, color: str = "#4CAF50") -> None:
        """更新状态指示器"""
        def _update() -> None:
            self.status_label.config(text=status, fg=color)
        self.master.after(0, _update)

    def start_process(self) -> None:
        raw_input = self.entry_var.get().strip()
        model_name = self.model_var.get()
        if not raw_input:
            messagebox.showwarning("⚠️ 提示", "请先输入视频链接或 BV 号")
            return

        # 更新UI状态
        self.start_button.config(state=tk.DISABLED, bg="#999")
        self.clear_button.config(state=tk.DISABLED, bg="#999")
        self._update_status("🔄 处理中...", "#FF9800")

        self.log_box.config(state=tk.NORMAL)
        self.log_box.delete("1.0", tk.END)
        self.log_box.config(state=tk.DISABLED)

        language_mode = normalize_language_mode(self.lang_options.get(self.lang_var.get(), LANGUAGE_AUTO))
        include_collection = self.include_collection_var.get()

        self.log(f"{'='*50}")
        self.log(f"🚀 开始处理: {raw_input}")
        self.log(f"⚙️ 模型: {model_name} | 语言: {self.lang_var.get()}")
        self.log(f"{'='*50}\n")

        thread = threading.Thread(
            target=self.run_task,
            args=(raw_input, model_name, language_mode, include_collection),
            daemon=True,
        )
        thread.start()

    def run_task(self, raw_input: str, model_name: str, language_mode: str, include_collection: bool) -> None:
        try:
            mode_key = self.mode_options.get(self.mode_var.get(), "single")
            if mode_key == "creator":
                self._run_creator(raw_input, model_name, language_mode)
            elif mode_key == "collection":
                self._run_collection(raw_input, model_name, language_mode)
            else:
                self._run_single(raw_input, model_name, language_mode, include_collection)
        except VideoProcessingError as exc:
            self.log(f"❌ {exc}")
            self.finish(success=False, message=str(exc))
        except Exception as exc:  # pragma: no cover
            self.log(f"❌ 未知错误：{exc}")
            self.finish(success=False, message=f"未知错误：{exc}")

    def _run_single(self, raw_input: str, model_name: str, language_mode: str, include_collection: bool) -> None:
        platform = detect_platform(raw_input)
        if platform == "bilibili":
            self.log("🎬 正在处理 B 站视频…")
            results = process_bilibili_video(
                raw_input,
                model_name=model_name,
                logger=self.log,
                include_collection=include_collection,
                language_mode=language_mode,
            )
        elif platform == "youtube":
            self.log("🎬 正在处理 YouTube 视频…")
            results = process_youtube_video(
                raw_input,
                model_name=model_name,
                logger=self.log,
                language_mode=language_mode,
            )
        else:
            raise VideoProcessingError("无法识别平台，目前仅支持 B 站和 YouTube")
        self._handle_success(results)

    def _run_creator(self, raw_input: str, model_name: str, language_mode: str) -> None:
        max_workers = self.concurrent_var.get()
        enable_concurrent = self.enable_concurrent_var.get()
        self.log(f"📦 批量导出模式：将处理创作者全部视频（并发：{max_workers if enable_concurrent else '禁用'}）…")
        results, failures = export_creator_videos(
            raw_input,
            model_name=model_name,
            language_mode=language_mode,
            logger=self.log,
            max_workers=max_workers,
            enable_concurrent=enable_concurrent,
        )
        self._summarize_batch(results, failures)

    def _run_collection(self, raw_input: str, model_name: str, language_mode: str) -> None:
        if detect_platform(raw_input) != "bilibili":
            raise VideoProcessingError("合集批量仅支持 B 站链接")
        max_workers = self.concurrent_var.get()
        enable_concurrent = self.enable_concurrent_var.get()
        self.log(f"📚 合集导出模式：正在遍历合集内全部视频（并发：{max_workers if enable_concurrent else '禁用'}）…")
        results, failures = export_bilibili_collection_videos(
            raw_input,
            model_name=model_name,
            language_mode=language_mode,
            logger=self.log,
            max_workers=max_workers,
            enable_concurrent=enable_concurrent,
        )
        self._summarize_batch(results, failures)

    def _summarize_batch(self, results: List[ProcessResult], failures: List[str]) -> None:
        if not results:
            raise VideoProcessingError("未成功导出任何视频，请检查链接或稍后重试")
        summary_lines = [
            f"成功 {len(results)} 个，失败 {len(failures)} 个。",
            f"示例输出：{results[0].markdown_path}",
        ]
        if failures:
            summary_lines.append("失败示例：")
            summary_lines.extend(f" - {fail}" for fail in failures[:5])
        self.finish(success=True, message="\n".join(summary_lines))

    def _handle_success(self, results: List[ProcessResult]) -> None:
        if not isinstance(results, list):
            results = [results]
        lines: List[str] = []
        for res in results:
            line = f"Markdown 已生成：{res.markdown_path}"
            if res.txt_path:
                line += f"（TXT：{res.txt_path}）"
            self.log(f"✅ {line}")
            lines.append(line)
        self.finish(success=True, message="\n".join(lines))

    def finish(self, success: bool, message: str) -> None:
        def _finalize() -> None:
            # 恢复按钮状态
            self.start_button.config(state=tk.NORMAL, bg="#4CAF50")
            self.clear_button.config(state=tk.NORMAL, bg="#f44336")

            # 更新状态指示器
            if success:
                self._update_status("✅ 完成", "#4CAF50")
                self.log(f"\n{'='*50}")
                self.log("✅ 处理成功！")
                self.log(f"{'='*50}")
                messagebox.showinfo("✅ 处理完成", message)
            else:
                self._update_status("❌ 失败", "#f44336")
                self.log(f"\n{'='*50}")
                self.log("❌ 处理失败")
                self.log(f"{'='*50}")
                messagebox.showerror("❌ 处理失败", message)

        self.master.after(0, _finalize)


def main() -> None:
    root = tk.Tk()
    app = BilibiliTranscriberApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
