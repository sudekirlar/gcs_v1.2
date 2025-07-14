import firebase_admin
from firebase_admin import credentials
from pathlib import Path

from config.settings import Settings

def init_firebase() -> None:
    """
    Uygulama boyunca bir kez çağrılır.
    .env’te belirtilen anahtar yolu ve DB URL’siyle Firebase Admin başlatır.
    """
    if firebase_admin._apps:
        return  # zaten başlatıldı

    cfg = Settings()

    cred_path = Path(cfg.firebase_credentials_json_path)
    if not cred_path.is_file():
        raise FileNotFoundError(f"Firebase anahtar dosyası bulunamadı -> {cred_path}")

    cred = credentials.Certificate(str(cred_path))
    firebase_admin.initialize_app(
        cred,
        {"databaseURL": cfg.firebase_db_url}
    )
