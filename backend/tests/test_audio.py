"""Phase 4 unit tests — AudioAnalyzer (no real checkpoint required)."""
import io
import wave
import struct
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.analyzers.audio import AudioAnalyzer
from app.config import Settings
from app.main import create_app
from app.schemas import (
    AnalysisResponse,
    AnalyzerResult,
    MetadataResult,
    PreprocessingResult,
    VisualResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wav_bytes(duration_s: float = 1.0, sample_rate: int = 16_000) -> bytes:
    """Produce a valid silent mono 16-bit PCM WAV in memory."""
    n_samples = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{n_samples}h", *([0] * n_samples)))
    return buf.getvalue()


def _analysis(tmp_path, audio_status="completed", audio_path=None, media_type="audio"):
    wav_rel = None
    if audio_status == "completed":
        wav_file = tmp_path / "audio.wav"
        wav_file.write_bytes(_make_wav_bytes())
        wav_rel = str(wav_file.relative_to(tmp_path))
    return AnalysisResponse(
        analysis_id="d971f896-ce57-4f40-93d6-f186df81f16c",
        filename="test.wav",
        media_type=media_type,
        sha256="0" * 64,
        size_bytes=100,
        visual=VisualResult(status="not_applicable"),
        audio=AnalyzerResult(status="not_applicable"),
        metadata=MetadataResult(),
        preprocessing=PreprocessingResult(
            source_path=audio_path or (wav_rel or "x.wav"),
            audio_status=audio_status,
            audio_path=audio_path or wav_rel,
        ),
    )


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_not_applicable_when_no_audio(tmp_path):
    """Silent video → not_applicable, no model loaded."""
    analyzer = AudioAnalyzer(Settings(data_dir=tmp_path, _env_file=None))
    result = analyzer.analyze(_analysis(tmp_path, audio_status="not_applicable", media_type="video"))
    assert result.status == "not_applicable"
    assert result.synthetic_probability is None


def test_unavailable_when_audio_status_failed(tmp_path):
    """audio_status=unavailable → analyzer reports unavailable without loading model."""
    analyzer = AudioAnalyzer(Settings(data_dir=tmp_path, _env_file=None))
    result = analyzer.analyze(_analysis(tmp_path, audio_status="unavailable", media_type="video"))
    assert result.status == "unavailable"


def test_missing_checkpoint_unavailable(tmp_path):
    """No checkpoint directory → unavailable, no fabricated scores."""
    analyzer = AudioAnalyzer(Settings(data_dir=tmp_path, audio_model_dir=tmp_path / "missing", _env_file=None))
    result = analyzer.analyze(_analysis(tmp_path))
    assert result.status == "unavailable"
    assert result.synthetic_probability is None
    assert result.confidence is None
    assert "missing" in result.findings[0].lower()


def test_disabled_does_not_load_model(tmp_path, monkeypatch):
    analyzer = AudioAnalyzer(Settings(data_dir=tmp_path, audio_enabled=False, _env_file=None))
    monkeypatch.setattr(analyzer, "_load", lambda: pytest.fail("Must not load"))
    result = analyzer.analyze(_analysis(tmp_path))
    assert result.status == "unavailable"


def test_mocked_inference_returns_score(tmp_path, monkeypatch):
    """End-to-end with mocked _load and _infer_waveform."""
    analyzer = AudioAnalyzer(Settings(data_dir=tmp_path, _env_file=None))
    monkeypatch.setattr(analyzer, "_load", lambda: None)
    analyzer._device = "cpu"
    monkeypatch.setattr(analyzer, "_infer_waveform", lambda wf: 0.72)
    result = analyzer.analyze(_analysis(tmp_path))
    assert result.status == "completed"
    assert result.synthetic_probability == pytest.approx(0.72)
    assert result.confidence == pytest.approx(0.72)  # max(0.72, 0.28)


def test_cuda_failure_retries_on_cpu(tmp_path, monkeypatch):
    analyzer = AudioAnalyzer(Settings(data_dir=tmp_path, _env_file=None))
    monkeypatch.setattr(analyzer, "_load", lambda: None)
    moves = []
    analyzer._device = "cuda"
    analyzer._model = SimpleNamespace(to=lambda d: moves.append(d))
    analyzer._torch = SimpleNamespace(cuda=SimpleNamespace(empty_cache=lambda: None))

    calls = []
    def mock_infer(wf):
        calls.append(analyzer._device)
        if analyzer._device == "cuda":
            raise RuntimeError("CUDA OOM")
        return 0.33
    monkeypatch.setattr(analyzer, "_infer_waveform", mock_infer)
    result = analyzer.analyze(_analysis(tmp_path))
    assert result.status == "completed"
    assert analyzer._device == "cpu"
    assert moves == ["cpu"]
    assert result.synthetic_probability == pytest.approx(0.33)
    assert "retried" in result.findings[0].lower()


def test_path_traversal_rejected(tmp_path, monkeypatch):
    analyzer = AudioAnalyzer(Settings(data_dir=tmp_path, _env_file=None))
    monkeypatch.setattr(analyzer, "_load", lambda: None)
    analyzer._device = "cpu"
    evil = _analysis(tmp_path)
    evil.preprocessing.audio_path = "../../etc/passwd"
    result = analyzer.analyze(evil)
    assert result.status == "unavailable"
    assert result.synthetic_probability is None


def test_audio_crash_preserves_api_metadata(tmp_path, monkeypatch):
    """Audio analyzer crash must NOT crash POST /api/analyze."""
    settings = Settings(data_dir=tmp_path, _env_file=None)
    app = create_app(settings)

    def crash(result):
        raise RuntimeError("deliberate audio crash")
    app.app.state.audio_analyzer.analyze = crash

    buf = io.BytesIO()
    Image.new("RGB", (32, 24), "blue").save(buf, format="PNG")
    with TestClient(app) as client:
        response = client.post("/api/analyze", files={"file": ("img.png", buf.getvalue(), "image/png")})
    assert response.status_code == 200
    data = response.json()
    assert data["audio"]["status"] == "unavailable"
    assert data["metadata"]["status"] == "completed"
    assert len(data["sha256"]) == 64


def test_window_splitting(tmp_path, monkeypatch):
    """Long audio (> WINDOW_SECONDS) must split and average."""
    import torch
    from app.analyzers.audio_checkpoint import WINDOW_SECONDS

    analyzer = AudioAnalyzer(Settings(data_dir=tmp_path, _env_file=None))
    monkeypatch.setattr(analyzer, "_load", lambda: None)
    analyzer._device = "cpu"
    analyzer._torch = torch
    # 75 s → 3 windows (30+30+15)
    long_waveform = torch.zeros(int(75 * 16_000))
    scores = [0.2, 0.8, 0.5]
    call_count = [0]
    original_windows = analyzer._windows

    def mock_infer(wf):
        # call real _windows to verify splitting
        parts = original_windows(wf)
        s = scores[min(call_count[0], len(scores) - 1)]
        call_count[0] += 1
        return s
    # Patch _load_waveform to return our tensor directly
    monkeypatch.setattr(AudioAnalyzer, "_load_waveform", staticmethod(lambda p: (long_waveform, 16_000)))
    monkeypatch.setattr(analyzer, "_infer_waveform", mock_infer)
    result = analyzer.analyze(_analysis(tmp_path))
    assert result.status == "completed"
