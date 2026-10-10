"""Reality Defender REST upload and bounded polling; secrets stay server-side."""
import re
import time
from urllib.parse import urlsplit

import httpx

from app.config import Settings
from app.reality_defender_schemas import RealityDefenderModel, RealityDefenderResult
from app.schemas import AnalysisResponse

API_BASE = "https://api.prd.realitydefender.xyz"
UPLOAD_ENDPOINT = API_BASE + "/api/files/aws-presigned"
RESULT_ENDPOINT = API_BASE + "/api/media/users/"
PENDING = {"ANALYZING", "DOWNLOADING"}
VERDICTS = {"AUTHENTIC", "FAKE", "SUSPICIOUS"}
STATUSES = VERDICTS | PENDING | {"NOT_APPLICABLE", "UNABLE_TO_EVALUATE", "UNKNOWN"}
SIZE_LIMITS = {"image": 50_000_000, "audio": 20_000_000, "video": 250_000_000}


class RealityDefenderUnavailable(Exception):
    """Only safe, fixed messages; no raw upstream bodies, URLs, or credentials."""


def validate_upload_url(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Missing upload URL")
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    # Current accounts may return Reality Defender's upload proxy or AWS S3.
    # Authentication is in the signed URL; never attach the API key to PUT.
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443)
        or parsed.fragment or not (host == urlsplit(API_BASE).hostname or
            re.fullmatch(r"(?:[a-z0-9][a-z0-9.-]*\.)?s3(?:[.-][a-z0-9-]+)?\.amazonaws\.com", host))):
        raise ValueError("Unexpected upload destination")
    return value


def validate_request_id(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError("Invalid request ID")
    return value


def parse_result(payload: object, request_id: str, media_type: str) -> RealityDefenderResult:
    if not isinstance(payload, dict) or payload.get("requestId") != request_id:
        raise ValueError("Mismatched result")
    if payload.get("mediaType") != media_type.upper():
        raise ValueError("Wrong media type")
    summary = payload.get("resultsSummary")
    if summary is not None and not isinstance(summary, dict):
        raise ValueError("Invalid summary")
    verdict = summary.get("status", payload.get("overallStatus")) if summary is not None else payload.get("overallStatus")
    if not isinstance(verdict, str) or verdict not in STATUSES:
        raise ValueError("Unknown ensemble status")
    metadata = summary.get("metadata", {}) if summary is not None else {}
    if not isinstance(metadata, dict):
        raise ValueError("Invalid score metadata")
    result = RealityDefenderResult(request_id=request_id, upload_attempted=True, verdict=verdict)
    if verdict in VERDICTS:
        result = RealityDefenderResult(status="completed", request_id=request_id, upload_attempted=True,
            verdict=verdict, manipulation_score=metadata.get("finalScore"),
            message="Reality Defender returned an ensemble verdict.")
        if result.manipulation_score is not None:
            result.indicator_score = int(100 - result.manipulation_score + 0.5)
    elif verdict == "NOT_APPLICABLE":
        result.status = "not_applicable"
        result.message = "Reality Defender could not apply its detectors to this media; this is neutral, not an authenticity verdict."
    elif verdict in PENDING:
        result.message = "Reality Defender is still processing this upload."
    else:
        result.message = "Reality Defender was unable to evaluate this media."
    raw_models = payload.get("models", [])
    if not isinstance(raw_models, list):
        raise ValueError("Invalid model list")
    for model in raw_models:
        if not isinstance(model, dict):
            raise ValueError("Invalid model")
        name = model.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_. ()-]{1,120}", name):
            raise ValueError("Invalid model name")
        status = model.get("status", "UNKNOWN")
        if not isinstance(status, str):
            raise ValueError("Invalid model status")
        result.models.append(RealityDefenderModel(name=name, status=status if status in STATUSES else "UNKNOWN",
            manipulation_score=model.get("finalScore") if status in VERDICTS else None))
    return result


