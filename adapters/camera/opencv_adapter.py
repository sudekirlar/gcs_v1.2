# adapters/camera/opencv_adapter.py
"""
Process-tabanlı OpenCV GStreamer adaptörü (Windows).
– Kaynak GStreamer pipeline olarak gelir (Settings.camera_sources).
– Decoder seçimi: decodebin + FEATURE_RANK ile NVDEC (nvh264dec) > avdec_h264.
– Sağlamlaştırma:
    1) Başlangıç zaman aşımı (20s içinde ilk kare gelmezse)
    2) Yayın kesilmesi tespiti (10s kare yoksa)
    3) Net hata nedenleri (failed(reason))
– Pose entegrasyonu (orchestrator model):
    • _CameraReaderProcess SADECE kare okur ve TEK kuyruğa yazar.
    • OpenCVAdapter UI’yı besler ve zaman-tabanlı örnekleme ile AI’ya kare gönderir.
    • PoseProcessor ayrı process’te çalışır (MultiPoseManager).
"""

from __future__ import annotations
import os, cv2, time, logging, multiprocessing, queue as pyqueue
from typing import Optional, Tuple, List, Dict, Any
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from core.ports.logger_port import ILoggerPort

# AI modülü (yalnızca alt process'te ağır yüklenir; burada import güvenli)
try:
    from services.mediapipe_pose_checker import MultiPoseManager  # AI process kullanacak
    _HAS_POSE = True
except Exception:
    _HAS_POSE = False


def _cuda_available() -> bool:
    try:
        return cv2.cuda.getCudaEnabledDeviceCount() > 0
    except Exception:
        return False


# Tek sorumluluğu vardır: GStreamer pipeline'dan kare okuyup frame_q'ya yazmak.
class _CameraReaderProcess(multiprocessing.Process):
    def __init__(
        self,
        source: str,                        # GStreamer pipeline STRING
        resolution_wh: Tuple[int, int],
        frame_q: multiprocessing.Queue,
        reason_q: multiprocessing.Queue,
        stop_event: multiprocessing.Event,
        use_cuda: bool,
        log_level: str = "INFO",
    ):
        super().__init__(name="CameraReader")
        self._src, (self._w, self._h) = source, resolution_wh
        self._q, self._rq, self._stop, self._cuda = frame_q, reason_q, stop_event, use_cuda
        self._log_level = log_level

    def _setup_gstreamer_env(self, log: logging.Logger) -> None:
        # 1) DLL yolu (Windows – zorunlu) (Manuel Derlemeden zorunlu şablonumuz)
        gst_bin_path = r"C:\Program Files\gstreamer\1.0\msvc_x86_64\bin"
        try:
            if hasattr(os, "add_dll_directory") and os.path.exists(gst_bin_path):
                os.add_dll_directory(gst_bin_path)
                log.info(f"[GST] DLL yolu eklendi: {gst_bin_path}")
            else:
                log.warning("[GST] DLL yolu eklenemedi veya bulunamadı.")
        except Exception as e:
            log.warning(f"[GST] DLL yolu eklenirken istisna: {e}")

        # 2) Decoder önceliği
        try:
            ranks = [
                "nvh264dec:MAX", "nvh265dec:MAX",
                "avdec_h264:LOW", "avdec_h265:LOW",
            ]
            os.environ["GST_PLUGIN_FEATURE_RANK"] = ";".join(ranks)
            os.environ.pop("GST_PLUGIN_PATH", None)
            log.info(f"[GST] FEATURE_RANK='{os.environ.get('GST_PLUGIN_FEATURE_RANK')}'")
        except Exception as e:
            log.warning(f"[GST] FEATURE_RANK ayarlanamadı: {e}")

    def _send_reason(self, reason: str) -> None:
        try:
            if self._rq is not None:
                self._rq.put_nowait(reason)
        except Exception:
            pass

    def run(self):
        os.environ["GST_DEBUG"] = "3,uridecodebin:5"
        logging.basicConfig(
            level=getattr(logging, self._log_level, logging.INFO),
            format="CamProc | %(levelname)s | %(message)s",
        )
        log = logging.getLogger("cam.reader")
        self._setup_gstreamer_env(log)

        log.info(f"OpenCV-CUDA: {'AKTİF' if self._cuda else 'PASİF'}")
        log.debug(f"Açılacak pipeline → {self._src}")

        cap = cv2.VideoCapture(self._src, cv2.CAP_GSTREAMER)
        if not cap.isOpened():
            log.error("GStreamer pipeline AÇILAMADI. Pipeline / kurulum / ağ parametrelerini kontrol et.")
            self._send_reason("Pipeline açılamadı")
            return

        log.info("Pipeline açıldı; decodebin NVDEC'i tercih edecek, yoksa avdec'e düşecek.")

        # Liveness
        last_success = time.perf_counter()
        LIVENESS_TIMEOUT = 10.0  # sn
        last_warn = 0.0

        try:
            while not self._stop.is_set():
                t0 = time.perf_counter()
                ok, frame = cap.read()
                if not ok or frame is None:
                    now = time.perf_counter()
                    if (now - last_success) > LIVENESS_TIMEOUT:
                        log.error(f"Yayından {LIVENESS_TIMEOUT} saniyedir kare alınamıyor. Yayın kesildi varsayılıyor.")
                        self._send_reason(f"Yayın kesildi ({int(LIVENESS_TIMEOUT)}s)")
                        break
                    if (now - last_warn) > 2.0:
                        log.warning("Frame alınamadı (geçici). Akış/EOS bekleniyor…")
                        last_warn = now
                    time.sleep(0.01)
                    continue

                last_success = time.perf_counter()

                # UI kuyruğuna en taze kare (maxsize=1 → eskisini at)
                if self._q.full():
                    try: self._q.get_nowait()
                    except Exception: pass
                try: self._q.put_nowait(frame)
                except Exception: pass

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


