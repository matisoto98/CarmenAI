"""Intercambio de identidad delegada: on-behalf-of por llamada (invariante 2, 7.8.1).

Solo lo usa el ejecutor de agente. El supervisor no puede importarlo (5.5).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from carmen.application.context import UserToken
from carmen.domain.ids import PatternId, Scope
from carmen.domain.text import require_text
from carmen.domain.time import Instant


class Audience(PatternId):
    """Destinatario del token delegado: el servidor MCP de un sistema."""

    __slots__ = ()
    pattern = re.compile(r"^(api://|https://)[A-Za-z0-9._/-]{1,200}$")


@dataclass(frozen=True, slots=True)
class DelegatedToken:
    """Token delegado para UN destinatario y unos scopes. Nunca entra en el contexto del modelo."""

    value: str = field(repr=False)
    audience: Audience
    scopes: frozenset[Scope]
    expires_at: Instant

    def __post_init__(self) -> None:
        require_text("token", self.value)

    def __str__(self) -> str:
        return f"DelegatedToken({self.audience}, ***)"

    def valid_at(self, now: Instant) -> bool:
        return now < self.expires_at


class TokenExchangePort(Protocol):
    async def exchange(
        self, *, user_token: UserToken, audience: Audience, scopes: Sequence[Scope]
    ) -> DelegatedToken:
        """Intercambio delegado.

        Lanza: IdentityUnavailableError, IdentityRejectedError, IdentityTimeoutError.
        """
        ...
