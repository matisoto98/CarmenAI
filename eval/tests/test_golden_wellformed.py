"""Prompt 6: el golden set, los modos etiquetados y los planes esperados están bien formados (10.4).

Estas pruebas no ejecutan a Carmen: comprueban que el criterio de «terminado» es coherente consigo
mismo y con los contratos antes de escribir el orquestador. Un caso que nombra una herramienta que
no está en el catálogo, un argumento que el catálogo rechaza o un plan que no está en forma normal
canónica hacen fallar la prueba.
"""

import json
import re
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Final, cast

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012, Schema

from carmen.domain.delegation.models import (
    AgentTask,
    Budgets,
    Composition,
    CompositionKind,
    DelegationPlan,
    Expects,
    TaskBudgets,
)
from carmen.domain.ids import (
    AgentId,
    DelegatedIdentityRef,
    DelegationPlanId,
    PrincipalId,
    TaskId,
    TurnId,
)
from carmen.domain.locale import Locale
from carmen.domain.orchestration.mode import ResponseMode
from carmen.domain.plan.canonical import canonical_json, plan_from_dict
from carmen.domain.plan.models import FactReference, QueryPlan
from carmen.domain.role import Role

pytestmark = pytest.mark.golden

ROOT: Final = Path(__file__).resolve().parents[2]
EVAL: Final = ROOT / "eval"
CONTRACTS: Final = ROOT / "contracts"
GOLDEN_SET: Final = EVAL / "golden" / "carmen_golden_set.yaml"
MODES: Final = EVAL / "golden" / "modes_labeled.yaml"
EXPECTED_PLANS: Final = EVAL / "fixtures" / "expected_plans"

Json = dict[str, object]


def _yaml(path: Path) -> Json:
    return cast("Json", yaml.safe_load(path.read_text(encoding="utf-8")))


def _json(path: Path) -> Json:
    return cast("Json", json.loads(path.read_text(encoding="utf-8")))


@cache
def _registry() -> Registry[Schema]:
    schemas = [*CONTRACTS.rglob("*.schema.json"), *(EVAL / "schemas").glob("*.schema.json")]
    resources = [
        (str(s["$id"]), Resource.from_contents(s, default_specification=DRAFT202012))
        for s in map(_json, schemas)
    ]
    return Registry[Schema]().with_resources(resources)


def _validator(schema: Path) -> Draft202012Validator:
    return Draft202012Validator(_json(schema), registry=_registry())


def _errors(schema: Path, doc: object) -> list[str]:
    return [
        f"{'/'.join(map(str, e.absolute_path)) or '/'}: {e.message}"
        for e in _validator(schema).iter_errors(doc)
    ]


CASE_SCHEMA: Final = EVAL / "schemas" / "golden-case.schema.json"
MODES_SCHEMA: Final = EVAL / "schemas" / "modes-labeled.schema.json"
CATALOG_SCHEMA: Final = EVAL / "schemas" / "catalog.schema.json"


def _golden_files() -> list[Path]:
    return [GOLDEN_SET, *sorted((EVAL / "golden").glob("*/*.yaml"))]


@dataclass(frozen=True)
class Case:
    file: str
    data: Mapping[str, object]

    @property
    def id(self) -> str:
        return str(self.data["id"])

    def get(self, key: str) -> object:
        return self.data.get(key)

    @property
    def plan(self) -> Mapping[str, object]:
        return cast("Mapping[str, object]", self.data.get("plan_esperado") or {})

    @property
    def depends(self) -> list[str]:
        return cast("list[str]", self.data.get("depende_de", []))


def _cases(path: Path) -> list[Case]:
    return [Case(path.name, c) for c in cast("list[Json]", _yaml(path)["casos"])]


def _all_cases() -> list[Case]:
    return [case for path in _golden_files() for case in _cases(path)]


def _mode_cases() -> list[Json]:
    return cast("list[Json]", _yaml(MODES)["casos"])


@cache
def _catalogs() -> dict[str, Json]:
    catalogs = {}
    for path in sorted((EVAL / "fixtures").glob("catalog_*.json")):
        catalog = _json(path)
        catalogs[str(catalog["system_id"])] = catalog
    return catalogs