# Gelen queue'dan frame'leri alır ve ve mediapipe+yolo tarafına gönderir. Buradan gelen çıktıyı out queue içine yazar.
class _PoseProcessorProcess(multiprocessing.Process):
    def __init__(
        self,
        in_q: multiprocessing.Queue,
        out_q: multiprocessing.Queue,
        stop_event: multiprocessing.Event,
        topk: int = 2,
        log_level: str = "INFO"
    ):
        super().__init__(name="PoseProcessor")
        self._in_q = in_q
        self._out_q = out_q
        self._stop = stop_event
        self._topk = max(1, int(topk))
        self._log_level = log_level

    @staticmethod
    def _label_of(cid: int) -> Optional[str]:
        if cid == 0: return "T-POSE"
        if cid == 1: return "ARMS-UP"
        return None

    def run(self):
        logging.basicConfig(
            level=getattr(logging, self._log_level, logging.INFO),
            format="PoseProc | %(levelname)s | %(message)s",
        )
        log = logging.getLogger("pose.proc")

        if not _HAS_POSE:
            log.error("mediapipe_pose_checker import edilemedi. PoseProcessor başlatılamıyor.")
            return

        try:
            pipe = MultiPoseManager(topk=self._topk)
        except Exception as e:
            log.error(f"MultiPoseManager başlatılamadı: {e}")
            return

        try:
            while not self._stop.is_set():
                try:
                    frame = self._in_q.get(timeout=0.5)
                except pyqueue.Empty:
                    continue
                except Exception:
                    continue

                try:
                    results = pipe.process(frame)  # List[(track_id, class_id, bbox, conf)]
                except Exception as e:
                    log.warning(f"Pose process hatası: {e}")
                    results = []

                now_ts = time.time()
                dtos: List[Dict[str, Any]] = []
                for tid, cid, bbox, conf in results:
                    lbl = self._label_of(int(cid))
                    if bbox is None:
                        continue
                    dto = {
                        "track_id": int(tid),
                        "class_id": int(cid),
                        "label": lbl,
                        "bbox": (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])),
                        "conf": float(conf),
                        "ts": float(now_ts),
                    }
                    dtos.append(dto)

                # En taze sonuç kalsın
                if self._out_q.full():
                    try: self._out_q.get_nowait()
                    except Exception: pass
                try: self._out_q.put_nowait(dtos)
                except Exception:
                    pass

        finally:
            try: pipe.close()
            except Exception: pass
            log.info("PoseProcessor kapandı.")


