"""QueryPlan locales de un agente (6.2), con valores válidos por defecto."""

from collections.abc import Mapping

from carmen.domain.ids import AgentId, PlanId, StepId
from carmen.domain.plan.models import (
    ArgumentValue,
    CrossJoin,
    Intent,
    PlanLimits,
    PlanStep,
    QueryPlan,
    StepDependency,
)
from carmen.domain.system import SystemId
from support.builders.common import CATALOG_VERSION, VIGIA, VIGIA_SYSTEM


def plan_step(
    number: int = 1,
    *,
    tool: str = "query_metric",
    agent: AgentId = VIGIA,
    system: SystemId = VIGIA_SYSTEM,
    arguments: Mapping[str, ArgumentValue] | None = None,
    deps: tuple[int, ...] = (),
    optional: bool = False,
) -> PlanStep:
    return PlanStep(
        step_id=StepId(f"s{number}"),
        agent=agent,
        system=system,
        tool=tool,
        arguments=arguments if arguments is not None else {"metric": "monitores_ko"},
        depends_on=tuple(StepDependency(StepId(f"s{d}")) for d in deps),
        optional=optional,
    )


def query_plan(
    *steps: PlanStep,
    plan_id: str = "pln_a1b2c3d4e5f6",
    intent: Intent = Intent.FACTUAL,
    max_rounds: int = 1,
    join: CrossJoin | None = None,
) -> QueryPlan:
    chosen = steps or (plan_step(),)
    return QueryPlan(
        plan_id=PlanId(plan_id),
        intent=intent,
        steps=chosen,
        catalog_versions={s.system: CATALOG_VERSION for s in chosen},
        limits=PlanLimits(max_rounds=max_rounds, max_tool_calls=max(2, len(chosen)), max_repairs=2),
        join=join,
    )
