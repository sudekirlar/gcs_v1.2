# adapters/ui/controllers/command_controller.py

from PyQt5.QtCore import QObject, pyqtSlot


class CommandController(QObject):
    """
    UI → Core köprüsü.  Core’u dinler, status paneline yazar.
    UI, adapter katmanını hiç görmez.
    """
    def __init__(self, ui, core, logger, parent=None):
        super().__init__(parent)
        self._ui, self._core, self._logger = ui, core, logger

        # --- UI sinyalleri doğrudan Core metotlarına bağlanıyor ---
        ui.arm_pushButton.clicked.connect(core.arm)
        ui.disarm_pushButton.clicked.connect(core.disarm)
        ui.land_pushButton.clicked.connect(core.land)
        ui.takeOff_pushButton.clicked.connect(self._takeoff)
        ui.changeMode_pushButton.clicked.connect(self._set_mode)

        # --- ACK geri bildirimi ---
        core.command_ack_received.connect(self._ack_status)

    # -------------------- helpers --------------------
    @pyqtSlot()
    def _takeoff(self):
        try:
            alt = float(self._ui.altitudeLineEdit.text())
        except ValueError:
            alt = 2.5      # varsayılan güvenli irtifa
        self._logger.info(f"Kullanıcı TAKEOFF istedi: {alt} m")
        self._core.takeoff(alt)

    @pyqtSlot()
    def _set_mode(self):
        mode = self._ui.mode_comboBox.currentText()
        self._logger.info(f"Kullanıcı mod değiştirmek istedi: {mode}")
        self._core.set_mode(mode)

    # -------------------- ACK UI feedback --------------------
    @pyqtSlot(str, int)
    def _ack_status(self, cmd: str, result: int):
        txt = "kabul" if result == 0 else f"REDDİ ({result})"
        self._ui.currentState_textEdit_2.append(f"{cmd} → {txt}")
