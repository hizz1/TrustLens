"""Server-side BitMind client. Never logs credentials or raw upstream responses."""
import mimetypes

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.config import Settings
from app.schemas import AnalysisResponse, VisualResult

ENDPOINT = "https://api.bitmind.ai/v1/detect"
MODEL_ID = "BitMind API"


class BitMindUnavailable(Exception):
    """A safe, user-facing reason to use the local model instead."""


class DetectionPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    isAI: StrictBool
    confidence: float = Field(strict=True, ge=0, le=1, allow_inf_nan=False)


class DetectionEnvelope(BaseModel):
    mediaType: str
    result: DetectionPayload


class BitMindAnalyzer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def analyze(self, analysis: AnalysisResponse) -> VisualResult:
        if analysis.media_type not in ("image", "video"):
            raise BitMindUnavailable("BitMind does not support audio; audio is analyzed locally.")
        key = self.settings.bitmind_api_key.get_secret_value()
        if not key:
            raise BitMindUnavailable("BitMind API key is not configured.")
        if analysis.size_bytes > self.settings.bitmind_max_upload_bytes:
            raise BitMindUnavailable("File exceeds BitMind's 10 MB direct-upload limit; it was not sent to BitMind.")
        path = (self.settings.data_dir / analysis.preprocessing.source_path).resolve()
        if not path.is_relative_to(self.settings.data_dir.resolve()):
            raise BitMindUnavailable("Prepared file is outside the configured data directory.")
        try:
            with path.open("rb") as source, httpx.Client(
                timeout=self.settings.bitmind_timeout_seconds, follow_redirects=False,
            ) as client:
                response = client.post(
                    ENDPOINT, headers={"Authorization": f"Bearer {key}"},
                    files={"file": ("media" + path.suffix, source, mimetypes.guess_type(path.name)[0] or "application/octet-stream")},
                )
            if response.status_code != 200:
                reasons = {401: "BitMind rejected the API credential.", 403: "BitMind denied access for this API key.",
                           429: "BitMind rate limit or quota was reached.", 413: "BitMind rejected the upload size."}
                raise BitMindUnavailable(reasons.get(response.status_code, f"BitMind request failed (HTTP {response.status_code})."))
            envelope = DetectionEnvelope.model_validate(response.json())
            if envelope.mediaType != analysis.media_type:
                raise ValueError("Wrong media type")
        except BitMindUnavailable:
            raise
        except httpx.TimeoutException:
            raise BitMindUnavailable("BitMind request timed out.") from None
        except httpx.RequestError:
            raise BitMindUnavailable("BitMind could not be reached.") from None
        except (ValueError, TypeError):
            raise BitMindUnavailable("BitMind returned an invalid or unsupported response.") from None
        except OSError:
            raise BitMindUnavailable("Prepared file could not be read for BitMind.") from None
        payload = envelope.result
        return VisualResult(
            status="completed", is_ai=payload.isAI, confidence=payload.confidence,
            model_id=MODEL_ID, device="remote",
            confidence_definition="Confidence reported by BitMind; vendor metric, not independently calibrated by TrustLens.",
            findings=[
                "BitMind classified this media as " + ("AI-generated." if payload.isAI else "not AI-generated."),
                f"BitMind reported confidence: {payload.confidence:.1%}.",
                "BitMind's documented response does not define confidence as a synthetic probability; its verdict is displayed separately from the Digital Trust Score.",
            ],
            limitations=[
                "This file was sent to BitMind for remote detection and is subject to its data handling policies.",
                "BitMind detects AI-generated content; this is not a dedicated facial-manipulation verdict or forensic proof.",
                "BitMind does not return per-frame scores in this endpoint; no suspicious-frame ranking is fabricated.",
                "The Digital Trust Score excludes the BitMind verdict; any available score uses local audio and provenance evidence only.",
            ],
        )
