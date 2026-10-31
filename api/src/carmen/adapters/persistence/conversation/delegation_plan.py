"""DelegationPlan ⇄ JSON para messages.delegation_plan.

Conversión explícita, campo a campo. El dinero viaja como texto para no perder precisión, y el
plan se reconstruye con su constructor, que vuelve a validar todas sus reglas.
"""

from collections.abc import Mapping
from decimal import Decimal

from carmen.adapters.persistence.types import as_mapping, as_sequence, dumps, loads
from carmen.application.jsontypes import JsonValue
from carmen.domain.delegation.models import (
    AgentTask,
    Budgets,
    Composition,
    CompositionKind,
    DelegationPlan,
    Expects,
    TaskBudgets,
)
from carmen.domain.errors import ValidationError
from carmen.domain.ids import (
    AgentId,
    DelegatedIdentityRef,
    DelegationPlanId,
    PrincipalId,
    TaskId,
    TurnId,
)
from carmen.domain.locale import Locale
from carmen.domain.orchestration.mode import ResponseMode


def _text(data: Mapping[str, JsonValue], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        msg = f"delegation_plan.{key} debe ser texto"
        raise ValidationError(msg)
    return value


def _optional_text(data: Mapping[str, JsonValue], key: str) -> str | None:
    value = data.get(key)
    return None if value is None else _text(data, key)


def _int(data: Mapping[str, JsonValue], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"delegation_plan.{key} debe ser un entero"
        raise ValidationError(msg)
    return value


def _bool(data: Mapping[str, JsonValue], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        msg = f"delegation_plan.{key} debe ser booleano"
        raise ValidationError(msg)
    return value


def _task_ids(value: JsonValue) -> tuple[TaskId, ...]:
    return tuple(TaskId(str(t)) for t in as_sequence(value))


def _task_to_json(t: AgentTask) -> JsonValue:
    return {
        "task_id": str(t.task_id),
        "agent_id": str(t.agent_id),
        "objective": t.objective,
        "entities": dict(t.entities),
        "expects": t.expects.value,
        "locale": t.locale.value,
        "budgets": {
            "max_wall_ms": t.budgets.max_wall_ms,
            "max_tokens": t.budgets.max_tokens,
            "max_cost_eur": str(t.budgets.max_cost_eur),
        },
        "delegated_identity": str(t.delegated_identity),
        "depends_on": [str(d) for d in t.depends_on],
        "optional": t.optional,
    }


def _task_from_json(value: JsonValue) -> AgentTask:
    data = as_mapping(value)
    budgets = as_mapping(data.get("budgets"))
    entities = as_mapping(data.get("entities"))
    return AgentTask(
        task_id=TaskId(_text(data, "task_id")),
        agent_id=AgentId(_text(data, "agent_id")),
        objective=_text(data, "objective"),
        entities={k: _text(entities, k) for k in entities},
        expects=Expects(_text(data, "expects")),
        locale=Locale(_text(data, "locale")),
        budgets=TaskBudgets(
            max_wall_ms=_int(budgets, "max_wall_ms"),
            max_tokens=_int(budgets, "max_tokens"),
            max_cost_eur=Decimal(_text(budgets, "max_cost_eur")),
        ),
        delegated_identity=DelegatedIdentityRef(_text(data, "delegated_identity")),
        depends_on=_task_ids(data.get("depends_on", [])),
        optional=_bool(data, "optional"),
    )


def plan_to_json(p: DelegationPlan) -> str:
    return dumps(
        {
            "plan_id": str(p.plan_id),
            "turn_id": str(p.turn_id),
            "response_mode": p.response_mode.value,
            "principal_id": str(p.principal_id),
            "policy_version": p.policy_version,
            "tasks": [_task_to_json(t) for t in p.tasks],
            "composition": {
                "kind": p.composition.kind.value,
                "tasks": [str(t) for t in p.composition.tasks],
                "entity": p.composition.entity,
                "canonical_id": p.composition.canonical_id,
                "on_missing": p.composition.on_missing,
            },
            "budgets": {
                "max_wall_ms": p.budgets.max_wall_ms,
                "max_tokens": p.budgets.max_tokens,
                "max_cost_eur": str(p.budgets.max_cost_eur),
                "max_agents": p.budgets.max_agents,
            },
            "requires_human_approval": p.requires_human_approval,
            "schema_version": p.schema_version,
        }
    )


def plan_from_json(text: str) -> DelegationPlan:
    data = as_mapping(loads(text))
    composition = as_mapping(data.get("composition"))
    budgets = as_mapping(data.get("budgets"))
    return DelegationPlan(
        plan_id=DelegationPlanId(_text(data, "plan_id")),
        turn_id=TurnId(_text(data, "turn_id")),
        response_mode=ResponseMode(_text(data, "response_mode")),
        principal_id=PrincipalId(_text(data, "principal_id")),
        policy_version=_text(data, "policy_version"),
        tasks=tuple(_task_from_json(t) for t in as_sequence(data.get("tasks"))),
        composition=Composition(
            kind=CompositionKind(_text(composition, "kind")),
            tasks=_task_ids(composition.get("tasks")),
            entity=_optional_text(composition, "entity"),
            canonical_id=_optional_text(composition, "canonical_id"),
            on_missing=_text(composition, "on_missing"),
        ),
        budgets=Budgets(
            max_wall_ms=_int(budgets, "max_wall_ms"),
            max_tokens=_int(budgets, "max_tokens"),
            max_cost_eur=Decimal(_text(budgets, "max_cost_eur")),
            max_agents=_int(budgets, "max_agents"),
        ),
        requires_human_approval=_bool(data, "requires_human_approval"),
        schema_version=_text(data, "schema_version"),
    )
