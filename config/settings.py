from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # ------------- Genel -------------
    log_level: str = "INFO"
    log_path: Path = Path("logs/gcs.log")

    # ------------- MAVLink (varsa) -------------
    baudrate: int = 115200
    tcp_host: str = "127.0.0.1"
    tcp_port: int = 5760

    # ------------- Firebase -------------
    firebase_db_url: str
    firebase_credentials_json_path: str
    firebase_db_path: str = "/mobil"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )
