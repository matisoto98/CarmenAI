"""Prompt 7: corpus, brief de fila única (7.3), glosario con historial y temas (7.8.4)."""

from dataclasses import replace
from decimal import Decimal

import pytest

from carmen.adapters.persistence.brief.mappers import fact_to_json
from carmen.adapters.persistence.brief.repository import PgBriefRepository
from carmen.adapters.persistence.engine import Database
from carmen.adapters.persistence.glossary.repository import PgGlossaryRepository
from carmen.adapters.persistence.knowledge.repository import (
    KnowledgeChunkDraft,
    PgKnowledgeRepository,
)
from carmen.adapters.persistence.topics.repository import PgTopicRepository
from carmen.adapters.persistence.types import dumps
from carmen.application.ports.repositories import (
    GlossaryAction,
    GlossaryTerm,
    SituationBrief,
    TermSource,
    Topic,
    TopicId,
    TopicStatus,
)
from carmen.domain.errors import ValidationError
from carmen.domain.evidence.models import EntityRef, PeriodInterpreted
from carmen.domain.system import SystemId
from repositories.pg import Pg, unit_vector
from support.builders import PLENDATA_SYSTEM, PRINCIPAL, VIGIA_SYSTEM, at, evidence_fact
from support.fakes.system import FrozenClock

pytestmark = pytest.mark.repositories


def chunk(source: str, ix: int, angle: float) -> KnowledgeChunkDraft:
    return KnowledgeChunkDraft(source, ix, f"{source} #{ix}", f"contenido {ix}", unit_vector(angle))


def test_knowledge_search_returns_only_chunks_above_the_threshold(pg: Pg) -> None:
    repo = PgKnowledgeRepository(FrozenClock())

    async def scenario(db: Database) -> None:
        async with db.unit_of_work():
            await repo.upsert_chunk(chunk("runbook-red", 0, 0.1))
            await repo.upsert_chunk(chunk("runbook-red", 1, 0.5))
            await repo.upsert_chunk(chunk("organigrama", 0, 1.4))
            await repo.upsert_chunk(replace(chunk("runbook-red", 1, 0.3), content="revisado"))
        async with db.unit_of_work():
            found = await repo.search(unit_vector(0), k=5, min_sim=0.9)
            nothing = await repo.search(unit_vector(1.5), k=5, min_sim=0.999)
        assert [(c.source, c.chunk_ix, c.content) for c in found] == [
            ("runbook-red", 0, "contenido 0"),
            ("runbook-red", 1, "revisado"),
        ]
        assert found[0].similarity > found[1].similarity
        assert nothing == []  # nunca el más parecido por debajo del umbral

    pg.run(scenario)
    assert len(pg.fetch("SELECT id FROM carmen.knowledge_chunks")) == 3


def test_the_brief_is_a_single_row_that_round_trips_typed_values(pg: Pg) -> None:
    repo = PgBriefRepository()
    rich = replace(
        evidence_fact("disponibilidad", Decimal("99.950"), label="Disponibilidad"),
        entity=EntityRef("servicio", "svc-1", None),
        dimensions={"region": "norte", "turno": "noche"},
        period=PeriodInterpreted("today", at(-3600), at(0), "hoy"),
    )
    facts = (
        rich,
        evidence_fact("monitores_ko", 4),
        evidence_fact("estado", "degradado", label="Estado", unit=None),
        evidence_fact("alerta", False, label="Alerta", unit=None, system=PLENDATA_SYSTEM),
        evidence_fact("sin_dato", None, label="Sin dato", unit=None),
    )
    first = SituationBrief(at(0), facts[:1])
    second = SituationBrief(at(60), facts)

    async def scenario(db: Database) -> None:
        async with db.unit_of_work():
            assert await repo.get() is None
            await repo.put(first)
        async with db.unit_of_work():
            await repo.put(second)
        async with db.unit_of_work():
            loaded = await repo.get()
        assert loaded == second
        assert loaded is not None
        assert isinstance(loaded.facts[0].value, Decimal)
        assert str(loaded.facts[0].value) == "99.950"
        assert loaded.facts[1].value == 4
        assert type(loaded.facts[1].value) is int
        assert loaded.facts[3].value is False

    pg.run(scenario)
    assert len(pg.fetch("SELECT id FROM carmen.situation_brief")) == 1


def term(definition: str = "Monitor que no responde.", **kw: object) -> GlossaryTerm:
    base = GlossaryTerm("monitor caido", "Monitor caído", definition, aliases=("monitor ko",))
    return replace(base, **kw)  # type: ignore[arg-type]


