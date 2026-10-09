"""Opt-in checkpoint smoke test; does not measure detection accuracy."""
import os

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from test_media import samples

pytestmark = pytest.mark.skipif(os.environ.get("TRUSTLENS_RUN_UNIFD_TESTS") != "1", reason="Opt-in UniFD checkpoint smoke test")


@pytest.mark.parametrize("device", ["cpu", "auto"])
def test_real_video_api(tmp_path, samples, device):
    settings = Settings(data_dir=tmp_path, unifd_device=device, _env_file=None)
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/analyze?detection_mode=ai_generated",
            files={"file": ("video.mp4", (samples / "silent.mp4").read_bytes(), "video/mp4")})
    assert response.status_code == 200
    result = response.json()
    assert result["detection_mode"] == "ai_generated"
    assert result["visual"]["status"] == "completed", result["visual"]["findings"]
    assert len(result["visual"]["frame_scores"]) == 12
    assert len(result["visual"]["suspicious_frames"]) == 5
    assert 0 <= result["visual"]["synthetic_probability"] <= 1
    assert result["audio"]["status"] == "not_applicable"
    if device == "cpu":
        assert result["visual"]["device"] == "cpu"
    print(f"UniFD smoke test device: {result['visual']['device']}")
