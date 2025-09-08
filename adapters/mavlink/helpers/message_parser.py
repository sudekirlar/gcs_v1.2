# adapters/mavlink/helpers/message_parser.py

from typing import Dict
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from pymavlink import mavutil


class MessageParser(QObject): # Ham telemetriyi alıp dict'e çevirir ve yalnızca değişen alanları yayınlar.
    telemetry = pyqtSignal(dict) # PyMavlink adapter bu sinyali (telemetry) dinler.

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last: Dict[str, float] = {} # Her bir telemetrinin son bilinen halini dict'te saklıyoruz.

    @pyqtSlot(object) # Pymavlink adapter'daki raw mesajları buraya bağlıyoruz.
    def parse(self, msg: mavutil.mavlink.MAVLink_message):
        d: Dict[str, float] = {} # O an işlenen mesajdan elde edilen verileri geçici olarak tutmak için boş bir sözlük oluşturulur.
        t = msg.get_type() # Gelen mesajın türünü str olarak alıyoruz.

        if t == "ATTITUDE":
            yaw_deg   = msg.yaw   * 57.2958 # Radyanı dereceye çevirelim. (Genel kullanım için)
            pitch_deg = msg.pitch * 57.2958
            roll_deg  = msg.roll  * 57.2958

            d = {
                "yaw":   (yaw_deg + 360) % 360,   # Yaw her zaman pozitif olsun.
                "pitch": abs(pitch_deg),          # pozitif
                "roll":  abs(roll_deg)
            }

        elif t == "GLOBAL_POSITION_INT":
            d = {
                "lat": msg.lat / 1e7,  # Tam değere ulaşmak için katsayıya bölelim.
                "lon": msg.lon / 1e7,
                "alt": msg.relative_alt / 1000.0
            }

        elif t == "VFR_HUD":
            d = {"speed": msg.groundspeed}

        elif t == "GPS_RAW_INT":
            d = {"hdop": msg.eph / 100.0}

        elif t == "HEARTBEAT":
            d = {
                "mode":  mavutil.mode_string_v10(msg), # pymavlink library'sinin sunduğu metot, mod numarasına bağlı işlem yapar.
                "armed": bool(
                    msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED # base mode birden çok durumu saklayan bit flag'tir. Base mode içi armed mı bakarız.
                )
            }

        elif t == "SYS_STATUS":
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

        if not d:
            return

        changed = {k: v for k, v in d.items() if self._last.get(k) != v} # Eğer eski değer faklıysa yaz.
        if changed:
            self._last.update(changed) # Sadece değişen verileri alıp dışarıya yollayalım.
            self.telemetry.emit(changed)

