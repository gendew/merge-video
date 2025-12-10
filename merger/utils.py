"""
通用工具函数：目录创建、日志、音频读写与长度处理。
"""
import logging
import os
import tempfile
import warnings
from typing import Optional

# 优先配置 ffmpeg 路径，再导入 pydub，避免导入时找不到 ffmpeg 的警告
try:
    import imageio_ffmpeg

    _ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    os.environ.setdefault("IMAGEIO_FFMPEG_EXE", _ffmpeg_bin)
    os.environ.setdefault("FFMPEG_BINARY", _ffmpeg_bin)
except Exception:
    _ffmpeg_bin = None

# 抑制 pydub 在探测 ffmpeg 时的冗余警告
warnings.filterwarnings(
    "ignore",
    message="Couldn't find ffmpeg or avconv - defaulting to ffmpeg",
    category=RuntimeWarning,
)
from pydub import AudioSegment  # noqa: E402

# 若找到了自带 ffmpeg，则更新 pydub converter
if _ffmpeg_bin:
    AudioSegment.converter = _ffmpeg_bin


def ensure_directories(log_dir: str = "logs", output_dir: str = "output", upload_dir: str = "uploads") -> None:
    """
    确保日志与输出目录存在。
    """
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    if upload_dir:
        os.makedirs(upload_dir, exist_ok=True)


def setup_logging(log_dir: str = "logs") -> logging.Logger:
    """
    配置全局日志，普通日志写入 app.log，错误写入 error.log，并同步输出到控制台。
    """
    ensure_directories(log_dir=log_dir)
    logger = logging.getLogger("video_merge_voiceover")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger  # 避免重复添加处理器

    # 普通日志
    info_handler = logging.FileHandler(os.path.join(log_dir, "app.log"), encoding="utf-8")
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    # 错误日志
    error_handler = logging.FileHandler(os.path.join(log_dir, "error.log"), encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    # 控制台输出
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
    根据用户选择的格式调整输出文件后缀。
    """
    base, ext = os.path.splitext(output_path)
    chosen_ext = f".{output_format.lower()}"
    return output_path if ext.lower() == chosen_ext else f"{base}{chosen_ext}"


def load_audio_segment(path: str, logger: Optional[logging.Logger] = None) -> Optional[AudioSegment]:
    """
    加载音频文件为 AudioSegment。
    """
    logger = logger or logging.getLogger("video_merge_voiceover")
    if not path:
        logger.warning("未提供音频路径。")
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
    将音频补齐或裁剪到目标时长；不足时先淡出再补静音，避免瞬时静音。
    """
    logger = logger or logging.getLogger("video_merge_voiceover")
    current_duration = len(audio)
    if current_duration < target_duration_ms:
        padding = target_duration_ms - current_duration
        fade_ms = min(1000, current_duration)
        audio_faded = audio.fade_out(fade_ms)
        logger.info("音频时长不足，尾部淡出 %d ms，补齐静音 %d ms。", fade_ms, padding)
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
    logger = logger or logging.getLogger("video_merge_voiceover")
    duration_ms = int(video_clip.duration * 1000) if video_clip and video_clip.duration else 0
    if not video_clip or not video_clip.audio:
        return create_silent_audio(duration_ms)

    audio_clip = video_clip.audio
    if not getattr(audio_clip, "fps", None):
        # 部分 CompositeAudioClip 无 fps 属性，写出前补一个默认采样率
        try:
            audio_clip = audio_clip.set_fps(44100)
        except Exception:  # pylint: disable=broad-except
            audio_clip.fps = 44100  # type: ignore[attr-defined]

    fd, temp_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        # 静默导出音频以供 pydub 加载
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
    logger = logger or logging.getLogger("video_merge_voiceover")
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
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
    logger = logger or logging.getLogger("video_merge_voiceover")
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("删除临时文件失败 %s: %s", path, exc)
