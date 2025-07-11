# core/gcs_core.py
from typing import Dict, Any
from PyQt5.QtCore import QObject, pyqtSignal

from core.ports.logger_port import ILoggerPort
from core.ports.pymavlink_port import IPyMavlinkPort
from config.settings import Settings

_cfg = Settings()


class GCSCore(QObject):
    # ----- Qt sinyalleri -----
    telemetry_updated    = pyqtSignal(dict)
    connection_opened    = pyqtSignal(str)
    connection_failed    = pyqtSignal(str)
    connection_closed    = pyqtSignal(str)
    command_ack_received = pyqtSignal(str, int)   # cmd_name, result

    # ----- ctor -----
    def __init__(self, adapter: IPyMavlinkPort, logger: ILoggerPort, parent=None):
        super().__init__(parent)
        self._adapter, self._logger = adapter, logger

        self._armed: bool = False
        self._mode:  str  = "STABILIZE"

        # Port sinyalleri
        adapter.connected.connect(self.connection_opened)
        adapter.failed.connect(self.connection_failed)
        adapter.disconnected.connect(self.connection_closed)
        adapter.telemetry.connect(self._on_telemetry)
        adapter.command_ack.connect(self._on_ack)

    # =================================================================
    # TELEMETRY
    # =================================================================
    def _on_telemetry(self, data: Dict[str, Any]):
        if "mode" in data:
            self._mode = data["mode"].upper()
        self.telemetry_updated.emit(data)

    # =================================================================
    # KULLANICI KOMUTLARI (UI bu metotları çağırır)
    # =================================================================
    def arm(self):
        if self._armed:
            self._reject("ARM", "Zaten armed"); return
        self._logger.info("ARM gönderiliyor…")
        self._adapter.arm()

    def disarm(self):
        if not self._armed:
            self._reject("DISARM", "Zaten disarmed"); return
        self._logger.info("DISARM gönderiliyor…")
        self._adapter.disarm()

    def takeoff(self, altitude_m: float):
        if not self._armed:
            self._reject("TAKEOFF", "Önce ARM"); return
        if self._mode != "GUIDED":
            self._reject("TAKEOFF", "Mod GUIDED olmalı"); return
        self._logger.info(f"TAKEOFF({altitude_m} m) gönderiliyor…")
        self._adapter.takeoff(altitude_m)

    def land(self):        self._logger.info("LAND gönderiliyor…");  self._adapter.land()
    def set_mode(self, m): self._logger.info(f"SET_MODE({m})…");     self._adapter.set_mode(m)

    # =================================================================
    # ACK DÖNÜŞÜ  (gelen komut adı uzun olabilir)
    # =================================================================
    def _on_ack(self, cmd_name: str, result: int):
        self._logger.info(f"ACK alındı ► {cmd_name} | result={result}")

        if result == 0:  # sadece başarıda güncelle
            up = cmd_name.upper()

            if "ARM_DISARM" in up:
                # result=0 ve param1=1 gönderdiğimizi biliyoruz → arm
                if self._armed is False:
                    self._armed = True
                    self._logger.info("Durum güncellendi: ARMED")

            elif "SET_MODE" in up:
                # Telemetry zaten mod değişimini getirir; ek işlem yok
                pass

        self.command_ack_received.emit(cmd_name, result)

    # =================================================================
    # PORT BAĞLANTI METOTLARI
    # =================================================================
    def connect(self, descr: str):
        if descr.startswith("TCP"):
            self._logger.info("TCP bağlantı açılıyor (SITL)")
            self._adapter.open_tcp(_cfg.tcp_host, _cfg.tcp_port)
        else:
            self._logger.info(f"Serial bağlantı açılıyor: {descr}")
            self._adapter.open_serial(descr, _cfg.baudrate)

    def disconnect(self):
        self._logger.info("Bağlantı kapatılıyor")
        self._adapter.close()

    # =================================================================
    # Yardımcı
    # =================================================================
    def _reject(self, cmd: str, reason: str):
        self._logger.warning(f"{cmd} reddedildi: {reason}")
        self.command_ack_received.emit(cmd, -1)
