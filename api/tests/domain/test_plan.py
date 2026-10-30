"""Prompt 2: construcción y rechazo de planes, ciclos y oleadas de ejecución (6.2)."""

from collections.abc import Mapping
from decimal import Decimal

import pytest

from carmen.domain.errors import InvalidPlanError, ValidationError
from carmen.domain.ids import AgentId, PlanId, StepId
from carmen.domain.plan.models import (
    MAX_STEPS,
    ArgumentValue,
    CrossJoin,
    FactReference,
    Intent,
    PlanLimits,
    PlanStep,
    QueryPlan,
    StepDependency,
)
from carmen.domain.system import SystemId

pytestmark = pytest.mark.domain

VIGIA = SystemId("vigia")
PLENDATA = SystemId("plendata")
LIMITS = PlanLimits(max_rounds=3, max_tool_calls=12, max_repairs=2)


def step(
    number: int,
    *,
    deps: tuple[int, ...] = (),
    soft: tuple[int, ...] = (),
    system: SystemId = VIGIA,
    agent: str = "agent.vigia",
    tool: str = "query_metric",
    arguments: Mapping[str, ArgumentValue] | None = None,
    optional: bool = False,
) -> PlanStep:
    dependencies = tuple(StepDependency(StepId(f"s{d}")) for d in deps) + tuple(
        StepDependency(StepId(f"s{d}"), hard=False) for d in soft
    )
    return PlanStep(
        step_id=StepId(f"s{number}"),
        agent=AgentId(agent),
        system=system,
        tool=tool,
        arguments=arguments if arguments is not None else {"metric": "alarmas"},
        depends_on=dependencies,
        optional=optional,
    )


def plan(*steps: PlanStep, **overrides: object) -> QueryPlan:
    fields: dict[str, object] = {
        "plan_id": PlanId("pln_a1b2c3d4e5f6"),
        "intent": Intent.ANALYTIC,
        "steps": steps,
        "catalog_versions": {VIGIA: "2026-07-20", PLENDATA: "2026-07-25"},
        "limits": LIMITS,
    }
    fields.update(overrides)
    return QueryPlan(**fields)  # type: ignore[arg-type]


def rejection(*steps: PlanStep, **overrides: object) -> frozenset[str]:
    with pytest.raises(InvalidPlanError) as caught:
        plan(*steps, **overrides)
    return caught.value.codes


def test_empty_plan_is_valid() -> None:
    built = plan()
    assert built.steps == ()
    assert built.systems == frozenset()
    assert built.execution_waves() == ()


def test_analytic_example_runs_s2_and_s3_in_parallel() -> None:
    ref = FactReference(StepId("s1"), "site_id")
    built = plan(
        step(3, deps=(1,), arguments={"site_id": ref, "window": "30d"}, optional=True),
        step(1, tool="site_resolver", arguments={"texto": "Getafe"}),
        step(2, deps=(1,), arguments={"entity": "site", "id": ref}),
    )
    assert built.step_ids == (StepId("s1"), StepId("s2"), StepId("s3"))
    assert built.execution_waves() == ((StepId("s1"),), (StepId("s2"), StepId("s3")))
    assert built.step(StepId("s3")).optional
    assert built.step(StepId("s2")).references == (ref,)


def test_steps_sort_numerically_not_lexically() -> None:
    built = plan(*(step(n) for n in (10, 2, 1)))
    assert built.step_ids == (StepId("s1"), StepId("s2"), StepId("s10"))


def test_unknown_step_lookup_raises_key_error() -> None:
    with pytest.raises(KeyError):
        plan(step(1)).step(StepId("s2"))


def test_systems_are_derived_from_steps() -> None:
    built = plan(step(1), step(2, system=PLENDATA, agent="agent.plendata"))
    assert built.systems == frozenset({VIGIA, PLENDATA})


def test_arguments_and_catalog_are_read_only() -> None:
    built = plan(step(1))
    with pytest.raises(TypeError):
        built.steps[0].arguments["metric"] = "otra"  # type: ignore[index]
    with pytest.raises(TypeError):
        built.catalog_versions[VIGIA] = "x"  # type: ignore[index]


def test_dependencies_are_sorted() -> None:
    built = plan(step(1), step(2), step(10, deps=(2, 1)))
    assert [d.step_id for d in built.step(StepId("s10")).depends_on] == ["s1", "s2"]


def test_soft_dependency_keeps_its_flag() -> None:
    built = plan(step(1), step(2, soft=(1,)))
    assert built.step(StepId("s2")).depends_on == (StepDependency(StepId("s1"), hard=False),)


@pytest.mark.parametrize(
    "tool", ["Query", "q", "query-metric", "1query", "a" * 49, "consulta_ñ", "_query"]
)
def test_invalid_tool_names_are_rejected(tool: str) -> None:
    with pytest.raises(ValidationError):
        step(1, tool=tool)


@pytest.mark.parametrize(
    "value",
    [
        "x" * 201,
        1.5,
        Decimal("NaN"),
        Decimal("Infinity"),
        tuple(range(51)),
        ("ok", 2.5),
        ("ok", ("anidado",)),
        None,
        {"texto": "libre"},
    ],
)
def test_invalid_argument_values_are_rejected(value: object) -> None:
    with pytest.raises(ValidationError):
        step(1, arguments={"arg": value})  # type: ignore[dict-item]


