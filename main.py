# main.py

import sys
import multiprocessing
from PyQt5.QtWidgets import QApplication

# ---------------- QtWebEngine önceliği ----------------
from adapters.ui.main_window import MainWindow  # WebEngine'den önce import edilmeli

# ---------------- Konfigürasyon & Firebase ------------
from config.settings import Settings
from config.firebase_init import init_firebase

init_firebase()  # ⇢ sadece 1 kez çağrılır
cfg = Settings()

# ---------------- Logger ------------------------------
from adapters.logging.logger_adapter import LoggerAdapter
logger = LoggerAdapter(level=cfg.log_level, file_path=str(cfg.log_path))

# ---------------- Adaptörler --------------------------

# MAVLink adaptörü
from adapters.mavlink.pymavlink_adapter import PymavlinkAdapter
mav_adapter = PymavlinkAdapter(logger)

# Firebase adaptörü
from adapters.firebase.firebase_adapter import FirebaseAdapter
fb_adapter = FirebaseAdapter(cfg.firebase_db_path, logger, clear_on_start=True)

# Kamera adaptörü
from adapters.camera.opencv_adapter import OpenCVAdapter
cam_adapter = OpenCVAdapter(logger)

# ---------------- Core -------------------------------

from core.gcs_core import GCSCore
from core.camera_core import CameraCore

gcs_core = GCSCore(mav_adapter, fb_adapter, logger)
cam_core = CameraCore(cam_adapter, logger)

# ---------------- Qt Uygulaması -----------------------
if __name__ == "__main__":
    multiprocessing.freeze_support()
    multiprocessing.set_start_method("spawn", force=True)

    app = QApplication(sys.argv)

    win = MainWindow(
        core=gcs_core,
        camera_core=cam_core,
        camera_adapter=cam_adapter,
        logger=logger,
        settings=cfg,
    )
    win.show()

    # ---------------- Temiz çıkış -----------------------
    def _cleanup():
        logger.info("Uygulama kapanıyor – kaynaklar serbest bırakılıyor…")
        cam_adapter.stop()
        mav_adapter.close()
        fb_adapter.stop()

    app.aboutToQuit.connect(_cleanup)
    sys.exit(app.exec_())
