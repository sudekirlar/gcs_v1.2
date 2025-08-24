# adapters/ui/controllers/video_recorder.py
import cv2
import numpy as np
from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal
import logging

# Logger'ı bu modül için de ayarlayalım
log = logging.getLogger(__name__)

class VideoRecorder(QObject):
    """
    Ayrı bir QThread üzerinde çalışmak üzere tasarlanmış video kayıt işçisi.
    Gelen ham (BGR) numpy karelerini bir video dosyasına yazar.
    """
    # UI'ye bilgi vermek için sinyaller (isteğe bağlı ama iyi bir pratik)
    recording_started = pyqtSignal(str)
    recording_stopped = pyqtSignal(str)
    recording_error   = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_writer = None
        self._is_recording = False
        self._file_path = ""

    @pyqtSlot(str, int, int, int)
    def start_recording(self, file_path: str, width: int, height: int, fps: int):
        """Video dosyasını oluşturur ve yazmaya başlar."""
        if self._is_recording:
            log.warning("Zaten bir kayıt devam ediyor.")
            return

        # MP4 için 'mp4v' kodeği yaygındır.
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self._file_path = file_path
        try:
            self.video_writer = cv2.VideoWriter(self._file_path, fourcc, fps, (width, height))
            if self.video_writer.isOpened():
                self._is_recording = True
                log.info(f"Kayıt başladı: {self._file_path}")
                self.recording_started.emit(self._file_path)
            else:
                log.error(f"VideoWriter açılamadı: {self._file_path}")
                self.recording_error.emit(f"Video dosyası oluşturulamadı: {self._file_path}")

        except Exception as e:
            log.error(f"VideoWriter başlatılırken kritik hata: {e}", exc_info=True)
            self.video_writer = None
            self.recording_error.emit(str(e))

    @pyqtSlot(np.ndarray)
    def add_frame(self, frame: np.ndarray):
        """Gelen kareyi video dosyasına yazar."""
        if self._is_recording and self.video_writer is not None:
            # OpenCV'nin VideoWriter'ı BGR formatında kare bekler.
            # OpenCVAdapter'dan gelen kare zaten BGR formatında.
            self.video_writer.write(frame)

    @pyqtSlot()
    def stop_recording(self):
        """Kaydı sonlandırır ve dosyayı kapatır."""
        if not self._is_recording:
            return

        self._is_recording = False
        if self.video_writer is not None:
            self.video_writer.release()
            self.video_writer = None
            log.info(f"Kayıt durduruldu ve dosya kaydedildi: {self._file_path}")
            self.recording_stopped.emit(self._file_path)