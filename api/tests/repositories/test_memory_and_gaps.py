"""Prompt 7: memoria de planes (7.3) y lagunas (unidad de trabajo 2 de 7.4)."""

import asyncio
import math

import pytest

from carmen.adapters.persistence.engine import Database
from carmen.adapters.persistence.gaps.repository import PgGapRepository
from carmen.adapters.persistence.memory.repository import PgMemoryRepository
from carmen.application.errors import EmbeddingDimensionMismatchError
from carmen.application.ports.repositories import (
    GapDraft,
    GapFilter,
    GapId,
    GapStatus,
    MemoryExampleDraft,
    MemoryId,
)
from carmen.domain.errors import ValidationError
from carmen.domain.locale import Locale
from repositories.pg import Pg, unit_vector
from support.builders import PRINCIPAL, at, plan_step, query_plan
from support.fakes.system import FrozenClock, SeqIdGenerator

pytestmark = pytest.mark.repositories


def draft(norm: str, angle: float, locale: Locale = Locale.ES) -> MemoryExampleDraft:
    return MemoryExampleDraft(
        question_norm=norm,
        question=norm.capitalize() + "?",
        embedding=unit_vector(angle),
        plan=query_plan(plan_step(1), plan_step(2, deps=(1,))),
        locale=locale,
        validated_by=PRINCIPAL,
    )


def gap(norm: str, seconds: float = 0, locale: Locale = Locale.ES) -> GapDraft:
    return GapDraft(norm, norm + "?", unit_vector(0.1), locale, "no_coverage", at(seconds))


def memory_repo() -> PgMemoryRepository:
    return PgMemoryRepository(SeqIdGenerator(), FrozenClock())


def test_similar_plans_respect_the_threshold_order_and_active_flag(pg: Pg) -> None:
    repo = memory_repo()

    async def scenario(db: Database) -> None:
        async with db.unit_of_work():
            near = await repo.upsert_example(draft("monitores caidos", 0.2))
            mid = await repo.upsert_example(draft("monitores en ko", 0.6))
            await repo.upsert_example(draft("facturas pendientes", 1.2))
            hidden = await repo.upsert_example(draft("monitores hoy", 0.05))
            await repo.deactivate(hidden, PRINCIPAL)
        async with db.unit_of_work():
            found = await repo.similar_plans(unit_vector(0), k=5, min_sim=0.8)
        assert [e.memory_id for e in found] == [near, mid]
        assert found[0].similarity == pytest.approx(math.cos(0.2), abs=1e-6)
        assert found[0].plan == query_plan(plan_step(1), plan_step(2, deps=(1,)))
        assert found[0].hits == 1
        async with db.unit_of_work():
            assert len(await repo.similar_plans(unit_vector(0), k=1, min_sim=0.0)) == 1
            assert await repo.similar_plans(unit_vector(0), k=5, min_sim=0.999) == []

    pg.run(scenario)


def test_upserting_the_same_question_increments_hits_and_reactivates(pg: Pg) -> None:
    repo = memory_repo()

    async def scenario(db: Database) -> tuple[MemoryId, MemoryId, MemoryId]:
        async with db.unit_of_work():
            first = await repo.upsert_example(draft("monitores caidos", 0.2))
            await repo.deactivate(first, PRINCIPAL)
        async with db.unit_of_work():
            second = await repo.upsert_example(draft("monitores caidos", 0.0))
        async with db.unit_of_work():
            other = await repo.upsert_example(draft("monitores caidos", 0.0, Locale.EN))
        return first, second, other

    first, second, other = pg.run(scenario)
    assert first == second != other
    rows = pg.fetch("SELECT id, hits, active, systems FROM carmen.query_memory ORDER BY id")
    assert [(r["id"], r["hits"], r["active"]) for r in rows] == [
        (str(first), 2, True),
        (str(other), 1, True),
    ]
    assert rows[0]["systems"] == ["vigia"]