def test_deactivating_a_term_keeps_it_and_leaves_history(pg: Pg) -> None:
    repo = PgGlossaryRepository()

    async def scenario(db: Database) -> None:
        async with db.unit_of_work():
            created = await repo.upsert(term(), PRINCIPAL, at(1))
            other = GlossaryTerm("ruta", "Ruta", "Trayecto asignado.", source=TermSource.ADMIN)
            await repo.upsert(other, PRINCIPAL, at(1))
        async with db.unit_of_work():
            updated = await repo.upsert(term("Monitor sin latido."), PRINCIPAL, at(2))
        async with db.unit_of_work():
            gone = await repo.deactivate("monitor caido", PRINCIPAL, at(3))
        assert created.action is GlossaryAction.CREATE
        assert created.before is None
        assert updated.action is GlossaryAction.UPDATE
        assert updated.before == term()
        assert gone.action is GlossaryAction.DEACTIVATE
        assert gone.after == term("Monitor sin latido.", active=False)
        async with db.unit_of_work():
            assert await repo.get("monitor caido") == term("Monitor sin latido.", active=False)
            assert [t.term for t in await repo.list_active()] == ["ruta"]
            history = await repo.history("monitor caido")
        assert history == (created, updated, gone)
        with pytest.raises(ValidationError, match="inactivo"):
            async with db.unit_of_work():
                await repo.deactivate("monitor caido", PRINCIPAL, at(4))
        with pytest.raises(ValidationError, match="no existe"):
            async with db.unit_of_work():
                await repo.deactivate("inexistente", PRINCIPAL, at(4))

    pg.run(scenario)
    assert len(pg.fetch("SELECT term FROM carmen.glossary_terms")) == 2
    rows = pg.fetch(
        "SELECT action, actor, created_by, updated_at FROM carmen.glossary_history h"
        " JOIN carmen.glossary_terms t USING (term) WHERE term = 'monitor caido' ORDER BY seq"
    )
    assert [r["action"] for r in rows] == ["create", "update", "deactivate"]
    assert rows[0]["updated_at"] == at(3).at


def topic(tid: str, asked: int, **kw: object) -> Topic:
    base = Topic(
        topic_id=TopicId(tid),
        label=f"tema {tid}",
        asked=asked,
        resolved=asked // 2,
        unresolved=asked - asked // 2,
        systems=frozenset({VIGIA_SYSTEM}),
        status=TopicStatus.OBSERVANDO,
        first_seen=at(0),
        last_seen=at(asked),
    )
    return replace(base, **kw)  # type: ignore[arg-type]


def test_topics_are_listed_by_demand_and_change_status(pg: Pg) -> None:
    repo = PgTopicRepository()
    both = frozenset({VIGIA_SYSTEM, SystemId("plendata")})

    async def scenario(db: Database) -> None:
        async with db.unit_of_work():
            await repo.upsert(topic("top_aaaa", 3))
            await repo.upsert(topic("top_bbbb", 9))
            await repo.upsert(topic("top_cccc", 5, systems=both))
            await repo.upsert(topic("top_aaaa", 12))
        async with db.unit_of_work():
            ranked = await repo.list_by_demand(2)
            changed = await repo.set_status(TopicId("top_cccc"), TopicStatus.PLANIFICADO, at(99))
        assert ranked == [topic("top_aaaa", 12), topic("top_bbbb", 9)]
        assert changed == topic("top_cccc", 5, systems=both, status=TopicStatus.PLANIFICADO)
        with pytest.raises(ValidationError, match="top_dddd"):
            async with db.unit_of_work():
                await repo.set_status(TopicId("top_dddd"), TopicStatus.CUBIERTO, at(99))

    pg.run(scenario)
    rows = pg.fetch("SELECT id, updated_at FROM carmen.topics WHERE id = 'top_cccc'")
    assert rows[0]["updated_at"] == at(99).at


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ('{"version": 2, "facts": []}', "versión de brief"),
        ('{"version": 1, "facts": {}}', "lista JSON"),
        ('{"version": 1, "facts": [3]}', "objeto JSON"),
    ],
)
def test_a_malformed_brief_is_a_validation_error(pg: Pg, payload: str, match: str) -> None:
    pg.fetch(
        "INSERT INTO carmen.situation_brief (id, payload, generated_at) VALUES (1, $1, now())",
        payload,
    )

    async def scenario(db: Database) -> None:
        with pytest.raises(ValidationError, match=match):
            async with db.unit_of_work():
                await PgBriefRepository().get()

    pg.run(scenario)


def test_a_badly_typed_fact_value_in_the_brief_is_refused(pg: Pg) -> None:
    good = fact_to_json(evidence_fact("monitores_ko", 4))
    assert isinstance(good, dict)
    pg.fetch(
        "INSERT INTO carmen.situation_brief (id, payload, generated_at) VALUES (1, $1, now())",
        dumps({"version": 1, "facts": [{**good, "value": {"type": "int", "value": "4"}}]}),
    )

    async def scenario(db: Database) -> None:
        with pytest.raises(ValidationError, match="mal codificado"):
            async with db.unit_of_work():
                await PgBriefRepository().get()

    pg.run(scenario)