def test_valid_argument_values() -> None:
    built = step(
        1,
        arguments={
            "texto": "x" * 200,
            "limite": 10,
            "umbral": Decimal("10.7"),
            "activo": True,
            "ids": tuple(str(i) for i in range(50)),
        },
    )
    assert built.arguments["umbral"] == Decimal("10.7")


@pytest.mark.parametrize(
    ("fact", "field"), [("", "value"), ("a" * 65, "value"), ("site_id", "texto")]
)
def test_invalid_fact_references_are_rejected(fact: str, field: str) -> None:
    with pytest.raises(ValidationError):
        FactReference(StepId("s1"), fact, field)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("rounds", "calls", "repairs"),
    [(0, 1, 0), (4, 1, 0), (1, -1, 0), (1, 13, 0), (1, 1, 3), (True, 1, 0)],
)
def test_limits_out_of_range_are_rejected(rounds: int, calls: int, repairs: int) -> None:
    with pytest.raises(ValidationError):
        PlanLimits(rounds, calls, repairs)


def test_direct_cycle_is_rejected() -> None:
    assert rejection(step(1, deps=(2,)), step(2, deps=(1,))) == {"dependency_cycle"}


def test_long_cycle_is_rejected() -> None:
    codes = rejection(step(1), step(2, deps=(1, 4)), step(3, deps=(2,)), step(4, deps=(3,)))
    assert codes == {"dependency_cycle"}


def test_self_dependency_is_a_cycle() -> None:
    assert rejection(step(1, deps=(1,))) == {"dependency_cycle"}


def test_diamond_is_not_a_cycle() -> None:
    built = plan(step(1), step(2, deps=(1,)), step(3, deps=(1,)), step(4, deps=(2, 3)))
    assert built.execution_waves() == (
        (StepId("s1"),),
        (StepId("s2"), StepId("s3")),
        (StepId("s4"),),
    )


def test_invalid_plan_reports_every_reason_at_once() -> None:
    codes = rejection(
        step(1, system=SystemId("plenmind"), agent="agent.intruso"),
        step(1),
        step(2, deps=(9,)),
        step(3, deps=(1, 1)),
        step(4, arguments={"id": FactReference(StepId("s2"), "site_id")}),
        agents=(AgentId("agent.vigia"), AgentId("agent.vigia")),
        round=4,
        schema_version="2.0",
    )
    assert codes == {
        "unsupported_schema_version",
        "round_over_limit",
        "duplicate_agent",
        "duplicate_step_id",
        "undeclared_agent",
        "missing_catalog_version",
        "unknown_step_reference",
        "duplicate_dependency",
        "reference_without_dependency",
    }


def test_reference_to_unknown_step_is_rejected() -> None:
    codes = rejection(step(1, arguments={"id": FactReference(StepId("s7"), "x")}))
    assert codes == {"unknown_step_reference"}


def test_too_many_steps() -> None:
    steps = [step(n) for n in range(1, MAX_STEPS + 2)]
    assert rejection(*steps) == {"too_many_steps", "over_tool_call_limit"}


def test_steps_over_tool_call_limit() -> None:
    codes = rejection(step(1), step(2), limits=PlanLimits(1, 1, 0))
    assert codes == {"over_tool_call_limit"}


@pytest.mark.parametrize("round_number", [0, -1, True])
def test_invalid_round(round_number: int) -> None:
    assert rejection(step(1), round=round_number) == {"invalid_round"}


def test_cross_join_between_agents() -> None:
    join = CrossJoin("estacion", "codigo_estacion", (StepId("s1"), StepId("s2")))
    built = plan(
        step(1, tool="top_n"),
        step(2, system=PLENDATA, agent="agent.plendata"),
        agents=(AgentId("agent.vigia"), AgentId("agent.plendata")),
        join=join,
    )
    assert built.join == join
    assert join.on_missing == "hueco_explicito"


def test_cross_join_needs_two_known_distinct_steps() -> None:
    same = CrossJoin("estacion", "codigo", (StepId("s1"), StepId("s1")))
    assert rejection(step(1), join=same) == {"invalid_join"}
    unknown = CrossJoin("estacion", "codigo", (StepId("s1"), StepId("s5")))
    assert rejection(step(1), join=unknown) == {"unknown_step_reference"}


@pytest.mark.parametrize(
    ("entity", "canonical", "on_missing"),
    [("", "codigo", "hueco_explicito"), ("estacion", "", "hueco_explicito"), ("e", "c", "drop")],
)
def test_malformed_cross_join(entity: str, canonical: str, on_missing: str) -> None:
    with pytest.raises(ValidationError):
        CrossJoin(entity, canonical, (StepId("s1"), StepId("s2")), on_missing)  # type: ignore[arg-type]


def test_execution_waves_guard_against_cycles_built_by_hand() -> None:
    built = plan(step(1), step(2))
    cyclic = (step(1, deps=(2,)), step(2, deps=(1,)))
    object.__setattr__(built, "steps", cyclic)
    with pytest.raises(InvalidPlanError):
        built.execution_waves()
