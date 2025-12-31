"""
通用工具函数：
- 路径与目录安全处理（适配桌面 / EXE）
- ffmpeg 配置（优先使用内置占位目录，兼容打包）
- 日志、音频读写、临时文件管理
"""
import logging
import os
import sys
import tempfile
import warnings
from pathlib import Path
from typing import List, Optional

LOGGER_NAME = "video_merge_voiceover"


def get_app_root() -> Path:
    """
    获取程序根目录（只用于读取内置资源，不写入）。
    支持 PyInstaller (sys._MEIPASS) 与源代码运行场景。
    """
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    if "__file__" in globals():
        # utils.py 所在目录的上级即 python-backend
        return Path(__file__).resolve().parent.parent
    return Path(sys.argv[0]).resolve().parent


def _is_subpath(child: Path, parent: Path) -> bool:
    """
    判断 child 是否位于 parent 之内。
    """
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _default_writable_root() -> Path:
    """
    获取默认可写目录：优先用户数据目录，其次系统临时目录。
    """
    candidates = [
        os.getenv("LOCALAPPDATA"),
        os.getenv("APPDATA"),
        os.getenv("HOME"),
    ]
    for candidate in candidates:
        if candidate:
            base = Path(candidate).expanduser()
            if base.exists() or base.parent.exists():
                return (base / "python-backend").resolve()
    return Path(tempfile.gettempdir()).resolve() / "python-backend"


def get_user_data_root() -> Path:
    """
    统一的用户可写数据根目录，可通过环境变量 PY_BACKEND_DATA_DIR 覆盖。
    """
    override = os.getenv("PY_BACKEND_DATA_DIR")
    base = Path(override).expanduser() if override else _default_writable_root()
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_temp_dir() -> Path:
    """
    系统临时目录下的专用子目录，避免写入安装目录。
    """
    temp_root = Path(tempfile.gettempdir()).resolve() / "python-backend" / "temp"
    temp_root.mkdir(parents=True, exist_ok=True)
    return temp_root


def get_logs_dir() -> Path:
    """
    日志目录：位于用户数据目录内，避免占用程序安装目录。
    """
    log_root = get_user_data_root() / "logs"
    log_root.mkdir(parents=True, exist_ok=True)
    return log_root


def get_runtime_dir() -> Path:
    """
    portable Python 运行时的占位目录。
    """
    return get_app_root() / "runtime"


def get_ffmpeg_dir() -> Path:
    """
    内置 ffmpeg 目录（只读占位，可由用户复制真实可执行文件）。
    """
    return get_app_root() / "ffmpeg"


def _bootstrap_ffmpeg_binary() -> Optional[str]:
    """
    优先使用内置 ffmpeg（若用户已复制），兼容 bin/ 或深层目录；否则回退 imageio-ffmpeg。
    """
    ffmpeg_dir = get_ffmpeg_dir()

    def _find_binary(name: str) -> Optional[Path]:
        preferred = [
            ffmpeg_dir / name,
            ffmpeg_dir / "bin" / name,
        ]
        deep = list(ffmpeg_dir.glob(f"**/{name}"))
        for candidate in preferred + deep:
            if candidate.exists():
                return candidate.resolve()
        return None

    packaged_ffmpeg = _find_binary("ffmpeg.exe")
    packaged_ffprobe = _find_binary("ffprobe.exe")

    if packaged_ffmpeg:
        os.environ["FFMPEG_BINARY"] = str(packaged_ffmpeg)
        os.environ["IMAGEIO_FFMPEG_EXE"] = str(packaged_ffmpeg)
        if packaged_ffprobe:
            os.environ.setdefault("FFPROBE_BINARY", str(packaged_ffprobe))
        current_path = os.environ.get("PATH", "")
        parent_dir = str(packaged_ffmpeg.parent)
        if parent_dir not in current_path:
            os.environ["PATH"] = f"{parent_dir}{os.pathsep}{current_path}"
        return str(packaged_ffmpeg)

    try:
        import imageio_ffmpeg  # type: ignore

        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        os.environ.setdefault("IMAGEIO_FFMPEG_EXE", ffmpeg_bin)
        os.environ.setdefault("FFMPEG_BINARY", ffmpeg_bin)
        return ffmpeg_bin
    except Exception:
        return None


_FFMPEG_BIN = _bootstrap_ffmpeg_binary()

# 抑制 pydub 在探测 ffmpeg 时的冗余警告
warnings.filterwarnings(
    "ignore",
    message="Couldn't find ffmpeg or avconv - defaulting to ffmpeg",
    category=RuntimeWarning,
)
from pydub import AudioSegment  # noqa: E402

# 若已定位到 ffmpeg，设置给 pydub
if _FFMPEG_BIN:
    AudioSegment.converter = _FFMPEG_BIN


def ensure_directories() -> None:
    """
    确保运行所需的日志与临时目录存在。
    """
    get_logs_dir()
    get_temp_dir()


def setup_logging(log_dir: Optional[str] = None) -> logging.Logger:
    """
    配置全局日志：info/error 文件写入日志目录，并同步到控制台。
    """
    target_dir = Path(log_dir) if log_dir else get_logs_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger  # 避免重复添加处理器

    info_handler = logging.FileHandler(target_dir / "app.log", encoding="utf-8")
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    error_handler = logging.FileHandler(target_dir / "error.log", encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))

    logger.addHandler(info_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)
    logger.propagate = False

    return logger


def adjust_output_path_extension(output_path: str, output_format: str) -> str:
    """
    根据用户选择的格式补全/替换输出文件后缀。
    """
    base, ext = os.path.splitext(output_path)
    chosen_ext = f".{output_format.lower()}"
    return output_path if ext.lower() == chosen_ext else f"{base}{chosen_ext}"


