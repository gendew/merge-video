"""
配音与 TTS 处理相关逻辑。
"""
import logging
import os
import tempfile
from typing import Optional, Tuple

import pyttsx3
from moviepy.editor import AudioFileClip
from moviepy.audio.fx import all as afx
from pydub import AudioSegment

from merger.utils import (
    extract_audio_segment_from_clip,
    pad_or_trim_audio,
    load_audio_segment,
    create_silent_audio,
    write_audiosegment_to_temp,
    safe_remove,
)


def select_voice(engine: pyttsx3.Engine, voice_type: str, logger: logging.Logger) -> Optional[str]:
    """
    根据用户选择的声线挑选合适的 pyttsx3 voice id。
    """
    voices = engine.getProperty("voices")
    target_keyword = None
    if voice_type == "B":
        target_keyword = "male"
    elif voice_type == "C":
        target_keyword = "female"

    if not target_keyword:
        return None  # 默认声线

    for voice in voices:
        desc = f"{getattr(voice, 'name', '')} {getattr(voice, 'gender', '')} {voice.id}".lower()
        if target_keyword in desc:
            logger.info("匹配到 TTS 声音：%s", voice.name)
            return voice.id

    logger.warning("未找到匹配的声线，使用默认声音。")
    return None


def generate_tts_audio(text: str, voice_type: str, output_path: str, logger: logging.Logger) -> None:
    """
    使用 pyttsx3 将文本转换为语音文件。
    """
    engine = pyttsx3.init()
    voice_id = select_voice(engine, voice_type, logger)
    if voice_id:
        engine.setProperty("voice", voice_id)
    engine.save_to_file(text, output_path)
    engine.runAndWait()
    logger.info("TTS 音频已生成：%s", output_path)


def prepare_voice_audio(
    voice_path: str,
    text_file: str,
    tts_voice: str,
    logger: logging.Logger,
) -> Optional[AudioSegment]:
    """
    加载外部配音或根据文本生成 TTS 音频，返回 AudioSegment。
    """
    if voice_path and voice_path.lower() != "none":
        logger.info("加载外部配音文件：%s", voice_path)
        return load_audio_segment(voice_path, logger)

    if text_file:
        if not os.path.exists(text_file):
            logger.error("配音文本文件不存在：%s", text_file)
            return None
        logger.info("读取配音文本并生成 TTS：%s", text_file)
        with open(text_file, "r", encoding="utf-8") as f:
            content = f.read()
        fd, temp_audio = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            generate_tts_audio(content, tts_voice, temp_audio, logger)
            audio_seg = load_audio_segment(temp_audio, logger)
            return audio_seg
        finally:
            safe_remove(temp_audio, logger)

    logger.warning("未提供配音文件或文本，无法生成配音。")
    return None


def apply_voice_to_video(
    video_clip,
    voice_audio: AudioSegment,
    mix_mode: str,
    logger: logging.Logger,
) -> Tuple:
    """
    将配音按指定策略叠加到视频，并返回更新后的 clip 与临时音频路径。
    """
    duration_ms = int(video_clip.duration * 1000)
    voice_aligned = pad_or_trim_audio(voice_audio, duration_ms, logger)

    base_audio = extract_audio_segment_from_clip(video_clip, logger)
    if len(base_audio) == 0:
        base_audio = create_silent_audio(duration_ms)
    base_audio = pad_or_trim_audio(base_audio, duration_ms, logger)

    if mix_mode == "A":
        logger.info("配音策略：覆盖原音轨")
        final_audio = voice_aligned
    elif mix_mode == "C":
        logger.info("配音策略：原音轨 + 配音背景 (30%%)")
        voice_bg = voice_aligned - 10  # 约 30% 音量
        final_audio = base_audio.overlay(voice_bg)
    else:
        logger.info("配音策略：混合，原音量减半")
        base_reduced = base_audio - 6  # 减半音量约 -6dB
        final_audio = base_reduced.overlay(voice_aligned)

    temp_audio_path = write_audiosegment_to_temp(final_audio, suffix=".wav", logger=logger)
    audio_clip = AudioFileClip(temp_audio_path)
    new_clip = video_clip.set_audio(audio_clip)
    # 使用 moviepy 的 afx.audio_fadeout 确保尾部淡出真实生效（默认 1s，最长不超过视频时长）
    fade_secs = 1.0 if not video_clip.duration else min(1.0, video_clip.duration)
    if fade_secs > 0:
        new_clip = new_clip.fx(afx.audio_fadeout, fade_secs)
    return new_clip, temp_audio_path
