from abc import ABC, abstractmethod
from typing import Callable
from core.assistance_request import AssistanceRequest

class RequestStreamPort(ABC):
    """AssistanceRequest olaylarını push eden (observable) akış."""

    @abstractmethod
    def subscribe(self, on_req: Callable[[AssistanceRequest], None]) -> None:
        """Her yeni kayıt geldiğinde `on_req` callback’i çağrılır."""
        ...