def _tool(system: str, name: str) -> Json | None:
    tools = cast("list[Json]", _catalogs()[system]["tools"])
    return next((t for t in tools if t["name"] == name), None)


def _tools_of(systems: Sequence[str]) -> dict[str, tuple[str, Json]]:
    """Herramienta → (sistema, descriptor) para los sistemas de un plan."""
    found: dict[str, tuple[str, Json]] = {}
    for system in systems:
        for tool in cast("list[Json]", _catalogs()[system]["tools"]):
            found.setdefault(str(tool["name"]), (system, tool))
    return found


def _expected_plan_files() -> list[Path]:
    return sorted(EXPECTED_PLANS.glob("*.json"))


# --- 1. Esquemas ---------------------------------------------------------------------------


@pytest.mark.parametrize("schema", sorted((EVAL / "schemas").glob("*.schema.json")), ids=str)
def test_eval_schema_is_valid_2020_12(schema: Path) -> None:
    document = _json(schema)
    Draft202012Validator.check_schema(document)
    assert document["$id"] == f"https://plenergy.internal/carmen/eval/{schema.name}"


@pytest.mark.parametrize("path", _golden_files(), ids=lambda p: p.name)
def test_golden_file_validates_against_case_schema(path: Path) -> None:
    assert _errors(CASE_SCHEMA, _yaml(path)) == []


def test_modes_file_validates_against_its_schema() -> None:
    assert _errors(MODES_SCHEMA, _yaml(MODES)) == []


@pytest.mark.parametrize("path", sorted((EVAL / "fixtures").glob("catalog_*.json")), ids=str)
def test_catalog_validates_against_its_schema(path: Path) -> None:
    assert _errors(CATALOG_SCHEMA, _json(path)) == []


def test_schemas_reject_what_they_must() -> None:
    """Un caso sin rúbrica, un REFUSE sin motivo o un SUPERVISOR_DIRECT con plan no valen."""
    case = cast("Json", _cases(GOLDEN_SET)[0].data)
    broken = [
        {k: v for k, v in case.items() if k != "rubrica"},
        {**case, "modo_esperado": "REFUSE"},
        {**case, "modo_esperado": "SUPERVISOR_DIRECT"},
        {**case, "k_de_n": [4, 3]},
        {**case, "propiedades": {"inventada": True}},
        {**case, "locale": "fr"},
    ]
    for doc in broken:
        assert _errors(CASE_SCHEMA, {"schema_version": "1.0", "casos": [doc]}), doc


# --- 2. Composición del golden set (10.4, Prompt 6) ----------------------------------------


REQUIRED_MIX: Final = {
    "factual": 8,
    "tendencia": 3,
    "analitica": 3,
    "negativa": 4,
    "conflicto": 2,
}


def test_initial_set_has_twenty_cases_with_the_required_mix() -> None:
    cases = _cases(GOLDEN_SET)
    assert len(cases) == 20
    assert Counter(str(c.get("categoria")) for c in cases) == REQUIRED_MIX


def test_initial_set_has_at_least_five_in_english_and_five_in_portuguese() -> None:
    locales = Counter(str(c.get("locale")) for c in _cases(GOLDEN_SET))
    assert locales[Locale.EN] >= 5
    assert locales[Locale.PT] >= 5


def test_ids_are_unique_and_match_the_category() -> None:
    prefixes = {
        "factual": "F",
        "tendencia": "T",
        "analitica": "A",
        "negativa": "N",
        "conflicto": "C",
        "catalogo": "VC",
    }
    cases = _all_cases()
    assert len({c.id for c in cases}) == len(cases)
    for case in cases:
        prefix = prefixes[str(case.get("categoria"))]
        assert re.fullmatch(rf"{prefix}[0-9]{{2}}", case.id), case.id


_INCIDENTS: Final = re.compile(r"incid", re.IGNORECASE)


def test_incident_questions_depend_on_prompt_12() -> None:
    """El MCP de VigIA aún no expone incidencias: sus casos esperan al Prompt 12."""
    for case in _all_cases():
        mentions = bool(_INCIDENTS.search(str(case.get("pregunta"))))
        assert mentions == ("P12" in case.depends), case.id


