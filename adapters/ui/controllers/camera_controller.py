# adapters/ui/controllers/camera_controller.py
"""
UI ► CameraController ◄ CameraCore
• Comboları doldurur, Aç/Kapat butonlarını yönetir
• new_frame’de QLabel’e FPS + ms overlay’li görüntü basar
• Pose sonuçlarını alır, kutu + etiket çizer (T-POSE: kırmızı, ARMS-UP: turuncu)
• OPTIMIZATION:
    1) Per-tracker eskime: Her track_id için 'last_seen' tutulur; taze olmayan kutu çizilmez.
    2) Smoothing sırası: Önce QLabel koordinatına map, sonra OneEuro ile yumuşat.
"""

import time, math
from collections import deque
from typing import Dict, List, Tuple, Optional

import numpy as np
from PyQt5.QtCore import QObject, pyqtSlot, Qt
from PyQt5.QtGui  import QImage, QPixmap, QPainter, QFont, QPen, QColor

from config.settings import Settings

# ---- Renk/Pen ----
ColorRed    = QColor(255, 0, 0)
ColorOrange = QColor(255, 165, 0)
ColorGrey   = QColor(180, 180, 180)
PenRed    = QPen(ColorRed, 2)
PenOrange = QPen(ColorOrange, 2)
PenGrey   = QPen(ColorGrey, 2)

