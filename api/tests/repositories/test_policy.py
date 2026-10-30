"""Prompt 7: política persistida (7.9.7) con el mismo algoritmo que el doble en memoria (7.9.3)."""

import itertools

import pytest

from carmen.adapters.persistence.engine import Database
from carmen.adapters.persistence.policy.repository import PgPolicy, PgPolicyStore
from carmen.domain.ids import AgentId, PrincipalId, RoleId, Scope
from carmen.domain.policy.models import (
    AgentAction,
    AssignmentSource,
    Effect,
    PlatformAction,
    PolicyDecision,
    PolicyRole,
    Principal,
    RoleAgentGrant,
    RoleAssignment,
)
from repositories.pg import Pg
from support.builders import PLENDATA, POLICY_VERSION, TURN, VIGIA, at
from support.fakes.policy import InMemoryPolicy
from support.fakes.system import FrozenClock

pytestmark = pytest.mark.repositories

ANA = PrincipalId("usr_ana1")
BEA = PrincipalId("usr_bea2")
CAR = PrincipalId("usr_car3")
NOBODY = PrincipalId("usr_none")
GHOST = AgentId("agent.fantasma")
UNREACHABLE = "postgresql://carmen:carmen@127.0.0.1:1/carmen"  # pragma: allowlist secret

OPERATOR = RoleId("ops.operator")
AUDITOR = RoleId("ops.auditor")
ADMIN = RoleId("carmen.admin")

ROLES = (
    PolicyRole(OPERATOR, "Operación", frozenset({PlatformAction.TOPICS_READ}), "v1"),
    PolicyRole(AUDITOR, "Auditoría", frozenset({PlatformAction.AUDIT_READ}), "v1"),
    PolicyRole(
        ADMIN,
        "Administración",
        frozenset({PlatformAction.CARMEN_ADMIN, PlatformAction.AGENTS_MANAGE}),
        "v1",
    ),
)
ASSIGNMENTS = (
    RoleAssignment(ANA, OPERATOR, AssignmentSource.DIRECTORY),
    RoleAssignment(BEA, OPERATOR, AssignmentSource.DIRECTORY),
    RoleAssignment(BEA, AUDITOR, AssignmentSource.MANUAL),
    RoleAssignment(CAR, ADMIN, AssignmentSource.MANUAL),
)
GRANTS = (
    RoleAgentGrant(
        OPERATOR,
        VIGIA,
        frozenset(AgentAction),
        Effect.ALLOW,
        frozenset({Scope("vigia.read.limited")}),
    ),
    RoleAgentGrant(
        OPERATOR,
        PLENDATA,
        frozenset({AgentAction.DISCOVER, AgentAction.DESCRIBE}),
        Effect.ALLOW,
        frozenset({Scope("plendata.read")}),
    ),
    RoleAgentGrant(
        AUDITOR,
        VIGIA,
        frozenset({AgentAction.INVOKE}),
        Effect.DENY,
        reason="auditoría no ejecuta consultas operativas",
    ),
    RoleAgentGrant(
        AUDITOR,
        PLENDATA,
        frozenset({AgentAction.DESCRIBE, AgentAction.INVOKE}),
        Effect.ALLOW,
        frozenset({Scope("plendata.audit")}),
    ),
)


def principal(pid: PrincipalId, *, active: bool = True) -> Principal:
    return Principal(pid, f"entra:{pid}", str(pid), active)


async def seed(db: Database) -> None:
    store = PgPolicyStore()
    async with db.unit_of_work():
        for pid in (ANA, BEA, CAR):
            await store.save_principal(principal(pid), at())
        for role in ROLES:
            await store.save_role(role)
        for assignment in ASSIGNMENTS:
            await store.assign(assignment, at())
        for grant in GRANTS:
            await store.grant(grant)


def memory_policy() -> InMemoryPolicy:
    return InMemoryPolicy(
        version=POLICY_VERSION, roles=ROLES, assignments=ASSIGNMENTS, grants=GRANTS
    )


def test_postgres_policy_decides_exactly_like_the_reference_algorithm(pg: Pg) -> None:
    reference = memory_policy()

    async def scenario(db: Database) -> int:
        await seed(db)
        policy = PgPolicy(db.engine, version=POLICY_VERSION, clock=FrozenClock())
        assert policy.version() == POLICY_VERSION
        compared = 0
        people = (ANA, BEA, CAR, NOBODY)
        for who, action, agent in itertools.product(people, AgentAction, (VIGIA, PLENDATA, GHOST)):
            got = await policy.decide(principal_id=who, action=action, agent_id=agent, turn_id=TURN)
            expected = await reference.decide(
                principal_id=who, action=action, agent_id=agent, turn_id=TURN
            )
            assert got == expected, (who, action, agent)
            compared += 1
        for who, platform in itertools.product(people, PlatformAction):
            got = await policy.decide_platform(principal_id=who, action=platform, turn_id=TURN)
            expected = await reference.decide_platform(
                principal_id=who, action=platform, turn_id=TURN
            )
            assert got == expected, (who, platform)
            compared += 1
        for who, action in itertools.product(people, AgentAction):
            agents = await policy.allowed_agents(principal_id=who, action=action, turn_id=TURN)
            assert agents == await reference.allowed_agents(
                principal_id=who, action=action, turn_id=TURN
            ), (who, action)
            compared += 1
        return compared

    assert pg.run(scenario) == 4 * 3 * 3 + 4 * len(PlatformAction) + 4 * 3


