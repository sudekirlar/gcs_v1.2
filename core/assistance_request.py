from dataclasses import dataclass

# slots=True KALDIRILDI
@dataclass(frozen=True)                 # ← bu satır
class AssistanceRequest:
    tc: str
    lat: float
    lon: float
    durum: str
