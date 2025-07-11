# config/settings.py

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict  # <-- yeni import

class Settings(BaseSettings):
    # ----- Logging -----
    log_level: str = "INFO"
    log_path:  Path = Path("logs/gcs.log")

    # ----- Serial -----
    baudrate: int = 115200

    # ----- TCP/SITL -----
    tcp_host: str = "127.0.0.1"
    tcp_port: int = 5760

    # Pydantic v2 config
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )
