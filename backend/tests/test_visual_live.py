"""Opt-in real checkpoint smoke checks; not an accuracy benchmark."""
import os

import pytest
from fastapi.testclient import TestClient

from app.analyzers.visual import VisualAnalyzer
from app.config import Settings
from app.main import create_app
from test_media import samples
from test_visual import prepared

pytestmark = pytest.mark.skipif(os.environ.get("TRUSTLENS_RUN_MODEL_TESTS") != "1", reason="Opt-in pretrained-weight smoke tests")


def test_actual_checkpoint_cpu(tmp_path):
    analyzer = VisualAnalyzer(Settings(data_dir=tmp_path, visual_device="cpu", _env_file=None))
    result = analyzer.analyze(prepared(tmp_path))
    assert result.status == "completed", result.findings
    assert result.device == "cpu"
    assert 0 <= result.synthetic_probability <= 1


def test_actual_checkpoint_api_video_and_gpu(tmp_path, samples):
    import torch
    settings = Settings(data_dir=tmp_path, _env_file=None)
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/analyze", files={"file": ("video.mp4", (samples / "silent.mp4").read_bytes(), "video/mp4")})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["visual"]["status"] == "completed", result["visual"]["findings"]
    assert result["visual"]["device"] == ("cuda" if torch.cuda.is_available() else "cpu")
    assert len(result["visual"]["frame_scores"]) == 12
    assert isinstance(result["trust_score"], int) and 0 <= result["trust_score"] <= 100
    assert result["risk_level"] in ("high", "review", "low")
    assert result["audio"]["status"] == "not_applicable"
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}, peak allocated: {torch.cuda.max_memory_allocated()/1024**2:.1f} MiB")
