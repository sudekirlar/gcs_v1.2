# adapters/ui/controllers/map_controller.py
from pathlib import Path
import json, time
from PyQt5.QtCore       import QObject, pyqtSlot, QTimer, QUrl
from PyQt5.QtWebChannel import QWebChannel

# Python'dan JavaScript'e giderken runJavaScript metodunu kullanarak Python'dan JavaScript fonksiyonlarını doğrudan çağırabiliyoruz. Drone konumu veya marker ekleme gibi komutları bu yolla gönderiyoruz.
# JavaScript'ten Python'a QWebChannel'ı kullandık. Python'daki MapController nesnemizi JavaScript'e backend adıyla kaydettik.

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
        self._pg  = self._v.page() # web sayfasının kendisiyle iletişime geçmek için kullanılır.
        self._pending = {}
        self._last_known_pos = {}  # Drone'un son bilinen pozisyonunu kalıcı olarak tutar.

        # Aşağıdaki satır, MapController'ın kendisini (self) JavaScript tarafına backend ismiyle tanıtır.
        # Artık JavaScript kodu, qt.webChannelTransport.objects.backend üzerinden
        # bu Python nesnesinin @pyqtSlot ile işaretlenmiş metodlarını çağırabilir.
        ch = QWebChannel(self._pg); ch.registerObject("backend", self)
        self._pg.setWebChannel(ch)

        self._t = QTimer(self, interval=80, singleShot=True)
        self._t.timeout.connect(self._flush)
        core.telemetry_updated.connect(self._on_tel)
        core.mobile_request_added.connect(self.on_mobile_request)

        html = locate_map_html()
        self._v.load(QUrl.fromLocalFile(str(html)))
        self._log.info(f"[Map] {html}")

    # ------------ Core → JS ------------
    @pyqtSlot(dict)
    def _on_tel(self, d):
        # Lat, lon, alt için telemetri tarafına bakıyoruz.
        new_data = {k: d[k] for k in ('lat', 'lon', 'yaw') if k in d}
        self._pending.update(new_data)
        self._last_known_pos.update(new_data)
        if not self._t.isActive(): self._t.start()

    def _flush(self):
        if {'lat','lon'}.issubset(self._pending):
            self._pg.runJavaScript(f"updateDrone({json.dumps(self._pending)})") # JSON formatı, 80ms'de bir güncelleme atar. (Throttling)
        self._pending.clear()

    # ------------ UI API ---------------
    def add_marker_here(self):
        lat = self._last_known_pos.get('lat')
        lon = self._last_known_pos.get('lon')

        if lat is None or lon is None:
            self._log.warning("[Map] Konum yok – marker eklenmedi"); return
        mkid = f"mk_{int(time.time())}"
        self._pg.runJavaScript(f"addMarker({lon}, {lat}, '{mkid}')")

    # Mobil istek, haritaya özel ikonlu marker ekle
    @pyqtSlot(object)  # AssistanceRequest
    def on_mobile_request(self, r):
        try:
            mkid = f"mob_{r.tc}_{int(time.time())}"
            # JS: addMobileMarker(lon, lat, id)
            self._pg.runJavaScript(
                f"addMobileMarker({float(r.lon)}, {float(r.lat)}, '{mkid}')"
            )
            self._log.info(f"[Map] Mobil marker eklendi: {mkid}")
        except Exception as e:
            self._log.warning(f"[Map] Mobil marker eklenemedi: {e}")

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