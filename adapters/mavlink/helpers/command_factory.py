# adapters/mavlink/helpers/command_factory.py

from typing import Tuple, Dict, Any
from pymavlink import mavutil

Command = Tuple[str, Dict[str, Any]]  # örn. ("ARM", {...})

# Burada Factory Pattern kullanıyoruz.
# PymavlinkAdapter içindeki worker'ın, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF gibi uzun ve ezberlemesi zor komut ID'leri
# veya hangi parametrenin (p1, p2, ... p7) hangi anlama geldiği gibi detaylarla uğraşmasını engeller.
# Worker sadece "Bana bir TAKEOFF komutu ver" der, fabrika da bunu hazırlar.

# GCSCore ne yapılacağını söyler (takeoff).
# PymavlinkAdapter kimin yapacağını yönetir (worker'a iletir).
# CommandFactory ise nasıl yapılacağını bilir (MAVLink mesajına çevirir).

class CommandFactory:
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

    # Tek noktaya gidiş.
    @staticmethod
    def goto(lat: float, lon: float, alt: float, yaw: float = 0.0) -> Command:
        return ("GOTO", {"lat": lat, "lon": lon, "alt": alt, "yaw": yaw})

    @staticmethod
    def set_servo(channel: int, pwm: int) -> Command:
        return ("SET_SERVO", {"channel": int(channel), "pwm": int(pwm)})

    # Çoğu komut 7 parametre içeren COMMAND_LONG tipi komutlar olduğu için genel bir send şablonu koyuyoruz.
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

        if name == "ARM":
            send(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)

        elif name == "DISARM":
            send(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0)

        elif name == "TAKEOFF":
            alt = float(params["alt"])
            send(mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, p7=alt)

        elif name == "LAND":
            send(mavutil.mavlink.MAV_CMD_NAV_LAND)

        # GUIDED'ı önce mode map haline çevirip göndermemiz lazım.
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

        elif name == "GOTO":
            p = params
            master.mav.mission_item_send(
                master.target_system,
                master.target_component,
                0,  # tek seferlik
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,  # 16
                2, 0,  # current = 2 (guided–wp), autocontinue = 0
                0, 0, 0, p.get("yaw", 0.0),  # hold, accept, pass, yaw
                p["lat"], p["lon"], p["alt"])  # lat, lon, alt

        elif name == "SET_SERVO":
            p = params
            send(mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
                 p1=p["channel"], p2=p["pwm"])

        else:
            raise ValueError(f"Desteklenmeyen komut: {name}")

