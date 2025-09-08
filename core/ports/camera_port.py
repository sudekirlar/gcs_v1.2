# core/ports/camera_port.py

from typing import Protocol, runtime_checkable, Any

@runtime_checkable
class ICameraPort(Protocol):
    # ---------- Qt-sinyalleri ----------
    started:  Any          # pyqtSignal()
    stopped:  Any          # pyqtSignal(str)      # kapanış nedeni
    failed:   Any          # pyqtSignal(str)      # açılış/okuma hatası
    new_frame: Any         # pyqtSignal(object)   # numpy.ndarray (BGR)

    def start(self, source_path: str, resolution_str: str) -> None: ...
    def stop(self) -> None: ...
