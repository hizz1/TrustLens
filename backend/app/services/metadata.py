"""Phase 5 — Media Metadata Extraction and Inspection service.

Extracts container format, stream parameters, codecs, frame rate, sample rate,
encoder/software metadata, and creation timestamps using FFprobe (for video/audio)
or Pillow/EXIF (for images). Missing metadata is neutrally reported.
"""
from fractions import Fraction
import logging
from pathlib import Path
from typing import Any
import warnings

from PIL import Image, UnidentifiedImageError

from app.config import Settings
from app.schemas import MetadataResult
from app.utils.ffmpeg import run_tool

logger = logging.getLogger(__name__)

DEMUXERS = {".mp4": "mov", ".wav": "wav", ".mp3": "mp3"}

# Common EXIF tag numeric IDs
TAG_MAKE = 271          # 0x010f
TAG_MODEL = 272         # 0x0110
TAG_SOFTWARE = 305      # 0x0131
TAG_DATETIME = 306      # 0x0132
TAG_DATETIME_ORIG = 36867  # 0x9003


def _parse_frame_rate(rate_str: str | None) -> str | None:
    if not rate_str or rate_str == "0/0":
        return None
    try:
        if "/" in rate_str:
            num, den = rate_str.split("/")
            val = float(num) / float(den)
            return f"{val:.2f} fps" if val % 1 else f"{int(val)} fps"
        return f"{float(rate_str):.2f} fps"
    except Exception:
        return rate_str


def _extract_image_metadata(path: Path, extension: str) -> MetadataResult:
    expected = "PNG" if extension.lower() == ".png" else "JPEG"
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                image.load()
                width, height = image.width, image.height
                mode = image.mode
                format_name = (image.format or expected).lower()
                
                # Check EXIF
                encoder_parts = []
                creation_time = None
                try:
                    exif = image.getexif()
                    if exif:
                        make = exif.get(TAG_MAKE)
                        model = exif.get(TAG_MODEL)
                        software = exif.get(TAG_SOFTWARE)
                        dt = exif.get(TAG_DATETIME_ORIG) or exif.get(TAG_DATETIME)
                        if make or model:
                            encoder_parts.append(" ".join(filter(None, [str(make or "").strip(), str(model or "").strip()])))
                        if software:
                            encoder_parts.append(str(software).strip())
                        if dt:
                            creation_time = str(dt).strip()
                except Exception as exc:
                    logger.debug("Could not read EXIF data: %s", exc)

                encoder = " | ".join(filter(None, encoder_parts)) or None
                resolution = f"{width}x{height}"
                
                findings = [
                    f"Image format: {format_name.upper()}, dimensions: {resolution}, color mode: {mode}."
                ]
                if encoder:
                    findings.append(f"Device/software metadata identified: {encoder}.")
                if creation_time:
                    findings.append(f"Creation timestamp identified: {creation_time}.")
                if not encoder and not creation_time:
                    findings.append(
                        "No device or authoring metadata tags were found; missing EXIF metadata "
                        "is common in web and social media images and is treated as neutral evidence."
                    )

                return MetadataResult(
                    status="completed",
                    format={"format_name": format_name},
                    streams=[{
                        "codec_type": "video",
                        "width": width,
                        "height": height,
                        "mode": mode,
                    }],
                    resolution=resolution,
                    video_codec=format_name,
                    encoder=encoder,
                    creation_time=creation_time,
                    findings=findings,
                )
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        logger.warning("Image metadata extraction failed: %s", exc)
        return MetadataResult(
            status="unavailable",
            findings=[f"Image metadata extraction failed: {str(exc)[:200]}"],
        )


