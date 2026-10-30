"""Delegación: lo que el supervisor encarga y lo que cada agente devuelve (6.12.3 a 6.12.5).

El supervisor habla de agentes, nunca de herramientas: un AgentTask no admite nombres de
herramienta. Un agente devuelve evidencia estructurada, nunca texto libre como resultado
principal. Un agente que necesita otra especialidad propone un DOMINIO, nunca un agente.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from carmen.domain.approval.models import ApprovalRecord
from carmen.domain.errors import InvalidPlanError, PlanIssue, ValidationError
from carmen.domain.evidence.models import EvidenceFact, EvidenceItem, EvidenceMedia, EvidencePassage
from carmen.domain.graph import topological_waves
from carmen.domain.ids import (
    AgentId,
    CallId,
    DelegatedIdentityRef,
    DelegationPlanId,
    PrincipalId,
    ProviderId,
    RunId,
    TaskId,
    TurnId,
)
from carmen.domain.locale import Locale
from carmen.domain.model_output import ModelOutput
from carmen.domain.orchestration.mode import ResponseMode
from carmen.domain.policy.models import PolicyDecision
from carmen.domain.system import SystemId
from carmen.domain.text import require_non_negative, require_text
from carmen.domain.time import Instant

SCHEMA_VERSION: Final = "1.0"
MAX_TASKS: Final = 12

# Un identificador con guion bajo (query_metric) o con llamada (fn()) es vocabulario de
# herramientas, no de dominio: el objetivo de una tarea se escribe en lenguaje de negocio.
_TOOL_LIKE: Final = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b|\w\(\)")
_AGENT_LIKE: Final = re.compile(r"\bagent\.[a-z]")


def _require_money(name: str, value: Decimal) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        msg = f"{name} debe ser un Decimal >= 0: {value!r}"
        raise ValidationError(msg)


class Expects(StrEnum):
    FACTS = "facts"
    PASSAGES = "passages"
    MEDIA = "media"
    MIXED = "mixed"


class AgentDomain(StrEnum):
    """Especialidades a las que un agente puede pedir re-delegación (6.12.5, ADR-044)."""

    MONITORIZACION = "monitorizacion"
    ECONOMICO = "economico"
    DOCUMENTAL = "documental"
    SOPORTE = "soporte"
    LEGAL = "legal"
    CONTRACTUAL = "contractual"


class NeedDelegationReason(StrEnum):
    NEEDS_PROCEDURE = "needs_procedure"
    NEEDS_COMPLEMENTARY_DATA = "needs_complementary_data"
    NEEDS_LEGAL_REVIEW = "needs_legal_review"
    OUT_OF_SCOPE = "out_of_scope"


class AgentResultStatus(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    NO_DATA = "no_data"
    DENIED = "denied"
    FAILED = "failed"


class CompositionKind(StrEnum):
    SINGLE = "single"
    BLOCKS = "blocks"
    JOIN = "join"


@dataclass(frozen=True, slots=True)
class TaskBudgets:
    max_wall_ms: int
    max_tokens: int
    max_cost_eur: Decimal

    def __post_init__(self) -> None:
        require_non_negative("max_wall_ms", self.max_wall_ms)
        require_non_negative("max_tokens", self.max_tokens)
        _require_money("max_cost_eur", self.max_cost_eur)


@dataclass(frozen=True, slots=True)
class Budgets:
    """Presupuesto global del turno."""

    max_wall_ms: int
    max_tokens: int
    max_cost_eur: Decimal
    max_agents: int

    def __post_init__(self) -> None:
        require_non_negative("max_wall_ms", self.max_wall_ms)
        require_non_negative("max_tokens", self.max_tokens)
        _require_money("max_cost_eur", self.max_cost_eur)
        require_non_negative("max_agents", self.max_agents)
        if self.max_agents < 1:
            msg = "max_agents debe ser al menos 1"
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class NeedDelegation:
    """Señal de que hace falta otra especialidad. Propone dominio, NUNCA agente."""

    reason: NeedDelegationReason
    suggested_domain: AgentDomain
    context_ref: str
    rationale: str

    def __post_init__(self) -> None:
        require_text("context_ref", self.context_ref)
        require_text("rationale", self.rationale)
        for name, value in (("context_ref", self.context_ref), ("rationale", self.rationale)):
            if _AGENT_LIKE.search(value):
                msg = f"NeedDelegation.{name} no puede nombrar agentes: solo dominio"
                raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class AgentTask:
    """Lo que Carmen encarga a UN agente. Autocontenido: el agente no ve el resto del plan.

    No contiene nombres de herramienta, otros tasks salvo por depends_on, credenciales en
    claro ni el prompt del supervisor. La identidad delegada viaja como referencia.
    """

    task_id: TaskId
    agent_id: AgentId
    objective: str
    entities: Mapping[str, str]
    expects: Expects
    locale: Locale
    budgets: TaskBudgets
    delegated_identity: DelegatedIdentityRef
    depends_on: tuple[TaskId, ...] = ()
    optional: bool = False

    def __post_init__(self) -> None:
        require_text("objective", self.objective)
        tool_like = _TOOL_LIKE.search(self.objective)
        if tool_like:
            msg = (
                f"{self.task_id}: el objetivo nombra una herramienta ({tool_like.group(0)!r});"
                " las herramientas son del agente"
            )
            raise ValidationError(msg)
        for key, value in self.entities.items():
            require_text("entities (clave)", key)
            require_text(f"entities.{key}", value)
        identity: object = self.delegated_identity  # un str con el token no basta
        if not isinstance(identity, DelegatedIdentityRef):
            msg = f"{self.task_id}: la identidad delegada viaja como referencia, nunca como token"
            raise ValidationError(msg)
        if self.task_id in self.depends_on:
            msg = f"{self.task_id} depende de sí mismo"
            raise ValidationError(msg)
        if len(set(self.depends_on)) != len(self.depends_on):
            msg = f"{self.task_id} repite una dependencia"
            raise ValidationError(msg)
        object.__setattr__(self, "entities", MappingProxyType(dict(self.entities)))
        object.__setattr__(
            self, "depends_on", tuple(sorted(self.depends_on, key=lambda t: t.number))
        )


@dataclass(frozen=True, slots=True)
class Composition:
    """Cómo se compone el resultado: una tarea, bloques por agente o unión por entidad."""

    kind: CompositionKind
    tasks: tuple[TaskId, ...]
    entity: str | None = None
    canonical_id: str | None = None
    on_missing: str = "hueco_explicito"

    def __post_init__(self) -> None:
        if len(set(self.tasks)) != len(self.tasks):
            msg = "composition repite tareas"
            raise ValidationError(msg)
        if self.on_missing != "hueco_explicito":
            msg = "composition solo admite on_missing=hueco_explicito"
            raise ValidationError(msg)
        if self.kind is CompositionKind.SINGLE and len(self.tasks) != 1:
            msg = "composition single compone exactamente una tarea"
            raise ValidationError(msg)
        if self.kind is not CompositionKind.SINGLE and len(self.tasks) < 2:
            msg = f"composition {self.kind} necesita al menos dos tareas"
            raise ValidationError(msg)
        if self.kind is CompositionKind.JOIN:
            if not self.entity or not self.canonical_id:
                msg = "composition join exige entity y canonical_id"
                raise ValidationError(msg)
        elif self.entity is not None or self.canonical_id is not None:
            msg = f"composition {self.kind} no lleva entity ni canonical_id"
            raise ValidationError(msg)
        object.__setattr__(self, "tasks", tuple(sorted(self.tasks, key=lambda t: t.number)))


@dataclass(frozen=True, slots=True)
class AgentWarning:
    code: str
    message: str

    def __post_init__(self) -> None:
        require_text("warning.code", self.code)
        require_text("warning.message", self.message)


@dataclass(frozen=True, slots=True)
class ToolCallTrace:
    call_id: CallId
    system_id: SystemId
    tool_name: str
    ms: int
    ok: bool

    def __post_init__(self) -> None:
        require_text("tool_name", self.tool_name)
        require_non_negative("ms", self.ms)


@dataclass(frozen=True, slots=True)
class ExternalCallTrace:
    """Toda llamada externa queda registrada (5.15.7). En v1 no debe existir ninguna."""

    policy_id: str
    at: Instant
    provider: ProviderId | None = None
    domain: str | None = None
    redactions: tuple[str, ...] = ()
    tokens: int = 0
    cost_eur: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        require_text("policy_id", self.policy_id)
        if self.provider is None and not self.domain:
            msg = "una llamada externa va a un proveedor o a un dominio"
            raise ValidationError(msg)
        require_non_negative("tokens", self.tokens)
        _require_money("cost_eur", self.cost_eur)


@dataclass(frozen=True, slots=True)
class AgentRun:
    run_id: RunId
    agent_id: AgentId
    started_at: Instant
    ended_at: Instant
    tokens_in: int = 0
    tokens_out: int = 0
    cost_eur: Decimal = Decimal(0)
    tool_calls: tuple[ToolCallTrace, ...] = ()
    external: tuple[ExternalCallTrace, ...] = ()
    policy_checks: tuple[PolicyDecision, ...] = ()
    approvals: tuple[ApprovalRecord, ...] = ()

    def __post_init__(self) -> None:
        if self.ended_at < self.started_at:
            msg = f"{self.run_id}: termina antes de empezar"
            raise ValidationError(msg)
        require_non_negative("tokens_in", self.tokens_in)
        require_non_negative("tokens_out", self.tokens_out)
        _require_money("cost_eur", self.cost_eur)

    @property
    def duration_ms(self) -> int:
        return int((self.ended_at.at - self.started_at.at).total_seconds() * 1000)


_EVIDENCE_TYPES: Final = (EvidenceFact, EvidencePassage, EvidenceMedia)


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Lo que devuelve un agente. Evidencia y texto de modelo van en campos separados."""

    task_id: TaskId
    agent_id: AgentId
    agent_version: str
    status: AgentResultStatus
    run: AgentRun
    evidence: tuple[EvidenceItem, ...] = ()
    warnings: tuple[AgentWarning, ...] = ()
    need_delegation: NeedDelegation | None = None
    model_outputs: tuple[ModelOutput, ...] = field(default=())

    def __post_init__(self) -> None:
        require_text("agent_version", self.agent_version)
        if self.run.agent_id != self.agent_id:
            msg = f"{self.task_id}: la ejecución es de otro agente ({self.run.agent_id})"
            raise ValidationError(msg)
        items: tuple[object, ...] = self.evidence
        if not all(isinstance(item, _EVIDENCE_TYPES) for item in items):
            msg = f"{self.task_id}: solo hechos, pasajes o adjuntos son evidencia"
            raise ValidationError(msg)
        outputs: tuple[object, ...] = self.model_outputs
        if not all(isinstance(output, ModelOutput) for output in outputs):
            msg = f"{self.task_id}: model_outputs solo admite ModelOutput"
            raise ValidationError(msg)
        produces = self.status in (AgentResultStatus.OK, AgentResultStatus.PARTIAL)
        if produces and not self.evidence:
            msg = (
                f"{self.task_id}: {self.status} sin evidencia; el texto libre no es un"
                " resultado principal"
            )
            raise ValidationError(msg)
        if not produces and self.evidence:
            msg = f"{self.task_id}: {self.status} no lleva evidencia"
            raise ValidationError(msg)
        if self.status is AgentResultStatus.PARTIAL and not self.warnings:
            msg = f"{self.task_id}: partial exige avisos que expliquen qué falta"
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class DelegationPlan:
    """Plan global del supervisor: qué agentes, con qué tareas, en qué orden y presupuesto."""

    plan_id: DelegationPlanId
    turn_id: TurnId
    response_mode: ResponseMode
    principal_id: PrincipalId
    policy_version: str
    tasks: tuple[AgentTask, ...]
    composition: Composition
    budgets: Budgets
    requires_human_approval: bool = False
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "tasks", tuple(sorted(self.tasks, key=lambda t: t.task_id.number)))
        issues = _plan_issues(self)
        if issues:
            raise InvalidPlanError(tuple(issues))

    @property
    def agents(self) -> frozenset[AgentId]:
        return frozenset(task.agent_id for task in self.tasks)

    def task(self, task_id: TaskId) -> AgentTask:
        for candidate in self.tasks:
            if candidate.task_id == task_id:
                return candidate
        msg = f"el plan no tiene la tarea {task_id}"
        raise KeyError(msg)

    def execution_waves(self) -> tuple[tuple[TaskId, ...], ...]:
        """Tareas agrupadas en oleadas: las de una oleada se delegan en paralelo."""
        waves = topological_waves(_graph(self.tasks), lambda t: t.number)
        if waves is None:  # imposible: el constructor ya rechazó los ciclos
            raise InvalidPlanError((PlanIssue("dependency_cycle", "plan con ciclo"),))
        return waves


