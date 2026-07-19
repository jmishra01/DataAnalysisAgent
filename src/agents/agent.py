from abc import ABC

from ..errors import LLMError, LLMRefusalError
from ..llm_client import LLMClient


class SpecializedAgent(ABC):
    """Shared resilience behavior for role-specific agents."""

    name = "specialized_agent"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.last_fallback_reason: str | None = None

    def _fallback_after(self, error: LLMError) -> None:
        if isinstance(error, LLMRefusalError):
            raise error
        self.last_fallback_reason = f"{type(error).__name__}: {error}"

    def reset_diagnostics(self) -> None:
        self.last_fallback_reason = None
