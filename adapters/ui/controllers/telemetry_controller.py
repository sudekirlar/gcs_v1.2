from PyQt5.QtCore import QObject, pyqtSlot

class TelemetryController(QObject):
    def __init__(self, widgets: dict, core, parent=None):
        super().__init__(parent)
        self._w = widgets
        core.telemetry_updated.connect(self._update)

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
