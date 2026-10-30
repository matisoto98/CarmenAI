"""Ejecutor de migraciones: SQL explícito con checksum (5.4, 9.x «Migraciones»).

Cada fichero `NNNN_nombre.sql` de api/migrations se aplica una vez, en orden y en su propia
transacción, y se registra con el sha256 de su contenido. Una migración aplicada no se edita: si
su fichero cambia, `--check` falla y `apply` se niega a seguir.
"""

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import asyncpg

MIGRATIONS_DIR: Final = Path(__file__).resolve().parents[4] / "migrations"
_NAME: Final = re.compile(r"^(?P<version>[0-9]{4})_(?P<name>[a-z0-9_]+)\.sql$")

_BOOKKEEPING: Final = """
CREATE SCHEMA IF NOT EXISTS carmen_meta;
CREATE TABLE IF NOT EXISTS carmen_meta.schema_migrations (
  version text PRIMARY KEY,
  name text NOT NULL,
  checksum text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);
"""


class MigrationError(RuntimeError):
    """El estado de la base no coincide con los ficheros de migración."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CheckReport:
    applied: tuple[str, ...]
    pending: tuple[str, ...]
    changed: tuple[str, ...]
    unknown: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not (self.pending or self.changed or self.unknown)


def load_migrations(directory: Path = MIGRATIONS_DIR) -> tuple[Migration, ...]:
    """Los ficheros de migración en orden. Un nombre fuera de patrón o un número repetido falla."""
    found: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        match = _NAME.fullmatch(path.name)
        if match is None:
            msg = f"nombre de migración inválido: {path.name}"
            raise MigrationError(msg)
        found.append(Migration(match["version"], match["name"], path.read_text(encoding="utf-8")))
    versions = [m.version for m in found]
    if len(set(versions)) != len(versions):
        msg = f"números de migración repetidos: {versions}"
        raise MigrationError(msg)
    return tuple(found)


def asyncpg_dsn(url: str) -> str:
    """Acepta también la URL de SQLAlchemy (postgresql+asyncpg://)."""
    return re.sub(r"^postgresql\+asyncpg://", "postgresql://", url)


async def _applied(conn: asyncpg.Connection) -> dict[str, str]:
    await conn.execute(_BOOKKEEPING)
    rows = await conn.fetch("SELECT version, checksum FROM carmen_meta.schema_migrations")
    return {str(r["version"]): str(r["checksum"]) for r in rows}


def _report(migrations: Sequence[Migration], applied: dict[str, str]) -> CheckReport:
    known = {m.version for m in migrations}
    return CheckReport(
        applied=tuple(m.version for m in migrations if applied.get(m.version) == m.checksum),
        pending=tuple(m.version for m in migrations if m.version not in applied),
        changed=tuple(
            m.version
            for m in migrations
            if m.version in applied and applied[m.version] != m.checksum
        ),
        unknown=tuple(sorted(v for v in applied if v not in known)),
    )


async def check(url: str, migrations: Sequence[Migration] | None = None) -> CheckReport:
    chosen = load_migrations() if migrations is None else migrations
    conn = await asyncpg.connect(asyncpg_dsn(url))
    try:
        return _report(chosen, await _applied(conn))
    finally:
        await conn.close()


async def apply(url: str, migrations: Sequence[Migration] | None = None) -> tuple[str, ...]:
    """Aplica las pendientes, cada una en su transacción. Devuelve las versiones aplicadas."""
    chosen = load_migrations() if migrations is None else migrations
    conn = await asyncpg.connect(asyncpg_dsn(url))
    try:
        # Un único ejecutor a la vez: el bloqueo se suelta al cerrar la sesión.
        await conn.execute("SELECT pg_advisory_lock(hashtext('carmen_migrations'))")
        report = _report(chosen, await _applied(conn))
        if report.changed or report.unknown:
            msg = (
                f"migraciones modificadas {list(report.changed)} o desconocidas "
                f"{list(report.unknown)}: una migración aplicada no se edita"
            )
            raise MigrationError(msg)
        done: list[str] = []
        for migration in chosen:
            if migration.version not in report.pending:
                continue
            async with conn.transaction():
                await conn.execute(migration.sql)
                await conn.execute(
                    "INSERT INTO carmen_meta.schema_migrations (version, name, checksum)"
                    " VALUES ($1, $2, $3)",
                    migration.version,
                    migration.name,
                    migration.checksum,
                )
            done.append(migration.version)
        return tuple(done)
    finally:
        await conn.close()
