# adapters/mavlink/helpers/message_parser.py

from typing import Dict, Any, Optional
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from pymavlink import mavutil


# ----------------------- ArduPilot Mode Tables -----------------------
# Kaynak: ArduPilot flight mode map (custom_mode değerleri)
_APM_COPTER = {
    0: "STABILIZE",
    1: "ACRO",
    2: "ALT_HOLD",
    3: "AUTO",
    4: "GUIDED",
    5: "LOITER",
    6: "RTL",
    7: "CIRCLE",
    9: "LAND",
    11: "DRIFT",
    13: "SPORT",
    14: "FLIP",
    15: "AUTOTUNE",
    16: "POSHOLD",
    17: "BRAKE",
    18: "THROW",
    19: "AVOID_ADSB",
    20: "GUIDED_NOGPS",
    21: "SMART_RTL",
    22: "FLOWHOLD",
    23: "FOLLOW",
    24: "ZIGZAG",
    25: "SYSTEMID",
    26: "AUTOROTATE",
    27: "AUTO_RTL",   # bazı firmware varyantlarında
}

_APM_PLANE = {
    0: "MANUAL",
    1: "CIRCLE",
    2: "STABILIZE",
    3: "TRAINING",
    4: "ACRO",
    5: "FBWA",
    6: "FBWB",
    7: "CRUISE",
    8: "AUTOTUNE",
    10: "AUTO",
    11: "RTL",
    12: "LOITER",
    13: "TAKEOFF",
    14: "AVOID_ADSB",
    15: "GUIDED",
    16: "INITIALIZING",
    17: "QSTABILIZE",
    18: "QHOVER",
    19: "QLOITER",
    20: "QLAND",
    21: "QRTL",
    22: "QAUTOTUNE",
    23: "QACRO",
    24: "THERMAL",
}

_APM_ROVER = {
    0: "MANUAL",
    1: "ACRO",
    2: "LEARNING",
    3: "STEERING",
    4: "HOLD",
    5: "LOITER",
    6: "FOLLOW",
    7: "SIMPLE",
    10: "AUTO",
    11: "RTL",
    15: "GUIDED",
    16: "SMART_RTL",
}


def _apm_mode_lookup(mav_type: int, custom_mode: int) -> Optional[str]:
    # MAV_TYPE’ten aracı seç
    if mav_type == mavutil.mavlink.MAV_TYPE_QUADROTOR or \
       mav_type == mavutil.mavlink.MAV_TYPE_HELICOPTER or \
       mav_type == mavutil.mavlink.MAV_TYPE_HEXAROTOR or \
       mav_type == mavutil.mavlink.MAV_TYPE_OCTOROTOR or \
       mav_type == mavutil.mavlink.MAV_TYPE_TRICOPTER:
        return _APM_COPTER.get(custom_mode)

    if mav_type == mavutil.mavlink.MAV_TYPE_FIXED_WING:
        return _APM_PLANE.get(custom_mode)

    if mav_type == mavutil.mavlink.MAV_TYPE_GROUND_ROVER or \
       mav_type == mavutil.mavlink.MAV_TYPE_SURFACE_BOAT:
        return _APM_ROVER.get(custom_mode)

    # Bilinmeyen tip: yok
    return None


