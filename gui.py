"""
Tkinter 桌面 GUI 入口。
"""
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import logging

from merger.utils import ensure_directories, setup_logging
from main import run_pipeline


class TextHandler(logging.Handler):
    """
    将日志写入 Tkinter 文本框的 Handler，线程安全使用 after。
    """

    def __init__(self, widget: tk.Text):
        super().__init__()
        self.widget = widget
        self.widget.configure(state=tk.DISABLED)

    def emit(self, record):
        msg = self.format(record)
        self.widget.after(0, self._append, msg)

    def _append(self, msg: str):
        self.widget.configure(state=tk.NORMAL)
        self.widget.insert(tk.END, msg + "\n")
        self.widget.see(tk.END)
        self.widget.configure(state=tk.DISABLED)


class App(tk.Tk):
    """
    主应用窗口。
    """

    def __init__(self):
        super().__init__()
        self.title("video_merge_voiceover")
        self.geometry("820x640")
        ensure_directories()

        # 变量
        self.input_files = []
        self.voice_file = tk.StringVar()
        self.text_file = tk.StringVar()
        self.output_format = tk.StringVar(value="mp4")
        self.merge_mode = tk.StringVar(value="A")
        self.voice_mix_mode = tk.StringVar(value="B")
        self.tts_voice = tk.StringVar(value="A")
        self.use_voice = tk.BooleanVar(value=False)
        self.output_name = tk.StringVar(value="merged_video")

        # 布局
        self._build_ui()

        # 日志
        self.logger = setup_logging()
        handler = TextHandler(self.log_text)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        self.logger.addHandler(handler)

    def _build_ui(self):
        """
        构建界面控件。
        """
        # 视频选择
        frame_files = ttk.LabelFrame(self, text="输入视频文件")
        frame_files.pack(fill=tk.X, padx=10, pady=5)
        btn_select = ttk.Button(frame_files, text="选择视频", command=self.select_videos)
        btn_select.pack(side=tk.LEFT, padx=5, pady=5)
        self.listbox = tk.Listbox(frame_files, height=5)
        self.listbox.pack(fill=tk.X, padx=5, pady=5, expand=True)

        # 配音与文本
        frame_voice = ttk.LabelFrame(self, text="配音 / 文本")
        frame_voice.pack(fill=tk.X, padx=10, pady=5)
        ttk.Checkbutton(frame_voice, text="启用配音", variable=self.use_voice).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Button(frame_voice, text="选择配音文件", command=self.select_voice_file).grid(row=1, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(frame_voice, textvariable=self.voice_file, width=70).grid(row=1, column=1, padx=5, pady=5)

        ttk.Button(frame_voice, text="选择配音文本文件", command=self.select_text_file).grid(row=2, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(frame_voice, textvariable=self.text_file, width=70).grid(row=2, column=1, padx=5, pady=5)

        # 拼接模式
        frame_merge = ttk.LabelFrame(self, text="拼接模式")
        frame_merge.pack(fill=tk.X, padx=10, pady=5)
        for idx, (text, value) in enumerate(
            [
                ("A: 原始分辨率直接拼接", "A"),
                ("B: 缩放到最大分辨率", "B"),
                ("C: 缩放到第一个视频分辨率", "C"),
            ]
        ):
            ttk.Radiobutton(frame_merge, text=text, value=value, variable=self.merge_mode).grid(
                row=0, column=idx, padx=10, pady=5, sticky="w"
            )

        # 配音混合模式
        frame_mix = ttk.LabelFrame(self, text="配音混合模式")
        frame_mix.pack(fill=tk.X, padx=10, pady=5)
        for idx, (text, value) in enumerate(
            [
                ("A: 覆盖原音轨", "A"),
                ("B: 混合，原音量减半", "B"),
                ("C: 原音轨 + 配音背景 (30%)", "C"),
            ]
        ):
            ttk.Radiobutton(frame_mix, text=text, value=value, variable=self.voice_mix_mode).grid(
                row=0, column=idx, padx=10, pady=5, sticky="w"
            )

        # TTS 声音与输出格式
        frame_opts = ttk.LabelFrame(self, text="TTS 与输出格式")
        frame_opts.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(frame_opts, text="TTS 声音").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Combobox(frame_opts, textvariable=self.tts_voice, values=["A", "B", "C"], width=5).grid(
            row=0, column=1, padx=5, pady=5
        )
        ttk.Label(frame_opts, text="输出格式").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        ttk.Combobox(frame_opts, textvariable=self.output_format, values=["mp4", "mov", "mkv"], width=7).grid(
            row=0, column=3, padx=5, pady=5
        )
        ttk.Label(frame_opts, text="输出文件名（不含后缀）").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(frame_opts, textvariable=self.output_name, width=40).grid(row=1, column=1, columnspan=3, padx=5, pady=5, sticky="w")

        # 按钮
        frame_actions = ttk.Frame(self)
        frame_actions.pack(fill=tk.X, padx=10, pady=5)
        self.btn_start = ttk.Button(frame_actions, text="开始合成", command=self.start_merge)
        self.btn_start.pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_actions, text="打开输出目录", command=self.open_output_dir).pack(side=tk.LEFT, padx=5)

        # 日志输出
        frame_log = ttk.LabelFrame(self, text="日志输出")
        frame_log.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.log_text = tk.Text(frame_log, height=18)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def select_videos(self):
        """
        选择多个视频文件并更新列表。
        """
        files = filedialog.askopenfilenames(
            title="选择视频",
            filetypes=[("Video Files", "*.mp4;*.mov;*.mkv"), ("All Files", "*.*")],
        )
        if files:
            self.input_files = list(files)
            self.listbox.delete(0, tk.END)
            for f in self.input_files:
                self.listbox.insert(tk.END, f)

    def select_voice_file(self):
        """
        选择配音音频文件。
        """
        file = filedialog.askopenfilename(
            title="选择配音文件",
            filetypes=[("Audio Files", "*.mp3;*.wav"), ("All Files", "*.*")],
        )
        if file:
            self.voice_file.set(file)

    def select_text_file(self):
        """
        选择包含配音文本的文件。
        """
        file = filedialog.askopenfilename(
            title="选择文本文件",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if file:
            self.text_file.set(file)

    def start_merge(self):
        """
        启动合成线程，避免阻塞界面。
        """
        if not self.input_files:
            messagebox.showwarning("提示", "请至少选择一个视频文件。")
            return

        output_filename = f"{self.output_name.get().strip()}.{self.output_format.get()}"
        output_path = os.path.join("output", output_filename)

        self.btn_start.config(state=tk.DISABLED)
        thread = threading.Thread(
            target=self._run_task,
            args=(
                output_path,
            ),
            daemon=True,
        )
        thread.start()

    def _run_task(self, output_path: str):
        """
        线程内执行合成，并在完成后恢复按钮。
        """
        try:
            run_pipeline(
                inputs=self.input_files,
                output=output_path,
                merge_mode=self.merge_mode.get(),
                use_voice=self.use_voice.get(),
                voice_path=self.voice_file.get(),
                voice_text_file=self.text_file.get(),
                voice_mix_mode=self.voice_mix_mode.get(),
                tts_voice=self.tts_voice.get(),
                output_format=self.output_format.get(),
                logger=self.logger,
            )
            messagebox.showinfo("完成", f"合成完成，输出：{output_path}")
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.exception("合成失败：%s", exc)
            messagebox.showerror("错误", f"处理失败：{exc}")
        finally:
            self.btn_start.config(state=tk.NORMAL)

    def open_output_dir(self):
        """
        打开输出目录。
        """
        ensure_directories()
        output_dir = os.path.abspath("output")
        try:
            if os.name == "nt":
                os.startfile(output_dir)  # type: ignore[attr-defined]
            else:
                os.system(f'xdg-open "{output_dir}"')
        except Exception as exc:  # pylint: disable=broad-except
            messagebox.showerror("错误", f"无法打开目录：{exc}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
