"""Llamadas externas de una ejecución (5.15.7): tabla external_calls y su conversión.

En v1 la tabla debe seguir vacía. La traza del dominio no lleva todavía la decisión de
exportación (6.12.7): export_decision queda nulo hasta que la escriba el egreso (ADR-049).
"""

from typing import Final

import sqlalchemy as sa
from sqlalchemy import RowMapping

from carmen.adapters.persistence.types import JSONB, MONEY, TEXT_ARRAY, TIMESTAMP, instant, metadata
from carmen.domain.delegation.models import ExternalCallTrace
from carmen.domain.ids import ProviderId, RunId

external_calls: Final = sa.Table(
    "external_calls",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
    sa.Column("agent_run_id", sa.Text, nullable=False),
    sa.Column("run_ord", sa.Integer, nullable=False),
    sa.Column("provider", sa.Text),
    sa.Column("model", sa.Text),
    sa.Column("model_version", sa.Text),
    sa.Column("domains", TEXT_ARRAY, nullable=False),
    sa.Column("sources_accepted", JSONB, nullable=False),
    sa.Column("sources_rejected", JSONB, nullable=False),
    sa.Column("egress_policy_id", sa.Text, nullable=False),
    sa.Column("export_decision", JSONB),
    sa.Column("redactions", TEXT_ARRAY, nullable=False),
    sa.Column("tokens", sa.Integer, nullable=False),
    sa.Column("cost_eur", MONEY, nullable=False),
    sa.Column("retrieved_at", TIMESTAMP, nullable=False),
)


def external_row(run_id: RunId, ord_: int, e: ExternalCallTrace) -> dict[str, object]:
    return {
        "agent_run_id": str(run_id),
        "run_ord": ord_,
        "provider": None if e.provider is None else str(e.provider),
        "domains": [] if e.domain is None else [e.domain],
        "egress_policy_id": e.policy_id,
        "redactions": list(e.redactions),
        "tokens": e.tokens,
        "cost_eur": e.cost_eur,
        "retrieved_at": e.at.at,
    }


def external_from_row(r: RowMapping) -> ExternalCallTrace:
    domains = list(r["domains"])
    return ExternalCallTrace(
        policy_id=r["egress_policy_id"],
        at=instant(r["retrieved_at"]),
        provider=None if r["provider"] is None else ProviderId(r["provider"]),
        domain=domains[0] if domains else None,
        redactions=tuple(r["redactions"]),
        tokens=int(r["tokens"]),
        cost_eur=r["cost_eur"],
    )
