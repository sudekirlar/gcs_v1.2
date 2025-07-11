# adapters/ui/controllers/connection_controller.py

from PyQt5.QtCore import QObject, pyqtSlot
from PyQt5.QtSerialPort import QSerialPortInfo

class ConnectionController(QObject):
    def __init__(self, combo, button, status_edit, core, logger, parent=None, close_button=None):
        super().__init__(parent)
        self._combo, self._button = combo, button
        self._status, self._core, self._logger = status_edit, core, logger
        self._close_btn = close_button

        self._populate_ports()
        button.clicked.connect(self._on_click)
        if self._close_btn:
            self._close_btn.clicked.connect(self._on_disconnect)
        core.connection_opened.connect(self._opened)
        core.connection_failed.connect(self._failed)
        core.connection_closed.connect(self._closed)

    def _populate_ports(self):
        self._combo.clear()
        for p in QSerialPortInfo.availablePorts():
            self._combo.addItem(p.portName())
        self._combo.addItem("TCP (SITL)")

    @pyqtSlot()
    def _on_click(self):
        descr = self._combo.currentText()
        self._status.append(f"Bağlanıyor… ({descr})")
        self._logger.info(f"Kullanıcı bağlanıyor: {descr}")
        self._core.connect(descr)

    @pyqtSlot()
    def _on_disconnect(self):
        self._status.append("Bağlantı kapatılıyor…")
        self._logger.info("Kullanıcı bağlantıyı kapatıyor")
        self._core.disconnect()

    @pyqtSlot(str)
    def _opened(self, descr):
        self._status.append(f"Bağlantı başarılı ({descr})")
        self._logger.info(f"Bağlantı açıldı: {descr}")

    @pyqtSlot(str)
    def _failed(self, reason):
        self._status.append(f"Bağlantı başarısız: {reason}")
        self._logger.error(f"Bağlantı hatası: {reason}")

    @pyqtSlot(str)
    def _closed(self, reason):
        self._status.append(f"Bağlantı kapandı: {reason}")
        self._logger.warning(f"Bağlantı kapandı: {reason}")
