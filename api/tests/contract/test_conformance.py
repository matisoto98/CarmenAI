"""Prompt 10: diagnóstico de conformidad de un servidor MCP frente a 6.4, 7.8.1 y 5.16.1.1.

La batería del Prompt 9 dice si un servidor cumple; estas pruebas dicen además en qué se separa,
para que el informe (`--report`) responda a lo que pide el Prompt 10:
  - forma del sobre y diferencias con 6.4;
  - si devuelve hechos identificables con procedencia;
  - si declara period_interpreted;
  - qué identidad ve el servidor y cómo niega lo que no corresponde (7.8.1);
  - qué herramientas hay y cuáles faltan para el golden set;
  - si siguen valiendo las reglas de interpretación de 5.16.1.1.

Cada herramienta se llama una sola vez por sesión con argumentos de ejemplo; el resto de pruebas
reutiliza esas llamadas. Contra el simulado todo pasa; contra VigIA real cada diferencia queda
anotada en su sección del informe y, si rompe el contrato, como fallo.
"""

import json
import os
import ssl
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pytest
import yaml
from jsonschema import Draft202012Validator

from contract.conftest import PROFILE_VIGIA_REAL, ROOT, Target, profile
from contract.envelope_checks import CORRELATION, ROLES, example_arguments, schema_errors
from contract.mcp_client import (
    Json,
    McpClient,
    McpError,
    McpHttpError,
    McpRpcError,
    McpTransportError,
    ToolResult,
    as_list,
    as_object,
)
from contract.report import Findings, Sample

pytestmark = pytest.mark.contract

ENVELOPE_SCHEMA: Final = json.loads(
    (ROOT / "contracts" / "mcp-envelope.schema.json").read_text(encoding="utf-8")
)
ENVELOPE_REQUIRED: Final = frozenset(ENVELOPE_SCHEMA["required"])
ENVELOPE_KEYS: Final = frozenset(ENVELOPE_SCHEMA["properties"])
PROVENANCE: Final = ("system_id", "call_id", "generated_at", "catalog_version")
PERIOD_PARAMS: Final = ("period", "periodo")
PERIOD_FIELDS: Final = ("expression", "from", "to", "text")
GOLDEN: Final = ROOT / "eval" / "golden"
FIXTURES: Final = ROOT / "eval" / "fixtures"
GUIDE: Final = "guía «Conectarse al MCP de Vigía», 7-oct-2026"
VIGIA_URL_DEFAULT: Final = "https://vigia.plenergy.local:8443/mcp"
PERIODS: Final = ("ahora", "hoy", "7d", "30d", "90d", "mes_actual", "mes_anterior")
OPEN_ALARMS_GUIDE: Final = 4000
DEGRADED_GUIDE: Final = 158
CARWASHES_GUIDE: Final = (72.0, 65.0)
PRINTER_SHARE: Final = (0.25, 0.42)
ROW_CAP: Final = 500
UNAUTHORIZED: Final = 401
FORBIDDEN: Final = 403


# --- Llamadas de ejemplo, una por herramienta y sesión ----------------------------------------


def observe(target: Target, findings: Findings) -> list[Sample]:
    """Catálogo y una llamada por herramienta; la primera prueba que lo pide lo guarda."""
    if target.system_id in findings.samples:
        return findings.samples[target.system_id]
    client = target.client()
    try:
        info = client.initialize()
        tools = client.list_tools()
        findings.server_info[target.system_id] = info
        findings.catalogs[target.system_id] = tools
        samples = [_sample(client, tool) for tool in tools]
    finally:
        client.close()
    findings.samples[target.system_id] = samples
    server = as_object(info.get("serverInfo", {}))
    findings.note(
        "destino",
        f"- `{target.system_id}` por {target.transport}: servidor `{server.get('name')}` "
        f"versión `{server.get('version')}`, protocolo `{info.get('protocolVersion')}`, "
        f"{len(tools)} herramientas.",
    )
    return samples