def _extract_av_metadata(path: Path, extension: str, settings: Settings, raw_metadata: MetadataResult | None = None) -> MetadataResult:
    try:
        if raw_metadata is not None:
            fmt = dict(raw_metadata.format)
            streams = list(raw_metadata.streams)
        else:
            demuxer = DEMUXERS.get(extension.lower())
            if not demuxer:
                return MetadataResult(status="unavailable", findings=["Unsupported container format for probing."])

            raw_json = run_tool([
                settings.ffprobe_path, "-v", "error",
                "-protocol_whitelist", "file", "-f", demuxer, "-i", str(path),
                "-show_format", "-show_streams", "-of", "json",
            ], settings.subprocess_timeout_seconds)
            
            import json
            payload = json.loads(raw_json)
            fmt = payload.get("format", {})
            streams = payload.get("streams", [])
            fmt.pop("filename", None)

        duration_sec = None
        if "duration" in fmt:
            try:
                duration_sec = round(float(fmt["duration"]), 4)
            except (ValueError, TypeError):
                pass

        # Locate video and audio streams
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        video_codec = video_stream.get("codec_name") if video_stream else None
        resolution = f"{video_stream.get('width')}x{video_stream.get('height')}" if video_stream and video_stream.get("width") else None
        raw_fps = video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") if video_stream else None
        frame_rate = _parse_frame_rate(raw_fps)

        audio_codec = audio_stream.get("codec_name") if audio_stream else None
        sample_rate = int(audio_stream.get("sample_rate")) if audio_stream and audio_stream.get("sample_rate") else None

        # Tags extraction from format and streams
        fmt_tags = fmt.get("tags") or {}
        encoder = (
            fmt_tags.get("encoder")
            or (video_stream.get("tags", {}).get("encoder") if video_stream else None)
            or (audio_stream.get("tags", {}).get("encoder") if audio_stream else None)
            or fmt_tags.get("compatible_brands")
        )
        creation_time = (
            fmt_tags.get("creation_time")
            or (video_stream.get("tags", {}).get("creation_time") if video_stream else None)
            or (audio_stream.get("tags", {}).get("creation_time") if audio_stream else None)
        )

        findings: list[str] = []
        fmt_name = fmt.get("format_name", "unknown")
        dur_str = f", duration: {duration_sec}s" if duration_sec is not None else ""
        findings.append(f"Container format: {fmt_name}{dur_str}.")

        if video_stream:
            fps_str = f" at {frame_rate}" if frame_rate else ""
            findings.append(f"Video stream: {video_codec} ({resolution}{fps_str}).")
        if audio_stream:
            sr_str = f", {sample_rate} Hz" if sample_rate else ""
            channels = audio_stream.get("channels")
            ch_str = f", {channels} ch" if channels else ""
            findings.append(f"Audio stream: {audio_codec}{sr_str}{ch_str}.")

        if encoder:
            findings.append(f"Encoder / authoring software identified: {encoder}.")
        if creation_time:
            findings.append(f"Creation timestamp identified: {creation_time}.")
        if not encoder and not creation_time:
            findings.append(
                "No encoder software or creation timestamp tags were found; missing container "
                "metadata is neutral evidence and does not indicate manipulation."
            )

        return MetadataResult(
            status="completed",
            format=fmt,
            streams=streams,
            duration_seconds=duration_sec,
            video_codec=video_codec,
            audio_codec=audio_codec,
            resolution=resolution,
            frame_rate=frame_rate,
            sample_rate=sample_rate,
            encoder=str(encoder) if encoder else None,
            creation_time=str(creation_time) if creation_time else None,
            findings=findings,
        )
    except Exception as exc:
        logger.warning("FFprobe metadata inspection failed: %s", exc)
        return MetadataResult(
            status="unavailable",
            findings=[f"Metadata inspection unavailable ({type(exc).__name__}): {str(exc)[:200]}"],
        )


def inspect_metadata(path: Path, extension: str, settings: Settings, raw_metadata: MetadataResult | None = None) -> MetadataResult:
    """Entry point for full metadata extraction."""
    ext = extension.lower()
    if ext in (".jpg", ".jpeg", ".png"):
        return _extract_image_metadata(path, ext)
    return _extract_av_metadata(path, ext, settings, raw_metadata=raw_metadata)
