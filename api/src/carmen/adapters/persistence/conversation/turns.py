"""TurnRepository sobre PostgreSQL (6.12.8, 7.3.1, unidad de trabajo 1 de 7.4).

El mensaje del asistente ES el turno: `save` completa ese mensaje con las columnas de 0002 y
escribe, en la unidad de trabajo en curso, las ejecuciones, el enlace de cada llamada con su
ejecución, las decisiones de política, las llamadas externas, la evidencia y el anclaje. Si algo
falla, la unidad de trabajo deshace también el mensaje: el turno se guarda entero o no se guarda.

`get` reconstruye un ConversationTurn igual al guardado. Para eso cada fila lleva su orden
(`ord` en el turno, `run_ord` en la ejecución) y nada se deduce de un orden implícito.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from carmen.adapters.persistence.approvals.mappers import record_from_row
from carmen.adapters.persistence.approvals.repository import RECORD_COLUMNS
from carmen.adapters.persistence.approvals.tables import approvals
from carmen.adapters.persistence.conversation import evidence
from carmen.adapters.persistence.conversation.agent_runs import (
    agent_runs,
    run_from_row,
    run_row,
    trace_from_row,
)
from carmen.adapters.persistence.conversation.delegation_plan import plan_from_json, plan_to_json
from carmen.adapters.persistence.conversation.external_calls import (
    external_calls,
    external_from_row,
    external_row,
)
from carmen.adapters.persistence.conversation.tables import (
    conversations,
    evidence_facts,
    evidence_media,
    evidence_passages,
    grounding_claims,
    messages,
    tool_calls,
)
from carmen.adapters.persistence.engine import connection
from carmen.adapters.persistence.policy.mappers import decision_from_row, decision_values
from carmen.adapters.persistence.policy.tables import policy_decisions
from carmen.adapters.persistence.types import as_text
from carmen.domain.approval.models import ApprovalRecord
from carmen.domain.conversation.turn import ConversationTurn, TokenUsage, TurnStatus
from carmen.domain.delegation.models import AgentResult, AgentRun
from carmen.domain.errors import ValidationError
from carmen.domain.evidence.grounding import GroundingClaim, GroundingResult
from carmen.domain.evidence.models import EvidenceFact, EvidenceItem, EvidencePassage
from carmen.domain.ids import AgentId, ConversationId, MessageId, PrincipalId, TurnId
from carmen.domain.orchestration.mode import ResponseMode

_ASSISTANT = "assistant"
_USER = "user"


@dataclass(frozen=True, slots=True)
class _StoredCall:
    """Una llamada guardada con el mensaje: su fila interna y lo que la traza debe repetir."""

    row_id: UUID
    row: RowMapping


class PgTurnRepository:
    """Escribe en la unidad de trabajo en curso, la misma en la que se guardó el mensaje."""

    async def save(
        self,
        turn: ConversationTurn,
        *,
        message_id: MessageId,
        results: Sequence[AgentResult] = (),
    ) -> None:
        if tuple(r.run for r in results) != turn.runs:
            msg = f"los resultados no corresponden a las ejecuciones del turno {turn.turn_id}"
            raise ValidationError(msg)
        conn = connection()
        answer = await self._lock_answer(conn, turn, message_id)
        await self._check_question(conn, turn, answer)
        stored_approvals = await self._check_approvals(conn, turn)
        if answer["turn_id"] is not None or await self._turn_exists(conn, turn.turn_id):
            msg = f"el turno de {message_id} ya está guardado y no se reescribe"
            raise ValidationError(msg)
        await self._write_turn(conn, turn, message_id)
        calls = await self._stored_calls(conn, message_id)
        for ord_, result in enumerate(results, start=1):
            await self._write_run(conn, turn, message_id, ord_, result, calls, stored_approvals)
        await self._write_evidence(conn, turn, message_id, calls)

    # --- comprobaciones ------------------------------------------------------------------

    async def _lock_answer(
        self, conn: AsyncConnection, turn: ConversationTurn, message_id: MessageId
    ) -> RowMapping:
        found = await conn.execute(
            sa.select(
                messages.c.id,
                messages.c.conversation_id,
                messages.c.seq,
                messages.c.role,
                messages.c.status,
                messages.c.turn_id,
                conversations.c.user_id,
            )
            .join(conversations, conversations.c.id == messages.c.conversation_id)
            .where(messages.c.id == str(message_id))
            .with_for_update(of=messages)
        )
        answer = found.mappings().one_or_none()
        if answer is None:
            msg = f"el mensaje {message_id} no existe: el turno se guarda con su respuesta"
            raise ValidationError(msg)
        if answer["role"] != _ASSISTANT:
            msg = f"el turno es la respuesta del asistente; {message_id} es de {answer['role']}"
            raise ValidationError(msg)
        if answer["conversation_id"] != str(turn.conversation_id):
            msg = f"el mensaje {message_id} es de otra conversación"
            raise ValidationError(msg)
        if answer["user_id"] != str(turn.principal_id):
            msg = f"la conversación de {message_id} es de otro principal"
            raise ValidationError(msg)
        if TurnStatus(answer["status"]) is not turn.status:
            msg = (
                f"el estado del turno ({turn.status}) no es el de su respuesta ({answer['status']})"
            )
            raise ValidationError(msg)
        return answer

    async def _check_question(
        self, conn: AsyncConnection, turn: ConversationTurn, answer: RowMapping
    ) -> None:
        question = await conn.scalar(
            sa.select(messages.c.content)
            .where(
                messages.c.conversation_id == answer["conversation_id"],
                messages.c.role == _USER,
                messages.c.seq < answer["seq"],
            )
            .order_by(messages.c.seq.desc())
            .limit(1)
        )
        if question != turn.question:
            msg = f"la pregunta del turno {turn.turn_id} no es el mensaje que respondió"
            raise ValidationError(msg)

    async def _check_approvals(
        self, conn: AsyncConnection, turn: ConversationTurn
    ) -> dict[str, ApprovalRecord]:
        """El turno lleva sus aprobaciones tal como están guardadas, ni una más ni una menos."""
        found = await conn.execute(
            sa.select(*RECORD_COLUMNS)
            .where(approvals.c.turn_id == str(turn.turn_id))
            .order_by(approvals.c.created_at, approvals.c.id)
        )
        stored = tuple(record_from_row(r) for r in found.mappings())
        if stored != turn.approvals:
            ids = sorted({str(a.request_id) for a in (*stored, *turn.approvals)})
            msg = f"las aprobaciones del turno no son las guardadas: {ids}"
            raise ValidationError(msg)
        by_id = {str(a.request_id): a for a in stored}
        for run in turn.runs:
            for record in run.approvals:
                if by_id.get(str(record.request_id)) != record:
                    msg = (
                        f"la aprobación {record.request_id} de {run.run_id} no es la guardada"
                        " para este turno"
                    )
                    raise ValidationError(msg)
        return by_id

    async def _turn_exists(self, conn: AsyncConnection, turn_id: TurnId) -> bool:
        found = await conn.scalar(
            sa.select(sa.literal(1)).where(messages.c.turn_id == str(turn_id))
        )
        return found is not None

    # --- escritura -----------------------------------------------------------------------

    async def _write_turn(
        self, conn: AsyncConnection, turn: ConversationTurn, message_id: MessageId
    ) -> None:
        grounding = turn.grounding
        await conn.execute(
            sa.update(messages)
            .where(messages.c.id == str(message_id))
            .values(
                turn_id=str(turn.turn_id),
                response_mode=turn.response_mode.value,
                policy_version=turn.policy_version,
                delegation_plan=(
                    None if turn.delegation_plan is None else plan_to_json(turn.delegation_plan)
                ),
                agents_used=[str(a) for a in turn.agents_used],
                missing_agents=[str(a) for a in turn.missing_agents],
                redelegations=turn.redelegations,
                cost_eur=turn.cost_eur,
                tokens_in=turn.tokens.tokens_in,
                tokens_out=turn.tokens.tokens_out,
                latency_ms=turn.latency_ms,
                grounding_ok=None if grounding is None else grounding.ok,
                grounding_unsupported=0 if grounding is None else len(grounding.unsupported),
            )
        )

    async def _stored_calls(
        self, conn: AsyncConnection, message_id: MessageId
    ) -> dict[str, _StoredCall]:
        found = await conn.execute(
            sa.select(
                tool_calls.c.id,
                tool_calls.c.call_id,
                tool_calls.c.system_id,
                tool_calls.c.tool_name,
                tool_calls.c.ms,
                tool_calls.c.ok,
            ).where(tool_calls.c.message_id == str(message_id))
        )
        return {r["call_id"]: _StoredCall(r["id"], r) for r in found.mappings()}

    async def _write_run(
        self,
        conn: AsyncConnection,
        turn: ConversationTurn,
        message_id: MessageId,
        ord_: int,
        result: AgentResult,
        calls: dict[str, _StoredCall],
        stored_approvals: dict[str, ApprovalRecord],
    ) -> None:
        run = result.run
        run_id = str(run.run_id)
        await conn.execute(
            sa.insert(agent_runs).values(run_row(message_id, ord_, result, turn.delegation_plan))
        )
        for run_ord, trace in enumerate(run.tool_calls, start=1):
            stored = calls.get(str(trace.call_id))
            if stored is None or trace_from_row(stored.row) != trace:
                msg = f"la traza {trace.call_id} de {run_id} no coincide con la llamada guardada"
                raise ValidationError(msg)
            await conn.execute(
                sa.update(tool_calls)
                .where(tool_calls.c.id == stored.row_id)
                .values(agent_run_id=run_id, run_ord=run_ord)
            )
        if run.policy_checks:
            await conn.execute(
                sa.insert(policy_decisions),
                [
                    {**decision_values(d), "agent_run_id": run_id, "run_ord": n}
                    for n, d in enumerate(run.policy_checks, start=1)
                ],
            )
        if run.external:
            await conn.execute(
                sa.insert(external_calls),
                [external_row(run.run_id, n, e) for n, e in enumerate(run.external, start=1)],
            )
        for record in run.approvals:
            if str(record.request_id) in stored_approvals:
                await conn.execute(
                    sa.update(approvals)
                    .where(approvals.c.id == str(record.request_id))
                    .values(agent_run_id=run_id)
                )

    async def _write_evidence(
        self,
        conn: AsyncConnection,
        turn: ConversationTurn,
        message_id: MessageId,
        calls: dict[str, _StoredCall],
    ) -> None:
        def call_row(item: EvidenceItem) -> UUID:
            stored = calls.get(str(item.call_id))
            if stored is None:
                msg = f"evidencia de una llamada que no es del mensaje {message_id}: {item.call_id}"
                raise ValidationError(msg)
            return stored.row_id

        facts, passages, media = [], [], []
        for ord_, item in enumerate(turn.evidence, start=1):
            row_id = call_row(item)
            if isinstance(item, EvidenceFact):
                facts.append(evidence.fact_row(message_id, row_id, ord_, item))
            elif isinstance(item, EvidencePassage):
                passages.append(evidence.passage_row(message_id, row_id, ord_, item))
            else:
                media.append(evidence.media_row(message_id, row_id, ord_, item))
        for table, rows in (
            (evidence_facts, facts),
            (evidence_passages, passages),
            (evidence_media, media),
        ):
            if rows:
                await conn.execute(sa.insert(table), rows)
        if turn.grounding is not None and turn.grounding.claims:
            await self._write_claims(conn, turn.grounding, message_id, calls)

    async def _write_claims(
        self,
        conn: AsyncConnection,
        grounding: GroundingResult,
        message_id: MessageId,
        calls: dict[str, _StoredCall],
    ) -> None:
        found = await conn.execute(
            sa.select(
                evidence_facts.c.id, evidence_facts.c.tool_call_id, evidence_facts.c.fact_key
            ).where(evidence_facts.c.message_id == str(message_id))
        )
        fact_rows = {(r.tool_call_id, r.fact_key): r.id for r in found}
        rows = []
        for ord_, claim in enumerate(grounding.claims, start=1):
            fact_row_id = None
            support = claim.supported_by
            if support is not None:
                stored = calls.get(str(support.call_id))
                key = None if stored is None else (stored.row_id, str(support.fact_id))
                fact_row_id = fact_rows.get(key) if key is not None else None
                if fact_row_id is None:
                    msg = (
                        f"la afirmación {claim.claim_id} se apoya en un hecho que no está en el"
                        f" turno: {support.call_id}/{support.fact_id}"
                    )
                    raise ValidationError(msg)
            rows.append(evidence.claim_row(message_id, ord_, claim, fact_row_id))
        await conn.execute(sa.insert(grounding_claims), rows)

    # --- lectura -------------------------------------------------------------------------

    async def get(self, turn_id: TurnId) -> ConversationTurn | None:
        conn = connection()
        asked = messages.alias("asked")
        question = (
            sa.select(asked.c.content)
            .where(
                asked.c.conversation_id == messages.c.conversation_id,
                asked.c.role == _USER,
                asked.c.seq < messages.c.seq,
            )
            .order_by(asked.c.seq.desc())
            .limit(1)
            .scalar_subquery()
        )
        found = await conn.execute(
            sa.select(
                messages,
                as_text(messages.c.delegation_plan).label("plan_text"),
                conversations.c.user_id,
                question.label("question"),
            )
            .join(conversations, conversations.c.id == messages.c.conversation_id)
            .where(messages.c.turn_id == str(turn_id))
        )
        m = found.mappings().one_or_none()
        if m is None:
            return None
        message_id = MessageId(m["id"])
        return ConversationTurn(
            turn_id=turn_id,
            conversation_id=ConversationId(m["conversation_id"]),
            principal_id=PrincipalId(m["user_id"]),
            question=m["question"],
            response_mode=ResponseMode(m["response_mode"]),
            policy_version=m["policy_version"],
            status=TurnStatus(m["status"]),
            agents_used=tuple(AgentId(a) for a in m["agents_used"]),
            delegation_plan=None if m["plan_text"] is None else plan_from_json(m["plan_text"]),
            runs=await self._runs(conn, message_id),
            evidence=await self._evidence(conn, message_id),
            grounding=(
                None
                if m["grounding_ok"] is None
                else GroundingResult.of(await self._claims(conn, message_id))
            ),
            approvals=await self._approvals(conn, approvals.c.turn_id == str(turn_id)),
            tokens=TokenUsage(int(m["tokens_in"] or 0), int(m["tokens_out"] or 0)),
            cost_eur=m["cost_eur"],
            latency_ms=int(m["latency_ms"] or 0),
            missing_agents=tuple(AgentId(a) for a in m["missing_agents"]),
            redelegations=int(m["redelegations"]),
        )

    async def _approvals(
        self, conn: AsyncConnection, where: sa.ColumnElement[bool]
    ) -> tuple[ApprovalRecord, ...]:
        found = await conn.execute(
            sa.select(*RECORD_COLUMNS).where(where).order_by(approvals.c.created_at, approvals.c.id)
        )
        return tuple(record_from_row(r) for r in found.mappings())

    async def _runs(self, conn: AsyncConnection, message_id: MessageId) -> tuple[AgentRun, ...]:
        found = await conn.execute(
            sa.select(agent_runs)
            .where(agent_runs.c.message_id == str(message_id))
            .order_by(agent_runs.c.ord)
        )
        runs = []
        for r in found.mappings().all():
            run_id = r["id"]
            traces = await conn.execute(
                sa.select(
                    tool_calls.c.call_id,
                    tool_calls.c.system_id,
                    tool_calls.c.tool_name,
                    tool_calls.c.ms,
                    tool_calls.c.ok,
                )
                .where(tool_calls.c.agent_run_id == run_id)
                .order_by(tool_calls.c.run_ord)
            )
            external = await conn.execute(
                sa.select(external_calls)
                .where(external_calls.c.agent_run_id == run_id)
                .order_by(external_calls.c.run_ord)
            )
            checks = await conn.execute(
                sa.select(policy_decisions)
                .where(policy_decisions.c.agent_run_id == run_id)
                .order_by(policy_decisions.c.run_ord)
            )
            runs.append(
                run_from_row(
                    r,
                    tool_calls=[trace_from_row(t) for t in traces.mappings()],
                    external=[external_from_row(e) for e in external.mappings()],
                    policy_checks=[decision_from_row(d) for d in checks.mappings()],
                    approvals=await self._approvals(conn, approvals.c.agent_run_id == run_id),
                )
            )
        return tuple(runs)

    async def _evidence(
        self, conn: AsyncConnection, message_id: MessageId
    ) -> tuple[EvidenceItem, ...]:
        call_id = tool_calls.c.call_id.label("call_id")
        facts = await conn.execute(
            sa.select(
                *(c for c in evidence_facts.c if c.name not in ("dimensions", "period")),
                as_text(evidence_facts.c.dimensions).label("dimensions"),
                as_text(evidence_facts.c.period).label("period"),
                call_id,
            )
            .join(tool_calls, tool_calls.c.id == evidence_facts.c.tool_call_id)
            .where(evidence_facts.c.message_id == str(message_id))
        )
        passages = await conn.execute(
            sa.select(evidence_passages, call_id)
            .join(tool_calls, tool_calls.c.id == evidence_passages.c.tool_call_id)
            .where(evidence_passages.c.message_id == str(message_id))
        )
        media = await conn.execute(
            sa.select(evidence_media, call_id)
            .join(tool_calls, tool_calls.c.id == evidence_media.c.tool_call_id)
            .where(evidence_media.c.message_id == str(message_id))
        )
        items: list[tuple[int, EvidenceItem]] = [
            *((int(r["ord"]), evidence.fact_from_row(r)) for r in facts.mappings()),
            *((int(r["ord"]), evidence.passage_from_row(r)) for r in passages.mappings()),
            *((int(r["ord"]), evidence.media_from_row(r)) for r in media.mappings()),
        ]
        return tuple(item for _, item in sorted(items, key=lambda pair: pair[0]))

    async def _claims(
        self, conn: AsyncConnection, message_id: MessageId
    ) -> tuple[GroundingClaim, ...]:
        found = await conn.execute(
            sa.select(
                grounding_claims,
                tool_calls.c.call_id.label("support_call_id"),
                evidence_facts.c.fact_key.label("support_fact_key"),
            )
            .outerjoin(evidence_facts, evidence_facts.c.id == grounding_claims.c.fact_id)
            .outerjoin(tool_calls, tool_calls.c.id == evidence_facts.c.tool_call_id)
            .where(grounding_claims.c.message_id == str(message_id))
            .order_by(grounding_claims.c.ord)
        )
        return tuple(evidence.claim_from_row(r) for r in found.mappings())