def validate_input_files(paths: List[str], logger: Optional[logging.Logger] = None) -> List[str]:
    """
    校验输入文件存在性并返回规范化绝对路径。
    仅读取，不复制、不写入安装目录。
    """
    logger = logger or logging.getLogger(LOGGER_NAME)
    normalized: List[str] = []
    for raw in paths:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"输入文件不存在：{candidate}")
        logger.info("确认输入文件：%s", candidate)
        normalized.append(str(candidate))
    return normalized


def apply_output_path_policy(output_path: str, logger: Optional[logging.Logger] = None) -> str:
    """
    限制输出路径不可位于程序安装目录内，防止 EXE 只读目录写入失败。
    """
    logger = logger or logging.getLogger(LOGGER_NAME)
    app_root = get_app_root()
    resolved = Path(output_path).resolve()
    if _is_subpath(resolved, app_root):
        raise ValueError("输出路径禁止位于程序安装目录或源码目录，请提供用户可写的完整路径。")
    logger.info("输出文件将写入：%s", resolved)
    return str(resolved)


def normalize_output_path(output_path: str, output_format: str, logger: Optional[logging.Logger] = None) -> str:
    """
    检查输出路径为绝对路径、补全后缀，并创建父目录。
    """
    logger = logger or logging.getLogger(LOGGER_NAME)
    path_obj = Path(output_path).expanduser()
    if not path_obj.is_absolute():
        raise ValueError("输出路径必须包含完整绝对路径（含文件名），以便桌面应用安全写入。")
    adjusted = Path(adjust_output_path_extension(str(path_obj), output_format))
    adjusted.parent.mkdir(parents=True, exist_ok=True)
    logger.info("规范化输出路径：%s", adjusted)
    return str(adjusted)


def _create_temp_file(suffix: str = ".tmp") -> str:
    """
    在系统临时目录下创建文件并返回路径，统一集中清理。
    """
    temp_dir = get_temp_dir()
    fd, temp_path = tempfile.mkstemp(suffix=suffix, dir=temp_dir)
    os.close(fd)
    return temp_path


def reserve_temp_file(suffix: str = ".tmp") -> str:
    """
    预留一个临时文件路径（空文件），供外部写入使用。
    """
    return _create_temp_file(suffix)


def load_audio_segment(path: str, logger: Optional[logging.Logger] = None) -> Optional[AudioSegment]:
    """
    读取音频文件为 AudioSegment。
    """
    logger = logger or logging.getLogger(LOGGER_NAME)
    if not path:
        logger.warning("未提供音频路径，跳过加载。")
        return None
    if not os.path.exists(path):
        logger.error("音频文件不存在：%s", path)
        return None
    try:
        return AudioSegment.from_file(path)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("加载音频失败：%s", exc)
        return None


def pad_or_trim_audio(audio: AudioSegment, target_duration_ms: int, logger: Optional[logging.Logger] = None) -> AudioSegment:
    """
    将音频补齐或裁剪到目标时长；不足时先淡出再补静音，避免突兀。
    """
    logger = logger or logging.getLogger(LOGGER_NAME)
    current_duration = len(audio)
    if current_duration < target_duration_ms:
        padding = target_duration_ms - current_duration
        fade_ms = min(1000, current_duration)
        audio_faded = audio.fade_out(fade_ms)
        logger.info("音频时长不足，尾部淡出 %d ms，补静音 %d ms。", fade_ms, padding)
        return audio_faded + AudioSegment.silent(duration=padding)
    if current_duration > target_duration_ms:
        logger.info("音频时长过长，裁剪到目标时长 %d ms。", target_duration_ms)
        return audio[:target_duration_ms]
    return audio


def create_silent_audio(duration_ms: int) -> AudioSegment:
    """
    创建指定时长的静音音频。
    """
    return AudioSegment.silent(duration=duration_ms)


def extract_audio_segment_from_clip(video_clip, logger: Optional[logging.Logger] = None) -> AudioSegment:
    """
    从视频片段提取音频为 AudioSegment，若无音轨则返回静音。
    """
    logger = logger or logging.getLogger(LOGGER_NAME)
    duration_ms = int(video_clip.duration * 1000) if video_clip and video_clip.duration else 0
    if not video_clip or not video_clip.audio:
        return create_silent_audio(duration_ms)

    audio_clip = video_clip.audio
    if not getattr(audio_clip, "fps", None):
        try:
            audio_clip = audio_clip.set_fps(44100)
        except Exception:  # pylint: disable=broad-except
            audio_clip.fps = 44100  # type: ignore[attr-defined]

    temp_path = _create_temp_file(".wav")
    try:
        audio_clip.write_audiofile(temp_path, verbose=False, logger=None)
        audio_seg = AudioSegment.from_file(temp_path)
        return pad_or_trim_audio(audio_seg, duration_ms, logger)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("提取视频音频失败：%s", exc)
        return create_silent_audio(duration_ms)
    finally:
        safe_remove(temp_path, logger)


def write_audiosegment_to_temp(audio: AudioSegment, suffix: str = ".wav", logger: Optional[logging.Logger] = None) -> str:
    """
    将 AudioSegment 写入临时文件，返回路径。
    """
    logger = logger or logging.getLogger(LOGGER_NAME)
    temp_path = _create_temp_file(suffix)
    try:
        audio.export(temp_path, format=suffix.replace(".", ""))
        return temp_path
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("写入临时音频失败：%s", exc)
        safe_remove(temp_path, logger)
        raise


def safe_remove(path: str, logger: Optional[logging.Logger] = None) -> None:
    """
    安全删除文件，不抛出异常。
    """
    logger = logger or logging.getLogger(LOGGER_NAME)
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("删除临时文件失败 %s: %s", path, exc)
