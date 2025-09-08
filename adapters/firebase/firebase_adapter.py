# adapters/firebase/firebase_adapter.py
from __future__ import annotations
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from firebase_admin import db

from core.assistance_request import AssistanceRequest
from core.ports.logger_port   import ILoggerPort

class _FirebaseWorker(QObject):
    new_req = pyqtSignal(AssistanceRequest) # Firebase'den geçerli bir yardım talebi geldiğinde, bu sinyali bir AssistanceRequest nesnesi ile birlikte yayınlar.
    err     = pyqtSignal(str)

    def __init__(self, path: str, log: ILoggerPort):
        super().__init__()
        self._path   = path
        self._log    = log
        self._ref    = db.reference(path)
        self._stream = None

    # -------- thread entry ---------------------------------------------------
    @pyqtSlot()
    def run(self):
        try:
            self._log.info(f"Dinleme başlatıldı: {self._path}")
            # Bu fonksiyon, Firebase Realtime Database'e kalıcı bir bağlantı açar ve veri değişikliklerini dinlemeye başlar.
            # Bu bir blocking işlemdir; yani programın akışı bu satırda durur ve _stream kapatılana kadar ilerlemez.
            # Eğer bu ana thread'de olsaydı, tüm uygulama donardı.
            self._stream = self._ref.listen(self._listener)   #  blocking
        except Exception as e:
            if "cannot create new thread at interpreter shutdown" not in str(e):
                self.err.emit(str(e))
        self._log.info("Firebase dinleyici run() sona erdi")   #  <<<

    @pyqtSlot()
    def stop(self):
        self._log.info("Firebase dinleyici stream'i kapatılıyor...")
        if self._stream:
            try:
                self._stream.close()
                self._log.info("Firebase stream başarıyla kapatıldı.")
            except Exception as e:
                self.err.emit(f"Firebase stream kapatılırken hata: {e}")
            finally:
                self._stream = None

    # Firebase veritabanında bir değişiklik olduğunda, Firebase kütüphanesi bu metodu otomatik olarak çağırır.
    def _listener(self, ev):
        if ev.data in (None, {}, []):
            return
        try:
            if ev.path == "/":
                self._emit_if_ok(ev.data)
            else:
                self._emit_if_ok(self._ref.get())
        except Exception as e:
            self._log.warning(f"Olay işlenemedi: {e}")

    # Eğer tüm gerekli alanlar (tc, durum ve konum) mevcutsa,
    # bir AssistanceRequest nesnesi oluşturur ve new_req sinyalini yayınlayarak bu yeni talebi ana thread'e bildirir.
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

class FirebaseAdapter(QObject):
    new_request = pyqtSignal(AssistanceRequest)
    error       = pyqtSignal(str)
    finished    = pyqtSignal()
    _stop_worker = pyqtSignal()

    def __init__(self, path: str, log: ILoggerPort, *, clear_on_start: bool = False):
        super().__init__()
        self._log = log

        if clear_on_start:
            try:
                db.reference(path).delete()
                log.info(f"{path} düğümü temizlendi")
            except Exception as e:
                log.warning(f"{path} temizlenemedi: {e}")

        # Bir QThread ve bir _FirebaseWorker oluşturulur.
        # moveToThread ile worker arka plan thread'ine taşınır.
        # Worker'ın sinyalleri (new_req, err) adapter'ın genel sinyallerine (new_request, error) bağlanır.
        # Adapter'ın stop() metodundan gelen sinyal, worker'ın stop() slotuna bağlanır.
        # Thread'in started sinyali, worker'ın run metodunu tetikleyecek şekilde ayarlanır ve thread başlatılır.
        self._t = QThread(self)
        self._w = _FirebaseWorker(path, log)
        self._w.moveToThread(self._t)

        self._w.new_req.connect(self.new_request)
        self._w.err.connect(self.error)

        self._stop_worker.connect(self._w.stop)
        self._t.finished.connect(self._w.deleteLater)
        self._t.finished.connect(self.finished)

        self._t.started.connect(self._w.run)
        self._t.start()

    def stop(self):
        if self._t and self._t.isRunning():
            self._log.info("Firebase dinleyici thread'ine durma komutu gönderiliyor.")
            self._stop_worker.emit()   # stream kapat
            self._t.quit()             # event-loop'u bitir
        else:
            self.finished.emit()       # zaten durmuşsa
