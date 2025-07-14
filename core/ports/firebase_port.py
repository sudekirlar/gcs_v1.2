from typing import Protocol, Any
from core.assistance_request import AssistanceRequest

class IFirebasePort(Protocol):
    new_request: Any    # pyqtSignal(AssistanceRequest)
    error: Any          # pyqtSignal(str)
    def stop(self) -> None: ...
