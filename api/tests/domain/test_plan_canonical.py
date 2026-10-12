"""Prompt 2: lectura estricta y forma normal canónica del plan (6.2.2)."""

import itertools
import json
from decimal import Decimal

import pytest

from carmen.domain.errors import InvalidPlanError
from carmen.domain.ids import StepId
from carmen.domain.plan.canonical import (
    canonical_json,
    plan_from_dict,
    plan_from_json,
    to_canonical_dict,
)
from carmen.domain.plan.models import FactReference, Intent

pytestmark = pytest.mark.domain

ANALYTIC = """
{ "schema_version":"1.0", "plan_id":"pln_b2c3d4e5f6a7",
  "intent":"analytic", "systems":["vigia"], "round":1,
  "catalog_versions":{"vigia":"2026-07-20"},
  "limits":{"max_rounds":3,"max_tool_calls":6,"max_repairs":2},
  "steps":[
    { "step_id":"s1", "agent":"vigia", "system":"vigia", "tool":"site_resolver",
      "arguments":{"texto":"Getafe"} },
    { "step_id":"s2", "agent":"vigia", "system":"vigia", "tool":"build_dossier",
      "depends_on":[{"step_id":"s1"}],
      "arguments":{ "entity":"site",
        "id":{"$ref_step":"s1","$ref_fact":"site_id","$ref_field":"value"},
        "period":"mes_actual", "compare_to":"periodo_anterior" } },
    { "step_id":"s3", "agent":"vigia", "system":"vigia", "tool":"correlate_events",
      "depends_on":[{"step_id":"s1"}], "optional": true,
      "arguments":{ "site_id":{"$ref_step":"s1","$ref_fact":"site_id"}, "window":"30d" } } ] }
"""

MULTIAGENT = """
{ "schema_version":"1.0", "plan_id":"pln_d4e5f6a7b8c9",
  "intent":"analytic", "agents":["vigia","plendata"], "round":2,
  "catalog_versions":{"vigia":"2026-07-20","plendata":"2026-07-25"},
  "limits":{"max_rounds":2,"max_tool_calls":4,"max_repairs":2},
  "steps":[
    { "step_id":"s1", "agent":"vigia", "system":"vigia", "tool":"top_n",
      "arguments":{"metric":"alarmas","group_by":"estacion","period":"mes_actual","limit":10,
                   "umbral":10.70, "estados":["ko","degradado"]} },
    { "step_id":"s2", "agent":"plendata", "system":"plendata", "tool":"query_metric",
      "depends_on":[{"step_id":"s1","hard":false}],
      "arguments":{"metric":"margen","group_by":"estacion","period":"mes_actual",
                   "label":{"$ref_step":"s1","$ref_fact":"top","$ref_field":"label"}} } ],
  "join":{ "entity":"estacion", "canonical_id":"codigo_estacion",
           "steps":["s2","s1"], "on_missing":"hueco_explicito" } }
"""


def _shuffle(value: object, depth: int = 0) -> object:
    """Reescribe un documento JSON con las claves de cada objeto en orden inverso."""
    if isinstance(value, dict):
        return {k: _shuffle(value[k], depth + 1) for k in reversed(list(value))}
    if isinstance(value, list):
        return [_shuffle(item, depth + 1) for item in value]
    return value


def test_reads_the_analytic_example() -> None:
    plan = plan_from_json(ANALYTIC)
    assert plan.intent is Intent.ANALYTIC
    assert plan.step(StepId("s2")).arguments["id"] == FactReference(StepId("s1"), "site_id")
    assert plan.step(StepId("s3")).optional
    assert plan.execution_waves()[1] == (StepId("s2"), StepId("s3"))


def test_decimals_are_read_as_decimal_never_float() -> None:
    plan = plan_from_json(MULTIAGENT)
    assert plan.step(StepId("s1")).arguments["umbral"] == Decimal("10.70")
    assert plan.step(StepId("s1")).arguments["estados"] == ("ko", "degradado")


def test_canonical_form_ignores_key_order() -> None:
    for text in (ANALYTIC, MULTIAGENT):
        original = json.loads(text)
        shuffled = _shuffle(original)
        assert json.dumps(shuffled) != json.dumps(original)
        assert canonical_json(plan_from_dict(shuffled)) == canonical_json(plan_from_dict(original))  # type: ignore[arg-type]


