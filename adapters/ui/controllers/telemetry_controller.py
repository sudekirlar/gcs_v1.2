# adapters/ui/controllers/telemetry_controller.py

from PyQt5.QtCore import QObject, pyqtSlot

class TelemetryController(QObject):
    def __init__(self, widgets: dict, core, parent=None):
        super().__init__(parent)
        self._w = widgets
        self._last_bat_v = None  # formatta voltaj yazmak için
        # Throttle cache
        self._last_pct_val = None
        self._last_band = None  # 'green' | 'orange' | 'red' | 'gray'
        self._last_text = None
        core.telemetry_updated.connect(self._update)

    def dispose(self):
        """Kapanışta sinyali ayır (widget yok olurken update gelmesin)."""
        if self._connected:
            try:
                self._core.telemetry_updated.disconnect(self._update)
            except Exception:
                pass
            self._connected = False

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
        if 'mode' in d:  self._w['mode'].setText(d['mode'])

        # ---- Batarya ----
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
                if self._last_bat_v is not None:
                    text = f"{value}%  {self._last_bat_v:.1f} V"
                else:
                    text = f"{value}%"
                band = ('green' if value >= 60 else 'orange' if value >= 30 else 'red')

            # ---- Throttle: yalnız değişince güncelle ----
            if value != self._last_pct_val:
                bar.setValue(value)
                self._last_pct_val = value

            if text != self._last_text:
                bar.setFormat(text)
                self._last_text = text

            if band != self._last_band:
                # Stil sadece band değiştiğinde yazılsın
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