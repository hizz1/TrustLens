import io
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.analyzers.unifd import UniFDAnalyzer, LIMITATIONS, MODEL_ID
from app.config import Settings
from app.main import create_app
from app.schemas import AnalysisResponse, AnalyzerResult, MetadataResult, PreprocessingResult, SampledFrame, VisualResult


def prepared():
    return AnalysisResponse(analysis_id="d971f896-ce57-4f40-93d6-f186df81f16c", filename="test.mp4",
        media_type="video", sha256="0"*64, size_bytes=10, visual=VisualResult(status="unavailable"),
        audio=AnalyzerResult(status="not_applicable"), metadata=MetadataResult(),
        preprocessing=PreprocessingResult(source_path="test.mp4", frames=[
            SampledFrame(index=i, sample_time_seconds=float(i), path=f"frame_{i}.png") for i in range(12)]))


def test_missing_disabled_and_nonvideo(tmp_path, monkeypatch):
    analyzer = UniFDAnalyzer(Settings(data_dir=tmp_path, unifd_model_dir=tmp_path / "missing", _env_file=None))
    result = analyzer.analyze(prepared())
    assert result.status == "unavailable" and result.synthetic_probability is None
    analyzer.settings.unifd_enabled = False
    monkeypatch.setattr(analyzer, "_load", lambda: pytest.fail("must not load"))
    assert analyzer.analyze(prepared()).status == "unavailable"
    item = prepared()
    item.media_type = "audio"
    assert analyzer.analyze(item).status == "not_applicable"


def test_aggregation_and_cuda_retry(tmp_path, monkeypatch):
    analyzer = UniFDAnalyzer(Settings(data_dir=tmp_path, _env_file=None))
    monkeypatch.setattr(analyzer, "_load", lambda: None)
    analyzer._device = "cuda"
    moves = []
    analyzer._model = analyzer._head = SimpleNamespace(to=lambda device: moves.append(device))
    analyzer._torch = SimpleNamespace(cuda=SimpleNamespace(empty_cache=lambda: None))
    def predict(paths):
        if analyzer._device == "cuda":
            raise RuntimeError("OOM")
        return [i/12 for i in range(12)]
    monkeypatch.setattr(analyzer, "_predict", predict)
    result = analyzer.analyze(prepared())
    assert result.status == "completed" and result.device == "cpu"
    assert result.synthetic_probability == pytest.approx(5.5/12)
    assert [f.index for f in result.suspicious_frames] == [11, 10, 9, 8, 7]
    assert moves == ["cpu", "cpu"]


@pytest.mark.parametrize("values", [[float("nan")]*12, [0.5], [1.1]*12])
def test_invalid_scores(tmp_path, monkeypatch, values):
    analyzer = UniFDAnalyzer(Settings(data_dir=tmp_path, _env_file=None))
    monkeypatch.setattr(analyzer, "_load", lambda: None)
    monkeypatch.setattr(analyzer, "_predict", lambda paths: values)
    result = analyzer.analyze(prepared())
    assert result.status == "unavailable" and result.synthetic_probability is None


@pytest.mark.parametrize("mode,media,expected", [(None,"video","deepfake"), ("ai_generated","video","ai_generated"), ("ai_generated","image","deepfake")])
def test_api_routing(tmp_path, monkeypatch, mode, media, expected):
    from app.api import routes
    item = prepared()
    item.media_type = media
    monkeypatch.setattr(routes, "prepare_media", lambda *args: item)
    app = create_app(Settings(data_dir=tmp_path, _env_file=None))
    calls = []
    def analyze(name):
        def run(item):
            calls.append(name)
            return VisualResult(status="completed", synthetic_probability=0.3, limitations=LIMITATIONS, model_id=MODEL_ID)
        return run
    app.app.state.visual_analyzer.analyze = analyze("deepfake")
    app.app.state.unifd_analyzer.analyze = analyze("ai_generated")
    app.app.state.audio_analyzer.analyze = lambda item: AnalyzerResult(status="not_applicable")
    with TestClient(app) as client:
        response = client.post("/api/analyze" + (f"?detection_mode={mode}" if mode else ""), files={"file": ("test.mp4", io.BytesIO(b"test"))})
    assert response.status_code == 200
    assert calls == [expected]
    assert response.json()["detection_mode"] == expected
    assert LIMITATIONS[0] in response.json()["limitations"]


def test_api_unifd_crash_and_invalid_mode(tmp_path, monkeypatch):
    from app.api import routes
    monkeypatch.setattr(routes, "prepare_media", lambda *args: prepared())
    app = create_app(Settings(data_dir=tmp_path, audio_enabled=False, _env_file=None))
    def crash(item):
        raise RuntimeError("test")
    app.app.state.unifd_analyzer.analyze = crash
    with TestClient(app) as client:
        response = client.post("/api/analyze?detection_mode=ai_generated", files={"file": ("test.mp4", b"test")})
        invalid = client.post("/api/analyze?detection_mode=invalid", files={"file": ("test.mp4", b"test")})
    assert response.status_code == 200
    assert response.json()["visual"]["synthetic_probability"] is None
    assert response.json()["trust_score"] is None
    assert invalid.status_code == 422 and "error" in invalid.json()


def test_sigmoid_unnormalized_features_and_center_crop(tmp_path):
    torch = pytest.importorskip("torch")
    from transformers import CLIPImageProcessor
    from PIL import Image
    analyzer = UniFDAnalyzer(Settings(data_dir=tmp_path, _env_file=None))
    analyzer._torch = torch
    analyzer._processor = CLIPImageProcessor(do_resize=False)
    seen = []
    def backbone(pixel_values):
        assert torch.is_inference_mode_enabled()
        assert pixel_values.shape[1:] == (3, 224, 224)
        seen.append(pixel_values.shape[0])
        # A red central crop remains red; resizing would introduce blue borders.
        assert pixel_values[0, 0].mean().item() == pytest.approx((1-0.48145466)/0.26862954, abs=1e-5)
        return SimpleNamespace(image_embeds=torch.full((pixel_values.shape[0], 768), 2.0))
    analyzer._model = backbone
    analyzer._head = torch.nn.Linear(768, 1)
    with torch.no_grad():
        analyzer._head.weight.fill_(1/768)
        analyzer._head.bias.zero_()
    image = Image.new("RGB", (448, 224), "blue")
    image.paste("red", (112, 0, 336, 224))
    path = tmp_path / "frame.png"
    image.save(path)
    values = analyzer._predict([path]*5)
    assert values == pytest.approx([torch.sigmoid(torch.tensor(2.)).item()]*5)
    assert seen == [4, 1]