def test_canonical_form_ignores_step_and_dependency_order() -> None:
    base = json.loads(ANALYTIC)
    base["steps"][1]["depends_on"] = [{"step_id": "s1"}]
    forms = set()
    for order in itertools.permutations(base["steps"]):
        variant = {**base, "steps": list(order)}
        forms.add(canonical_json(plan_from_dict(variant)))
    assert len(forms) == 1


def test_canonical_form_omits_defaults() -> None:
    canonical = to_canonical_dict(plan_from_json(ANALYTIC))
    assert "round" not in canonical
    assert "agents" not in canonical
    assert "join" not in canonical
    s1, s2, s3 = canonical["steps"]  # type: ignore[misc]
    assert "depends_on" not in s1
    assert "optional" not in s2
    assert s3["optional"] is True
    assert s2["arguments"]["id"] == {"$ref_step": "s1", "$ref_fact": "site_id"}
    assert s2["depends_on"] == [{"step_id": "s1"}]


def test_canonical_form_keeps_non_defaults() -> None:
    canonical = to_canonical_dict(plan_from_json(MULTIAGENT))
    assert canonical["round"] == 2
    assert canonical["agents"] == ["plendata", "vigia"]
    assert canonical["systems"] == ["plendata", "vigia"]
    assert canonical["join"] == {
        "entity": "estacion",
        "canonical_id": "codigo_estacion",
        "steps": ["s1", "s2"],
    }
    s2 = canonical["steps"][1]  # type: ignore[index]
    assert s2["depends_on"] == [{"step_id": "s1", "hard": False}]
    assert s2["arguments"]["label"]["$ref_field"] == "label"


def test_canonical_json_is_compact_sorted_and_stable() -> None:
    text = canonical_json(plan_from_json(MULTIAGENT))
    assert " " not in text.replace("hueco explicito", "")
    assert '"umbral":10.7' in text
    assert text.index('"agents"') < text.index('"catalog_versions"') < text.index('"intent"')
    assert canonical_json(plan_from_json(text)) == text


def test_equivalent_numbers_serialize_identically() -> None:
    first = json.loads(MULTIAGENT)
    second = json.loads(MULTIAGENT)
    second["steps"][0]["arguments"]["umbral"] = 10.7
    first["steps"][0]["arguments"]["limit"] = 10
    second["steps"][0]["arguments"]["limit"] = Decimal("1E+1")
    assert canonical_json(plan_from_dict(first)) == canonical_json(plan_from_dict(second))


def test_zero_and_negative_zero_serialize_identically() -> None:
    doc = json.loads(MULTIAGENT)
    doc["steps"][0]["arguments"]["umbral"] = Decimal("-0.00")
    assert '"umbral":0' in canonical_json(plan_from_dict(doc))


def test_round_trip_through_canonical_form() -> None:
    for text in (ANALYTIC, MULTIAGENT):
        plan = plan_from_json(text)
        assert plan_from_dict(to_canonical_dict(plan)) == plan  # type: ignore[arg-type]


def test_systems_may_be_omitted_and_are_derived() -> None:
    doc = json.loads(MULTIAGENT)
    assert "systems" not in doc
    assert to_canonical_dict(plan_from_dict(doc))["systems"] == ["plendata", "vigia"]


def _codes(doc: object) -> frozenset[str]:
    with pytest.raises(InvalidPlanError) as caught:
        plan_from_dict(doc)  # type: ignore[arg-type]
    return caught.value.codes


def test_declared_systems_must_match_steps() -> None:
    doc = json.loads(ANALYTIC)
    doc["systems"] = ["vigia", "plenmind"]
    assert _codes(doc) == {"systems_mismatch"}
    doc["systems"] = ["vigia", "vigia"]
    assert _codes(doc) == {"invalid_value"}
    doc["systems"] = ["Vigia"]
    assert _codes(doc) == {"invalid_value"}
    doc["systems"] = "vigia"
    assert _codes(doc) == {"invalid_type"}


