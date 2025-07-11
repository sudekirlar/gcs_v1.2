# adapters/ui/controllers/log_controller.py

from PyQt5.QtCore import QObject, pyqtSlot
from adapters.logging.logger_adapter import LoggerAdapter  # tip ipucu

class LogController(QObject):
    """
    GUI'deki criticalShown_textEdit'i, LoggerAdapter sinyaline bağlar.
    MainWindow'un içine mantık koymaz.
    """
    def __init__(self, text_edit_widget, logger: LoggerAdapter):
        super().__init__()
        self._text_edit = text_edit_widget
        logger.new_log_message.connect(self._append_log)

    @pyqtSlot(str, str)
    def _append_log(self, level: str, msg: str):
        self._text_edit.append(f"[{level}] {msg}")
