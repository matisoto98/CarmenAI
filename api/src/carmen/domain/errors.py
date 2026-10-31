"""Taxonomía única de errores de dominio (6.6, ADR-017).

Ningún error conoce códigos HTTP: la traducción a HTTP y a SSE vive solo en presentación.
Cada clase concreta tiene un código propio y estable; los grupos intermedios agrupan errores
que se tratan igual, pero no se lanzan por sí mismos.
"""

from dataclasses import dataclass
from typing import ClassVar


class CarmenError(Exception):
    """Raíz de todos los errores de Carmen."""

    code: ClassVar[str] = "carmen_error"
    abstract: ClassVar[bool] = True

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.code)
        self.message = message or self.code


# --- Validación (los crea domain o el validador de plan de application) ---


class ValidationError(CarmenError):
    code = "validation_error"
    abstract = False


class UnknownSystemError(ValidationError):
    code = "unknown_system"


class UnknownToolError(ValidationError):
    code = "unknown_tool"


class InvalidArgumentsError(ValidationError):
    code = "invalid_arguments"


class InvalidTransitionError(ValidationError):
    """Transición de ciclo de vida que no está entre las de 7.11.2."""

    code = "invalid_transition"


# --- Coherencia semántica y cobertura ---


class MetricConflictError(CarmenError):
    code = "metric_conflict"
    abstract = False


class NoCoverageError(CarmenError):
    code = "no_coverage"
    abstract = False


# --- Resultados de sistema que no son fallos ---


class NoDataError(CarmenError):
    code = "no_data"
    abstract = False


class EntityNotResolvedError(CarmenError):
    code = "entity_not_resolved"
    abstract = False


class ForbiddenError(CarmenError):
    code = "forbidden"
    abstract = False


# --- Fallos de un servidor MCP: el sistema se trata como no disponible ---


class McpError(CarmenError):
    code = "mcp_error"


class McpTimeoutError(McpError):
    code = "mcp_timeout"
    abstract = False


class McpUnavailableError(McpError):
    code = "mcp_unavailable"
    abstract = False


class McpContractViolationError(McpError):
    code = "mcp_contract_violation"
    abstract = False


# --- Fallos del modelo ---


class LlmError(CarmenError):
    code = "llm_error"


class LlmUnavailableError(LlmError):
    code = "llm_unavailable"
    abstract = False


class LlmTimeoutError(LlmError):
    code = "llm_timeout"
    abstract = False


# --- Anclaje, cancelación y límite superior ---


class GroundingFailedError(CarmenError):
    code = "grounding_failed"
    abstract = False


class CancelledError(CarmenError):
    code = "cancelled"
    abstract = False


class InternalError(CarmenError):
    """Solo se crea en el límite superior, conservando la causa y la correlación."""

    code = "internal"
    abstract = False

    def __init__(self, message: str = "", correlation_id: str | None = None) -> None:
        super().__init__(message)
        self.correlation_id = correlation_id


# --- Rechazo de un plan: la validación es previa y total (6.2.3) ---


@dataclass(frozen=True, slots=True)
class PlanIssue:
    """Un motivo de rechazo, con código estable y detalle legible."""

    code: str
    detail: str


class InvalidPlanError(ValidationError):
    """Un plan mal formado. Reúne TODOS los motivos, no solo el primero."""

    code = "invalid_plan"

    def __init__(self, issues: tuple[PlanIssue, ...]) -> None:
        super().__init__("; ".join(f"{i.code}: {i.detail}" for i in issues))
        self.issues = issues

    @property
    def codes(self) -> frozenset[str]:
        return frozenset(issue.code for issue in self.issues)
