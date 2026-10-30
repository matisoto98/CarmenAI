"""Prompt 3: DelegationPlan, AgentTask, AgentResult y NeedDelegation (6.12.3 a 6.12.5)."""

from dataclasses import replace
from decimal import Decimal

import pytest

from carmen.domain.delegation.models import (
    AgentDomain,
    AgentResult,
    AgentResultStatus,
    AgentRun,
    AgentTask,
    AgentWarning,
    Budgets,
    Composition,
    CompositionKind,
    DelegationPlan,
    Expects,
    ExternalCallTrace,
    NeedDelegation,
    NeedDelegationReason,
    TaskBudgets,
    ToolCallTrace,
)
from carmen.domain.egress.models import Purpose
from carmen.domain.errors import InvalidPlanError, ValidationError
from carmen.domain.evidence.models import EvidenceFact, Provenance
from carmen.domain.ids import (
    AgentId,
    CallId,
    DelegatedIdentityRef,
    DelegationPlanId,
    FactId,
    PrincipalId,
    ProviderId,
    RunId,
    TaskId,
    TurnId,
)
from carmen.domain.locale import Locale
from carmen.domain.model_output import ModelOutput
from carmen.domain.orchestration.mode import ResponseMode
from carmen.domain.system import SystemId
from carmen.domain.time import Instant

pytestmark = pytest.mark.domain

VIGIA = AgentId("agent.vigia")
PLENDATA = AgentId("agent.plendata")
IDENTITY = DelegatedIdentityRef("idr_7f3a9c1e2b40")
START = Instant.parse("2026-07-27T09:14:20Z")
END = Instant.parse("2026-07-27T09:14:22Z")
BUDGET = TaskBudgets(max_wall_ms=10000, max_tokens=6000, max_cost_eur=Decimal("0.00"))
GLOBAL = Budgets(max_wall_ms=20000, max_tokens=14000, max_cost_eur=Decimal("0.00"), max_agents=3)
JOIN = Composition(
    CompositionKind.JOIN,
    (TaskId("t1"), TaskId("t2")),
    entity="estacion",
    canonical_id="codigo_estacion",
)


def task(
    number: int,
    agent: AgentId = VIGIA,
    *,
    deps: tuple[int, ...] = (),
    budgets: TaskBudgets = BUDGET,
    objective: str = "alarmas por estación del mes en curso, top 10",
    optional: bool = False,
) -> AgentTask:
    return AgentTask(
        task_id=TaskId(f"t{number}"),
        agent_id=agent,
        objective=objective,
        entities={"periodo": "mes_actual"},
        expects=Expects.FACTS,
        locale=Locale.ES,
        budgets=budgets,
        delegated_identity=IDENTITY,
        depends_on=tuple(TaskId(f"t{d}") for d in deps),
        optional=optional,
    )


def plan(*tasks: AgentTask, **overrides: object) -> DelegationPlan:
    fields: dict[str, object] = {
        "plan_id": DelegationPlanId("dpl_7a3b9c1e4f20"),
        "turn_id": TurnId("trn_18ab44de"),
        "response_mode": ResponseMode.DELEGATE_MULTI,
        "principal_id": PrincipalId("usr_a91f"),
        "policy_version": "pol-2026-07-21",
        "tasks": tasks,
        "composition": JOIN,
        "budgets": GLOBAL,
    }
    fields.update(overrides)
    return DelegationPlan(**fields)  # type: ignore[arg-type]


def codes(*tasks: AgentTask, **overrides: object) -> frozenset[str]:
    with pytest.raises(InvalidPlanError) as caught:
        plan(*tasks, **overrides)
    return caught.value.codes


def example_plan() -> DelegationPlan:
    """El DelegationPlan de 6.12.3: VigIA y Plendata en paralelo, unidos por estación."""
    return plan(
        task(1, VIGIA),
        task(2, PLENDATA, objective="margen por estación del mes en curso", optional=True),
    )


def test_the_example_of_6_12_3_builds_without_infrastructure() -> None:
    built = example_plan()
    assert built.agents == {VIGIA, PLENDATA}
    assert built.execution_waves() == ((TaskId("t1"), TaskId("t2")),)
    assert built.task(TaskId("t2")).optional
    assert not built.requires_human_approval
    assert built.task(TaskId("t1")).entities["periodo"] == "mes_actual"