def _sample(client: McpClient, tool: dict[str, Json]) -> Sample:
    arguments = example_arguments(tool)
    try:
        result = client.call_tool(str(tool["name"]), arguments, correlation_id=CORRELATION)
    except McpError as error:
        return Sample(tool, arguments, None, str(error))
    return Sample(tool, arguments, result, None)


def _shape(value: Json) -> str:
    if isinstance(value, dict):
        return "objeto"
    if isinstance(value, list):
        return f"lista[{len(value)}]"
    if isinstance(value, bool):
        return "booleano"
    if isinstance(value, (int, float)):
        return "número"
    return "nulo" if value is None else "texto"


def properties_of(tool: dict[str, Json]) -> dict[str, Json]:
    return as_object(as_object(tool.get("inputSchema", {})).get("properties", {}))


# --- Forma del sobre --------------------------------------------------------------------------


def test_every_tool_answers_with_a_json_envelope(target: Target, findings: Findings) -> None:
    """Lo mínimo para que exista un adaptador: un objeto JSON por llamada, no texto libre."""
    unusable = []
    for sample in observe(target, findings):
        if sample.error is not None:
            findings.note(
                "sobre", f"- `{target.system_id}.{sample.name}`: la llamada falló: {sample.error}"
            )
            unusable.append(f"{sample.name}: {sample.error}")
            continue
        assert sample.result is not None
        envelope = sample.result.envelope
        if envelope is None:
            findings.note(
                "sobre",
                f"- `{target.system_id}.{sample.name}`: no hay sobre; ni structuredContent ni "
                "texto JSON "
                f"(empieza por {sample.result.text[:80]!r}).",
            )
            unusable.append(f"{sample.name}: sin sobre JSON")
            continue
        where = "structuredContent" if sample.result.structured else "texto JSON"
        keys = set(envelope)
        missing = sorted(ENVELOPE_REQUIRED - keys)
        extra = sorted(keys - ENVELOPE_KEYS)
        errors = schema_errors(envelope)
        shape = ", ".join(f"{key}: {_shape(envelope[key])}" for key in sorted(keys))
        verdict = "conforme a 6.4" if not errors else f"{len(errors)} errores de esquema"
        findings.note(
            "sobre",
            f"- `{target.system_id}.{sample.name}` ({where}, {verdict}). Claves: {shape}."
            + (f" Faltan: {', '.join(missing)}." if missing else "")
            + (f" Sobran: {', '.join(extra)}." if extra else "")
            + (f" Primeros errores: {'; '.join(errors[:3])}." if errors else ""),
        )
        if sample.result.is_error:
            unusable.append(f"{sample.name}: isError con los argumentos de ejemplo")
    assert not unusable, "\n".join(unusable)


# --- Hechos y procedencia ---------------------------------------------------------------------


def fact_problems(envelope: dict[str, Json]) -> list[str]:
    problems = [f"sin {key}" for key in PROVENANCE if not envelope.get(key)]
    facts = envelope.get("facts")
    if not isinstance(facts, list):
        return [*problems, "no devuelve facts"]
    keys = [as_object(f).get("key") for f in facts if isinstance(f, dict)]
    if len(keys) != len(facts) or not all(isinstance(k, str) and k for k in keys):
        problems.append("hay hechos sin key")
    elif len(set(keys)) != len(keys):
        problems.append("hay hechos con la misma key: no se pueden citar uno a uno")
    for fact in (as_object(f) for f in facts if isinstance(f, dict)):
        if isinstance(fact.get("value"), (int, float)) and not fact.get("unit"):
            problems.append(f"el hecho {fact.get('key')} es numérico y no lleva unidad")
    passages = envelope.get("passages")
    for passage in (
        (as_object(p) for p in passages if isinstance(p, dict))
        if isinstance(passages, list)
        else ()
    ):
        if not passage.get("doc_version") or not passage.get("updated_at"):
            problems.append(f"el pasaje {passage.get('passage_id')} no lleva versión y fecha")
    return problems


