"""
Process-tabanlı OpenCV adaptörü (CUDA opsiyonlu).
– Sürüm 2.1: Yanıp sönme (blinking) sorununu çözen _poll_q mantığı düzeltildi.
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
from enum import Enum, auto


# ------------------------------ yardımcılar (DEĞİŞİKLİK YOK) ------------------------------
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
    # Bu yardımcı fonksiyonda bir değişiklik yok.
    if not _is_rtsp(url):
        return url
    parsed = urlparse(url)
    query_raw = parsed.query or ""
    q = parse_qs(query_raw)
    wants_tcp = ("tcp" in query_raw.lower())
    wants_udp = ("udp" in query_raw.lower())
    tr = (q.get("transport", [""])[0] or "").lower()
    if tr in ("tcp", "udp"):
        wants_tcp = (tr == "tcp")
        wants_udp = (tr == "udp")
    if wants_tcp or wants_udp:
        transport = "tcp" if wants_tcp else "udp"
        opts = [f"rtsp_transport;{transport}", "stimeout;2000000", "max_delay;0", "buffer_size;102400"]
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "|".join(opts)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return url


# ------------------------------ process (DEĞİŞİKLİK YOK) ------------------------------
class CameraState(Enum):
    CONNECTING = auto()
    STREAMING = auto()
    RECONNECTING = auto()


class _CameraReaderProcess(multiprocessing.Process):
    # Bu sınıfın tamamı önceki haliyle aynı kalıyor.
    # State machine mantığı doğru çalışıyor.
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
        logging.basicConfig(level=getattr(logging, self._log_level, logging.INFO),
                            format="CamProc | %(levelname)s | %(message)s")
        log = logging.getLogger("cam.reader")
        log.info(f"Süreç başlatıldı. CUDA: {'ON' if self._cuda else 'OFF'}")
        state = CameraState.CONNECTING
        cap = None
        reconnect_delay = 1.0
        if self._cuda:
            gpu_mat = cv2.cuda_GpuMat()
        while not self._stop.is_set():
            if state == CameraState.CONNECTING:
                log.info(f"Kamera kaynağına bağlanılıyor: {self._src}")
                src = str(self._src)
                if src.isdigit():
                    cap = cv2.VideoCapture(int(src))
                else:
                    open_url = _apply_rtsp_transport_from_query(src)
                    cap = cv2.VideoCapture(open_url, cv2.CAP_FFMPEG)
                    try:
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000)
                        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2000)
                    except Exception:
                        pass
                if cap and cap.isOpened():
                    log.info("Bağlantı başarılı. Akış başlıyor.")
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._w)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._h)
                    state = CameraState.STREAMING
                    reconnect_delay = 1.0
                else:
                    log.error(f"Kamera/akış açılamadı: {self._src}")
                    state = CameraState.RECONNECTING
            elif state == CameraState.STREAMING:
                ok, frame = cap.read()
                if ok:
                    if self._cuda:
                        gpu_mat.upload(frame)
                        frame = gpu_mat.download()
                    if frame.shape[1] != self._w or frame.shape[0] != self._h:
                        frame = cv2.resize(frame, (self._w, self._h), interpolation=cv2.INTER_AREA)
                    if self._q.full():
                        try:
                            self._q.get_nowait()
                        except Exception:
                            pass
                    try:
                        self._q.put_nowait(frame)
                    except Exception:
                        pass
                else:
                    log.warning("Akış kesildi. Yeniden bağlanma moduna geçiliyor.")
                    state = CameraState.RECONNECTING
                    try:
                        self._q.put_nowait(None)
                    except Exception:
                        pass
            elif state == CameraState.RECONNECTING:
                if cap:
                    cap.release()
                    cap = None
                log.info(f"{reconnect_delay:.1f} saniye sonra yeniden bağlanma denenecek...")
                wait_end_time = time.time() + reconnect_delay
                while time.time() < wait_end_time:
                    if self._stop.is_set(): break
                    time.sleep(0.1)
                if self._stop.is_set(): break
                reconnect_delay = min(reconnect_delay * 1.5, 30)
                state = CameraState.CONNECTING
        log.info("Kamera süreci durduruluyor.")
        if cap:
            cap.release()


# ------------------------------ Qt adapter ------------------------------
class OpenCVAdapter(QObject):
    started = pyqtSignal()
    stopped = pyqtSignal(str)
    failed = pyqtSignal(str)
    new_frame = pyqtSignal(object)

    def __init__(self, logger: ILoggerPort, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._log = logger
        self._proc: Optional[multiprocessing.Process] = None
        self._q: Optional[multiprocessing.Queue] = None
        self._stop_evt: Optional[multiprocessing.Event] = None
        self._poll = QTimer(self, interval=16)  # ~60 FPS
        self._poll.timeout.connect(self._poll_q)
        self._cuda = _cuda_available()
        if self._cuda:
            self._log.info("[Cam] CUDA destekli OpenCV tespit edildi.")

    # start, stop, _check_proc_end, _finalize_stop metodları aynı kalıyor (DEĞİŞİKLİK YOK)
    def start(self, src: str, res: str):
        if self._proc and self._proc.is_alive():
            self.stop()
        try:
            w, h = map(int, res.lower().replace('×', 'x').split('x'))
        except ValueError:
            self._log.error(f"Geçersiz çözünürlük: {res}")
            self.failed.emit("Çözünürlük")
            return
        self._q = multiprocessing.Queue(2)
        self._stop_evt = multiprocessing.Event()
        log_level_name = logging.getLevelName(self._log.level if hasattr(self._log, 'level') else logging.INFO)
        self._proc = _CameraReaderProcess(src, (w, h), self._q, self._stop_evt, self._cuda, log_level=log_level_name)
        self._proc.start()
        self._poll.start()
        self.started.emit()

    def stop(self):
        if not self._proc: return
        if self._stop_evt: self._stop_evt.set()
        self._wait_tmr = QTimer(self, interval=100, singleShot=False)
        self._wait_elapsed = 0
        self._wait_tmr.timeout.connect(self._check_proc_end)
        self._wait_tmr.start()
        self._poll.stop()
        self._log.info("Kamera sürecinin kapanması bekleniyor…")

    def _check_proc_end(self):
        if not self._proc:
            self._wait_tmr.stop()
            return
        if not self._proc.is_alive():
            self._finalize_stop("normal exit")
            return
        self._wait_elapsed += 100
        if self._wait_elapsed >= 2000:
            self._log.warning("Kamera süreci zorla sonlandırılıyor.")
            self._proc.terminate()
            self._finalize_stop("forced")

    def _finalize_stop(self, reason: str):
        if hasattr(self, '_wait_tmr'): self._wait_tmr.stop()
        if self._proc:
            self._proc.join(timeout=0.5)
            self._proc = None
        self._q = None
        self.stopped.emit(reason)

    # YENİ ve DÜZELTİLMİŞ MANTIK
    def _poll_q(self):
        """
        Kuyruktan en son öğeyi alır ve UI'ye gönderir.
        Bu metodun yeni hali yanıp sönme (blinking) sorununu çözer.
        """
        if not self._q or self._q.empty():
            # Kuyruk yoksa veya BOŞSA, hiçbir şey yapma ve fonksiyondan çık.
            # Bu, "henüz yeni kare gelmedi" durumudur, hata değil.
            return

        # Sürecin çökme ihtimaline karşı kontrol
        if self._proc and not self._proc.is_alive() and self._q.empty():
            self._poll.stop()
            self.failed.emit("Kamera süreci beklenmedik şekilde bitti")
            return

        # Kuyruktaki tüm bekleyen kareleri atla ve sadece en sonuncuyu al.
        # Bu, UI'nin her zaman en güncel kareyi göstermesini sağlar.
        last_item = None
        while not self._q.empty():
            try:
                last_item = self._q.get_nowait()
            except multiprocessing.queues.Empty:
                break

        # Kuyruktan aldığımız son öğe ne ise (resim karesi veya None),
        # onu UI'ye sinyal olarak gönder.
        # Eğer yukarıdaki ilk if bloğu sayesinde buraya geldiysek,
        # kuyruğun en az bir eleman içerdiğinden eminiz.
        self.new_frame.emit(last_item)