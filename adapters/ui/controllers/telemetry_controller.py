# adapters/ui/controllers/telemetry_controller.py
from PyQt5.QtCore import QObject, pyqtSlot, QTimer, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QListWidgetItem

from adapters.audio.audio_notifier import AudioNotifier

class TelemetryController(QObject):
    def __init__(self, widgets: dict, core, parent=None):
        super().__init__(parent)
        self._w = widgets
        self._last_bat_v = None
        self._last_pct_val = None
        self._last_band = None
        self._last_text = None
        self._last_mode = None  # Son mod bilgisi

        core.telemetry_updated.connect(self._update)


        # Ses bildirimleri
        self._notifier0 = AudioNotifier("assets/sounds/auto.wav")
        self._notifier1 = AudioNotifier("assets/sounds/guided.wav")
        self._notifier2 = AudioNotifier("assets/sounds/rtl.wav")

        # --- Mission WP başlığını UI açılır açılmaz ekle ---
        # --- Mission WP başlığını UI açılır açılmaz ekle ---
        try:
            lst = self._w['waypoint_listWidget']  # QListWidget
            need_header = (lst.count() == 0) or (lst.item(0).text() != "Mission WP")
            if need_header:
                header = QListWidgetItem("Mission WP")
                header.setFlags(Qt.NoItemFlags)  # seçilemesin
                f = QFont()
                f.setBold(True)
                header.setFont(f)
                lst.insertItem(0, header)
        except KeyError:
            pass

    def dispose(self):
        """Kapanışta sinyali ayır (widget yok olurken update gelmesin)."""
        try:
            # core bağlantısı constructor'da yapılmıştı
            # burada sadece güvenli disconnect yapıyoruz
            self._core.telemetry_updated.disconnect(self._update)
        except Exception:
            pass

    @pyqtSlot(dict)
    def _update(self, d):
        if 'yaw' in d:   self._w['yaw'].setText(f"{d['yaw']:.1f}°")
        if 'pitch' in d: self._w['pitch'].setText(f"{d['pitch']:.1f}°")
        if 'roll' in d:  self._w['roll'].setText(f"{d['roll']:.1f}°")
        if 'lat' in d:   self._w['lat'].setText(f"{d['lat']:.6f}")
        if 'lon' in d:   self._w['lon'].setText(f"{d['lon']:.6f}")
        if 'alt' in d:   self._w['alt'].setText(f"{d['alt']:.1f} m")
        if 'speed' in d: self._w['spd'].setText(f"{d['speed']:.1f} m/s")
        if 'hdop' in d:  self._w['hdop'].setText(f"{d['hdop']:.2f}")

        # --- Mode sesleri ---
        if 'mode' in d:
            mode_str = str(d['mode']).strip()
            self._w['mode'].setText(mode_str)

            if mode_str != self._last_mode:
                m = mode_str.lower()
                if m == "auto":
                    QTimer.singleShot(500, self._notifier0.play)
                elif m == "guided":
                    QTimer.singleShot(500, self._notifier1.play)
                elif m in ("rtl", "return to launch", "return-to-launch"):
                    QTimer.singleShot(500, self._notifier2.play)
                self._last_mode = mode_str

        # --- Batarya ---
        if 'bat_v' in d:
            self._last_bat_v = d['bat_v']

        if 'bat_pct' in d or 'bat_v' in d:
            bar = self._w['bat']
            pct = d.get('bat_pct', None)

            if pct is None:
                value = 0
                text = f"N/A  {self._last_bat_v:.1f} V" if self._last_bat_v is not None else "N/A"
                band = 'gray'
            else:
                value = max(0, min(100, int(pct)))
                text = f"{value}%  {self._last_bat_v:.1f} V" if self._last_bat_v is not None else f"{value}%"
                band = 'green' if value >= 60 else 'orange' if value >= 30 else 'red'

            if value != self._last_pct_val:
                bar.setValue(value)
                self._last_pct_val = value

            if text != self._last_text:
                bar.setFormat(text)
                self._last_text = text

            if band != self._last_band:
                if band == 'green':
                    color = "#2ecc71"
                elif band == 'orange':
                    color = "#f39c12"
                elif band == 'red':
                    color = "#e74c3c"
                else:
                    color = "#808080"
                css = f"""
                    QProgressBar {{
                        border: 1px solid #444; border-radius: 4px; text-align: center;
                    }}
                    QProgressBar::chunk {{
                        background-color: {color};
                    }}
                """
                bar.setStyleSheet(css)
                bar.setTextVisible(True)
                self._last_band = band

