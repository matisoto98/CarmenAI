"""AgentCard: la ficha del agente y lo único que Carmen puede usar para hablar de él (5.14.3).

Incluye la visibilidad (5.14.4), la conectividad (5.15.2) y el ciclo de vida (7.11.2). Las
transiciones de estado son exactamente las cuatro del diagrama; cualquier otra es un error.
"""

import re
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum
from typing import Final

from carmen.domain.errors import InvalidTransitionError, ValidationError
from carmen.domain.ids import AgentId, McpServerId, ProviderId, Scope
from carmen.domain.text import require_non_negative, require_text

_SEMVER: Final = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


class AgentLifecycleState(StrEnum):
    DISCOVERED = "DISCOVERED"
    COMPATIBLE = "COMPATIBLE"
    CERTIFIED = "CERTIFIED"
    QUARANTINED = "QUARANTINED"

    @property
    def invocable(self) -> bool:
        """Solo un agente CERTIFIED se invoca desde producción."""
        return self is AgentLifecycleState.CERTIFIED

    def can_transition_to(self, target: "AgentLifecycleState") -> bool:
        return (self, target) in LIFECYCLE_TRANSITIONS


LIFECYCLE_TRANSITIONS: Final = frozenset(
    {
        # contrato validado
        (AgentLifecycleState.DISCOVERED, AgentLifecycleState.COMPATIBLE),
        # certificación
        (AgentLifecycleState.COMPATIBLE, AgentLifecycleState.CERTIFIED),
        # incidente, SLO roto o hallazgo de seguridad
        (AgentLifecycleState.CERTIFIED, AgentLifecycleState.QUARANTINED),
        # revisión: vuelve a empezar y exige nueva certificación
        (AgentLifecycleState.QUARANTINED, AgentLifecycleState.DISCOVERED),
    }
)


class Visibility(StrEnum):
    PUBLIC_CATALOG = "PUBLIC_CATALOG"
    DISCOVERABLE = "DISCOVERABLE"
    AUTHORIZED_ONLY = "AUTHORIZED_ONLY"
    HIDDEN = "HIDDEN"


class Connectivity(StrEnum):
    INTERNAL_ONLY = "INTERNAL_ONLY"
    EXTERNAL_GOVERNED = "EXTERNAL_GOVERNED"
    HYBRID_GOVERNED = "HYBRID_GOVERNED"


class AllowedAction(StrEnum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True, slots=True)
class AgentSlo:
    p95_ms: int
    availability: Decimal

    def __post_init__(self) -> None:
        require_non_negative("slo.p95_ms", self.p95_ms)
        if not Decimal(0) <= self.availability <= Decimal(100):
            msg = f"slo.availability fuera de [0, 100]: {self.availability}"
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class AgentBudgets:
    """Presupuesto por ejecución declarado en la ficha."""

    max_tokens_per_run: int
    max_cost_per_run_eur: Decimal
    max_wall_ms: int

    def __post_init__(self) -> None:
        require_non_negative("budgets.max_tokens_per_run", self.max_tokens_per_run)
        require_non_negative("budgets.max_wall_ms", self.max_wall_ms)
        if not self.max_cost_per_run_eur.is_finite() or self.max_cost_per_run_eur < 0:
            msg = "budgets.max_cost_per_run_eur debe ser >= 0"
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class AgentCard:
    agent_id: AgentId
    version: str
    display_name: str
    owner: str
    status: AgentLifecycleState
    connectivity: Connectivity
    visibility: Visibility
    safe_description: str
    public_capabilities: tuple[str, ...]
    routing_description: str
    allowed_actions: frozenset[AllowedAction]
    scopes: frozenset[Scope]
    entities_exposed: tuple[str, ...]
    mcp_bindings: tuple[McpServerId, ...]
    provider_bindings: tuple[ProviderId, ...]
    slo: AgentSlo
    budgets: AgentBudgets
    golden_set: str
    kill_switch: bool

    def __post_init__(self) -> None:
        if not _SEMVER.fullmatch(self.version):
            msg = f"versión de agente no semántica: {self.version!r}"
            raise ValidationError(msg)
        for name, value in (
            ("display_name", self.display_name),
            ("owner", self.owner),
            ("safe_description", self.safe_description),
            ("routing_description", self.routing_description),
            ("golden_set", self.golden_set),
        ):
            require_text(name, value)
        for capability in self.public_capabilities:
            require_text("public_capabilities", capability)
        if not self.allowed_actions:
            msg = "allowed_actions no puede estar vacío"
            raise ValidationError(msg)
        if AllowedAction.WRITE in self.allowed_actions:
            msg = "v1 es de solo lectura: ningún agente declara write (invariante 5)"
            raise ValidationError(msg)
        if len(set(self.mcp_bindings)) != len(self.mcp_bindings):
            msg = "mcp_bindings repite un servidor"
            raise ValidationError(msg)

    def transition_to(self, target: AgentLifecycleState) -> "AgentCard":
        """Nueva ficha con el estado cambiado. Solo las transiciones de 7.11.2."""
        if not self.status.can_transition_to(target):
            msg = f"{self.agent_id}: transición no permitida {self.status} -> {target}"
            raise InvalidTransitionError(msg)
        return replace(self, status=target)
