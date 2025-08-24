# adapters/camera/opencv_adapter.py
"""
Process-tabanlı OpenCV adaptörü (CUDA opsiyonlu).
– GPU varsa: kare GPU’ye upload, (isteğe bağlı resize) → host belleğe geri
– Renk dönüşümü UI’de tek .rgbSwapped() ile yapılacak
– RTSP için path’e '?tcp' veya '?udp' eklersen (örn: .../cam1?tcp),
  OpenCV-FFmpeg backend'e uygun seçenekler ENV ile geçirilir ve URL temizlenir.
"""

from __future__ import annotations
import os, cv2, time, logging, multiprocessing
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from core.ports.logger_port import ILoggerPort


# ------------------------------ yardımcılar ------------------------------
def _cuda_available() -> bool:
    try:
        return cv2.cuda.getCudaEnabledDeviceCount() > 0
    except AttributeError:
        return False

def _is_rtsp(url: str) -> bool:
    try:
        return url.lower().startswith("rtsp://")
    except Exception:
        return False

def _apply_rtsp_transport_from_query(url: str) -> str:
    """
    URL'de '?tcp' veya '?udp' varsa:
      - FFmpeg capture options'u env ile ayarla
      - URL'den query'i çıkarıp temiz URL döndür
    Yoksa URL’i aynen döndürür.

    Destekli biçimler:
      rtsp://host:8554/cam1?tcp
      rtsp://host:8554/cam1?udp
      rtsp://host:8554/cam1?transport=tcp  (veya udp)
    """
    if not _is_rtsp(url):
        return url

    parsed = urlparse(url)
    query_raw = parsed.query or ""
    q = parse_qs(query_raw)

    # Basit: "?tcp" veya "?udp"
    wants_tcp = ("tcp" in query_raw.lower())
    wants_udp = ("udp" in query_raw.lower())

    # Daha açık: "?transport=tcp|udp"
    tr = (q.get("transport", [""])[0] or "").lower()
    if tr in ("tcp", "udp"):
        wants_tcp = (tr == "tcp")
        wants_udp = (tr == "udp")

    if wants_tcp or wants_udp:
        transport = "tcp" if wants_tcp else "udp"
        # Düşük gecikme odaklı temel ayarlar:
        # - rtsp_transport;{tcp|udp}  → taşıma seçimi
        # - stimeout;2000000          → 2 sn socket timeout (µs)
        # - max_delay;0               → FFmpeg tarafı jitter kuyruğunu minimumda tut
        # - buffer_size;102400        → giriş buffer'ını küçük tut (100 KB)
        opts = [
            f"rtsp_transport;{transport}",
            "stimeout;2000000",
            "max_delay;0",
            "buffer_size;102400",
        ]
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "|".join(opts)

        # Query’i kaldır (OpenCV’ye temiz URL ver)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        return clean_url

    return url


# ------------------------------ process ------------------------------
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

        # Kaynağı hazırla: RTSP ise '?tcp'/'?udp' işaretini ENV'e uygula ve URL'i temizle
        src = str(self._src)
        if src.isdigit():
            # Yerel kamera index'i
            cap = cv2.VideoCapture(int(src))
        else:
            open_url = _apply_rtsp_transport_from_query(src)
            if _is_rtsp(open_url):
                # FFmpeg backend ile aç – RTSP’de daha tutarlı
                cap = cv2.VideoCapture(open_url, cv2.CAP_FFMPEG)

                # Destekleyen derlemelerde etkili olabilir:
                try:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)           # dequeue hızını artır
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000) # 3s open timeout
                    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2000) # 2s read timeout
                except Exception:
                    pass
            else:
                # Dosya veya başka URL tipi
                cap = cv2.VideoCapture(open_url)

        if not cap.isOpened():
            log.error(f"Kamera/akış açılamadı: {self._src}")
            return

        # İstenen çözünürlüğe çek
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self._w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._h)

        if self._cuda:
            gpu_mat = cv2.cuda_GpuMat()
            # gpu_resize = cv2.cuda.resize  # gerekirse ileride

        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok:
                # RTSP kısa kopma anlarında hemen çıkma; küçük bekleme ile yeniden dene
                # (cap.read False → bağlantı askıda kalmış olabilir)
                time.sleep(0.02)
                continue

            if self._cuda:
                gpu_mat.upload(frame)
                frame = gpu_mat.download()  # BGR olarak geri

            # QLabel'e uygun hale getir
            if frame is not None and (frame.shape[1] != self._w or frame.shape[0] != self._h):
                frame = cv2.resize(frame, (self._w, self._h))

            # Kuyruğa son kareyi koy (overflow'da eskisini düşür)
            if self._q.full():
                try:
                    self._q.get_nowait()
                except Exception:
                    pass
            try:
                self._q.put_nowait(frame)
            except Exception:
                pass

            # UI tarafını boğmamak için küçük uyku
            time.sleep(0.001)


# ------------------------------ Qt adapter ------------------------------
class OpenCVAdapter(QObject):
    started = pyqtSignal()
    stopped = pyqtSignal(str)
    failed = pyqtSignal(str)
    new_frame = pyqtSignal(object)   # numpy.ndarray (BGR)

    def __init__(self, logger: ILoggerPort, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._log = logger
        self._proc: Optional[multiprocessing.Process] = None
        self._q: Optional[multiprocessing.Queue] = None
        self._stop_evt: Optional[multiprocessing.Event] = None
        self._poll = QTimer(self, interval=16)
        self._poll.timeout.connect(self._poll_q)
        self._cuda = _cuda_available()
        if self._cuda:
            self._log.info("[Cam] CUDA destekli OpenCV tespit edildi.")

    def start(self, src: str, res: str):
        # Çalışıyorsa durdur
        if self._proc and self._proc.is_alive():
            self.stop()

        # Çözünürlük doğrula
        try:
            w, h = map(int, res.lower().replace('×', 'x').split('x'))
        except ValueError:
            self._log.error(f"Geçersiz çözünürlük: {res}")
            self.failed.emit("Çözünürlük")
            return

        # Süreç + kuyruğu kur
        self._q = multiprocessing.Queue(2)
        self._stop_evt = multiprocessing.Event()
        log_level = getattr(logging, self._log.__dict__.get("levelname", "INFO"), logging.INFO)
        self._proc = _CameraReaderProcess(
            src, (w, h), self._q, self._stop_evt, self._cuda,
            log_level=logging.getLevelName(log_level)
        )
        self._proc.start()
        self._poll.start()
        self.started.emit()

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
        self._poll.stop()
        self._log.info("Kamera sürecinin kapanması bekleniyor…")

    # ---------------- internal helper ----------------
    def _check_proc_end(self):
        """100 ms’de bir çağrılır; süreç ölmezse 2 sn sonra terminate."""
        if not self._proc:
            self._wait_tmr.stop()
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
        try:
            self._proc.join(timeout=0)
        except Exception:
            pass
        self._proc = None
        self._q = None
        self.stopped.emit(reason)

    def _poll_q(self):
        if not self._q:
            return

        # Süreç öldüyse ve kuyruk boşsa failure bildir
        if self._proc and (not self._proc.is_alive()) and self._q.empty():
            self._poll.stop()
            self.failed.emit("Kamera süreci bitti")
            return

        last = None
        while not self._q.empty():
            try:
                last = self._q.get_nowait()
            except multiprocessing.queues.Empty:
                break

        if last is not None:
            self.new_frame.emit(last)
