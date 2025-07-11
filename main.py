# main.py

from PyQt5.QtWidgets import QApplication

from config.settings import Settings
from adapters.logging.logger_adapter import LoggerAdapter
from adapters.mavlink.pymavlink_adapter import PymavlinkAdapter
from core.gcs_core import GCSCore
from adapters.ui.main_window import MainWindow   # controller'lar içeride kuruluyor

# ----- Konfigürasyonu yükle -----
cfg = Settings()

# ----- Ortak logger -----
logger = LoggerAdapter(level=cfg.log_level, file_path=str(cfg.log_path))

# ----- Bağlantı adaptörü + Core -----
adapter = PymavlinkAdapter(logger)
core    = GCSCore(adapter, logger)

# ----- Qt uygulaması -----
app = QApplication([])

# MainWindow, controller'ları kendi ctor'unda oluşturur
win = MainWindow(core=core, logger=logger)
win.show()

app.exec_()