# Buranın yöneticisi.
class OpenCVAdapter(QObject):
    started = pyqtSignal()
    stopped = pyqtSignal(str)
    failed  = pyqtSignal(str)
    new_frame = pyqtSignal(object)
    pose_results = pyqtSignal(object)

    def __init__(self, logger: ILoggerPort, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._log: ILoggerPort = logger

        # Reader taraf
        self._proc: Optional[multiprocessing.Process] = None
        self._q: Optional[multiprocessing.Queue] = None
        self._reason_q: Optional[multiprocessing.Queue] = None
        self._stop_evt: Optional[multiprocessing.Event] = None

        # AI tarafı
        self._ai_proc: Optional[multiprocessing.Process] = None
        self._pose_in_q: Optional[multiprocessing.Queue] = None
        self._pose_out_q: Optional[multiprocessing.Queue] = None
        self._pose_stop_evt: Optional[multiprocessing.Event] = None

        # AI parametreleri
        self._pose_enabled: bool = True
        self._pose_topk: int = 2
        self._pose_conf_thr: float = 0.60       # bir kere loglama eşiği
        self._pose_log_ttl_sec: float = 15.0    # görünmeyen track TTL

        # Zaman tabanlı sampling: hedef AI FPS
        self._pose_target_fps: float = 10.0
        self._pose_min_interval: float = 1.0 / max(1e-3, self._pose_target_fps)
        self._last_ai_send_ts: float = 0.0

        # Bir kere loglama state’i
        self._pose_logged_by_track: Dict[int, set] = {}
        self._pose_last_seen: Dict[int, float] = {}

        # Poll timer (yaklaşık 60hz)
        self._poll = QTimer(self)
        self._poll.setInterval(16)
        self._poll.timeout.connect(self._poll_q)

        # Startup timeout
        self._startup_timeout_timer: Optional[QTimer] = None
        self._first_frame_seen: bool = False

        self._cuda = _cuda_available()
        if self._cuda:
            try: self._log.info("[Cam] OpenCV-CUDA tespit edildi (GPU işleme etkin).")
            except Exception: pass

        self._wait_tmr: Optional[QTimer] = None
        self._wait_elapsed = 0  # ms

    def start(self, src: str, res: str):
        # Zaten çalışıyorsa kapat
        if self._proc and self._proc.is_alive():
            self.stop()

        try:
            w, h = map(int, res.lower().replace('×', 'x').split('x'))
        except Exception:
            self._log.error("[Cam] Geçersiz çözünürlük: %s", res)
            self.failed.emit("Çözünürlük")
            return

        # Kuyruklar
        self._q = multiprocessing.Queue(maxsize=1)          # düşük gecikme için 1
        self._reason_q = multiprocessing.Queue(maxsize=4)
        self._stop_evt = multiprocessing.Event()

        # AI process
        if self._pose_enabled:
            self._pose_in_q = multiprocessing.Queue(maxsize=1)
            self._pose_out_q = multiprocessing.Queue(maxsize=1)
            self._pose_stop_evt = multiprocessing.Event()
            self._ai_proc = _PoseProcessorProcess(
                in_q=self._pose_in_q,
                out_q=self._pose_out_q,
                stop_event=self._pose_stop_evt,
                topk=self._pose_topk,
                log_level="INFO",
            )
            self._ai_proc.daemon = True
            try:
                self._ai_proc.start()
            except Exception as e:
                self._log.error(f"[Cam] PoseProcessor başlatılamadı: {e}")
                # Pose kapalı devam
                self._pose_enabled = False
                self._ai_proc = None
                self._pose_in_q = None
                self._pose_out_q = None
                self._pose_stop_evt = None

        # ReaderProcess
        self._proc = _CameraReaderProcess(
            src, (w, h),
            self._q, self._reason_q, self._stop_evt, self._cuda,
            log_level="INFO",
        )
        self._proc.daemon = True
        try:
            self._proc.start()
        except Exception as e:
            self._log.error(f"[Cam] Kamera süreci başlatılamadı: {e}")
            self.failed.emit("Process")
            self._stop_ai_process()
            return

        # Startup timeout
        if self._startup_timeout_timer is None:
            self._startup_timeout_timer = QTimer(self)
            self._startup_timeout_timer.setSingleShot(True)
            self._startup_timeout_timer.timeout.connect(self._on_startup_timeout)
        self._first_frame_seen = False
        self._startup_timeout_timer.start(20000)  # 20s

        # reset AI send ts
        self._last_ai_send_ts = 0.0

        self._poll.start()
        self.started.emit()
        self._log.info("[Cam] Kamera adaptörü başlatıldı (orchestrator mode).")

    def stop(self):
        # Reader’ı durdur
        if self._stop_evt:
            try: self._stop_evt.set()
            except Exception: pass

        try:
            if self._startup_timeout_timer and self._startup_timeout_timer.isActive():
                self._startup_timeout_timer.stop()
        except Exception:
            pass

        # AI’yı durdur
        self._stop_ai_process()

        if self._wait_tmr is None:
            self._wait_tmr = QTimer(self)
            self._wait_tmr.setInterval(100)
            self._wait_tmr.setSingleShot(False)
            self._wait_tmr.timeout.connect(self._check_proc_end)

        self._wait_elapsed = 0
        self._wait_tmr.start()

        self._poll.stop()
        self._log.info("[Cam] Kamera sürecinin kapanması bekleniyor…")

    def _stop_ai_process(self):
        try:
            if self._pose_stop_evt:
                self._pose_stop_evt.set()
        except Exception:
            pass
        # join
        try:
            if self._ai_proc and self._ai_proc.is_alive():
                self._ai_proc.join(timeout=0.5)
        except Exception:
            pass
        # terminate fallback
        try:
            if self._ai_proc and self._ai_proc.is_alive():
                self._ai_proc.terminate()
        except Exception:
            pass
        self._ai_proc = None
        self._pose_in_q = None
        self._pose_out_q = None
        self._pose_stop_evt = None
        # bir kere loglama hafızasını temizle
        self._pose_logged_by_track.clear()
        self._pose_last_seen.clear()
        self._last_ai_send_ts = 0.0

    def _on_startup_timeout(self):
        if self._first_frame_seen:
            return
        if self._proc and self._proc.is_alive():
            self._log.error("[Cam] Kamera başlatma zaman aşımına uğradı (20s).")
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
            try: self._proc.terminate()
            except Exception: pass
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

    @staticmethod
    def _label_of(cid: int) -> Optional[str]:
        if cid == 0: return "T-POSE"
        if cid == 1: return "ARMS-UP"
        return None

    def _apply_once_logging(self, dtos: List[Dict[str, Any]]):
        now = time.time()
        # TTL temizliği
        to_del = [tid for tid, ts in self._pose_last_seen.items() if now - ts > self._pose_log_ttl_sec]
        for tid in to_del:
            self._pose_last_seen.pop(tid, None)
            self._pose_logged_by_track.pop(tid, None)

        # Yeni sonuçlar
        for d in dtos:
            tid = int(d["track_id"])
            cid = int(d["class_id"])
            lbl = d.get("label")
            cf  = float(d.get("conf", 0.0))
            self._pose_last_seen[tid] = now
            if lbl is None or cf < self._pose_conf_thr:
                continue
            done = self._pose_logged_by_track.setdefault(tid, set())
            if lbl not in done:
                if lbl == "T-POSE":
                    msg = f"T-Pose tespit edildi, ilk yardım kiti bekleyen kişi saptandı! (track={tid}, conf={cf:.2f})"
                else:
                    msg = f"Arms-Up tespit edildi, ilk yardım kiti bekleyen kişi saptandı! (track={tid}, conf={cf:.2f})"
                try: self._log.warning(msg)
                except Exception: pass
                done.add(lbl)

    def _maybe_send_to_ai(self, frame) -> None:
        if not self._pose_enabled or self._pose_in_q is None:
            return
        now = time.time()
        if (now - self._last_ai_send_ts) < self._pose_min_interval:
            return
        # En taze kalsın
        if self._pose_in_q.full():
            try: self._pose_in_q.get_nowait()
            except Exception: pass
        try:
            self._pose_in_q.put_nowait(frame)
            self._last_ai_send_ts = now
        except Exception:
            pass

    def _poll_q(self):
        if self._reason_q is not None:
            while True:
                try:
                    reason = self._reason_q.get_nowait()
                except pyqueue.Empty:
                    break
                except Exception:
                    break
                else:
                    try:
                        self.failed.emit(str(reason))
                    finally:
                        self.stop()
                        return

        # 2) Reader çökmüşse ve kare yoksa: failed
        if self._proc and (not self._proc.is_alive()) and self._q and self._q.empty():
            self._poll.stop()
            self.failed.emit("Kamera süreci bitti")
            return

        # 3) FRAME KUYRUĞU: en son kareyi al
        last = None
        if self._q is not None:
            while True:
                try:
                    item = self._q.get_nowait()
                    last = item
                except pyqueue.Empty:
                    break
                except Exception:
                    break

        if last is not None:
            if (self._startup_timeout_timer is not None) and self._startup_timeout_timer.isActive():
                self._startup_timeout_timer.stop()
            self._first_frame_seen = True

            # UI'ya yolla
            self.new_frame.emit(last)

            # AI'ya zaman tabanlı yolla
            try:
                self._maybe_send_to_ai(last)
            except Exception:
                pass

        # 4) AI ÇIKIŞ KUYRUĞU: en son DTO listesini al ve yay
        if self._pose_out_q is not None:
            last_dtos = None
            while True:
                try:
                    dtos = self._pose_out_q.get_nowait()
                    last_dtos = dtos
                except pyqueue.Empty:
                    break
                except Exception:
                    break

            if last_dtos is not None:
                # Bir kere loglama
                try: self._apply_once_logging(last_dtos)
                except Exception: pass
                # UI’ya yay
                try: self.pose_results.emit(last_dtos)
                except Exception: pass
