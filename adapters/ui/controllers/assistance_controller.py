from PyQt5.QtCore import QObject
from core.assistance_request import AssistanceRequest
from adapters.logging.logger_adapter import LoggerAdapter

class AssistanceController(QObject):
    """
    Sadece Core’dan gelen sinyali dinler; kendi FirebaseAdapter’ı yok.
    """
    def __init__(self, ui, logger: LoggerAdapter, parent=None):
        super().__init__(parent)
        self._ui = ui
        self._log = logger
        # RequestListenerWorker satırları **tamamen silindi**

    # -------- slot --------
    def on_request(self, r: AssistanceRequest):
        text = (f"TC      : {r.tc}\n"
                f"Durum   : {r.durum}\n"
                f"Konum   : ({r.lat:.5f}, {r.lon:.5f})\n")
        self._ui.mobileBox_textEdit.append(text)   # birikmeli yaz