def test_negative_cases_never_expect_a_figure() -> None:
    for case in _all_cases():
        if case.get("categoria") == "negativa":
            properties = cast("Mapping[str, object]", case.get("propiedades"))
            assert properties.get("sin_cifras") is True, case.id


# --- 3. Casos del catálogo semilla de VigIA (5.17.7) ---------------------------------------


def _catalog_cases() -> list[Case]:
    return [c for c in _all_cases() if c.get("categoria") == "catalogo"]


def test_catalog_seed_covers_the_simulator_messages() -> None:
    """Las dos erratas, la estación ambigua, «@carmen 2», «@carmen ayuda», fuera de catálogo,
    clasificación restringida y mensaje de grupo sin mención (5.17.11).
    """
    messages = [str(c.get("pregunta")) for c in _catalog_cases()]
    answers = Counter(
        str(cast("Mapping[str, object]", c.get("catalogo"))["respuesta"]) for c in _catalog_cases()
    )
    assert any("Arcorcon" in m for m in messages)
    assert any("Alconcon" in m for m in messages)
    assert "@carmen 2" in messages
    assert "@carmen ayuda" in messages
    for answer in (
        "ambigua",
        "opcion",
        "ayuda",
        "fuera_de_catalogo",
        "consultar_en_web",
        "ignorar",
    ):
        assert answers[answer] >= 1, answer


def test_typos_resolve_to_alcorcon() -> None:
    for case in _catalog_cases():
        if re.search("Arcorcon|Alconcon", str(case.get("pregunta"))):
            catalog = cast("Mapping[str, object]", case.get("catalogo"))
            parameters = cast("Mapping[str, object]", catalog["parametros"])
            assert parameters["estacion"] == "Alcorcón", case.id


def test_a_group_message_without_mention_is_ignored() -> None:
    for case in _catalog_cases():
        catalog = cast("Mapping[str, object]", case.get("catalogo"))
        ignored = catalog["respuesta"] == "ignorar"
        assert ignored == (catalog.get("en_grupo") is True and catalog.get("mencion") is False)


# --- 4. Planes esperados frente a los catálogos --------------------------------------------


def _plan_cases() -> Iterator[Case]:
    yield from (c for c in _all_cases() if c.plan)


@pytest.mark.parametrize("case", list(_plan_cases()), ids=lambda c: c.id)
def test_expected_plan_only_names_catalog_tools(case: Case) -> None:
    systems = cast("list[str]", case.plan["systems"])
    assert set(systems) <= set(_catalogs()), f"{case.id}: sistema sin catálogo"
    tools = _tools_of(systems)
    required = cast("list[str]", case.plan.get("steps_min", []))
    forbidden = cast("list[str]", case.plan.get("steps_prohibidos", []))
    assert set(required) | set(forbidden) <= set(tools), case.id
    assert not set(required) & set(forbidden), case.id
    dependencies = cast("Mapping[str, list[str]]", case.plan.get("dependencias", {}))
    for step, before in dependencies.items():
        assert {step, *before} <= set(required), case.id


@pytest.mark.parametrize("case", list(_plan_cases()), ids=lambda c: c.id)
def test_required_tools_allow_the_role_of_the_case(case: Case) -> None:
    tools = _tools_of(cast("list[str]", case.plan["systems"]))
    for name in cast("list[str]", case.plan.get("steps_min", [])):
        roles = cast("list[str]", tools[name][1]["roles"])
        assert case.get("role") in roles, f"{case.id}: {name} no admite {case.get('role')}"


