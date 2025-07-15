# adapters/camera/opencv_adapter.py
"""
Process-tabanlı OpenCV adaptörü (CUDA opsiyonlu).
– GPU varsa: kare GPU’ye upload, (isteğe bağlı resize) → host belleğe geri
– Renk dönüşümü UI’de tek .rgbSwapped() ile yapılacak
"""

from __future__ import annotations
import cv2, time, logging, multiprocessing
from typing import Optional, Tuple
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from core.ports.logger_port import ILoggerPort


def _cuda_available() -> bool:
    try:
        return cv2.cuda.getCudaEnabledDeviceCount() > 0
    except AttributeError:
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

        cap = cv2.VideoCapture(int(self._src)) if str(self._src).isdigit() else cv2.VideoCapture(self._src)
        if not cap.isOpened():
            log.error(f"Kamera açılamadı: {self._src}"); return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self._w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._h)

        if self._cuda:
            gpu_mat = cv2.cuda_GpuMat()
            # gpu_resize = cv2.cuda.resize  # gelecekte gerekirse

        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok: break

            if self._cuda:
                gpu_mat.upload(frame)
                # gpu_mat = gpu_resize(gpu_mat,(self._w,self._h))
                frame = gpu_mat.download()       # BGR olarak geri

            if self._q.full():
                try: self._q.get_nowait()
                except Exception: pass
            try: self._q.put_nowait(frame)
            except Exception: pass
            time.sleep(0.001)

        cap.release(); log.info("Kamera kapatıldı.")


class OpenCVAdapter(QObject):
    started = pyqtSignal(); stopped = pyqtSignal(str); failed = pyqtSignal(str)
    new_frame = pyqtSignal(object)   # numpy.ndarray (BGR)

    def __init__(self, logger: ILoggerPort, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._log = logger
        self._proc = None; self._q = None; self._stop_evt = None
        self._poll = QTimer(self, interval=16); self._poll.timeout.connect(self._poll_q)
        self._cuda = _cuda_available()
        if self._cuda: self._log.info("[Cam] CUDA destekli OpenCV tespit edildi.")

    def start(self, src: str, res: str):
        if self._proc and self._proc.is_alive(): self.stop()
        try: w,h = map(int, res.lower().replace('×','x').split('x'))
        except ValueError:
            self._log.error(f"Geçersiz çözünürlük: {res}"); self.failed.emit("Çözünürlük"); return
        self._q, self._stop_evt = multiprocessing.Queue(2), multiprocessing.Event()
        self._proc = _CameraReaderProcess(src,(w,h),self._q,self._stop_evt,self._cuda,
                                          log_level=self._log.__dict__.get("levelname","INFO"))
        self._proc.start(); self._poll.start(); self.started.emit()

    def stop(self):
        """Kamerayı durdur – UI’yı bloklama."""
        if not self._proc:
            return

        # 1) Sürece “dur” sinyali gönder
        self._stop_evt.set()

        # 2) join(2) yerine: arka planda bekle
        self._wait_tmr = QTimer(self, interval=100, singleShot=False)
        self._wait_elapsed = 0  # ms
        self._wait_tmr.timeout.connect(self._check_proc_end)
        self._wait_tmr.start()

        # UI hemen serbest – stopped emit’ini süreç bittikten sonra yapacağız
        self._poll.stop()  # kare çekmeyi durdur
        self._log.info("Kamera sürecinin kapanması bekleniyor…")

    # ---------------- internal helper ----------------
    def _check_proc_end(self):
        """100 ms’de bir çağrılır; süreç ölmezse 2 sn sonra terminate."""
        if not self._proc:  # güvenlik
            self._wait_tmr.stop();
            return

        if not self._proc.is_alive():
            self._finalize_stop("normal exit")
            return

        self._wait_elapsed += 100
        if self._wait_elapsed >= 2000:  # 2 sn geçti
            self._log.warning("Kamera süreci zorla sonlandırılıyor.")
            self._proc.terminate()
            self._finalize_stop("forced")

    def _finalize_stop(self, reason: str):
        self._wait_tmr.stop()
        self._proc.join(timeout=0)  # artık anlık
        self._proc = None;
        self._q = None
        self.stopped.emit(reason)

    def _poll_q(self):
        if not self._q: return
        if self._proc and (not self._proc.is_alive()) and self._q.empty():
            self._poll.stop(); self.failed.emit("Kamera süreci bitti"); return
        last = None
        while not self._q.empty():
            try: last = self._q.get_nowait()
            except multiprocessing.queues.Empty: break
        if last is not None: self.new_frame.emit(last)
