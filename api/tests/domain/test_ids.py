"""Prompt 2: identificadores tipados, sistemas, idioma, rol e instantes."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from carmen.domain.errors import ValidationError
from carmen.domain.ids import (
    AgentId,
    CallId,
    ClaimId,
    CorrelationId,
    FactId,
    MediaId,
    PassageId,
    PlanId,
    StepId,
)
from carmen.domain.locale import Locale
from carmen.domain.role import Role
from carmen.domain.system import SystemId
from carmen.domain.time import Instant

pytestmark = pytest.mark.domain


@pytest.mark.parametrize(
    ("factory", "valid"),
    [
        (AgentId, "agent.zoho-desk"),
        (SystemId, "plen-data_2"),
        (PlanId, "pln_a1b2c3d4e5f6"),
        (StepId, "s12"),
        (CallId, "cal_7f3a9c1e2b40"),
        (CorrelationId, "cor_18ab44de"),
        (FactId, "alarmas_total"),
        (PassageId, "psg:4.2"),
        (MediaId, "med-1"),
        (ClaimId, "c1"),
    ],
)
def test_valid_identifiers_are_strings(factory: type[str], valid: str) -> None:
    value = factory(valid)
    assert value == valid
    assert isinstance(value, str)
    assert type(value) is factory


@pytest.mark.parametrize(
    ("factory", "invalid"),
    [
        (AgentId, "vigia"),
        (AgentId, "agent.Vigia"),
        (AgentId, "agent.v"),
        (AgentId, "agent." + "a" * 33),
        (SystemId, "1vigia"),
        (PlanId, "pln_short"),
        (PlanId, "pln_A1B2C3D4E5F6"),
        (StepId, "s"),
        (StepId, "s100"),
        (StepId, "1"),
        (CallId, "call_1"),
        (CorrelationId, "cor_"),
        (FactId, ""),
        (FactId, "a" * 65),
        (FactId, "con espacio"),
    ],
)
def test_malformed_identifiers_are_rejected(factory: type[str], invalid: str) -> None:
    with pytest.raises(ValidationError):
        factory(invalid)


def test_identifier_rejects_non_strings() -> None:
    with pytest.raises(ValidationError):
        AgentId(7)  # type: ignore[arg-type]


def test_step_number_orders_numerically() -> None:
    steps = [StepId("s10"), StepId("s2"), StepId("s1")]
    assert [s.number for s in sorted(steps, key=lambda s: s.number)] == [1, 2, 10]


def test_locale_and_role_values() -> None:
    assert [loc.value for loc in Locale] == ["es", "en", "pt"]
    assert {r.value for r in Role} == {"ADMIN", "MANAGER", "OPERATOR", "AUDITOR"}


def test_instant_normalizes_to_utc() -> None:
    madrid = timezone(timedelta(hours=2))
    instant = Instant(datetime(2026, 7, 27, 11, 14, 22, tzinfo=madrid))
    assert instant.at.tzinfo is UTC
    assert instant.isoformat() == "2026-07-27T09:14:22Z"


def test_instant_rejects_naive_datetimes() -> None:
    with pytest.raises(ValidationError):
        Instant(datetime(2026, 7, 27, 9, 0))  # noqa: DTZ001 - el caso que se rechaza


def test_instant_parse_and_order() -> None:
    early = Instant.parse("2026-07-01T00:00:00Z")
    late = Instant.parse("2026-07-27T11:14:22+02:00")
    assert early < late
    assert late == Instant.parse("2026-07-27T09:14:22Z")


@pytest.mark.parametrize("text", ["ayer", "2026-07-27T09:14:22"])
def test_instant_parse_rejects_invalid_or_naive(text: str) -> None:
    with pytest.raises(ValidationError):
        Instant.parse(text)