# ===================== OneEuro (UI smoothing) =====================
class _OneEuro:
    @staticmethod
    def _alpha(cutoff: float, freq: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        te  = 1.0 / max(1e-6, freq)
        return 1.0 / (1.0 + tau / te)

    def __init__(self, freq=30.0, mincutoff=1.0, beta=0.007, dcutoff=1.0):
        self.freq=freq; self.mincutoff=mincutoff; self.beta=beta; self.dcutoff=dcutoff
        self._xp=None; self._dx=0.0; self._tp=None

    def __call__(self, x: float, t: float) -> float:
        if self._tp is None:
            self._tp=t; self._xp=float(x); self._dx=0.0
            return float(x)
        dt = max(1e-6, t - self._tp)
        self.freq = 1.0 / dt
        dx = (x - self._xp) * self.freq
        a_d = self._alpha(self.dcutoff, self.freq)
        self._dx = a_d * dx + (1.0 - a_d) * self._dx
        cutoff = self.mincutoff + self.beta * abs(self._dx)
        a = self._alpha(cutoff, self.freq)
        xh = a * x + (1.0 - a) * self._xp
        self._xp = xh; self._tp = t
        return float(xh)

class _BBoxSmoother:
    """
    track-id başına (x,y,w,h) için OneEuro filtreleri.
    DİKKAT: QLabel koordinat sisteminde çalışır (UI-space smoothing).
    """
    def __init__(self, mincutoff: float = 1.0, beta: float = 0.007):
        self._mincut = float(mincutoff)
        self._beta   = float(beta)
        self._state: Dict[int, Dict[str, _OneEuro]] = {}
        self._last_seen: Dict[int, float] = {}

    def smooth_label_space(self, tid: int, lbbox: Tuple[float,float,float,float], now: float) -> Tuple[int,int,int,int]:
        st = self._state.get(tid)
        if st is None:
            st = {
                "x": _OneEuro(mincutoff=self._mincut, beta=self._beta),
                "y": _OneEuro(mincutoff=self._mincut, beta=self._beta),
                "w": _OneEuro(mincutoff=self._mincut, beta=self._beta),
                "h": _OneEuro(mincutoff=self._mincut, beta=self._beta),
            }
            self._state[tid] = st
        self._last_seen[tid] = now
        x, y, w, h = map(float, lbbox)
        xs = st["x"](x, now); ys = st["y"](y, now)
        ws = st["w"](w, now); hs = st["h"](h, now)
        return int(round(xs)), int(round(ys)), int(round(ws)), int(round(hs))

    def gc(self, now: float, ttl_sec: float = 8.0):
        stale = [tid for tid, ts in self._last_seen.items() if now - ts > ttl_sec]
        for tid in stale:
            self._last_seen.pop(tid, None)
            self._state.pop(tid, None)

# ===================== Controller =====================
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
    # ------------------------------
    def __init__(self, ui_widgets: Dict[str, object], core, settings: Settings, parent=None):
        super().__init__(parent)
        self._ui   = ui_widgets
        self._core = core
        self._cfg  = settings

        self._populate_combos()

        # UI olayları
        self._ui['open_btn' ].clicked.connect(self._on_open)
        self._ui['close_btn'].clicked.connect(self._core.stop_camera)

        # Core olayları
        self._core.camera_started.connect(self._on_started)
        self._core.camera_stopped.connect(self._on_stopped)
        self._core.camera_failed .connect(self._on_failed)

        # Pose sonuçları
        try:
            self._core.camera_pose_results.connect(self.on_pose_results)
        except Exception:
            pass

        # FPS ölçümü
        self._ts_hist = deque(maxlen=30)
        self._last_ts = None

        # --- Per-tracker pose cache ---
        # track_id -> DTO (içine 'last_seen' eklenecek)
        self._pose_cache: Dict[int, Dict] = {}
        self._pose_stale_max_sec: float = 0.40  # 400 ms: “takılı kalma”yı pratikte bitirir

        # UI-space bbox smoother
        self._bbox_smoother = _BBoxSmoother(mincutoff=1.0, beta=0.007)

    # ------------------------------
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

        # Pose state reset
        if not running:
            self._pose_cache.clear()
            # Smoother state'ini de yumuşak bir reset ile temizleyelim
            try:
                self._bbox_smoother.gc(time.time(), ttl_sec=0.0)
            except Exception:
                pass

    # ------------------------------ Pose sinyali (Per-tracker hafıza)
    @pyqtSlot(object)
    def on_pose_results(self, detections: object):
        """
        detections: List[PoseDetectionDTO] (dict)
        DTO: {track_id, class_id, label, bbox:(x,y,w,h), conf, ts}
        """
        now = time.time()
        if not isinstance(detections, list):
            return

        # 1) Gelen taze bilgileri cache'e işle
        for d in detections:
            try:
                tid = d.get("track_id", None)
                if tid is None:
                    continue
                tid = int(tid)

                # DTO'ya UI-zamanlı last_seen ekle
                d = dict(d)  # kopya al (yan etkisiz)
                d["last_seen"] = now
                self._pose_cache[tid] = d
            except Exception:
                # tek bir bozuk DTO tüm listeyi bozmasın
                continue

        # 2) Çok uzun süredir hiç gelmeyenleri cache'ten süpür (opsiyonel; bellek koruma)
        try:
            old_ids = [tid for tid, data in self._pose_cache.items() if (now - data.get("last_seen", 0.0)) > 10.0]
            for tid in old_ids:
                self._pose_cache.pop(tid, None)
        except Exception:
            pass

    # ------------------------------ Yardımcı: frame→QLabel mapping (float)
    @staticmethod
    def _map_bbox_to_label_float(
        bbox: Tuple[int,int,int,int],
        frame_wh: Tuple[int,int],
        label_wh: Tuple[int,int]
    ) -> Optional[Tuple[float,float,float,float]]:
        x, y, w, h = bbox
        w0, h0 = frame_wh
        W, H   = label_wh
        if w0 <= 0 or h0 <= 0 or W <= 0 or H <= 0:
            return None
        # KeepAspectRatioByExpanding
        s = max(W / float(w0), H / float(h0))
        scaled_w = w0 * s
        scaled_h = h0 * s
        x_off = (scaled_w - W) * 0.5
        y_off = (scaled_h - H) * 0.5
        x_p = x * s - x_off
        y_p = y * s - y_off
        w_p = w * s
        h_p = h * s
        return (float(x_p), float(y_p), float(w_p), float(h_p))

    # ------------------------------ Ana çizim
    @pyqtSlot(object)
    def update_display(self, frame: np.ndarray):
        if frame is None:
            return

        # ----- FPS -----
        now = time.time()
        if self._last_ts is not None:
            self._ts_hist.append(now - self._last_ts)
        self._last_ts = now
        if self._ts_hist:
            avg_dt = sum(self._ts_hist) / len(self._ts_hist)
            fps = 1.0 / avg_dt if avg_dt > 1e-9 else 0.0
            ms  = avg_dt * 1000.0
        else:
            fps = ms = 0.0

        # ----- QPixmap -----
        h0, w0, ch = frame.shape
        img = QImage(frame.data, w0, h0, ch * w0, QImage.Format_RGB888).rgbSwapped()
        pix = QPixmap.fromImage(img)

        # ----- QLabel crop (KeepAspectRatioByExpanding) -----
        lbl_size = self._ui['display_label'].size()
        W, H = lbl_size.width(), lbl_size.height()
        scaled = pix.scaled(lbl_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x_off = (scaled.width() - W) // 2
        y_off = (scaled.height() - H) // 2
        cropped = scaled.copy(x_off, y_off, W, H)

        # ----- Çizim -----
        painter = QPainter(cropped)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setFont(QFont("Consolas", 10, QFont.Bold))

        # FPS overlay (sol üst, gölgeli)
        txt = f"{fps:4.0f} fps  {ms:3.0f} ms"
        painter.setPen(QPen(QColor(0, 0, 0), 2)); painter.drawText(6, 16, txt)
        painter.setPen(Qt.white);                 painter.drawText(5, 15, txt)

        # ----- Pose çizimi (Per-tracker eskime + UI-space smoothing) -----
        try:
            # 1) Çizilecek taze kutuları topla
            to_draw: List[Dict] = []
            for tid, data in self._pose_cache.items():
                last_seen = float(data.get("last_seen", 0.0))
                if (now - last_seen) <= self._pose_stale_max_sec:
                    to_draw.append(data)

            if to_draw:
                # GC: uzun süredir görünmeyeni temizle (smoother tarafı)
                self._bbox_smoother.gc(now, ttl_sec=8.0)

                # 2) Taze olanları çiz
                for d in to_draw:
                    cid  = int(d.get("class_id", -1))
                    bbox = d.get("bbox", None)
                    label = d.get("label", None)
                    tid  = int(d.get("track_id", -1))
                    conf = float(d.get("conf", 0.0))
                    if bbox is None or label is None or tid < 0:
                        continue

                    # (A) Önce QLabel koordinatına map'le (float)
                    mapped = self._map_bbox_to_label_float(tuple(bbox), (w0, h0), (W, H))
                    if mapped is None:
                        continue

                    # (B) Sonra UI-space OneEuro smoothing uygula
                    mx, my, mw, mh = self._bbox_smoother.smooth_label_space(tid, mapped, now)

                    # Renk seçimi
                    if cid == 0:   painter.setPen(PenRed)
                    elif cid == 1: painter.setPen(PenOrange)
                    else:          painter.setPen(PenGrey)

                    # Kutuyu çiz
                    painter.drawRect(mx, my, mw, mh)

                    # Etiket
                    text = f"{label} {conf:.2f}"
                    tx, ty = mx, max(14, my - 6)
                    painter.setPen(QPen(QColor(0,0,0), 3)); painter.drawText(tx+1, ty+1, text)
                    painter.setPen(Qt.white);               painter.drawText(tx, ty, text)
            # else: taze yoksa overlay çizme (doğal sönüm)
        except Exception:
            # UI’yi kilitlemeyelim; hata ayıklamada loglayabilirsin.
            pass

        painter.end()
        self._ui['display_label'].setPixmap(cropped)
