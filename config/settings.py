# config/settings.py
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------- Alt modeller ----------
class CameraSource(BaseModel):
    name: str
    path: str

def _default_cam_sources() -> Tuple[CameraSource, ...]:
    """
    Windows için GStreamer pipeline’ları:
      1) Laptop Kamerası (ksvideosrc)
      2) Test Videosu (uridecodebin)
      3) SIYI A8 (UDP/RTP H.264) → NVDEC (nvh264dec) tercihli
    """
    # 1) Laptop Kamera
    laptop_pipeline = (
        "ksvideosrc device-index=0 ! "
        "video/x-raw,width=1280,height=720,framerate=30/1 ! "
        "videoconvert ! video/x-raw,format=BGR ! "
        "appsink drop=true max-buffers=1 sync=false"
    )

    # 2) Test Videosu
   #
    # 3) SIYI A8 – UDP/RTP (Kısa Yol ile Optimize Edilmiş)
    # siyi_udp_pipeline = (
    #     "udpsrc port=5000 caps=\"application/x-rtp, encoding-name=H264, payload=96\" ! "
    #     "rtph264depay ! h264parse ! d3d12h264device1dec ! "
    #     # d3d12convert kaldırıldı eğer gerekirse videodaki gibi ekle.
    #     "d3d12download ! "
    #     "videoconvert ! video/x-raw,format=BGR ! "
    #     "appsink drop=true max-buffers=1 sync=false"
    # )
    siyi_udp_pipeline = (
        "udpsrc port=5000 caps=\"application/x-rtp, encoding-name=H264, payload=96\" ! "
        "rtph264depay ! h264parse ! decodebin ! "  # decodebin'e işi bırakıyoruz
        "videoconvert ! video/x-raw,format=BGR ! "
        "appsink drop=true max-buffers=1 sync=false"
    )

    return (
        CameraSource(name="Laptop Kamerası", path=laptop_pipeline),
        #CameraSource(name="Test Videosu",    path=video_pipeline),
        CameraSource(name="SIYI A8 (UDP)",   path=siyi_udp_pipeline),
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

    # ----- Sistem Bilgileri / Hava Durumu -----
    weather_enabled: bool = True
    weather_timeout_sec: int = 3

    # Güvenlik tercihleri
    use_device_location: bool = True  # OS/driver üzerinden konum (tercih edilen)
    use_ip_location: bool = False  # IP lookup’u tamamen kapatır (güvenli varsayılan)

    # ENV fallback (opsiyonel sabit konum)
    default_lat: Optional[float] = None
    default_lon: Optional[float] = None
    default_city: Optional[str] = None

