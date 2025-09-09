# adapters/ui/main_window.py
from __future__ import annotations

from PyQt5.QtCore import pyqtSlot
from PyQt5.QtWidgets import QMainWindow, QApplication
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.uic.properties import QtGui
import time

from adapters.ui.controllers.command_controller    import CommandController
from adapters.ui.controllers.connection_controller import ConnectionController
from adapters.ui.controllers.telemetry_controller  import TelemetryController
from adapters.ui.controllers.log_controller        import LogController
from adapters.ui.controllers.map_controller        import MapController
from adapters.ui.controllers.assistance_controller import AssistanceController
from adapters.ui.controllers.camera_controller     import CameraController

from newDesign import Ui_MainWindow
from config.settings import Settings
from adapters.firebase.firebase_adapter import FirebaseAdapter
from adapters.ui.controllers.system_info_controller import SystemInfoController

# Model: GCSCore (veriyi ve iş mantığını tutan katman).
# View: Ui_MainWindow (Qt Designer ile oluşturulan, butonları vb. içeren görsel kısım).
# Controller: MainWindow ve içindeki CommandController, TelemetryController gibi yardımcı sınıflar (Model ile View arasındaki iletişimi organize eden, olayları yöneten katman).

class MainWindow(QMainWindow):

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

        self._core = core          # GCS iş mantığı
        self._log  = logger        # Logger (uygulama geneli)
        self._fb   = fb_adapter    # Firebase adaptörü

        # UI yükleyelim. (View)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.ui.exit_pushButton.clicked.connect(self.close)
        self.ui.minimize_pushButton.clicked.connect(self.showMinimized)

        # QT'de label bırakmışız, onu QWebEngineView yapıyoruz kod ile!!
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

        # GCSCore'daki mobile_request_added ile Assistance Controller içindeki on_request bağlanır.
        # Böylece Core'da yeni bir istek oluştuğunda, UI'daki controller'ın haberi olur ve listeyi günceller.
        self._assist = AssistanceController(self.ui, self._log)
        core.mobile_request_added.connect(self._assist.on_request)
        self.ui.loadMission_pushButton.clicked.connect(self._deliver_aid)

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

        # **Yüksek hacimli kare sinyali doğrudan UI controller'a** (Performans için yapıldı.)
        camera_adapter.new_frame.connect(self.cam_ctrl.update_display)

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

        # MapController gerçek mapView ile bağlanıyor.
        self.map_ctrl = MapController(
            map_widget=self.mapView,
            core=core,
            logger=self._log,
            parent=self,
        )

        # UI-Map bağlantıları.
        self.ui.clearPath_pushButton.clicked.connect(self.map_ctrl.clear_path)
        self.ui.addMarker_pushButton.clicked.connect(self.map_ctrl.add_marker_here)
        self.ui.clearMarker_pushButton.clicked.connect(self.map_ctrl.clear_markers)
        self.ui.goToFocus_pushButton.clicked.connect(self.map_ctrl.recenter_and_follow)
        self.ui.saveMission_pushButton.clicked.connect(self.map_ctrl.start_demo)

        self.sys_ctrl = SystemInfoController(
            time_label=self.ui.time_label,
            date_label=self.ui.date_label,
            weather_label=self.ui.weather_label,
            settings=settings,
            logger=self._log,
            parent=self,
        )
        self.sys_ctrl.start()

        # Akıllı Panel Hafızasını Başlat
        self._panels_state = {}

        # Olayları, Paneli Güncelleyecek Metotlara Bağla
        camera_adapter.pose_results.connect(self._on_pose_results_for_panel)
        core.mobile_request_added.connect(self._on_mobile_request_for_panel)

        # Panelleri başlangıç durumuna getir
        self._reset_panels()


    def closeEvent(self, event):  # <<<
        self._log.info("Ana pencere kapanıyor – kapanış işlemleri tetiklendi.")
        super().closeEvent(event)  # <<<

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
            "bat": self.ui.progressBar,
        }

    # ------------ Yardım Gönder ------------
    def _deliver_aid(self):
        # Görev yükleye basılınca önce controller tarafa gidip kullanıcı hangi isteği seçti sorarız.
        # Eğer bir istek seçilmişse core'u çağırırız.
        req = self._assist.get_selected_request()
        if req:
            self._log.info(f"[UI] Seçilen yardım isteği: {req}")
            self._core.interrupt_mission_for_request(req)
        else:
            self._log.warning("Yardım gönderilemedi – seçim yapılmadı.")

    def update_camera_image(self, frame):
        height, width, channel = frame.shape
        bytes_per_line = 3 * width
        qimg = QtGui.QImage(
            frame.data, width, height, bytes_per_line, QtGui.QImage.Format_RGB888
        ).rgbSwapped()
        self.ui.cameraShown_label.setPixmap(QtGui.QPixmap.fromImage(qimg))

    def _format_panel_html(self, top_icons: str, title: str, bottom_icons: str) -> str:
        """Paneller için standart bir HTML şablonu oluşturur."""
        return f"""
        <div style="text-align: center; font-family: Consolas; color: white;">
            <span style="font-size: 20px;">{top_icons}</span><br>
            <b style="font-size: 12px;">{title}</b><br>
            <span style="font-size: 15px;">{bottom_icons}</span>
        </div>
        """

    @pyqtSlot()
    def _reset_panels(self):
        """Tespit panellerini ve hafızayı başlangıç durumuna sıfırlar."""
        self._panels_state = {
            "tpose": {"announced": False, "data": None},
            "armsup": {"announced": False, "data": None},
            "mobile": {"announced": False, "data": None}
        }

        # Panellerin başlangıç metinlerini ayarla (YENİ LABEL İSİMLERİYLE)
        self.ui.bodyDetectedShown_label.setText(self._format_panel_html("⏳", "T-Pose Bekleniyor", "❔❔❔"))
        self.ui.woundDetectedShown_label.setText(self._format_panel_html("⏳", "Arms-Up Bekleniyor", "❔❔❔"))
        self.ui.fireDetectedShown_label.setText(self._format_panel_html("⏳", "Mobil İstek Bekleniyor", "❔❔❔"))

        self._log.info("Akıllı bilgi panelleri sıfırlandı.")

    @pyqtSlot(object)
    def _on_mobile_request_for_panel(self, req):
        """Yeni bir mobil istek geldiğinde ilgili paneli günceller."""
        state = self._panels_state["mobile"]
        if not state["announced"]:
            state["announced"] = True

            html_content = self._format_panel_html(
                top_icons="📱➡️🚁",
                title="MOBİL BİLDİRİM",
                bottom_icons=f"LAT: {req.lat:.3f}<br>LON: {req.lon:.3f}"
            )
            # Mobil bildirim `fireDetectedShown_label`'a gidecek (YENİ LABEL İSMİ)
            self.ui.fireDetectedShown_label.setText(html_content)
            self._log.info("Mobil bildirim paneli güncellendi.")

    @pyqtSlot(object)
    def _on_pose_results_for_panel(self, detections: list):
        """Pose sonuçlarını işler ve T-Pose/Arms-Up panellerini günceller."""
        if self._panels_state["tpose"]["announced"] and self._panels_state["armsup"]["announced"]:
            return

        for detection in detections:
            label = detection.get("label")

            if label == "T-POSE":
                state = self._panels_state["tpose"]
                if not state["announced"]:
                    state["announced"] = True

                    html_content = self._format_panel_html(
                        top_icons="📦➡️🧍",
                        title="T-POSE TESPİT EDİLDİ",
                        bottom_icons=f"ID: {detection.get('track_id', -1)} | Güven: {detection.get('conf', 0):.2f}"
                    )
                    # T-Pose `bodyDetectedShown_label`'a gidecek (YENİ LABEL İSMİ)
                    self.ui.bodyDetectedShown_label.setText(html_content)
                    self._log.info("T-Pose paneli güncellendi.")

            elif label == "ARMS-UP":
                state = self._panels_state["armsup"]
                if not state["announced"]:
                    state["announced"] = True

                    html_content = self._format_panel_html(
                        top_icons="📦➡️🙌",
                        title="ARMS-UP TESPİT EDİLDİ",
                        bottom_icons=f"ID: {detection.get('track_id', -1)} | Güven: {detection.get('conf', 0):.2f}"
                    )
                    # Arms-Up `woundDetectedShown_label`'a gidecek (YENİ LABEL İSMİ)
                    self.ui.woundDetectedShown_label.setText(html_content)
                    self._log.info("Arms-Up paneli güncellendi.")

            if self._panels_state["tpose"]["announced"] and self._panels_state["armsup"]["announced"]:
                break