import os
import sys
import subprocess
from PyQt5.QtCore import QObject, pyqtSlot, QTimer, Qt
from PyQt5.QtWidgets import QMessageBox, QDialog, QLabel, QVBoxLayout, QApplication

class LoginHandler(QObject):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.tema_combo = None
        self.login_disabled = False
        self._blocker = None   # modal bekleme diyaloğu referansı

    def set_tema_combo(self, combo):
        self.tema_combo = combo

    @pyqtSlot(str, str)
    def kullanici_dogrula(self, kullanici, sifre):
        if self.login_disabled:
            return
        self.login_disabled = True

        dogru_bilgiler = {
            "ilayda": "boncuk",
            "sude": "baykuş"
        }
        if dogru_bilgiler.get(kullanici) == sifre:
            # Önce modal bloklayıcıyı göster (tüm inputu kilitle)
            self._show_wait_dialog(kullanici)
            # Sonra temayı başlat
            self.uygulamayi_baslat()
        else:
            QMessageBox.warning(None, "Hatalı Giriş", "Kullanıcı adı veya şifre yanlış.")
            self.login_disabled = False

    # ---- Modal bloklayıcı (tüm tıklamaları yutar) ----
    def _show_wait_dialog(self, kullanici_adi: str):
        self._blocker = QDialog(self.window)
        self._blocker.setModal(True)
        self._blocker.setWindowModality(Qt.ApplicationModal)
        self._blocker.setWindowFlags(
            Qt.Dialog |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        # Tam pencereyi kapla + yarı saydam arka plan
        self._blocker.setAttribute(Qt.WA_TranslucentBackground, True)
        self._blocker.setGeometry(self.window.rect())

        # Mesaj
        lbl = QLabel(f"Hoşgeldin {kullanici_adi}, lütfen biraz bekle…", self._blocker)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 160);
                color: white;
                font-size: 20pt;
                font-weight: bold;
            }
        """)

        lay = QVBoxLayout(self._blocker)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(lbl)

        # Login penceresini de pasifleştir (ekstra güvence)
        self.window.setEnabled(False)

        self._blocker.show()
        QApplication.processEvents()  # hemen çiz

    def _close_all(self):
        # modal’ı kapatıp login’i kapat
        try:
            if self._blocker is not None:
                self._blocker.close()
        except Exception:
            pass
        self.window.close()

    def uygulamayi_baslat(self):
        tema = (self.tema_combo.currentText() if self.tema_combo else "").strip().lower()
        script_adi = "main_klasik.py" if tema == "klasik" else "main.py"

        base_dir = os.path.dirname(os.path.abspath(__file__))
        hedef = os.path.join(base_dir, script_adi)

        if not os.path.exists(hedef):
            QMessageBox.critical(None, "Hata", f"'{script_adi}' bulunamadı:\n{hedef}")
            self.login_disabled = False
            return

        try:
            popen_kwargs = dict(
                args=[sys.executable, hedef],
                cwd=base_dir,
                close_fds=True
            )
            if os.name == "nt":
                DETACHED_PROCESS = 0x00000008
                CREATE_NEW_PROCESS_GROUP = 0x00000200
                popen_kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

            subprocess.Popen(**popen_kwargs)

        except Exception as e:
            QMessageBox.critical(None, "Hata", f"{script_adi} açılamadı:\n{e}")
            self.login_disabled = False
            # bloklayıcıyı da kaldır ki kullanıcı tekrar deneyebilsin
            try:
                if self._blocker is not None:
                    self._blocker.close()
            except Exception:
                pass
            self.window.setEnabled(True)
            return

        # Biraz beklet, sonra modal’ı ve login’i kapat
        QTimer.singleShot(4000, self._close_all)
