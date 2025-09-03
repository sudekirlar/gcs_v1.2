# adapters/camera/opencv_adapter.py
"""
Process-tabanlı OpenCV GStreamer adaptörü (Windows).
– Kaynak GStreamer pipeline olarak gelir (Settings.camera_sources).
– Decoder seçimi: decodebin + FEATURE_RANK ile NVDEC (nvh264dec) > avdec_h264.
– GPU varsa: OpenCV-CUDA ile opsiyonel upload/resize → host’a geri.
– UI tarafı RGB dönüşümü QImage.rgbSwapped() ile yapar.
"""

from __future__ import annotations
import os, cv2, time, logging, multiprocessing, queue as pyqueue
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
        self,
        source: str,                        # GStreamer pipeline STRING
        resolution_wh: Tuple[int, int],     # QLabel’e uydurmak için post-resize
        frame_q: multiprocessing.Queue,
        stop_event: multiprocessing.Event,
        use_cuda: bool,
        log_level: str = "INFO",
    ):
        super().__init__(name="CameraReader")
        self._src, (self._w, self._h) = source, resolution_wh
        self._q, self._stop, self._cuda = frame_q, stop_event, use_cuda
        self._log_level = log_level

    def _setup_gstreamer_env(self, log: logging.Logger) -> None:
        """
        Her process başlangıcında:
          - GStreamer DLL arama yolu (Windows)
          - NVDEC/avdec öncelik sırası (decodebin için)
        """
        # 1) DLL yolu (Windows – zorunlu)
        gst_bin_path = r"C:\Program Files\gstreamer\1.0\msvc_x86_64\bin"
        try:
            if hasattr(os, "add_dll_directory") and os.path.exists(gst_bin_path):
                os.add_dll_directory(gst_bin_path)
                log.info(f"[GST] DLL yolu eklendi: {gst_bin_path}")
            else:
                log.warning("[GST] DLL yolu eklenemedi veya bulunamadı.")
        except Exception as e:
            log.warning(f"[GST] DLL yolu eklenirken istisna: {e}")

        # 2) Decoder önceliği: NVDEC MAX, avdec LOW (decodebin bunu dikkate alır)
        try:
            ranks = [
                "nvh264dec:MAX", "nvh265dec:MAX",
                "avdec_h264:LOW", "avdec_h265:LOW",
            ]
            os.environ["GST_PLUGIN_FEATURE_RANK"] = ";".join(ranks)
            os.environ.pop("GST_PLUGIN_PATH", None)  # kullanıcı PATH’leri karışmasın
            log.info(f"[GST] FEATURE_RANK='{os.environ.get('GST_PLUGIN_FEATURE_RANK')}'")
        except Exception as e:
            log.warning(f"[GST] FEATURE_RANK ayarlanamadı: {e}")

    def run(self):
        logging.basicConfig(
            level=getattr(logging, self._log_level, logging.INFO),
            format="CamProc | %(levelname)s | %(message)s",
        )
        log = logging.getLogger("cam.reader")

        os.environ["GST_DEBUG"] = "3"  # 2 = INFO seviyesi, 3 yaparsan çok daha detaylı

        self._setup_gstreamer_env(log)

        # CUDA (OpenCV) kullanılabilirliği – decode GPU’dan bağımsızdır
        log.info(f"OpenCV-CUDA: {'AKTİF' if self._cuda else 'PASİF'}")
        log.debug(f"Açılacak pipeline → {self._src}")

        # GStreamer ile aç
        cap = cv2.VideoCapture(self._src, cv2.CAP_GSTREAMER)
        if not cap.isOpened():
            log.error("GStreamer pipeline AÇILAMADI. Pipeline / kurulum / ağ parametrelerini kontrol et.")
            return

        log.info("Pipeline açıldı; decodebin NVDEC'i tercih edecek, yoksa avdec'e düşecek.")

        gpu_mat = None
        if self._cuda:
            try:
                gpu_mat = cv2.cuda_GpuMat()
            except Exception as e:
                log.warning(f"CUDA GpuMat oluşturulamadı, CPU moduna düşülüyor. Detay: {e}")
                self._cuda = False

        last_ok = True
        try:
            while not self._stop.is_set():
                t0 = time.perf_counter()
                ok, frame = cap.read()
                if not ok or frame is None:
                    if last_ok:
                        log.warning("Frame alınamadı (geçici). Akış bekleniyor…")
                    last_ok = False
                    time.sleep(0.01)
                    continue

                last_ok = True

                # (Opsiyonel) OpenCV-CUDA işleme
                if self._cuda and gpu_mat is not None:
                    try:
                        gpu_mat.upload(frame)
                        # gerekirse burada CUDA resize/filtre ekleyebilirsin
                        frame = gpu_mat.download()  # BGR
                    except Exception as e:
                        log.error(f"CUDA işleminde hata. CPU’ya düşüyorum. Detay: {e}")
                        self._cuda = False

                # QLabel alanına uygun post-resize (CPU)
                if (frame.shape[1] != self._w) or (frame.shape[0] != self._h):
                    try:
                        frame = cv2.resize(frame, (self._w, self._h), interpolation=cv2.INTER_AREA)
                    except Exception:
                        pass

                # Kuyruğa en güncel kare – doluysa eskisini at
                if self._q.full():
                    try:
                        self._q.get_nowait()
                    except Exception:
                        pass
                try:
                    self._q.put_nowait(frame)
                except Exception:
                    pass

                # Hafif nefes – UI’yi rahatlat
                if (time.perf_counter() - t0) < 0.001:
                    time.sleep(0.001)

        finally:
            try:
                if cap and cap.isOpened():
                    cap.release()
                    log.info("VideoCapture serbest bırakıldı.")
            except Exception:
                pass
            log.info("Kamera okuma süreci kapandı.")


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

        # Ana döngüde kuyruğu poll eden timer (~60 Hz)
        self._poll = QTimer(self)
        self._poll.setInterval(16)
        self._poll.timeout.connect(self._poll_q)

        self._cuda = _cuda_available()
        if self._cuda:
            try:
                self._log.info("[Cam] OpenCV-CUDA tespit edildi (GPU işleme etkin).")
            except Exception:
                pass

        self._wait_tmr: Optional[QTimer] = None
        self._wait_elapsed = 0  # ms

    # ---------------- public API ----------------
    def start(self, src: str, res: str):
        # Zaten çalışıyorsa kapat
        if self._proc and self._proc.is_alive():
            self.stop()

        # Çözünürlük parse
        try:
            w, h = map(int, res.lower().replace('×', 'x').split('x'))
        except Exception:
            self._log.error("[Cam] Geçersiz çözünürlük: %s", res)
            self.failed.emit("Çözünürlük")
            return

        # Pipeline string beklenir; numeric kamera index desteklemiyoruz
        self._q = multiprocessing.Queue(maxsize=2)
        self._stop_evt = multiprocessing.Event()

        log_level = "INFO"

        # Process’i başlat
        self._proc = _CameraReaderProcess(
            src, (w, h), self._q, self._stop_evt, self._cuda, log_level=log_level
        )
        self._proc.daemon = True
        try:
            self._proc.start()
        except Exception as e:
            self._log.error(f"[Cam] Kamera süreci başlatılamadı: {e}")
            self.failed.emit("Process")
            return

        self._poll.start()
        self.started.emit()
        self._log.info("[Cam] Kamera adaptörü başlatıldı.")

    def stop(self):
        if not self._proc:
            return
        try:
            if self._stop_evt:
                self._stop_evt.set()
        except Exception:
            pass

        if self._wait_tmr is None:
            self._wait_tmr = QTimer(self)
            self._wait_tmr.setInterval(100)
            self._wait_tmr.setSingleShot(False)
            self._wait_tmr.timeout.connect(self._check_proc_end)

        self._wait_elapsed = 0
        self._wait_tmr.start()

        self._poll.stop()
        self._log.info("[Cam] Kamera sürecinin kapanması bekleniyor…")

    # -------------- internal helpers --------------
    def _check_proc_end(self):
        if not self._proc:
            if self._wait_tmr:
                self._wait_tmr.stop()
            return

        if not self._proc.is_alive():
            self._finalize_stop("normal exit")
            return

        self._wait_elapsed += 100
        if self._wait_elapsed >= 2000:
            self._log.warning("[Cam] Kamera süreci zorla sonlandırılıyor.")
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
        self._log.info(f"[Cam] Kamera adaptörü durdu: {reason}")

    def _poll_q(self):
        if not self._q:
            return

        # Süreç çöktü + sırada kare yoksa → failed
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