def test_facts_are_identifiable_and_carry_provenance(target: Target, findings: Findings) -> None:
    problems: list[str] = []
    for sample in observe(target, findings):
        envelope = None if sample.result is None else sample.result.envelope
        if envelope is None:
            findings.note(
                "hechos", f"- `{target.system_id}.{sample.name}`: no hay sobre que examinar."
            )
            continue
        found = fact_problems(envelope)
        facts = envelope.get("facts")
        count = len(facts) if isinstance(facts, list) else 0
        entities = (
            sum(1 for f in facts if isinstance(f, dict) and f.get("entity"))
            if isinstance(facts, list)
            else 0
        )
        summary = f"{count} hechos, {entities} con entidad"
        if found:
            findings.note(
                "hechos", f"- `{target.system_id}.{sample.name}`: {summary}; {'; '.join(found)}."
            )
            problems.extend(f"{sample.name}: {p}" for p in found)
        else:
            findings.note(
                "hechos",
                f"- `{target.system_id}.{sample.name}`: {summary}; cada hecho se cita por su key "
                "y el "
                "sobre lleva sistema, llamada, instante y versión de catálogo.",
            )
    assert not problems, "\n".join(problems)


# --- Periodo interpretado ---------------------------------------------------------------------


def test_tools_with_a_period_declare_how_they_read_it(target: Target, findings: Findings) -> None:
    problems = []
    with_period = [
        s for s in observe(target, findings) if set(properties_of(s.tool)) & set(PERIOD_PARAMS)
    ]
    if not with_period:
        findings.note(
            "periodo", f"- `{target.system_id}`: ninguna herramienta tiene parámetro de periodo."
        )
    for sample in with_period:
        envelope = None if sample.result is None else sample.result.envelope
        if envelope is None:
            problems.append(f"{sample.name}: sin sobre, no se puede comprobar")
            continue
        declared = envelope.get("period_interpreted")
        if not isinstance(declared, dict):
            findings.note(
                "periodo", f"- `{target.system_id}.{sample.name}`: NO declara period_interpreted."
            )
            problems.append(f"{sample.name}: no declara period_interpreted")
            continue
        lacking = [name for name in PERIOD_FIELDS if not declared.get(name)]
        if lacking:
            problems.append(f"{sample.name}: period_interpreted sin {', '.join(lacking)}")
        findings.note(
            "periodo",
            f"- `{target.system_id}.{sample.name}` con "
            f"{json.dumps(sample.arguments, ensure_ascii=False)}: "
            f"declara {json.dumps(declared, ensure_ascii=False)}"
            + (f"; le falta {', '.join(lacking)}." if lacking else "."),
        )
    assert not problems, "\n".join(problems)


# --- Identidad --------------------------------------------------------------------------------


def fixture_catalog(system_id: str) -> list[dict[str, Json]]:
    path = FIXTURES / f"catalog_{system_id}.json"
    if not path.is_file():
        return []
    return [as_object(t) for t in json.loads(path.read_text(encoding="utf-8"))["tools"]]


def refusal(client: McpClient, name: str, arguments: dict[str, Json]) -> str | None:
    """Cómo se niega una llamada; None si la contestó."""
    try:
        result = client.call_tool(name, arguments)
    except McpHttpError as error:
        return f"HTTP {error.status}"
    except McpRpcError as error:
        return f"error JSON-RPC {error.code} ({error.message[:120]})"
    except McpTransportError as error:
        return f"fallo de transporte ({error})"
    return f"isError ({result.text[:120]})" if result.is_error else None


