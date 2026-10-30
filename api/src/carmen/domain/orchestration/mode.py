"""Los cinco modos de respuesta (2.3.2). Se clasifican ANTES de construir cualquier plan."""

from enum import StrEnum


class ResponseMode(StrEnum):
    SUPERVISOR_DIRECT = "SUPERVISOR_DIRECT"
    DELEGATE_SINGLE = "DELEGATE_SINGLE"
    DELEGATE_MULTI = "DELEGATE_MULTI"
    CLARIFY = "CLARIFY"
    REFUSE = "REFUSE"

    @property
    def delegates(self) -> bool:
        """Solo los dos modos de delegación producen DelegationPlan y AgentRun."""
        return self in (ResponseMode.DELEGATE_SINGLE, ResponseMode.DELEGATE_MULTI)
