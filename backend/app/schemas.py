from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from app.reality_defender_schemas import RealityDefenderResult


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["trustlens-api"] = "trustlens-api"
    version: str = "0.1.0"


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class AnalyzerResult(BaseModel):
    status: Literal["completed", "unavailable", "not_applicable"]
    synthetic_probability: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    findings: list[str] = Field(default_factory=list)


class FrameScore(BaseModel):
    index: int
    sample_time_seconds: float
    path: str
    synthetic_probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)


class VisualResult(AnalyzerResult):
    is_ai: bool | None = None
    suspicious_frames: list[FrameScore] = Field(default_factory=list)
    frame_scores: list[FrameScore] = Field(default_factory=list)
    model_id: str | None = None
    model_revision: str | None = None
    device: str | None = None
    confidence_definition: str = "max(mean Fake softmax, mean Real softmax); uncalibrated model certainty, not accuracy"
    limitations: list[str] = Field(default_factory=list)


class MetadataResult(BaseModel):
    status: Literal["completed", "unavailable"] = "completed"
    format: dict[str, Any] = Field(default_factory=dict)
    streams: list[dict[str, Any]] = Field(default_factory=list)
    duration_seconds: float | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    resolution: str | None = None
    frame_rate: str | None = None
    sample_rate: int | None = None
    encoder: str | None = None
    creation_time: str | None = None
    findings: list[str] = Field(default_factory=list)


class ProvenanceResult(BaseModel):
    status: Literal["verified", "invalid", "not_present", "unavailable", "error"] = "not_present"
    verified: bool = False
    details: list[str] = Field(default_factory=lambda: [
        "No C2PA Content Credentials found. The absence of provenance metadata is neutral evidence and does not indicate manipulation."
    ])


class SampledFrame(BaseModel):
    index: int
    sample_time_seconds: float
    path: str


class PreprocessingResult(BaseModel):
    status: Literal["completed", "partial"] = "completed"
    source_path: str
    duration_seconds: float | None = None
    frames: list[SampledFrame] = Field(default_factory=list)
    audio_status: Literal["completed", "not_applicable", "unavailable"] = "not_applicable"
    audio_path: str | None = None


class AnalysisResponse(BaseModel):
    detection_provider: Literal["offline", "bitmind", "reality_defender"] = "offline"
    provider_used: Literal["offline", "bitmind", "reality_defender"] = "offline"
    reality_defender: RealityDefenderResult | None = None
    fallback_reason: str | None = None
    detection_mode: Literal["deepfake", "ai_generated"] = "deepfake"
    analysis_id: UUID
    filename: str
    media_type: Literal["image", "audio", "video"]
    sha256: str
    size_bytes: int
    trust_score: int | None = None
    risk_level: Literal["high", "review", "low", "unavailable"] = "unavailable"
    visual: VisualResult
    audio: AnalyzerResult
    metadata: MetadataResult
    provenance: ProvenanceResult = Field(default_factory=ProvenanceResult)
    preprocessing: PreprocessingResult
    findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=lambda: [
        "Digital Trust Score fusion is not implemented yet.",
        "This prototype does not provide forensic proof or guaranteed deepfake detection.",
    ])