def test_tasks_are_ordered_and_lookup_fails_for_unknown() -> None:
    built = plan(
        task(10, deps=(2,)),
        task(2),
        composition=Composition(CompositionKind.BLOCKS, (TaskId("t2"), TaskId("t10"))),
    )
    assert [t.task_id for t in built.tasks] == ["t2", "t10"]
    assert built.execution_waves() == ((TaskId("t2"),), (TaskId("t10"),))
    with pytest.raises(KeyError):
        built.task(TaskId("t3"))


@pytest.mark.parametrize(
    "objective",
    [
        "ejecuta query_metric con alarmas",
        "usa build_dossier sobre Getafe",
        "llama a top_n()",
        "lanza run()",
    ],
)
def test_agent_task_rejects_tool_names(objective: str) -> None:
    with pytest.raises(ValidationError, match="herramienta"):
        task(1, objective=objective)


def test_agent_task_has_no_tool_field() -> None:
    with pytest.raises(TypeError):
        AgentTask(  # type: ignore[call-arg]
            TaskId("t1"),
            VIGIA,
            "alarmas abiertas",
            {},
            Expects.FACTS,
            Locale.ES,
            BUDGET,
            IDENTITY,
            tool="query_metric",
        )


@pytest.mark.parametrize(
    "token",
    [
        ".".join(["eyJ" + "hbGciOiJub25lIn0", "eyJ" + "zdWIiOiJ4In0", "c2ln"]),  # forma de JWT
        "Bearer abcdefgh12345678",
        "idr_corta",
    ],
)
def test_delegated_identity_is_a_reference_never_a_token(token: str) -> None:
    with pytest.raises(ValidationError):
        DelegatedIdentityRef(token)
    with pytest.raises(ValidationError, match="referencia"):
        replace(task(1), delegated_identity=token)