def test_the_server_applies_the_user_access_control(target: Target, findings: Findings) -> None:
    """7.8.1 y 7.11.3: lo que el usuario no puede usar no se lista y, si se pide, se niega."""
    listed = {s.name: s.tool for s in observe(target, findings)}
    declared_roles = [str(t.get("name")) for t in listed.values() if t.get("roles")]
    findings.note(
        "identidad",
        f"- `{target.system_id}`: {len(declared_roles)} de {len(listed)} herramientas publican "
        "sus roles (6.9.4)."
        if declared_roles
        else f"- `{target.system_id}`: ninguna herramienta publica roles; el catálogo no dice "
        "quién puede usar qué.",
    )
    hidden = [t for t in fixture_catalog(target.system_id) if str(t["name"]) not in listed]
    answered = []
    if not hidden:
        findings.note(
            "identidad",
            f"- `{target.system_id}`: la identidad usada ve todas las herramientas del catálogo "
            "de fixtures.",
        )
    client = target.client()
    client.initialize()
    try:
        for tool in hidden:
            name = str(tool["name"])
            roles = ", ".join(map(str, as_list(tool.get("roles", []))))
            how = refusal(client, name, example_arguments({"inputSchema": tool["input_schema"]}))
            if how is None:
                answered.append(name)
            findings.note(
                "identidad",
                f"- `{target.system_id}.{name}` (roles {roles}) no se lista para esta identidad "
                "y, pedida, "
                + (f"se niega con {how}." if how else "SE CONTESTA: fuga de control de acceso."),
            )
    finally:
        client.close()
    if target.command is not None:
        findings.note(
            "identidad",
            "- La audiencia y el scope del token de Entra no los puede medir la batería: el "
            "puente obtiene y renueva el token y nunca lo entrega. Se leen de la configuración "
            'del puente, sin tocar el token: `grep -nE "scope|audience|api://|clientId|'
            'client_id|tenant|authority" ~/bin/vigia-mcp-bridge.mjs`.',
        )
    assert not answered, f"herramientas no listadas que se contestan: {', '.join(answered)}"


def certificate_file(variable: str) -> str:
    return str(Path(os.environ[variable]).expanduser())


def tls_context(*, with_certificate: bool) -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=certificate_file("VIGIA_MCP_CA"))
    if with_certificate:
        context.load_cert_chain(
            certificate_file("VIGIA_MCP_CERT"),
            certificate_file("VIGIA_MCP_KEY"),
            password=lambda: "",  # una clave cifrada falla aquí en vez de pedir la frase
        )
    return context


def attempt(url: str, context: ssl.SSLContext) -> tuple[str, str]:
    """Un initialize sin token: (contesta | http | tls | red, detalle)."""
    try:
        McpClient(url, None, ssl_context=context).initialize()
    except McpHttpError as error:
        return "http", f"HTTP {error.status}"
    except McpTransportError as error:
        cause = error.__cause__
        reason = getattr(cause, "reason", cause)
        refused_tls = isinstance(reason, (ssl.SSLError, ConnectionResetError))
        return ("tls" if refused_tls else "red"), str(error)
    except McpError as error:
        return "http", str(error)
    return "contesta", "contesta"


def test_the_real_server_demands_certificate_and_token(findings: Findings) -> None:
    """7.11.3 Seguridad: TLS mutuo y token del usuario. Solo contra VigIA real, sin el puente."""
    if profile() != PROFILE_VIGIA_REAL:
        pytest.skip("solo con CARMEN_CONTRACT_TARGET=vigia-real: el simulado no tiene TLS")
    url = os.environ.get("CARMEN_VIGIA_URL", VIGIA_URL_DEFAULT)
    accepted: list[str] = []
    for with_certificate, case in (
        (False, "sin certificado de cliente"),
        (True, "con certificado y sin token"),
    ):
        try:
            context = tls_context(with_certificate=with_certificate)
        except (ssl.SSLError, OSError) as error:
            findings.note(
                "identidad", f"- {url}, {case}: no se probó, el TLS local no carga ({error})."
            )
            continue
        kind, detail = attempt(url, context)
        if kind == "red":
            findings.note(
                "identidad", f"- {url}, {case}: no se llegó al servidor ({detail}); no comprobable."
            )
            continue
        # sin certificado, solo cortar el TLS es correcto; con certificado, pedir el token
        refused = kind == "tls" or (
            with_certificate and detail in (f"HTTP {UNAUTHORIZED}", f"HTTP {FORBIDDEN}")
        )
        findings.note(
            "identidad",
            f"- {url}, {case}: "
            + ({"tls": "corta el TLS", "http": "responde", "contesta": "CONTESTA"}[kind])
            + (f" ({detail})." if kind != "contesta" else ": acepta la petición."),
        )
        if not refused:
            accepted.append(case)
    assert not accepted, f"{url} acepta peticiones {' y '.join(accepted)}"


