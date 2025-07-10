import logging
from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal
from core.ports.logger_port import ILoggerPort

class LoggerAdapter(QObject, ILoggerPort):
    """
    • stdout + dosya + Qt sinyali → hepsi aynı yerde (Plan A).
    • MainWindow log paneli bu sinyali dinler.
    """
    new_log_message = pyqtSignal(str, str)          # level, message

    def __init__(self, level: str = "INFO", file_path: str = "logs/gcs.log"):
        super().__init__()
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            format="%(asctime)s | %(levelname)s | %(message)s",
            handlers=[
                logging.FileHandler(file_path, encoding="utf-8"),
                logging.StreamHandler()
            ]
        )

    # --- iç yardımcı ---
    def _log(self, lvl, msg: str):
        logging.log(lvl, msg)
        self.new_log_message.emit(logging.getLevelName(lvl), msg)

    # --- ILoggerPort implementasyonu ---
    def debug(self, m):   self._log(logging.DEBUG,   m)
    def info(self, m):    self._log(logging.INFO,    m)
    def warning(self, m): self._log(logging.WARNING, m)
    def error(self, m):   self._log(logging.ERROR,   m)
