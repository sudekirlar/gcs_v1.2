# core/gcs_core.py
from __future__ import annotations
from typing import Dict, Optional, Any
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from config.settings import Settings
from core.ports.logger_port   import ILoggerPort
from core.ports.pymavlink_port import IPyMavlinkPort
from core.ports.firebase_port  import IFirebasePort
from core.assistance_request   import AssistanceRequest

_cfg = Settings()


class GCSCore(QObject):
    # ---------- Qt sinyalleri ----------
    telemetry_updated    = pyqtSignal(dict)
    connection_opened    = pyqtSignal(str)
    connection_failed    = pyqtSignal(str)
    connection_closed    = pyqtSignal(str)
    command_ack_received = pyqtSignal(str, int)

    mobile_request_added = pyqtSignal(AssistanceRequest)

    # ---------- ctor ----------
    def __init__(
        self,
        mav_adapter: IPyMavlinkPort,
        fb_adapter : IFirebasePort,
        logger     : ILoggerPort,
        parent=None
    ):
        super().__init__(parent)
        self._mav, self._fb, self._log = mav_adapter, fb_adapter, logger

        # Uçuş durumu
        self._armed = False
        self._mode  = "STABILIZE"
        self._current_alt = 0.0

        # Mobil istekler
        self._latest_mobile_req: Optional[AssistanceRequest] = None

        #  -- Kesinti iş akışı değişkenleri --
        self._awaiting_guided = False
        self._pending_req    : Optional[AssistanceRequest] = None
        self._pending_alt    = 0.0

        # MAVLink sinyalleri
        mav_adapter.connected.connect(self.connection_opened)
        mav_adapter.failed.connect(self.connection_failed)
        mav_adapter.disconnected.connect(self.connection_closed)
        mav_adapter.telemetry.connect(self._on_telemetry)
        mav_adapter.command_ack.connect(self._on_ack)

        # Firebase sinyalleri
        fb_adapter.new_request.connect(self._on_mobile_request)
        fb_adapter.error.connect(self._log.error)

    # =================================================================
    # TELEMETRY  – durum makinesi
    # =================================================================
    @pyqtSlot(dict)
    def _on_telemetry(self, d: Dict[str, Any]):
        if "alt"  in d: self._current_alt = d["alt"]

        if "mode" in d:
            new_mode = d["mode"].upper()
            if new_mode != self._mode:
                self._mode = new_mode
                self._log.info(f"[MODE] {self._mode}")

                # GUIDED teyidi bekliyorsak
                if self._awaiting_guided and self._mode == "GUIDED" \
                        and self._pending_req:
                    r = self._pending_req
                    alt = self._pending_alt
                    self._awaiting_guided = False
                    self._pending_req = None
                    self._log.info("♦ NAV_WAYPOINT gönderiliyor (mobil hedef)")
                    self._mav.goto(r.lat, r.lon, alt)

        if "armed" in d: self._armed = bool(d["armed"])
        self.telemetry_updated.emit(d)

    # =================================================================
    # MOBİL YARDIM İSTEKLERİ
    # =================================================================
    @pyqtSlot(AssistanceRequest)
    def _on_mobile_request(self, req: AssistanceRequest):
        self._log.info(f"Yeni mobil istek ► TC={req.tc} | {req.durum}")
        self._latest_mobile_req = req
        self.mobile_request_added.emit(req)

    # -----------------------------------------------------------------
    # UI → “Göreve Ara” butonu çağırır
    # -----------------------------------------------------------------
    def interrupt_mission_for_request(self, req: AssistanceRequest):
        if self._mode != "AUTO":
            self._log.warning("Görev kesilemedi: Drone AUTO modda değil")
            return

        self._pending_req = req
        self._pending_alt = max(self._current_alt, 5.0)  # güvenli irtifa
        self._awaiting_guided = True

        self._log.info("♦ Adım 1: GUIDED moda geç komutu gönderildi")
        self.set_mode("GUIDED")

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
