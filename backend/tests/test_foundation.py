from fastapi.testclient import TestClient

from app.config import PROJECT_ROOT, Settings
from app.main import create_app


def test_startup_health_and_directories(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path, _env_file=None))) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "trustlens-api", "version": "0.1.0"}
        assert all((tmp_path / name).is_dir() for name in ("uploads", "frames", "audio"))


def test_local_cors_and_rejected_origin(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path, _env_file=None))) as client:
        for origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
            response = client.get("/api/health", headers={"Origin": origin})
            assert response.headers["access-control-allow-origin"] == origin
        response = client.get("/api/health", headers={"Origin": "https://example.com"})
        assert "access-control-allow-origin" not in response.headers


def test_structured_errors(tmp_path):
    application = create_app(Settings(data_dir=tmp_path, _env_file=None))

    @application.app.get("/test-error")
    def fail():
        raise RuntimeError("private diagnostic")

    @application.app.get("/test-validation")
    def validate(count: int):
        return count

    with TestClient(application, raise_server_exceptions=False) as client:
        assert client.get("/missing").json()["error"]["code"] == "http_404"
        response = client.get("/test-validation?count=wrong")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
        response = client.get("/test-error", headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert "private diagnostic" not in response.text
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_relative_data_path_is_project_relative():
    assert Settings(data_dir="data", _env_file=None).data_dir == PROJECT_ROOT / "data"
