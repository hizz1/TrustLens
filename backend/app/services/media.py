import json
import math
import warnings
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import Settings
from app.schemas import (
    AnalysisResponse, AnalyzerResult, MetadataResult, PreprocessingResult,
    SampledFrame, VisualResult,
)
from app.services.cleanup import remove_analysis
from app.services.metadata import inspect_metadata
from app.utils.ffmpeg import MediaToolError, run_tool
from app.utils.hashing import save_and_hash

SUPPORTED = {".jpg": "image", ".jpeg": "image", ".png": "image", ".mp4": "video", ".wav": "audio", ".mp3": "audio"}
DEMUXERS = {".mp4": "mov", ".wav": "wav", ".mp3": "mp3"}


def image_metadata(path: Path, extension: str) -> MetadataResult:
    expected = "PNG" if extension == ".png" else "JPEG"
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format != expected:
                    raise HTTPException(422, "Image contents do not match the filename extension.")
                image.verify()
            with Image.open(path) as image:
                image.load()
                return MetadataResult(format={"format_name": expected.lower()}, streams=[{
                    "codec_type": "video", "width": image.width, "height": image.height, "mode": image.mode,
                }])
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(422, "Image cannot be safely decoded.") from exc


def input_arguments(path: Path, extension: str) -> list[str]:
    # Fixed demuxers reject disguised playlists; local file protocol only.
    return ["-protocol_whitelist", "file", "-f", DEMUXERS[extension], "-i", str(path)]


def probe(path: Path, extension: str, settings: Settings) -> MetadataResult:
    data = run_tool([
        settings.ffprobe_path, "-v", "error", *input_arguments(path, extension),
        "-show_format", "-show_streams", "-of", "json",
    ], settings.subprocess_timeout_seconds)
    try:
        payload = json.loads(data)
        metadata = MetadataResult(format=payload.get("format", {}), streams=payload.get("streams", []))
    except (ValueError, TypeError, AttributeError) as exc:
        raise MediaToolError("FFprobe returned invalid media information.") from exc
    metadata.format.pop("filename", None)
    return metadata


def positive_duration(value) -> float | None:
    try:
        seconds = float(value)
        return seconds if math.isfinite(seconds) and seconds > 0 else None
    except (TypeError, ValueError):
        return None


def normalize_audio(path: Path, extension: str, output: Path, stream_index: int, settings: Settings) -> None:
    run_tool([
        settings.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-xerror",
        *input_arguments(path, extension), "-map", f"0:{stream_index}", "-vn",
        "-t", str(settings.max_media_seconds), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output),
    ], settings.subprocess_timeout_seconds)
    if not output.exists() or output.stat().st_size <= 44:
        raise MediaToolError("No audio samples could be decoded.")


def extract_frames(path: Path, output_dir: Path, duration: float, stream_index: int, settings: Settings) -> list[SampledFrame]:
    # A single decode samples the whole video; padding handles very short/sparse clips.
    video_filter = (
        f"setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={duration:.9f},"
        f"fps=12/{duration:.9f}:start_time=0:round=near,"
        "scale=1280:1280:force_original_aspect_ratio=decrease"
    )
    run_tool([
        settings.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-xerror",
        *input_arguments(path, ".mp4"), "-map", f"0:{stream_index}", "-an", "-vf", video_filter,
        "-frames:v", "12", "-q:v", "2", str(output_dir / "frame_%02d.jpg"),
    ], settings.subprocess_timeout_seconds)
    frames = []
    for index in range(12):
        output = output_dir / f"frame_{index + 1:02d}.jpg"
        if not output.is_file() or output.stat().st_size == 0:
            raise MediaToolError("Video could not produce the required 12 representative frames.")
        frames.append(SampledFrame(
            index=index, sample_time_seconds=round(index * duration / 12, 6),
            path=output.relative_to(settings.data_dir).as_posix(),
        ))
    return frames