# --- Catálogo frente al golden set ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Requirement:
    """Lo que un caso del golden set necesita del catálogo: una herramienta o un valor."""

    case_id: str
    tool: str
    param: str | None
    value: Json
    pending: tuple[str, ...]


def golden_requirements(system_id: str) -> Iterator[Requirement]:
    for path in sorted(GOLDEN.rglob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for case in data.get("casos", []):
            plan = case.get("plan_esperado") or {}
            if system_id not in (plan.get("systems") or []):
                continue
            pending = tuple(str(p) for p in case.get("depende_de") or ())
            for tool in plan.get("steps_min") or []:
                yield Requirement(case["id"], str(tool), None, None, pending)
            for dotted, value in (plan.get("argumentos") or {}).items():
                tool, _, param = str(dotted).partition(".")
                yield Requirement(case["id"], tool, param, value, pending)


def gap(requirement: Requirement, tools: dict[str, dict[str, Json]]) -> str | None:
    tool = tools.get(requirement.tool)
    if tool is None:
        return f"falta la herramienta `{requirement.tool}`"
    if requirement.param is None:
        return None
    schema = properties_of(tool).get(requirement.param)
    if not isinstance(schema, dict):
        return f"`{requirement.tool}` no tiene el parámetro `{requirement.param}`"
    if list(Draft202012Validator(schema).iter_errors(requirement.value)):
        return f"`{requirement.tool}.{requirement.param}` no admite {requirement.value!r}"
    return None


def test_the_catalog_covers_the_golden_set(target: Target, findings: Findings) -> None:
    tools = {s.name: s.tool for s in observe(target, findings)}
    known = {str(t["name"]) for t in fixture_catalog(target.system_id)}
    if known:
        absent, new = sorted(known - set(tools)), sorted(set(tools) - known)
        findings.note(
            "catalogo",
            f"- `{target.system_id}` frente a eval/fixtures/catalog_{target.system_id}.json: "
            + (f"no están {', '.join(absent)}" if absent else "están todas las herramientas")
            + (f"; nuevas: {', '.join(new)}." if new else "; ninguna nueva."),
        )
    blocking: dict[str, list[str]] = {}
    pending: dict[str, list[str]] = {}
    restricted = {
        str(t["name"]): ", ".join(map(str, as_list(t.get("roles", []))))
        for t in fixture_catalog(target.system_id)
        if set(map(str, as_list(t.get("roles", [])))) != ROLES
    }
    for requirement in golden_requirements(target.system_id):
        found = gap(requirement, tools)
        if found is None:
            continue
        hidden = requirement.tool not in tools and requirement.tool in restricted
        bucket = pending if requirement.pending or hidden else blocking
        label = requirement.case_id + (
            f" (depende de {', '.join(requirement.pending)})" if requirement.pending else ""
        )
        if hidden:
            found = (
                f"`{requirement.tool}` no es visible para esta identidad (roles "
                f"{restricted[requirement.tool]})"
            )
        cases = bucket.setdefault(found, [])
        if label not in cases:
            cases.append(label)
    for found, cases in blocking.items():
        findings.note(
            "catalogo", f"- `{target.system_id}`: {found}; lo necesitan {', '.join(cases)}."
        )
    for found, cases in pending.items():
        findings.note(
            "catalogo",
            f"- `{target.system_id}`, pendiente: {found}; lo necesitan {', '.join(cases)}.",
        )
    if not blocking and not pending:
        findings.note(
            "catalogo", f"- `{target.system_id}`: el catálogo cubre todo lo que pide el golden set."
        )
    assert not blocking, "\n".join(f"{g}: {', '.join(c)}" for g, c in blocking.items())


# --- Reglas de interpretación de 5.16.1.1 -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class Rule:
    rule: str
    guide: str
    observed: str
    status: str  # coincide, cambió o no comprobable
    blocking: bool = False


class Prober:
    """Llamadas de comprobación sobre el catálogo observado; lo que no existe no se inventa."""

    def __init__(self, client: McpClient, tools: dict[str, dict[str, Json]]) -> None:
        self.client = client
        self.tools = tools

    def call(self, name: str, arguments: dict[str, Json]) -> tuple[ToolResult | None, str]:
        tool = self.tools.get(name)
        if tool is None:
            return None, f"falta la herramienta {name}"
        schema = as_object(tool.get("inputSchema", {}))
        if list(Draft202012Validator(schema).iter_errors(arguments)):
            return None, f"{name} no admite {json.dumps(arguments, ensure_ascii=False)}"
        try:
            return self.client.call_tool(name, arguments), ""
        except McpError as error:
            return None, str(error)

    def number(self, name: str, arguments: dict[str, Json]) -> tuple[float | None, str]:
        result, why = self.call(name, arguments)
        if result is None or result.envelope is None or result.is_error:
            return None, why or "sin sobre"
        for fact in as_list(result.envelope.get("facts", [])):
            value = as_object(fact).get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value), ""
        return None, "ningún hecho numérico"


