# main.py

import sys, multiprocessing
from PyQt5.QtWidgets import QApplication

# ---------------- QtWebEngine önceliği ----------------
from adapters.ui.main_window import MainWindow

# ---------------- Konfig & Firebase -------------------
from config.settings       import Settings
from config.firebase_init  import init_firebase
init_firebase()
cfg = Settings()

# ---------------- Logger ------------------------------
from adapters.logging.logger_adapter import LoggerAdapter
logger = LoggerAdapter(level=cfg.log_level, file_path=str(cfg.log_path))

# ---------------- Adaptörler --------------------------
from adapters.mavlink.pymavlink_adapter import PymavlinkAdapter
from adapters.firebase.firebase_adapter  import FirebaseAdapter
from adapters.camera.opencv_adapter      import OpenCVAdapter

mav_adapter = PymavlinkAdapter(logger)
fb_adapter  = FirebaseAdapter(cfg.firebase_db_path, logger, clear_on_start=True)
cam_adapter = OpenCVAdapter(logger)

# ---------------- Core -------------------------------
from core.gcs_core     import GCSCore
from core.camera_core  import CameraCore
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
        fb_adapter=fb_adapter,
    )
    win.show()

    # ---------- Asenkron & Merkezi Temiz Çıkış ----------
    pending_tasks = 1   # şimdilik sadece Firebase

    def _task_done():
        global pending_tasks
        pending_tasks -= 1
        logger.info(f"Asenkron görev tamamlandı – beklenen: {pending_tasks}")
        if pending_tasks == 0:
            logger.info("Tüm görevler bitti, uygulama kapanıyor.")
            app.quit()

    fb_adapter.finished.connect(_task_done)

    def initiate_cleanup():
        logger.info("aboutToQuit – temizleme başlatılıyor…")
        cam_adapter.stop()
        mav_adapter.close()
        fb_adapter.stop()        # asenkron

    app.aboutToQuit.connect(initiate_cleanup)
    sys.exit(app.exec_())
