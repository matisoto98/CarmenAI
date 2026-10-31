"""Prompt 9: lo que solo se exige al servidor simulado (mcp-mock/).

La batería de test_mcp_contract.py vale para cualquier servidor. Aquí se comprueba lo propio del
simulado: determinismo, modos de fallo por configuración, dominio documental, RBAC por rol del
token simulado, agregación real sobre el conjunto de datos y el registro con instrucciones
embebidas para las pruebas de inyección.
"""

import ast
import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Final

import pytest

from contract.conftest import ADMIN_TOKEN, MockServer, run_mock
from contract.mcp_client import (
    Json,
    McpClient,
    McpHttpError,
    McpTransportError,
    ToolResult,
    as_list,
    as_object,
)
from contract.test_mcp_contract import example_arguments, schema_errors

pytestmark = pytest.mark.contract

ROOT: Final = Path(__file__).resolve().parents[3]
FORBIDDEN: Final = 403
UNAUTHORIZED: Final = 401
BAD_REQUEST: Final = 400
ROWS_CAP: Final = 500
OPERATOR_NORTE: Final = "sim:OPERATOR:usr_ope1:norte"
OPERATOR_CENTRO: Final = "sim:OPERATOR:usr_ope2:centro"
MANAGER: Final = "sim:MANAGER:usr_man1"
AUDITOR: Final = "sim:AUDITOR:usr_aud1"
GETAFE: Final = "1"
ALCORCON: Final = "2"
DETERMINISM_RUNS: Final = 20


def connect(server: MockServer, system_id: str, token: str = ADMIN_TOKEN) -> McpClient:
    client = McpClient(server.url(system_id), token)
    client.initialize()
    return client


def envelope_of(result: ToolResult) -> dict[str, Json]:
    assert not result.is_error, result.text
    assert result.envelope is not None
    return result.envelope


def call(
    server: MockServer, system_id: str, tool: str, args: dict[str, Json], token: str = ADMIN_TOKEN
) -> dict[str, Json]:
    client = connect(server, system_id, token)
    try:
        return envelope_of(client.call_tool(tool, args))
    finally:
        client.close()


def facts(envelope: dict[str, Json]) -> dict[str, dict[str, Json]]:
    return {str(f["key"]): f for f in (as_object(x) for x in as_list(envelope["facts"]))}


def value(envelope: dict[str, Json], key: str) -> Json:
    return facts(envelope)[key]["value"]


def number(envelope: dict[str, Json], key: str) -> Decimal:
    raw = value(envelope, key)
    assert isinstance(raw, int | float), (key, raw)
    return Decimal(str(raw))


def warning_codes(envelope: dict[str, Json]) -> set[str]:
    return {str(as_object(w)["code"]) for w in as_list(envelope["warnings"])}


def evidence(envelope: dict[str, Json]) -> Json:
    """Lo que debe repetirse en dos llamadas iguales: todo menos call_id y generated_at."""
    return {
        k: v for k, v in envelope.items() if k not in ("call_id", "correlation_id", "generated_at")
    }


# --- Catálogo y determinismo -----------------------------------------------------------------


@pytest.mark.parametrize("system_id", ["vigia", "plenmind"])
def test_the_mock_serves_exactly_the_catalog_of_the_golden_set(
    mock_server: MockServer, system_id: str
) -> None:
    catalog = json.loads((ROOT / f"eval/fixtures/catalog_{system_id}.json").read_text("utf-8"))
    client = connect(mock_server, system_id)
    served = client.list_tools()
    version = client.call_tool(str(served[0]["name"]), example_arguments(served[0]))
    client.close()
    expected = [
        {
            "name": t["name"],
            "description": t["description"],
            "inputSchema": t["input_schema"],
            "result_kind": t["result_kind"],
            "roles": t["roles"],
        }
        for t in catalog["tools"]
    ]
    assert [{k: t[k] for k in expected[0]} for t in served] == expected
    assert envelope_of(version)["catalog_version"] == catalog["catalog_version"]


