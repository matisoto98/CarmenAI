"""Motor, conexión y unidad de trabajo (7.2, 7.4).

La transacción la abre y la cierra el caso de uso con `async with db.unit_of_work():`. Los
repositorios no abren transacciones: toman la conexión de la unidad de trabajo en curso y, si no
hay ninguna, fallan. Así ningún repositorio decide su propio límite transaccional.
"""

import re
from contextvars import ContextVar, Token
from types import TracebackType
from typing import Final, Self

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncTransaction,
    create_async_engine,
)

_CURRENT: Final[ContextVar[AsyncConnection | None]] = ContextVar(
    "carmen_unit_of_work", default=None
)


class UnitOfWorkError(RuntimeError):
    """Se usó un repositorio fuera de una unidad de trabajo, o se anidaron dos."""


def sqlalchemy_url(url: str) -> str:
    """postgresql://… → postgresql+asyncpg://… (la de --check y la del motor son la misma)."""
    return re.sub(r"^postgresql(\+asyncpg)?://", "postgresql+asyncpg://", url)


def connection() -> AsyncConnection:
    """La conexión de la unidad de trabajo en curso."""
    current = _CURRENT.get()
    if current is None:
        msg = "un repositorio solo se usa dentro de una unidad de trabajo (7.4)"
        raise UnitOfWorkError(msg)
    return current


class UnitOfWork:
    """Una transacción: todo lo que se escribe dentro se confirma junto o no se confirma nada."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._connection: AsyncConnection | None = None
        self._transaction: AsyncTransaction | None = None
        self._token: Token[AsyncConnection | None] | None = None

    async def __aenter__(self) -> Self:
        if _CURRENT.get() is not None:
            msg = "las unidades de trabajo no se anidan: cada una es su propia transacción"
            raise UnitOfWorkError(msg)
        self._connection = await self._engine.connect()
        self._transaction = await self._connection.begin()
        self._token = _CURRENT.set(self._connection)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._connection is not None
        assert self._transaction is not None
        assert self._token is not None
        try:
            if exc_type is None:
                await self._transaction.commit()
            else:
                await self._transaction.rollback()
        finally:
            _CURRENT.reset(self._token)
            await self._connection.close()


class Database:
    """El motor de la aplicación. El tiempo máximo de sentencia lo impone el servidor."""

    def __init__(self, url: str, *, pool_size: int = 10, max_overflow: int = 10) -> None:
        self.engine: Final = create_async_engine(
            sqlalchemy_url(url),
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
        )

    def unit_of_work(self) -> UnitOfWork:
        return UnitOfWork(self.engine)

    async def dispose(self) -> None:
        await self.engine.dispose()
