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

        # ----------------- Diff filtresi -----------------
        if not d:
            return

        changed = {k: v for k, v in d.items() if self._last.get(k) != v}
        if changed:
            self._last.update(changed)
            self.telemetry.emit(changed)

