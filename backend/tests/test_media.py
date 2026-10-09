import hashlib
import io
import subprocess
import wave
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.services import media
from app.utils.ffmpeg import MediaToolError, run_tool


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data", visual_enabled=False, audio_enabled=False, _env_file=None)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as api:
        yield api


@pytest.fixture(scope="module")
def samples(tmp_path_factory):
    root = tmp_path_factory.mktemp("media-fixtures")

    def generate(name, arguments):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *arguments, str(root / name)], check=True, timeout=30, capture_output=True)

    # Three distinct colors prove the sampler reaches the end, not just the beginning.
    generate("silent.mp4", ["-f", "lavfi", "-i", "color=red:s=64x48:r=12:d=1", "-f", "lavfi", "-i", "color=green:s=64x48:r=12:d=1", "-f", "lavfi", "-i", "color=blue:s=64x48:r=12:d=1", "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-c:v", "mpeg4"])
    generate("sound.mp4", ["-i", str(root / "silent.mp4"), "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=3", "-c:v", "copy", "-c:a", "aac", "-shortest"])
    generate("short.mp4", ["-f", "lavfi", "-i", "color=red:s=64x48:r=1:d=1", "-frames:v", "1", "-c:v", "mpeg4"])
    generate("offset.mp4", ["-i", str(root / "silent.mp4"), "-vf", "setpts=PTS+2/TB", "-fps_mode", "passthrough", "-c:v", "mpeg4"])
    generate("sample.wav", ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=1", "-ac", "2", "-c:a", "pcm_s16le"])
    generate("sample.mp3", ["-i", str(root / "sample.wav"), "-c:a", "libmp3lame"])
    return root


def image_bytes(format="PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), "red").save(buffer, format=format)
    return buffer.getvalue()


def post(client, name, content):
    return client.post("/api/analyze", files={"file": (name, content, "application/octet-stream")})


@pytest.mark.parametrize("name,format", [("photo.JPG", "JPEG"), ("photo.jpeg", "JPEG"), ("photo.png", "PNG")])
def test_images_hash_and_isolation(client, settings, name, format):
    content = image_bytes(format)
    first = post(client, name, content)
    assert first.status_code == 200, first.text
    result = first.json()
    UUID(result["analysis_id"])
    assert result["sha256"] == hashlib.sha256(content).hexdigest()
    assert result["trust_score"] is None
    assert result["visual"]["status"] == "unavailable"
    assert result["audio"]["status"] == "not_applicable"
    assert result["metadata"]["streams"][0]["width"] == 32
    second = post(client, name, content).json()
    assert second["analysis_id"] != result["analysis_id"]
    assert second["sha256"] == result["sha256"]
    for item in (result, second):
        source = settings.data_dir / item["preprocessing"]["source_path"]
        assert source.parent.name == item["analysis_id"]
        assert source.read_bytes() == content


@pytest.mark.parametrize("name", ["silent.mp4", "sound.mp4", "short.mp4", "offset.mp4"])
def test_video_frames_and_audio(client, settings, samples, name):
    response = post(client, name, (samples / name).read_bytes())
    assert response.status_code == 200, response.text
    result = response.json()
    prep = result["preprocessing"]
    assert result["media_type"] == "video"
    assert result["metadata"]["format"]["duration"]
    assert prep["duration_seconds"] > 0
    assert len(prep["frames"]) == 12
    assert prep["frames"][-1]["sample_time_seconds"] > 0.9 * prep["duration_seconds"]
    for frame in prep["frames"]:
        path = settings.data_dir / frame["path"]
        assert path.parent.name == result["analysis_id"]
        with Image.open(path) as image:
            image.load()
    if name != "short.mp4":
        with Image.open(settings.data_dir / prep["frames"][0]["path"]) as image:
            r, g, b = image.getpixel((10, 10))
            assert r > b + 100
        with Image.open(settings.data_dir / prep["frames"][-1]["path"]) as image:
            r, g, b = image.getpixel((10, 10))
            assert b > r + 100
    if name == "sound.mp4":
        assert prep["audio_status"] == "completed"
        assert_wav(settings.data_dir / prep["audio_path"])
    else:
        assert prep["audio_status"] == "not_applicable"
        assert prep["audio_path"] is None
        assert result["audio"]["status"] == "not_applicable"


def assert_wav(path):
    with wave.open(str(path)) as audio:
        assert audio.getframerate() == 16000
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.getnframes() > 0


@pytest.mark.parametrize("name", ["sample.wav", "sample.mp3"])
def test_audio_normalization(client, settings, samples, name):
    content = (samples / name).read_bytes()
    response = post(client, name, content)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["sha256"] == hashlib.sha256(content).hexdigest()
    assert result["media_type"] == "audio"
    assert result["visual"]["status"] == "not_applicable"
    assert result["audio"]["status"] == "unavailable"
    assert result["preprocessing"]["frames"] == []
    assert_wav(settings.data_dir / result["preprocessing"]["audio_path"])


@pytest.mark.parametrize("name,content,status", [
    ("bad.txt", b"text", 415), ("empty.png", b"", 422),
    ("broken.png", b"not an image", 422), ("broken.mp4", b"not a video", 422),
    ("broken.wav", b"not audio", 422), ("broken.mp3", b"not audio", 422),
    ("wrong.jpg", image_bytes(), 422), ("disguised.mp4", image_bytes(), 422),
])
def test_invalid_uploads_cleanup(client, settings, name, content, status):
    response = post(client, name, content)
    assert response.status_code == status, response.text
    assert "error" in response.json()
    for category in ("uploads", "frames", "audio"):
        assert list((settings.data_dir / category).iterdir()) == []


def test_file_size_limit(client, settings):
    settings.max_upload_bytes = 10
    assert post(client, "large.png", image_bytes()).status_code == 413
    assert list((settings.data_dir / "uploads").iterdir()) == []


def test_duration_limit(client, settings, samples):
    settings.max_media_seconds = 0.5
    assert post(client, "long.mp4", (samples / "silent.mp4").read_bytes()).status_code == 413
    assert list((settings.data_dir / "uploads").iterdir()) == []


def test_untrusted_filename(client, settings):
    response = post(client, "../../escape.png", image_bytes())
    assert response.status_code == 200
    result = response.json()
    assert result["filename"] == "escape.png"
    source = (settings.data_dir / result["preprocessing"]["source_path"]).resolve()
    assert source.is_relative_to(settings.data_dir.resolve())
    assert source.name == "source.png"


def test_tools_unavailable(client, settings, samples):
    settings.ffprobe_path = str(settings.data_dir / "missing-ffprobe.exe")
    response = post(client, "clip.mp4", (samples / "silent.mp4").read_bytes())
    assert response.status_code == 503
    assert "unavailable" in response.json()["error"]["message"]
    assert list((settings.data_dir / "uploads").iterdir()) == []
    assert client.get("/api/health").status_code == 200


def test_video_audio_failure_is_partial(client, settings, samples, monkeypatch):
    def fail(*args):
        raise MediaToolError("Audio decode failed.")
    monkeypatch.setattr(media, "normalize_audio", fail)
    response = post(client, "clip.mp4", (samples / "sound.mp4").read_bytes())
    assert response.status_code == 200
    prep = response.json()["preprocessing"]
    assert prep["status"] == "partial"
    assert prep["audio_status"] == "unavailable"
    assert len(prep["frames"]) == 12


def test_post_cors_and_missing_file(client):
    response = client.options("/api/analyze", headers={"Origin": "http://127.0.0.1:3000", "Access-Control-Request-Method": "POST"})
    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]
    assert client.post("/api/analyze").status_code == 422


def test_subprocess_timeout_and_no_shell(monkeypatch):
    def timeout(arguments, **kwargs):
        assert kwargs["shell"] is False
        assert isinstance(arguments, list)
        raise subprocess.TimeoutExpired(arguments, kwargs["timeout"])
    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(MediaToolError) as error:
        run_tool(["ffmpeg", "-version"], 1)
    assert error.value.status_code == 504


@pytest.mark.parametrize("chunked", [False, True])
def test_request_limit_before_multipart_spooling(tmp_path, chunked):
    settings = Settings(data_dir=tmp_path, max_upload_bytes=10, _env_file=None)
    body = b"x" * (64 * 1024 + 100)
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/analyze", content=iter([body]) if chunked else body,
                               headers={"Content-Type": "multipart/form-data; boundary=sample"})
        assert response.status_code == 413, response.text
        assert response.json()["error"]["code"] == "http_413"
