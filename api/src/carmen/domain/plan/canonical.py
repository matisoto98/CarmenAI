"""Lectura estricta y forma normal canónica del QueryPlan (6.2, 6.2.2).

La lectura rechaza claves desconocidas, tipos incorrectos y valores mal formados, y reúne todos
los motivos antes de rechazar. La forma canónica ordena claves, pasos y dependencias y omite los
campos con valor por defecto, de modo que dos planes equivalentes producen exactamente la misma
serialización, sea cual sea el orden en que el modelo escribió las claves.
"""

import json
import math
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Final, TypeVar

from carmen.domain.errors import InvalidPlanError, PlanIssue, ValidationError
from carmen.domain.ids import AgentId, PlanId, StepId
from carmen.domain.plan.models import (
    ArgumentValue,
    CrossJoin,
    FactField,
    FactReference,
    Intent,
    PlanLimits,
    PlanStep,
    QueryPlan,
    Scalar,
    StepDependency,
)
from carmen.domain.system import SystemId

CanonicalValue = str | int | Decimal | bool | list["CanonicalValue"] | dict[str, "CanonicalValue"]

_PLAN_KEYS: Final = frozenset(
    {
        "schema_version",
        "plan_id",
        "intent",
        "systems",
        "agents",
        "join",
        "steps",
        "catalog_versions",
        "limits",
        "round",
    }
)
_PLAN_REQUIRED: Final = (
    "schema_version",
    "plan_id",
    "intent",
    "steps",
    "catalog_versions",
    "limits",
)
_STEP_KEYS: Final = frozenset(
    {"step_id", "agent", "system", "tool", "arguments", "depends_on", "optional"}
)
_STEP_REQUIRED: Final = ("step_id", "agent", "system", "tool", "arguments")
_DEPENDENCY_KEYS: Final = frozenset({"step_id", "hard"})
_REFERENCE_KEYS: Final = frozenset({"$ref_step", "$ref_fact", "$ref_field"})
_LIMIT_KEYS: Final = ("max_rounds", "max_tool_calls", "max_repairs")
_JOIN_KEYS: Final = frozenset({"entity", "canonical_id", "steps", "on_missing"})
_FACT_FIELDS: Final[tuple[FactField, ...]] = ("value", "entity_id", "label")

_T = TypeVar("_T")


class _Reader:
    """Acumula los motivos de rechazo mientras recorre el documento."""

    def __init__(self) -> None:
        self.issues: list[PlanIssue] = []

    def add(self, code: str, path: str, detail: str) -> None:
        self.issues.append(PlanIssue(code, f"{path}: {detail}"))

    def mapping(self, value: object, path: str) -> Mapping[str, object] | None:
        if isinstance(value, Mapping) and all(isinstance(k, str) for k in value):
            return value
        self.add("invalid_type", path, "se esperaba un objeto")
        return None

    def keys(
        self,
        data: Mapping[str, object],
        path: str,
        allowed: frozenset[str],
        required: tuple[str, ...],
    ) -> bool:
        complete = True
        for key in sorted(set(data) - allowed):
            self.add("unknown_field", path, f"campo no admitido {key!r}")
        for key in required:
            if key not in data:
                self.add("missing_field", path, f"falta el campo obligatorio {key!r}")
                complete = False
        return complete

    def build(self, factory: Callable[[str], _T], value: object, path: str) -> _T | None:
        if not isinstance(value, str):
            self.add("invalid_type", path, "se esperaba una cadena")
            return None
        try:
            return factory(value)
        except ValidationError as exc:
            self.add("invalid_value", path, exc.message)
            return None

    def integer(self, value: object, path: str) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int):
            self.add("invalid_type", path, "se esperaba un entero")
            return None
        return value

    def boolean(self, value: object, path: str) -> bool | None:
        if not isinstance(value, bool):
            self.add("invalid_type", path, "se esperaba un booleano")
            return None
        return value

    def array(self, value: object, path: str) -> list[object] | None:
        if not isinstance(value, list | tuple):
            self.add("invalid_type", path, "se esperaba una lista")
            return None
        return list(value)


def _intent(value: str) -> Intent:
    try:
        return Intent(value)
    except ValueError as exc:
        msg = f"intención desconocida: {value!r}"
        raise ValidationError(msg) from exc


