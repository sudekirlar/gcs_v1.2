# core/gcs_core.py
from typing import Dict, Any

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from config.settings import Settings
from core.ports.logger_port import ILoggerPort
from core.ports.pymavlink_port import IPyMavlinkPort
from core.ports.firebase_port import IFirebasePort         # ★ yeni
from core.assistance_request import AssistanceRequest      # ★ yeni

_cfg = Settings()


class GCSCore(QObject):
    # ----- Qt sinyalleri -----
    telemetry_updated    = pyqtSignal(dict)
    connection_opened    = pyqtSignal(str)
    connection_failed    = pyqtSignal(str)
    connection_closed    = pyqtSignal(str)
    command_ack_received = pyqtSignal(str, int)            # cmd_name, result

    mobile_request_added = pyqtSignal(AssistanceRequest)   # ★ yeni

    # -----------------------------------------------------------------
    # ctor
    # -----------------------------------------------------------------
    def __init__(
        self,
        mav_adapter: IPyMavlinkPort,
        fb_adapter:  IFirebasePort,                # ★ yeni
        logger:      ILoggerPort,
        parent=None
    ):
        super().__init__(parent)

        self._mav = mav_adapter
        self._fb  = fb_adapter                      # ★
        self._log = logger

        self._armed: bool = False
        self._mode:  str  = "STABILIZE"

        # ----- MAVLink port sinyalleri -----
        mav_adapter.connected.connect(self.connection_opened)
        mav_adapter.failed.connect(self.connection_failed)
        mav_adapter.disconnected.connect(self.connection_closed)
        mav_adapter.telemetry.connect(self._on_telemetry)
        mav_adapter.command_ack.connect(self._on_ack)

        # ----- Firebase port sinyalleri -----
        fb_adapter.new_request.connect(self._on_mobile_request)    # ★
        fb_adapter.error.connect(self._log.error)                  # ★

    # =================================================================
    # TELEMETRY
    # =================================================================
    @pyqtSlot(dict)
    def _on_telemetry(self, data: Dict[str, Any]):
        if "mode" in data:
            self._mode = data["mode"].upper()
        if "armed" in data:
            self._armed = bool(data["armed"])
        self.telemetry_updated.emit(data)

    # =================================================================
    # MOBİL YARDIM İSTEKLERİ
    # =================================================================
    @pyqtSlot(AssistanceRequest)
    def _on_mobile_request(self, req: AssistanceRequest):
        """
        Firebase'den gelen yeni yardım çağrısı.
        UI katmanı mobile_request_added sinyaline abone olur.
        """
        self._log.info(f"Yeni mobil istek ► TC={req.tc} | {req.durum}")
        self.mobile_request_added.emit(req)

    # =================================================================
    # KULLANICI KOMUTLARI
    # =================================================================
    def arm(self):
        if self._armed:
            self._reject("ARM", "Zaten armed")
            return
        self._log.info("ARM gönderiliyor…")
        self._mav.arm()

    def disarm(self):
        if not self._armed:
            self._reject("DISARM", "Zaten disarmed")
            return
        self._log.info("DISARM gönderiliyor…")
        self._mav.disarm()

    def takeoff(self, altitude_m: float):
        if not self._armed:
            self._reject("TAKEOFF", "Önce ARM")
            return
        if self._mode != "GUIDED":
            self._reject("TAKEOFF", "Mod GUIDED olmalı")
            return
        self._log.info(f"TAKEOFF({altitude_m} m) gönderiliyor…")
        self._mav.takeoff(altitude_m)

    def land(self):
        self._log.info("LAND gönderiliyor…")
        self._mav.land()

    def set_mode(self, mode: str):
        self._log.info(f"SET_MODE({mode})…")
        self._mav.set_mode(mode)

    # =================================================================
    # ACK – sadece log + UI
    # =================================================================
    @pyqtSlot(str, int)
    def _on_ack(self, cmd_name: str, result: int):
        self._log.info(f"ACK alındı ► {cmd_name} | result={result}")
        self.command_ack_received.emit(cmd_name, result)

    # =================================================================
    # PORT BAĞLANTI
    # =================================================================
    def connect(self, descr: str):
        if descr.startswith("TCP"):
            self._log.info("TCP bağlantı açılıyor (SITL)")
            self._mav.open_tcp(_cfg.tcp_host, _cfg.tcp_port)
        else:
            self._log.info(f"Serial bağlantı açılıyor: {descr}")
            self._mav.open_serial(descr, _cfg.baudrate)

    def disconnect(self):
        self._log.info("Bağlantı kapatılıyor")
        self._mav.close()

    # =================================================================
    # Yardımcı
    # =================================================================
    def _reject(self, cmd: str, reason: str):
        self._log.warning(f"{cmd} reddedildi: {reason}")
        self.command_ack_received.emit(cmd, -1)
