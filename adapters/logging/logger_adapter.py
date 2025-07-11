# adapters/logging/logger_adapter.py

import logging
from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal
from core.ports.logger_port import ILoggerPort  # sadece type hint

class LoggerAdapter(QObject):
    """
    stdout + dosya + Qt sinyali — Plan A
    """
    new_log_message = pyqtSignal(str, str)   # (LEVEL, MESSAGE)

    def __init__(self, level: str = "INFO", file_path: str = "logs/gcs.log"):
        super().__init__()
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            format="%(asctime)s | %(levelname)s | %(message)s",
            handlers=[
                logging.FileHandler(file_path, mode="w", encoding="utf-8"),
                logging.StreamHandler()
            ]
        )

    # ---- internal helper ----
    def _log(self, lvl, msg: str):
        logging.log(lvl, msg)
        self.new_log_message.emit(logging.getLevelName(lvl), msg)

    # ---- ILoggerPort implementation ----
    def debug(self, m):   self._log(logging.DEBUG,   m)
    def info(self, m):    self._log(logging.INFO,    m)
    def warning(self, m): self._log(logging.WARNING, m)
    def error(self, m):   self._log(logging.ERROR,   m)