def near(observed: float, expected: float, tolerance: float = 0.25) -> bool:
    return abs(observed - expected) <= tolerance * expected


def server_month(samples: list[Sample]) -> datetime:
    for sample in samples:
        envelope = None if sample.result is None else sample.result.envelope
        stamp = None if envelope is None else envelope.get("generated_at")
        if isinstance(stamp, str):
            return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return datetime.now(UTC)


def months_before(moment: datetime, months: int) -> str:
    index = moment.year * 12 + moment.month - 1 - months
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def rule_periods(prober: Prober, now: datetime) -> Rule:
    guide = "ahora, hoy, 7/30/90 días, mes actual, mes anterior o un mes; tope de 400 días"
    if "query_metric" not in prober.tools:
        return Rule("Periodos y tope de 400 días", guide, "falta query_metric", "no comprobable")
    refused = []
    for period in (*PERIODS, months_before(now, 1)):
        result, _ = prober.call("query_metric", {"metric": "alarmas", "period": period})
        if result is None or result.is_error:
            refused.append(period)
    too_old = months_before(now, 14)
    old, _ = prober.call("query_metric", {"metric": "alarmas", "period": too_old})
    old_answered = old is not None and not old.is_error and not (old.envelope or {}).get("warnings")
    observed = (
        ("admite todos" if not refused else f"rechaza {', '.join(refused)}")
        + f"; {too_old} (más de 400 días) "
        + ("se contesta sin aviso" if old_answered else "se rechaza o avisa")
    )
    changed = bool(refused) or old_answered
    return Rule(
        "Periodos y tope de 400 días",
        guide,
        observed,
        "cambió" if changed else "coincide",
        blocking=changed,
    )


