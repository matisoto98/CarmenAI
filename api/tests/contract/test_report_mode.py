"""Prompt 10: el modo informe, el transporte stdio y el perfil vigia-real, probados sin VigIA.

Lo que se ejecutará contra el MCP real tiene que funcionar antes aquí:
  - con `--report`, la batería registra cada fallo, sigue con lo demás y escribe el informe;
  - por stdio, a través de un puente como el de 4.6.6, la batería pasa igual que por HTTP y el
    token del puente no aparece ni en la salida ni en el informe;
  - el perfil vigia-real exige el perfil dev, los certificados y el puente, y CI nunca lo activa.
"""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest

from contract.conftest import (
    ADMIN_TOKEN,
    ROOT,
    MockServer,
    parse_endpoint,
    run_mock,
    vigia_real_endpoint,
)
from contract.mcp_client import McpClient, McpRpcError, McpTransportError, as_object
from contract.report import SECTIONS, Findings, Outcome, render

pytestmark = [pytest.mark.contract, pytest.mark.mock_only]

CONTRACT: Final = ROOT / "api" / "tests" / "contract"
BRIDGE: Final = CONTRACT / "stdio_bridge.py"
BRIDGE_TOKEN: Final = "sim:ADMIN:usr_puente_secreto"
BATTERY: Final = ("test_mcp_contract.py", "test_conformance.py")
BRIDGE_HTTP_ERROR: Final = -32001


@pytest.fixture(scope="module")
def mock() -> Iterator[MockServer]:
    with run_mock() as server:
        yield server


def clean_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CARMEN_", "VIGIA_MCP_"))}
    return {**env, **extra}


