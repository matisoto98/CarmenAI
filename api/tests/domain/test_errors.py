"""Prompt 2: taxonomía de errores completa, sin solapes y sin códigos HTTP (6.6)."""

import inspect

import pytest

from carmen.domain import errors
from carmen.domain.errors import (
    CarmenError,
    InternalError,
    InvalidPlanError,
    LlmError,
    McpError,
    PlanIssue,
    ValidationError,
)

pytestmark = pytest.mark.domain

SPEC_CODES = {
    "validation_error",
    "unknown_system",
    "unknown_tool",
    "invalid_arguments",
    "metric_conflict",
    "no_coverage",
    "no_data",
    "entity_not_resolved",
    "forbidden",
    "mcp_timeout",
    "mcp_unavailable",
    "mcp_contract_violation",
    "llm_unavailable",
    "llm_timeout",
    "grounding_failed",
    "cancelled",
    "internal",
}


def _error_classes() -> list[type[CarmenError]]:
    return [
        obj
        for _, obj in inspect.getmembers(errors, inspect.isclass)
        if issubclass(obj, CarmenError)
    ]


def test_every_error_descends_from_carmen_error() -> None:
    classes = _error_classes()
    assert len(classes) > len(SPEC_CODES)
    assert all(issubclass(cls, CarmenError) for cls in classes)


def test_codes_are_unique() -> None:
    codes = [cls.code for cls in _error_classes()]
    assert len(codes) == len(set(codes))


def test_taxonomy_covers_every_code_of_section_6_6() -> None:
    concrete = {cls.code for cls in _error_classes() if not cls.abstract}
    assert concrete >= SPEC_CODES
    assert concrete - SPEC_CODES == {"invalid_plan"}


def test_groups_are_abstract_and_have_concrete_children() -> None:
    for group in (CarmenError, McpError, LlmError):
        assert group.abstract
        assert any(
            issubclass(cls, group) and cls is not group and not cls.abstract
            for cls in _error_classes()
        )


def test_no_overlap_between_branches() -> None:
    """Cada error concreto pertenece a una sola rama bajo CarmenError."""
    roots = [cls for cls in _error_classes() if cls.__bases__ == (CarmenError,)]
    for cls in _error_classes():
        if cls is CarmenError:
            continue
        assert sum(issubclass(cls, root) for root in roots) == 1, cls.__name__


def test_errors_do_not_know_http() -> None:
    for cls in _error_classes():
        own = {name.lower() for name in vars(cls)}
        assert not any("http" in name or "status" in name for name in own), cls.__name__


def test_message_defaults_to_code() -> None:
    assert ValidationError().message == "validation_error"
    assert str(ValidationError("detalle")) == "detalle"


def test_internal_error_keeps_correlation() -> None:
    error = InternalError("fallo", correlation_id="cor_abc")
    assert error.correlation_id == "cor_abc"
    assert error.code == "internal"


def test_invalid_plan_error_gathers_every_issue() -> None:
    issues = (PlanIssue("too_many_steps", "13"), PlanIssue("dependency_cycle", "s1"))
    error = InvalidPlanError(issues)
    assert isinstance(error, ValidationError)
    assert error.codes == {"too_many_steps", "dependency_cycle"}
    assert "too_many_steps: 13" in error.message
