"""ApprovalRepository sobre PostgreSQL (6.12.6, 7.3.1).

Cada transición es una sola sentencia condicionada a `status = 'pending'`: dos decisiones
simultáneas no pueden ganar las dos. Además, un disparador de la base impide salir de un estado
que no sea pending aunque alguien escriba la tabla sin pasar por aquí.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from carmen.adapters.persistence.approvals import mappers
from carmen.adapters.persistence.approvals.tables import approvals
from carmen.adapters.persistence.engine import connection
from carmen.adapters.persistence.types import as_text
from carmen.application.ports.system import Clock
from carmen.domain.approval.models import ApprovalRecord, ApprovalStatus, HumanApprovalRequest
from carmen.domain.errors import InvalidTransitionError, ValidationError
from carmen.domain.ids import ApprovalId, PrincipalId
from carmen.domain.time import Instant

RECORD_COLUMNS = (
    approvals.c.id,
    approvals.c.status,
    as_text(approvals.c.evidence_refs).label("evidence_refs"),
    approvals.c.decided_by,
    approvals.c.decided_at,
)

_DECISIONS = (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED)


class PgApprovalRepository:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    async def create(self, request: HumanApprovalRequest) -> ApprovalRecord:
        created = await connection().execute(
            insert(approvals)
            .values(mappers.request_row(request, self._clock.now()))
            .on_conflict_do_nothing(index_elements=[approvals.c.id])
            .returning(*RECORD_COLUMNS)
        )
        row = created.mappings().one_or_none()
        if row is None:
            msg = f"la aprobación {request.request_id} ya existe"
            raise ValidationError(msg)
        return mappers.record_from_row(row)

    async def get(self, request_id: ApprovalId) -> ApprovalRecord | None:
        found = await connection().execute(
            sa.select(*RECORD_COLUMNS).where(approvals.c.id == str(request_id))
        )
        row = found.mappings().one_or_none()
        return None if row is None else mappers.record_from_row(row)

    async def decide(
        self, request_id: ApprovalId, status: ApprovalStatus, by: PrincipalId, at: Instant
    ) -> ApprovalRecord:
        if status not in _DECISIONS:
            msg = f"una persona aprueba o rechaza; {status} no es una decisión"
            raise InvalidTransitionError(msg)
        decided = await connection().execute(
            sa.update(approvals)
            .where(
                approvals.c.id == str(request_id),
                approvals.c.status == ApprovalStatus.PENDING.value,
                approvals.c.expires_at > at.at,
            )
            .values(status=status.value, decided_by=str(by), decided_at=at.at)
            .returning(*RECORD_COLUMNS)
        )
        row = decided.mappings().one_or_none()
        if row is not None:
            return mappers.record_from_row(row)
        if await self.get(request_id) is None:
            msg = f"la aprobación {request_id} no existe"
            raise ValidationError(msg)
        msg = f"{request_id} ya no está pendiente o su plazo venció"
        raise InvalidTransitionError(msg)

    async def expire_due(self, now: Instant) -> tuple[ApprovalId, ...]:
        expired = await connection().execute(
            sa.update(approvals)
            .where(
                approvals.c.status == ApprovalStatus.PENDING.value,
                approvals.c.expires_at <= now.at,
            )
            .values(status=ApprovalStatus.EXPIRED.value)
            .returning(approvals.c.id)
        )
        return tuple(sorted(ApprovalId(i) for i in expired.scalars()))
