# adapters/ui/controllers/command_controller.py

from PyQt5.QtCore import QObject, pyqtSlot

def _html_line(text: str, color: str = "#222", bold: bool = False) -> str:
    b1, b2 = ("<b>", "</b>") if bold else ("", "")
    return f'<span style="color:{color}">{b1}{text}{b2}</span><br/>'

class CommandController(QObject):
    COLOR_OK = "#ffd1dc"       # yeşil
    COLOR_ERR = "#c62828"      # kırmızı
    COLOR_INFO = "#fde910"     # mavi
    COLOR_WARN = "#ef6c00"     # turuncu
    COLOR_TEXT = "#fffff0"     # siyah-gri

    def __init__(self, ui, core, logger, parent=None):
        super().__init__(parent)
        self._ui, self._core, self._logger = ui, core, logger

        # Komutları core'a bağlıyoruz. Aşağıdakiler direkt gidenler. Bazıları için bazı tanımlamalar vermek gerektiği için önce kurallarını vereceğimiz metotları koyalım.
        ui.arm_pushButton.clicked.connect(core.arm)
        ui.disarm_pushButton.clicked.connect(core.disarm)
        ui.land_pushButton.clicked.connect(core.land)
        ui.takeOff_pushButton.clicked.connect(self._takeoff)
        ui.changeMode_pushButton.clicked.connect(self._set_mode)
        ui.loadMission_pushButton.clicked.connect(self._start_mobile_interrupt)

        # ACK alma.
        core.command_ack_received.connect(self._ack_status)

        self._append_status("Sistem hazır.", self.COLOR_INFO)

    @pyqtSlot()
    def _takeoff(self):
        try:
            alt = float(self._ui.altitudeLineEdit.text())
        except ValueError:
            alt = 2.5      # Varsayılan irtifa.
        self._logger.info(f"Kullanıcı TAKEOFF istedi: {alt} m")
        self._core.takeoff(alt)

    @pyqtSlot()
    def _set_mode(self):
        mode = self._ui.mode_comboBox.currentText()
        self._logger.info(f"Kullanıcı mod değiştirmek istedi: {mode}")
        self._core.set_mode(mode)

    @pyqtSlot()
    def _start_mobile_interrupt(self):
        req = self._core._latest_mobile_req
        if not req:
            self._logger.warning("Mobil istek yok")
            self._append_status("Mobil istek yok.", self.COLOR_WARN)
            return
        self._logger.info("Kullanıcı: Görevi kes – mobil hedefe git")
        self._append_status("Görev kesiliyor → Mobil GUIDED başlatılıyor…", self.COLOR_INFO)
        self._core.interrupt_mission_for_request(req)

    @pyqtSlot(str, int)
    def _ack_status(self, cmd, res):
        # Ok/hata belirleme. 0 ise başarılıdır.
        is_mission_ack = (cmd == "MISSION_ACK")
        ok = (res == 0)

        # Metinlerini verelim.
        if is_mission_ack:
            txt_map = {0: "ACCEPTED", 1: "ERROR", 2: "UNSUPPORTED", 3: "NO_SPACE"}
            txt = txt_map.get(res, f"CODE {res}")
        else:
            txt = "OK" if res == 0 else f"Hata({res})"

        if cmd in ("MAV_CMD_DO_SET_SERVO", "SET_SERVO"):
            color = self.COLOR_OK if ok else self.COLOR_ERR
            label = "SET_SERVO"
        elif cmd in ("MAV_CMD_NAV_WAYPOINT",):
            color = self.COLOR_OK if ok else self.COLOR_ERR
            label = "GOTO"
        elif is_mission_ack:
            color = self.COLOR_OK if ok else self.COLOR_ERR
            label = "MISSION_ACK"
        else:
            color = self.COLOR_TEXT
            label = cmd

        self._append_status(f"{label} → {txt}", color, bold=(label == "SET_SERVO"))

    def _append_status(self, text: str, color: str = COLOR_TEXT, bold: bool = False):
        try:
            self._ui.currentState_textEdit_2.insertHtml(_html_line(text, color, bold))
            self._ui.currentState_textEdit_2.ensureCursorVisible()
        except Exception:
            self._ui.currentState_textEdit_2.append(text)
