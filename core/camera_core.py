# core/camera_core.py
"""
Kamera orkestrasyon katmanı.
UI  ──► CameraCore ──► ICameraPort (adapter)
        ▲            ▼
        │ (status)   │
        └────────────┘
"""

from typing import Optional
from PyQt5.QtCore import QObject, pyqtSignal

from core.ports.camera_port import ICameraPort
from core.ports.logger_port import ILoggerPort


class CameraCore(QObject):
    # ----- UI’nin dinleyeceği sinyaller -----
    camera_started = pyqtSignal()          # adaptör sağlıklı başladı
    camera_stopped = pyqtSignal(str)       # neden
    camera_failed  = pyqtSignal(str)       # hata açıklaması

    # ------------------------------------------------------------------
    def __init__(
        self,
        camera_adapter: ICameraPort,
        logger: ILoggerPort,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._adapter = camera_adapter
        self._log     = logger

        # Adapter sinyallerini core sinyallerine yönlendir
        camera_adapter.started.connect(self.camera_started)
        camera_adapter.stopped.connect(self.camera_stopped)
        camera_adapter.failed .connect(self.camera_failed)

    # ------------------------------------------------------------------
    #  UI → Core → Adapter
    # ------------------------------------------------------------------
    def start_camera(self, source_path: str, resolution_str: str) -> None:
        """UI tetikli: Kamerayı başlat."""
        self._log.info(f"[CamCore] Kamera açılıyor: {source_path} @ {resolution_str}")
        self._adapter.start(source_path, resolution_str)

    def stop_camera(self) -> None:
        """UI tetikli: Kamerayı durdur."""
        self._log.info("[CamCore] Kamera durduruluyor…")
        self._adapter.stop()
