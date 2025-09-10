# adapters/mavlink/pymavlink_adapter.py

from typing import Optional
from queue import Queue, Empty

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from pymavlink import mavutil

from core.ports.logger_port import ILoggerPort
from adapters.mavlink.helpers.message_parser import MessageParser
from adapters.mavlink.helpers.command_factory import CommandFactory, Command


# ====================================================================
# Thread-worker: I/O + komut kuyruğu + COMMAND_ACK dinleme
# ====================================================================
class _Worker(QObject):
    connected = pyqtSignal(str)
    failed = pyqtSignal(str)
    disconnected = pyqtSignal(str)
    command_ack = pyqtSignal(str, int)
    raw_msg = pyqtSignal(object)

    ### DEĞİŞİKLİK 1: __init__ metodu artık tek bir string yerine bir sözlük alıyor.
    def __init__(self, link_dict: dict, logger: ILoggerPort, cmd_q: Queue):
        super().__init__()
        self._link, self._logger, self._q = link_dict, logger, cmd_q
        self._running = False
        self._master: Optional[mavutil.mavfile] = None

    @pyqtSlot()
    def run(self):
        ### DEĞİŞİKLİK 2: Bağlantı mantığını, gelen sözlüğe göre daha açık ve hatasız hale getiriyoruz.
        try:
            kind = self._link.get("kind")

            if kind == "serial":
                device = self._link["device"]
                baud = 57600
                self._logger.info(f"mavutil.mavlink_connection çağrılıyor: device={device}, baud={baud}")
                # Pymavlink'i en sağlam yoluyla, ayrı argümanlarla çağırıyoruz
                self._master = mavutil.mavlink_connection(device, baud=baud)
                display_name = f"{device}@{baud}"

            elif kind == "tcp":
                host = self._link["host"]
                port = int(self._link["port"])
                conn_str = f"tcp:{host}:{port}"
                self._logger.info(f"mavutil.mavlink_connection çağrılıyor: conn_str={conn_str}")
                self._master = mavutil.mavlink_connection(conn_str)
                display_name = conn_str
            else:
                raise RuntimeError(f"Bilinmeyen link türü: {kind}")

            # --- MEVCUT KODUNUZ (HİÇ DOKUNULMADI) ---
            # 1) Heartbeat bekle: target_system/component dolsun
            self._master.wait_heartbeat(timeout=5)
            self._logger.info("Heartbeat alındı; stream ayarlanıyor")

            # 2) Geniş kapsamlı stream iste (eski yöntem)
            try:
                self._master.mav.request_data_stream_send(
                    self._master.target_system,
                    self._master.target_component,
                    mavutil.mavlink.MAV_DATA_STREAM_ALL,
                    10,  # Hz
                    1  # start
                )
            except Exception as e:
                self._logger.warning(f"request_data_stream gönderilemedi: {e}")

            # 3) Kritik mesajlara SET_MESSAGE_INTERVAL (yeni yöntem)
            try:
                from pymavlink.dialects.v20 import ardupilotmega as apm

                def set_interval(msg_id, hz):
                    usec = int(1_000_000 / hz) if hz > 0 else -1
                    self._master.mav.command_long_send(
                        self._master.target_system, self._master.target_component,
                        apm.MAV_CMD_SET_MESSAGE_INTERVAL,
                        0, msg_id, usec, 0, 0, 0, 0, 0
                    )

                set_interval(apm.MAVLINK_MSG_ID_ATTITUDE, 20)
                set_interval(apm.MAVLINK_MSG_ID_GLOBAL_POSITION_INT, 10)
                set_interval(apm.MAVLINK_MSG_ID_VFR_HUD, 5)
                set_interval(apm.MAVLINK_MSG_ID_GPS_RAW_INT, 1)
                set_interval(apm.MAVLINK_MSG_ID_SYS_STATUS, 1)
            except Exception as e:
                self._logger.warning(f"SET_MESSAGE_INTERVAL gönderilemedi: {e}")
            # --- MEVCUT KODUNUZUN SONU ---

            self._logger.info(f"Mavlink bağlantısı başarılı: {display_name}")
            self.connected.emit(display_name)
        except Exception as e:
            self._logger.error(f"Bağlantı hatası: {e}")
            self.failed.emit(str(e))
            return

        self._running = True
        try:
            while self._running:
                # ===== Kuyruktan komut gönder =====
                try:
                    cmd: Command = self._q.get_nowait()
                    try:
                        CommandFactory.to_mavlink(self._master, cmd)
                        self._logger.info(f"{cmd[0]} MAVLink'e gönderildi")
                    except Exception as e:
                        self._logger.error(f"{cmd[0]} gönderilemedi → {e}")
                except Empty:
                    pass

                # ===== Mesaj al =====
                msg = self._master.recv_match(blocking=False, timeout=0.1)

                if not msg:
                    continue

                if msg.get_type() == "COMMAND_ACK":
                    try:
                        cmd_enum = mavutil.mavlink.enums['MAV_CMD'][msg.command]
                        cmd_name = cmd_enum.name
                    except (KeyError, AttributeError):
                        cmd_name = f"UNKNOWN_CMD_{msg.command}"
                    self.command_ack.emit(cmd_name, msg.result)

                elif msg.get_type() == "MISSION_ACK":
                    result = msg.type
                    self.command_ack.emit("MISSION_ACK", result)

                elif msg.get_type() == "STATUSTEXT":
                    text = msg.text.strip()
                    severity = mavutil.mavlink.enums['MAV_SEVERITY'][msg.severity].name
                    self._logger.warning(f"DRONE MESAJI [{severity}]: {text}")

                else:
                    self.raw_msg.emit(msg)

        except Exception as e:
            self._running = False
            self._logger.error(f"Worker hatası: {e}")

        finally:
            if self._master:
                try:
                    self._master.close()
                except Exception:
                    pass
            if self._running:
                self.disconnected.emit("link lost")

    @pyqtSlot(str)
    def stop(self, reason: str = "user request"):
        self._running = False
        self.disconnected.emit(reason)


