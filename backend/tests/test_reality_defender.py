from copy import deepcopy
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.analyzers.reality_defender import (
    RealityDefenderAnalyzer, UPLOAD_ENDPOINT, RESULT_ENDPOINT, parse_result, validate_upload_url,
)
from app.config import Settings
from app.main import create_app
from app.reality_defender_schemas import RealityDefenderResult
from app.schemas import AnalyzerResult, VisualResult
from test_unifd import prepared

SIGNED_URL = "https://rd-test.s3.us-east-1.amazonaws.com/media.mp4?signature=private"
REQUEST_ID = "request-123"


def completed(score=85, verdict="FAKE"):
    return {"requestId": REQUEST_ID, "mediaType": "VIDEO", "overallStatus": verdict,
        "resultsSummary": {"status": verdict, "metadata": {"finalScore": score}},
        "models": [{"name": "rd-video-ensemble", "status": verdict, "finalScore": score, "predictionNumber": 0.99}]}


def setup_analyzer(tmp_path, monkeypatch, handler=None, **settings):
    item = prepared()
    (tmp_path / "test.mp4").write_bytes(b"test video")
    config = Settings(data_dir=tmp_path, reality_defender_api_key="test-secret",
        reality_defender_max_poll_attempts=3, _env_file=None, **settings)
    client_class = httpx.Client
    requests = []
    def dispatch(request):
        requests.append(request)
        if handler:
            custom = handler(request)
            if custom is not None:
                return custom
        if str(request.url) == UPLOAD_ENDPOINT:
            assert request.headers["X-API-KEY"] == "test-secret"
            return httpx.Response(200, json={"requestId": REQUEST_ID, "mediaId": "media-1", "response": {"signedUrl": SIGNED_URL}})
        if request.method == "PUT":
            assert "x-api-key" not in request.headers and "authorization" not in request.headers
            assert request.read() == b"test video"
            return httpx.Response(200)
        assert str(request.url) == RESULT_ENDPOINT + REQUEST_ID
        assert request.headers["X-API-KEY"] == "test-secret"
        return httpx.Response(200, json=completed())
    monkeypatch.setattr("app.analyzers.reality_defender.httpx.Client", lambda **kw: client_class(transport=httpx.MockTransport(dispatch), **kw))
    monkeypatch.setattr("app.analyzers.reality_defender.time.sleep", lambda seconds: None)
    return RealityDefenderAnalyzer(config), item, requests


def test_upload_poll_and_credential_isolation(tmp_path, monkeypatch):
    analyzer, item, calls = setup_analyzer(tmp_path, monkeypatch)
    result = analyzer.analyze(item)
    assert result.status == "completed" and result.verdict == "FAKE"
    assert result.manipulation_score == 85 and result.indicator_score == 15
    assert result.models[0].manipulation_score == 85  # Never use raw 0-1 prediction as normalized score.
    assert [r.method for r in calls] == ["POST", "PUT", "GET"]
    assert "test-secret" not in result.model_dump_json() and "signature" not in result.model_dump_json()


def test_reality_defender_upload_proxy_is_allowed(tmp_path, monkeypatch):
    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"requestId": REQUEST_ID,
                "response": {"signedUrl": "https://api.prd.realitydefender.xyz/upload/test?signature=private"}})
        return None
    analyzer, item, calls = setup_analyzer(tmp_path, monkeypatch, handler)
    assert analyzer.analyze(item).status == "completed"
    assert "x-api-key" not in calls[1].headers


@pytest.mark.parametrize("score,expected", [(0, 100), (100, 0), (50, 50), (85.7, 14), (None, None)])
def test_ensemble_score_scale_and_missing_score(score, expected):
    result = parse_result(completed(score), REQUEST_ID, "video")
    assert result.indicator_score == expected
    assert result.status == "completed" and result.verdict == "FAKE"


