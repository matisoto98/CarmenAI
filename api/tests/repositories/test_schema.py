"""Prompt 7: la migración 0001, su ejecutor y la correspondencia esquema ⇄ dominio ⇄ tablas."""

import asyncio
from dataclasses import replace
from pathlib import Path

import asyncpg
import pytest
import sqlalchemy as sa
from sqlalchemy.schema import CreateTable

from carmen.adapters.persistence.engine import Database, UnitOfWorkError, connection
from carmen.adapters.persistence.migrator import (
    MigrationError,
    apply,
    asyncpg_dsn,
    check,
    load_migrations,
)
from carmen.adapters.persistence.schema import ALL_TABLES
from carmen.adapters.persistence.types import EMBEDDING_DIM, metadata, vector_value
from carmen.application.errors import EmbeddingDimensionMismatchError
from carmen.domain.agents.card import AgentLifecycleState
from carmen.domain.approval.models import ApprovalStatus, Impact
from carmen.domain.conversation.turn import TurnStatus
from carmen.domain.delegation.models import AgentResultStatus
from carmen.domain.locale import Locale
from carmen.domain.orchestration.mode import ResponseMode
from carmen.domain.role import Role
from carmen.migrations.__main__ import main as migrations_main
from repositories.pg import Pg

pytestmark = pytest.mark.repositories


#: sha256 de 0001_carmen.sql tal como se fusionó en el Prompt 7. Una migración aplicada no se edita.
CHECKSUM_0001 = (
    "c3eb64dbec03bef9bdc8f4c32b0c6cfe5d5eed3d5786ccca98fdb70ed2d6098e"  # pragma: allowlist secret
)


def test_migration_0001_has_not_changed_since_it_was_merged(pg: Pg) -> None:
    first = load_migrations()[0]
    assert (first.version, first.checksum) == ("0001", CHECKSUM_0001)
    recorded = pg.fetch("SELECT checksum FROM carmen_meta.schema_migrations WHERE version = '0001'")
    assert recorded[0]["checksum"] == CHECKSUM_0001


def test_approval_impacts_match_the_domain(pg: Pg) -> None:
    rows = pg.fetch(
        "SELECT pg_get_constraintdef(c.oid) AS def FROM pg_constraint c"
        " JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace"
        " WHERE n.nspname = 'carmen' AND t.relname = 'approvals' AND c.contype = 'c'"
        " AND pg_get_constraintdef(c.oid) LIKE '%impact%'"
    )
    assert len(rows) == 1
    assert all(f"'{i.value}'" in rows[0]["def"] for i in Impact)
    assert rows[0]["def"].count("'") == 2 * len(Impact)


def test_migrations_are_applied_once_and_check_passes(pg: Pg) -> None:
    report = asyncio.run(check(pg.url))
    assert report.ok
    assert report.applied == tuple(m.version for m in load_migrations())
    assert asyncio.run(apply(pg.url)) == ()  # reaplicar no hace nada


def test_an_edited_migration_fails_check_and_apply_refuses(pg: Pg) -> None:
    edited = tuple(replace(m, sql=m.sql + "\n-- editada\n") for m in load_migrations())
    report = asyncio.run(check(pg.url, edited))
    assert not report.ok
    assert report.changed == tuple(m.version for m in edited)
    with pytest.raises(MigrationError, match="no se edita"):
        asyncio.run(apply(pg.url, edited))


def test_an_applied_migration_missing_from_disk_is_unknown(pg: Pg) -> None:
    report = asyncio.run(check(pg.url, ()))
    assert report.unknown == ("0001", "0002")
    assert not report.ok


@pytest.mark.parametrize(
    ("type_name", "domain_values"),
    [
        ("msg_status", [s.value for s in TurnStatus]),
        ("locale", [loc.value for loc in Locale]),
        ("role", [r.value for r in Role]),
        ("response_mode", [m.value for m in ResponseMode]),
        ("agent_state", [s.value for s in AgentLifecycleState]),
        ("agent_result_status", [s.value for s in AgentResultStatus]),
        ("approval_status", [s.value for s in ApprovalStatus]),
    ],
)
def test_sql_enums_match_domain_enums(pg: Pg, type_name: str, domain_values: list[str]) -> None:
    rows = pg.fetch(
        "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid"
        " JOIN pg_namespace n ON n.oid = t.typnamespace"
        " WHERE n.nspname = 'carmen' AND t.typname = $1 ORDER BY e.enumsortorder",
        type_name,
    )
    assert [r["enumlabel"] for r in rows] == domain_values


def test_every_vector_column_has_the_fixed_dimension(pg: Pg) -> None:
    rows = pg.fetch(
        "SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod) AS type"
        " FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid"
        " JOIN pg_namespace n ON n.oid = c.relnamespace"
        " JOIN pg_type t ON t.oid = a.atttypid"
        " WHERE n.nspname = 'carmen' AND t.typname = 'vector' AND c.relkind = 'r'"
        " ORDER BY 1, 2"
    )
    assert EMBEDDING_DIM == 1024
    assert {(r["relname"], r["attname"]) for r in rows} == {
        ("gaps", "embedding"),
        ("knowledge_chunks", "embedding"),
        ("query_memory", "embedding"),
        ("topics", "centroid"),
    }
    assert {r["type"] for r in rows} == {"vector(1024)"}


