# adapters/ui/controllers/camera_controller.py
"""
UI ► CameraController ◄ CameraCore
• Comboları doldurur, Aç/Kapat butonlarını yönetir
• new_frame’de QLabel’e FPS + ms overlay’li görüntü basar
• Video kaydını ayrı bir thread'de yönetir
"""

import time
from collections import deque
from typing import Dict, Union
import os
from datetime import datetime
import logging

import numpy as np
# Gerekli QThread ve pyqtSignal eklemeleri
from PyQt5.QtCore import QObject, pyqtSlot, Qt, pyqtSignal, QThread
from PyQt5.QtGui import QImage, QPixmap, QPainter, QFont, QPen, QColor

from config.settings import Settings
# Yeni oluşturduğumuz VideoRecorder sınıfı
from adapters.ui.controllers.video_recorder import VideoRecorder

log = logging.getLogger(__name__)


class CameraController(QObject):
    # Recorder worker'ına komut göndermek için thread-safe sinyaller
    start_recording_signal = pyqtSignal(str, int, int, int)
    stop_recording_signal = pyqtSignal()
    frame_to_record_signal = pyqtSignal(np.ndarray)

    """
    ui_widgets = {
        'open_btn'     : QPushButton,
        'close_btn'    : QPushButton,
        'snapshot_btn' : QPushButton,  # YENİ
        'source_combo' : QComboBox,
        'res_combo'    : QComboBox,
        'display_label': QLabel
    }
    """

    # --------------------------------------------------------------
    def __init__(
            self,
            ui_widgets: Dict[str, object],
            core,  # CameraCore
            settings: Settings,
            parent=None,
    ):
        super().__init__(parent)
        self._ui = ui_widgets
        self._core = core
        self._cfg = settings
        self._is_recording = False  # Kayıt durumunu takip eden bayrak

        self._populate_combos()
        self._setup_recorder()  # YENİ: Kayıt mekanizmasını kur

        # --- UI olayları ---
        self._ui['open_btn'].clicked.connect(self._on_open)
        self._ui['close_btn'].clicked.connect(self._core.stop_camera)
        # YENİ: Kayıt butonunun click olayını bağla
        self._ui['snapshot_btn'].clicked.connect(self._toggle_recording)

        # --- Core olayları ---
        self._core.camera_started.connect(self._on_started)
        self._core.camera_stopped.connect(self._on_stopped)
        self._core.camera_failed.connect(self._on_failed)

        # FPS & latency ölçümü
        self._ts_hist = deque(maxlen=30)
        self._last_ts = None

    def _setup_recorder(self):
        """Video kaydediciyi ve çalışacağı thread'i ayarlar."""
        self._recorder_thread = QThread(self)
        self._recorder_thread.setObjectName("VideoRecorderThread")
        self._recorder = VideoRecorder()
        self._recorder.moveToThread(self._recorder_thread)

        # Sinyalleri worker'ın slot'larına bağla
        self.start_recording_signal.connect(self._recorder.start_recording)
        self.stop_recording_signal.connect(self._recorder.stop_recording)
        # Gelen kareyi kaydetmek için sinyali bağla
        self.frame_to_record_signal.connect(self._recorder.add_frame)

        # Worker'dan gelen bilgi sinyallerini log'a yazdırabiliriz (isteğe bağlı)
        self._recorder.recording_started.connect(lambda path: log.info(f"Worker onayladı: Kayıt başladı -> {path}"))
        self._recorder.recording_stopped.connect(lambda path: log.info(f"Worker onayladı: Kayıt bitti -> {path}"))
        self._recorder.recording_error.connect(lambda err: log.error(f"Kayıt Hatası: {err}"))

        self._recorder_thread.start()

    def cleanup(self):
        """Uygulama kapanırken thread'i güvenli bir şekilde sonlandırır."""
        log.info("CameraController temizleniyor...")
        if self._is_recording:
            self._stop_recording()

        # Thread'e çıkış yapmasını söyle ve bitmesini bekle
        self._recorder_thread.quit()
        if not self._recorder_thread.wait(2000):  # 2 saniye bekle
            log.warning("Video kayıt thread'i zamanında durmadı, sonlandırılıyor.")
            self._recorder_thread.terminate()

    # ==============================================================
    #   Kayıt Yönetimi (Yeni Bölüm)
    # ==============================================================
    @pyqtSlot()
    def _toggle_recording(self):
        """Kayıt başlat/durdur butonunun ana işlevi."""
        if not self._is_recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        """Kayıt işlemini başlatmak için sinyal gönderir."""
        records_dir = "records"
        os.makedirs(records_dir, exist_ok=True)

        filename = datetime.now().strftime("%d%m%Y_%H%M%S") + ".mp4"
        full_path = os.path.join(records_dir, filename)

        res_str = self._ui['res_combo'].currentText()
        try:
            w, h = map(int, res_str.lower().replace('×', 'x').split('x'))
        except ValueError:
            log.error(f"Kayıt için geçersiz çözünürlük: {res_str}")
            return

        # FPS değişken olabilir, kayıt için sabit bir değer (örn. 30) kullanmak daha stabil sonuç verir.
        target_fps = 30

        self.start_recording_signal.emit(full_path, w, h, target_fps)
        self._is_recording = True
        log.info("Kayıt başlatma komutu gönderildi.")
        # İsteğe bağlı: Butonun görünümünü değiştir
        self._ui['snapshot_btn'].setText("Kaydı Durdur")
        self._ui['snapshot_btn'].setStyleSheet("background-color: red; color: white;")

    def _stop_recording(self):
        """Kayıt işlemini durdurmak için sinyal gönderir."""
        if not self._is_recording:
            return

        self.stop_recording_signal.emit()
        self._is_recording = False
        log.info("Kayıt durdurma komutu gönderildi.")
        # İsteğe bağlı: Butonun görünümünü eski haline getir
        self._ui['snapshot_btn'].setText("Kayıt Başlat")
        self._ui['snapshot_btn'].setStyleSheet("")

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
        res = self._ui['res_combo'].currentText()
        self._core.start_camera(path, res)

    # ==============================================================
    #   Core feedback → UI
    # ==============================================================
    @pyqtSlot()
    def _on_started(self):
        self._toggle_ui(True)

    @pyqtSlot(str)
    def _on_stopped(self, _):
        # GÜNCELLENDİ: Kamera durursa, devam eden kaydı da durdur.
        if self._is_recording:
            self._stop_recording()
        self._toggle_ui(False)

    @pyqtSlot(str)
    def _on_failed(self, _):
        # GÜNCELLENDİ: Kamera hata verirse, devam eden kaydı da durdur.
        if self._is_recording:
            self._stop_recording()
        self._toggle_ui(False)

    def _toggle_ui(self, running: bool):
        self._ui['open_btn'].setEnabled(not running)
        self._ui['close_btn'].setEnabled(running)
        self._ui['source_combo'].setEnabled(not running)
        self._ui['res_combo'].setEnabled(not running)
        # GÜNCELLENDİ: Kayıt butonu sadece kamera çalışırken aktif olmalı.
        self._ui['snapshot_btn'].setEnabled(running)

        if not running:
            lbl = self._ui['display_label']
            lbl.clear()
            lbl.setText("Kamera Kapalı")
            # Kamera kapalıyken butonun durumunu sıfırla
            if self._is_recording:
                self._stop_recording()

        self._ts_hist.clear()
        self._last_ts = None

    # ==============================================================
    #   Frame işleme & gösterme
    # ==============================================================
    @pyqtSlot(object)
    # YENİ: Python 3.9 ve altı ile uyumlu tip bildirimi
    def update_display(self, frame: Union[np.ndarray, None]):
        """
        Gelen kareyi işler. Kare 'None' ise bağlantı kopma durumunu yönetir.
        """
        if frame is None:
            if self._is_recording:
                self._stop_recording()

            lbl = self._ui['display_label']
            lbl.clear()
            lbl.setText("Sinyal Yok / Yeniden Bağlanılıyor...")
            lbl.setAlignment(Qt.AlignCenter)

            self._ts_hist.clear()
            self._last_ts = None

            return

        if self._ui['display_label'].text():
            self._ui['display_label'].clear()
            self._ui['display_label'].setAlignment(Qt.AlignLeft | Qt.AlignTop)

        if self._is_recording:
            self.frame_to_record_signal.emit(frame.copy())

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

        h, w, ch = frame.shape
        img = QImage(frame.data, w, h, ch * w, QImage.Format_RGB888).rgbSwapped()
        pix = QPixmap.fromImage(img)

        lbl_size = self._ui['display_label'].size()
        scaled = pix.scaled(
            lbl_size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        )
        x_off = (scaled.width() - lbl_size.width()) // 2
        y_off = (scaled.height() - lbl_size.height()) // 2
        cropped = scaled.copy(
            x_off, y_off, lbl_size.width(), lbl_size.height()
        )

        painter = QPainter(cropped)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setFont(QFont("Consolas", 10, QFont.Bold))
        txt = f"{fps:4.0f} fps  {ms:3.0f} ms"
        painter.setPen(QPen(QColor(0, 0, 0), 2))
        painter.drawText(6, 16, txt)
        painter.setPen(Qt.white)
        painter.drawText(5, 15, txt)
        painter.end()

        self._ui['display_label'].setPixmap(cropped)