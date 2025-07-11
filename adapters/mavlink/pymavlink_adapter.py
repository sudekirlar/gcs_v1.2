# adapters/mavlink/pymavlink_adapter.py

from typing import Optional
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from pymavlink import mavutil

from core.ports.logger_port import ILoggerPort
from adapters.mavlink.helpers.message_parser import MessageParser


# --------------------------- Thread Worker ----------------------------

class _Worker(QObject):
    connected    = pyqtSignal(str)   # URL
    failed       = pyqtSignal(str)   # reason
    disconnected = pyqtSignal(str)   # reason: "user request" | "link lost"
    raw_msg      = pyqtSignal(object)

    def __init__(self, link_url: str, logger: ILoggerPort):
        super().__init__()
        self._url     = link_url
        self._logger  = logger
        self._running = False
        self._master: Optional[mavutil.mavfile] = None

    @pyqtSlot()
    def run(self):
        """Thread entry point."""
        try:
            self._master = mavutil.mavlink_connection(self._url)
            self._logger.info(f"Mavlink bağlantısı başarılı: {self._url}")
            self.connected.emit(self._url)
        except Exception as e:
            self._logger.error(f"Bağlantı hatası: {e}")
            self.failed.emit(str(e))
            return

        self._running = True
        try:
            while self._running:
                msg = self._master.recv_match(blocking=True, timeout=0.5)
                if msg:
                    self.raw_msg.emit(msg)
        except Exception as e:
            self._logger.error(f"I/O hatası: {e}")
        finally:
            if self._master:
                self._master.close()
            # Yalnızca beklenmedik kesinti ise "link lost" de
            if self._running:                       # hâlâ True ⇒ kopma
                self.disconnected.emit("link lost")

    @pyqtSlot(str)
    def stop(self, reason: str = "user request"):
        """Ana thread bağlantıyı kapatmak istediğinde çağrılır."""
        self._running = False
        self.disconnected.emit(reason)              # hemen bilgilendir


# --------------------------- Adapter (main thread) --------------------

class PymavlinkAdapter(QObject):
    connected    = pyqtSignal(str)
    failed       = pyqtSignal(str)
    disconnected = pyqtSignal(str)
    telemetry    = pyqtSignal(dict)

    def __init__(self, logger: ILoggerPort, parent=None):
        super().__init__(parent)
        self._logger = logger
        self._thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None

        # Mesaj ayrıştırıcı
        self._parser = MessageParser()
        self._parser.telemetry.connect(self.telemetry)

    # ---------- API ----------
    def open_serial(self, port: str, baudrate: int):
        self._start_worker(f"serial:{port}:{baudrate}")

    def open_tcp(self, host: str, tcp_port: int):
        self._start_worker(f"tcp:{host}:{tcp_port}")

    def close(self):
        """UI 'Disconnect' dediğinde çağrılır."""
        if self._worker:
            self._worker.stop("user request")   # nedeni ilet
        if self._thread:
            self._thread.quit()
            self._thread.wait()

    # ---------- internal ----------
    def _start_worker(self, url: str):
        """Önceki bağlantı varsa kapat, yenisini başlat."""
        self.close()

        self._thread = QThread()
        self._worker = _Worker(url, self._logger)
        self._worker.moveToThread(self._thread)

        # Sinyal köprüleri
        self._worker.connected.connect(self.connected)
        self._worker.failed.connect(self.failed)
        self._worker.disconnected.connect(self.disconnected)
        self._worker.raw_msg.connect(self._parser.parse)

        self._thread.started.connect(self._worker.run)
        self._thread.start()
