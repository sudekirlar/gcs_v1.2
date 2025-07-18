from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from firebase_admin import db

from core.assistance_request import AssistanceRequest
from core.ports.logger_port  import ILoggerPort


# ------------------------------------------------------------------
# Worker (dinleyici) ------------------------------------------------
# ------------------------------------------------------------------
class _FirebaseWorker(QObject):
    new_req = pyqtSignal(AssistanceRequest)
    err     = pyqtSignal(str)

    def __init__(self, path: str, log: ILoggerPort):
        super().__init__()
        self._path = path
        self._log  = log
        self._ref  = db.reference(path)

    # -------- thread entry --------
    @pyqtSlot()
    def run(self):
        try:
            self._log.info(f"Dinleme başlatıldı: {self._path}")
            self._ref.listen(self._listener)
        except Exception as e:
            self.err.emit(str(e))

    # -------- listener --------
    def _listener(self, ev):
        if ev.data in (None, {}, []):
            return
        try:
            # Kök veri (ilk bağlantı) → tek seferde işle
            if ev.path == "/":
                self._emit_if_ok(ev.data)
            else:
                # Alt alan güncellendi: güncel kaydın tamamını oku
                self._emit_if_ok(self._ref.get())
        except Exception as e:
            self._log.warning(f"Olay işlenemedi: {e}")

    # -------- helper --------
    def _emit_if_ok(self, d: dict):
        if not all(k in d for k in ("tc", "durum", "konum")):
            return
        loc = d["konum"]
        if not all(k in loc for k in ("lat", "lon")):
            return

        req = AssistanceRequest(
            tc    = str(d["tc"]),
            lat   = float(loc["lat"]),
            lon   = float(loc["lon"]),
            durum = str(d["durum"]),
        )
        self.new_req.emit(req)


# ------------------------------------------------------------------
# Adapter (port implementasyonu) -----------------------------------
# ------------------------------------------------------------------
class FirebaseAdapter(QObject):
    """
    clear_on_start=True → dinleme başlatılmadan önce belirtilen path'i siler.
    """
    new_request = pyqtSignal(AssistanceRequest)
    error       = pyqtSignal(str)

    def __init__(self, path: str, log: ILoggerPort, *, clear_on_start: bool = False):
        super().__init__()
        self._path = path
        self._log  = log

        # --- Worker thread ---
        self._t = QThread(self)
        self._w = _FirebaseWorker(path, log)
        self._w.moveToThread(self._t)

        self._w.new_req.connect(self.new_request)
        self._w.err.connect(self.error)

        # Başlamadan önce düğümü temizle (isteğe bağlı)
        def _start():
            if clear_on_start:
                try:
                    db.reference(path).delete()
                    log.info(f"{path} düğümü temizlendi")
                except Exception as e:
                    log.warning(f"{path} temizlenemedi: {e}")
            self._w.run()

        self._t.started.connect(_start)
        self._t.start()

    # ----------------------------------------------------------------
    def stop(self):
        if self._t.isRunning():
            self._t.quit()
            self._t.wait()