@pytest.mark.parametrize("case", list(_plan_cases()), ids=lambda c: c.id)
def test_expected_arguments_are_accepted_by_the_catalog(case: Case) -> None:
    """Un caso que depende de un prompt posterior espera argumentos que el catálogo aún no tiene."""
    tools = _tools_of(cast("list[str]", case.plan["systems"]))
    required = set(cast("list[str]", case.plan.get("steps_min", [])))
    arguments = cast("Mapping[str, object]", case.plan.get("argumentos", {}))
    for key, value in arguments.items():
        tool, _, name = key.partition(".")
        assert tool in required, f"{case.id}: {key} no es de un paso obligatorio"
        input_schema = cast("Mapping[str, Mapping[str, Json]]", tools[tool][1]["input_schema"])
        schema = input_schema["properties"]
        assert name in schema, f"{case.id}: {tool} no tiene el argumento {name}"
        if not case.depends:
            errors = [e.message for e in Draft202012Validator(schema[name]).iter_errors(value)]
            assert errors == [], f"{case.id}: {key}={value!r}: {errors}"


def test_role_variants_follow_the_tool_roles() -> None:
    """El comportamiento diferencial por rol coincide con los roles del catálogo."""
    for case in _all_cases():
        for variant in cast("list[Json]", case.get("variantes_por_rol") or []):
            plan = cast("Mapping[str, object]", variant.get("plan_esperado") or {})
            tools = _tools_of(cast("list[str]", plan.get("systems", [])))
            for name in cast("list[str]", plan.get("steps_min", [])):
                assert variant["role"] in cast("list[str]", tools[name][1]["roles"]), case.id
            if variant["modo_esperado"] == ResponseMode.REFUSE:
                assert "negativa" in variant, case.id


# --- 5. Planes esperados en forma normal canónica ------------------------------------------


def _is_delegation(document: Mapping[str, object]) -> bool:
    return "tasks" in document


@pytest.mark.parametrize("path", _expected_plan_files(), ids=lambda p: p.name)
def test_expected_plan_validates_against_its_contract(path: Path) -> None:
    document = _json(path)
    schema = "delegation-plan.schema.json" if _is_delegation(document) else "plan.schema.json"
    assert _errors(CONTRACTS / schema, document) == []


def _pretty(document: object) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _canonical_delegation(document: Mapping[str, object]) -> Json:
    """Forma normal del DelegationPlan, la misma regla que 6.2.2: claves ordenadas, tareas por
    task_id, dependencias ordenadas y sin campos con su valor por defecto.
    """
    tasks = []
    for task in sorted(cast("list[Json]", document["tasks"]), key=lambda t: str(t["task_id"])):
        entry = {k: v for k, v in task.items() if k not in ("depends_on", "optional")}
        if task.get("depends_on"):
            entry["depends_on"] = sorted(cast("list[str]", task["depends_on"]))
        if task.get("optional"):
            entry["optional"] = True
        tasks.append(entry)
    canonical = {k: v for k, v in document.items() if k not in ("tasks", "requires_human_approval")}
    canonical["tasks"] = tasks
    if document.get("requires_human_approval"):
        canonical["requires_human_approval"] = True
    return canonical


def _query_plan(path: Path) -> QueryPlan:
    return plan_from_dict(_json(path))


def _delegation_plan(document: Mapping[str, object]) -> DelegationPlan:
    """El documento leído como DelegationPlan del dominio, que aplica sus invariantes."""
    tasks = []
    for raw in cast("list[Json]", document["tasks"]):
        budgets = cast("Mapping[str, int]", raw["budgets"])
        tasks.append(
            AgentTask(
                task_id=TaskId(str(raw["task_id"])),
                agent_id=AgentId(str(raw["agent_id"])),
                objective=str(raw["objective"]),
                entities=cast("Mapping[str, str]", raw["entities"]),
                expects=Expects(str(raw["expects"])),
                locale=Locale(str(raw["locale"])),
                budgets=TaskBudgets(
                    max_wall_ms=budgets["max_wall_ms"],
                    max_tokens=budgets["max_tokens"],
                    max_cost_eur=_decimal(budgets["max_cost_eur"]),
                ),
                delegated_identity=DelegatedIdentityRef(str(raw["delegated_identity"])),
                depends_on=tuple(TaskId(t) for t in cast("list[str]", raw.get("depends_on", []))),
                optional=bool(raw.get("optional", False)),
            )
        )
    composition = cast("Mapping[str, object]", document["composition"])
    budgets = cast("Mapping[str, int]", document["budgets"])
    return DelegationPlan(
        plan_id=DelegationPlanId(str(document["plan_id"])),
        turn_id=TurnId(str(document["turn_id"])),
        response_mode=ResponseMode(str(document["response_mode"])),
        principal_id=PrincipalId(str(document["principal_id"])),
        policy_version=str(document["policy_version"]),
        tasks=tuple(tasks),
        composition=Composition(
            CompositionKind(str(composition["kind"])),
            tuple(TaskId(t) for t in cast("list[str]", composition["tasks"])),
            entity=cast("str | None", composition.get("entity")),
            canonical_id=cast("str | None", composition.get("canonical_id")),
        ),
        budgets=Budgets(
            max_wall_ms=budgets["max_wall_ms"],
            max_tokens=budgets["max_tokens"],
            max_cost_eur=_decimal(budgets["max_cost_eur"]),
            max_agents=budgets["max_agents"],
        ),
        requires_human_approval=bool(document.get("requires_human_approval", False)),
    )


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