def _scalar(reader: _Reader, value: object, path: str) -> Scalar | None:
    if isinstance(value, bool | str | int | Decimal):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            reader.add("invalid_value", path, "número no finito")
            return None
        return Decimal(repr(value))
    reader.add("invalid_type", path, f"tipo de argumento no admitido: {type(value).__name__}")
    return None


def _reference(reader: _Reader, data: Mapping[str, object], path: str) -> FactReference | None:
    if not reader.keys(data, path, _REFERENCE_KEYS, ("$ref_step", "$ref_fact")):
        return None
    step_id = reader.build(StepId, data["$ref_step"], f"{path}.$ref_step")
    fact = data["$ref_fact"]
    field = data.get("$ref_field", "value")
    if not isinstance(fact, str):
        reader.add("invalid_type", f"{path}.$ref_fact", "se esperaba una cadena")
        return None
    chosen = next((f for f in _FACT_FIELDS if f == field), None)
    if chosen is None:
        reader.add("invalid_value", f"{path}.$ref_field", f"campo desconocido {field!r}")
        return None
    if step_id is None:
        return None
    try:
        return FactReference(step_id, fact, chosen)
    except ValidationError as exc:
        reader.add("invalid_value", path, exc.message)
        return None


def _argument(reader: _Reader, value: object, path: str) -> ArgumentValue | None:
    if isinstance(value, Mapping):
        data = reader.mapping(value, path)
        return None if data is None else _reference(reader, data, path)
    if isinstance(value, list | tuple):
        items = [_scalar(reader, item, f"{path}[{i}]") for i, item in enumerate(value)]
        present = tuple(item for item in items if item is not None)
        return present if len(present) == len(items) else None
    return _scalar(reader, value, path)


def _arguments(reader: _Reader, value: object, path: str) -> dict[str, ArgumentValue] | None:
    data = reader.mapping(value, path)
    if data is None:
        return None
    parsed = {name: _argument(reader, raw, f"{path}.{name}") for name, raw in data.items()}
    complete = {name: arg for name, arg in parsed.items() if arg is not None}
    return complete if len(complete) == len(parsed) else None


def _dependency(reader: _Reader, value: object, path: str) -> StepDependency | None:
    data = reader.mapping(value, path)
    if data is None or not reader.keys(data, path, _DEPENDENCY_KEYS, ("step_id",)):
        return None
    step_id = reader.build(StepId, data["step_id"], f"{path}.step_id")
    hard = reader.boolean(data.get("hard", True), f"{path}.hard")
    if step_id is None or hard is None:
        return None
    return StepDependency(step_id, hard)


def _step(reader: _Reader, value: object, path: str) -> PlanStep | None:
    data = reader.mapping(value, path)
    if data is None or not reader.keys(data, path, _STEP_KEYS, _STEP_REQUIRED):
        return None
    step_id = reader.build(StepId, data["step_id"], f"{path}.step_id")
    agent = reader.build(AgentId, data["agent"], f"{path}.agent")
    system = reader.build(SystemId, data["system"], f"{path}.system")
    tool = data["tool"]
    if not isinstance(tool, str):
        reader.add("invalid_type", f"{path}.tool", "se esperaba una cadena")
    arguments = _arguments(reader, data["arguments"], f"{path}.arguments")
    raw_deps = reader.array(data.get("depends_on", []), f"{path}.depends_on")
    deps = [
        _dependency(reader, raw, f"{path}.depends_on[{i}]") for i, raw in enumerate(raw_deps or [])
    ]
    optional = reader.boolean(data.get("optional", False), f"{path}.optional")
    if (
        step_id is None
        or agent is None
        or system is None
        or not isinstance(tool, str)
        or arguments is None
        or optional is None
        or raw_deps is None
        or any(d is None for d in deps)
    ):
        return None
    try:
        return PlanStep(
            step_id,
            agent,
            system,
            tool,
            arguments,
            tuple(d for d in deps if d is not None),
            optional,
        )
    except ValidationError as exc:
        reader.add("invalid_value", path, exc.message)
        return None


