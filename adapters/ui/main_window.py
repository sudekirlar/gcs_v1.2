# adapters/ui/main_window.py
from __future__ import annotations

from PyQt5.QtWidgets import QMainWindow, QApplication
from PyQt5.QtWebEngineWidgets import QWebEngineView

# ---------------- Controller'lar ----------------
from adapters.ui.controllers.command_controller    import CommandController
from adapters.ui.controllers.connection_controller import ConnectionController
from adapters.ui.controllers.telemetry_controller  import TelemetryController
from adapters.ui.controllers.log_controller        import LogController
from adapters.ui.controllers.map_controller        import MapController
from adapters.ui.controllers.assistance_controller import AssistanceController
from adapters.ui.controllers.camera_controller     import CameraController

from newDesign import Ui_MainWindow
from config.settings import Settings  # type hint
from adapters.firebase.firebase_adapter import FirebaseAdapter


class MainWindow(QMainWindow):
    """
    View  +  Controller wiring (GCS + Kamera + Mobil).
    """

    def __init__(
        self,
        core,                       # GCSCore
        camera_core,                # CameraCore
        camera_adapter,             # OpenCVAdapter
        logger,
        settings: Settings,
        fb_adapter: FirebaseAdapter,
        parent=None,
    ):
        super().__init__(parent)

        # ------------ Bağımlılıklar ------------
        self._core = core          # GCS iş mantığı
        self._log  = logger        # Logger (uygulama geneli)
        self._fb   = fb_adapter    # Firebase adaptörü

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

        parent_layout = placeholder.parent().layout()
        if parent_layout is not None:
            idx = parent_layout.indexOf(placeholder)
            parent_layout.insertWidget(idx, self.mapView)
        else:
            self.mapView.show()
        placeholder.deleteLater()


        self.ui.loadMission_pushButton.clicked.connect(self._deliver_aid)

        # ------------ Kamera Controller ------------
        self.cam_ctrl = CameraController(
            ui_widgets={
                "open_btn":     self.ui.openCamera_pushButton,
                "close_btn":    self.ui.closeCamera_pushButton,
                "source_combo": self.ui.videoCapture_comboBox,
                "res_combo":    self.ui.resolution_comboBox,
                "display_label": self.ui.cameraShown_label,
            },
            core=camera_core,
            settings=settings,
            parent=self,
        )

        # **Yüksek hacimli kare sinyali doğrudan UI controller'a**
        camera_adapter.new_frame.connect(self.cam_ctrl.update_display)

        # ------------ Diğer Controller'lar ------------
        self.log_ctrl = LogController(self.log_panel, self._log)
        self.conn_ctrl = ConnectionController(
            combo=self.combo,
            button=self.connect_btn,
            status_edit=self.status_edit,
            core=core,
            logger=self._log,
            close_button=self.close_btn,
            parent=self,
        )

        self.tel_ctrl = TelemetryController(self.telemetry_widgets, core, parent=self)
        self.cmd_ctrl = CommandController(self.ui, core, self._log, parent=self)

        # MapController gerçek mapView ile bağlanıyor
        self.map_ctrl = MapController(
            map_widget=self.mapView,
            core=core,
            logger=self._log,
            parent=self,
        )

        # ------------ AssistanceController (mobil) ------------
        self._assist = AssistanceController(self.ui, self._log, self.map_ctrl)
        core.mobile_request_added.connect(self._assist.on_request)

        # ------------ UI ↔ Map bağlantıları ------------
        self.ui.clearPath_pushButton.clicked.connect(self.map_ctrl.clear_path)
        self.ui.addMarker_pushButton.clicked.connect(self.map_ctrl.add_marker_here)
        self.ui.clearMarker_pushButton.clicked.connect(self.map_ctrl.clear_markers)
        self.ui.goToFocus_pushButton.clicked.connect(self.map_ctrl.recenter_and_follow)
        self.ui.saveMission_pushButton.clicked.connect(self.map_ctrl.start_demo)

    def closeEvent(self, event):  # <<<
        self._log.info("Ana pencere kapanıyor – kapanış işlemleri tetiklendi.")
        super().closeEvent(event)  # <<<

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

    # ------------ Yardım Gönder ------------
    def _deliver_aid(self):
        """
        'Görev Yükle' (Yardım Ulaştır) butonunun slot'u.
        Seçili mobil isteği alır ve core'a iletir.
        """
        req = self._assist.get_selected_request()
        if req:
            self._log.info(f"[UI] Seçilen yardım isteği: {req}")
            self._core.interrupt_mission_for_request(req)
        else:
            self._log.warning("Yardım gönderilemedi – seçim yapılmadı.")