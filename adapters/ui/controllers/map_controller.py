# adapters/ui/controllers/map_controller.py
from pathlib import Path
import json, time
from PyQt5.QtCore       import QObject, pyqtSlot, QTimer, QUrl
from PyQt5.QtWebChannel import QWebChannel


def locate_map_html():
    cur = Path(__file__).resolve().parent
    for _ in range(8):
        p = cur / "map" / "map.html"
        if p.exists():
            return p
        cur = cur.parent
    raise FileNotFoundError("map/map.html bulunamadı")


class MapController(QObject):
    def __init__(self, map_widget, core, logger, parent=None):
        super().__init__(parent)
        self._v = map_widget
        self._log = logger
        self._pg  = self._v.page()
        self._pending = {}
        self._last_known_pos = {}  # Drone'un son bilinen pozisyonunu kalıcı olarak tutar

        ch = QWebChannel(self._pg); ch.registerObject("backend", self)
        self._pg.setWebChannel(ch)

        self._t = QTimer(self, interval=80, singleShot=True)
        self._t.timeout.connect(self._flush)
        core.telemetry_updated.connect(self._on_tel)

        html = locate_map_html()
        self._v.load(QUrl.fromLocalFile(str(html)))
        self._log.info(f"[Map] {html}")

    # ------------ Core → JS ------------
    @pyqtSlot(dict)
    def _on_tel(self, d):
        # Hem geçici listeyi hem de kalıcı son durumu güncelle
        new_data = {k: d[k] for k in ('lat', 'lon', 'yaw') if k in d}
        self._pending.update(new_data)
        self._last_known_pos.update(new_data)  # Kalıcı durumu da güncelle
        if not self._t.isActive(): self._t.start()

    def _flush(self):
        if {'lat','lon'}.issubset(self._pending):
            self._pg.runJavaScript(f"updateDrone({json.dumps(self._pending)})")
        self._pending.clear()

    # ------------ UI API ---------------
    def add_marker_here(self):
        lat = self._last_known_pos.get('lat')
        lon = self._last_known_pos.get('lon')

        if lat is None or lon is None:
            self._log.warning("[Map] Konum yok – marker eklenmedi"); return
        mkid = f"mk_{int(time.time())}"
        self._pg.runJavaScript(f"addMarker({lon}, {lat}, '{mkid}')")

    def add_marker(self, lat: float, lon: float, mkid: str = ""):
        """Haritaya marker ekler mobilden gelen konum"""
        if not mkid:
            mkid = f"mk_{int(time.time())}"
        self._pg.runJavaScript(f"addMarker({lon}, {lat}, '{mkid}')")

    def clear_markers(self):
        self._pg.runJavaScript("clearMarkers()")

    def clear_path(self):
        self._pg.runJavaScript("clearPolyline()")

    def recenter_and_follow(self):
        self._pg.runJavaScript("recenterAndFollow()")

    # -------- DEMO tetikleyici -------------------------
    def start_demo(self):
        """HOME etrafında daire çizer (JS tarafı)."""
        self._pg.runJavaScript("startDemoFlight()")