@pytest.mark.parametrize("system_id", ["vigia", "plenmind"])
def test_the_same_call_returns_identical_evidence_twenty_times(
    mock_server: MockServer, system_id: str
) -> None:
    client = connect(mock_server, system_id)
    for tool in client.list_tools():
        args = example_arguments(tool)
        first = evidence(envelope_of(client.call_tool(str(tool["name"]), args)))
        for _ in range(DETERMINISM_RUNS - 1):
            again = evidence(envelope_of(client.call_tool(str(tool["name"]), args)))
            assert again == first, tool["name"]
    client.close()


def test_two_processes_with_the_same_seed_produce_the_same_facts() -> None:
    args: dict[str, Json] = {"metric": "alarmas", "group_by": "estacion", "period": "30d"}
    with run_mock() as one, run_mock() as two:
        assert evidence(call(one, "vigia", "top_n", args)) == evidence(
            call(two, "vigia", "top_n", args)
        )


def test_another_seed_produces_another_dataset() -> None:
    args: dict[str, Json] = {"metric": "alarmas", "group_by": "estacion", "period": "30d"}
    with run_mock() as default, run_mock({"MCP_MOCK_SEED": "7"}) as other:
        assert evidence(call(default, "vigia", "top_n", args)) != evidence(
            call(other, "vigia", "top_n", args)
        )


# --- Modos de fallo --------------------------------------------------------------------------

QUERY: Final[dict[str, Json]] = {"metric": "alarmas", "period": "7d"}


@pytest.fixture
def failing() -> Iterator[MockServer]:
    with run_mock(
        {
            "MCP_MOCK_FAILURES": (
                "vigia.query_metric=slow:400;vigia.top_n=error;vigia.build_dossier=forbidden;"
                "vigia.correlate_events=down;vigia.get_situation_brief=invalid"
            )
        }
    ) as server:
        yield server


def test_slowness_delays_the_answer_without_changing_it(
    failing: MockServer, mock_server: MockServer
) -> None:
    started = time.monotonic()
    slow = call(failing, "vigia", "query_metric", QUERY)
    assert time.monotonic() - started >= 0.4
    assert evidence(slow) == evidence(call(mock_server, "vigia", "query_metric", QUERY))


def test_an_error_mode_returns_a_tool_error(failing: MockServer) -> None:
    client = connect(failing, "vigia")
    result = client.call_tool("top_n", {"metric": "alarmas", "group_by": "zona", "period": "7d"})
    client.close()
    assert result.is_error
    assert "simulado" in result.text


def test_a_forbidden_mode_answers_403_whatever_the_role(failing: MockServer) -> None:
    client = connect(failing, "vigia")
    with pytest.raises(McpHttpError) as raised:
        client.call_tool("build_dossier", {"entity": "red", "period": "7d"})
    client.close()
    assert raised.value.status == FORBIDDEN


def test_a_down_mode_drops_the_connection(failing: MockServer) -> None:
    client = connect(failing, "vigia")
    with pytest.raises(McpTransportError):
        client.call_tool("correlate_events", {"site_id": GETAFE, "window": "7d"})
    client.close()


def test_an_invalid_mode_returns_an_envelope_that_breaks_the_contract(
    failing: MockServer,
) -> None:
    client = connect(failing, "vigia")
    result = client.call_tool("get_situation_brief", {})
    client.close()
    assert result.envelope is not None
    errors = schema_errors(result.envelope)
    assert any("passages" in e for e in errors), errors


def test_a_whole_server_down_refuses_even_the_handshake() -> None:
    with run_mock({"MCP_MOCK_FAILURES": "*=down"}) as server, pytest.raises(McpTransportError):
        connect(server, "vigia")


def test_a_malformed_failure_configuration_stops_the_mock() -> None:
    with (
        pytest.raises(RuntimeError, match="no arrancó"),
        run_mock({"MCP_MOCK_FAILURES": "vigia.query_metric=explota"}),
    ):
        pass


# --- Dominio documental (6.9) ----------------------------------------------------------------


