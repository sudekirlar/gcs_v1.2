# adapters/ui/controllers/camera_controller.py
"""
UI ► CameraController ◄ CameraCore
• Comboları doldurur, Aç/Kapat butonlarını yönetir
• new_frame’de QLabel’e FPS + ms overlay’li görüntü basar
"""

import time
from collections import deque
from typing import Dict

import numpy as np
from PyQt5.QtCore import QObject, pyqtSlot, Qt
from PyQt5.QtGui  import QImage, QPixmap, QPainter, QFont, QPen, QColor

from config.settings import Settings


class CameraController(QObject):
    """
    ui_widgets = {
        'open_btn'     : QPushButton,
        'close_btn'    : QPushButton,
        'source_combo' : QComboBox,
        'res_combo'    : QComboBox,
        'display_label': QLabel
    }
    """
    # --------------------------------------------------------------
    def __init__(
        self,
        ui_widgets: Dict[str, object],
        core,                  # CameraCore
        settings: Settings,
        parent=None,
    ):
        super().__init__(parent)
        self._ui   = ui_widgets
        self._core = core
        self._cfg  = settings

        self._populate_combos()

        # --- UI olayları ---
        self._ui['open_btn' ].clicked.connect(self._on_open)
        self._ui['close_btn'].clicked.connect(self._core.stop_camera)

        # --- Core olayları ---
        self._core.camera_started.connect(self._on_started)
        self._core.camera_stopped.connect(self._on_stopped)
        self._core.camera_failed .connect(self._on_failed)

        # FPS & latency ölçümü
        self._ts_hist = deque(maxlen=30)   # son 30 frame aralığı
        self._last_ts = None

    # ==============================================================
    #   UI yardımcıları
    # ==============================================================
    def _populate_combos(self):
        for src in self._cfg.camera_sources:
            self._ui['source_combo'].addItem(src.name, userData=src.path)
        for res in self._cfg.camera_resolutions:
            self._ui['res_combo'].addItem(res)

    @pyqtSlot()
    def _on_open(self):
        path = self._ui['source_combo'].currentData()
        res  = self._ui['res_combo'].currentText()
        self._core.start_camera(path, res)

    # ==============================================================
    #   Core feedback → UI
    # ==============================================================
    @pyqtSlot()
    def _on_started(self): self._toggle_ui(True)
    @pyqtSlot(str)
    def _on_stopped(self, _): self._toggle_ui(False)
    @pyqtSlot(str)
    def _on_failed(self,  _): self._toggle_ui(False)

    def _toggle_ui(self, running: bool):
        self._ui['open_btn' ].setEnabled(not running)
        self._ui['close_btn'].setEnabled(running)
        self._ui['source_combo'].setEnabled(not running)
        self._ui['res_combo'   ].setEnabled(not running)
        if not running:
            lbl = self._ui['display_label']
            lbl.clear()
            lbl.setText("Kamera Kapalı")
        self._ts_hist.clear()
        self._last_ts = None

    # ==============================================================
    #   Frame işleme & gösterme
    # ==============================================================
    @pyqtSlot(object)
    def update_display(self, frame: np.ndarray):
        if frame is None:
            return

        # ----- FPS hesapla -----
        now = time.time()
        if self._last_ts is not None:
            self._ts_hist.append(now - self._last_ts)
        self._last_ts = now

        if self._ts_hist:
            avg_dt = sum(self._ts_hist) / len(self._ts_hist)
            fps = 1.0 / avg_dt
            ms = avg_dt * 1000
        else:
            fps = ms = 0.0

        # ----- QPixmap oluştur (BGR→RGB) -----
        h, w, ch = frame.shape
        img = QImage(frame.data, w, h, ch * w, QImage.Format_RGB888).rgbSwapped()
        pix = QPixmap.fromImage(img)

        # ----- QLabel alanına oran/kırp -----
        lbl_size = self._ui['display_label'].size()
        scaled = pix.scaled(
            lbl_size,
            Qt.KeepAspectRatioByExpanding,  # kenar kırp
            Qt.SmoothTransformation  # daha hafif
        )
        x_off = (scaled.width() - lbl_size.width()) // 2
        y_off = (scaled.height() - lbl_size.height()) // 2
        cropped = scaled.copy(
            x_off, y_off, lbl_size.width(), lbl_size.height()
        )

        # ----- FPS overlay KIRPILMIŞ pixmap’e çiz -----
        painter = QPainter(cropped)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setFont(QFont("Consolas", 10, QFont.Bold))

        txt = f"{fps:4.0f} fps  {ms:3.0f} ms"
        painter.setPen(QPen(QColor(0, 0, 0), 2))  # gölge
        painter.drawText(6, 16, txt)
        painter.setPen(Qt.white)
        painter.drawText(5, 15, txt)
        painter.end()

        self._ui['display_label'].setPixmap(cropped)