# ====================================================================
# Ana adapter ‒ main-thread
# ====================================================================
class PymavlinkAdapter(QObject):
    connected = pyqtSignal(str)
    failed = pyqtSignal(str)
    disconnected = pyqtSignal(str)
    telemetry = pyqtSignal(dict)
    command_ack = pyqtSignal(str, int)

    def __init__(self, logger: ILoggerPort, parent=None):
        super().__init__(parent)
        self._logger = logger
        self._thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None
        self._cmd_q: Queue = Queue()
        self._parser = MessageParser()
        self._parser.telemetry.connect(self.telemetry)

    ### DEĞİŞİKLİK 3: open_serial ve open_tcp, _start_worker'a artık string değil, sözlük gönderecek.
    def open_serial(self, port: str, baudrate: int):
        self._start_worker({"kind": "serial", "device": port, "baud": baudrate})

    def open_tcp(self, host: str, tcp_port: int):
        self._start_worker({"kind": "tcp", "host": host, "port": tcp_port})

    def close(self):
        if self._worker:
            self._worker.stop("user request")
        if self._thread:
            self._thread.quit()
            self._thread.wait()

    # ---------- yüksek-seviye komut API (Değişiklik yok)----------
    def arm(self):
        self._cmd_q.put(CommandFactory.arm())

    def disarm(self):
        self._cmd_q.put(CommandFactory.disarm())

    def land(self):
        self._cmd_q.put(CommandFactory.land())

    def takeoff(self, alt: float):
        self._cmd_q.put(CommandFactory.takeoff(alt))

    def set_mode(self, mode: str):
        self._cmd_q.put(CommandFactory.set_mode(mode))

    def goto(self, lat, lon, alt, yaw=0.0):
        self._cmd_q.put(CommandFactory.goto(lat, lon, alt, yaw))

    def set_servo(self, channel: int, pwm: int):
        self._cmd_q.put(CommandFactory.set_servo(channel, pwm))

    ### DEĞİŞİKLİK 4: _start_worker metodu artık bir sözlük alacak ve worker'a bunu verecek.
    def _start_worker(self, link_dict: dict):
        self.close()

        self._thread = QThread()
        self._worker = _Worker(link_dict, self._logger, self._cmd_q)
        self._worker.moveToThread(self._thread)

        self._worker.connected.connect(self.connected)
        self._worker.failed.connect(self.failed)
        self._worker.disconnected.connect(self.disconnected)
        self._worker.command_ack.connect(self.command_ack)
        self._worker.raw_msg.connect(self._parser.parse)

        self._worker.connected.connect(lambda *_: self._parser.reset())
        self._worker.disconnected.connect(lambda *_: self._parser.reset())

        self._thread.started.connect(self._worker.run)
        self._thread.start()