"""Phase 5 unit tests — Metadata inspection and C2PA Provenance verification."""
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.schemas import MetadataResult, ProvenanceResult
from app.services.metadata import inspect_metadata
from app.services.provenance import verify_provenance
from test_media import samples  # noqa: F401 fixture


def test_image_metadata_extraction(tmp_path):
    img_path = tmp_path / "test.png"
    Image.new("RGB", (640, 480), "blue").save(img_path)
    settings = Settings(data_dir=tmp_path, _env_file=None)
    
    meta = inspect_metadata(img_path, ".png", settings)
    assert meta.status == "completed"
    assert meta.resolution == "640x480"
    assert meta.video_codec == "png"
    assert any("neutral" in f.lower() for f in meta.findings)


def test_video_metadata_extraction(tmp_path, samples):
    settings = Settings(data_dir=tmp_path, _env_file=None)
    sound_mp4 = samples / "sound.mp4"
    
    meta = inspect_metadata(sound_mp4, ".mp4", settings)
    assert meta.status == "completed"
    assert meta.duration_seconds is not None
    assert meta.video_codec is not None
    assert meta.audio_codec is not None
    assert meta.resolution is not None
    assert len(meta.streams) >= 2
    assert any("container format" in f.lower() for f in meta.findings)


def test_audio_metadata_extraction(tmp_path, samples):
    settings = Settings(data_dir=tmp_path, _env_file=None)
    sample_wav = samples / "sample.wav"
    
    meta = inspect_metadata(sample_wav, ".wav", settings)
    assert meta.status == "completed"
    assert meta.audio_codec is not None
    assert meta.sample_rate == 44100 or meta.sample_rate is not None
    assert any("audio stream" in f.lower() for f in meta.findings)


def test_ffprobe_failure_returns_unavailable_without_crash(tmp_path):
    settings = Settings(data_dir=tmp_path, ffprobe_path="nonexistent_probe", _env_file=None)
    dummy_mp4 = tmp_path / "dummy.mp4"
    dummy_mp4.write_bytes(b"not a real video")
    
    meta = inspect_metadata(dummy_mp4, ".mp4", settings)
    assert meta.status == "unavailable"
    assert len(meta.findings) > 0


def test_provenance_not_present_on_standard_file(tmp_path):
    img_path = tmp_path / "plain.jpg"
    Image.new("RGB", (100, 100), "white").save(img_path)
    
    prov = verify_provenance(img_path, ".jpg")
    assert prov.status == "not_present"
    assert prov.verified is False
    assert any("neutral" in d.lower() for d in prov.details)


def test_provenance_verified_mocked(tmp_path, monkeypatch):
    test_file = tmp_path / "c2pa_signed.jpg"
    test_file.write_bytes(b"fake_c2pa_bytes")
    
    fake_manifest_data = {
        "active_manifest": {
            "claim_generator": "Adobe Photoshop 2026",
            "title": "Authentic Photo",
        },
        "validation_status": [],
    }
    
    mock_reader = MagicMock()
    mock_reader.json.return_value = json.dumps(fake_manifest_data)
    
    import c2pa
    monkeypatch.setattr(c2pa, "Reader", lambda path: mock_reader)
    
    prov = verify_provenance(test_file, ".jpg")
    assert prov.status == "verified"
    assert prov.verified is True
    assert any("Adobe Photoshop" in d for d in prov.details)


def test_provenance_invalid_manifest_mocked(tmp_path, monkeypatch):
    test_file = tmp_path / "c2pa_tampered.jpg"
    test_file.write_bytes(b"fake_tampered_bytes")
    
    fake_manifest_data = {
        "active_manifest": {"title": "Tampered"},
        "validation_status": [
            {"status": "error", "explanation": "Hash mismatch: image content altered"}
        ],
    }
    
    mock_reader = MagicMock()
    mock_reader.json.return_value = json.dumps(fake_manifest_data)
    
    import c2pa
    monkeypatch.setattr(c2pa, "Reader", lambda path: mock_reader)
    
    prov = verify_provenance(test_file, ".jpg")
    assert prov.status == "invalid"
    assert prov.verified is False
    assert any("Hash mismatch" in d for d in prov.details)


def test_provenance_unavailable_when_c2pa_missing(tmp_path, monkeypatch):
    test_file = tmp_path / "any.png"
    test_file.write_bytes(b"data")
    
    import sys
    monkeypatch.setitem(sys.modules, "c2pa", None)
    
    prov = verify_provenance(test_file, ".png")
    assert prov.status in ("unavailable", "not_present")
    assert prov.verified is False


def test_api_analyze_returns_metadata_and_provenance(tmp_path, samples):
    settings = Settings(data_dir=tmp_path, visual_enabled=False, audio_enabled=False, _env_file=None)
    app = create_app(settings)
    
    with TestClient(app) as client:
        sound_mp4 = samples / "sound.mp4"
        response = client.post("/api/analyze", files={"file": ("sound.mp4", sound_mp4.read_bytes(), "video/mp4")})
        
    assert response.status_code == 200, response.text
    data = response.json()
    
    # Metadata assertions
    assert data["metadata"]["status"] == "completed"
    assert data["metadata"]["duration_seconds"] is not None
    assert data["metadata"]["video_codec"] is not None
    assert len(data["metadata"]["streams"]) >= 2
    
    # Provenance assertions
    assert data["provenance"]["status"] == "not_present"
    assert data["provenance"]["verified"] is False
    assert any("neutral" in d.lower() for d in data["provenance"]["details"])
    
    # Deterministic SHA-256
    import hashlib
    assert data["sha256"] == hashlib.sha256(sound_mp4.read_bytes()).hexdigest()
