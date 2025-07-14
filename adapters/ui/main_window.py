# adapters/ui/main_window.py
from PyQt5.QtWidgets           import QMainWindow
from PyQt5.QtWebEngineWidgets  import QWebEngineView

from adapters.ui.controllers.command_controller     import CommandController
from adapters.ui.controllers.connection_controller  import ConnectionController
from adapters.ui.controllers.telemetry_controller   import TelemetryController
from adapters.ui.controllers.log_controller         import LogController
from adapters.ui.controllers.map_controller         import MapController
from adapters.ui.controllers.assistance_controller  import AssistanceController
from newDesign import Ui_MainWindow                 # pyuic5 çıktısı


class MainWindow(QMainWindow):
    """
    View + Controller wiring.
    """
    def __init__(self, core, logger, parent=None):
        super().__init__(parent)

        # ------------ UI yükle ------------
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.ui.exit_pushButton.clicked.connect(self.close)
        self.ui.minimize_pushButton.clicked.connect(self.showMinimized)

        # ------------ mapShown_label → QWebEngineView ------------
        placeholder = self.ui.mapShown_label
        self.mapView = QWebEngineView(self.ui.centralwidget)
        self.mapView.setObjectName("mapView")
        self.mapView.setSizePolicy(placeholder.sizePolicy())
        self.mapView.setGeometry(placeholder.geometry())

        # ---- AssistanceController: artık self.ui veriyoruz (1 değişiklik) ----
        self._assist = AssistanceController(self.ui, logger)           # ← düzeltildi
        core.mobile_request_added.connect(self._assist.on_request)

        # placeholder'ı layout’ta değiştir
        parent_layout = placeholder.parent().layout()
        if parent_layout is not None:
            idx = parent_layout.indexOf(placeholder)
            parent_layout.insertWidget(idx, self.mapView)
        else:
            self.mapView.show()
        placeholder.deleteLater()

        # ------------ Diğer Controller'lar ------------
        self.log_ctrl = LogController(self.log_panel, logger)
        self.conn_ctrl = ConnectionController(
            combo        = self.combo,
            button       = self.connect_btn,
            status_edit  = self.status_edit,
            core         = core,
            logger       = logger,
            close_button = self.close_btn,
            parent       = self)

        self.tel_ctrl = TelemetryController(self.telemetry_widgets, core, parent=self)
        self.cmd_ctrl = CommandController(self.ui, core, logger, parent=self)

        # MapController gerçek mapView ile bağlanıyor
        self.map_ctrl = MapController(
            map_widget = self.mapView,
            core       = core,
            logger     = logger,
            parent     = self)

        # ---- UI ↔ Map bağlantıları ----
        self.ui.clearPath_pushButton.clicked.connect(self.map_ctrl.clear_path)
        self.ui.addMarker_pushButton.clicked.connect(self.map_ctrl.add_marker_here)
        self.ui.clearMarker_pushButton.clicked.connect(self.map_ctrl.clear_markers)
        self.ui.goToFocus_pushButton.clicked.connect(self.map_ctrl.recenter_and_follow)
        self.ui.saveMission_pushButton.clicked.connect(self.map_ctrl.start_demo)

    # ------------ Widget kısayolları ------------
    @property
    def combo(self):       return self.ui.comPortTelemetry_comboBox
    @property
    def connect_btn(self): return self.ui.openTelemetry_pushButton
    @property
    def close_btn(self):   return self.ui.closeTelemetry_pushButton
    @property
    def status_edit(self): return self.ui.currentState_textEdit_2
    @property
    def log_panel(self):   return self.ui.criticalShown_textEdit

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
