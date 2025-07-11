"""
Core’un bağlantı katmanını tanıdığı *yapısal* arayüz.
PymavlinkAdapter (ve ileride başka adaptörler) bu imzayı sağladığı
sürece Core değişmez.
"""
from typing import Protocol, runtime_checkable, Any

@runtime_checkable
class IConnectionPort(Protocol):
    # ---- Qt sinyalleri ----
    connected: Any          # pyqtSignal(str)
    failed: Any             # pyqtSignal(str)
    disconnected: Any       # pyqtSignal(str)
    telemetry: Any          # pyqtSignal(dict)

    # ---- metotlar ----
    def open_serial(self, port: str, baudrate: int) -> None: ...
    def open_tcp(self, host: str, tcp_port: int) -> None: ...
    def close(self) -> None: ...
