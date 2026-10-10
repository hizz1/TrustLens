from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Query, Request, UploadFile

from app.schemas import AnalysisResponse, HealthResponse, ProvenanceResult
from app.services.fusion import fuse_evidence
from app.services.media import prepare_media
from app.services.provenance import verify_provenance
from app.analyzers.visual import unavailable as visual_unavailable
from app.analyzers.unifd import unavailable as unifd_unavailable
from app.analyzers.audio import unavailable as audio_unavailable
from app.analyzers.bitmind import BitMindUnavailable

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse()


@router.post("/analyze", response_model=AnalysisResponse, tags=["media"])
def analyze(
    request: Request,
    file: UploadFile = File(...),
    detection_mode: Literal["deepfake", "ai_generated"] = Query(default="deepfake", description="Offline video detection: facial deepfake or AI-generated frames (UniFD)."),
    detection_provider: Literal["offline", "bitmind", "reality_defender"] = Query(default="offline", description="Explicitly opt into BitMind or Reality Defender remote submission. Reality Defender supplements independent local checks.")
) -> AnalysisResponse:
    """Prepare a single file. Blocking decoding runs in FastAPI's worker thread."""
    try:
        result = prepare_media(file, request.app.state.settings)
        result.detection_mode = detection_mode if result.media_type == "video" else "deepfake"
        result.detection_provider = detection_provider
        if detection_provider == "reality_defender":
            try:
                result.reality_defender = request.app.state.reality_defender_analyzer.analyze(result)
                if result.reality_defender.status in ("completed", "not_applicable"):
                    result.provider_used = "reality_defender"
                else:
                    result.fallback_reason = result.reality_defender.message + " Local analysis is preserved."
                result.findings.append("Reality Defender: " + result.reality_defender.message)
            except Exception:
                result.fallback_reason = "Reality Defender could not complete detection; local analysis is preserved."
        if detection_provider == "bitmind":
            try:
                result.visual = request.app.state.bitmind_analyzer.analyze(result)
                result.provider_used = "bitmind"
            except BitMindUnavailable as exc:
                result.fallback_reason = str(exc)
            except Exception:
                result.fallback_reason = "BitMind could not complete detection."
            if result.fallback_reason:
                result.findings.append(result.fallback_reason + " Using offline analysis.")
        # Use appropriate visual analyzer based on detection mode
        if result.provider_used == "bitmind":
            pass
        elif result.detection_mode == "ai_generated":
            try:
                result.visual = request.app.state.unifd_analyzer.analyze(result)
            except Exception as exc:
                result.visual = unifd_unavailable(f"UniFD analyzer failed ({type(exc).__name__}); other evidence is preserved.")
        else:
            try:
                result.visual = request.app.state.visual_analyzer.analyze(result)
            except Exception as exc:
                result.visual = visual_unavailable(f"Visual analyzer failed ({type(exc).__name__}); other evidence is preserved.")
        result.findings.extend(result.visual.findings)
        result.limitations.extend(result.visual.limitations)
        try:
            result.audio = request.app.state.audio_analyzer.analyze(result)
        except Exception as exc:
            result.audio = audio_unavailable(f"Audio analyzer failed ({type(exc).__name__}); other evidence is preserved.")
        result.findings.extend(result.audio.findings)
        try:
            source_file = request.app.state.settings.data_dir / result.preprocessing.source_path
            result.provenance = verify_provenance(source_file, Path(result.filename).suffix)
        except Exception as exc:
            result.provenance = ProvenanceResult(status="error", verified=False, details=[f"Provenance verification failed ({type(exc).__name__})."])
        result.findings.extend(result.provenance.details)
        fuse_evidence(result)
        if result.reality_defender is not None:
            result.limitations.extend(result.reality_defender.limitations)
        return result
    finally:
        file.file.close()