def rule_open_alarms(prober: Prober) -> Rule:
    result, why = prober.call("query_metric", {"metric": "alarmas_abiertas", "period": "ahora"})
    guide = "más de 4.000 abiertas, unas 3.700 de dos códigos de Alvic que nunca se cierran"
    if result is None or result.envelope is None:
        return Rule("«Alarmas abiertas» no es carga de trabajo", guide, why, "no comprobable")
    value, _ = prober.number("query_metric", {"metric": "alarmas_abiertas", "period": "ahora"})
    warnings = [str(as_object(w).get("code")) for w in as_list(result.envelope.get("warnings", []))]
    observed = (f"{value:.0f} abiertas" if value is not None else "sin cifra") + (
        f"; el servidor avisa ({', '.join(warnings)})" if warnings else "; el servidor no avisa"
    )
    holds = value is not None and value > OPEN_ALARMS_GUIDE
    return Rule(
        "«Alarmas abiertas» no es carga de trabajo",
        guide,
        observed,
        "coincide" if holds else "cambió",
    )


def rule_printers(prober: Prober) -> Rule:
    guide = "«Error de impresora» es en torno a un tercio de todas las alarmas"
    total, why = prober.number("query_metric", {"metric": "alarmas", "period": "30d"})
    ranking, why_ranking = prober.call(
        "top_n", {"metric": "alarmas", "group_by": "tipo_alarma", "period": "30d", "limit": 10}
    )
    if total is None or ranking is None or ranking.envelope is None:
        return Rule(
            "Rankings dominados por impresoras", guide, why or why_ranking, "no comprobable"
        )
    printers = next(
        (
            float(value)
            for fact in as_list(ranking.envelope.get("facts", []))
            if "impresora" in json.dumps(fact, ensure_ascii=False).lower()
            and isinstance(value := as_object(fact).get("value"), (int, float))
        ),
        None,
    )
    if printers is None or not total:
        return Rule("Rankings dominados por impresoras", guide, "el ranking no la nombra", "cambió")
    share = printers / total
    return Rule(
        "Rankings dominados por impresoras",
        guide,
        f"{share:.0%} de las alarmas de 30 días",
        "coincide" if PRINTER_SHARE[0] <= share <= PRINTER_SHARE[1] else "cambió",
    )


def rule_degraded(prober: Prober) -> Rule:
    guide = "un tercio de la red sale degradada: unas 158 de 412 sedes"
    value, why = prober.number("query_metric", {"metric": "sedes_degradadas", "period": "ahora"})
    if value is None:
        return Rule("Sedes degradadas infladas", guide, why, "no comprobable")
    return Rule(
        "Sedes degradadas infladas",
        guide,
        f"{value:.0f} sedes degradadas",
        "coincide" if near(value, DEGRADED_GUIDE) else "cambió",
    )


def rule_carwashes(prober: Prober) -> Rule:
    guide = "72 es el universo; 65 es «Lavaderos OK» (sin avería abierta)"
    universe, why = prober.number("query_metric", {"metric": "lavaderos", "period": "ahora"})
    healthy, why_ok = prober.number("query_metric", {"metric": "lavaderos_ok", "period": "ahora"})
    if universe is None or healthy is None:
        return Rule("Lavaderos: dos definiciones", guide, why or why_ok, "no comprobable")
    two_definitions = healthy <= universe
    same = (universe, healthy) == CARWASHES_GUIDE
    return Rule(
        "Lavaderos: dos definiciones",
        guide,
        f"universo {universe:.0f}, OK {healthy:.0f}",
        "coincide" if two_definitions and same else "cambió",
        blocking=not two_definitions,
    )


def rule_admin(prober: Prober) -> Rule:
    guide = "sin rol ADMIN falta correlate_events y la correlación da error de permisos"
    if "correlate_events" in prober.tools:
        return Rule(
            "correlate_events solo con ADMIN",
            guide,
            "la identidad usada la ve: tiene ADMIN; sin ADMIN no se puede comprobar con ella",
            "no comprobable",
        )
    how = refusal(prober.client, "correlate_events", {"site_id": "1", "window": "7d"})
    return Rule(
        "correlate_events solo con ADMIN",
        guide,
        "no se lista; pedida, " + (f"se niega con {how}" if how else "SE CONTESTA"),
        "coincide" if how else "cambió",
        blocking=how is None,
    )


