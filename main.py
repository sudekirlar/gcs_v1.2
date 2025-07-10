from PyQt5.QtWidgets import QApplication
from adapters.logging.logger_adapter import LoggerAdapter
from adapters.ui.main_window import MainWindow
from adapters.ui.controllers.log_controller import LogController
from core.gcs_core import GCSCore

def main():
    logger = LoggerAdapter(level="DEBUG")
    core   = GCSCore(logger_port=logger)

    app = QApplication([])
    window = MainWindow()                 # Salt view
    window.show()

    # --- Controller'ı bağla ---
    LogController(window.log_text_edit, logger)   # tek sorumluluk

    logger.info("Uygulama başlatıldı")   # Dosya + terminal + GUI
    core.start()

    app.exec_()

if __name__ == "__main__":
    main()
