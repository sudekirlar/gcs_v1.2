# adapters/mavlink/pymavlink_adapter.py
from typing import Optional
from queue import Queue, Empty

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from pymavlink import mavutil

from core.ports.logger_port import ILoggerPort
from adapters.mavlink.helpers.message_parser import MessageParser
from adapters.mavlink.helpers.command_factory import CommandFactory, Command

class _Worker(QObject):
    connected    = pyqtSignal(str)
    failed       = pyqtSignal(str)
    disconnected = pyqtSignal(str)
    command_ack  = pyqtSignal(str, int)
    raw_msg      = pyqtSignal(object)

    def __init__(self, link, logger: ILoggerPort, cmd_q: Queue): # Worker oluşturulurken ona bağlantı bilgileri (link), log nesnesi ve iletişim kuracağı komut kuyruğunu veriyoruz.
        super().__init__()
        self._link, self._logger, self._q = link, logger, cmd_q
        self._running = False  # Worker'ın çalışma bayrağı. stop() ile tetiklenir.
        self._master: Optional[mavutil.mavfile] = None # Ana bağlantı nesnemizi tutmak için değişken.

    # Thread başladığında burası başlar ve worker burada yaşar.
    @pyqtSlot()
    def run(self):
        # link dict'indeki bilgilere göre bir açma düzeni belirleyelim.
        try:
            kind = self._link.get("kind")
            if kind == "serial":
                device = self._normalize_serial_device(self._link["device"])
                baud   = int(self._link.get("baud", 57600))
                self._master = mavutil.mavlink_connection(device, baud=baud)
                self._logger.info(f"Serial bağlı: {device} @ {baud}")
                self.connected.emit(f"{device}@{baud}")

            elif kind == "tcp":
                host = self._link["host"]; port = int(self._link["port"])
                self._master = mavutil.mavlink_connection(f"tcp:{host}:{port}")
                self._logger.info(f"TCP bağlı: {host}:{port}")
                self.connected.emit(f"tcp:{host}:{port}")

            else:
                raise RuntimeError(f"Bilinmeyen link türü: {kind}")

        except Exception as e:
            self._logger.error(f"Bağlantı hatası: {e}")
            self.failed.emit(str(e))
            return

        self._running = True
        try:
            while self._running:
                try:
                    # Döngünün her turunda komut kuyruğunu kontrol ediyoruz ve bir komut varsa bunu command factory tarafına gönderiyoruz.
                    cmd: Command = self._q.get_nowait() # nowait() ile eğer kuyruk boşsa program beklemez.
                    try:
                        CommandFactory.to_mavlink(self._master, cmd)
                        self._logger.info(f"{cmd[0]} MAVLink'e gönderildi")
                    except Exception as e:
                        self._logger.error(f"{cmd[0]} gönderilemedi → {e}")
                except Empty:
                    pass

                # Drone'da bir mesaj var mı kontrol edelim.
                msg = self._master.recv_match(blocking=False, timeout=0.1) # blocking False ile burada takılıp kalmayız.
                if not msg:
                    continue

                # Gelen mesaj türüne göre işlem yapalım.
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

    @staticmethod
    def _normalize_serial_device(s: str) -> str: # En son alınan COM Port bağlantı başarısız çözümü için eklendi.
        import re
        s = s.strip()
        m = re.search(r'(COM\d+)', s, flags=re.IGNORECASE)
        if m:
            return m.group(1).upper()
        if s.startswith('/dev/'):
            return s
        if s.lower().startswith('serial:'):
            return s.split(':', 1)[1]
        return s

class PymavlinkAdapter(QObject):
    connected    = pyqtSignal(str)
    failed       = pyqtSignal(str)
    disconnected = pyqtSignal(str)
    telemetry    = pyqtSignal(dict)
    command_ack  = pyqtSignal(str, int)

    def __init__(self, logger: ILoggerPort, parent=None):
        super().__init__(parent)
        self._logger = logger

        self._thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None
        self._cmd_q: Queue = Queue()

        self._parser = MessageParser() # Gelen ham mesajı inceleyecek utility.
        self._parser.telemetry.connect(self.telemetry) # Buradaki telemetri verisi oraya bağlanır.

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

    # Bu komutlar sadece API sağlar. Tek iş, komutları kuyruğa koymaktır.
    def arm(self):                 self._cmd_q.put(CommandFactory.arm())
    def disarm(self):              self._cmd_q.put(CommandFactory.disarm())
    def land(self):                self._cmd_q.put(CommandFactory.land())
    def takeoff(self, alt: float): self._cmd_q.put(CommandFactory.takeoff(alt))
    def set_mode(self, mode: str): self._cmd_q.put(CommandFactory.set_mode(mode))
    def goto(self, lat, lon, alt, yaw=0.0):
        self._cmd_q.put(CommandFactory.goto(lat, lon, alt, yaw))
    def set_servo(self, channel: int, pwm: int):
        self._cmd_q.put(CommandFactory.set_servo(channel, pwm))

    def _start_worker(self, link):
        self.close() # Önce varsa eskiyi kapat.

        self._thread = QThread() # Bir QThread ve Worker nesnesi oluşturalım.
        self._worker = _Worker(link, self._logger, self._cmd_q)
        self._worker.moveToThread(self._thread) # Worker nesnesinin tüm olaylarının ve slot'larının artık _thread üzerinde çalışacağını belirtelim.

        self._worker.connected.connect(self.connected)
        self._worker.failed.connect(self.failed)
        self._worker.disconnected.connect(self.disconnected)
        self._worker.command_ack.connect(self.command_ack)
        self._worker.raw_msg.connect(self._parser.parse)

        self._thread.started.connect(self._worker.run)
        self._thread.start()

# Ana thread'den worker thread'ine komut göndermek için bir kuyruk (Queue) kullandık.
# Worker thread'inden ana thread'e bilgi (telemetri, bağlantı durumu vb.) aktarmak için ise PyQt'nun sinyal-slot mekanizmasından yararlandık.