# adapters/ui/main_window.py

from PyQt5.QtWidgets import QMainWindow

from adapters.ui.controllers.command_controller import CommandController
from newDesign import Ui_MainWindow          # Qt Designer çıktısı

# Controller importları
from adapters.ui.controllers.connection_controller import ConnectionController
from adapters.ui.controllers.telemetry_controller  import TelemetryController
from adapters.ui.controllers.log_controller        import LogController
from adapters.ui.request_listener_worker import RequestListenerWorker   # üstteki import
from PyQt5.QtGui import QTextCursor
from datetime import datetime, timezone




class MainWindow(QMainWindow):
    """
    • Salt view öğelerini kurar
    • Controller’ları OLDUĞU anda oluşturur ve kendisine (parent) bağlar
      -> GC tarafından toplanmaz; sinyaller daima çalışır
    """
    def __init__(self, core, logger, parent=None):
        super().__init__(parent)

        # ------------ UI yükle ------------
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.ui.exit_pushButton.clicked.connect(self.close)
        self.ui.minimize_pushButton.clicked.connect(self.showMinimized)

        # ------------ Controller'lar ------------
        # 1. Log paneli
        self.log_ctrl = LogController(
            self.log_panel, logger)                  # parent parametresi yok

        # 2. Bağlantı ve durum
        self.conn_ctrl = ConnectionController(
            combo       = self.combo,
            button      = self.connect_btn,
            status_edit = self.status_edit,
            core        = core,
            logger      = logger,
            close_button=self.close_btn,
            parent      = self)                      # parent veriyoruz

        # 3. Telemetri gösterimi
        self.tel_ctrl = TelemetryController(
            self.telemetry_widgets, core, parent=self)

        self.cmd_ctrl = CommandController(self.ui, core, logger, parent=self)


        self._request_listener = RequestListenerWorker(self)
        self._request_listener.newReq.connect(self._display_mobile_msg)  # ← slot ekleyin
        self._request_listener.start()

    # ------------ Widget kısayolları ------------
    @property
    def combo(self):
        return self.ui.comPortTelemetry_comboBox

    @property
    def connect_btn(self):
        return self.ui.openTelemetry_pushButton

    @property
    def close_btn(self):
        return self.ui.closeTelemetry_pushButton

    @property
    def status_edit(self):
        return self.ui.currentState_textEdit_2

    @property
    def log_panel(self):
        return self.ui.criticalShown_textEdit

    @property
    def telemetry_widgets(self):
        return {
            "yaw":   self.ui.yaw_textEdit,
            "pitch": self.ui.pitch_textEdit,
            "roll":  self.ui.roll_textEdit,
            "lat":   self.ui.latitude_textEdit_2,
            "lon":   self.ui.longitude_textEdit,
            "alt":   self.ui.altitude_textEdit,
            "spd":   self.ui.speed_textEdit,
            "hdop":  self.ui.hdop_textEdit,
            "mode":  self.ui.currentMode_textEdit,
        }

    def _display_mobile_msg(self, req):  # req: AssistanceRequest
        now = datetime.now(timezone.utc).strftime("%H:%M:%S")
        line = (f"[{now}]  Durum:{req.durum}  "
                f"TC:{req.tc}  "
                f"Konum:{req.lat:.5f}, {req.lon:.5f}")
        self.ui.mobileBox_textEdit.append(line)
        self.ui.mobileBox_textEdit.moveCursor(QTextCursor.End)  # en alta kaydır
