# adapters/camera/opencv_adapter.py
"""
Process-tabanlı OpenCV GStreamer adaptörü (Windows).
– Kaynak GStreamer pipeline olarak gelir (Settings.camera_sources).
– Decoder seçimi: decodebin + FEATURE_RANK ile NVDEC (nvh264dec) > avdec_h264.
– Bu sürümde "sağlamlaştırma" eklendi:
    1) Başlangıç zaman aşımı (20s içinde ilk kare gelmezse)
    2) Yayın kesilmesi tespiti (10s kare yoksa)
    3) Net hata nedenleri (failed(reason))
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
        resolution_wh: Tuple[int, int],     # QLabel’e uydurmak için post-resize (UI zaten ölçekler)
        frame_q: multiprocessing.Queue,
        reason_q: multiprocessing.Queue,     # NEW: süreçten neden bilgisi
        stop_event: multiprocessing.Event,
        use_cuda: bool,
        log_level: str = "INFO",
    ):
        super().__init__(name="CameraReader")
        self._src, (self._w, self._h) = source, resolution_wh
        self._q, self._rq, self._stop, self._cuda = frame_q, reason_q, stop_event, use_cuda
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

    def _send_reason(self, reason: str) -> None:
        """UI’ya net mesaj geçmek için (non-blocking)."""
        try:
            if self._rq is not None:
                self._rq.put_nowait(reason)
        except Exception:
            pass

    def run(self):
        logging.basicConfig(
            level=getattr(logging, self._log_level, logging.INFO),
            format="CamProc | %(levelname)s | %(message)s",
        )
        log = logging.getLogger("cam.reader")

        # GStreamer debug’u üretimde kapalı tutmak daha iyi
        # os.environ["GST_DEBUG"] = "3"

        self._setup_gstreamer_env(log)

        # CUDA (OpenCV) kullanılabilirliği – decode GPU’dan bağımsızdır
        log.info(f"OpenCV-CUDA: {'AKTİF' if self._cuda else 'PASİF'}")
        log.debug(f"Açılacak pipeline → {self._src}")

        # GStreamer ile aç
        cap = cv2.VideoCapture(self._src, cv2.CAP_GSTREAMER)
        if not cap.isOpened():
            log.error("GStreamer pipeline AÇILAMADI. Pipeline / kurulum / ağ parametrelerini kontrol et.")
            self._send_reason("Pipeline açılamadı")
            return

        log.info("Pipeline açıldı; decodebin NVDEC'i tercih edecek, yoksa avdec'e düşecek.")

        gpu_mat = None
        if self._cuda:
            try:
                gpu_mat = cv2.cuda_GpuMat()
            except Exception as e:
                log.warning(f"CUDA GpuMat oluşturulamadı, CPU moduna düşülüyor. Detay: {e}")
                self._cuda = False

        # ---- Liveness (yayın kesilmesi) izlemesi ----
        last_success = time.perf_counter()
        LIVENESS_TIMEOUT = 10.0  # sn

        last_warn = 0.0
        try:
            while not self._stop.is_set():
                t0 = time.perf_counter()
                ok, frame = cap.read()
                if not ok or frame is None:
                    now = time.perf_counter()
                    # Yayın kesilmesi kontrolü
                    if (now - last_success) > LIVENESS_TIMEOUT:
                        log.error(f"Yayından {LIVENESS_TIMEOUT} saniyedir kare alınamıyor. Yayın kesildi varsayılıyor.")
                        self._send_reason(f"Yayın kesildi ({int(LIVENESS_TIMEOUT)}s)")
                        break
                    # Sık log basma
                    if (now - last_warn) > 2.0:
                        log.warning("Frame alınamadı (geçici). Akış/EOS bekleniyor…")
                        last_warn = now
                    time.sleep(0.01)
                    continue

                # Başarılı okuma → liveness timer’ı güncelle
                last_success = time.perf_counter()

                # (İsteğe bağlı) OpenCV-CUDA burada gerçek işlem yapacaksan kullanılmalı;
                # yalnızca upload/download yapmak gereksizdir. Şimdilik hiç dokunmuyoruz.

                # Process içinde resize/conversion YOK (UI ölçekler)
                # Kuyruğa en taze kare – doluysa eskisini at
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
    new_frame = pyqtSignal(object)   # numpy.ndarray (BGR/BGRA)

    def __init__(self, logger: ILoggerPort, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._log: ILoggerPort = logger
        self._proc: Optional[multiprocessing.Process] = None
        self._q: Optional[multiprocessing.Queue] = None
        self._reason_q: Optional[multiprocessing.Queue] = None  # NEW
        self._stop_evt: Optional[multiprocessing.Event] = None

        # Ana döngüde kuyruğu poll eden timer (~60 Hz)
        self._poll = QTimer(self)
        self._poll.setInterval(16)
        self._poll.timeout.connect(self._poll_q)

        # Başlangıç zaman aşımı (ilk kare bekleme)
        self._startup_timeout_timer: Optional[QTimer] = None
        self._first_frame_seen: bool = False

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

        # Pipeline string beklenir
        self._q = multiprocessing.Queue(maxsize=1)          # düşük gecikme için 1
        self._reason_q = multiprocessing.Queue(maxsize=4)   # NEW: neden mesajları
        self._stop_evt = multiprocessing.Event()

        log_level = "INFO"

        # Process’i başlat
        self._proc = _CameraReaderProcess(
            src, (w, h), self._q, self._reason_q, self._stop_evt, self._cuda, log_level=log_level
        )
        self._proc.daemon = True
        try:
            self._proc.start()
        except Exception as e:
            self._log.error(f"[Cam] Kamera süreci başlatılamadı: {e}")
            self.failed.emit("Process")
            return

        # Başlangıç zaman aşımı: 20s içinde ilk kare gelmezse
        if self._startup_timeout_timer is None:
            self._startup_timeout_timer = QTimer(self)
            self._startup_timeout_timer.setSingleShot(True)
            self._startup_timeout_timer.timeout.connect(self._on_startup_timeout)
        self._first_frame_seen = False
        self._startup_timeout_timer.start(20000)  # 20,000 ms

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

        # Startup timeout timer’ını kapat (varsa)
        try:
            if self._startup_timeout_timer and self._startup_timeout_timer.isActive():
                self._startup_timeout_timer.stop()
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

    # -------------- callbacks & helpers --------------
    def _on_startup_timeout(self):
        """20s boyunca ilk kare gelmediyse başarısız say."""
        if self._first_frame_seen:
            return
        if self._proc and self._proc.is_alive():
            self._log.error("[Cam] Kamera başlatma zaman aşımına uğradı (20s).")
            # Temiz kapat ve UI’ya net mesaj ver
            self.stop()
            self.failed.emit("Başlatılamadı: Zaman Aşımı")

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
        self._reason_q = None
        self._stop_evt = None
        self.stopped.emit(reason)
        self._log.info(f"[Cam] Kamera adaptörü durdu: {reason}")

    def _poll_q(self):
        if not self._q:
            return

        # Önce süreçten gelen "neden" mesajlarını boşalt (varsa)
        if self._reason_q is not None:
            while True:
                try:
                    reason = self._reason_q.get_nowait()
                except pyqueue.Empty:
                    break
                except Exception:
                    break
                else:
                    # Süreç hata bildiriyor → UI’ya yansıt ve kapat
                    try:
                        self.failed.emit(str(reason))
                    finally:
                        # Süreç hâlâ yaşıyor olabilir; nazikçe durdur
                        self.stop()
                        return

        # Süreç çöktüyse ve sırada kare yoksa → failed
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
            # İlk kare geldiyse startup timeout’u iptal et
            if (self._startup_timeout_timer is not None) and self._startup_timeout_timer.isActive():
                self._startup_timeout_timer.stop()
            self._first_frame_seen = True

            self.new_frame.emit(last)