@pytest.mark.parametrize("verdict", ["NOT_APPLICABLE", "UNABLE_TO_EVALUATE", "ANALYZING", "DOWNLOADING"])
def test_non_verdict_states_never_produce_scores(verdict):
    result = parse_result(completed(99, verdict), REQUEST_ID, "video")
    assert result.manipulation_score is None and result.indicator_score is None
    assert result.models[0].manipulation_score is None


@pytest.mark.parametrize("score", [-1, 101, True, "90", float("nan"), float("inf")])
def test_invalid_scores_fail_closed(score):
    with pytest.raises(ValueError):
        parse_result(completed(score), REQUEST_ID, "video")


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(requestId="another-request"),
    lambda p: p.update(mediaType="IMAGE"),
    lambda p: p.update(resultsSummary=[]),
    lambda p: p["resultsSummary"].update(status="unexpected"),
    lambda p: p["resultsSummary"].update(metadata=[]),
    lambda p: p.update(models={}),
    lambda p: p["models"][0].update(name="https://secret-url"),
])
def test_invalid_responses(mutation):
    payload = completed()
    mutation(payload)
    with pytest.raises(ValueError):
        parse_result(payload, REQUEST_ID, "video")


@pytest.mark.parametrize("url", [
    "http://rd.s3.amazonaws.com/file", "https://127.0.0.1/file", "https://evil.example/file",
    "https://s3.amazonaws.com.evil.example/file", "https://rd.s3.amazonaws.com:444/file",
    "https://user:pass@rd.s3.amazonaws.com/file", "https://rd.s3.amazonaws.com/file#fragment",
])
def test_upload_url_rejects_unexpected_destinations(url):
    with pytest.raises(ValueError):
        validate_upload_url(url)


@pytest.mark.parametrize("code", [401, 403, 429, 413, 500, 302])
def test_http_failures_do_not_leak_or_upload(tmp_path, monkeypatch, code):
    analyzer, item, calls = setup_analyzer(tmp_path, monkeypatch, lambda r: httpx.Response(code, text="test-secret upstream private"))
    result = analyzer.analyze(item)
    assert result.status == "unavailable" and result.indicator_score is None
    assert not result.upload_attempted and len(calls) == 1
    assert "test-secret" not in result.model_dump_json() and "upstream private" not in result.model_dump_json()


def test_free_tier_restriction_explained_without_upload_or_secret_leak(tmp_path, monkeypatch):
    analyzer, item, calls = setup_analyzer(tmp_path, monkeypatch,
        lambda request: httpx.Response(403, json={"code": "free-tier-restriction", "message": "test-secret private upstream text"}))
    result = analyzer.analyze(item)
    assert result.status == "unavailable" and result.indicator_score is None
    assert "free tier" in result.message and "paid plan" in result.message
    assert "local analysis" in result.message
    assert not result.upload_attempted and len(calls) == 1
    assert "test-secret" not in result.model_dump_json() and "private upstream" not in result.model_dump_json()


def test_processing_404_then_completed(tmp_path, monkeypatch):
    count = 0
    def handler(request):
        nonlocal count
        if request.method == "GET":
            count += 1
            if count == 1:
                return httpx.Response(404)
            if count == 2:
                return httpx.Response(200, json=completed(None, "ANALYZING"))
        return None
    analyzer, item, calls = setup_analyzer(tmp_path, monkeypatch, handler)
    assert analyzer.analyze(item).status == "completed"
    assert count == 3 and len(calls) == 5


def test_poll_limit_preserves_upload_and_request_id(tmp_path, monkeypatch):
    def handler(request):
        return httpx.Response(200, json=completed(None, "ANALYZING")) if request.method == "GET" else None
    analyzer, item, calls = setup_analyzer(tmp_path, monkeypatch, handler)
    result = analyzer.analyze(item)
    assert result.status == "unavailable" and result.verdict == "ANALYZING"
    assert result.upload_attempted and result.request_id == REQUEST_ID
    assert len(calls) == 5


