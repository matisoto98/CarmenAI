"""Prompt 2: evidencia como unión discriminada de hecho, pasaje y adjunto (6.3, 6.9.2)."""

from decimal import Decimal

import pytest

from carmen.domain.errors import ValidationError
from carmen.domain.evidence.models import (
    EntityRef,
    EvidenceFact,
    EvidenceItem,
    EvidenceMedia,
    EvidencePassage,
    EvidenceReference,
    FactValue,
    PeriodInterpreted,
    Provenance,
    Unit,
    require_numeric_fact,
)
from carmen.domain.ids import CallId, FactId, MediaId, PassageId
from carmen.domain.system import SystemId
from carmen.domain.time import Instant

pytestmark = pytest.mark.domain

CALL = CallId("cal_7f3a9c1e2b40")
VIGIA = SystemId("vigia")
PLENMIND = SystemId("plenmind")
NOW = Instant.parse("2026-07-27T09:14:22Z")
PROVENANCE = Provenance("build_dossier", "2026-07-20", NOW)


def fact(value: FactValue = 29, **extra: object) -> EvidenceFact:
    return EvidenceFact(
        fact_id=FactId("alarmas_total"),
        call_id=CALL,
        system_id=VIGIA,
        label="Alarmas del periodo",
        value=value,
        provenance=PROVENANCE,
        **extra,  # type: ignore[arg-type]
    )


def passage(**overrides: object) -> EvidencePassage:
    fields: dict[str, object] = {
        "passage_id": PassageId("psg_1"),
        "call_id": CALL,
        "system_id": PLENMIND,
        "document_id": "manual-alvic",
        "title": "Manual de surtidor Alvic · Averías",
        "text": "Compruebe la sonda de nivel antes de reiniciar.",
        "kind": "procedure",
        "relevance": 0.92,
        "section": "4.2 Sonda de nivel sin datos",
        "updated_at": NOW,
    }
    fields.update(overrides)
    return EvidencePassage(**fields)  # type: ignore[arg-type]


def media(**overrides: object) -> EvidenceMedia:
    fields: dict[str, object] = {
        "media_id": MediaId("med_1"),
        "call_id": CALL,
        "system_id": PLENMIND,
        "document_id": "manual-alvic",
        "mime": "image/png",
        "caption": "Esquema de conexión de la sonda",
        "uri": "https://plenmind.internal/docs/manual-alvic/fig-4.png",
        "bytes": 20480,
    }
    fields.update(overrides)
    return EvidenceMedia(**fields)  # type: ignore[arg-type]


def test_full_fact_from_the_envelope_example() -> None:
    period = PeriodInterpreted(
        "mes_actual",
        Instant.parse("2026-07-01T00:00:00Z"),
        NOW,
        "del 1 al 27 de julio de 2026",
    )
    built = fact(
        metric="alarmas",
        unit=Unit.COUNT,
        entity=EntityRef("site", "1", "Getafe"),
        dimensions={"tipo": "Enlace respaldo KO"},
        period=period,
    )
    assert built.evidence_type == "fact"
    assert built.numeric_value == Decimal(29)
    assert built.dimensions["tipo"] == "Enlace respaldo KO"
    with pytest.raises(TypeError):
        built.dimensions["tipo"] = "otro"  # type: ignore[index]


@pytest.mark.parametrize("value", [Decimal("10.7"), 0, -3])
def test_numeric_facts(value: FactValue) -> None:
    assert fact(value).is_numeric
    assert require_numeric_fact(fact(value)).value == value


@pytest.mark.parametrize("value", ["Getafe", True, None])
def test_non_numeric_facts(value: FactValue) -> None:
    built = fact(value)
    assert not built.is_numeric
    with pytest.raises(ValidationError):
        _ = built.numeric_value
    with pytest.raises(ValidationError):
        require_numeric_fact(built)


@pytest.mark.parametrize("value", [10.7, Decimal("NaN"), [1], {"a": 1}])
def test_invalid_fact_values(value: object) -> None:
    with pytest.raises(ValidationError):
        fact(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("extra", [{"label": " "}, {"metric": ""}])
def test_fact_requires_texts(extra: dict[str, str]) -> None:
    fields: dict[str, object] = {
        "fact_id": FactId("f"),
        "call_id": CALL,
        "system_id": VIGIA,
        "label": "Etiqueta",
        "value": 1,
        "provenance": PROVENANCE,
    }
    fields.update(extra)
    with pytest.raises(ValidationError):
        EvidenceFact(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "build",
    [
        lambda: EntityRef("", "1"),
        lambda: EntityRef("site", " "),
        lambda: PeriodInterpreted("", NOW, NOW, "hoy"),
        lambda: PeriodInterpreted("hoy", NOW, NOW, ""),
        lambda: PeriodInterpreted("hoy", NOW, Instant.parse("2026-07-01T00:00:00Z"), "x"),
        lambda: Provenance("", "2026-07-20", NOW),
        lambda: Provenance("tool", "", NOW),
    ],
)
def test_malformed_parts_of_a_fact(build: object) -> None:
    with pytest.raises(ValidationError):
        build()  # type: ignore[operator]


def test_passage_is_not_accepted_where_a_numeric_fact_is_required() -> None:
    items: tuple[EvidenceItem, ...] = (passage(), media())
    for item in items:
        with pytest.raises(ValidationError, match=item.evidence_type):
            require_numeric_fact(item)


def test_discriminators_are_distinct() -> None:
    assert {fact().evidence_type, passage().evidence_type, media().evidence_type} == {
        "fact",
        "passage",
        "media",
    }


def test_procedure_requires_updated_at() -> None:
    with pytest.raises(ValidationError, match="updated_at"):
        passage(updated_at=None)
    assert passage(kind="reference", updated_at=None).updated_at is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "opinion"},
        {"relevance": 1.5},
        {"relevance": -0.1},
        {"relevance": True},
        {"text": ""},
        {"title": " "},
        {"document_id": ""},
    ],
)
def test_malformed_passages(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        passage(**overrides)


def test_media_travels_as_reference() -> None:
    assert media().uri.startswith("https://")
    with pytest.raises(ValidationError, match="referencia"):
        media(uri="data:image/png;base64,iVBORw0KGgo=")
    with pytest.raises(ValidationError):
        media(uri=" DATA:image/png;base64,AAAA")


@pytest.mark.parametrize(
    "overrides",
    [
        {"mime": "png"},
        {"mime": "Image/PNG"},
        {"bytes": -1},
        {"bytes": True},
        {"caption": ""},
        {"uri": " "},
        {"document_id": ""},
    ],
)
def test_malformed_media(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        media(**overrides)


def test_evidence_reference_points_at_a_fact() -> None:
    built = fact()
    assert EvidenceReference.to(built) == EvidenceReference(CALL, FactId("alarmas_total"))
