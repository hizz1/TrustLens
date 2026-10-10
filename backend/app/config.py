from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRUSTLENS_", env_file=PROJECT_ROOT / ".env", extra="ignore"
    )

    data_dir: Path = PROJECT_ROOT / "data"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    max_upload_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    max_media_seconds: float = Field(default=600, gt=0, allow_inf_nan=False)
    subprocess_timeout_seconds: float = Field(default=120, gt=0, allow_inf_nan=False)
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    bitmind_api_key: SecretStr = SecretStr("")
    bitmind_timeout_seconds: float = Field(default=60, gt=0, le=180, allow_inf_nan=False)
    bitmind_max_upload_bytes: int = Field(default=10_000_000, gt=0, le=10_000_000)
    reality_defender_api_key: SecretStr = SecretStr("")
    reality_defender_timeout_seconds: float = Field(default=180, gt=0, le=600, allow_inf_nan=False)
    reality_defender_request_timeout_seconds: float = Field(default=30, gt=0, le=60, allow_inf_nan=False)
    reality_defender_poll_interval_seconds: float = Field(default=2, ge=0.1, le=10, allow_inf_nan=False)
    reality_defender_max_poll_attempts: int = Field(default=90, ge=1, le=300)
    visual_enabled: bool = True
    visual_model_dir: Path = PROJECT_ROOT / "models" / "visual"
    visual_device: Literal["auto", "cpu", "cuda"] = "auto"
    visual_batch_size: int = Field(default=4, ge=1, le=4)
    aide_enabled: bool = True
    aide_model_dir: Path = PROJECT_ROOT / "models" / "aide"
    aide_device: Literal["auto", "cpu", "cuda"] = "auto"
    aide_batch_size: int = Field(default=4, ge=1, le=4)
    audio_enabled: bool = True
    unifd_enabled: bool = True
    unifd_model_dir: Path = PROJECT_ROOT / "models" / "unifd"
    unifd_device: Literal["auto", "cpu", "cuda"] = "auto"
    unifd_batch_size: int = Field(default=4, ge=1, le=4)
    audio_model_dir: Path = PROJECT_ROOT / "models" / "audio"
    audio_device: Literal["auto", "cpu", "cuda"] = "auto"

    @field_validator("data_dir", "visual_model_dir", "aide_model_dir", "audio_model_dir", "unifd_model_dir", mode="after")
    @classmethod
    def resolve_data_dir(cls, value: Path) -> Path:
        return (PROJECT_ROOT / value).resolve() if not value.is_absolute() else value.resolve()

    def ensure_data_directories(self) -> None:
        for name in ("uploads", "frames", "audio"):
            (self.data_dir / name).mkdir(parents=True, exist_ok=True)
