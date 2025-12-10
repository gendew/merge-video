"""
Main program entry: CLI parsing and orchestration for video merge + optional voiceover.
"""
import argparse
import logging
from typing import List, Optional

from merger.utils import ensure_directories, setup_logging, adjust_output_path_extension, safe_remove
from merger.video_merge import merge_videos, export_video_clip
from merger.voiceover import prepare_voice_audio, apply_voice_to_video


def str2bool(value: str) -> bool:
    """
    Parse string into boolean, accepting common truthy values.
    """
    return str(value).lower() in {"1", "true", "t", "yes", "y"}


def parse_args() -> argparse.Namespace:
    """
    Build CLI arguments.
    """
    parser = argparse.ArgumentParser(
        description="Local multi-video merge tool with optional voiceover and TTS",
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="Input video paths in order",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output file path (extension auto-adjusted by --output_format)",
    )
    parser.add_argument(
        "--merge_mode",
        choices=["A", "B", "C"],
        default="A",
        help="Merge strategy: A keep native sizes; B upscale/downscale to max; C to first video size",
    )
    parser.add_argument(
        "--use_voice",
        type=str2bool,
        default=False,
        help="Whether to enable voiceover processing",
    )
    parser.add_argument(
        "--voice",
        default="",
        help="Voiceover audio path (MP3/WAV). If omitted, --voice_text_file may generate TTS.",
    )
    parser.add_argument(
        "--voice_text_file",
        default="",
        help="Text file path for TTS generation when no voice file is given",
    )
    parser.add_argument(
        "--voice_mix_mode",
        choices=["A", "B", "C"],
        default="B",
        help="Mix strategy: A replace original; B mix with original half volume; C keep original, voice as 30%% bg",
    )
    parser.add_argument(
        "--tts_voice",
        choices=["A", "B", "C"],
        default="A",
        help="TTS voice type: A default; B male; C female",
    )
    parser.add_argument(
        "--output_format",
        choices=["mp4", "mov", "mkv"],
        default="mp4",
        help="Output video format",
    )
    parser.add_argument(
        "--trim_seconds",
        nargs="*",
        type=float,
        default=None,
        help="Optional list matching inputs: how many seconds to keep per video",
    )
    parser.add_argument(
        "--trim_modes",
        nargs="*",
        choices=["start", "end"],
        default=None,
        help="Optional list matching inputs: start to cut from beginning, end to keep last N seconds",
    )
    parser.add_argument(
        "--tail_image",
        default="",
        help="Optional image path to append as a tail frame",
    )
    parser.add_argument(
        "--tail_duration",
        type=float,
        default=0.0,
        help="How many seconds the tail image stays (works when >0)",
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
    Execute the end-to-end merge and optional voiceover flow.
    """
    ensure_directories()
    logger = logger or setup_logging()
    temp_files = []
    final_output = adjust_output_path_extension(output, output_format)
    merged_clip = None

    try:
        logger.info("开始执行视频拼接流程...")
        merged_clip = merge_videos(
            inputs,
            merge_mode,
            logger,
            trims=trims,
            trim_modes=trim_modes,
            tail_image_path=tail_image_path,
            tail_duration=tail_duration,
        )

        if use_voice:
            logger.info("开始处理配音/语音合成...")
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
            logger.info("未开启配音，直接导出视频。")

        final_path = export_video_clip(
            video_clip=merged_clip,
            output_path=final_output,
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
    CLI entry point.
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
