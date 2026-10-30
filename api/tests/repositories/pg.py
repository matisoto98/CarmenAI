"""PostgreSQL real para las pruebas de repositorio (etapa 5).

Se usa una base PROPIA de pruebas, nunca la de desarrollo: al empezar la sesión se borran sus
esquemas y se aplican las migraciones desde cero, y antes de cada prueba se vacían las tablas.
La URL sale de CARMEN_TEST_DATABASE_URL; sin ella, carmen_test en el PostgreSQL local (4.6.2).
Si la base no existe se crea, conectando a la base de mantenimiento del mismo servidor.

No hay pytest-asyncio: cada prueba ejecuta su escenario con `pg.run(...)`, que crea el motor
dentro del bucle de eventos del escenario y lo libera al terminar.
"""

import asyncio
import math
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit, urlunsplit

import asyncpg

from carmen.adapters.persistence.engine import Database
from carmen.adapters.persistence.migrator import apply, asyncpg_dsn
from carmen.adapters.persistence.types import EMBEDDING_DIM

DEFAULT_TEST_URL: Final = (
    "postgresql://carmen:carmen@localhost:5432/carmen_test"  # pragma: allowlist secret
)
SCHEMAS: Final = ("carmen", "carmen_meta")


def database_url() -> str:
    return os.environ.get("CARMEN_TEST_DATABASE_URL", DEFAULT_TEST_URL)


async def _ensure_database(url: str) -> None:
    parts = urlsplit(asyncpg_dsn(url))
    name = parts.path.lstrip("/")
    maintenance = urlunsplit(parts._replace(path="/postgres"))
    conn = await asyncpg.connect(maintenance)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


async def reset(url: str) -> None:
    await _ensure_database(url)
    conn = await asyncpg.connect(asyncpg_dsn(url))
    try:
        for schema in SCHEMAS:
            await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    finally:
        await conn.close()
    await apply(url)


async def truncate(url: str) -> None:
    conn = await asyncpg.connect(asyncpg_dsn(url))
    try:
        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'carmen' ORDER BY tablename"
        )
        names = ", ".join(f"carmen.{t['tablename']}" for t in tables)
        await conn.execute(f"TRUNCATE {names} CASCADE")
    finally:
        await conn.close()


@dataclass(frozen=True, slots=True)
class Pg:
    """Acceso a la base de pruebas desde una prueba síncrona."""

    url: str

    def run[T](self, scenario: Callable[[Database], Awaitable[T]]) -> T:
        async def main() -> T:
            db = Database(self.url, pool_size=10, max_overflow=15)
            try:
                return await scenario(db)
            finally:
                await db.dispose()

        return asyncio.run(main())

    def fetch(self, sql: str, *args: object) -> list[asyncpg.Record]:
        """Lectura directa, fuera de los repositorios, para comprobar lo que quedó escrito."""

        async def main() -> list[asyncpg.Record]:
            conn = await asyncpg.connect(asyncpg_dsn(self.url))
            try:
                return list(await conn.fetch(sql, *args))
            finally:
                await conn.close()

        return asyncio.run(main())


def unit_vector(angle: float) -> tuple[float, ...]:
    """Vector unitario en el plano de los dos primeros ejes: el coseno entre dos de ellos es
    cos(a - b), así una prueba fija la similitud que quiere.
    """
    return (math.cos(angle), math.sin(angle), *([0.0] * (EMBEDDING_DIM - 2)))
