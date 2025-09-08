# core/assistance_request.py

from dataclasses import dataclass

@dataclass(frozen=True)
class AssistanceRequest:
    tc: str
    lat: float
    lon: float
    durum: str