def _limits(reader: _Reader, value: object, path: str) -> PlanLimits | None:
    data = reader.mapping(value, path)
    if data is None or not reader.keys(data, path, frozenset(_LIMIT_KEYS), _LIMIT_KEYS):
        return None
    numbers = [reader.integer(data[key], f"{path}.{key}") for key in _LIMIT_KEYS]
    rounds, calls, repairs = numbers
    if rounds is None or calls is None or repairs is None:
        return None
    try:
        return PlanLimits(rounds, calls, repairs)
    except ValidationError as exc:
        reader.add("invalid_value", path, exc.message)
        return None


def _join(reader: _Reader, value: object, path: str) -> CrossJoin | None:
    data = reader.mapping(value, path)
    if data is None or not reader.keys(data, path, _JOIN_KEYS, ("entity", "canonical_id", "steps")):
        return None
    entity, canonical_id = data["entity"], data["canonical_id"]
    on_missing = data.get("on_missing", "hueco_explicito")
    raw_steps = reader.array(data["steps"], f"{path}.steps")
    steps = [reader.build(StepId, s, f"{path}.steps[{i}]") for i, s in enumerate(raw_steps or [])]
    if not isinstance(entity, str) or not isinstance(canonical_id, str):
        reader.add("invalid_type", path, "entity y canonical_id deben ser cadenas")
        return None
    if on_missing != "hueco_explicito":
        reader.add("invalid_value", f"{path}.on_missing", "solo se admite hueco_explicito")
        return None
    present = tuple(s for s in steps if s is not None)
    if raw_steps is None or len(present) != len(steps):
        return None
    try:
        return CrossJoin(entity, canonical_id, present)
    except ValidationError as exc:
        reader.add("invalid_value", path, exc.message)
        return None


def _catalog_versions(reader: _Reader, value: object, path: str) -> dict[SystemId, str] | None:
    data = reader.mapping(value, path)
    if data is None:
        return None
    versions: dict[SystemId, str] = {}
    for name, version in data.items():
        system = reader.build(SystemId, name, f"{path} (clave)")
        if not isinstance(version, str):
            reader.add("invalid_type", f"{path}.{name}", "se esperaba una cadena")
        elif system is not None:
            versions[system] = version
    return versions if len(versions) == len(data) else None


def plan_from_dict(data: Mapping[str, object]) -> QueryPlan:
    """Construye un QueryPlan desde su forma JSON. Rechaza con TODOS los motivos a la vez."""
    reader = _Reader()
    root = reader.mapping(data, "plan")
    if root is None or not reader.keys(root, "plan", _PLAN_KEYS, _PLAN_REQUIRED):
        raise InvalidPlanError(tuple(reader.issues))

    schema_version = root["schema_version"]
    if not isinstance(schema_version, str):
        reader.add("invalid_type", "plan.schema_version", "se esperaba una cadena")
    plan_id = reader.build(PlanId, root["plan_id"], "plan.plan_id")
    intent = reader.build(_intent, root["intent"], "plan.intent")
    raw_steps = reader.array(root["steps"], "plan.steps")
    steps = [_step(reader, raw, f"plan.steps[{i}]") for i, raw in enumerate(raw_steps or [])]
    catalog_versions = _catalog_versions(reader, root["catalog_versions"], "plan.catalog_versions")
    limits = _limits(reader, root["limits"], "plan.limits")
    raw_agents = reader.array(root.get("agents", []), "plan.agents")
    agents = [reader.build(AgentId, a, f"plan.agents[{i}]") for i, a in enumerate(raw_agents or [])]
    join = _join(reader, root["join"], "plan.join") if "join" in root else None
    round_number = reader.integer(root.get("round", 1), "plan.round")
    declared_systems = _declared_systems(reader, root)

    if (
        reader.issues
        or not isinstance(schema_version, str)
        or plan_id is None
        or intent is None
        or catalog_versions is None
        or limits is None
        or round_number is None
    ):
        raise InvalidPlanError(tuple(reader.issues))

    plan = QueryPlan(
        plan_id=plan_id,
        intent=intent,
        steps=tuple(s for s in steps if s is not None),
        catalog_versions=catalog_versions,
        limits=limits,
        agents=tuple(a for a in agents if a is not None),
        join=join,
        round=round_number,
        schema_version=schema_version,
    )
    if declared_systems is not None and declared_systems != plan.systems:
        detail = (
            f"systems declara {sorted(declared_systems)} y los pasos usan {sorted(plan.systems)}"
        )
        raise InvalidPlanError((PlanIssue("systems_mismatch", detail),))
    return plan


