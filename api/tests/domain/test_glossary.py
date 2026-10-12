"""Prompt 2: equivalencias y conflictos de métricas entre sistemas (invariante 4, 10.5.8)."""

import pytest

from carmen.domain.errors import MetricConflictError, ValidationError
from carmen.domain.glossary.models import (
    Glossary,
    MetricConflict,
    MetricEquivalence,
    MetricUse,
)
from carmen.domain.system import SystemId

pytestmark = pytest.mark.domain

VIGIA = SystemId("vigia")
PLENMIND = SystemId("plenmind")
PLENDATA = SystemId("plendata")


def use(system: SystemId, metric: str) -> MetricUse:
    return MetricUse(system, metric)


CONSULTAS = MetricEquivalence(
    "consultas",
    frozenset({use(VIGIA, "consultas"), use(PLENMIND, "queries")}),
    aggregable=True,
    definition="Consultas recibidas por el sistema",
)
INCIDENCIAS = MetricEquivalence(
    "incidencias",
    frozenset({use(VIGIA, "incidencias"), use(PLENDATA, "incidencias")}),
    aggregable=False,
    definition="Mismo concepto, distinta ventana de cómputo: se comparan, no se suman",
)
DISPONIBILIDAD = MetricConflict(
    "disponibilidad",
    frozenset({VIGIA, PLENMIND}),
    (
        (VIGIA, "Tiempo con servicio sobre indisponibilidad confirmada"),
        (PLENMIND, "Porcentaje de documentos accesibles"),
    ),
)
GLOSSARY = Glossary((CONSULTAS, INCIDENCIAS), (DISPONIBILIDAD,))


def test_homonym_without_equivalence_is_a_conflict() -> None:
    found = GLOSSARY.conflicts_in([use(VIGIA, "disponibilidad"), use(PLENMIND, "disponibilidad")])
    assert len(found) == 1
    assert found[0].metric == "disponibilidad"
    assert found[0].systems == {VIGIA, PLENMIND}
    assert found[0].definition_for(PLENMIND) == "Porcentaje de documentos accesibles"
    with pytest.raises(MetricConflictError, match="disponibilidad"):
        GLOSSARY.ensure_no_conflicts(
            [use(VIGIA, "disponibilidad"), use(PLENMIND, "disponibilidad")]
        )


def test_new_system_with_homonym_raises_conflict_without_declaring_it() -> None:
    found = GLOSSARY.conflicts_in([use(VIGIA, "alarmas"), use(PLENDATA, "alarmas")])
    assert [(c.metric, c.systems, c.definitions) for c in found] == [
        ("alarmas", frozenset({VIGIA, PLENDATA}), ())
    ]


def test_single_system_metric_never_conflicts() -> None:
    uses = [use(VIGIA, "disponibilidad"), use(VIGIA, "alarmas")]
    assert GLOSSARY.conflicts_in(uses) == ()
    GLOSSARY.ensure_no_conflicts(uses)


def test_declared_equivalence_removes_the_conflict() -> None:
    uses = [use(VIGIA, "incidencias"), use(PLENDATA, "incidencias")]
    assert GLOSSARY.conflicts_in(uses) == ()


def test_partial_equivalence_still_conflicts() -> None:
    uses = [use(VIGIA, "incidencias"), use(PLENDATA, "incidencias"), use(PLENMIND, "incidencias")]
    assert [c.systems for c in GLOSSARY.conflicts_in(uses)] == [
        frozenset({VIGIA, PLENDATA, PLENMIND})
    ]


def test_aggregation_only_with_aggregable_equivalence() -> None:
    assert GLOSSARY.can_aggregate([use(VIGIA, "consultas"), use(PLENMIND, "queries")])
    assert not GLOSSARY.can_aggregate([use(VIGIA, "incidencias"), use(PLENDATA, "incidencias")])
    assert not GLOSSARY.can_aggregate([use(VIGIA, "consultas"), use(PLENDATA, "incidencias")])
    assert not GLOSSARY.can_aggregate([use(VIGIA, "alarmas"), use(PLENDATA, "alarmas")])
    assert GLOSSARY.can_aggregate([use(VIGIA, "alarmas")])
    assert not GLOSSARY.can_aggregate([use(VIGIA, "alarmas"), use(VIGIA, "consultas")])


def test_equivalence_lookup() -> None:
    assert GLOSSARY.equivalence_of(use(PLENMIND, "queries")) is CONSULTAS
    assert GLOSSARY.equivalence_of(use(PLENMIND, "consultas")) is None


@pytest.mark.parametrize(
    "build",
    [
        lambda: MetricUse(VIGIA, " "),
        lambda: MetricEquivalence("", frozenset({use(VIGIA, "a"), use(PLENMIND, "a")}), True, "d"),
        lambda: MetricEquivalence("x", frozenset({use(VIGIA, "a"), use(PLENMIND, "a")}), True, ""),
        lambda: MetricEquivalence("x", frozenset({use(VIGIA, "a")}), True, "d"),
        lambda: MetricEquivalence("x", frozenset({use(VIGIA, "a"), use(VIGIA, "b")}), True, "d"),
        lambda: MetricConflict("", frozenset({VIGIA, PLENMIND})),
        lambda: MetricConflict("m", frozenset({VIGIA})),
        lambda: MetricConflict("m", frozenset({VIGIA, PLENMIND}), ((PLENDATA, "ajena"),)),
    ],
)
def test_malformed_declarations(build: object) -> None:
    with pytest.raises(ValidationError):
        build()  # type: ignore[operator]


def test_metric_cannot_be_in_two_equivalences() -> None:
    other = MetricEquivalence(
        "otra", frozenset({use(VIGIA, "consultas"), use(PLENDATA, "peticiones")}), True, "d"
    )
    with pytest.raises(ValidationError, match="dos equivalencias"):
        Glossary((CONSULTAS, other))


def test_metric_cannot_be_equivalent_and_conflicting() -> None:
    clash = MetricConflict("consultas", frozenset({VIGIA, PLENDATA}))
    with pytest.raises(ValidationError, match="equivalente"):
        Glossary((CONSULTAS,), (clash,))