def test_a_vector_of_another_dimension_is_rejected_by_adapter_and_database(pg: Pg) -> None:
    with pytest.raises(EmbeddingDimensionMismatchError):
        vector_value((1.0,) * 768)

    async def insert_short_vector() -> None:
        conn = await asyncpg.connect(asyncpg_dsn(pg.url))
        try:
            await conn.execute(
                "INSERT INTO carmen.knowledge_chunks"
                " (source, title, chunk_ix, content, embedding, created_at, updated_at)"
                " VALUES ('doc', 't', 0, 'c', '[1,0,0]', now(), now())"
            )
        finally:
            await conn.close()

    with pytest.raises(asyncpg.DataError, match="1024"):
        asyncio.run(insert_short_vector())


def test_declared_tables_match_the_migrated_schema(pg: Pg) -> None:
    """Los mapeadores escriben en columnas que existen, con su nulabilidad real."""
    rows = pg.fetch(
        "SELECT table_name, column_name, is_nullable FROM information_schema.columns"
        " WHERE table_schema = 'carmen'"
    )
    database = {(r["table_name"], r["column_name"]): r["is_nullable"] == "YES" for r in rows}
    declared: dict[tuple[str, str], bool] = {}
    assert set(ALL_TABLES) == set(metadata.tables.values())
    for table in ALL_TABLES:
        for column in table.columns:
            declared[(table.name, column.name)] = bool(column.nullable)
    assert declared.keys() <= database.keys(), sorted(declared.keys() - database.keys())
    declared_tables = {t for t, _ in declared}
    missing = sorted(k for k in database if k[0] in declared_tables and k not in declared)
    assert not missing, f"columnas del esquema sin declarar en tables.py: {missing}"
    wrong = sorted(k for k, nullable in declared.items() if database[k] != nullable)
    assert not wrong, f"nulabilidad distinta de la migración: {wrong}"
    migrated_tables = {t for t, _ in database}
    assert declared_tables == migrated_tables, sorted(migrated_tables ^ declared_tables)


def test_a_deny_grant_without_reason_is_rejected_by_the_database(pg: Pg) -> None:
    async def insert(reason: str | None) -> None:
        conn = await asyncpg.connect(asyncpg_dsn(pg.url))
        try:
            await conn.execute(
                "INSERT INTO carmen.roles (id, name, version) VALUES ('ops', 'Ops', 'v1')"
                " ON CONFLICT DO NOTHING"
            )
            await conn.execute(
                "INSERT INTO carmen.role_agent_grants (role_id, agent_id, actions, effect, reason)"
                " VALUES ('ops', 'agent.vigia', ARRAY['invoke'], 'deny', $1)",
                reason,
            )
        finally:
            await conn.close()

    for reason in (None, "", "   "):
        with pytest.raises(asyncpg.CheckViolationError, match="ck_deny_reason"):
            asyncio.run(insert(reason))
    asyncio.run(insert("incidente abierto"))
    assert pg.fetch("SELECT reason FROM carmen.role_agent_grants")[0]["reason"] == (
        "incidente abierto"
    )


def test_unit_of_work_is_required_and_not_nested(pg: Pg) -> None:
    with pytest.raises(UnitOfWorkError):
        connection()

    async def nested(db: Database) -> None:
        async with db.unit_of_work():
            await connection().execute(sa.text("SELECT 1"))
            with pytest.raises(UnitOfWorkError):
                async with db.unit_of_work():
                    pass

    pg.run(nested)


def test_declared_vector_and_jsonb_columns_compile_to_the_migrated_types(pg: Pg) -> None:
    dialect = Database(pg.url).engine.dialect  # no conecta: solo compila
    ddl = "\n".join(str(CreateTable(table).compile(dialect=dialect)) for table in ALL_TABLES)
    assert ddl.count("vector(1024)") == 4
    assert "jsonb" in ddl


def test_migration_files_must_follow_the_naming_rule(tmp_path: Path) -> None:
    (tmp_path / "0001_base.sql").write_text("SELECT 1;", encoding="utf-8")
    assert [m.name for m in load_migrations(tmp_path)] == ["base"]
    (tmp_path / "0001_otra.sql").write_text("SELECT 2;", encoding="utf-8")
    with pytest.raises(MigrationError, match="repetidos"):
        load_migrations(tmp_path)
    (tmp_path / "0001_otra.sql").unlink()
    (tmp_path / "2-Mal.sql").write_text("SELECT 3;", encoding="utf-8")
    with pytest.raises(MigrationError, match="inválido"):
        load_migrations(tmp_path)


def test_the_migrations_command_applies_and_checks(
    pg: Pg, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CARMEN_DATABASE_URL", pg.url)
    assert migrations_main([]) == 0
    assert "aplicadas ahora: ninguna" in capsys.readouterr().out
    assert migrations_main(["--check"]) == 0
    assert "pendientes: -" in capsys.readouterr().out


def test_the_migrations_command_fails_on_an_unknown_migration(
    pg: Pg, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pg.fetch(
        "INSERT INTO carmen_meta.schema_migrations (version, name, checksum)"
        " VALUES ('9999', 'futura', 'x')"
    )
    monkeypatch.setenv("CARMEN_DATABASE_URL", pg.url)
    try:
        assert migrations_main(["--check"]) == 1
        assert "desconocidas: 9999" in capsys.readouterr().out
        assert migrations_main([]) == 1
        assert "no se edita" in capsys.readouterr().err
    finally:
        pg.fetch("DELETE FROM carmen_meta.schema_migrations WHERE version = '9999'")
