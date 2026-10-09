"""Phase 6 unit tests — Evidence Fusion and Digital Trust Score calculations."""
import uuid

import pytest

from app.schemas import (
    AnalysisResponse,
    AnalyzerResult,
    FrameScore,
    MetadataResult,
    PreprocessingResult,
    ProvenanceResult,
    VisualResult,
)
from app.services.fusion import (
    DISCLAIMER,
    PROVENANCE_BOOST,
    PROVENANCE_PENALTY,
    WEIGHT_AUDIO,
    WEIGHT_VISUAL,
    fuse_evidence,
    map_risk_level,
)


def make_analysis(
    visual_status="completed",
    visual_synthetic_prob=0.10,
    audio_status="completed",
    audio_synthetic_prob=0.20,
    provenance_status="not_present",
    provenance_verified=False,
    media_type="video",
    num_frames=12,
    num_elevated_frames=0,
) -> AnalysisResponse:
    frames = []
    if num_frames > 0:
        for i in range(num_frames):
            prob = 0.85 if i < num_elevated_frames else visual_synthetic_prob
            frames.append(
                FrameScore(
                    index=i,
                    sample_time_seconds=float(i),
                    path=f"frames/frame_{i}.png",
                    synthetic_probability=prob,
                    confidence=max(prob, 1.0 - prob),
                )
            )

    return AnalysisResponse(
        analysis_id=uuid.uuid4(),
        filename=f"sample.{'mp4' if media_type == 'video' else ('png' if media_type == 'image' else 'wav')}",
        media_type=media_type,
        sha256="a" * 64,
        size_bytes=1000,
        visual=VisualResult(
            status=visual_status,
            synthetic_probability=visual_synthetic_prob if visual_status == "completed" else None,
            confidence=0.85 if visual_status == "completed" else None,
            frame_scores=frames,
        ),
        audio=AnalyzerResult(
            status=audio_status,
            synthetic_probability=audio_synthetic_prob if audio_status == "completed" else None,
            confidence=0.80 if audio_status == "completed" else None,
        ),
        metadata=MetadataResult(status="completed"),
        provenance=ProvenanceResult(
            status=provenance_status,
            verified=provenance_verified,
        ),
        preprocessing=PreprocessingResult(
            source_path="uploads/source.mp4",
        ),
    )


def test_risk_level_mapping():
    assert map_risk_level(None) == "unavailable"
    assert map_risk_level(0) == "high"
    assert map_risk_level(39) == "high"
    assert map_risk_level(40) == "review"
    assert map_risk_level(69) == "review"
    assert map_risk_level(70) == "low"
    assert map_risk_level(100) == "low"


def test_video_and_audio_fusion():
    """Both visual (synthetic_prob=0.20 -> auth=0.80) and audio (synthetic_prob=0.10 -> auth=0.90) available."""
    analysis = make_analysis(
        visual_synthetic_prob=0.20,
        audio_synthetic_prob=0.10,
        provenance_status="not_present",
    )
    fuse_evidence(analysis)

    # Expected: 0.60 * 0.80 + 0.40 * 0.90 = 0.48 + 0.36 = 0.84 -> score = 84
    assert analysis.trust_score == 84
    assert analysis.risk_level == "low"
    assert DISCLAIMER in analysis.limitations


def test_image_only_fusion():
    """Visual only (synthetic_prob=0.10 -> auth=0.90); audio not_applicable."""
    analysis = make_analysis(
        visual_synthetic_prob=0.10,
        audio_status="not_applicable",
        media_type="image",
        num_frames=0,
    )
    fuse_evidence(analysis)

    # Expected: 100% visual -> 0.90 * 100 = 90
    assert analysis.trust_score == 90
    assert analysis.risk_level == "low"
    assert any("visual evidence alone" in f.lower() for f in analysis.findings)


