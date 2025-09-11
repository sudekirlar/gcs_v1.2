import os
import winsound

class AudioNotifier:
    """
    Basit uyarı sesi çalar.
    - Sadece Windows (winsound).
    - Daima asenkron çalışır, UI'yi asla bloklamaz.
    - Sadece WAV destekler.
    """
    def __init__(self, default_sound: str = None):
        self._default = default_sound

    def play(self, wav_path: str = None):
        path = wav_path or self._default
        if not path or not os.path.exists(path):
            return
        winsound.PlaySound(
            path,
            winsound.SND_FILENAME | winsound.SND_ASYNC
        )

    def stop(self):
        # Çalan sesi durdurur (örneğin loop’ta kullanıyorsan)
        winsound.PlaySound(None, 0)
