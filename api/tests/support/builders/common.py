"""Valores fijos que comparten los constructores: el mismo turno, la misma persona, el mismo día."""

from datetime import timedelta
from decimal import Decimal
from typing import Final

from carmen.application.context import ExecutionContext, Requester, UserToken
from carmen.domain.ids import (
    AgentId,
    ConversationId,
    CorrelationId,
    DelegatedIdentityRef,
    MessageId,
    PrincipalId,
    TurnId,
)
from carmen.domain.locale import Locale
from carmen.domain.role import Role
from carmen.domain.system import SystemId
from carmen.domain.time import Instant
from support.fakes.llm import FAKE_DESCRIPTOR
from support.fakes.system import EPOCH

VIGIA: Final = AgentId("agent.vigia")
PLENDATA: Final = AgentId("agent.plendata")
VIGIA_SYSTEM: Final = SystemId("vigia")
PLENDATA_SYSTEM: Final = SystemId("plendata")
PRINCIPAL: Final = PrincipalId("usr_a91f")
TURN: Final = TurnId("trn_18ab44de")
CONVERSATION: Final = ConversationId("cnv_0001")
MESSAGE: Final = MessageId("msg_0001")
CORRELATION: Final = CorrelationId("cor_7f3a9c1e")
IDENTITY: Final = DelegatedIdentityRef("idr_7f3a9c1e2b40")
POLICY_VERSION: Final = "pol-2026-07-21"
CATALOG_VERSION: Final = "2026-07-20"
ZERO: Final = Decimal(0)


def at(seconds: float = 0) -> Instant:
    """EPOCH más `seconds`: el mismo eje de tiempo que FrozenClock."""
    return Instant(EPOCH.at + timedelta(seconds=seconds))


def requester(principal_id: PrincipalId = PRINCIPAL, role: Role = Role.OPERATOR) -> Requester:
    return Requester(principal_id=principal_id, role=role, token=UserToken("user-token-fixture"))


def execution_context(
    *,
    principal_id: PrincipalId = PRINCIPAL,
    role: Role = Role.OPERATOR,
    locale: Locale = Locale.ES,
    deadline_seconds: float | None = 30,
) -> ExecutionContext:
    return ExecutionContext(
        correlation_id=CORRELATION,
        conversation_id=CONVERSATION,
        message_id=MESSAGE,
        requester=requester(principal_id, role),
        locale=locale,
        started_at=at(),
        llm=FAKE_DESCRIPTOR,
        prompt_hash="ph_fixture",
        catalog_versions={VIGIA_SYSTEM: CATALOG_VERSION},
        deadline=None if deadline_seconds is None else at(deadline_seconds),
    )