@pytest.mark.parametrize("scenario", ["timeout", "invalid_json", "unsafe_upload", "bad_request_id", "redirect_upload"])
def test_failure_during_protocol(tmp_path, monkeypatch, scenario):
    def handler(request):
        if scenario == "timeout":
            raise httpx.ReadTimeout("test-secret signed-url")
        if scenario == "invalid_json":
            return httpx.Response(200, text="invalid")
        if request.method == "POST" and scenario in ("unsafe_upload", "bad_request_id"):
            return httpx.Response(200, json={"requestId": "../escape" if scenario == "bad_request_id" else REQUEST_ID,
                "response": {"signedUrl": "http://127.0.0.1/file" if scenario == "unsafe_upload" else SIGNED_URL}})
        if request.method == "PUT" and scenario == "redirect_upload":
            return httpx.Response(302, headers={"Location": "https://evil.example/"})
        return None
    analyzer, item, calls = setup_analyzer(tmp_path, monkeypatch, handler)
    result = analyzer.analyze(item)
    assert result.status == "unavailable"
    assert len(calls) == (2 if scenario == "redirect_upload" else 1)
    assert "test-secret" not in result.model_dump_json() and "signed-url" not in result.model_dump_json()


@pytest.mark.parametrize("scenario", ["missing_key", "oversize_audio", "escaped_path", "missing_file"])
def test_no_network_for_ineligible_inputs(tmp_path, monkeypatch, scenario):
    analyzer, item, calls = setup_analyzer(tmp_path, monkeypatch, lambda r: pytest.fail("Must not send media"))
    if scenario == "missing_key":
        analyzer.settings = Settings(data_dir=tmp_path, _env_file=None)
    elif scenario == "oversize_audio":
        item.media_type = "audio"
        item.size_bytes = 20_000_001
    elif scenario == "escaped_path":
        item.preprocessing.source_path = "../outside.mp4"
    else:
        item.preprocessing.source_path = "missing.mp4"
    result = analyzer.analyze(item)
    assert not calls and not result.upload_attempted and result.indicator_score is None


@pytest.mark.parametrize("provider,status", [("offline", "completed"), ("reality_defender", "completed"),
    ("reality_defender", "unavailable"), ("reality_defender", "not_applicable")])
def test_api_opt_in_and_independent_local_fusion(tmp_path, monkeypatch, provider, status):
    from app.api import routes
    monkeypatch.setattr(routes, "prepare_media", lambda *args: deepcopy(prepared()))
    app = create_app(Settings(data_dir=tmp_path, _env_file=None))
    state = app.app.state
    state.reality_defender_analyzer.analyze = Mock(return_value=RealityDefenderResult(status=status,
        verdict="FAKE" if status == "completed" else "UNKNOWN", manipulation_score=90 if status == "completed" else None,
        indicator_score=10 if status == "completed" else None))
    state.bitmind_analyzer.analyze = Mock(side_effect=AssertionError("Wrong provider"))
    state.visual_analyzer.analyze = Mock(return_value=VisualResult(status="completed", synthetic_probability=0.2))
    state.audio_analyzer.analyze = Mock(return_value=AnalyzerResult(status="not_applicable"))
    with TestClient(app) as client:
        response = client.post(f"/api/analyze?detection_provider={provider}", files={"file": ("test.mp4", b"test")})
        invalid = client.post("/api/analyze?detection_provider=hive", files={"file": ("test.mp4", b"test")})
    assert response.status_code == 200 and invalid.status_code == 422
    body = response.json()
    assert body["provider_used"] == ("reality_defender" if provider == "reality_defender" and status != "unavailable" else "offline")
    assert body["trust_score"] == 80
    assert state.reality_defender_analyzer.analyze.call_count == int(provider == "reality_defender")
    assert state.visual_analyzer.analyze.call_count == 1 and state.bitmind_analyzer.analyze.call_count == 0
    assert bool(body["fallback_reason"]) == (provider == "reality_defender" and status == "unavailable")
