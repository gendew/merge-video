"""
桌面 / Electron / Windows EXE 入口脚本。
保持原有视频拼接与配音业务流程不变，仅调整路径与运行环境以便被桌面端安全调用。
"""
import argparse
import logging
from typing import List, Optional

from merger.utils import (
    apply_output_path_policy,
    ensure_directories,
    normalize_output_path,
    setup_logging,
    safe_remove,
    validate_input_files,
)
from merger.video_merge import export_video_clip, merge_videos
from merger.voiceover import apply_voice_to_video, prepare_voice_audio


def str2bool(value: str) -> bool:
    """
    将字符串转为布尔值，兼容常见输入形式。
    """
    return str(value).lower() in {"1", "true", "t", "yes", "y"}


def parse_args() -> argparse.Namespace:
    """
    构建 CLI 参数。
    """
    parser = argparse.ArgumentParser(
        description="本地多视频拼接与可选配音 / TTS，适配桌面应用调用",
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="输入视频的本地路径列表（顺序即拼接顺序）",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="输出文件的完整路径（包含文件名，可自动按 --output_format 补全后缀）",
    )
    parser.add_argument(
        "--merge_mode",
        choices=["A", "B", "C"],
        default="A",
        help="拼接分辨率策略：A 保持原分辨率；B 统一到最大分辨率；C 统一到首个视频分辨率",
    )
    parser.add_argument(
        "--use_voice",
        type=str2bool,
        default=False,
        help="是否启用配音流程",
    )
    parser.add_argument(
        "--voice",
        default="",
        help="配音音频文件路径（MP3/WAV）。若为空，可配合 --voice_text_file 生成 TTS。",
    )
    parser.add_argument(
        "--voice_text_file",
        default="",
        help="配音文本文件路径，未提供配音音频时用于生成 TTS。",
    )
    parser.add_argument(
        "--voice_mix_mode",
        choices=["A", "B", "C"],
        default="B",
        help="混音策略：A 替换原声；B 原声减半后混音；C 原声保留，配音做 30% 背景",
    )
    parser.add_argument(
        "--tts_voice",
        choices=["A", "B", "C"],
        default="A",
        help="TTS 声音：A 默认；B 男声；C 女声",
    )
    parser.add_argument(
        "--output_format",
        choices=["mp4", "mov", "mkv"],
        default="mp4",
        help="输出视频格式",
    )
    parser.add_argument(
        "--trim_seconds",
        nargs="*",
        type=float,
        default=None,
        help="可选：与 inputs 一一对应的裁剪秒数，>0 时截取指定秒数",
    )
    parser.add_argument(
        "--trim_modes",
        nargs="*",
        choices=["start", "end"],
        default=None,
        help="可选：与 inputs 对应，start 表示保留开头，end 表示保留尾部 N 秒",
    )
    parser.add_argument(
        "--tail_image",
        default="",
        help="可选：尾帧图片路径，存在时会追加到拼接视频末尾",
    )
    parser.add_argument(
        "--tail_duration",
        type=float,
        default=0.0,
        help="尾帧图片停留秒数（>0 生效）",
    )
    return parser.parse_args()


def run_pipeline(
    inputs: List[str],
    output: str,
    merge_mode: str = "A",
    use_voice: bool = False,
    voice_path: str = "",
    voice_text_file: str = "",
    voice_mix_mode: str = "B",
    tts_voice: str = "A",
    output_format: str = "mp4",
    logger: Optional[logging.Logger] = None,
    trims: Optional[List[float]] = None,
    trim_modes: Optional[List[str]] = None,
    tail_image_path: str = "",
    tail_duration: float = 0.0,
) -> str:
    """
    执行端到端的视频拼接与可选配音流程。
    """
    ensure_directories()
    logger = logger or setup_logging()
    validated_inputs = validate_input_files(inputs, logger)
    normalized_output = normalize_output_path(output, output_format, logger)
    normalized_output = apply_output_path_policy(normalized_output, logger)

    temp_files = []
    merged_clip = None

    try:
        logger.info("开始执行视频拼接流程...")
        merged_clip = merge_videos(
            validated_inputs,
            merge_mode,
            logger,
            trims=trims,
            trim_modes=trim_modes,
            tail_image_path=tail_image_path,
            tail_duration=tail_duration,
        )

        if use_voice:
            logger.info("开始处理配音与 TTS ...")
            voice_audio = prepare_voice_audio(
                voice_path=voice_path,
                text_file=voice_text_file,
                tts_voice=tts_voice,
                logger=logger,
            )
            if voice_audio:
                merged_clip, temp_audio = apply_voice_to_video(
                    video_clip=merged_clip,
                    voice_audio=voice_audio,
                    mix_mode=voice_mix_mode,
                    logger=logger,
                )
                if temp_audio:
                    temp_files.append(temp_audio)
            else:
                logger.warning("未提供有效配音文件或文本，跳过配音处理。")
        else:
            logger.info("未启用配音，直接导出视频。")

        final_path = export_video_clip(
            video_clip=merged_clip,
            output_path=normalized_output,
            output_format=output_format,
            logger=logger,
        )
        logger.info("处理完成，输出文件：%s", final_path)
        return final_path
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("处理过程中发生错误：%s", exc)
        raise
    finally:
        for temp in temp_files:
            safe_remove(temp, logger)
        if merged_clip:
            merged_clip.close()


def main() -> None:
    """
    CLI 入口。
    """
    args = parse_args()
    run_pipeline(
        inputs=args.inputs,
        output=args.output,
        merge_mode=args.merge_mode,
        use_voice=args.use_voice,
        voice_path=args.voice,
        voice_text_file=args.voice_text_file,
        voice_mix_mode=args.voice_mix_mode,
        tts_voice=args.tts_voice,
        output_format=args.output_format,
        trims=args.trim_seconds,
        trim_modes=args.trim_modes,
        tail_image_path=args.tail_image,
        tail_duration=args.tail_duration,
    )


if __name__ == "__main__":
    main()