def run_battery(report: Path, **env: str) -> subprocess.CompletedProcess[str]:
    """La orden del Prompt 10, desde api/, en un pytest aparte."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *(f"tests/contract/{name}" for name in BATTERY),
            "-v",
            "-p",
            "no:cacheprovider",
            "--report",
            str(report),
        ],
        cwd=ROOT / "api",
        env=clean_env(**env),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def stdio_target(server: MockServer, system_id: str = "vigia") -> str:
    return f"{system_id}=stdio:{sys.executable} {BRIDGE} {server.url(system_id)}"


# --- Transporte stdio -------------------------------------------------------------------------


def bridge_client(server: MockServer) -> McpClient:
    """El puente hereda MCP_BRIDGE_TOKEN del entorno; el cliente no recibe token."""
    endpoint = parse_endpoint(f"stdio:{sys.executable} {BRIDGE} {server.url('vigia')}")
    assert endpoint.command is not None
    return McpClient(endpoint.url, None, command=endpoint.command)


def test_the_client_speaks_mcp_over_stdio(
    mock: MockServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCP_BRIDGE_TOKEN", BRIDGE_TOKEN)
    client = bridge_client(mock)
    try:
        info = client.initialize()
        tools = client.list_tools()
        result = client.call_tool(
            "query_metric", {"metric": "monitores_ko", "period": "ahora"}, correlation_id="cor_x1"
        )
    finally:
        client.close()
    assert as_object(info["serverInfo"])["name"] == "carmen-mcp-mock-vigia"
    assert "query_metric" in {t["name"] for t in tools}
    assert result.structured
    assert result.envelope is not None
    assert result.envelope["correlation_id"] == "cor_x1"


def test_a_refusal_behind_the_bridge_is_an_error_not_an_answer(
    mock: MockServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MCP_BRIDGE_TOKEN", raising=False)
    client = bridge_client(mock)
    with pytest.raises(McpRpcError) as raised:
        client.initialize()
    client.close()
    assert raised.value.code == BRIDGE_HTTP_ERROR
    assert "HTTP 401" in raised.value.message


def test_a_process_that_dies_is_a_transport_error() -> None:
    client = McpClient("stdio:exit", None, command=(sys.executable, "-c", "pass"))
    with pytest.raises(McpTransportError, match="terminó"):
        client.initialize()
    client.close()


def test_a_silent_process_times_out_instead_of_hanging() -> None:
    silent = (sys.executable, "-c", "import sys; sys.stdin.read()")
    client = McpClient("stdio:silencio", None, timeout_s=0.5, command=silent)
    with pytest.raises(McpTransportError, match="sin respuesta"):
        client.initialize()
    client.close()


def test_a_command_that_does_not_exist_is_a_transport_error() -> None:
    client = McpClient("stdio:nada", None, command=("/no/existe/puente",))
    with pytest.raises(McpTransportError, match="no se pudo lanzar"):
        client.initialize()


# --- Modo informe -----------------------------------------------------------------------------


def test_the_report_records_every_failure_and_does_not_abort(tmp_path: Path) -> None:
    report = tmp_path / "informe.md"
    failures = "vigia.query_metric=invalid;vigia.top_n=down"
    with run_mock({"MCP_MOCK_FAILURES": failures}) as broken:
        run = run_battery(report, CARMEN_MCP_TARGETS=f"vigia={broken.url('vigia')}")
    assert run.returncode == 1, run.stdout[-2000:]
    text = report.read_text(encoding="utf-8")
    for _, title in SECTIONS:
        assert title in text
    assert (
        "| `test_mcp_contract.py::test_every_tool_answers_with_a_valid_envelope[vigia]` | failed"
        in text
    )
    assert "query_metric" in text
    assert "top_n" in text
    # lo que viene después del fallo se ejecutó igual
    assert "test_a_request_without_a_token_is_refused[vigia]` | passed" in text
    assert "test_the_catalog_covers_the_golden_set[vigia]` | passed" in text
    assert "Anexo: catálogo observado de vigia" in text


def test_the_battery_passes_over_stdio_and_never_shows_the_token(
    mock: MockServer, tmp_path: Path
) -> None:
    report = tmp_path / "informe.md"
    run = run_battery(report, CARMEN_MCP_TARGETS=stdio_target(mock), MCP_BRIDGE_TOKEN=BRIDGE_TOKEN)
    assert run.returncode == 0, run.stdout[-3000:]
    text = report.read_text(encoding="utf-8")
    assert "`vigia` por stdio" in text
    assert "Todas las comprobaciones pasan." in text
    assert "puente obtiene y renueva el token" in text
    for output in (text, run.stdout, run.stderr):
        assert BRIDGE_TOKEN not in output


def test_an_http_token_is_struck_out_of_the_report() -> None:
    findings = Findings(generated_at="2026-10-31T12:00:00Z", profile="mock")
    findings.outcomes.append(Outcome("x::y", "failed", f"HTTP 401: token {ADMIN_TOKEN} rechazado"))
    findings.note("identidad", f"- se usó {ADMIN_TOKEN}")
    text = render(findings, secrets=[ADMIN_TOKEN])
    assert ADMIN_TOKEN not in text
    assert "«credencial tachada»" in text


def test_an_unknown_section_is_a_programming_error() -> None:
    findings = Findings(generated_at="2026-10-31T12:00:00Z", profile="mock")
    with pytest.raises(ValueError, match="sección"):
        findings.note("otra", "x")


# --- Perfil vigia-real ------------------------------------------------------------------------


def certificates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("VIGIA_MCP_CERT", "VIGIA_MCP_KEY", "VIGIA_MCP_CA"):
        path = tmp_path / f"{name.lower()}.pem"
        path.write_text("no es un certificado: solo se comprueba que exista\n", encoding="utf-8")
        monkeypatch.setenv(name, str(path))


def test_vigia_real_only_exists_in_the_dev_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CARMEN_PROFILE", raising=False)
    with pytest.raises(pytest.UsageError, match="CARMEN_PROFILE=dev"):
        vigia_real_endpoint()


def test_vigia_real_needs_the_client_certificate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CARMEN_PROFILE", "dev")
    certificates(tmp_path, monkeypatch)
    monkeypatch.setenv("VIGIA_MCP_KEY", str(tmp_path / "no-esta.pem"))
    with pytest.raises(pytest.UsageError, match="VIGIA_MCP_KEY") as raised:
        vigia_real_endpoint()
    assert "VIGIA_MCP_CERT" not in str(raised.value)


def test_vigia_real_needs_the_bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARMEN_PROFILE", "dev")
    certificates(tmp_path, monkeypatch)
    monkeypatch.setenv("CARMEN_VIGIA_BRIDGE", f"node {tmp_path / 'vigia-mcp-bridge.mjs'}")
    with pytest.raises(pytest.UsageError, match="no existe el puente"):
        vigia_real_endpoint()


def test_vigia_real_launches_the_bridge_by_stdio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CARMEN_PROFILE", "dev")
    certificates(tmp_path, monkeypatch)
    script = tmp_path / "bin" / "vigia-mcp-bridge.mjs"
    script.parent.mkdir()
    script.write_text("// puente de prueba\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CARMEN_VIGIA_BRIDGE", raising=False)
    endpoint = vigia_real_endpoint()
    assert endpoint.command == ("node", str(script))


def test_ci_never_selects_the_real_server() -> None:
    workflows = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / ".github" / "workflows").glob("*.y*ml")
    )
    assert "vigia-real" not in workflows
    assert "CARMEN_CONTRACT_TARGET" not in workflows
