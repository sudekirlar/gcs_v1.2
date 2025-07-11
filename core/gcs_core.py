# core/gcs_core.py

from PyQt5.QtCore import QObject, pyqtSignal

from core.ports.logger_port import ILoggerPort
from core.ports.pymavlink_connection_port import IConnectionPort   # ← yeni tip ipucu
from config.settings import Settings

_cfg = Settings()


class GCSCore(QObject):
    """
    • UI’den bağlantı isteği alır, ConnectionPort üzerinden aç/kapat yapar
    • Adapter (Pymavlink) sinyallerini dinleyip kendi sinyallerini yayar
    • Tüm olayları ILoggerPort üzerinden loglar
    """

    # ------------ Qt sinyalleri ------------
    telemetry_updated = pyqtSignal(dict)  # {'yaw':…, …}
    connection_opened = pyqtSignal(str)   # descr
    connection_failed = pyqtSignal(str)   # reason
    connection_closed = pyqtSignal(str)   # reason

    # ------------ ctor ------------
    def __init__(
        self,
        adapter: IConnectionPort,          # yapısal port
        logger: ILoggerPort,
        parent=None
    ):
        super().__init__(parent)
        self._adapter = adapter
        self._logger  = logger

        # Adapter sinyallerini kendi sinyallerine köprüle
        adapter.connected.connect(self.connection_opened)
        adapter.failed.connect(self.connection_failed)
        adapter.disconnected.connect(self.connection_closed)
        adapter.telemetry.connect(self.telemetry_updated)

    # ------------ UI çağrıları ------------
    def connect(self, descr: str) -> None:
        """UI, seçili port dizgesini (COM5 veya 'TCP (SITL)') iletir."""
        if descr.startswith("TCP"):
            self._logger.info("TCP bağlantı açılıyor (SITL)")
            self._adapter.open_tcp(_cfg.tcp_host, _cfg.tcp_port)
        else:
            self._logger.info(f"Serial bağlantı açılıyor: {descr}")
            self._adapter.open_serial(descr, _cfg.baudrate)

    def disconnect(self) -> None:
        """UI’den bağlantı kesme isteği geldiğinde çağrılır."""
        self._logger.info("Bağlantı kapatılıyor")
        self._adapter.close()