def test_unknown_and_missing_fields_are_all_reported() -> None:
    doc = json.loads(ANALYTIC)
    doc["extra"] = 1
    del doc["limits"]
    with pytest.raises(InvalidPlanError) as caught:
        plan_from_dict(doc)
    assert caught.value.codes == {"unknown_field", "missing_field"}
    assert any("extra" in i.detail for i in caught.value.issues)


def test_root_must_be_an_object() -> None:
    assert _codes(["no"]) == {"invalid_type"}
    with pytest.raises(InvalidPlanError) as caught:
        plan_from_json("[1, 2]")
    assert caught.value.codes == {"invalid_type"}
    with pytest.raises(InvalidPlanError) as caught:
        plan_from_json("{no es json")
    assert caught.value.codes == {"invalid_json"}


def test_malformed_values_everywhere_are_reported_together() -> None:
    doc = json.loads(MULTIAGENT)
    doc["schema_version"] = 1
    doc["plan_id"] = "pln_corto"
    doc["intent"] = "adivinar"
    doc["agents"] = ["Vigia"]
    doc["round"] = "1"
    doc["catalog_versions"] = {"vigia": 20260720, "Plendata": "x"}
    doc["limits"]["max_rounds"] = "3"
    doc["join"]["on_missing"] = "descartar"
    step = doc["steps"][0]
    step["step_id"] = 1
    step["tool"] = 7
    step["optional"] = "si"
    step["depends_on"] = "s0"
    step["arguments"]["raro"] = None
    step["arguments"]["lista"] = [1, None]
    second = doc["steps"][1]
    second["depends_on"] = [{"step_id": "s1", "hard": "no"}, "s1", {"paso": "s1"}]
    second["arguments"]["label"] = {"$ref_step": "s1", "$ref_fact": 5}
    with pytest.raises(InvalidPlanError) as caught:
        plan_from_dict(doc)
    assert caught.value.codes == {"invalid_type", "invalid_value", "unknown_field", "missing_field"}
    assert len(caught.value.issues) >= 18


ARG = ("steps", 0, "arguments", "texto")


@pytest.mark.parametrize(
    ("path", "value", "code"),
    [
        (ARG, "x" * 201, "invalid_value"),
        (ARG, float("nan"), "invalid_value"),
        (ARG, {"$ref_step": "s9", "$ref_fact": "f"}, "unknown_step_reference"),
        (ARG, {"$ref_step": "s1", "$ref_fact": ""}, "invalid_value"),
        (ARG, {"$ref_step": "z", "$ref_fact": "f"}, "invalid_value"),
        (
            ("steps", 0, "arguments", "texto"),
            {"$ref_step": "s1", "$ref_fact": "f", "$ref_field": "otro"},
            "invalid_value",
        ),
        (ARG, {"texto": "libre"}, "unknown_field"),
        (ARG, {1: "clave no textual"}, "invalid_type"),
        (("steps", 0, "arguments"), [], "invalid_type"),
        (("steps", 0, "tool"), "Exec-SQL", "invalid_value"),
        (("steps", 0), "s1", "invalid_type"),
        (("steps",), {}, "invalid_type"),
        (("limits",), {"max_rounds": 9, "max_tool_calls": 1, "max_repairs": 0}, "invalid_value"),
        (("limits",), [], "invalid_type"),
        (("catalog_versions",), [], "invalid_type"),
        (("join",), {"entity": 1, "canonical_id": "c", "steps": ["s1", "s2"]}, "invalid_type"),
        (("join",), {"entity": "", "canonical_id": "c", "steps": ["s1", "s2"]}, "invalid_value"),
        (("join",), {"entity": "e", "canonical_id": "c", "steps": ["s1", "x"]}, "invalid_value"),
        (("join",), {"entity": "e", "canonical_id": "c", "steps": "s1"}, "invalid_type"),
        (("join",), {"entity": "e", "canonical_id": "c"}, "missing_field"),
    ],
)
def test_single_malformed_value(path: tuple[str | int, ...], value: object, code: str) -> None:
    doc = json.loads(MULTIAGENT)
    target = doc
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert code in _codes(doc)


def test_structural_rules_still_apply_after_reading() -> None:
    doc = json.loads(ANALYTIC)
    doc["steps"][0]["depends_on"] = [{"step_id": "s2"}]
    assert _codes(doc) == {"dependency_cycle"}
