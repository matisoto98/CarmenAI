"""Ciclo de vida: tabla ⇄ dominio."""

from sqlalchemy import RowMapping

from carmen.adapters.persistence.types import instant
from carmen.application.ports.repositories import AgentLifecycleEntry, LifecycleChange
from carmen.domain.agents.card import AgentLifecycleState
from carmen.domain.ids import AgentId, PrincipalId


def entry_values(e: AgentLifecycleEntry) -> dict[str, object]:
    return {
        "agent_id": str(e.agent_id),
        "state": e.state.value,
        "version": e.version,
        "owner": e.owner,
        "certified_at": None if e.certified_at is None else e.certified_at.at,
        "report_ref": e.report_ref,
        "updated_at": e.updated_at.at,
    }


def entry_from_row(r: RowMapping) -> AgentLifecycleEntry:
    return AgentLifecycleEntry(
        agent_id=AgentId(r["agent_id"]),
        state=AgentLifecycleState(r["state"]),
        version=r["version"],
        updated_at=instant(r["updated_at"]),
        owner=r["owner"],
        certified_at=None if r["certified_at"] is None else instant(r["certified_at"]),
        report_ref=r["report_ref"],
    )


def change_values(c: LifecycleChange) -> dict[str, object]:
    return {
        "agent_id": str(c.agent_id),
        "from_state": None if c.from_state is None else c.from_state.value,
        "to_state": c.to_state.value,
        "reason": c.reason,
        "actor": str(c.actor),
        "at": c.at.at,
    }


def change_from_row(r: RowMapping) -> LifecycleChange:
    return LifecycleChange(
        agent_id=AgentId(r["agent_id"]),
        from_state=None if r["from_state"] is None else AgentLifecycleState(r["from_state"]),
        to_state=AgentLifecycleState(r["to_state"]),
        reason=r["reason"],
        actor=PrincipalId(r["actor"]),
        at=instant(r["at"]),
    )