class MessageParser(QObject):
    """Ham MAVLink mesajı → okunabilir dict; yalnız değişen alanlar yayılır."""
    telemetry = pyqtSignal(dict)          # örn. {'yaw':…, 'armed':…, 'mode': …}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last: Dict[str, Any] = {}
        # Mode stabilizasyonu için (base_mode, custom_mode)
        self._last_mode_key: Optional[tuple[int, int]] = None

    @pyqtSlot()
    def reset(self):
        """Bağlantı döngülerinde diff cache’i sıfırla."""
        self._last.clear()
        self._last_mode_key = None

    # ------------------------------------------------------------------
    @pyqtSlot(object)
    def parse(self, msg: mavutil.mavlink.MAVLink_message):
        d: Dict[str, Any] = {}
        t = msg.get_type()

        # ----------------- ATTITUDE -----------------
        if t == "ATTITUDE":
            yaw_deg   = msg.yaw   * 57.2958
            pitch_deg = msg.pitch * 57.2958
            roll_deg  = msg.roll  * 57.2958

            d = {
                "yaw":   (yaw_deg + 360.0) % 360.0,   # 0–360°
                "pitch": abs(pitch_deg),
                "roll":  abs(roll_deg)
            }

        # ----------------- GLOBAL POSITION -----------------
        elif t == "GLOBAL_POSITION_INT":
            d = {
                "lat": msg.lat / 1e7,
                "lon": msg.lon / 1e7,
                "alt": msg.relative_alt / 1000.0
            }

        # ----------------- HIZ & HDOP -----------------
        elif t == "VFR_HUD":
            d = {"speed": msg.groundspeed}

        elif t == "GPS_RAW_INT":
            d = {"hdop": msg.eph / 100.0}

        # ----------------- HEARTBEAT (MODE + ARMED) -----------------
        elif t == "HEARTBEAT":
            base_mode = int(getattr(msg, "base_mode", 0))
            custom_mode = int(getattr(msg, "custom_mode", 0))
            mav_type = int(getattr(msg, "type", 0))
            new_mode_key = (base_mode, custom_mode)

            # Arming bayrağı
            armed = bool(base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            if self._last.get("armed") != armed:
                d["armed"] = armed

            # 1) Önce resmi API'yi dene
            mode_name_raw = mavutil.mode_string_v10(msg) or ""
            mode_name_raw = mode_name_raw.strip().upper()

            # 2) Eğer "MODE(0X....)" gibi ham çıktı geldiyse kendi eşlememize düş
            looks_hex = mode_name_raw.startswith("MODE(")
            mapped = _apm_mode_lookup(mav_type, custom_mode) if looks_hex else None

            if looks_hex and mapped:
                mode_name = mapped
            elif looks_hex and not mapped:
                # Haritaya düşmüyorsa: son bilinen moda geri düş (ilk sefer hariç)
                mode_name = self._last.get("mode", "UNKNOWN")
            else:
                # Normal isim geldiyse onu kullan
                mode_name = mode_name_raw or "UNKNOWN"

            # İlk HEARTBEAT: ne gelirse gelsin bir kere yayınla (UI boş kalmasın)
            if self._last_mode_key is None:
                if self._last.get("mode") != mode_name:
                    d["mode"] = mode_name
                self._last_mode_key = new_mode_key
            else:
                # Sonraki kareler:
                if self._last_mode_key != new_mode_key:
                    # Gerçekten mod anahtarı değişmiş → yeni ismi yayınla (UNKNOWN değilse);
                    # eğer eşleyemiyorsak (mapped yok) son bilinen modda kal.
                    if mode_name != "UNKNOWN" and self._last.get("mode") != mode_name:
                        d["mode"] = mode_name
                    # Anahtarı, anlamlı isim üretebildiysek güncelle
                    if mode_name != "UNKNOWN":
                        self._last_mode_key = new_mode_key
                else:
                    # Anahtar değişmedi ama isim farklılaşıyorsa (nadir) güncelle
                    if mode_name != "UNKNOWN" and self._last.get("mode") != mode_name:
                        d["mode"] = mode_name

        elif t == "SYS_STATUS":
            pct = msg.battery_remaining
            v_mv = msg.voltage_battery
            a_10ma = msg.current_battery

            d = {}
            if pct is not None and pct >= 0:
                d["bat_pct"] = int(round(float(pct)))
            if v_mv is not None and v_mv > 0:
                d["bat_v"] = round(v_mv / 1000.0, 1)
            if a_10ma is not None and a_10ma > 0:
                d["bat_a"] = round(a_10ma / 100.0, 2)  # Amper

        # ----------------- Diff filtresi -----------------
        if not d:
            return

        changed = {k: v for k, v in d.items() if self._last.get(k) != v}
        if changed:
            self._last.update(changed)
            self.telemetry.emit(changed)
