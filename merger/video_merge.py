"""
视频拼接相关逻辑。
"""
import os
from typing import List, Tuple, Optional

# Pillow>=10 移除了 Image.ANTIALIAS，moviepy 仍有引用，这里先补齐再导入 moviepy
try:  # pragma: no cover - 兼容性补丁
    from PIL import Image as _PILImage

    if not hasattr(_PILImage, "ANTIALIAS"):
        _PILImage.ANTIALIAS = _PILImage.Resampling.LANCZOS
except Exception:  # pylint: disable=broad-except
    _PILImage = None

from moviepy.editor import VideoFileClip, concatenate_videoclips, ImageClip
# 再次确保 ANTIALIAS 存在（有些环境在导入 moviepy 前未补丁到位）
try:  # pragma: no cover - 兼容性补丁
    from PIL import Image as _PILImage2

    if not hasattr(_PILImage2, "ANTIALIAS"):
        resampling = getattr(_PILImage2, "Resampling", None)
        fallback = getattr(resampling, "LANCZOS", None) if resampling else None
        _PILImage2.ANTIALIAS = fallback or getattr(_PILImage2, "BICUBIC", None) or _PILImage2.NEAREST
except Exception:  # pylint: disable=broad-except
    pass

from merger.utils import adjust_output_path_extension


def _calculate_target_resolution(clips: List[VideoFileClip], merge_mode: str) -> Tuple[int, int]:
    """
    根据模式计算目标分辨率。
    """
    if merge_mode == "B":
        max_w = max(clip.w for clip in clips)
        max_h = max(clip.h for clip in clips)
        return max_w, max_h
    if merge_mode == "C":
        return clips[0].w, clips[0].h
    return 0, 0  # 模式 A 不做统一缩放


def _trim_clip_if_needed(
    clip: VideoFileClip,
    trim_seconds: Optional[float],
    trim_mode: str,
    logger,
) -> VideoFileClip:
    """
    若提供裁剪秒数，可选择截取开头或末尾的指定时长。
    """
    if trim_seconds is None or trim_seconds <= 0:
        return clip
    duration = clip.duration or 0
    actual = min(trim_seconds, duration)
    if trim_seconds > duration:
        logger.warning("裁剪秒数 %.2f 超出视频时长 %.2f，已自动截到视频末尾", trim_seconds, duration)
    use_end = str(trim_mode or "").lower() == "end"
    if use_end:
        start = max(duration - actual, 0)
        end = duration
        logger.info("截取视频末尾%.2f 秒", actual)
        return clip.subclip(start, end)
    logger.info("截取视频前%.2f 秒", actual)
    return clip.subclip(0, actual)


def merge_videos(
    input_paths: List[str],
    merge_mode: str,
    logger,
    trims: Optional[List[float]] = None,
    trim_modes: Optional[List[str]] = None,
    tail_image_path: Optional[str] = None,
    tail_duration: Optional[float] = None,
) -> VideoFileClip:
    """
    按指定模式拼接多个视频，可选按序对每个视频裁剪前/后N秒，并可附加尾帧图片。
    """
    if not input_paths:
        raise ValueError("必须提供至少一个输入视频。")

    trims = trims or []
    trim_modes = trim_modes or []
    # 读取视频
    clips: List[VideoFileClip] = []
    for idx, path in enumerate(input_paths):
        if not os.path.exists(path):
            raise FileNotFoundError(f"输入视频不存在：{path}")
        logger.info("加载视频：%s", path)
        clip = VideoFileClip(path)
        trim_val = trims[idx] if idx < len(trims) else None
        trim_mode = trim_modes[idx] if idx < len(trim_modes) else "start"
        clip = _trim_clip_if_needed(clip, trim_val, trim_mode, logger)
        clips.append(clip)

    target_w, target_h = _calculate_target_resolution(clips, merge_mode)
    base_w = clips[0].w if clips else 0
    base_h = clips[0].h if clips else 0
    final_w = target_w or base_w
    final_h = target_h or base_h

    processed = []
    for clip in clips:
        if merge_mode == "A":
            processed.append(clip)
        else:
            logger.info("调整分辨率为 (%s, %s)", target_w, target_h)
            processed.append(clip.resize(newsize=(target_w, target_h)))

    if tail_image_path and tail_duration and tail_duration > 0:
        if not os.path.exists(tail_image_path):
            logger.warning("尾帧图片不存在：%s", tail_image_path)
        else:
            logger.info("追加尾帧图片 %s，持续 %.2f 秒", tail_image_path, tail_duration)
            tail_clip = ImageClip(tail_image_path).set_duration(tail_duration)
            if final_w and final_h:
                tail_clip = tail_clip.resize(newsize=(final_w, final_h))
            if clips and getattr(clips[0], "fps", None):
                tail_clip = tail_clip.set_fps(clips[0].fps)
            processed.append(tail_clip)

    logger.info("开始拼接视频，模式：%s", merge_mode)
    merged_clip = concatenate_videoclips(processed, method="compose")
    return merged_clip


def export_video_clip(video_clip: VideoFileClip, output_path: str, output_format: str, logger) -> str:
    """
    将 VideoClip 导出到指定路径。
    """
    output_path = adjust_output_path_extension(output_path, output_format)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    logger.info("写出视频到 %s", output_path)
    video_clip.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile="temp-audio.m4a",
        remove_temp=True,
        verbose=False,
    )
    return output_path