@pytest.mark.parametrize("path", _expected_plan_files(), ids=lambda p: p.name)
def test_expected_plan_is_in_canonical_normal_form(path: Path) -> None:
    """El fichero es su propia forma normal: leerlo y volver a escribirlo no cambia nada."""
    document = _json(path)
    if _is_delegation(document):
        _delegation_plan(document)
        canonical: object = _canonical_delegation(document)
    else:
        canonical = json.loads(canonical_json(_query_plan(path)))
    assert path.read_text(encoding="utf-8") == _pretty(canonical)


@pytest.mark.parametrize(
    "path",
    [p for p in _expected_plan_files() if not _is_delegation(_json(p))],
    ids=lambda p: p.name,
)
def test_expected_query_plan_matches_the_catalogs(path: Path) -> None:
    plan = _query_plan(path)
    for system, version in plan.catalog_versions.items():
        assert _catalogs()[system]["catalog_version"] == version, path.name
    for step in plan.steps:
        tool = _tool(step.system, step.tool)
        assert tool is not None, f"{path.name}: {step.system}.{step.tool} no está en el catálogo"
        schema = cast("Json", tool["input_schema"])
        literal = {k: v for k, v in step.arguments.items() if not isinstance(v, FactReference)}
        properties = cast("Mapping[str, Json]", schema["properties"])
        assert set(step.arguments) <= set(properties), path.name
        for name, value in literal.items():
            argument = list(value) if isinstance(value, tuple) else value
            assert Draft202012Validator(properties[name]).is_valid(argument), (path.name, name)
        missing = set(cast("list[str]", schema.get("required", []))) - set(step.arguments)
        assert missing == set(), f"{path.name}: {step.tool} sin {missing}"


def _references() -> Iterator[tuple[str, str]]:
    for case in _all_cases():
        for name in cast("list[str]", case.plan.get("canonicos", [])):
            yield case.id, name
    for entry in _mode_cases():
        for name in cast("list[str]", entry.get("canonicos", [])):
            yield str(entry["id"]), name


def test_every_expected_plan_is_referenced_and_every_reference_exists() -> None:
    names = {p.name for p in _expected_plan_files()}
    referenced = {name for _, name in _references()}
    assert referenced == names


@pytest.mark.parametrize(
    "case", [c for c in _plan_cases() if c.plan.get("canonicos")], ids=lambda c: c.id
)
def test_case_assertions_agree_with_its_canonical_plans(case: Case) -> None:
    for name in cast("list[str]", case.plan["canonicos"]):
        document = _json(EXPECTED_PLANS / name)
        if _is_delegation(document):
            agents = {str(t["agent_id"]) for t in cast("list[Json]", document["tasks"])}
            assert agents == set(cast("list[str]", case.get("agentes"))), case.id
            assert document["response_mode"] == case.get("modo_esperado"), case.id
            continue
        plan = _query_plan(EXPECTED_PLANS / name)
        tools = {s.tool for s in plan.steps}
        by_tool = {s.tool: s for s in plan.steps}
        assert plan.intent == case.plan["intent"], case.id
        assert sorted(plan.systems) == sorted(cast("list[str]", case.plan["systems"])), case.id
        assert set(cast("list[str]", case.plan.get("steps_min", []))) <= tools, case.id
        assert not set(cast("list[str]", case.plan.get("steps_prohibidos", []))) & tools, case.id
        for key, value in cast("Mapping[str, object]", case.plan.get("argumentos", {})).items():
            tool, _, argument = key.partition(".")
            assert by_tool[tool].arguments.get(argument) == value, (case.id, key)
        dependencies = cast("Mapping[str, list[str]]", case.plan.get("dependencias", {}))
        steps = {s.step_id: s.tool for s in plan.steps}
        for tool, before in dependencies.items():
            declared = {steps[d.step_id] for d in by_tool[tool].depends_on}
            assert set(before) <= declared, (case.id, tool)


