"""Intercambio de identidad delegada simulado (7.8.1)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from carmen.application.context import UserToken
from carmen.application.errors import IdentityRejectedError, IdentityUnavailableError
from carmen.application.ports.identity import Audience, DelegatedToken
from carmen.application.ports.system import Clock
from carmen.domain.ids import Scope
from carmen.domain.time import Instant
from support.fakes.system import FrozenClock


@dataclass(frozen=True, slots=True)
class Exchange:
    """Lo que se registra de un intercambio: destinatario y scopes, nunca el token."""

    audience: Audience
    scopes: frozenset[Scope]


class FakeTokenExchange:
    def __init__(
        self,
        *,
        clock: Clock | None = None,
        ttl: timedelta = timedelta(minutes=5),
        rejected: frozenset[Audience] = frozenset(),
        available: bool = True,
    ) -> None:
        self._clock = clock or FrozenClock()
        self._ttl = ttl
        self._rejected = rejected
        self._available = available
        self.exchanges: list[Exchange] = []

    async def exchange(
        self, *, user_token: UserToken, audience: Audience, scopes: Sequence[Scope]
    ) -> DelegatedToken:
        if not self._available:
            msg = "el proveedor de identidad no responde"
            raise IdentityUnavailableError(msg)
        if audience in self._rejected:
            msg = f"intercambio rechazado para {audience}"
            raise IdentityRejectedError(msg)
        granted = frozenset(scopes)
        self.exchanges.append(Exchange(audience, granted))
        now = self._clock.now()
        return DelegatedToken(
            value=f"delegated-{len(self.exchanges)}-{len(user_token.value)}",
            audience=audience,
            scopes=granted,
            expires_at=Instant(now.at + self._ttl),
        )