def test_memory_rejects_another_dimension_and_unknown_ids(pg: Pg) -> None:
    repo = memory_repo()

    async def scenario(db: Database) -> None:
        async with db.unit_of_work():
            with pytest.raises(EmbeddingDimensionMismatchError):
                await repo.similar_plans((1.0, 0.0), k=3, min_sim=0.5)
        with pytest.raises(ValidationError, match="mem_404404"):
            async with db.unit_of_work():
                await repo.deactivate(MemoryId("mem_404404"), PRINCIPAL)

    pg.run(scenario)


def test_twenty_concurrent_gaps_for_one_question_count_exactly_twenty(pg: Pg) -> None:
    repo = PgGapRepository(SeqIdGenerator())

    async def record_once(db: Database, n: int) -> GapId:
        async with db.unit_of_work():
            return await repo.record(gap("cuantos camiones hay en ruta", n))

    async def scenario(db: Database) -> set[GapId]:
        ids = await asyncio.gather(*(record_once(db, n) for n in range(20)))
        return set(ids)

    ids = pg.run(scenario)
    assert len(ids) == 1
    rows = pg.fetch("SELECT id, occurrences, first_seen, last_seen FROM carmen.gaps")
    assert len(rows) == 1
    assert rows[0]["occurrences"] == 20
    assert rows[0]["id"] == str(next(iter(ids)))
    assert rows[0]["last_seen"] == at(19).at


def test_gap_clusters_filter_and_order_by_occurrences(pg: Pg) -> None:
    repo = PgGapRepository(SeqIdGenerator())

    async def scenario(db: Database) -> None:
        async with db.unit_of_work():
            for _ in range(3):
                await repo.record(gap("camiones en ruta", 1))
            await repo.record(gap("camiones en ruta", 9))
            await repo.record(gap("pedidos de ayer", 2))
            await repo.record(gap("trucks on route", 3, Locale.EN))
            closed = await repo.record(gap("facturas", 4))
        await asyncio.to_thread(
            pg.fetch, "UPDATE carmen.gaps SET status = 'closed' WHERE id = $1", str(closed)
        )
        async with db.unit_of_work():
            clusters = await repo.list_clusters(GapFilter())
            assert [(c.questions, c.occurrences, c.locale) for c in clusters] == [
                (("camiones en ruta?",), 4, Locale.ES),
                (("pedidos de ayer?",), 1, Locale.ES),
                (("trucks on route?",), 1, Locale.EN),
            ]
            assert clusters[0].last_seen == at(9)
            assert clusters[0].cluster_name is None
            spanish = await repo.list_clusters(GapFilter(locale=Locale.ES, min_occurrences=2))
            assert [c.questions for c in spanish] == [("camiones en ruta?",)]
            closed_only = await repo.list_clusters(GapFilter(status=GapStatus.CLOSED))
            assert [c.questions for c in closed_only] == [("facturas?",)]
            assert len(await repo.list_clusters(GapFilter(status=None, limit=2))) == 2

    pg.run(scenario)


def test_gaps_already_clustered_are_listed_as_one_group(pg: Pg) -> None:
    repo = PgGapRepository(SeqIdGenerator())

    async def scenario(db: Database) -> None:
        async with db.unit_of_work():
            await repo.record(gap("camiones en ruta", 1))
            await repo.record(gap("camiones en ruta", 2))
            await repo.record(gap("vehiculos en ruta", 5))
            await repo.record(gap("pedidos de ayer", 3))
        await asyncio.to_thread(
            pg.fetch,
            "UPDATE carmen.gaps SET cluster_id = '00000000-0000-0000-0000-00000000000a',"
            " cluster_name = 'flota en ruta' WHERE question_norm LIKE '%en ruta'",
        )
        async with db.unit_of_work():
            clusters = await repo.list_clusters(GapFilter())
        assert [(c.cluster_name, c.questions, c.occurrences) for c in clusters] == [
            ("flota en ruta", ("camiones en ruta?", "vehiculos en ruta?"), 3),
            (None, ("pedidos de ayer?",), 1),
        ]
        assert clusters[0].last_seen == at(5)

    pg.run(scenario)