def test_explicit_deny_wins_and_scopes_are_united(pg: Pg) -> None:
    async def scenario(db: Database) -> None:
        await seed(db)
        policy = PgPolicy(db.engine, version=POLICY_VERSION, clock=FrozenClock())
        denied = await policy.decide(
            principal_id=BEA, action=AgentAction.INVOKE, agent_id=VIGIA, turn_id=TURN
        )
        assert (denied.decision, denied.reason_code) == (Effect.DENY, "explicit_deny")
        allowed = await policy.decide(
            principal_id=BEA, action=AgentAction.DESCRIBE, agent_id=PLENDATA, turn_id=TURN
        )
        assert allowed.scopes == {Scope("plendata.read"), Scope("plendata.audit")}
        admin = await policy.decide(
            principal_id=CAR, action=AgentAction.DISCOVER, agent_id=VIGIA, turn_id=TURN
        )
        assert (admin.decision, admin.reason_code) == (Effect.DENY, "no_grant")  # 7.9.4

    pg.run(scenario)


def test_an_inactive_principal_has_no_roles(pg: Pg) -> None:
    async def scenario(db: Database) -> None:
        await seed(db)
        async with db.unit_of_work():
            await PgPolicyStore().save_principal(principal(ANA, active=False), at(5))
        policy = PgPolicy(db.engine, version=POLICY_VERSION, clock=FrozenClock())
        decision = await policy.decide(
            principal_id=ANA, action=AgentAction.INVOKE, agent_id=VIGIA, turn_id=TURN
        )
        assert (decision.decision, decision.reason_code) == (Effect.DENY, "no_grant")
        platform = await policy.decide_platform(
            principal_id=ANA, action=PlatformAction.TOPICS_READ, turn_id=TURN
        )
        assert platform.reason_code == "no_role"

    pg.run(scenario)


def test_an_unreachable_policy_denies_instead_of_raising(pg: Pg) -> None:
    async def scenario(db: Database) -> None:
        broken = Database(UNREACHABLE)
        try:
            policy = PgPolicy(broken.engine, version=POLICY_VERSION, clock=FrozenClock())
            decision = await policy.decide(
                principal_id=ANA, action=AgentAction.INVOKE, agent_id=VIGIA, turn_id=TURN
            )
            platform = await policy.decide_platform(
                principal_id=ANA, action=PlatformAction.KPIS_READ, turn_id=TURN
            )
            agents = await policy.allowed_agents(
                principal_id=ANA, action=AgentAction.DISCOVER, turn_id=TURN
            )
        finally:
            await broken.dispose()
        assert (decision.decision, decision.reason_code) == (Effect.DENY, "policy_unavailable")
        assert (platform.decision, platform.reason_code) == (Effect.DENY, "policy_unavailable")
        assert agents == ()

    pg.run(scenario)


def test_decisions_are_recorded_with_their_policy_version(pg: Pg) -> None:
    decision = PolicyDecision(
        turn_id=TURN,
        principal_id=ANA,
        action=AgentAction.INVOKE,
        decision=Effect.DENY,
        reason_code="explicit_deny",
        policy_version=POLICY_VERSION,
        decided_at=at(7),
        agent_id=VIGIA,
    )
    platform = PolicyDecision(
        turn_id=TURN,
        principal_id=CAR,
        action=PlatformAction.CARMEN_ADMIN,
        decision=Effect.ALLOW,
        reason_code="platform_role",
        policy_version=POLICY_VERSION,
        decided_at=at(8),
    )

    async def scenario(db: Database) -> None:
        async with db.unit_of_work():
            await PgPolicyStore().record(decision)
            await PgPolicyStore().record(platform)

    pg.run(scenario)
    rows = pg.fetch(
        "SELECT turn_id, principal_id, agent_id, action, decision, reason_code, policy_version,"
        " decided_at FROM carmen.policy_decisions ORDER BY decided_at"
    )
    assert [tuple(r.values()) for r in rows] == [
        (
            str(TURN),
            "usr_ana1",
            "agent.vigia",
            "invoke",
            "deny",
            "explicit_deny",
            POLICY_VERSION,
            at(7).at,
        ),
        (
            str(TURN),
            "usr_car3",
            None,
            "carmen.admin",
            "allow",
            "platform_role",
            POLICY_VERSION,
            at(8).at,
        ),
    ]


def test_saving_policy_twice_replaces_rows_instead_of_duplicating(pg: Pg) -> None:
    async def scenario(db: Database) -> None:
        await seed(db)
        await seed(db)

    pg.run(scenario)
    assert len(pg.fetch("SELECT 1 FROM carmen.role_agent_grants")) == len(GRANTS)
    assert len(pg.fetch("SELECT 1 FROM carmen.role_assignments")) == len(ASSIGNMENTS)
    assert len(pg.fetch("SELECT 1 FROM carmen.principals")) == 3