@pytest.mark.parametrize(
    "overrides",
    [
        {"objective": " "},
        {"entities": {"": "x"}},
        {"entities": {"periodo": ""}},
        {"depends_on": (TaskId("t1"),)},
        {"depends_on": (TaskId("t2"), TaskId("t2"))},
    ],
)
def test_malformed_tasks(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        replace(task(1), **overrides)


def test_sum_of_task_budgets_cannot_exceed_the_global_one() -> None:
    big = TaskBudgets(10000, 8000, Decimal("0.30"))
    found = codes(
        task(1, budgets=big),
        task(2, PLENDATA, budgets=big),
        budgets=replace(GLOBAL, max_cost_eur=Decimal("0.50")),
    )
    assert found == {"over_budget"}
    details = _details(task(1, budgets=big), task(2, PLENDATA, budgets=big))
    assert any("tokens" in d for d in details)
    assert not any("coste" in d for d in details)


def _details(*tasks: AgentTask) -> tuple[str, ...]:
    """Motivos del rechazo con un coste global holgado: solo fallan los tokens."""
    with pytest.raises(InvalidPlanError) as caught:
        plan(*tasks, budgets=replace(GLOBAL, max_cost_eur=Decimal("1.00")))
    return tuple(i.detail for i in caught.value.issues)


def test_wall_time_adds_up_only_along_dependencies() -> None:
    slow = TaskBudgets(15000, 1000, Decimal(0))
    parallel = plan(task(1, budgets=slow), task(2, PLENDATA, budgets=slow))
    assert parallel.budgets.max_wall_ms == 20000
    chained = codes(
        task(1, budgets=slow),
        task(2, PLENDATA, deps=(1,), budgets=slow),
    )
    assert chained == {"over_budget"}


def test_depends_on_without_cycles() -> None:
    blocks = Composition(CompositionKind.BLOCKS, (TaskId("t1"), TaskId("t2")))
    assert codes(task(1, deps=(2,)), task(2, PLENDATA, deps=(1,)), composition=blocks) == {
        "dependency_cycle"
    }


def test_every_reason_is_reported_at_once() -> None:
    found = codes(
        task(1),
        task(1, PLENDATA),
        task(2, AgentId("agent.zoho-desk"), deps=(9,)),
        task(3, AgentId("agent.plenmind")),
        composition=Composition(CompositionKind.BLOCKS, (TaskId("t1"), TaskId("t5"))),
        budgets=Budgets(1000, 1000, Decimal(0), max_agents=2),
        policy_version=" ",
        schema_version="2.0",
    )
    assert found == {
        "unsupported_schema_version",
        "missing_policy_version",
        "duplicate_task_id",
        "unknown_task_reference",
        "over_agent_limit",
        "over_budget",
    }


def test_too_many_tasks() -> None:
    tiny = TaskBudgets(1, 1, Decimal(0))
    many = [task(n, budgets=tiny) for n in range(1, 14)]
    blocks = Composition(CompositionKind.BLOCKS, (TaskId("t1"), TaskId("t2")))
    assert codes(*many, composition=blocks) == {"too_many_tasks"}


def test_mode_and_task_count_must_agree() -> None:
    single = Composition(CompositionKind.SINGLE, (TaskId("t1"),))
    assert plan(task(1), response_mode=ResponseMode.DELEGATE_SINGLE, composition=single)
    assert codes(
        task(1), task(2), response_mode=ResponseMode.DELEGATE_SINGLE, composition=single
    ) == {"mode_task_mismatch"}
    assert codes(task(1), composition=single) == {"mode_task_mismatch", "composition_mismatch"}
    assert codes(task(1), response_mode=ResponseMode.SUPERVISOR_DIRECT, composition=single) == {
        "mode_without_delegation"
    }


@pytest.mark.parametrize(
    "build",
    [
        lambda: Composition(CompositionKind.SINGLE, (TaskId("t1"), TaskId("t2"))),
        lambda: Composition(CompositionKind.BLOCKS, (TaskId("t1"),)),
        lambda: Composition(CompositionKind.BLOCKS, (TaskId("t1"), TaskId("t1"))),
        lambda: Composition(CompositionKind.JOIN, (TaskId("t1"), TaskId("t2"))),
        lambda: Composition(CompositionKind.BLOCKS, (TaskId("t1"), TaskId("t2")), entity="e"),
        lambda: Composition(
            CompositionKind.JOIN, (TaskId("t1"), TaskId("t2")), "e", "c", on_missing="descartar"
        ),
    ],
)
def test_malformed_compositions(build: object) -> None:
    with pytest.raises(ValidationError):
        build()  # type: ignore[operator]


@pytest.mark.parametrize(
    "build",
    [
        lambda: TaskBudgets(-1, 0, Decimal(0)),
        lambda: TaskBudgets(0, 0, Decimal("-0.01")),
        lambda: TaskBudgets(0, 0, 0.5),
        lambda: Budgets(0, 0, Decimal(0), max_agents=0),
    ],
)
def test_malformed_budgets(build: object) -> None:
    with pytest.raises(ValidationError):
        build()  # type: ignore[operator]


def test_need_delegation_proposes_a_domain_never_an_agent() -> None:
    need = NeedDelegation(
        NeedDelegationReason.NEEDS_PROCEDURE,
        AgentDomain.DOCUMENTAL,
        context_ref="ev:cal_1/alarma_42",
        rationale="La alarma necesita el procedimiento oficial",
    )
    assert need.suggested_domain == "documental"
    with pytest.raises(TypeError):
        NeedDelegation(  # type: ignore[call-arg]
            NeedDelegationReason.NEEDS_PROCEDURE,
            AgentDomain.DOCUMENTAL,
            "ev:1",
            "x",
            agent_id=AgentId("agent.plenmind"),
        )
    with pytest.raises(ValidationError, match="agentes"):
        replace(need, rationale="pásalo a agent.plenmind")
    with pytest.raises(ValidationError):
        replace(need, context_ref="")


# --- AgentRun y AgentResult ---


def run(agent: AgentId = VIGIA, **overrides: object) -> AgentRun:
    fields: dict[str, object] = {"run_id": RunId("run_0001"), "agent_id": agent}
    fields.update({"started_at": START, "ended_at": END})
    fields.update(overrides)
    return AgentRun(**fields)  # type: ignore[arg-type]


FACT = EvidenceFact(
    fact_id=FactId("alarmas_total"),
    call_id=CallId("cal_1"),
    system_id=SystemId("vigia"),
    label="Alarmas del periodo",
    value=29,
    provenance=Provenance("top_n", "2026-07-20", END),
)
OUTPUT = ModelOutput(
    ProviderId("provider.internal-ollama"),
    "qwen3",
    "2026-07",
    Purpose.NARRATION,
    "Hay 29 alarmas.",
    10,
    5,
    Decimal(0),
    END,
)


def result(status: AgentResultStatus, **overrides: object) -> AgentResult:
    fields: dict[str, object] = {
        "task_id": TaskId("t1"),
        "agent_id": VIGIA,
        "agent_version": "1.4.0",
        "status": status,
        "run": run(),
    }
    fields.update(overrides)
    return AgentResult(**fields)  # type: ignore[arg-type]


def test_run_traces() -> None:
    traced = run(
        tool_calls=(ToolCallTrace(CallId("cal_1"), SystemId("vigia"), "top_n", 820, ok=True),),
        tokens_in=900,
        tokens_out=120,
    )
    assert traced.duration_ms == 2000
    external = ExternalCallTrace("egress.legal-sources", END, domain="boe.es")
    assert external.provider is None


@pytest.mark.parametrize(
    "build",
    [
        lambda: run(started_at=END, ended_at=START),
        lambda: run(tokens_in=-1),
        lambda: run(cost_eur=Decimal(-1)),
        lambda: ToolCallTrace(CallId("cal_1"), SystemId("vigia"), "", 1, ok=True),
        lambda: ToolCallTrace(CallId("cal_1"), SystemId("vigia"), "top_n", -1, ok=True),
        lambda: ExternalCallTrace("egress.x", END),
        lambda: ExternalCallTrace("", END, domain="boe.es"),
        lambda: ExternalCallTrace("egress.x", END, domain="boe.es", tokens=-1),
    ],
)
def test_malformed_traces(build: object) -> None:
    with pytest.raises(ValidationError):
        build()  # type: ignore[operator]


def test_result_with_evidence_and_separate_model_output() -> None:
    built = result(AgentResultStatus.OK, evidence=(FACT,), model_outputs=(OUTPUT,))
    assert built.evidence == (FACT,)
    assert built.model_outputs == (OUTPUT,)
    partial = result(
        AgentResultStatus.PARTIAL,
        evidence=(FACT,),
        warnings=(AgentWarning("system_unavailable", "Plendata no respondió"),),
    )
    assert partial.warnings[0].code == "system_unavailable"
    assert result(AgentResultStatus.NO_DATA).evidence == ()


def test_free_text_as_main_result_cannot_be_built() -> None:
    with pytest.raises(ValidationError, match="texto libre"):
        result(AgentResultStatus.OK, model_outputs=(OUTPUT,))


def test_model_output_is_not_accepted_as_evidence() -> None:
    with pytest.raises(ValidationError, match="evidencia"):
        result(AgentResultStatus.OK, evidence=(OUTPUT,))
    with pytest.raises(ValidationError, match="ModelOutput"):
        result(AgentResultStatus.OK, evidence=(FACT,), model_outputs=(FACT,))


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": AgentResultStatus.PARTIAL, "evidence": (FACT,)},
        {"status": AgentResultStatus.DENIED, "evidence": (FACT,)},
        {"status": AgentResultStatus.OK, "evidence": (FACT,), "run": run(PLENDATA)},
        {"status": AgentResultStatus.OK, "evidence": (FACT,), "agent_version": ""},
    ],
)
def test_incoherent_results(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        result(**overrides)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "build",
    [lambda: AgentWarning("", "m"), lambda: AgentWarning("c", " ")],
)
def test_malformed_warnings(build: object) -> None:
    with pytest.raises(ValidationError):
        build()  # type: ignore[operator]


def test_execution_waves_guard_against_cycles_built_by_hand() -> None:
    built = example_plan()
    object.__setattr__(built, "tasks", (task(1, deps=(2,)), task(2, deps=(1,))))
    with pytest.raises(InvalidPlanError):
        built.execution_waves()