def check_http(response: httpx.Response) -> None:
    if 200 <= response.status_code < 300:
        return
    if response.status_code == 403:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and payload.get("code") == "free-tier-restriction":
            raise RealityDefenderUnavailable(
                "Reality Defender's free tier does not support video uploads. "
                "Video analysis through this API requires a paid plan; images and audio are supported on the free tier. "
                "Independent local analysis is shown below."
            )
    messages = {401: "Reality Defender rejected the API credential.",
        403: "Reality Defender denied access; check account permissions and supported media on your plan.",
        429: "Reality Defender rate limit or scan quota was reached.",
        413: "Reality Defender rejected the upload size."}
    raise RealityDefenderUnavailable(messages.get(response.status_code,
        f"Reality Defender request failed (HTTP {response.status_code})."))


class RealityDefenderAnalyzer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def analyze(self, analysis: AnalysisResponse) -> RealityDefenderResult:
        result = RealityDefenderResult()
        try:
            key = self.settings.reality_defender_api_key.get_secret_value()
            if not key:
                raise RealityDefenderUnavailable("Reality Defender API key is not configured.")
            path = (self.settings.data_dir / analysis.preprocessing.source_path).resolve()
            if not path.is_relative_to(self.settings.data_dir.resolve()):
                raise RealityDefenderUnavailable("Prepared file is outside the configured data directory.")
            if max(path.stat().st_size, analysis.size_bytes) > min(SIZE_LIMITS[analysis.media_type], self.settings.max_upload_bytes):
                raise RealityDefenderUnavailable("File exceeds the Reality Defender media upload limit; it was not sent.")
            deadline = time.monotonic() + self.settings.reality_defender_timeout_seconds

            def remaining() -> float:
                value = deadline - time.monotonic()
                if value <= 0:
                    raise RealityDefenderUnavailable("Reality Defender processing timed out; an uploaded file may still be processed remotely.")
                return min(value, self.settings.reality_defender_request_timeout_seconds)

            # Credentials are attached per API request, never as client defaults.
            headers = {"X-API-KEY": key}
            with httpx.Client(follow_redirects=False) as client:
                response = client.post(UPLOAD_ENDPOINT, headers=headers,
                    json={"fileName": f"{analysis.analysis_id}{path.suffix}"}, timeout=remaining())
                check_http(response)
                payload = response.json()
                result.request_id = validate_request_id(payload["requestId"])
                upload_url = validate_upload_url(payload["response"]["signedUrl"])
                with path.open("rb") as source:
                    result.upload_attempted = True
                    response = client.put(upload_url, content=source, timeout=remaining())
                check_http(response)
                for attempt in range(self.settings.reality_defender_max_poll_attempts):
                    response = client.get(RESULT_ENDPOINT + result.request_id, headers=headers, timeout=remaining())
                    if response.status_code != 404:
                        check_http(response)
                        parsed = parse_result(response.json(), result.request_id, analysis.media_type)
                        if parsed.verdict not in PENDING:
                            result = parsed
                            break
                        result.verdict = parsed.verdict
                    if attempt + 1 == self.settings.reality_defender_max_poll_attempts:
                        raise RealityDefenderUnavailable("Reality Defender is still processing after the polling limit; local analysis is preserved.")
                    time.sleep(min(self.settings.reality_defender_poll_interval_seconds, remaining()))
        except RealityDefenderUnavailable as exc:
            result.message = str(exc)
        except httpx.TimeoutException:
            result.message = "Reality Defender request timed out; a submitted file may still be processed remotely."
        except httpx.RequestError:
            result.message = "Reality Defender could not be reached."
        except OSError:
            result.message = "Prepared media could not be read for Reality Defender."
        except (ValueError, TypeError, KeyError):
            result.message = "Reality Defender returned an invalid or unsupported response."
        except Exception:
            result.message = "Reality Defender could not complete detection."
        if result.upload_attempted:
            result.limitations.append("Media was submitted or attempted to be submitted to Reality Defender under its data handling policies. Local results do not undo a remote upload.")
        return result