def test_audio_only_fusion():
    """Audio only (synthetic_prob=0.75 -> auth=0.25); visual not_applicable."""
    analysis = make_analysis(
        visual_status="not_applicable",
        audio_synthetic_prob=0.75,
        media_type="audio",
        num_frames=0,
    )
    fuse_evidence(analysis)

    # Expected: 100% audio -> 0.25 * 100 = 25
    assert analysis.trust_score == 25
    assert analysis.risk_level == "high"
    assert any("audio evidence alone" in f.lower() for f in analysis.findings)


def test_unavailable_analyzers_do_not_crash_scoring():
    """Visual unavailable, audio completed (synthetic_prob=0.50 -> auth=0.50)."""
    analysis = make_analysis(
        visual_status="unavailable",
        audio_synthetic_prob=0.50,
        provenance_status="not_present",
    )
    fuse_evidence(analysis)

    # Expected: audio alone = 50
    assert analysis.trust_score == 50
    assert analysis.risk_level == "review"
    assert any("visual analysis was unavailable" in f.lower() for f in analysis.findings)


def test_all_unavailable_reports_unavailable():
    """Both visual and audio unavailable -> trust_score is None, risk_level is unavailable."""
    analysis = make_analysis(
        visual_status="unavailable",
        audio_status="unavailable",
    )
    fuse_evidence(analysis)

    assert analysis.trust_score is None
    assert analysis.risk_level == "unavailable"
    assert any("insufficient modality signals" in f.lower() for f in analysis.findings)


def test_provenance_boost_and_neutrality():
    """Verified provenance adds boost (+10), missing provenance is neutral (0)."""
    neutral_analysis = make_analysis(visual_synthetic_prob=0.30, audio_synthetic_prob=0.30, provenance_status="not_present")
    fuse_evidence(neutral_analysis)
    neutral_score = neutral_analysis.trust_score  # (1 - 0.3) * 100 = 70

    verified_analysis = make_analysis(visual_synthetic_prob=0.30, audio_synthetic_prob=0.30, provenance_status="verified", provenance_verified=True)
    fuse_evidence(verified_analysis)
    verified_score = verified_analysis.trust_score  # 70 + 10 = 80

    assert verified_score == neutral_score + 10
    assert any("neutral evidence" in f.lower() for f in neutral_analysis.findings)
    assert any("confirm asset provenance" in f.lower() for f in verified_analysis.findings)


def test_provenance_penalty_on_invalid():
    """Invalid provenance applies penalty (-20)."""
    neutral_analysis = make_analysis(visual_synthetic_prob=0.30, audio_synthetic_prob=0.30, provenance_status="not_present")
    fuse_evidence(neutral_analysis)

    invalid_analysis = make_analysis(visual_synthetic_prob=0.30, audio_synthetic_prob=0.30, provenance_status="invalid", provenance_verified=False)
    fuse_evidence(invalid_analysis)

    assert invalid_analysis.trust_score == neutral_analysis.trust_score - 20
    assert any("failed cryptographic validation" in f.lower() for f in invalid_analysis.findings)


def test_score_clamping():
    """Scores cannot exceed 100 or go below 0."""
    high_analysis = make_analysis(visual_synthetic_prob=0.0, audio_synthetic_prob=0.0, provenance_status="verified", provenance_verified=True)
    fuse_evidence(high_analysis)
    assert high_analysis.trust_score == 100

    low_analysis = make_analysis(visual_synthetic_prob=1.0, audio_synthetic_prob=1.0, provenance_status="invalid")
    fuse_evidence(low_analysis)
    assert low_analysis.trust_score == 0
    assert low_analysis.risk_level == "high"


def test_template_frame_findings():
    """Verifies that frame-level template counts elevated frames deterministically."""
    analysis = make_analysis(
        visual_synthetic_prob=0.10,
        audio_status="not_applicable",
        num_frames=12,
        num_elevated_frames=8,
    )
    fuse_evidence(analysis)
    assert any("elevated synthetic-media indicators in 8 of 12 sampled frames" in f for f in analysis.findings)
