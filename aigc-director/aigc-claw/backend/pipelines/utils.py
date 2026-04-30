import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable, Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def write_text(path: str, content: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def write_json(path: str, data: Any) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def artifact(path: str, kind: str, name: Optional[str] = None) -> dict[str, Any]:
    return {
        "kind": kind,
        "name": name or os.path.basename(path),
        "path": path,
        "exists": os.path.exists(path),
    }


def extract_json_array(text: str) -> list[Any]:
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except Exception:
        pass

    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S)
    if not match:
        match = re.search(r"(\[.*\])", text, re.S)
    if match:
        data = json.loads(match.group(1))
        if isinstance(data, list):
            return data
    raise ValueError("Model response did not contain a JSON array.")


def split_script(text: str, split_mode: str = "paragraph") -> list[str]:
    if split_mode == "line":
        parts = [line.strip() for line in text.splitlines()]
    elif split_mode == "sentence":
        parts = [part.strip() for part in re.split(r"(?<=[。！？.!?])\s*", text)]
    else:
        parts = [part.strip() for part in re.split(r"\n\s*\n", text)]
    return [part for part in parts if part]


def copy_input_file(path: str, output_dir: str, prefix: str) -> str:
    if path.startswith(("http://", "https://", "file://", "data:")):
        return path
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    dst = Path(output_dir) / f"{prefix}{src.suffix.lower()}"
    shutil.copy2(src, dst)
    return str(dst)


