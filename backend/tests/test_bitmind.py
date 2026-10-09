import io
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.analyzers.bitmind import BitMindAnalyzer, BitMindUnavailable, ENDPOINT
from app.config import Settings
from app.main import create_app
from app.schemas import AnalyzerResult, VisualResult
from test_unifd import prepared


def setup_analyzer(tmp_path, monkeypatch, handler):
    settings = Settings(data_dir=tmp_path, bitmind_api_key="test-secret", _env_file=None)
    item = prepared()
    (tmp_path / "test.mp4").write_bytes(b"test video")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("app.analyzers.bitmind.httpx.Client", lambda **kwargs: client)
    return BitMindAnalyzer(settings), item


@pytest.mark.parametrize("is_ai,confidence", [(True, 0.9), (False, 0.23)])
def test_api_response_and_multipart(tmp_path, monkeypatch, is_ai, confidence):
    def handler(request):
        assert str(request.url) == ENDPOINT
        assert request.headers["Authorization"] == "Bearer test-secret"
        body = request.read()
        assert b'name="file"' in body and b"test video" in body
        return httpx.Response(200, json={"mediaType": "video", "result": {"isAI": is_ai, "confidence": confidence}})
    analyzer, item = setup_analyzer(tmp_path, monkeypatch, handler)
    result = analyzer.analyze(item)
    assert result.is_ai == is_ai and result.confidence == confidence
    assert result.synthetic_probability is None
    assert result.frame_scores == [] and result.suspicious_frames == []


@pytest.mark.parametrize("code", [401, 403, 429, 500, 413, 302])
def test_http_errors_do_not_leak_response(tmp_path, monkeypatch, code):
    analyzer, item = setup_analyzer(tmp_path, monkeypatch, lambda request: httpx.Response(code, text="test-secret private upstream text"))
    with pytest.raises(BitMindUnavailable) as exc:
        analyzer.analyze(item)
    assert "test-secret" not in str(exc.value) and "private" not in str(exc.value)


@pytest.mark.parametrize("payload", [{}, {"mediaType": "image", "result": {"isAI": True,"confidence": 0.9}},
    {"mediaType": "video", "result": {"isAI": "false", "confidence": 0.9}},
    {"mediaType": "video", "result": {"isAI": False, "confidence": 1.9}}])
def test_invalid_responses(tmp_path, monkeypatch, payload):
    analyzer, item = setup_analyzer(tmp_path, monkeypatch, lambda request: httpx.Response(200, json=payload))
    with pytest.raises(BitMindUnavailable, match="invalid"):
        analyzer.analyze(item)


def test_timeout(tmp_path, monkeypatch):
    def timeout(request):
        raise httpx.ReadTimeout("test-secret")
    analyzer, item = setup_analyzer(tmp_path, monkeypatch, timeout)
    with pytest.raises(BitMindUnavailable, match="timed out"):
        analyzer.analyze(item)


@pytest.mark.parametrize("scenario", ["audio", "oversize", "missing_key", "escaped_path"])
def test_no_upload_for_ineligible_inputs(tmp_path, monkeypatch, scenario):
    settings = Settings(data_dir=tmp_path, bitmind_api_key="test-secret", _env_file=None)
    item = prepared()
    if scenario == "audio":
        item.media_type = "audio"
    elif scenario == "oversize":
        item.size_bytes = 10_000_001
    elif scenario == "missing_key":
        settings = Settings(data_dir=tmp_path, _env_file=None)
    else:
        item.preprocessing.source_path = "../outside.mp4"
    monkeypatch.setattr("app.analyzers.bitmind.httpx.Client", lambda **kwargs: pytest.fail("Network must not be used"))
    with pytest.raises(BitMindUnavailable):
        BitMindAnalyzer(settings).analyze(item)


@pytest.mark.parametrize("provider,failed,expected", [("offline", False, "offline"), ("bitmind", False, "bitmind"), ("bitmind", True, "offline")])
def test_provider_routing_and_fallback(tmp_path, monkeypatch, provider, failed, expected):
    from app.api import routes
    monkeypatch.setattr(routes, "prepare_media", lambda *args: prepared())
    app = create_app(Settings(data_dir=tmp_path, _env_file=None))
    state = app.app.state
    state.unifd_analyzer.analyze = Mock(return_value=VisualResult(status="completed", synthetic_probability=0.2))
    state.visual_analyzer.analyze = Mock(side_effect=AssertionError("wrong fallback"))
    state.bitmind_analyzer.analyze = Mock(side_effect=BitMindUnavailable("BitMind request timed out.") if failed else None,
        return_value=VisualResult(status="completed", is_ai=True, confidence=0.8, model_id="BitMind API"))
    state.audio_analyzer.analyze = Mock(return_value=AnalyzerResult(status="not_applicable"))
    with TestClient(app) as client:
        response = client.post(f"/api/analyze?detection_provider={provider}&detection_mode=ai_generated", files={"file": ("test.mp4", b"test")})
    assert response.status_code == 200
    body = response.json()
    assert body["provider_used"] == expected
    assert state.bitmind_analyzer.analyze.call_count == (1 if provider == "bitmind" else 0)
    assert state.unifd_analyzer.analyze.call_count == (1 if expected == "offline" else 0)
    assert bool(body["fallback_reason"]) == (provider == "bitmind" and failed)
    if expected == "bitmind":
        assert body["trust_score"] is None and body["visual"]["is_ai"] is True


def test_default_stays_local_and_invalid_provider_rejected(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, visual_enabled=False, _env_file=None))
    app.app.state.bitmind_analyzer.analyze = Mock(side_effect=AssertionError("Must not send media without explicit API selection"))
    buffer = io.BytesIO()
    Image.new("RGB", (32,32)).save(buffer, format="PNG")
    with TestClient(app) as client:
        response = client.post("/api/analyze", files={"file": ("image.png", buffer.getvalue())})
        invalid = client.post("/api/analyze?detection_provider=wrong", files={"file": ("image.png", buffer.getvalue())})
    assert response.json()["provider_used"] == "offline"
    assert app.app.state.bitmind_analyzer.analyze.call_count == 0
    assert invalid.status_code == 422