def _graph(tasks: tuple[AgentTask, ...]) -> dict[TaskId, frozenset[TaskId]]:
    return {t.task_id: frozenset(t.depends_on) for t in tasks}


def _longest_wall_ms(tasks: tuple[AgentTask, ...]) -> int:
    """Tiempo del camino crítico: las tareas de una cadena de dependencias se suman."""
    by_id = {t.task_id: t for t in tasks}
    waves = topological_waves(_graph(tasks), lambda t: t.number) or ()
    finish: dict[TaskId, int] = {}
    for wave in waves:
        for task_id in wave:
            task = by_id[task_id]
            start = max((finish[d] for d in task.depends_on), default=0)
            finish[task_id] = start + task.budgets.max_wall_ms
    return max(finish.values(), default=0)


def _plan_issues(plan: DelegationPlan) -> list[PlanIssue]:
    issues: list[PlanIssue] = []

    def add(code: str, detail: str) -> None:
        issues.append(PlanIssue(code, detail))

    if plan.schema_version != SCHEMA_VERSION:
        add("unsupported_schema_version", f"se esperaba {SCHEMA_VERSION}")
    if not plan.policy_version.strip():
        add("missing_policy_version", "policy_version es obligatorio para reproducir")
    if not plan.response_mode.delegates:
        add("mode_without_delegation", f"{plan.response_mode} no produce DelegationPlan")
    elif plan.response_mode is ResponseMode.DELEGATE_SINGLE and len(plan.tasks) != 1:
        add("mode_task_mismatch", "DELEGATE_SINGLE lleva exactamente una tarea")
    elif plan.response_mode is ResponseMode.DELEGATE_MULTI and len(plan.tasks) < 2:
        add("mode_task_mismatch", "DELEGATE_MULTI lleva al menos dos tareas")
    if len(plan.tasks) > MAX_TASKS:
        add("too_many_tasks", f"{len(plan.tasks)} tareas; máximo {MAX_TASKS}")

    ids = [t.task_id for t in plan.tasks]
    known = set(ids)
    for duplicated in sorted({i for i in ids if ids.count(i) > 1}, key=lambda t: t.number):
        add("duplicate_task_id", f"{duplicated} aparece más de una vez")
    unknown = False
    for task in plan.tasks:
        for dep in task.depends_on:
            if dep not in known:
                unknown = True
                add("unknown_task_reference", f"{task.task_id} depende de {dep}, que no existe")
    checkable = not unknown and len(known) == len(ids)
    if checkable and topological_waves(_graph(plan.tasks), lambda t: t.number) is None:
        add("dependency_cycle", "el grafo de dependencias entre tareas tiene un ciclo")

    for task_id in plan.composition.tasks:
        if task_id not in known:
            add("unknown_task_reference", f"composition referencia {task_id}, que no existe")
    if plan.response_mode is ResponseMode.DELEGATE_MULTI and (
        plan.composition.kind is CompositionKind.SINGLE
    ):
        add("composition_mismatch", "DELEGATE_MULTI no se compone como single")

    if len(plan.agents) > plan.budgets.max_agents:
        add("over_agent_limit", f"{len(plan.agents)} agentes > max_agents")
    tokens = sum(t.budgets.max_tokens for t in plan.tasks)
    if tokens > plan.budgets.max_tokens:
        add("over_budget", f"tokens de las tareas {tokens} > global {plan.budgets.max_tokens}")
    cost = sum((t.budgets.max_cost_eur for t in plan.tasks), Decimal(0))
    if cost > plan.budgets.max_cost_eur:
        add("over_budget", f"coste de las tareas {cost} > global {plan.budgets.max_cost_eur}")
    wall = _longest_wall_ms(plan.tasks)  # 0 si el grafo no es válido: ya hay motivo
    if wall > plan.budgets.max_wall_ms:
        add("over_budget", f"camino crítico {wall} ms > global {plan.budgets.max_wall_ms}")
    return issues
