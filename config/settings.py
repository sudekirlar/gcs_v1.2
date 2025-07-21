# config/settings.py
# config/settings.py
from __future__ import annotations
from pathlib import Path
from typing import Tuple

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------- Alt modeller ----------
class CameraSource(BaseModel):
    name: str
    path: str


def _default_cam_sources() -> Tuple[CameraSource, ...]:
    return (
        CameraSource(name="Laptop Kamerası", path="0"),
        CameraSource(name="Test Videosu",    path="source_videos/test2.mp4"),
        CameraSource(name="SIYI A8 (RTSP)", path="rtsp://192.168.144.25:8554/live"), #genel olarak buymuş ama güncellenecek.
    )


# ---------- Ana ayarlar ----------
class Settings(BaseSettings):
    # ----- Logging -----
    log_level: str = "INFO"
    log_path : Path = Path("logs/gcs.log")

    # ----- Serial -----
    baudrate: int = 115200

    # ----- TCP/SITL -----
    tcp_host: str = "127.0.0.1"
    tcp_port: int = 5760

    # ----- Firebase -----
    firebase_credentials_json_path: Path  # .env ⇒ FIREBASE_CREDENTIALS_JSON_PATH
    firebase_db_url: str                  # .env ⇒ FIREBASE_DB_URL
    firebase_db_path: str = "/mobil"      # .env ⇒ FIREBASE_DB_PATH

    # ----- Kamera -----
    camera_sources: Tuple[CameraSource, ...] = Field(
        default_factory=_default_cam_sources
    )
    camera_resolutions: Tuple[str, ...] = (
        "640x480", "1280x720", "1920x1080"
    )

    # ----- Pydantic -----
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # env_prefix=""  # istersen tüm env’lere ortak prefix ekleyebilirsin
        extra="forbid"   # bilinmeyen env değişkenlerini reddetmeye devam eder
    )
