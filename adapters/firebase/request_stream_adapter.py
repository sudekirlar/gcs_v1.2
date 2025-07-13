from firebase_admin import db
from core.assistance_request import AssistanceRequest
import logging


class FirebaseRequestStreamAdapter:
    def __init__(self, path: str = "/mobil"):
        self._ref = db.reference(path)
        self._logger = logging.getLogger(__name__)

    # ---------------- PUBLIC ----------------
    def subscribe(self, on_new_req):
        def _listener(event):
            try:
                data = event.data
                if data is None:
                    return

                # İlk dump (event.path == "/") → sözlükse doğrudan işle
                if isinstance(data, dict):
                    self._process_dict(data, on_new_req)
                else:
                    self._logger.warning("Beklenmeyen veri tipi: %s", data)

            except Exception:
                self._logger.exception("Stream callback error")

        self._ref.listen(_listener)

    # -------------- PRIVATE -----------------
    def _process_dict(self, payload: dict, emit_cb):
        """
        payload: {'durum': 'x', 'tc': '...', 'konum': {'lat': .., 'lon': ..}}
                 veya {'-Nk…': {...}, '-Nkp…': {...}}  (pushId yapısı)
        """
        # 1) Push-ID’li yapıysa alt çocukları gez
        if not {"durum", "tc", "konum"} <= payload.keys():
            for child in payload.values():
                if isinstance(child, dict):
                    self._process_dict(child, emit_cb)
            return

        # 2) Beklenen anahtarlara sahip tekil kayıt
        loc = payload.get("konum", {})
        if not (isinstance(loc, dict) and {"lat", "lon"} <= loc.keys()):
            self._logger.warning("Eksik 'konum': %s", payload)
            return

        try:
            req = AssistanceRequest(
                durum=str(payload["durum"]),
                tc=int(payload["tc"]),
                lat=float(loc["lat"]),
                lon=float(loc["lon"]),
            )
            emit_cb(req)                     # → Qt sinyali tetikle
        except (ValueError, TypeError):
            self._logger.warning("Tip dönüştürme hatası: %s", payload)
