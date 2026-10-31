"""Ejecuciones de agente del turno (7.3.1): tabla agent_runs y su conversión.

Una ejecución guarda lo que el AgentRun del dominio no tiene y su AgentResult sí: la tarea, la
versión del agente y el estado. Sus llamadas, decisiones de política, llamadas externas y
aprobaciones viven en sus propias tablas, enlazadas por agent_run_id y ordenadas por run_ord.
"""

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from sqlalchemy import RowMapping

from carmen.adapters.persistence.types import (
    AGENT_RESULT_STATUS,
    MONEY,
    TIMESTAMP,
    instant,
    metadata,
)
from carmen.domain.approval.models import ApprovalRecord
from carmen.domain.delegation.models import (
    AgentResult,
    AgentRun,
    DelegationPlan,
    ExternalCallTrace,
    ToolCallTrace,
)
from carmen.domain.ids import AgentId, CallId, MessageId, RunId
from carmen.domain.policy.models import PolicyDecision
from carmen.domain.system import SystemId

agent_runs: Final = sa.Table(
    "agent_runs",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("message_id", sa.Text, nullable=False),
    sa.Column("ord", sa.Integer, nullable=False),
    sa.Column("task_id", sa.Text, nullable=False),
    sa.Column("agent_id", sa.Text, nullable=False),
    sa.Column("agent_version", sa.Text, nullable=False),
    sa.Column("status", AGENT_RESULT_STATUS, nullable=False),
    sa.Column("redelegated", sa.Boolean, nullable=False),
    sa.Column("started_at", TIMESTAMP, nullable=False),
    sa.Column("ended_at", TIMESTAMP, nullable=False),
    sa.Column("tokens_in", sa.Integer, nullable=False),
    sa.Column("tokens_out", sa.Integer, nullable=False),
    sa.Column("cost_eur", MONEY, nullable=False),
)


def run_row(
    message_id: MessageId, ord_: int, result: AgentResult, plan: DelegationPlan | None
) -> dict[str, object]:
    """Una tarea que no está en el plan del turno llegó por re-delegación (6.12.5)."""
    run = result.run
    planned = {t.task_id for t in plan.tasks} if plan is not None else set()
    return {
        "id": str(run.run_id),
        "message_id": str(message_id),
        "ord": ord_,
        "task_id": str(result.task_id),
        "agent_id": str(result.agent_id),
        "agent_version": result.agent_version,
        "status": result.status.value,
        "redelegated": result.task_id not in planned,
        "started_at": run.started_at.at,
        "ended_at": run.ended_at.at,
        "tokens_in": run.tokens_in,
        "tokens_out": run.tokens_out,
        "cost_eur": run.cost_eur,
    }


def trace_from_row(r: RowMapping) -> ToolCallTrace:
    return ToolCallTrace(
        call_id=CallId(r["call_id"]),
        system_id=SystemId(r["system_id"]),
        tool_name=r["tool_name"],
        ms=int(r["ms"] or 0),
        ok=bool(r["ok"]),
    )


def run_from_row(
    r: RowMapping,
    *,
    tool_calls: Sequence[ToolCallTrace],
    external: Sequence[ExternalCallTrace],
    policy_checks: Sequence[PolicyDecision],
    approvals: Sequence[ApprovalRecord],
) -> AgentRun:
    return AgentRun(
        run_id=RunId(r["id"]),
        agent_id=AgentId(r["agent_id"]),
        started_at=instant(r["started_at"]),
        ended_at=instant(r["ended_at"]),
        tokens_in=int(r["tokens_in"]),
        tokens_out=int(r["tokens_out"]),
        cost_eur=r["cost_eur"],
        tool_calls=tuple(tool_calls),
        external=tuple(external),
        policy_checks=tuple(policy_checks),
        approvals=tuple(approvals),
    )
