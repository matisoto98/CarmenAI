"""AgentTask y DelegationPlan (6.12.3, 6.12.4): el modo y la composición se deducen solos."""

from collections.abc import Mapping
from decimal import Decimal

from carmen.domain.delegation.models import (
    AgentTask,
    Budgets,
    Composition,
    CompositionKind,
    DelegationPlan,
    Expects,
    TaskBudgets,
)
from carmen.domain.ids import AgentId, DelegationPlanId, PrincipalId, TaskId, TurnId
from carmen.domain.locale import Locale
from carmen.domain.orchestration.mode import ResponseMode
from support.builders.common import IDENTITY, POLICY_VERSION, PRINCIPAL, TURN, VIGIA, ZERO

TASK_BUDGET = TaskBudgets(max_wall_ms=10000, max_tokens=6000, max_cost_eur=ZERO)


def agent_task(
    number: int = 1,
    agent: AgentId = VIGIA,
    *,
    objective: str = "alarmas por estación del mes en curso, top 10",
    entities: Mapping[str, str] | None = None,
    expects: Expects = Expects.FACTS,
    deps: tuple[int, ...] = (),
    optional: bool = False,
    budgets: TaskBudgets = TASK_BUDGET,
) -> AgentTask:
    return AgentTask(
        task_id=TaskId(f"t{number}"),
        agent_id=agent,
        objective=objective,
        entities=entities if entities is not None else {"periodo": "mes_actual"},
        expects=expects,
        locale=Locale.ES,
        budgets=budgets,
        delegated_identity=IDENTITY,
        depends_on=tuple(TaskId(f"t{d}") for d in deps),
        optional=optional,
    )


def delegation_plan(
    *tasks: AgentTask,
    turn_id: TurnId = TURN,
    principal_id: PrincipalId = PRINCIPAL,
    composition: Composition | None = None,
    max_agents: int = 3,
    requires_human_approval: bool = False,
) -> DelegationPlan:
    """Una tarea: DELEGATE_SINGLE con composición single. Varias: DELEGATE_MULTI por bloques."""
    chosen = tasks or (agent_task(),)
    ids = tuple(t.task_id for t in chosen)
    single = len(chosen) == 1
    return DelegationPlan(
        plan_id=DelegationPlanId("dpl_7a3b9c1e4f20"),
        turn_id=turn_id,
        response_mode=ResponseMode.DELEGATE_SINGLE if single else ResponseMode.DELEGATE_MULTI,
        principal_id=principal_id,
        policy_version=POLICY_VERSION,
        tasks=chosen,
        composition=composition
        or Composition(CompositionKind.SINGLE if single else CompositionKind.BLOCKS, ids),
        budgets=Budgets(
            max_wall_ms=sum(t.budgets.max_wall_ms for t in chosen),
            max_tokens=sum(t.budgets.max_tokens for t in chosen),
            max_cost_eur=sum((t.budgets.max_cost_eur for t in chosen), start=Decimal(0)),
            max_agents=max_agents,
        ),
        requires_human_approval=requires_human_approval,
    )
