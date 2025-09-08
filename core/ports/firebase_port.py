from typing import Protocol, Any
from core.assistance_request import AssistanceRequest

class IFirebasePort(Protocol):
    new_request: Any
    error: Any
    def stop(self) -> None: ...
