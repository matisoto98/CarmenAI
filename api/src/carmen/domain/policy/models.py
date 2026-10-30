"""Política: quién puede descubrir, describir e invocar qué agente (5.14.4, 7.9.2).

Aquí están los tipos y sus reglas de forma. El algoritmo de resolución (denegación por defecto,
el deny explícito gana) es de application/policy (Prompt 10).
"""

from dataclasses import dataclass
from enum import StrEnum

from carmen.domain.errors import ValidationError
from carmen.domain.ids import AgentId, PrincipalId, RoleId, Scope, TurnId
from carmen.domain.text import require_text
from carmen.domain.time import Instant


class AgentAction(StrEnum):
    """Tres permisos distintos sobre un agente (5.14.4)."""

    DISCOVER = "discover"
    DESCRIBE = "describe"
    INVOKE = "invoke"


class PlatformAction(StrEnum):
    """Acciones de plataforma (7.9.4). Ninguna concede acceso a datos de negocio."""

    CARMEN_ADMIN = "carmen.admin"
    AGENTS_MANAGE = "agents.manage"
    GLOSSARY_WRITE = "glossary.write"
    POLICY_WRITE = "policy.write"
    KPIS_READ = "kpis.read"
    TOPICS_READ = "topics.read"
    AUDIT_READ = "audit.read"


class Effect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class AssignmentSource(StrEnum):
    DIRECTORY = "directory"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class Principal:
    principal_id: PrincipalId
    directory_ref: str
    display_name: str
    active: bool

    def __post_init__(self) -> None:
        require_text("directory_ref", self.directory_ref)
        require_text("display_name", self.display_name)


@dataclass(frozen=True, slots=True)
class PolicyRole:
    """Rol de la política versionada (7.9.2). No confundir con el Role de plataforma."""

    role_id: RoleId
    name: str
    platform_actions: frozenset[PlatformAction]
    version: str

    def __post_init__(self) -> None:
        require_text("name", self.name)
        require_text("version", self.version)


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    principal_id: PrincipalId
    role_id: RoleId
    source: AssignmentSource


@dataclass(frozen=True, slots=True)
class RoleAgentGrant:
    """Concesión de un rol sobre un agente. Un deny exige motivo (ck_deny_reason)."""

    role_id: RoleId
    agent_id: AgentId
    actions: frozenset[AgentAction]
    effect: Effect
    scopes: frozenset[Scope] = frozenset()
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.actions:
            msg = f"{self.role_id} -> {self.agent_id}: una concesión necesita acciones"
            raise ValidationError(msg)
        if self.effect is Effect.DENY and (self.reason is None or not self.reason.strip()):
            msg = f"{self.role_id} -> {self.agent_id}: un deny exige motivo"
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Resultado reproducible de evaluar la política: qué, a quién, con qué versión y por qué."""

    turn_id: TurnId
    principal_id: PrincipalId
    action: AgentAction | PlatformAction
    decision: Effect
    reason_code: str
    policy_version: str
    decided_at: Instant
    agent_id: AgentId | None = None
    scopes: frozenset[Scope] = frozenset()

    def __post_init__(self) -> None:
        require_text("reason_code", self.reason_code)
        require_text("policy_version", self.policy_version)
        if isinstance(self.action, AgentAction) and self.agent_id is None:
            msg = "una decisión sobre una acción de agente exige agent_id"
            raise ValidationError(msg)
        if isinstance(self.action, PlatformAction) and self.agent_id is not None:
            msg = "una acción de plataforma no se decide sobre un agente"
            raise ValidationError(msg)
        if self.decision is Effect.DENY and self.scopes:
            msg = "una denegación no concede scopes"
            raise ValidationError(msg)

    @property
    def allowed(self) -> bool:
        return self.decision is Effect.ALLOW
