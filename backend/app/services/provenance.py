"""Phase 5 — Provenance and Content Credentials (C2PA) verification service.

Uses c2pa-python when available to read and verify C2PA manifests.
Reports statuses:
  - verified: Valid C2PA manifest found with verified integrity
  - invalid: C2PA manifest found but validation failed
  - not_present: No C2PA manifest found (neutral evidence, NOT proof of manipulation)
  - unavailable: C2PA verification library not installed or cannot run
  - error: Error reading provenance store

Missing C2PA credentials are treated as neutral evidence.
"""
import json
import logging
from pathlib import Path

from app.schemas import ProvenanceResult

logger = logging.getLogger(__name__)

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".mp4": "video/mp4",
    ".wav": "audio/x-wav",
    ".mp3": "audio/mpeg",
}

NEUTRAL_DETAILS = [
    "No C2PA Content Credentials found. The absence of provenance metadata is neutral evidence and does not indicate manipulation."
]


def verify_provenance(path: Path, extension: str) -> ProvenanceResult:
    """Inspect file for C2PA content credentials."""
    ext = extension.lower()
    mime_type = MIME_TYPES.get(ext)
    if not mime_type:
        return ProvenanceResult(
            status="not_present",
            verified=False,
            details=NEUTRAL_DETAILS,
        )

    try:
        import c2pa  # type: ignore[import]
    except ImportError:
        return ProvenanceResult(
            status="unavailable",
            verified=False,
            details=[
                "c2pa library is not installed on this system; provenance verification is unavailable. Missing provenance is neutral evidence."
            ],
        )

    try:
        try:
            reader = c2pa.Reader(str(path))
        except Exception as read_exc:
            exc_str = str(read_exc).lower()
            if isinstance(read_exc, getattr(c2pa.C2paError, "ManifestNotFound", ())) or any(k in exc_str for k in ("not found", "manifestnotfound", "no jumbf", "no manifest", "empty")):
                return ProvenanceResult(
                    status="not_present",
                    verified=False,
                    details=NEUTRAL_DETAILS,
                )
            logger.debug("C2PA reader exception on %s: %s", path.name, read_exc)
            return ProvenanceResult(
                status="not_present",
                verified=False,
                details=NEUTRAL_DETAILS,
            )

        raw_json = reader.json()
        if not raw_json or raw_json.strip() in ("{}", "null", ""):
            return ProvenanceResult(
                status="not_present",
                verified=False,
                details=NEUTRAL_DETAILS,
            )

        store = json.loads(raw_json)
        active_manifest = store.get("active_manifest")
        validation_status = store.get("validation_status", [])

        errors = [
            v for v in validation_status
            if isinstance(v, dict) and v.get("status") in ("error", "invalid")
        ]
        if errors:
            error_msgs = [e.get("explanation", str(e)) for e in errors[:3]]
            return ProvenanceResult(
                status="invalid",
                verified=False,
                details=[
                    "C2PA Content Credentials manifest failed validation:",
                    *error_msgs,
                ],
            )

        details = []
        if active_manifest and isinstance(active_manifest, dict):
            claim_generator = active_manifest.get("claim_generator")
            title = active_manifest.get("title")
            if claim_generator:
                details.append(f"Claim generator: {claim_generator}")
            if title:
                details.append(f"Manifest title: {title}")
        details.append(
            "C2PA Content Credentials verified successfully with intact cryptographic bindings."
        )

        return ProvenanceResult(
            status="verified",
            verified=True,
            details=details,
        )

    except Exception as exc:
        exc_str = str(exc).lower()
        if any(k in exc_str for k in ("not found", "manifestnotfound", "no manifest", "empty")):
            return ProvenanceResult(
                status="not_present",
                verified=False,
                details=NEUTRAL_DETAILS,
            )
        logger.warning("Unexpected provenance error: %s", exc)
        return ProvenanceResult(
            status="error",
            verified=False,
            details=[f"Provenance verification error: {str(exc)[:200]}"],
        )
