# adapters/mavlink/helpers/message_parser.py

from typing import Dict
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from pymavlink import mavutil


class MessageParser(QObject):
    """Ham MAVLink mesajı → okunabilir dict; yalnız değişen alanlar yayılır."""
    telemetry = pyqtSignal(dict)          # örn. {'yaw':…, 'armed':…}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last: Dict[str, float] = {}


    @pyqtSlot()
    def reset(self):
        """Bağlantı döngülerinde diff cache’i sıfırla."""
        self._last.clear()

    # ------------------------------------------------------------------
    @pyqtSlot(object)
    def parse(self, msg: mavutil.mavlink.MAVLink_message):
        d: Dict[str, float] = {}
        t = msg.get_type()

        # ----------------- ATTITUDE -----------------
        if t == "ATTITUDE":
            yaw_deg   = msg.yaw   * 57.2958
            pitch_deg = msg.pitch * 57.2958
            roll_deg  = msg.roll  * 57.2958

            d = {
                "yaw":   (yaw_deg + 360) % 360,   # 0–360°
                "pitch": abs(pitch_deg),          # pozitif
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

        # ----------------- HEARTBEAT -----------------
        elif t == "HEARTBEAT":
            d = {
                "mode":  mavutil.mode_string_v10(msg),
                "armed": bool(
                    msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                )
            }

        elif t == "SYS_STATUS":
            # ArduPilot: mV, 10mA, %, -1 → bilinmiyor
            pct = msg.battery_remaining
            v_mv = msg.voltage_battery
            a_10ma = msg.current_battery

            d = {}
            if pct is not None and pct >= 0:
                # Gürültüyü azalt: int yüzde
                d["bat_pct"] = int(round(float(pct)))
            if v_mv is not None and v_mv > 0:
                # 0.1 V çözünürlük yeterli (UI flood'u keser)
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

