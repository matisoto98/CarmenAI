"""Política de acceso a agentes y a la plataforma (5.14.4, 7.9).

El puerto siempre decide: no lanza. Sin concesión aplicable, o si la política no se puede
resolver, la respuesta es una denegación con su motivo. Un agente inexistente y uno oculto reciben
la misma denegación, con la misma forma y sin consulta adicional (7.9.5).
"""

from typing import Protocol

from carmen.domain.ids import AgentId, PrincipalId, TurnId
from carmen.domain.policy.models import AgentAction, PlatformAction, PolicyDecision


class PolicyPort(Protocol):
    def version(self) -> str:
        """Versión de la política vigente; toda decisión la lleva para poder recalcularse."""
        ...

    async def decide(
        self, *, principal_id: PrincipalId, action: AgentAction, agent_id: AgentId, turn_id: TurnId
    ) -> PolicyDecision:
        """Denegación por defecto; un deny explícito prevalece; allow une los scopes (7.9.3)."""
        ...

    async def decide_platform(
        self, *, principal_id: PrincipalId, action: PlatformAction, turn_id: TurnId
    ) -> PolicyDecision:
        """Administrar no es acceder: ninguna acción de plataforma concede datos (7.9.4)."""
        ...

    async def allowed_agents(
        self, *, principal_id: PrincipalId, action: AgentAction, turn_id: TurnId
    ) -> tuple[PolicyDecision, ...]:
        """Una decisión allow por agente concedido, ordenadas por agente. Nada de los demás."""
        ...
