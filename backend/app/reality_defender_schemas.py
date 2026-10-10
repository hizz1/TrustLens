"""Reality Defender evidence is separate from TrustLens local-model fusion."""
from typing import Literal

from pydantic import BaseModel, Field

VendorStatus = Literal["AUTHENTIC", "FAKE", "SUSPICIOUS", "NOT_APPLICABLE", "UNABLE_TO_EVALUATE", "ANALYZING", "DOWNLOADING", "UNKNOWN"]


class RealityDefenderModel(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    status: VendorStatus
    manipulation_score: float | None = Field(default=None, strict=True, ge=0, le=100, allow_inf_nan=False)


class RealityDefenderResult(BaseModel):
    status: Literal["completed", "not_applicable", "unavailable"] = "unavailable"
    message: str = "Reality Defender could not complete detection."
    request_id: str | None = None
    upload_attempted: bool = False
    verdict: VendorStatus = "UNKNOWN"
    manipulation_score: float | None = Field(default=None, strict=True, ge=0, le=100, allow_inf_nan=False)
    indicator_score: int | None = Field(default=None, ge=0, le=100)
    models: list[RealityDefenderModel] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=lambda: [
        "Reality Defender scores and verdicts are vendor model outputs, not forensic proof or guarantees of authenticity.",
        "The Reality Defender indicator is 100 minus the vendor ensemble manipulation score, rounded. It is separate from local evidence fusion.",
        "This integration reports ensemble and model results; it does not claim face bounding boxes, voice identity, or music-specific detection.",
    ])