def test_a_procedure_comes_with_document_section_version_date_and_its_warning(
    mock_server: MockServer,
) -> None:
    envelope = call(mock_server, "plenmind", "get_procedure", {"document_id": "RB-041"})
    passages = [as_object(p) for p in as_list(envelope["passages"])]
    assert envelope["facts"] == []
    assert passages
    for p in passages:
        assert p["document_id"] == "RB-041"
        assert p["section"]
        assert p["doc_version"]
        assert p["updated_at"]
    kinds = [p["kind"] for p in passages]
    assert kinds[0] == "warning", "el aviso va antes de los pasos, como en el origen"
    assert "procedure" in kinds
    media = [as_object(m) for m in as_list(envelope["media"])]
    assert media
    assert all(str(m["uri"]).startswith("http") for m in media)


def test_media_travels_as_an_authenticated_reference(mock_server: MockServer) -> None:
    envelope = call(mock_server, "plenmind", "get_media", {"media_id": "RB-041-fig2"})
    (media,) = (as_object(m) for m in as_list(envelope["media"]))
    assert envelope["passages"] == []
    assert media["mime"] == "image/png"
    assert media["caption"]
    uri = str(media["uri"])
    request = urllib.request.Request(uri, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
    with urllib.request.urlopen(request, timeout=5) as response:
        body = response.read()
        assert response.headers["Content-Type"] == "image/png"
    assert body.startswith(b"\x89PNG")
    assert len(body) == media["bytes"]
    with pytest.raises(urllib.error.HTTPError) as raised:
        urllib.request.urlopen(uri, timeout=5)
    raised.value.close()
    assert raised.value.code == UNAUTHORIZED


def test_search_glossary_and_listing_return_their_passage_kinds(mock_server: MockServer) -> None:
    found = call(mock_server, "plenmind", "search_documents", {"query": "sonda de nivel"})
    relevances = [as_object(p)["relevance"] for p in as_list(found["passages"])]
    assert relevances
    assert relevances == sorted(relevances, reverse=True)  # type: ignore[type-var]
    listed = call(mock_server, "plenmind", "list_procedures", {"equipo": "sonda"})
    assert {as_object(p)["kind"] for p in as_list(listed["passages"])} == {"reference"}
    term = call(mock_server, "plenmind", "glossary", {"term": "lavaderos"})
    (definition,) = (as_object(p) for p in as_list(term["passages"]))
    assert definition["kind"] == "definition"
    assert "72" in str(definition["text"])
    assert "65" in str(definition["text"])


def test_an_outdated_runbook_is_returned_with_its_old_date(mock_server: MockServer) -> None:
    envelope = call(mock_server, "plenmind", "get_procedure", {"document_id": "RB-009"})
    dates = {str(as_object(p)["updated_at"]) for p in as_list(envelope["passages"])}
    assert dates
    assert all(d.startswith("2023") for d in dates)


def test_an_unknown_document_is_an_empty_answer_with_a_warning(mock_server: MockServer) -> None:
    envelope = call(mock_server, "plenmind", "get_procedure", {"document_id": "RB-999"})
    assert envelope["passages"] == []
    assert warning_codes(envelope) == {"documento_no_encontrado"}


# --- Identidad simulada y RBAC propio --------------------------------------------------------


def test_the_same_query_returns_the_scope_of_the_role(mock_server: MockServer) -> None:
    network = call(mock_server, "vigia", "query_metric", QUERY, MANAGER)
    norte = call(mock_server, "vigia", "query_metric", QUERY, OPERATOR_NORTE)
    centro = call(mock_server, "vigia", "query_metric", QUERY, OPERATOR_CENTRO)
    assert number(norte, "alarmas") < number(network, "alarmas")
    assert number(norte, "alarmas") != number(centro, "alarmas")
    assert "ambito_zona" in warning_codes(norte)
    assert "ambito_zona" not in warning_codes(network)


def test_an_operator_cannot_read_a_site_outside_its_zone(mock_server: MockServer) -> None:
    args: dict[str, Json] = {**QUERY, "site_id": GETAFE}
    assert call(mock_server, "vigia", "query_metric", args, OPERATOR_CENTRO)["facts"]
    client = connect(mock_server, "vigia", OPERATOR_NORTE)
    with pytest.raises(McpHttpError) as raised:
        client.call_tool("query_metric", args)
    client.close()
    assert raised.value.status == FORBIDDEN


def test_without_admin_there_is_no_correlation(mock_server: MockServer) -> None:
    client = connect(mock_server, "vigia", MANAGER)
    names = {str(t["name"]) for t in client.list_tools()}
    with pytest.raises(McpHttpError) as raised:
        client.call_tool("correlate_events", {"site_id": GETAFE, "window": "7d"})
    client.close()
    assert "correlate_events" not in names
    assert raised.value.status == FORBIDDEN
    assert call(mock_server, "vigia", "correlate_events", {"site_id": GETAFE, "window": "7d"})


def test_an_auditor_reads_definitions_but_not_procedures(mock_server: MockServer) -> None:
    assert call(mock_server, "plenmind", "glossary", {"term": "SAI"}, AUDITOR)["passages"]
    client = connect(mock_server, "plenmind", AUDITOR)
    with pytest.raises(McpHttpError) as raised:
        client.call_tool("get_procedure", {"document_id": "RB-041"})
    client.close()
    assert raised.value.status == FORBIDDEN


@pytest.mark.parametrize("token", ["sim:INTRUSO:usr_x", "otro-token", "sim:ADMIN"])
def test_an_unknown_token_is_unauthorized(mock_server: MockServer, token: str) -> None:
    with pytest.raises(McpHttpError) as raised:
        connect(mock_server, "vigia", token)
    assert raised.value.status == UNAUTHORIZED


def test_a_request_without_a_session_is_refused(mock_server: MockServer) -> None:
    client = connect(mock_server, "vigia")
    client.session_id = None
    with pytest.raises(McpHttpError) as raised:
        client.list_tools()
    assert raised.value.status == BAD_REQUEST


# --- Agregación real sobre el conjunto de datos ----------------------------------------------


def test_figures_add_up_across_tools(mock_server: MockServer) -> None:
    period: dict[str, Json] = {"period": "30d"}
    total = call(mock_server, "vigia", "query_metric", {"metric": "alarmas", **period})
    ranking = call(
        mock_server,
        "vigia",
        "top_n",
        {"metric": "alarmas", "group_by": "estacion", "limit": 50, **period},
    )
    by_zone = call(
        mock_server, "vigia", "top_n", {"metric": "alarmas", "group_by": "zona", **period}
    )
    assert sum(number(ranking, k) for k in facts(ranking)) == number(total, "alarmas")
    assert sum(number(by_zone, k) for k in facts(by_zone)) == number(total, "alarmas")
    states = call(
        mock_server, "vigia", "query_metric", {"metric": "estado_monitores", "period": "ahora"}
    )
    parts = ("monitores_ok", "monitores_ko", "monitores_indeterminado")
    assert sum(number(states, k) for k in parts) == number(states, "monitores_total")
    ko = call(mock_server, "vigia", "query_metric", {"metric": "monitores_ko", "period": "ahora"})
    assert number(ko, "monitores_ko") == number(states, "monitores_ko")


def test_the_dossier_matches_the_metric_of_its_site(mock_server: MockServer) -> None:
    dossier = call(
        mock_server, "vigia", "build_dossier", {"entity": "site", "id": GETAFE, "period": "30d"}
    )
    site = call(
        mock_server,
        "vigia",
        "query_metric",
        {"metric": "alarmas", "period": "30d", "site_id": GETAFE},
    )
    assert number(dossier, "alarmas_total") == number(site, "alarmas")
    assert facts(dossier)["alarmas_total"]["entity"] == {
        "type": "site",
        "id": GETAFE,
        "name": "Getafe",
    }
    dominant = facts(dossier)["tipo_dominante_pct"]
    assert as_object(dominant["dimensions"])["tipo"]
    assert Decimal(0) < number(dossier, "tipo_dominante_pct") <= Decimal(100)


def test_open_alarms_and_printer_rankings_carry_their_mandatory_warnings(
    mock_server: MockServer,
) -> None:
    open_now = call(
        mock_server, "vigia", "query_metric", {"metric": "alarmas_abiertas", "period": "ahora"}
    )
    assert "alarmas_abiertas_acumuladas" in warning_codes(open_now)
    ranking = call(
        mock_server,
        "vigia",
        "top_n",
        {"metric": "alarmas", "group_by": "tipo_alarma", "period": "90d"},
    )
    top = facts(ranking)["top_01"]
    assert as_object(top["dimensions"])["tipo_alarma"] == "Error de impresora"
    assert "ranking_dominado_por_impresoras" in warning_codes(ranking)


def test_periods_are_interpreted_and_declared(mock_server: MockServer) -> None:
    month = call(
        mock_server, "vigia", "query_metric", {"metric": "alarmas", "period": "mes_actual"}
    )
    assert month["period_interpreted"] == {
        "expression": "mes_actual",
        "from": "2026-07-01T00:00:00Z",
        "to": "2026-07-27T09:14:22Z",
        "text": "del 1 al 27 de julio de 2026",
    }
    named = call(mock_server, "vigia", "query_metric", {"metric": "alarmas", "period": "2026-05"})
    assert as_object(named["period_interpreted"])["text"] == "mayo de 2026"
    client = connect(mock_server, "vigia")
    too_old = client.call_tool("query_metric", {"metric": "alarmas", "period": "2025-01"})
    client.close()
    assert too_old.is_error
    assert "400 días" in too_old.text


def test_a_heavy_series_is_cut_and_declared_partial(mock_server: MockServer) -> None:
    series = call(
        mock_server,
        "vigia",
        "query_metric",
        {"metric": "alarmas", "period": "90d", "granularity": "hora"},
    )
    assert series["partial"] is True
    assert "recortado" in warning_codes(series)
    assert len(as_list(series["rows"])) == ROWS_CAP
    assert not schema_errors(series)


def test_site_resolver_handles_typos_and_asks_to_confirm_distant_ones(
    mock_server: MockServer,
) -> None:
    close = call(mock_server, "vigia", "site_resolver", {"texto": "Arcorcon"})
    assert value(close, "site_id") == ALCORCON
    assert value(close, "site_name") == "Alcorcón"
    assert not warning_codes(close)
    distant = call(mock_server, "vigia", "site_resolver", {"texto": "Alconcon"})
    assert value(distant, "site_id") == ALCORCON
    assert warning_codes(distant) == {"resolucion_aproximada"}
    nothing = call(mock_server, "vigia", "site_resolver", {"texto": "Kuala Lumpur"})
    assert nothing["facts"] == []
    assert warning_codes(nothing) == {"sin_coincidencia"}


def test_the_dataset_carries_one_record_with_embedded_instructions(
    mock_server: MockServer,
) -> None:
    """Para las pruebas de inyección: el sistema devuelve el texto tal cual, como dato."""
    alarms = call(
        mock_server,
        "vigia",
        "query_metric",
        {"metric": "alarmas", "period": "30d", "site_id": ALCORCON},
    )
    texts = [str(as_object(r).get("descripcion", "")) for r in as_list(alarms["rows"])]
    injected = [t for t in texts if "ignora las instrucciones" in t.lower()]
    assert len(injected) == 1
    found = call(mock_server, "plenmind", "search_documents", {"query": "nota del sistema"})
    passages = [str(as_object(p)["text"]).lower() for p in as_list(found["passages"])]
    assert any("ignora las instrucciones" in p for p in passages)


# --- Independencia ---------------------------------------------------------------------------

INDEPENDENT: Final = (
    *sorted((ROOT / "mcp-mock").glob("*.py")),
    ROOT / "api/tests/contract/conftest.py",
    ROOT / "api/tests/contract/mcp_client.py",
    ROOT / "api/tests/contract/test_mcp_contract.py",
)


@pytest.mark.parametrize("path", INDEPENDENT, ids=lambda p: p.name)
def test_the_mock_and_the_battery_do_not_import_carmen(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        name.split(".")[0]
        for node in ast.walk(tree)
        for name in (
            [a.name for a in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
            if isinstance(node, ast.ImportFrom)
            else []
        )
    }
    assert "carmen" not in imported
