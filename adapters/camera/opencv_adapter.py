# adapters/camera/opencv_adapter.py
"""
Process-tabanlı OpenCV adaptörü (CUDA opsiyonlu).
– GPU varsa: kare GPU’ye upload, (isteğe bağlı resize) → host belleğe geri
– Renk dönüşümü UI’de tek .rgbSwapped() ile yapılacak
"""

from __future__ import annotations
import cv2, time, logging, multiprocessing, queue as pyqueue
from typing import Optional, Tuple
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from core.ports.logger_port import ILoggerPort


def _cuda_available() -> bool:
    try:
        return cv2.cuda.getCudaEnabledDeviceCount() > 0
    except Exception:
        return False


class _CameraReaderProcess(multiprocessing.Process):
    def __init__(
        self, source: str, resolution_wh: Tuple[int, int],
        frame_q: multiprocessing.Queue, stop_event: multiprocessing.Event,
        use_cuda: bool, log_level: str = "INFO",
    ):
        super().__init__(name="CameraReader")
        self._src, (self._w, self._h) = source, resolution_wh
        self._q, self._stop, self._cuda = frame_q, stop_event, use_cuda
        self._log_level = log_level

    def run(self):
        logging.basicConfig(
            level=getattr(logging, self._log_level, logging.INFO),
            format="CamProc | %(levelname)s | %(message)s",
        )
        log = logging.getLogger("cam.reader")
        log.info(f"CUDA {'ON' if self._cuda else 'OFF'}")

        # Kaynak aç
        cap = cv2.VideoCapture(int(self._src)) if str(self._src).isdigit() else cv2.VideoCapture(self._src)
        if not cap.isOpened():
            log.error(f"Kamera açılamadı: {self._src}")
            return

        # Hedef çözünürlüğü iste
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self._w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._h)

        gpu_mat = None
        if self._cuda:
            try:
                gpu_mat = cv2.cuda_GpuMat()
            except Exception:
                log.warning("CUDA GpuMat oluşturulamadı, CPU moduna düşülüyor.")
                self._cuda = False

        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    time.sleep(0.01)
                    continue

                if self._cuda and gpu_mat is not None:
                    try:
                        gpu_mat.upload(frame)
                        # Gerekirse burada CUDA resize/blur vb. uygulanabilir
                        frame = gpu_mat.download()  # BGR
                    except Exception:
                        # GPU’da sorun olursa CPU’ya düş
                        self._cuda = False

                # QLabel’e uygun boyut
                if (frame.shape[1] != self._w) or (frame.shape[0] != self._h):
                    try:
                        frame = cv2.resize(frame, (self._w, self._h))
                    except Exception:
                        pass

                # Kuyruğa son kareyi koy, doluysa en eskisini at
                if self._q.full():
                    try:
                        self._q.get_nowait()
                    except Exception:
                        pass
                try:
                    self._q.put_nowait(frame)
                except Exception:
                    pass

                # Çok agresif olmayan sıkılık
                time.sleep(0.001)
        finally:
            try:
                cap.release()
            except Exception:
                pass
            log.info("Kamera süreci kapandı.")


class OpenCVAdapter(QObject):
    started = pyqtSignal()
    stopped = pyqtSignal(str)
    failed  = pyqtSignal(str)
    new_frame = pyqtSignal(object)   # numpy.ndarray (BGR)

    def __init__(self, logger: ILoggerPort, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._log: ILoggerPort = logger
        self._proc: Optional[multiprocessing.Process] = None
        self._q: Optional[multiprocessing.Queue] = None
        self._stop_evt: Optional[multiprocessing.Event] = None

        # Ana döngüde kuyruğu poll eden timer
        self._poll = QTimer(self)
        self._poll.setInterval(16)  # ~60 Hz
        self._poll.timeout.connect(self._poll_q)

        self._cuda = _cuda_available()
        if self._cuda:
            try:
                self._log.info("[Cam] CUDA destekli OpenCV tespit edildi.")
            except Exception:
                pass

        self._wait_tmr: Optional[QTimer] = None
        self._wait_elapsed = 0  # ms

    def start(self, src: str, res: str):
        # Önce varsa kapat
        if self._proc and self._proc.is_alive():
            self.stop()

        # Çözünürlüğü ayrıştır
        try:
            w, h = map(int, res.lower().replace('×', 'x').split('x'))
        except Exception:
            self._log.error(f"Geçersiz çözünürlük: {res}")
            self.failed.emit("Çözünürlük")
            return

        # Child process için kaynaklar
        self._q = multiprocessing.Queue(maxsize=2)
        self._stop_evt = multiprocessing.Event()

        # Logger level elde edilemiyorsa INFO’ya düş
        log_level = "INFO"
        try:
            # ILoggerPort genelde .level veya benzeri taşımaz; sabit bırakıyoruz.
            pass
        except Exception:
            pass

        # Süreci başlat
        self._proc = _CameraReaderProcess(
            src, (w, h), self._q, self._stop_evt, self._cuda, log_level=log_level
        )
        self._proc.daemon = True  # uygulama kapanırken arkada kalmasın
        try:
            self._proc.start()
        except Exception as e:
            self._log.error(f"Kamera süreci başlatılamadı: {e}")
            self.failed.emit("Process")
            return

        self._poll.start()
        self.started.emit()
        self._log.info("Kamera adaptörü başlatıldı.")

    def stop(self):
        """Kamerayı durdur – UI’yı bloklama."""
        if not self._proc:
            return

        # 1) Sürece “dur” sinyali
        try:
            if self._stop_evt:
                self._stop_evt.set()
        except Exception:
            pass

        # 2) join yerine arka planda bekle
        if self._wait_tmr is None:
            self._wait_tmr = QTimer(self)
            self._wait_tmr.setInterval(100)
            self._wait_tmr.setSingleShot(False)
            self._wait_tmr.timeout.connect(self._check_proc_end)

        self._wait_elapsed = 0
        self._wait_tmr.start()

        # UI serbest
        self._poll.stop()
        self._log.info("Kamera sürecinin kapanması bekleniyor…")

    # ---------------- internal helper ----------------
    def _check_proc_end(self):
        """100 ms’de bir çağrılır; süreç ölmezse 2 sn sonra terminate."""
        if not self._proc:
            if self._wait_tmr:
                self._wait_tmr.stop()
            return

        if not self._proc.is_alive():
            self._finalize_stop("normal exit")
            return

        self._wait_elapsed += 100
        if self._wait_elapsed >= 2000:  # 2 sn geçti
            self._log.warning("Kamera süreci zorla sonlandırılıyor.")
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._finalize_stop("forced")

    def _finalize_stop(self, reason: str):
        if self._wait_tmr:
            self._wait_tmr.stop()
        try:
            if self._proc:
                self._proc.join(timeout=0)
        except Exception:
            pass

        self._proc = None
        self._q = None
        self._stop_evt = None
        self.stopped.emit(reason)
        self._log.info(f"Kamera adaptörü durdu: {reason}")

    def _poll_q(self):
        if not self._q:
            return

        # Süreç çöktüyse ve sırada kare yoksa “failed” sinyali
        if self._proc and (not self._proc.is_alive()) and self._q.empty():
            self._poll.stop()
            self.failed.emit("Kamera süreci bitti")
            return

        last = None
        while True:
            try:
                item = self._q.get_nowait()
                last = item
            except pyqueue.Empty:
                break
            except Exception:
                break

        if last is not None:
            self.new_frame.emit(last)
