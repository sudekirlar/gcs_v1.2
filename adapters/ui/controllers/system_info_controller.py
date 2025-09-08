# adapters/ui/controllers/system_info_controller.py
from __future__ import annotations
import datetime
import threading
import requests
import locale
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import QObject, QTimer, QLocale, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QLabel

# Hava durumu verisini çeken requests çağrısını ayrı bir arka plan thread'ine taşıyarak çözdüm.
# Bu thread, işini bitirdiğinde sonucu ana thread'e bildirmek için PyQt'nun thread-güvenli sinyal-slot mekanizmasını kullanır.
# Arka plan thread'i emit ile bir sinyal yayar, ana thread'deki bir slot ise bu sinyali yakalar ve arayüzü günceller.

@dataclass
class WeatherResult: # API'dan gelen hava durumu verisini yapısal bir şekilde tutar.
    city: Optional[str]
    temp_c: Optional[float]
    code: Optional[int]
    desc: str
    icon: str

def _weathercode_to_icon_desc(code: int):
    table = {
        0:  ("☀️", "Açık"),
        1:  ("🌤️", "Genelde açık"),
        2:  ("⛅",  "Parçalı bulutlu"),
        3:  ("☁️", "Bulutlu"),
        45: ("🌫️", "Sis"),
        48: ("🌫️", "Kırağılı sis"),
        51: ("🌦️", "Çiseleme hafif"),
        53: ("🌦️", "Çiseleme orta"),
        55: ("🌧️", "Çiseleme yoğun"),
        56: ("🌧️", "Dondurucu çiseleme hafif"),
        57: ("🌧️", "Dondurucu çiseleme yoğun"),
        61: ("🌦️", "Yağmur hafif"),
        63: ("🌧️", "Yağmur orta"),
        65: ("🌧️", "Yağmur şiddetli"),
        71: ("🌨️", "Kar hafif"),
        73: ("🌨️", "Kar orta"),
        75: ("🌨️", "Kar şiddetli"),
        77: ("🌨️", "Kar taneleri"),
        80: ("🌦️", "Sağanak hafif"),
        81: ("🌧️", "Sağanak orta"),
        82: ("⛈️",  "Sağanak şiddetli"),
        85: ("🌨️", "Kar sağanağı hafif"),
        86: ("🌨️", "Kar sağanağı şiddetli"),
        95: ("⛈️",  "Gök gürültülü"),
        96: ("⛈️",  "Dolu ihtimali"),
        99: ("⛈️",  "Şiddetli dolu"),
    }
    return table.get(code, ("❓", "Bilinmiyor"))


# ==============================================================
# Controller (yalnızca .env → Settings kullanır)
# ==============================================================
class SystemInfoController(QObject):
    _weather_ready = pyqtSignal(object)  # Bu, arka plan thread'i ile ana thread arasındaki iletişim kanalıdır. Arka planda hava durumu verisi çekildiğinde, bu sinyal WeatherResult nesnesi ile birlikte yayılır.

    def __init__(
        self,
        time_label: QLabel,
        date_label: QLabel,
        weather_label: QLabel,
        settings,
        logger,
        parent=None
    ):
        super().__init__(parent)
        self._time_label = time_label
        self._date_label = date_label
        self._weather_label = weather_label
        self._cfg = settings
        self._log = logger

        try:
            locale.setlocale(locale.LC_TIME, "")
        except Exception:
            pass
        self._qloc = QLocale(QLocale.Turkish, QLocale.Turkey)

        # Ayarlar
        self._weather_timeout = getattr(self._cfg, "weather_timeout_sec", 3)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

        self._weather_ready.connect(self._on_weather_ready)

    def start(self):
        self._on_tick()
        self._timer.start()
        if getattr(self._cfg, "weather_enabled", True):
            self._fetch_weather_once_async()

    @pyqtSlot()
    def _on_tick(self):
        now = datetime.datetime.now()
        self._time_label.setText(now.strftime("%H:%M:%S"))
        self._date_label.setText(self._qloc.toString(now.date(), "dd MMM yyyy"))

    def _fetch_weather_once_async(self): # Bu metod arka plan thread'inde çalışır.
        threading.Thread(target=self._weather_job_env_only, daemon=True).start() # Ana uygulama kapandığında bu arka plan thread'inin de otomatik olarak sonlanmasını daemon ile sağlıyoruz.

    def _weather_job_env_only(self):
        try:
            env_city = getattr(self._cfg, "default_city", None)
            env_lat  = getattr(self._cfg, "default_lat", None)
            env_lon  = getattr(self._cfg, "default_lon", None)

            if env_lat is None or env_lon is None:
                self._log.warning("[Weather] .env lat/lon eksik; gösterilecek veri yok.")
                self._weather_ready.emit(WeatherResult(city=env_city, temp_c=None, code=None,
                                                       desc="Konum yok", icon="❗"))
                return

            lat = float(env_lat)
            lon = float(env_lon)
            self._log.debug(f"[Weather] Kaynak=.env → {env_city} ({lat},{lon})")

            w = self._get_open_meteo_weather(lat, lon)
            w.city = env_city  # şehir adı da sadece .env’den

            self._log.debug(f"[Weather] chosen=(lat={lat}, lon={lon}) city='{w.city}' temp={w.temp_c}")
            self._weather_ready.emit(w)

        except Exception as e:
            self._log.error(f"[Weather] Hata (.env akışı): {e}")
            self._weather_ready.emit(WeatherResult(city=getattr(self._cfg, "default_city", None),
                                                   temp_c=None, code=None, desc="Hata", icon="⚠️"))

    # Muhtemel bloklayıcı normalde buradaydı. (Blocking) Thread ile çözüldü.
    def _get_open_meteo_weather(self, lat: float, lon: float) -> WeatherResult:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&current_weather=true&timezone=auto"
        )
        self._log.debug(f"[Weather] Current weather GET: {url}")
        r = requests.get(url, timeout=self._weather_timeout)
        j = r.json()
        cw = j.get("current_weather") or {}
        temp = cw.get("temperature")
        code = cw.get("weathercode")
        icon, desc = _weathercode_to_icon_desc(int(code) if code is not None else -1)
        return WeatherResult(city=None, temp_c=temp, code=code, desc=desc, icon=icon)

    @pyqtSlot(object) # Ana thread'de çalışır.
    def _on_weather_ready(self, w: WeatherResult):
        pieces = []
        if w.city:
            pieces.append(w.city)
        if w.icon:
            pieces.append(w.icon)
        if w.temp_c is not None:
            try:
                pieces.append(f"{round(float(w.temp_c))}°C")
            except Exception:
                pieces.append(f"{w.temp_c}°C")
        text = " • ".join(pieces) if pieces else "Hava bilgisi yok"
        self._weather_label.setText(text)
        self._weather_label.setToolTip(w.desc or "")
