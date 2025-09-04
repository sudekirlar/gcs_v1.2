# adapters/mavlink/pymavlink_adapter.py
from typing import Optional
from queue import Queue, Empty

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from pymavlink import mavutil

from core.ports.logger_port import ILoggerPort
from adapters.mavlink.helpers.message_parser import MessageParser
from adapters.mavlink.helpers.command_factory import CommandFactory, Command  # ("ARM", {...})


# ====================================================================
# Thread-worker: I/O + komut kuyruğu + COMMAND_ACK dinleme
# ====================================================================
class _Worker(QObject):
    connected    = pyqtSignal(str)
    failed       = pyqtSignal(str)
    disconnected = pyqtSignal(str)
    command_ack  = pyqtSignal(str, int)   # cmd_name, result
    raw_msg      = pyqtSignal(object)

    def __init__(self, link_url: str, logger: ILoggerPort, cmd_q: Queue):
        super().__init__()
        self._url, self._logger, self._q = link_url, logger, cmd_q
        self._running = False
        self._master: Optional[mavutil.mavfile] = None

    @pyqtSlot()
    def run(self):
        # --- bağlantı ---
        try:
            self._master = mavutil.mavlink_connection(self._url)
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
                    1    # start
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

                set_interval(apm.MAVLINK_MSG_ID_ATTITUDE,            20)  # yaw/pitch/roll
                set_interval(apm.MAVLINK_MSG_ID_GLOBAL_POSITION_INT, 10)  # lat/lon/alt
                set_interval(apm.MAVLINK_MSG_ID_VFR_HUD,              5)  # speed
                set_interval(apm.MAVLINK_MSG_ID_GPS_RAW_INT,          1)  # hdop
                set_interval(apm.MAVLINK_MSG_ID_SYS_STATUS,           1)  # batarya
            except Exception as e:
                self._logger.warning(f"SET_MESSAGE_INTERVAL gönderilemedi: {e}")

            self._logger.info(f"Mavlink bağlantısı başarılı: {self._url}")
            self.connected.emit(self._url)
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

                # (Teşhis için) gelen mesaj tiplerini logla
                if msg:
                    try:
                        self._logger.debug(f"[RAW] {msg.get_type()}")
                    except Exception:
                        pass
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
                    # 0=ACCEPTED, 1=ERROR, 2=UNSUPPORTED, 3=NO_SPACE
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
    connected    = pyqtSignal(str)
    failed       = pyqtSignal(str)
    disconnected = pyqtSignal(str)
    telemetry    = pyqtSignal(dict)
    command_ack  = pyqtSignal(str, int)  # cmd_name, result

    def __init__(self, logger: ILoggerPort, parent=None):
        super().__init__(parent)
        self._logger = logger

        self._thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None
        self._cmd_q: Queue = Queue()

        # Telemetry ayrıştırıcı
        self._parser = MessageParser()
        self._parser.telemetry.connect(self.telemetry)

    # ---------- bağlantı kontrolü ----------
    def open_serial(self, port: str, baudrate: int):
        self._start_worker(f"serial:{port}:{baudrate}")

    def open_tcp(self, host: str, tcp_port: int):
        self._start_worker(f"tcp:{host}:{tcp_port}")

    def close(self):
        if self._worker:
            self._worker.stop("user request")
        if self._thread:
            self._thread.quit()
            self._thread.wait()

    # ---------- yüksek-seviye komut API ----------
    def arm(self):                 self._cmd_q.put(CommandFactory.arm())
    def disarm(self):              self._cmd_q.put(CommandFactory.disarm())
    def land(self):                self._cmd_q.put(CommandFactory.land())
    def takeoff(self, alt: float): self._cmd_q.put(CommandFactory.takeoff(alt))
    def set_mode(self, mode: str): self._cmd_q.put(CommandFactory.set_mode(mode))
    def goto(self, lat, lon, alt, yaw=0.0):
        self._cmd_q.put(CommandFactory.goto(lat, lon, alt, yaw))
    def set_servo(self, channel: int, pwm: int):
        self._cmd_q.put(CommandFactory.set_servo(channel, pwm))

    # ---------- internal ----------
    def _start_worker(self, url: str):
        self.close()  # önceki worker varsa kapat

        self._thread = QThread()
        self._worker = _Worker(url, self._logger, self._cmd_q)
        self._worker.moveToThread(self._thread)

        # köprüler
        self._worker.connected.connect(self.connected)
        self._worker.failed.connect(self.failed)
        self._worker.disconnected.connect(self.disconnected)
        self._worker.command_ack.connect(self.command_ack)
        self._worker.raw_msg.connect(self._parser.parse)

        # parser diff cache: bağlantı açılış/kapanışta temizle
        self._worker.connected.connect(lambda *_: self._parser.reset())
        self._worker.disconnected.connect(lambda *_: self._parser.reset())

        self._thread.started.connect(self._worker.run)
        self._thread.start()
