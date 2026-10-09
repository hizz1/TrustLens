"""Opt-in real checkpoint smoke checks for audio; not an accuracy benchmark.

Run with:
    TRUSTLENS_RUN_MODEL_TESTS=1 python -m pytest tests/test_audio_live.py -v
"""
import os

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from test_media import samples  # noqa: F401 (fixture)

pytestmark = pytest.mark.skipif(
    os.environ.get("TRUSTLENS_RUN_MODEL_TESTS") != "1",
    reason="Opt-in pretrained-weight smoke tests",
)


def test_actual_audio_checkpoint_wav(tmp_path, samples):
    """POST a WAV file; audio analysis should complete with a real probability."""
    import torch
    settings = Settings(data_dir=tmp_path, _env_file=None)
    with TestClient(create_app(settings)) as client:
        wav_file = samples / "sample.wav"
        wav_bytes = wav_file.read_bytes() if wav_file.exists() else _make_wav_bytes()
        response = client.post("/api/analyze", files={"file": ("sample.wav", wav_bytes, "audio/wav")})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["audio"]["status"] == "completed", result["audio"]["findings"]
    assert 0 <= result["audio"]["synthetic_probability"] <= 1
    assert result["audio"]["confidence"] is not None
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")


def test_actual_audio_checkpoint_mp4_with_audio(tmp_path, samples):
    """MP4 with audio track → audio status completed."""
    settings = Settings(data_dir=tmp_path, _env_file=None)
    sound_mp4 = samples / "sound.mp4"
    if not sound_mp4.exists():
        pytest.skip("sound.mp4 not found in test samples")
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/analyze",
            files={"file": ("sound.mp4", sound_mp4.read_bytes(), "video/mp4")},
        )
    assert response.status_code == 200, response.text
    result = response.json()
    # Audio status should be completed (video had audio) or unavailable (prep failed)
    assert result["audio"]["status"] in ("completed", "unavailable"), result["audio"]


def test_actual_audio_checkpoint_silent_mp4(tmp_path, samples):
    """MP4 without audio → not_applicable."""
    settings = Settings(data_dir=tmp_path, _env_file=None)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/analyze",
            files={"file": ("silent.mp4", (samples / "silent.mp4").read_bytes(), "video/mp4")},
        )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["audio"]["status"] == "not_applicable"


# ---------------------------------------------------------------------------
# Minimal WAV generator (fallback if no sample file)
# ---------------------------------------------------------------------------

def _make_wav_bytes(duration_s: float = 2.0, sample_rate: int = 16_000) -> bytes:
    import io, struct, wave
    n = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{n}h", *([0] * n)))
    return buf.getvalue()
