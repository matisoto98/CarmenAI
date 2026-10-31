"""QueryPlan: el plan LOCAL de un agente sobre sus propias herramientas (6.2, ADR-015).

Aquí vive la validación estructural, la que no necesita catálogo ni política: forma de los
identificadores, límites, referencias entre pasos y ciclos. La que sí los necesita (herramienta
existente, argumentos contra su esquema, mapa de entidades, conflicto de métricas) es del
validador de application. La validación es previa y total: se reúnen todos los motivos.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Literal

from carmen.domain.errors import InvalidPlanError, PlanIssue, ValidationError
from carmen.domain.graph import topological_waves
from carmen.domain.ids import AgentId, PlanId, StepId
from carmen.domain.system import SystemId

SCHEMA_VERSION: Final = "1.0"
MAX_STEPS: Final = 12
MAX_STRING_ARGUMENT: Final = 200
MAX_ARRAY_ARGUMENT: Final = 50
MAX_FACT_KEY: Final = 64
TOOL_NAME_MAX: Final = 48


class Intent(StrEnum):
    SOCIAL = "social"
    MANIFEST = "manifest"
    GLOSSARY = "glossary"
    FACTUAL = "factual"
    TREND = "trend"
    ANALYTIC = "analytic"
    KNOWLEDGE = "knowledge"
    DOCUMENTAL = "documental"
    PROCEDURAL = "procedural"
    WRITE_BLOCKED = "write_blocked"


FactField = Literal["value", "entity_id", "label"]


@dataclass(frozen=True, slots=True)
class FactReference:
    """Referencia a un hecho de un paso anterior. Nunca texto pegado de un resultado."""

    step_id: StepId
    fact: str
    field: FactField = "value"

    def __post_init__(self) -> None:
        if not self.fact or len(self.fact) > MAX_FACT_KEY:
            msg = f"clave de hecho inválida: {self.fact!r}"
            raise ValidationError(msg)
        if self.field not in ("value", "entity_id", "label"):
            msg = f"campo de referencia inválido: {self.field!r}"
            raise ValidationError(msg)


Scalar = str | int | Decimal | bool
ArgumentValue = Scalar | tuple[Scalar, ...] | FactReference


def _check_scalar(name: str, value: object) -> None:
    if isinstance(value, str):
        if len(value) > MAX_STRING_ARGUMENT:
            msg = f"argumento {name} supera {MAX_STRING_ARGUMENT} caracteres"
            raise ValidationError(msg)
    elif isinstance(value, float) or not isinstance(value, int | Decimal | bool):
        msg = f"argumento {name} de tipo no admitido: {type(value).__name__}"
        raise ValidationError(msg)
    elif isinstance(value, Decimal) and not value.is_finite():
        msg = f"argumento {name} no es un número finito"
        raise ValidationError(msg)


def _check_argument(name: str, value: object) -> None:
    if isinstance(value, FactReference):
        return
    if isinstance(value, tuple):
        if len(value) > MAX_ARRAY_ARGUMENT:
            msg = f"argumento {name} supera {MAX_ARRAY_ARGUMENT} elementos"
            raise ValidationError(msg)
        for item in value:
            _check_scalar(name, item)
        return
    _check_scalar(name, value)


@dataclass(frozen=True, slots=True)
class StepDependency:
    step_id: StepId
    hard: bool = True


@dataclass(frozen=True, slots=True)
class PlanStep:
    step_id: StepId
    agent: AgentId
    system: SystemId
    tool: str
    arguments: Mapping[str, ArgumentValue] = field(default_factory=dict)
    depends_on: tuple[StepDependency, ...] = ()
    optional: bool = False

    def __post_init__(self) -> None:
        if not (
            1 < len(self.tool) <= TOOL_NAME_MAX
            and self.tool[0].isascii()
            and self.tool[0].islower()
            and all(c.isascii() and (c.islower() or c.isdigit() or c == "_") for c in self.tool)
        ):
            msg = f"nombre de herramienta inválido: {self.tool!r}"
            raise ValidationError(msg)
        for name, value in self.arguments.items():
            _check_argument(name, value)
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))
        object.__setattr__(
            self, "depends_on", tuple(sorted(self.depends_on, key=lambda d: d.step_id.number))
        )

    @property
    def references(self) -> tuple[FactReference, ...]:
        """Referencias a hechos de otros pasos, en sus argumentos."""
        return tuple(v for v in self.arguments.values() if isinstance(v, FactReference))


@dataclass(frozen=True, slots=True)
class CrossJoin:
    """Unión de resultados de varios agentes. Solo con mapa de entidades declarado (6.11)."""

    entity: str
    canonical_id: str
    steps: tuple[StepId, ...]
    on_missing: Literal["hueco_explicito"] = "hueco_explicito"

    def __post_init__(self) -> None:
        if not self.entity or not self.canonical_id:
            msg = "join exige entity y canonical_id"
            raise ValidationError(msg)
        object.__setattr__(self, "steps", tuple(sorted(self.steps, key=lambda s: s.number)))
        on_missing: object = self.on_missing  # puede llegar sin tipar desde fuera
        if on_missing != "hueco_explicito":
            msg = "join solo admite on_missing=hueco_explicito"
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class PlanLimits:
    max_rounds: int
    max_tool_calls: int
    max_repairs: int

    def __post_init__(self) -> None:
        for name, value, low, high in (
            ("max_rounds", self.max_rounds, 1, 3),
            ("max_tool_calls", self.max_tool_calls, 0, MAX_STEPS),
            ("max_repairs", self.max_repairs, 0, 2),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                msg = f"{name} fuera de rango [{low}, {high}]: {value!r}"
                raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class QueryPlan:
    plan_id: PlanId
    intent: Intent
    steps: tuple[PlanStep, ...]
    catalog_versions: Mapping[SystemId, str]
    limits: PlanLimits
    agents: tuple[AgentId, ...] = ()
    join: CrossJoin | None = None
    round: int = 1
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "steps", tuple(sorted(self.steps, key=lambda s: s.step_id.number)))
        object.__setattr__(self, "catalog_versions", MappingProxyType(dict(self.catalog_versions)))
        object.__setattr__(self, "agents", tuple(sorted(self.agents)))
        issues = _structural_issues(self)
        if issues:
            raise InvalidPlanError(tuple(issues))

    @property
    def systems(self) -> frozenset[SystemId]:
        """Sistemas que tocan los pasos. Se deriva; no se declara (ADR-043)."""
        return frozenset(step.system for step in self.steps)

    @property
    def step_ids(self) -> tuple[StepId, ...]:
        return tuple(step.step_id for step in self.steps)

    def step(self, step_id: StepId) -> PlanStep:
        for candidate in self.steps:
            if candidate.step_id == step_id:
                return candidate
        msg = f"el plan no tiene el paso {step_id}"
        raise KeyError(msg)

    def execution_waves(self) -> tuple[tuple[StepId, ...], ...]:
        """Pasos agrupados en oleadas: los de una misma oleada se ejecutan en paralelo."""
        waves = _waves(self.steps)
        if waves is None:  # imposible: el constructor ya rechazó los ciclos
            msg = "plan con ciclo"
            raise InvalidPlanError((PlanIssue("dependency_cycle", msg),))
        return waves


def _waves(steps: tuple[PlanStep, ...]) -> tuple[tuple[StepId, ...], ...] | None:
    """Orden topológico por niveles. None si hay un ciclo."""
    graph = {s.step_id: frozenset(d.step_id for d in s.depends_on) for s in steps}
    return topological_waves(graph, lambda s: s.number)


def _structural_issues(plan: QueryPlan) -> list[PlanIssue]:
    issues: list[PlanIssue] = []

    def add(code: str, detail: str) -> None:
        issues.append(PlanIssue(code, detail))

    if plan.schema_version != SCHEMA_VERSION:
        add("unsupported_schema_version", f"se esperaba {SCHEMA_VERSION}")
    if isinstance(plan.round, bool) or not isinstance(plan.round, int) or plan.round < 1:
        add("invalid_round", f"round debe ser un entero >= 1: {plan.round!r}")
    elif plan.round > plan.limits.max_rounds:
        add("round_over_limit", f"round {plan.round} supera max_rounds")
    if len(plan.steps) > MAX_STEPS:
        add("too_many_steps", f"{len(plan.steps)} pasos; máximo {MAX_STEPS}")
    if len(plan.steps) > plan.limits.max_tool_calls:
        add("over_tool_call_limit", f"{len(plan.steps)} pasos > max_tool_calls")
    if len(set(plan.agents)) != len(plan.agents):
        add("duplicate_agent", "agents tiene elementos repetidos")

    ids = [s.step_id for s in plan.steps]
    known = set(ids)
    for duplicated in sorted({i for i in ids if ids.count(i) > 1}, key=lambda s: s.number):
        add("duplicate_step_id", f"{duplicated} aparece más de una vez")

    for step in plan.steps:
        if plan.agents and step.agent not in plan.agents:
            add("undeclared_agent", f"{step.step_id} usa {step.agent}, que no está en agents")
        if step.system not in plan.catalog_versions:
            add(
                "missing_catalog_version",
                f"{step.step_id}: sin versión de catálogo de {step.system}",
            )
        dependencies = {d.step_id for d in step.depends_on}
        if len(dependencies) != len(step.depends_on):
            add("duplicate_dependency", f"{step.step_id} repite una dependencia")
        for dep in sorted(dependencies, key=lambda s: s.number):
            if dep not in known:
                add("unknown_step_reference", f"{step.step_id} depende de {dep}, que no existe")
            elif dep == step.step_id:
                add("dependency_cycle", f"{step.step_id} depende de sí mismo")
        for ref in step.references:
            if ref.step_id not in known:
                add("unknown_step_reference", f"{step.step_id} referencia {ref.step_id}")
            elif ref.step_id not in dependencies:
                add(
                    "reference_without_dependency",
                    f"{step.step_id} referencia {ref.step_id} sin declararlo en depends_on",
                )

    has_self_loop = any(i.code == "dependency_cycle" for i in issues)
    has_unknown = any(i.code == "unknown_step_reference" for i in issues)
    acyclic_checkable = not has_self_loop and not has_unknown and len(known) == len(ids)
    if acyclic_checkable and _waves(plan.steps) is None:
        add("dependency_cycle", "el grafo de dependencias tiene un ciclo")

    if plan.join is not None:
        if len(set(plan.join.steps)) < len(plan.join.steps):
            add("invalid_join", "join repite pasos")
        if len(set(plan.join.steps)) < 2:
            add("invalid_join", "join necesita al menos dos pasos distintos")
        for sid in plan.join.steps:
            if sid not in known:
                add("unknown_step_reference", f"join referencia {sid}, que no existe")
    return issues
