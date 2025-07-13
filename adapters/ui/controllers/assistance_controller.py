from PyQt5 import QtWidgets, QtGui

from adapters.ui.request_listener_worker import RequestListenerWorker

from core.assistance_request import AssistanceRequest

class AssistanceController:
    def __init__(self, ui, parent=None):
        self._ui = ui
        self._worker = RequestListenerWorker(parent)
        self._worker.newReq.connect(self._on_new_req)
        self._worker.start()

    def _on_new_req(self, req: AssistanceRequest):
        # Form alanlarını güncelle
        self._ui.tcLineEdit.setText(req.tc)
        self._ui.needLineEdit.setText(req.need)
        self._ui.latLineEdit.setText(f"{req.lat:.6f}")
        self._ui.lonLineEdit.setText(f"{req.lon:.6f}")

        # Listeye ekle
        txt = f"{req.tc} | {req.need} | ({req.lat:.5f}, {req.lon:.5f})"
        item = QtWidgets.QListWidgetItem(txt)
        item.setForeground(QtGui.QColor("cyan"))
        self._ui.requestListWidget.addItem(item)
