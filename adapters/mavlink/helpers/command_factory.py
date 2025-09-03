# adapters/mavlink/helpers/command_factory.py
"""
• GOTO komutu MAV_CMD_NAV_WAYPOINT ile gönderiliyor
• SET_SERVO (MAV_CMD_DO_SET_SERVO) eklendi
"""
from typing import Tuple, Dict, Any
from pymavlink import mavutil

Command = Tuple[str, Dict[str, Any]]  # örn. ("ARM", {...})


class CommandFactory:
    # ---------- Core / UI ----------
    @staticmethod
    def arm() -> Command: return ("ARM", {})
    @staticmethod
    def disarm() -> Command: return ("DISARM", {})
    @staticmethod
    def land() -> Command: return ("LAND", {})
    @staticmethod
    def takeoff(alt: float) -> Command: return ("TAKEOFF", {"alt": alt})
    @staticmethod
    def set_mode(mode: str) -> Command: return ("SET_MODE", {"mode": mode})

    # ---------- GUIDED tek-nokta ----------
    @staticmethod
    def goto(lat: float, lon: float, alt: float, yaw: float = 0.0) -> Command:
        """
        GUIDED modda tek koordinata git.
        hold_time=0, accept_radius=0 (=WP_RADIUS), pass_radius=0, yaw=deg
        """
        return ("GOTO", {"lat": lat, "lon": lon, "alt": alt, "yaw": yaw})

    # ---------- SERVO ----------
    @staticmethod
    def set_servo(channel: int, pwm: int) -> Command:
        """
        MAV_CMD_DO_SET_SERVO
        :param channel: 1..14 (MAIN/AUX mapping autopilot konfigine bağlı)
        :param pwm: 1000..2000 µs arası
        """
        return ("SET_SERVO", {"channel": int(channel), "pwm": int(pwm)})

    # ---------- Worker ----------
    @staticmethod
    def to_mavlink(master, cmd: Command) -> None:
        name, params = cmd

        def send(cmd_id, p1=0, p2=0, p3=0, p4=0, p5=0, p6=0, p7=0):
            master.mav.command_long_send(
                master.target_system,
                master.target_component,
                cmd_id,
                0, p1, p2, p3, p4, p5, p6, p7
            )

        # ------------------ ARM / DISARM ------------------
        if name == "ARM":
            send(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)

        elif name == "DISARM":
            send(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0)

        # ------------------ TAKEOFF -----------------------
        elif name == "TAKEOFF":
            alt = float(params["alt"])
            send(mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, p7=alt)

        # ------------------ LAND --------------------------
        elif name == "LAND":
            send(mavutil.mavlink.MAV_CMD_NAV_LAND)

        # ------------------ SET_MODE ----------------------
        elif name == "SET_MODE":
            mode_str = params["mode"].upper()
            mode_map = master.mode_mapping()
            if mode_map is None:
                raise RuntimeError("Mod haritası alınamadı (HEARTBEAT yok)")

            mode_id = mode_map.get(mode_str)
            if mode_id is None:
                raise ValueError(f"Geçersiz mod: {mode_str} • {list(mode_map)}")

            master.mav.set_mode_send(
                master.target_system,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                mode_id
            )

        # ------------------ GOTO (GUIDED) -----------------
        elif name == "GOTO":
            p = params
            master.mav.mission_item_send(
                master.target_system,
                master.target_component,
                0,  # seq (tek seferlik)
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,  # 16
                2, 0,  # ★ current = 2 (guided–wp), autocontinue = 0
                0, 0, 0, p.get("yaw", 0.0),  # hold, accept, pass, yaw
                p["lat"], p["lon"], p["alt"])  # lat, lon, alt

        # ------------------ SET_SERVO ---------------------
        elif name == "SET_SERVO":
            p = params
            send(mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
                 p1=p["channel"], p2=p["pwm"])

        # ------------------ Bilinmeyen --------------------
        else:
            raise ValueError(f"Desteklenmeyen komut: {name}")

