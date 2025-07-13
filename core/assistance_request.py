from dataclasses import dataclass

@dataclass(frozen=True)
class AssistanceRequest:
    """Mobil uygulamadan gelen ‘yardım çağrısı’ kaydı."""
    tc: str          # 11 haneli
    lat: float
    lon: float
    durum: str        # ör. "yara", "ilaç", "gıda"
