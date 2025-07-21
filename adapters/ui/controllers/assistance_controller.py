# adapters/ui/controllers/assistance_controller.py
from __future__ import annotations

from PyQt5.QtCore import QObject, Qt
from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QLabel

from core.assistance_request import AssistanceRequest
from adapters.logging.logger_adapter import LoggerAdapter


class AssistanceController(QObject):
    """
    Mobil yardım isteğini renkli ve seçilebilir şekilde gösterir.
    """
    _COLOR_MAP = {
        "x": "#FFA500",    # Gıda → turuncu
        "=": "#FF2400",    # İlk yardım → kırmızı
        "!": "#7DF9FF",    # Afad → açık mavi
    }

    _DESC_MAP = {
        "x": "İhtiyaç: Gıda Paketi",
        "=": "İhtiyaç: İlk Yardım Paketi",
        "!": "İhtiyaç: Acil Müdahale Ekipleri",
    }

    def __init__(self, ui, logger: LoggerAdapter, parent=None):
        super().__init__(parent)
        self._ui = ui
        self._log = logger
        self._requests = []

        # QTextEdit yerine QListWidget yerleştir
        self._ui.mobileBox_textEdit.setVisible(False)
        self._list = QListWidget(self._ui.tab_7)
        self._list.setGeometry(self._ui.mobileBox_textEdit.geometry())
        self._list.setObjectName("mobileBox_listWidget")
        self._list.setStyleSheet("""
            background: transparent;
            border: none;
        """)
        self._ui.tab_7.setStyleSheet("background: transparent;")
        self._ui.mobileBox_listWidget = self._list  # UI dışından erişim için

    def on_request(self, r: AssistanceRequest):
        desc = self._DESC_MAP.get(r.durum, "İhtiyaç: Bilinmeyen")
        color = self._COLOR_MAP.get(r.durum, "#ccc")
        lat_txt = f"{abs(r.lat):.5f} {'N' if r.lat >= 0 else 'S'}"
        lon_txt = f"{abs(r.lon):.5f} {'E' if r.lon >= 0 else 'W'}"

        # ✔ Tüm bilgileri içeren metin
        text = f"{desc}\nKonum: {lat_txt}, {lon_txt}\nTC: {r.tc}"

        item = QListWidgetItem()

        label = QLabel(text)
        label.setWordWrap(True)
        label.setAttribute(Qt.WA_TranslucentBackground)
        label.setStyleSheet(f"""
            color: {color};
            background: transparent;
            padding: 5px;
            font-size: 12px;
        """)

        # Boyutu içeriğe göre ayarla
        label.adjustSize()
        item.setSizeHint(label.sizeHint())

        self._list.addItem(item)
        self._list.setItemWidget(item, label)

        self._requests.append(r)

    def get_selected_request(self) -> AssistanceRequest | None:
        idx = self._list.currentRow()
        if 0 <= idx < len(self._requests):
            return self._requests[idx]
        self._log.warning("Yardım isteği seçilmedi.")
        return None


