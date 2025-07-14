# main.py
import sys
from PyQt5.QtWidgets import QApplication

# ---------------- Konfig & Firebase init ----------------
from config.settings import Settings
from config.firebase_init import init_firebase

init_firebase()                 # ⇢ sadece 1 kez çağrılır
cfg = Settings()

# ---------------- Ortak logger --------------------------
from adapters.logging.logger_adapter import LoggerAdapter
logger = LoggerAdapter(level=cfg.log_level,
                       file_path=str(cfg.log_path))

# ---------------- Adaptörler ----------------------------
from adapters.mavlink.pymavlink_adapter import PymavlinkAdapter
from adapters.firebase.firebase_adapter import FirebaseAdapter

mav_adapter = PymavlinkAdapter(logger)

fb_adapter = FirebaseAdapter(cfg.firebase_db_path, logger, clear_on_start=True)


# ---------------- Çekirdek ------------------------------
from core.gcs_core import GCSCore
core = GCSCore(mav_adapter, fb_adapter, logger)

# ---------------- Qt Uygulaması & Ana Pencere -----------
from adapters.ui.main_window import MainWindow

app = QApplication(sys.argv)
win = MainWindow(core=core, logger=logger)
win.show()

status = app.exec_()

# ---------------- Temiz çıkış ---------------------------
mav_adapter.close()
fb_adapter.stop()
sys.exit(status)
