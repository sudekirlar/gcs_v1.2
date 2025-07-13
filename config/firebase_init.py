import firebase_admin
from firebase_admin import credentials

def init_firebase() -> None:
    """Projede tam 1 kez çağrılmalı."""
    if firebase_admin._apps:       # zaten çalıştıysa atla
        return

    cred = credentials.Certificate("config/firebase_key.json")
    firebase_admin.initialize_app(cred, {
        "databaseURL": "https://drone-a5683-default-rtdb.firebaseio.com/"
    })
