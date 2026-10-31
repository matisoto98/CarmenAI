"""Prompt 2: afirmaciones y resultado del anclaje, coherentes por construcción (6.3)."""

from decimal import Decimal

import pytest

from carmen.domain.errors import ValidationError
from carmen.domain.evidence.grounding import GroundingClaim, GroundingResult, TextSpan
from carmen.domain.evidence.models import EvidenceReference
from carmen.domain.ids import CallId, ClaimId, FactId

pytestmark = pytest.mark.domain

REF = EvidenceReference(CallId("cal_1"), FactId("alarmas_total"))


def supported(claim: str = "c1") -> GroundingClaim:
    return GroundingClaim(ClaimId(claim), TextSpan(10, 12), "29", Decimal(29), REF, "supported")


def unsupported(claim: str = "c2") -> GroundingClaim:
    return GroundingClaim(
        ClaimId(claim), TextSpan(20, 24), "10,7", Decimal("10.7"), None, "unsupported", "sin hecho"
    )


def whitelisted(claim: str = "c3") -> GroundingClaim:
    return GroundingClaim(ClaimId(claim), TextSpan(0, 4), "2026", None, None, "whitelisted", "año")


@pytest.mark.parametrize(("start", "end"), [(-1, 2), (3, 3), (5, 2)])
def test_invalid_spans(start: int, end: int) -> None:
    with pytest.raises(ValidationError):
        TextSpan(start, end)


def test_span_length() -> None:
    assert TextSpan(3, 7).length == 4


def test_valid_claims() -> None:
    assert supported().supported_by == REF
    assert unsupported().reason == "sin hecho"
    assert whitelisted().normalized is None


@pytest.mark.parametrize(
    "build",
    [
        lambda: GroundingClaim(ClaimId("c"), TextSpan(0, 3), "29", Decimal(29), REF, "supported"),
        lambda: GroundingClaim(ClaimId("c"), TextSpan(0, 2), "29", Decimal(29), None, "supported"),
        lambda: GroundingClaim(ClaimId("c"), TextSpan(0, 2), "29", None, REF, "supported"),
        lambda: GroundingClaim(ClaimId("c"), TextSpan(0, 2), "29", None, REF, "unsupported", "x"),
        lambda: GroundingClaim(ClaimId("c"), TextSpan(0, 2), "29", None, None, "unsupported"),
        lambda: GroundingClaim(ClaimId("c"), TextSpan(0, 2), "29", None, None, "whitelisted", ""),
        lambda: GroundingClaim(ClaimId("c"), TextSpan(0, 2), "29", None, None, "dudoso", "x"),
    ],
)
def test_incoherent_claims_cannot_be_built(build: object) -> None:
    with pytest.raises(ValidationError):
        build()  # type: ignore[operator]


def test_result_derived_from_claims() -> None:
    ok = GroundingResult.of((supported(), whitelisted()))
    assert ok.ok
    assert ok.checked == 2
    assert ok.unsupported == ()
    failed = GroundingResult.of((supported(), unsupported()))
    assert not failed.ok
    assert failed.unsupported == (ClaimId("c2"),)
    assert GroundingResult.of(()).ok


@pytest.mark.parametrize(
    ("ok", "checked", "claims", "missing"),
    [
        (True, 2, (supported(), unsupported()), (ClaimId("c2"),)),
        (False, 1, (supported(),), ()),
        (True, 3, (supported(), whitelisted()), ()),
        (False, 2, (supported(), unsupported()), ()),
        (False, 2, (unsupported("c1"), unsupported("c1")), (ClaimId("c1"), ClaimId("c1"))),
    ],
)
def test_incoherent_results_cannot_be_built(
    ok: bool,
    checked: int,
    claims: tuple[GroundingClaim, ...],
    missing: tuple[ClaimId, ...],
) -> None:
    with pytest.raises(ValidationError):
        GroundingResult(ok, checked, claims, missing)
