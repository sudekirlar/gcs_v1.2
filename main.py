import sys, multiprocessing
from PyQt5.QtWidgets import QApplication
# ---- WebEngine'i ÖNCE import et ----
from adapters.ui.main_window import MainWindow        # <-- yukarı alındı

# -------------------------------------------------
# Konfig + Logger
# -------------------------------------------------
from config.settings            import Settings
from adapters.logging.logger_adapter import LoggerAdapter

cfg     = Settings()
logger  = LoggerAdapter(level=cfg.log_level, file_path=str(cfg.log_path))

# -------------------------------------------------
# MAVLink dünyası
# -------------------------------------------------
from adapters.mavlink.pymavlink_adapter import PymavlinkAdapter
from core.gcs_core                       import GCSCore

mav_adapter = PymavlinkAdapter(logger)
gcs_core    = GCSCore(mav_adapter, logger)

# -------------------------------------------------
# Kamera dünyası
# -------------------------------------------------
from adapters.camera.opencv_adapter import OpenCVAdapter
from core.camera_core               import CameraCore

cam_adapter = OpenCVAdapter(logger)
cam_core    = CameraCore(cam_adapter, logger)

# -------------------------------------------------
# Qt uygulaması
# -------------------------------------------------
if __name__ == "__main__":
    multiprocessing.freeze_support()
    multiprocessing.set_start_method("spawn", force=True)

    app = QApplication(sys.argv)            # <-- artık WebEngine import edilmiş durumda

    win = MainWindow(
        core            = gcs_core,
        camera_core     = cam_core,
        camera_adapter  = cam_adapter,
        logger          = logger,
        settings        = cfg,
    )
    win.show()

    # Temiz kapanış
    def _cleanup():
        logger.info("Uygulama kapanıyor – kaynaklar serbest bırakılıyor…")
        cam_adapter.stop()
        mav_adapter.close()
    app.aboutToQuit.connect(_cleanup)

    sys.exit(app.exec_())
