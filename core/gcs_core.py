# core/gcs_core.py
from __future__ import annotations
from typing import Dict, Optional, Any, Tuple
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

from config.settings import Settings
from core.ports.logger_port    import ILoggerPort
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

        # -- Kesinti iş akışı değişkenleri --
        self._awaiting_guided = False
        self._pending_req    : Optional[AssistanceRequest] = None
        self._pending_alt    = 0.0

        # -- Mobil hedefe yönelim + varış --
        self._is_enroute_to_mobile_target: bool = False
        self._mobile_target_coords: Optional[Tuple[float, float]] = None  # (lat, lon)
        self._arrival_threshold_m: float = 3.0  # varış metriği
        self._wait_before_release_ms: int = 15_000  # 15 sn
        self._servo_channel: int = 9
        self._servo_pwm: int = 1750
        self._release_done: bool = False

        self._arrival_timer = QTimer(self)
        self._arrival_timer.setSingleShot(True)
        self._arrival_timer.timeout.connect(self._release_payload)

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



        if "alt" in d:
            self._current_alt = float(d["alt"])

        # --- MOD değişimi takip ---
        if "mode" in d:
            new_mode = str(d["mode"]).upper()
            if new_mode != self._mode:
                self._mode = new_mode
                self._log.info(f"[MODE] {self._mode}")

                # GUIDED teyidi bekliyorsak → GOTO at ve enroute başlat
                if self._awaiting_guided and self._mode == "GUIDED" and self._pending_req:
                    r = self._pending_req
                    alt = self._pending_alt
                    self._awaiting_guided = False
                    self._pending_req = None

                    self._log.info("♦ NAV_WAYPOINT gönderiliyor (mobil hedef)")
                    self._mav.goto(r.lat, r.lon, alt)

                    # Enroute takibi
                    self._is_enroute_to_mobile_target = True
                    self._mobile_target_coords = (r.lat, r.lon)
                    self._release_done = False
                    if self._arrival_timer.isActive():
                        self._arrival_timer.stop()

        # --- Varış kontrolü (lat/lon varsa) ---
        if self._is_enroute_to_mobile_target and ("lat" in d and "lon" in d):
            try:
                cur_lat = float(d["lat"]); cur_lon = float(d["lon"])
                tgt_lat, tgt_lon = self._mobile_target_coords or (None, None)
                if tgt_lat is not None:
                    dist_m = self._haversine_m(cur_lat, cur_lon, tgt_lat, tgt_lon)
                    if dist_m <= self._arrival_threshold_m:
                        self._is_enroute_to_mobile_target = False
                        self._log.info(f"► Hedefe varıldı (~{dist_m:.1f} m). "
                                       f"{self._wait_before_release_ms/1000:.0f} sn bekleniyor…")
                        self._arrival_timer.start(self._wait_before_release_ms)
            except Exception as e:
                self._log.error(f"Varış kontrolü hatası: {e}")

        if "armed" in d:
            self._armed = bool(d["armed"])

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
        # if self._mode != "AUTO":
        #     self._log.warning("Görev kesilemedi: Drone AUTO modda değil")
        #     return

        self._pending_req = req
        self._pending_alt = max(self._current_alt, 5.0)  # güvenli irtifa
        self._awaiting_guided = True

        # Enroute state reset
        self._is_enroute_to_mobile_target = False
        self._mobile_target_coords = (req.lat, req.lon)
        self._release_done = False
        if self._arrival_timer.isActive():
            self._arrival_timer.stop()

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

    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Metre cinsinden hızlı Haversine.
        """
        from math import radians, sin, cos, asin, sqrt
        R = 6371000.0
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        return R * c

    def _release_payload(self):
        if self._release_done:
            return
        self._release_done = True
        self._log.info(f"► 15 sn doldu. Yük bırakılıyor: SERVO {self._servo_channel} → PWM {self._servo_pwm}")
        self._mav.set_servo(self._servo_channel, self._servo_pwm)
        # İstersen kapama için küçük bir single-shot daha ekleyebilirsin (örn. 1 sn sonra 1100 µs),
        # benden istek gelmediği için tek tetik ile bıraktım.
