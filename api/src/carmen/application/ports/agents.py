"""La única salida del supervisor hacia los datos (5.13.4, 5.14.6).

Dos implementaciones, un contrato: InProcessAgentRunner y SubAgentRunner. El orquestador no sabe
cuál está activa. El ejecutor de agente no puede importar este módulo (prueba de arquitectura).
"""

from typing import Protocol

from carmen.application.context import ExecutionContext
from carmen.domain.delegation.models import AgentResult, AgentTask


class AgentRunnerPort(Protocol):
    async def run(self, task: AgentTask, ctx: ExecutionContext) -> AgentResult:
        """Ejecuta UNA tarea en UN agente y devuelve su resultado.

        El agente recibe solo su AgentTask: no ve el DelegationPlan, ni a los demás agentes, ni el
        prompt del supervisor (6.12.4).
        Lanza: AgentUnavailableError, AgentTimeoutError, AgentContractViolationError.
        """
        ...
