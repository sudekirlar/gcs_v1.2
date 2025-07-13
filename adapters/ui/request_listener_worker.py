from PyQt5.QtCore import QObject, pyqtSignal, QThread
from adapters.firebase.request_stream_adapter import FirebaseRequestStreamAdapter
from core.assistance_request import AssistanceRequest

class RequestListenerWorker(QObject):
    newReq = pyqtSignal(object)          # Qt için genel Python objesi

    def __init__(self, parent=None):
        super().__init__(None)           # ① parent'ı None bırak
        self._stream = FirebaseRequestStreamAdapter("/mobil")

    def _run(self):
        self._stream.subscribe(self.newReq.emit)  # BLOKLAYICI DEĞİL

    def start(self):
        th = QThread()                   # ② parent vermiyoruz
        th.started.connect(self._run)
        th.start()
        self._thread = th                # ③ referansı sakla
