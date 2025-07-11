# adapters/mavlink/helpers/command_factory.py

from typing import Tuple, Dict, Any
from pymavlink import mavutil

Command = Tuple[str, Dict[str, Any]]      # ("ARM", {...})


class CommandFactory:
    # ---------- Core / UI ----------
    @staticmethod
    def arm()      -> Command: return ("ARM", {})
    @staticmethod
    def disarm()   -> Command: return ("DISARM", {})
    @staticmethod
    def land()     -> Command: return ("LAND", {})
    @staticmethod
    def takeoff(alt: float) -> Command: return ("TAKEOFF", {"alt": alt})
    @staticmethod
    def set_mode(mode: str)  -> Command: return ("SET_MODE", {"mode": mode})

    # ---------- Worker ----------
    @staticmethod
    def to_mavlink(master, cmd: Command) -> None:
        name, params = cmd

        # Ortak yardımcı – tüm parametreleri sıfırla
        def send(cmd_id, p1=0, p2=0, p3=0, p4=0, p5=0, p6=0, p7=0):
            master.mav.command_long_send(
                master.target_system,
                master.target_component,
                cmd_id,
                0,           # confirmation
                p1, p2, p3, p4, p5, p6, p7
            )

        # ------------------- ARM / DISARM -------------------
        if name == "ARM":
            send(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)

        elif name == "DISARM":
            send(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0)

        # ------------------- TAKEOFF -----------------------
        elif name == "TAKEOFF":
            alt = float(params["alt"])
            send(mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, p7=alt)

        # ------------------- LAND --------------------------
        elif name == "LAND":
            send(mavutil.mavlink.MAV_CMD_NAV_LAND)

        # ------------------- SET_MODE ----------------------
        elif name == "SET_MODE":
            mode_str = params["mode"].upper()

            mode_map = master.mode_mapping()       # heartbeat sonrası dolar
            if mode_map is None:
                raise RuntimeError("Mod haritası alınamadı (HEARTBEAT yok)")

            mode_id = mode_map.get(mode_str)
            if mode_id is None:
                raise ValueError(f"Geçersiz mod: {mode_str} • {list(mode_map)}")

            # cmd 11 ‒ SET_MODE   (bazı firmware’lerde cmd 176 DENIED döner)
            master.mav.set_mode_send(
                master.target_system,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                mode_id
            )

        # ------------------- Bilinmeyen --------------------
        else:
            raise ValueError(f"Desteklenmeyen komut: {name}")
