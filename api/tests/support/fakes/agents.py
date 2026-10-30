"""Ejecutor de agentes con guion por agente (5.13.4)."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from carmen.application.context import ExecutionContext
from carmen.application.errors import AgentContractViolationError, AgentUnavailableError
from carmen.domain.delegation.models import AgentResult, AgentTask
from carmen.domain.errors import CarmenError
from carmen.domain.ids import AgentId

AgentBehavior = AgentResult | CarmenError | Callable[[AgentTask], AgentResult]


@dataclass(frozen=True, slots=True)
class AgentCall:
    task: AgentTask
    ctx: ExecutionContext


class FakeAgentRunner:
    """Un agente sin guion no está disponible. Un resultado de otra tarea viola el contrato."""

    def __init__(self, behaviors: Mapping[AgentId, AgentBehavior]) -> None:
        self._behaviors = dict(behaviors)
        self.calls: list[AgentCall] = []

    async def run(self, task: AgentTask, ctx: ExecutionContext) -> AgentResult:
        self.calls.append(AgentCall(task, ctx))
        behavior = self._behaviors.get(task.agent_id)
        if behavior is None:
            msg = f"{task.agent_id} no está disponible"
            raise AgentUnavailableError(msg)
        if isinstance(behavior, CarmenError):
            raise behavior
        result = behavior if isinstance(behavior, AgentResult) else behavior(task)
        if result.task_id != task.task_id or result.agent_id != task.agent_id:
            msg = f"{task.agent_id} devolvió el resultado de {result.agent_id}/{result.task_id}"
            raise AgentContractViolationError(msg)
        return result

    @property
    def tasks(self) -> list[AgentTask]:
        return [call.task for call in self.calls]
