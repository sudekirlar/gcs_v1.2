# core/camera_core.py
from typing import Optional
from PyQt5.QtCore import QObject, pyqtSignal

from core.ports.camera_port import ICameraPort
from core.ports.logger_port import ILoggerPort

class CameraCore(QObject):
    camera_started = pyqtSignal()
    camera_stopped = pyqtSignal(str)
    camera_failed  = pyqtSignal(str)
    # NEW: Pose sonuçlarını Core üzerinden de yayınlayalım (Controller buradan dinleyecek)
    camera_pose_results = pyqtSignal(object)  # List[PoseDetectionDTO]

    def __init__(
        self,
        camera_adapter: ICameraPort,
        logger: ILoggerPort,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._adapter = camera_adapter
        self._log     = logger

        camera_adapter.started.connect(self.camera_started)
        camera_adapter.stopped.connect(self.camera_stopped)
        camera_adapter.failed .connect(self.camera_failed)

        # NEW: Pose sinyali
        try:
            camera_adapter.pose_results.connect(self.camera_pose_results)
        except Exception:
            # Eski adapter’lar için savunmacı
            pass

    def start_camera(self, source_path: str, resolution_str: str) -> None:
        self._log.info(f"[CamCore] Kamera açılıyor: {source_path} @ {resolution_str}")
        self._adapter.start(source_path, resolution_str)

    def stop_camera(self) -> None:
        self._log.info("[CamCore] Kamera durduruluyor…")
        self._adapter.stop()
