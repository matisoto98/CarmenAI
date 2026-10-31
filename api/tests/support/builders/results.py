"""Evidencia, ejecuciones, AgentResult y sobres MCP (6.3, 6.4, 6.12.4)."""

from decimal import Decimal

from carmen.application.ports.mcp import (
    ENVELOPE_VERSION,
    EnvelopeFact,
    EnvelopeWarning,
    McpEnvelope,
)
from carmen.domain.delegation.models import (
    AgentResult,
    AgentResultStatus,
    AgentRun,
    AgentTask,
    AgentWarning,
)
from carmen.domain.evidence.models import EvidenceFact, EvidenceItem, Provenance, Unit
from carmen.domain.ids import CallId, FactId, RunId
from carmen.domain.system import SystemId
from support.builders.common import CATALOG_VERSION, CORRELATION, VIGIA_SYSTEM, at

CALL = CallId("cal_7f3a9c1e2b40")


def evidence_fact(
    key: str = "monitores_ko",
    value: Decimal | int | str | bool | None = 4,
    *,
    system: SystemId = VIGIA_SYSTEM,
    call_id: CallId = CALL,
    label: str = "Monitores en KO",
    unit: Unit | None = Unit.COUNT,
) -> EvidenceFact:
    return EvidenceFact(
        fact_id=FactId(key),
        call_id=call_id,
        system_id=system,
        label=label,
        value=value,
        provenance=Provenance("query_metric", CATALOG_VERSION, at(1)),
        metric=key,
        unit=unit,
    )


def agent_run(task: AgentTask, *, seconds: float = 2, tokens_in: int = 0) -> AgentRun:
    agent = task.agent_id.removeprefix("agent.").replace("-", "").replace("_", "")
    return AgentRun(
        run_id=RunId(f"run_{task.task_id}{agent}"),
        agent_id=task.agent_id,
        started_at=at(),
        ended_at=at(seconds),
        tokens_in=tokens_in,
    )


def agent_result(
    task: AgentTask,
    status: AgentResultStatus = AgentResultStatus.OK,
    *,
    evidence: tuple[EvidenceItem, ...] | None = None,
    warnings: tuple[AgentWarning, ...] | None = None,
) -> AgentResult:
    """ok lleva un hecho; partial, un hecho y un aviso; el resto, nada (6.12.4)."""
    with_evidence = status in (AgentResultStatus.OK, AgentResultStatus.PARTIAL)
    default_warnings = (
        (AgentWarning("system_unavailable", "un sistema no respondió"),)
        if status is AgentResultStatus.PARTIAL
        else ()
    )
    return AgentResult(
        task_id=task.task_id,
        agent_id=task.agent_id,
        agent_version="1.0.0",
        status=status,
        run=agent_run(task),
        evidence=evidence
        if evidence is not None
        else ((evidence_fact(),) if with_evidence else ()),
        warnings=warnings if warnings is not None else default_warnings,
    )


def envelope(
    *facts: EnvelopeFact,
    system: SystemId = VIGIA_SYSTEM,
    tool: str = "query_metric",
    call_id: CallId = CALL,
    partial: bool = False,
) -> McpEnvelope:
    chosen = facts or (EnvelopeFact(key="monitores_ko", label="Monitores en KO", value=4),)
    return McpEnvelope(
        schema_version=ENVELOPE_VERSION,
        system_id=system,
        tool_name=tool,
        call_id=call_id,
        correlation_id=CORRELATION,
        generated_at=at(1),
        catalog_version=CATALOG_VERSION,
        facts=chosen,
        passages=(),
        media=(),
        warnings=(EnvelopeWarning("partial", "faltan datos de una estación"),) if partial else (),
        partial=partial,
    )