async def run_blocking(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def concat_videos(video_paths: Iterable[str], output_path: str) -> Optional[str]:
    paths = [path for path in video_paths if path and os.path.exists(path)]
    if not paths:
        return None

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        logger.warning("ffmpeg not found; cannot concatenate videos")
        return None

    list_path = os.path.join(os.path.dirname(output_path), "concat.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for path in paths:
            f.write(f"file '{os.path.abspath(path)}'\n")

    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", output_path]
    logger.info("Concatenating %d videos -> %s", len(paths), output_path)
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    logger.info("Video concatenation complete: %s", output_path)
    return output_path


def create_static_image_clip(
    image_path: str,
    audio_path: str,
    output_path: str,
    *,
    video_ratio: str = "9:16",
    duration: Optional[float] = None,
) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to create static short-video clips.")
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    width, height = _resolution_from_ratio(video_ratio)
    clip_duration = duration or media_duration_seconds(audio_path) or 3.0
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        "format=yuv420p"
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    logger.info(
        "Creating static image clip: image=%s audio=%s duration=%.2fs -> %s",
        image_path,
        audio_path,
        clip_duration,
        output_path,
    )
    cmd = [
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-framerate",
        "30",
        "-i",
        image_path,
        "-i",
        audio_path,
        "-t",
        f"{clip_duration:.3f}",
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        output_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path


def _load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in str(text or "").splitlines() or [""]:
        current = ""
        for char in paragraph.strip():
            candidate = current + char
            if current and _text_width(draw, candidate, font) > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines or [""]


def _draw_centered_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    *,
    center_x: int,
    y: int,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    stroke_width: int,
    stroke_fill: tuple[int, int, int, int],
    line_gap: int,
) -> int:
    cursor = y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        draw.text(
            (center_x - width / 2, cursor),
            line,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        cursor += height + line_gap
    return cursor


def render_static_text_image(
    image_path: str,
    output_path: str,
    *,
    subtitle: str,
    title: Optional[str] = None,
    video_ratio: str = "9:16",
) -> str:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    width, height = _resolution_from_ratio(video_ratio)
    with Image.open(image_path) as source:
        source = source.convert("RGB")
        source.thumbnail((width, height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (width, height), (0, 0, 0))
        canvas.paste(source, ((width - source.width) // 2, (height - source.height) // 2))

    image = canvas.convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    title_font = _load_font(max(48, int(height * 0.06)))
    subtitle_font = _load_font(max(32, int(height * 0.035)))
    margin_x = max(48, int(width * 0.07))
    max_text_width = width - margin_x * 2

    if title:
        title_lines = _wrap_text(draw, title, title_font, max_text_width)
        title_line_height = max(1, draw.textbbox((0, 0), "国", font=title_font)[3])
        title_height = len(title_lines) * title_line_height + max(0, len(title_lines) - 1) * 10
        title_y = max(48, int(height * 0.055))
        _draw_centered_lines(
            draw,
            title_lines,
            center_x=width // 2,
            y=title_y,
            font=title_font,
            fill=(255, 255, 255, 255),
            stroke_width=3,
            stroke_fill=(0, 0, 0, 210),
            line_gap=10,
        )

    subtitle_lines = _wrap_text(draw, subtitle, subtitle_font, max_text_width)
    subtitle_line_height = max(1, draw.textbbox((0, 0), "国", font=subtitle_font)[3])
    subtitle_height = len(subtitle_lines) * subtitle_line_height + max(0, len(subtitle_lines) - 1) * 10
    subtitle_y = height - max(96, int(height * 0.08)) - subtitle_height
    _draw_centered_lines(
        draw,
        subtitle_lines,
        center_x=width // 2,
        y=subtitle_y,
        font=subtitle_font,
        fill=(255, 255, 255, 255),
        stroke_width=3,
        stroke_fill=(0, 0, 0, 230),
        line_gap=10,
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    Image.alpha_composite(image, overlay).convert("RGB").save(output_path, quality=95)
    logger.info("Rendered static title/subtitle image: %s -> %s", image_path, output_path)
    return output_path


def concat_audios(audio_paths: Iterable[str], output_path: str) -> Optional[str]:
    paths = [path for path in audio_paths if path and os.path.exists(path)]
    if not paths:
        return None
    if len(paths) == 1:
        return paths[0]

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        logger.warning("ffmpeg not found; cannot concatenate audios")
        return None

    list_path = os.path.join(os.path.dirname(output_path), "concat_audio.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for path in paths:
            f.write(f"file '{os.path.abspath(path)}'\n")

    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", output_path]
    logger.info("Concatenating %d audios -> %s", len(paths), output_path)
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path


def replace_video_audio(video_path: str, audio_path: str, output_path: str) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to replace digital-human video audio.")
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    logger.info("Replacing video audio: video=%s audio=%s -> %s", video_path, audio_path, output_path)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        video_path,
        "-i",
        audio_path,
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        output_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path


def media_duration_seconds(path: str) -> Optional[float]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not os.path.exists(path):
        return None

    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        duration = float(result.stdout.strip())
        logger.debug("Media duration: %s = %.3fs", path, duration)
        return duration
    except Exception as exc:
        logger.warning("Failed to probe media duration: %s (%s)", path, exc)
        return None


def _resolution_from_ratio(video_ratio: str) -> tuple[int, int]:
    ratio = (video_ratio or "9:16").strip()
    if ratio in {"16:9", "landscape"}:
        return 1920, 1080
    if ratio in {"1:1", "square"}:
        return 1080, 1080
    return 1080, 1920


def _ass_time(seconds: float) -> str:
    total_centiseconds = max(0, int(round(seconds * 100)))
    centiseconds = total_centiseconds % 100
    total_seconds = total_centiseconds // 100
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def _ass_text(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = cleaned.replace("{", "｛").replace("}", "｝")
    return cleaned.replace("\r\n", "\\N").replace("\n", "\\N")


def write_ass_subtitles(
    path: str,
    *,
    subtitles: Iterable[tuple[str, float]],
    title: Optional[str] = None,
    video_ratio: str = "9:16",
) -> str:
    width, height = _resolution_from_ratio(video_ratio)
    title_size = max(36, int(height * 0.038))
    subtitle_size = max(34, int(height * 0.032))
    title_margin_v = max(70, int(height * 0.06))
    subtitle_margin_v = max(80, int(height * 0.085))
    subtitle_margin_h = max(70, int(width * 0.07))

    events: list[str] = []
    cursor = 0.0
    normalized: list[tuple[str, float, float]] = []
    for text, duration in subtitles:
        duration_seconds = max(0.1, float(duration or 0))
        start = cursor
        end = cursor + duration_seconds
        normalized.append((text, start, end))
        cursor = end

    total_duration = cursor or 0.1
    if title:
        events.append(
            f"Dialogue: 0,{_ass_time(0)},{_ass_time(total_duration)},Title,,0,0,0,,{_ass_text(title)}"
        )
    for text, start, end in normalized:
        events.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Subtitle,,0,0,0,,{_ass_text(text)}"
        )

    content = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "Collisions: Normal",
            f"PlayResX: {width}",
            f"PlayResY: {height}",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Title,Arial,{title_size},&H00FFFFFF,&H000000FF,&H99000000,&H66000000,-1,0,0,0,100,100,0,0,1,4,0,8,{subtitle_margin_h},{subtitle_margin_h},{title_margin_v},1",
            f"Style: Subtitle,Arial,{subtitle_size},&H00FFFFFF,&H000000FF,&HAA000000,&H66000000,0,0,0,0,100,100,0,0,1,4,0,2,{subtitle_margin_h},{subtitle_margin_h},{subtitle_margin_v},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            *events,
            "",
        ]
    )
    logger.info("Writing ASS subtitles: %s lines=%d title=%s", path, len(normalized), bool(title))
    return write_text(path, content)


def _ffmpeg_filter_path(path: str) -> str:
    escaped = os.path.abspath(path).replace("\\", "/")
    return escaped.replace(":", "\\:").replace("'", "\\'")


def _ffmpeg_has_filter(ffmpeg: str, filter_name: str) -> bool:
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception as exc:
        logger.warning("Failed to inspect ffmpeg filters: %s", exc)
        return False
    return any(line.split()[1:2] == [filter_name] for line in result.stdout.splitlines() if line.strip())


def burn_ass_subtitles(video_path: str, subtitle_path: str, output_path: str) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to burn subtitles into video.")
    if not _ffmpeg_has_filter(ffmpeg, "ass"):
        raise RuntimeError(
            "ffmpeg was found, but its libass/ass filter is unavailable. "
            "Install an ffmpeg build with libass support before burning ASS subtitles."
        )
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not os.path.exists(subtitle_path):
        raise FileNotFoundError(f"Subtitle not found: {subtitle_path}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    logger.info("Burning ASS subtitles: video=%s subtitles=%s -> %s", video_path, subtitle_path, output_path)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        video_path,
        "-vf",
        f"ass=filename='{_ffmpeg_filter_path(subtitle_path)}'",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "veryfast",
        "-c:a",
        "copy",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as exc:
        logger.error("Failed to burn ASS subtitles: %s", exc.stderr)
        raise
    return output_path


def speed_audio_to_duration(audio_path: str, output_path: str, target_seconds: int) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to speed up long digital-human narration audio.")

    duration = media_duration_seconds(audio_path)
    if not duration:
        return audio_path
    if duration <= target_seconds:
        return audio_path

    speed = duration / float(target_seconds)
    filters = []
    remaining = speed
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    filters.append(f"atempo={remaining:.6f}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    logger.info(
        "Speeding audio to fit video duration: %s duration=%.2fs target=%ss speed=%.3fx -> %s",
        audio_path,
        duration,
        target_seconds,
        speed,
        output_path,
    )
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        audio_path,
        "-filter:a",
        ",".join(filters),
        "-vn",
        "-acodec",
        "libmp3lame",
        output_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path


def extract_last_frame(video_path: str, output_path: str) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to extract the previous video tail frame.")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    logger.info("Extracting tail frame: %s -> %s", video_path, output_path)
    cmd = [
        ffmpeg,
        "-y",
        "-sseof",
        "-0.1",
        "-i",
        video_path,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        output_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path
