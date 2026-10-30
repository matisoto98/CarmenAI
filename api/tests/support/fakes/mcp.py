"""Cliente MCP con guion por herramienta. El servidor simulado completo llega en el Prompt 9."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from carmen.application.context import ExecutionContext
from carmen.application.errors import McpToolError
from carmen.application.ports.mcp import (
    HealthStatus,
    McpEnvelope,
    SystemHealth,
    ToolDescriptor,
    ToolInvocation,
)
from carmen.application.ports.system import Clock
from carmen.domain.errors import CarmenError, McpUnavailableError
from carmen.domain.system import SystemId
from support.fakes.system import FrozenClock

ToolBehavior = McpEnvelope | CarmenError | Callable[[ToolInvocation], McpEnvelope]


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    invocation: ToolInvocation
    ctx: ExecutionContext


class FakeMcpClient:
    """Un sistema sin herramientas declaradas no está disponible; una herramienta sin guion
    responde con error de herramienta.
    """

    def __init__(
        self,
        *,
        tools: Mapping[SystemId, Sequence[ToolDescriptor]],
        responses: Mapping[tuple[SystemId, str], ToolBehavior],
        down: frozenset[SystemId] = frozenset(),
        clock: Clock | None = None,
    ) -> None:
        self._tools = {s: tuple(t) for s, t in tools.items()}
        self._responses = dict(responses)
        self._down = down
        self._clock = clock or FrozenClock()
        self.calls: list[ToolCallRecord] = []

    async def list_tools(self, system: SystemId, ctx: ExecutionContext) -> list[ToolDescriptor]:
        if system in self._down or system not in self._tools:
            msg = f"{system} no está disponible"
            raise McpUnavailableError(msg)
        return list(self._tools[system])

    async def call_tool(self, invocation: ToolInvocation, ctx: ExecutionContext) -> McpEnvelope:
        self.calls.append(ToolCallRecord(invocation, ctx))
        if invocation.system in self._down:
            msg = f"{invocation.system} no está disponible"
            raise McpUnavailableError(msg)
        behavior = self._responses.get((invocation.system, invocation.tool))
        if behavior is None:
            msg = f"{invocation.system}.{invocation.tool} sin respuesta en el guion"
            raise McpToolError(msg)
        if isinstance(behavior, CarmenError):
            raise behavior
        return behavior if isinstance(behavior, McpEnvelope) else behavior(invocation)

    async def health(self, system: SystemId) -> SystemHealth:
        up = system in self._tools and system not in self._down
        status = HealthStatus.UP if up else HealthStatus.DOWN
        return SystemHealth(system=system, status=status, checked_at=self._clock.now())
