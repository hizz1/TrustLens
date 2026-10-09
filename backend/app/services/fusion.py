"""Phase 6 — Evidence Fusion and Digital Trust Score calculation service.

Combines visual authenticity (1 - visual_synthetic_prob) and audio authenticity
(1 - audio_synthetic_prob) using deterministic weighting:
  - Visual weight: 0.60
  - Audio weight: 0.40
Weights normalize automatically around available evidence.
Missing provenance is strictly neutral (0 adjustment).
Verified C2PA provenance adds +10 points.
Invalid C2PA provenance penalizes -20 points.

Risk levels:
  - 0–39: high (HIGH RISK)
  - 40–69: review (REVIEW)
  - 70–100: low (LOWER RISK)

Does NOT use LLMs. All explanations are deterministic templates.
Does NOT claim forensic proof or guaranteed detection.
"""
from typing import Literal

from app.schemas import AnalysisResponse

DISCLAIMER = (
    "Higher scores indicate that available evidence is more consistent with authentic media. "
    "The Digital Trust Score is an experimental decision-support metric and is not forensic proof."
)

WEIGHT_VISUAL = 0.60
WEIGHT_AUDIO = 0.40
PROVENANCE_BOOST = 10.0
PROVENANCE_PENALTY = -20.0


def map_risk_level(score: int | None) -> Literal["high", "review", "low", "unavailable"]:
    if score is None:
        return "unavailable"
    if score <= 39:
        return "high"
    if score <= 69:
        return "review"
    return "low"


def fuse_evidence(analysis: AnalysisResponse) -> None:
    """Computes trust_score, risk_level, fusion findings, and standardized limitations in-place."""
    has_visual = (
        analysis.visual.status == "completed"
        and analysis.visual.synthetic_probability is not None
    )
    has_audio = (
        analysis.audio.status == "completed"
        and analysis.audio.synthetic_probability is not None
    )

    fusion_findings: list[str] = []

    # 1. Evaluate visual findings template
    if has_visual:
        v_prob = analysis.visual.synthetic_probability
        if analysis.visual.frame_scores:
            elevated = sum(1 for f in analysis.visual.frame_scores if f.synthetic_probability >= 0.5)
            total = len(analysis.visual.frame_scores)
            fusion_findings.append(
                f"Visual analysis identified elevated synthetic-media indicators in {elevated} of {total} sampled frames."
            )
        else:
            level_desc = "elevated" if v_prob >= 0.5 else "low"
            fusion_findings.append(
                f"Visual analysis identified {level_desc} synthetic-media indicators (synthetic probability: {v_prob:.2f})."
            )
    elif analysis.visual.status == "unavailable":
        fusion_findings.append("Visual analysis was unavailable; visual signals excluded from fusion.")

    # 2. Evaluate audio findings template
    if has_audio:
        a_prob = analysis.audio.synthetic_probability
        level_desc = "elevated" if a_prob >= 0.5 else "low"
        fusion_findings.append(
            f"Audio analysis identified {level_desc} synthetic-speech indicators (synthetic probability: {a_prob:.2f})."
        )
    elif analysis.audio.status == "unavailable":
        fusion_findings.append("Audio analysis was unavailable; audio signals excluded from fusion.")

    # 3. Evaluate provenance
    prov_adjustment = 0.0
    if analysis.provenance.status == "verified" and analysis.provenance.verified:
        prov_adjustment = PROVENANCE_BOOST
        fusion_findings.append(
            "Cryptographically verified Content Credentials (C2PA) confirm asset provenance (+10 trust points)."
        )
    elif analysis.provenance.status == "invalid":
        prov_adjustment = PROVENANCE_PENALTY
        fusion_findings.append(
            "Content Credentials (C2PA) manifest failed cryptographic validation (-20 trust points)."
        )
    else:
        fusion_findings.append(
            "No verifiable Content Credentials were found. Their absence is treated as neutral evidence."
        )

    # 4. Authenticity score fusion
    if not has_visual and not has_audio:
        analysis.trust_score = None
        analysis.risk_level = "unavailable"
        fusion_findings.append("Insufficient modality signals available to calculate a Digital Trust Score.")
    else:
        v_auth = (1.0 - analysis.visual.synthetic_probability) if has_visual else 0.0
        a_auth = (1.0 - analysis.audio.synthetic_probability) if has_audio else 0.0

        if has_visual and has_audio:
            tot_weight = WEIGHT_VISUAL + WEIGHT_AUDIO
            base_auth = (v_auth * WEIGHT_VISUAL + a_auth * WEIGHT_AUDIO) / tot_weight
            fusion_findings.append(
                f"Evidence weighted across visual ({int(WEIGHT_VISUAL*100)}%) and audio ({int(WEIGHT_AUDIO*100)}%) modalities."
            )
        elif has_visual:
            base_auth = v_auth
            fusion_findings.append("Score computed from visual evidence alone (100% visual weight).")
        else:
            base_auth = a_auth
            fusion_findings.append("Score computed from audio evidence alone (100% audio weight).")

        raw_score = base_auth * 100.0 + prov_adjustment
        clamped_score = int(round(max(0.0, min(100.0, raw_score))))
        analysis.trust_score = clamped_score
        analysis.risk_level = map_risk_level(clamped_score)
        fusion_findings.append(
            f"Digital Trust Score calculated at {clamped_score}/100 ({analysis.risk_level.upper()} RISK)."
        )

    analysis.findings.extend(fusion_findings)
    analysis.limitations = [
        *analysis.visual.limitations,
        DISCLAIMER,
        "Analyses are produced by heuristic and pretrained deep-learning models without forensic guarantees.",
        "Adversarial manipulations, compression artifacts, or out-of-distribution media may affect score precision.",
    ]