def prepare_media(upload: UploadFile, settings: Settings) -> AnalysisResponse:
    filename = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED:
        raise HTTPException(415, "Supported types: JPG, JPEG, PNG, MP4, WAV, MP3.")
    media_type = SUPPORTED[extension]
    analysis_id = str(uuid4())
    try:
        for category in ("uploads", "frames", "audio"):
            (settings.data_dir / category / analysis_id).mkdir(parents=True, exist_ok=False)
        source = settings.data_dir / "uploads" / analysis_id / f"source{extension}"
        fingerprint, size = save_and_hash(upload.file, source, settings.max_upload_bytes)
        prep = PreprocessingResult(source_path=source.relative_to(settings.data_dir).as_posix())
        findings = ["SHA-256 calculated from the original uploaded bytes."]
        has_audio = False
        if media_type == "image":
            metadata = image_metadata(source, extension)
            findings.append("Image decoded successfully.")
        else:
            metadata = probe(source, extension, settings)
            video = [s for s in metadata.streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")]
            audio = [s for s in metadata.streams if s.get("codec_type") == "audio"]
            has_audio = bool(audio)
            if media_type == "video" and not video:
                raise HTTPException(422, "MP4 must contain a decodable video stream.")
            if media_type == "audio" and (not audio or video):
                raise HTTPException(422, "Expected an audio-only file.")
            if extension == ".mp3" and audio[0].get("codec_name") != "mp3":
                raise HTTPException(422, "File contents are not MP3 audio.")
            primary = video[0] if media_type == "video" else audio[0]
            duration = positive_duration(primary.get("duration")) or positive_duration(metadata.format.get("duration"))
            if duration is None:
                raise HTTPException(422, "A positive finite media duration is required.")
            durations = [duration, positive_duration(metadata.format.get("duration")) or 0]
            durations.extend(positive_duration(s.get("duration")) or 0 for s in metadata.streams)
            if max(durations) > settings.max_media_seconds:
                raise HTTPException(413, "Media exceeds the configured duration limit.")
            prep.duration_seconds = duration
            if media_type == "video":
                prep.frames = extract_frames(source, settings.data_dir / "frames" / analysis_id, duration, int(primary["index"]), settings)
                findings.append("Extracted 12 frames at uniformly spaced sample times across the video.")
                findings.append("Frame times are sampling targets, not exact source timestamps; short or sparse clips may repeat frames.")
            if has_audio:
                output = settings.data_dir / "audio" / analysis_id / "normalized.wav"
                try:
                    normalize_audio(source, extension, output, int(audio[0]["index"]), settings)
                    prep.audio_status = "completed"
                    prep.audio_path = output.relative_to(settings.data_dir).as_posix()
                    findings.append("Created an analysis copy of the first audio stream: mono, 16 kHz, PCM WAV.")
                except MediaToolError as exc:
                    if media_type == "audio":
                        raise
                    output.unlink(missing_ok=True)
                    prep.audio_status = "unavailable"
                    prep.status = "partial"
                    findings.append(f"Audio preparation unavailable: {exc}")
            else:
                findings.append("No audio stream is present; audio preparation is not applicable.")
        metadata = inspect_metadata(source, extension, settings, raw_metadata=metadata)
        findings.extend(metadata.findings)
        return AnalysisResponse(
            analysis_id=analysis_id, filename=filename, media_type=media_type,
            sha256=fingerprint, size_bytes=size, metadata=metadata, preprocessing=prep,
            visual=VisualResult(status="not_applicable" if media_type == "audio" else "unavailable", findings=["Visual inference is not implemented yet."] if media_type != "audio" else []),
            audio=AnalyzerResult(status="unavailable" if has_audio else "not_applicable", findings=["Audio inference is not implemented yet."] if has_audio else []),
            findings=findings,
        )
    except Exception as exc:
        remove_analysis(settings.data_dir, analysis_id)
        if isinstance(exc, MediaToolError):
            raise HTTPException(exc.status_code, str(exc)) from exc
        raise
