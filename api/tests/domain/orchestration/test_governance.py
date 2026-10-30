"""Prompt 3: aprobación humana, exportación y ModelOutput separado de la evidencia."""

from dataclasses import replace
from decimal import Decimal

import pytest

from carmen.domain.approval.models import (
    ApprovalRecord,
    ApprovalStatus,
    HumanApprovalRequest,
    Impact,
)
from carmen.domain.egress.models import DataClass, DataExportDecision, Destination, Purpose
from carmen.domain.errors import ValidationError
from carmen.domain.evidence.models import (
    EvidenceFact,
    EvidenceMedia,
    EvidencePassage,
    EvidenceReference,
    require_numeric_fact,
)
from carmen.domain.ids import AgentId, ApprovalId, CallId, FactId, PrincipalId, ProviderId, TurnId
from carmen.domain.model_output import ModelOutput
from carmen.domain.policy.models import Effect
from carmen.domain.role import Role
from carmen.domain.time import Instant

pytestmark = pytest.mark.domain

NOW = Instant.parse("2026-07-28T10:00:00Z")
LATER = Instant.parse("2026-07-28T11:00:00Z")
REQUEST = ApprovalId("apr_0001")
OLLAMA = ProviderId("provider.internal-ollama")


def model_output(**overrides: object) -> ModelOutput:
    fields: dict[str, object] = {
        "provider": OLLAMA,
        "model": "qwen3",
        "model_version": "2026-07",
        "purpose": Purpose.NARRATION,
        "text": "Hay 29 alarmas en Getafe.",
        "tokens_in": 120,
        "tokens_out": 30,
        "cost_eur": Decimal(0),
        "produced_at": NOW,
    }
    fields.update(overrides)
    return ModelOutput(**fields)  # type: ignore[arg-type]


def test_approval_request() -> None:
    request = HumanApprovalRequest(
        request_id=REQUEST,
        turn_id=TurnId("trn_18ab44de"),
        agent_id=AgentId("agent.plenlegal"),
        action="export_contract",
        impact=Impact.CRITICAL,
        summary="Enviar el contrato al proveedor externo",
        evidence_refs=(EvidenceReference(CallId("cal_1"), FactId("contrato")),),
        required_role=Role.MANAGER,
        expires_at=LATER,
    )
    assert request.impact == "critical"
    with pytest.raises(ValidationError):
        replace(request, summary="")
    with pytest.raises(ValidationError):
        replace(request, action=" ")


def test_approval_records_follow_ck_decided() -> None:
    approved = ApprovalRecord(REQUEST, ApprovalStatus.APPROVED, (), PrincipalId("usr_b0ss"), NOW)
    assert approved.approved
    assert not ApprovalRecord(REQUEST, ApprovalStatus.PENDING).approved
    assert ApprovalRecord(REQUEST, ApprovalStatus.EXPIRED).status == "expired"


@pytest.mark.parametrize(
    ("status", "by", "at"),
    [
        (ApprovalStatus.APPROVED, None, None),
        (ApprovalStatus.REJECTED, PrincipalId("usr_b0ss"), None),
        (ApprovalStatus.PENDING, PrincipalId("usr_b0ss"), NOW),
        (ApprovalStatus.PENDING, None, NOW),
    ],
)
def test_incoherent_approval_records(
    status: ApprovalStatus, by: PrincipalId | None, at: Instant | None
) -> None:
    with pytest.raises(ValidationError):
        ApprovalRecord(REQUEST, status, (), by, at)


def test_data_classes_are_ordered() -> None:
    assert DataClass.PUBLICO.fits_within(DataClass.CONFIDENCIAL)
    assert DataClass.INTERNO.fits_within(DataClass.INTERNO)
    assert not DataClass.CONFIDENCIAL.fits_within(DataClass.PUBLICO)


def export(**overrides: object) -> DataExportDecision:
    fields: dict[str, object] = {
        "decision": Effect.DENY,
        "classification": DataClass.CONFIDENCIAL,
        "destination": Destination(ProviderId("provider.external-a"), "modelo-x", "eu"),
        "purpose": Purpose.ANALYSIS,
        "policy_id": "egress.legal-sources",
        "redactions": ("nombres_de_empleado",),
        "reason": "El contrato no puede salir del perímetro",
        "decided_at": NOW,
    }
    fields.update(overrides)
    return DataExportDecision(**fields)  # type: ignore[arg-type]


def test_export_decision_requires_a_reason_even_when_allowed() -> None:
    assert not export().allowed
    assert export(decision=Effect.ALLOW, classification=DataClass.PUBLICO).allowed
    with pytest.raises(ValidationError):
        export(decision=Effect.ALLOW, reason="")


@pytest.mark.parametrize(
    "overrides",
    [
        {"policy_id": ""},
        {"redactions": ("",)},
    ],
)
def test_malformed_export_decisions(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        export(**overrides)


@pytest.mark.parametrize(
    "build",
    [
        lambda: Destination(OLLAMA, "", "eu"),
        lambda: Destination(OLLAMA, "qwen3", " "),
    ],
)
def test_malformed_destinations(build: object) -> None:
    with pytest.raises(ValidationError):
        build()  # type: ignore[operator]


def test_model_output_is_not_evidence() -> None:
    output = model_output()
    assert not isinstance(output, EvidenceFact | EvidencePassage | EvidenceMedia)
    assert not hasattr(output, "evidence_type")
    with pytest.raises(ValidationError, match="ModelOutput"):
        require_numeric_fact(output)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"model": ""},
        {"model_version": " "},
        {"tokens_in": -1},
        {"tokens_out": True},
        {"cost_eur": Decimal(-1)},
        {"cost_eur": Decimal("NaN")},
    ],
)
def test_malformed_model_outputs(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        model_output(**overrides)