# --- 6. Conjunto de modos (2.3.2, 2.3.4) ---------------------------------------------------


def test_every_mode_has_at_least_four_labeled_cases() -> None:
    counts = Counter(str(e["modo"]) for e in _mode_cases())
    assert set(counts) == {m.value for m in ResponseMode}
    assert min(counts.values()) >= 4, counts


def test_mode_ids_are_unique() -> None:
    ids = [str(e["id"]) for e in _mode_cases()]
    assert len(set(ids)) == len(ids)


DISTINCTION: Final = {
    "¿Qué es VigIA?": ResponseMode.SUPERVISOR_DIRECT,
    "¿Qué puede hacer VigIA?": ResponseMode.SUPERVISOR_DIRECT,
    "¿Tengo acceso a VigIA?": ResponseMode.SUPERVISOR_DIRECT,
    "¿Cómo está VigIA?": ResponseMode.DELEGATE_SINGLE,
    "¿Qué alarmas tiene VigIA?": ResponseMode.DELEGATE_SINGLE,
    "¿Qué estaciones con más alarmas tienen peor margen?": ResponseMode.DELEGATE_MULTI,
    "¿Cuál fue el margen?": ResponseMode.CLARIFY,
}


def test_the_semantic_distinction_table_is_labeled_as_in_2_3_4() -> None:
    labeled = {str(e["pregunta"]): str(e["modo"]) for e in _mode_cases()}
    for question, mode in DISTINCTION.items():
        assert labeled.get(question) == mode, question
    plenmind = {
        str(e["role"]): str(e["modo"])
        for e in _mode_cases()
        if e["pregunta"] == "¿Qué es Plenmind?"
    }
    assert set(plenmind.values()) == {ResponseMode.SUPERVISOR_DIRECT, ResponseMode.REFUSE}


def test_pairs_differ_in_mode() -> None:
    """Cada par son dos preguntas casi idénticas que se resuelven por caminos distintos."""
    pairs: dict[str, list[Json]] = {}
    for entry in _mode_cases():
        if "par" in entry:
            pairs.setdefault(str(entry["par"]), []).append(entry)
    assert pairs
    for name, members in pairs.items():
        assert len(members) == 2, name
        assert members[0]["modo"] != members[1]["modo"], name
    vigia = next(
        m
        for m in pairs.values()
        if {str(e["pregunta"]) for e in m} == {"¿Qué es VigIA?", "¿Cómo está VigIA?"}
    )
    assert {str(e["modo"]) for e in vigia} == {"SUPERVISOR_DIRECT", "DELEGATE_SINGLE"}


def test_delegating_modes_name_their_agents() -> None:
    for entry in _mode_cases():
        agents = cast("list[str]", entry.get("agentes", []))
        mode = ResponseMode(str(entry["modo"]))
        if mode is ResponseMode.DELEGATE_SINGLE:
            assert len(agents) == 1, entry["id"]
        elif mode is ResponseMode.DELEGATE_MULTI:
            assert len(agents) >= 2, entry["id"]
        else:
            assert agents == [], entry["id"]


def test_mode_set_spans_languages_and_roles() -> None:
    entries = _mode_cases()
    assert {str(e["locale"]) for e in entries} == {loc.value for loc in Locale}
    assert {str(e["role"]) for e in entries} <= {r.value for r in Role}