def rule_unrecorded(prober: Prober) -> Rule:
    guide = "no hay dato de falsos positivos; el MTTR solo cubre proveedores con SLA"
    text = json.dumps(list(prober.tools.values()), ensure_ascii=False).lower()
    offered = [word for word in ("falso", "false_positive", "mttr") if word in text]
    return Rule(
        "Lo que no se registra",
        guide,
        f"el catálogo ahora menciona {', '.join(offered)}"
        if offered
        else "ninguna herramienta lo ofrece",
        "cambió" if offered else "coincide",
    )


def rule_families(prober: Prober) -> Rule:
    guide = "SAI, CCTV o alumbrado son familias de varios códigos, no valores filtrables"
    values = {
        str(v).lower()
        for tool in prober.tools.values()
        for prop in properties_of(tool).values()
        if isinstance(prop, dict)
        for v in as_list(prop.get("enum", []))
    }
    filterable = sorted(v for v in values if v in {"sai", "cctv", "alumbrado"})
    return Rule(
        "Familias de códigos",
        guide,
        f"ahora son filtrables: {', '.join(filterable)}"
        if filterable
        else "no son valores de ningún parámetro",
        "cambió" if filterable else "coincide",
    )


def rule_row_cap(samples: list[Sample]) -> Rule:
    guide = "respuestas recortadas a 500 filas; consultas pesadas rechazadas con aviso"
    envelopes = [s.result.envelope for s in samples if s.result and s.result.envelope]
    over = [e for e in envelopes if len(as_list(e.get("rows", []))) > ROW_CAP]
    silent = [e for e in envelopes if e.get("partial") is True and not e.get("warnings")]
    if over or silent:
        return Rule(
            "Recorte a 500 filas",
            guide,
            f"{len(over)} sobres con más de 500 filas, {len(silent)} parciales sin aviso",
            "cambió",
            blocking=True,
        )
    return Rule(
        "Recorte a 500 filas",
        guide,
        "ninguna llamada de ejemplo lo supera; ninguna parcial sin aviso",
        "coincide",
    )


UNPROBEABLE: Final = (
    (
        "El MCP cuenta toda la red",
        "el informe de Dirección excluye lavaderos, impresoras, ruido y la estación de pruebas",
        "no hay en el MCP una cifra de Dirección con la que contrastar",
    ),
    (
        "SAI y CCTV desde el 2-sep-2026",
        "antes de esa fecha no contaban como alarmas",
        "el catálogo no permite filtrar por código para ver el salto",
    ),
)


def test_the_interpretation_rules_still_hold(target: Target, findings: Findings) -> None:
    if target.system_id != "vigia":
        pytest.skip("las reglas de 5.16.1.1 son de VigIA")
    samples = observe(target, findings)
    client = target.client()
    client.initialize()
    probes: list[Callable[[Prober], Rule]] = [
        lambda p: rule_periods(p, server_month(samples)),
        rule_open_alarms,
        rule_printers,
        rule_degraded,
        rule_carwashes,
        rule_admin,
        rule_unrecorded,
        rule_families,
    ]
    try:
        prober = Prober(client, {s.name: s.tool for s in samples})
        rules = [probe(prober) for probe in probes]
    finally:
        client.close()
    rules.append(rule_row_cap(samples))
    rules.extend(Rule(name, guide, why, "no comprobable") for name, guide, why in UNPROBEABLE)
    findings.note("reglas", f"Contraste con la {GUIDE}. Las cifras caducan; los avisos no.")
    findings.note("reglas", "")
    findings.note("reglas", "| Regla | Guía | Observado | Estado |")
    findings.note("reglas", "|---|---|---|---|")
    for rule in rules:
        findings.note(
            "reglas",
            f"| {rule.rule} | {rule.guide} | {rule.observed.replace('|', '/')} | {rule.status} |",
        )
    broken = [f"{r.rule}: {r.observed}" for r in rules if r.blocking]
    assert not broken, "\n".join(broken)
