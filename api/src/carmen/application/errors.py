"""Fallos tipados que declara cada método de puerto (5.5, 5.13.4, 5.15.6).

No son códigos nuevos: cada uno refina un error de la taxonomía de 6.6 y hereda su código, así
presentación los traduce sin conocerlos. El árbol sigue teniendo su raíz en el dominio (ADR-046).
"""

from carmen.domain.errors import (
    ForbiddenError,
    LlmTimeoutError,
    LlmUnavailableError,
    McpContractViolationError,
    McpTimeoutError,
    McpUnavailableError,
)

# --- Modelo de lenguaje y embeddings ---


class LlmMalformedOutputError(LlmUnavailableError):
    """El modelo respondió, pero no con la estructura pedida."""


class EmbeddingUnavailableError(LlmUnavailableError):
    pass


class EmbeddingTimeoutError(LlmTimeoutError):
    pass


class EmbeddingDimensionMismatchError(LlmUnavailableError):
    """El vector no tiene la dimensión fija con la que arrancó el sistema (corrección C2)."""


# --- MCP e identidad delegada: el sistema se trata como no disponible o se deniega ---


class McpUnauthorizedError(ForbiddenError):
    pass


class McpForbiddenError(ForbiddenError):
    pass


class McpToolError(McpUnavailableError):
    """La herramienta respondió con un error propio."""


class IdentityUnavailableError(McpUnavailableError):
    pass


class IdentityRejectedError(ForbiddenError):
    pass


class IdentityTimeoutError(McpTimeoutError):
    pass


# --- Ejecución de un agente: un agente caído es un agente ausente, no un turno fallido ---


class AgentUnavailableError(McpUnavailableError):
    pass


class AgentTimeoutError(McpTimeoutError):
    pass


class AgentContractViolationError(McpContractViolationError):
    """El agente devolvió algo que no es un AgentResult válido."""


# --- Salida externa y proveedores de modelo (5.15.6): siempre antes de abrir la conexión ---


class ClassificationDeniedError(ForbiddenError):
    """La clase del dato supera lo que admite el destino."""


class BudgetExceededError(ForbiddenError):
    pass


class ProviderNotBoundError(ForbiddenError):
    """El proveedor no está registrado o no está ligado a ese agente."""


class EgressDomainNotAllowedError(ForbiddenError):
    pass


class EgressClassificationDeniedError(ClassificationDeniedError):
    pass


class EgressBudgetExceededError(BudgetExceededError):
    pass


class EgressUnavailableError(McpUnavailableError):
    pass
