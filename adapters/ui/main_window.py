from PyQt5.QtWidgets import QMainWindow
from newDesign import Ui_MainWindow    # Designer çıktısı

class MainWindow(QMainWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)             # Widget'lar hazır

    # Hiçbir mantık yok: widget'lar dışarıdan erişilsin diye property
    @property
    def log_text_edit(self):
        return self.ui.criticalShown_textEdit
