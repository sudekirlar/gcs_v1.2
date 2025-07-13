# main.py
from PyQt5.QtWidgets import QApplication
from firebase_admin import db                   # ① EKLE

from config.settings import Settings
from adapters.logging.logger_adapter import LoggerAdapter
from adapters.mavlink.pymavlink_adapter import PymavlinkAdapter
from core.gcs_core import GCSCore
from adapters.ui.main_window import MainWindow
from config.firebase_init import init_firebase

init_firebase()

# -------------- AÇILIŞ TEMİZLİĞİ --------------
def clear_mobil_node():
    try:
        db.reference("/mobil").delete()
    except Exception as e:
        print(f"/mobil düğümü silinemedi: {e}")

clear_mobil_node()                              # ② ⬅ ilk satır verileri sıfırla
# ----------------------------------------------

# ----- Konfigürasyonu yükle -----
cfg = Settings()

# ----- Ortak logger -----
logger = LoggerAdapter(level=cfg.log_level, file_path=str(cfg.log_path))

# ----- Bağlantı adaptörü + Core -----
adapter = PymavlinkAdapter(logger)
core    = GCSCore(adapter, logger)

# ----- Qt uygulaması -----
app = QApplication([])

win = MainWindow(core=core, logger=logger)
win.show()

app.exec_()