def _declared_systems(reader: _Reader, root: Mapping[str, object]) -> frozenset[SystemId] | None:
    """systems es redundante con los pasos (ADR-043): si viene, debe coincidir con ellos."""
    if "systems" not in root:
        return None
    raw = reader.array(root["systems"], "plan.systems")
    built = [reader.build(SystemId, s, f"plan.systems[{i}]") for i, s in enumerate(raw or [])]
    if raw is None or any(s is None for s in built):
        return None
    present = frozenset(s for s in built if s is not None)
    if len(present) != len(raw):
        reader.add("invalid_value", "plan.systems", "systems tiene elementos repetidos")
        return None
    return present


def plan_from_json(text: str) -> QueryPlan:
    """Lee un plan desde JSON. Los números con decimales se leen como Decimal, nunca float."""
    try:
        data = json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise InvalidPlanError((PlanIssue("invalid_json", str(exc)),)) from exc
    if not isinstance(data, dict):
        raise InvalidPlanError((PlanIssue("invalid_type", "plan: se esperaba un objeto"),))
    return plan_from_dict(data)


def _canonical_argument(value: ArgumentValue) -> CanonicalValue:
    if isinstance(value, FactReference):
        reference: dict[str, CanonicalValue] = {
            "$ref_step": str(value.step_id),
            "$ref_fact": value.fact,
        }
        if value.field != "value":
            reference["$ref_field"] = value.field
        return reference
    if isinstance(value, tuple):
        return list(value)
    return value


def _canonical_step(step: PlanStep) -> dict[str, CanonicalValue]:
    data: dict[str, CanonicalValue] = {
        "step_id": str(step.step_id),
        "agent": str(step.agent),
        "system": str(step.system),
        "tool": step.tool,
        "arguments": {name: _canonical_argument(v) for name, v in step.arguments.items()},
    }
    if step.depends_on:
        dependencies: list[CanonicalValue] = []
        for dep in step.depends_on:
            entry: dict[str, CanonicalValue] = {"step_id": str(dep.step_id)}
            if not dep.hard:
                entry["hard"] = False
            dependencies.append(entry)
        data["depends_on"] = dependencies
    if step.optional:
        data["optional"] = True
    return data


def to_canonical_dict(plan: QueryPlan) -> dict[str, CanonicalValue]:
    """Forma normal (6.2.2): pasos por step_id, dependencias ordenadas, sin valores por defecto.

    systems se emite siempre, derivado de los pasos, porque el esquema lo exige (ADR-043).
    """
    data: dict[str, CanonicalValue] = {
        "schema_version": plan.schema_version,
        "plan_id": str(plan.plan_id),
        "intent": plan.intent.value,
        "systems": [str(s) for s in sorted(plan.systems)],
        "steps": [_canonical_step(step) for step in plan.steps],
        "catalog_versions": {str(k): v for k, v in plan.catalog_versions.items()},
        "limits": {
            "max_rounds": plan.limits.max_rounds,
            "max_tool_calls": plan.limits.max_tool_calls,
            "max_repairs": plan.limits.max_repairs,
        },
    }
    if plan.agents:
        data["agents"] = [str(a) for a in plan.agents]
    if plan.join is not None:
        data["join"] = {
            "entity": plan.join.entity,
            "canonical_id": plan.join.canonical_id,
            "steps": [str(s) for s in plan.join.steps],
        }
    if plan.round != 1:
        data["round"] = plan.round
    return data


def _number(value: Decimal) -> str:
    """Un decimal en notación fija y sin ceros sobrantes: 10.70 y 10.7 se escriben igual."""
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "0") else text


def _dump(value: CanonicalValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        return _number(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(_dump(item) for item in value) + "]"
    return "{" + ",".join(f"{_dump(k)}:{_dump(value[k])}" for k in sorted(value)) + "}"


def canonical_json(plan: QueryPlan) -> str:
    """Serialización canónica: claves ordenadas, sin espacios, idéntica para planes equivalentes."""
    return _dump(to_canonical_dict(plan))
