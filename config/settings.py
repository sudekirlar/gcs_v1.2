# config/settings.py
from pathlib import Path
from typing  import List, Tuple
from pydantic import BaseModel, Field, ConfigDict
from pydantic_settings import BaseSettings


# ---------- Kamera kaynak modeli ----------
class CameraSource(BaseModel):
    name: str
    path: str


def _default_cam_sources() -> Tuple[CameraSource, ...]:
    # Tuple = immutable → v1 veya v2 her ikisi de 'mutable default' demez
    return (
        CameraSource(name="Laptop Kamerası", path="0"),
        CameraSource(name="Test Videosu",    path="source_videos/test2.mp4"),
    )


# ---------- Ana ayarlar ----------
class Settings(BaseSettings):
    # ----- Logging -----
    log_level: str = "INFO"
    log_path : Path = Path("logs/gcs.log")

    # ----- Serial ------
    baudrate: int = 115200

    # ----- TCP/SITL ----
    tcp_host: str = "127.0.0.1"
    tcp_port: int = 5760

    # ----- Kamera ------
    camera_sources: Tuple[CameraSource, ...] = Field(
        default_factory=_default_cam_sources
    )
    camera_resolutions: Tuple[str, ...] = (
        "640x480", "1280x720", "1920x1080"
    )

    # ----- Pydantic config -----
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )
