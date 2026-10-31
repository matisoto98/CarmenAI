"""Prompt 1: las reglas de importación de la sección 5.3 las verifica una prueba, no la disciplina.

El análisis recorre el árbol sintáctico de cada módulo (no expresiones regulares sobre el texto),
construye el grafo de imports internos y comprueba cada regla. Las del supervisor y las del agente
son TRANSITIVAS: un paquete no puede llegar a un módulo prohibido ni a través de otro módulo.
Importar un módulo ejecuta los __init__ de sus paquetes padre, así que esos también son aristas.
"""

import ast
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
ROOT_PACKAGE = "carmen"

# --- Única declaración de paquetes del supervisor y del agente (5.3, 5.14.5, 5.14.6) ---

SUPERVISOR_PACKAGES = (
    "application.orchestrator",
    "application.routing",
    "application.direct",
    "application.delegation",
    "application.join",
    "application.narration",
    "application.grounding",
    "application.policy",
    "application.approval",
    "application.budgets",
)
SUPERVISOR_FORBIDDEN = (
    "application.ports.mcp",
    "application.ports.identity",
    "application.ports.egress",
    "application.ports.model_provider",
    "application.planning",
    "application.execution",
)
AGENT_PACKAGES = (
    "application.agents.executor",
    "application.planning",
    "application.execution",
)
AGENT_FORBIDDEN = ("application.ports.agents",)

# Lo único de application/ que ve un adaptador: los puertos y el vocabulario de sus firmas
# (quién pregunta, los errores que el puerto declara y los valores JSON). Nunca un caso de uso.
ADAPTER_APPLICATION_VOCABULARY = (
    "application.ports",
    "application.context",
    "application.errors",
    "application.jsontypes",
)

# El dominio no conoce frameworks ni protocolos (5.3).
DOMAIN_FORBIDDEN_THIRD_PARTY = (
    "fastapi",
    "starlette",
    "uvicorn",
    "sqlalchemy",
    "asyncpg",
    "psycopg",
    "psycopg2",
    "httpx",
    "requests",
    "aiohttp",
    "urllib3",
    "ollama",
    "openai",
    "anthropic",
    "mcp",
)


@dataclass(frozen=True)
class Violation:
    rule: str
    module: str
    path: Path
    detail: str

    def __str__(self) -> str:
        return f"{self.path}: [{self.rule}] {self.module} -> {self.detail}"


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    path: Path
    internal: frozenset[str]
    external: frozenset[str]


def _module_name(path: Path, src_root: Path) -> str:
    parts = list(path.relative_to(src_root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_relative(module: str, is_package: bool, level: int, target: str | None) -> str:
    base = module.split(".")
    if not is_package:
        base = base[:-1]
    if level > 1:
        base = base[: len(base) - (level - 1)]
    return ".".join([*base, target] if target else base)


def _with_parents(name: str, root: str) -> set[str]:
    parts = name.split(".")
    return {".".join(parts[:i]) for i in range(1, len(parts) + 1) if parts[0] == root}


def collect_modules(src_root: Path, root: str = ROOT_PACKAGE) -> dict[str, ModuleInfo]:
    """Recorre src_root/root y devuelve cada módulo con sus imports internos y externos."""
    files = sorted((src_root / root).rglob("*.py"))
    names = {_module_name(f, src_root) for f in files}
    modules: dict[str, ModuleInfo] = {}
    for file in files:
        name = _module_name(file, src_root)
        is_package = file.name == "__init__.py"
        tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        internal: set[str] = set()
        external: set[str] = set()
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = (
                    _resolve_relative(name, is_package, node.level, node.module)
                    if node.level
                    else node.module or ""
                )
                targets = [base]
                targets += [f"{base}.{a.name}" for a in node.names if f"{base}.{a.name}" in names]
            for target in targets:
                if target.split(".")[0] == root:
                    internal |= {t for t in _with_parents(target, root) if t in names}
                elif target:
                    external.add(target.split(".")[0])
        internal.discard(name)
        modules[name] = ModuleInfo(name, file, frozenset(internal), frozenset(external))
    return modules


def _in(module: str, package: str) -> bool:
    return module == package or module.startswith(f"{package}.")


def _path_to(
    modules: dict[str, ModuleInfo], start: str, forbidden: Callable[[str], bool]
) -> list[str] | None:
    """Camino más corto de start a un módulo prohibido, o None si no lo alcanza."""
    previous: dict[str, str | None] = {start: None}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for target in sorted(modules[current].internal):
            if target in previous:
                continue
            previous[target] = current
            if forbidden(target):
                chain = [target]
                step: str | None = current
                while step is not None:
                    chain.append(step)
                    step = previous[step]
                return list(reversed(chain))
            queue.append(target)
    return None


def check_layer_rules(src_root: Path, root: str = ROOT_PACKAGE) -> list[Violation]:
    """Aplica las reglas de 5.3 al árbol bajo src_root/root."""
    modules = collect_modules(src_root, root)

    def pkg(suffix: str) -> str:
        return f"{root}.{suffix}"

    def direct(rule: str, info: ModuleInfo, allowed: Callable[[str], bool]) -> list[Violation]:
        return [
            Violation(rule, info.name, info.path, target)
            for target in sorted(info.internal)
            if target != root and not allowed(target)
        ]

    def transitive(
        rule: str, sources: tuple[str, ...], forbidden: tuple[str, ...]
    ) -> list[Violation]:
        found: list[Violation] = []
        for info in modules.values():
            if not any(_in(info.name, pkg(s)) for s in sources):
                continue
            chain = _path_to(modules, info.name, lambda m: any(_in(m, pkg(f)) for f in forbidden))
            if chain:
                found.append(Violation(rule, info.name, info.path, " -> ".join(chain[1:])))
        return found

    violations: list[Violation] = []
    for info in modules.values():
        if _in(info.name, pkg("domain")):
            violations += direct("domain-solo-domain", info, lambda t: _in(t, pkg("domain")))
            violations += [
                Violation("domain-sin-frameworks", info.name, info.path, lib)
                for lib in sorted(info.external)
                if lib in DOMAIN_FORBIDDEN_THIRD_PARTY
            ]
        elif _in(info.name, pkg("application")):
            violations += direct(
                "application-sin-adapters-ni-presentation",
                info,
                lambda t: _in(t, pkg("domain")) or _in(t, pkg("application")),
            )
        elif _in(info.name, pkg("adapters")):
            violations += direct(
                "adapters-solo-domain-y-ports",
                info,
                lambda t: (
                    _in(t, pkg("domain"))
                    or _in(t, pkg("adapters"))
                    or any(_in(t, pkg(p)) for p in ADAPTER_APPLICATION_VOCABULARY)
                    or t == pkg("application")
                ),
            )
        elif _in(info.name, pkg("presentation")):
            violations += direct(
                "presentation-sin-adapters", info, lambda t: not _in(t, pkg("adapters"))
            )

    violations += transitive(
        "supervisor-sin-herramientas", SUPERVISOR_PACKAGES, SUPERVISOR_FORBIDDEN
    )
    violations += transitive("agente-no-llama-a-agente", AGENT_PACKAGES, AGENT_FORBIDDEN)
    return violations


# --- La regla sobre el código real ---


def test_repository_respects_layer_rules() -> None:
    violations = check_layer_rules(SRC_ROOT)
    assert not violations, "\n".join(str(v) for v in violations)


def test_supervisor_and_agent_packages_do_not_overlap() -> None:
    assert not set(SUPERVISOR_PACKAGES) & set(AGENT_PACKAGES)


# --- Casos negativos: un módulo temporal viola cada regla y la prueba lo detecta ---


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    src = tmp_path / "src"
    for relative, body in files.items():
        file = src / ROOT_PACKAGE / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        for parent in file.relative_to(src).parents:
            init = src / parent / "__init__.py"
            if parent != Path() and not init.exists():
                init.write_text("", encoding="utf-8")
        file.write_text(body, encoding="utf-8")
    return src


BASE_LAYERS = {
    "domain/plan.py": "",
    "application/ports/mcp.py": "",
    "application/ports/identity.py": "",
    "application/ports/egress.py": "",
    "application/ports/model_provider.py": "",
    "application/ports/agents.py": "",
    "application/ports/llm.py": "",
    "application/planning/builder.py": "",
    "application/execution/runner.py": "",
    "application/usecases/ask.py": "",
    "application/context.py": "",
    "application/errors.py": "",
    "application/jsontypes.py": "",
    "adapters/mcp/client.py": "",
    "adapters/persistence/engine.py": "",
    "presentation/http/app.py": "",
    "bootstrap/container.py": "",
}

NEGATIVE_CASES = {
    "domain-importa-application": (
        {"domain/bad.py": "from carmen.application.usecases import ask\n"},
        "domain-solo-domain",
        "carmen.domain.bad",
    ),
    "domain-importa-fastapi": (
        {"domain/bad.py": "import fastapi\n"},
        "domain-sin-frameworks",
        "carmen.domain.bad",
    ),
    "application-importa-adapters": (
        {"application/usecases/bad.py": "from carmen.adapters.mcp import client\n"},
        "application-sin-adapters-ni-presentation",
        "carmen.application.usecases.bad",
    ),
    "application-importa-presentation": (
        {"application/usecases/bad.py": "import carmen.presentation.http.app\n"},
        "application-sin-adapters-ni-presentation",
        "carmen.application.usecases.bad",
    ),
    "application-importa-bootstrap": (
        {"application/usecases/bad.py": "from carmen.bootstrap import container\n"},
        "application-sin-adapters-ni-presentation",
        "carmen.application.usecases.bad",
    ),
    "adapters-importa-caso-de-uso": (
        {"adapters/mcp/bad.py": "from carmen.application.usecases.ask import x\n"},
        "adapters-solo-domain-y-ports",
        "carmen.adapters.mcp.bad",
    ),
    "adapters-importa-planificacion": (
        {"adapters/persistence/bad.py": "from carmen.application.planning import builder\n"},
        "adapters-solo-domain-y-ports",
        "carmen.adapters.persistence.bad",
    ),
    "adapters-importa-presentation": (
        {"adapters/mcp/bad.py": "from carmen.presentation.http import app\n"},
        "adapters-solo-domain-y-ports",
        "carmen.adapters.mcp.bad",
    ),
    "presentation-importa-adapters": (
        {"presentation/http/bad.py": "from carmen.adapters.mcp.client import McpClient\n"},
        "presentation-sin-adapters",
        "carmen.presentation.http.bad",
    ),
    "supervisor-importa-ports-mcp-directo": (
        {"application/orchestrator/machine.py": "from carmen.application.ports import mcp\n"},
        "supervisor-sin-herramientas",
        "carmen.application.orchestrator.machine",
    ),
    "supervisor-alcanza-ports-egress-transitivo": (
        {
            "application/orchestrator/machine.py": (
                "from carmen.application.usecases import helper\n"
            ),
            "application/usecases/helper.py": "import carmen.application.ports.egress\n",
        },
        "supervisor-sin-herramientas",
        "carmen.application.orchestrator.machine",
    ),
    "supervisor-alcanza-model-provider-relativo": (
        {"application/routing/stage1.py": "from ..ports import model_provider\n"},
        "supervisor-sin-herramientas",
        "carmen.application.routing.stage1",
    ),
    "supervisor-alcanza-por-init-del-paquete": (
        {
            "application/narration/compose.py": "from carmen.application.shared import util\n",
            "application/shared/__init__.py": "from carmen.application.ports import identity\n",
            "application/shared/util.py": "",
        },
        "supervisor-sin-herramientas",
        "carmen.application.narration.compose",
    ),
    "supervisor-importa-planning": (
        {"application/grounding/check.py": "from carmen.application.planning.builder import B\n"},
        "supervisor-sin-herramientas",
        "carmen.application.grounding.check",
    ),
    "supervisor-importa-execution": (
        {"application/policy/rules.py": "import carmen.application.execution.runner\n"},
        "supervisor-sin-herramientas",
        "carmen.application.policy.rules",
    ),
    "agente-importa-ports-agents": (
        {"application/agents/executor/run.py": "from carmen.application.ports import agents\n"},
        "agente-no-llama-a-agente",
        "carmen.application.agents.executor.run",
    ),
    "agente-alcanza-ports-agents-transitivo": (
        {
            "application/planning/validator.py": "from carmen.application.usecases import relay\n",
            "application/usecases/relay.py": "from carmen.application.ports.agents import Port\n",
        },
        "agente-no-llama-a-agente",
        "carmen.application.planning.validator",
    ),
}


@pytest.mark.parametrize("case", sorted(NEGATIVE_CASES))
def test_negative_case_is_detected(tmp_path: Path, case: str) -> None:
    files, rule, module = NEGATIVE_CASES[case]
    src = _tree(tmp_path, {**BASE_LAYERS, **files})
    violations = check_layer_rules(src)
    hits = [v for v in violations if v.rule == rule and v.module == module]
    assert hits, f"no se detectó {rule} en {module}: {[str(v) for v in violations]}"
    assert hits[0].path.name in {Path(p).name for p in files}


def test_every_rule_has_a_negative_case() -> None:
    rules = {
        "domain-solo-domain",
        "domain-sin-frameworks",
        "application-sin-adapters-ni-presentation",
        "adapters-solo-domain-y-ports",
        "presentation-sin-adapters",
        "supervisor-sin-herramientas",
        "agente-no-llama-a-agente",
    }
    assert rules == {rule for _, rule, _ in NEGATIVE_CASES.values()}


def test_allowed_imports_are_not_flagged(tmp_path: Path) -> None:
    src = _tree(
        tmp_path,
        {
            **BASE_LAYERS,
            "application/orchestrator/machine.py": (
                "from carmen.domain import plan\nfrom carmen.application.ports import llm\n"
            ),
            "application/agents/executor/run.py": (
                "from carmen.application.ports import mcp\n"
                "from carmen.application.planning import builder\n"
            ),
            "adapters/mcp/client.py": "from carmen.application.ports import mcp\nimport httpx\n",
            "adapters/persistence/engine.py": (
                "from carmen.application.context import Requester\n"
                "from carmen.application.errors import EmbeddingDimensionMismatchError\n"
                "from carmen.application.jsontypes import JsonValue\n"
                "import sqlalchemy\n"
            ),
            "presentation/http/app.py": (
                "from carmen.application.usecases import ask\n"
                "from carmen.bootstrap import container\n"
            ),
            "bootstrap/container.py": (
                "from carmen.adapters.mcp import client\n"
                "from carmen.application.usecases import ask\n"
            ),
        },
    )
    assert check_layer_rules(src) == []


def test_violation_message_names_file_and_rule(tmp_path: Path) -> None:
    src = _tree(tmp_path, {**BASE_LAYERS, "domain/bad.py": "import carmen.adapters.mcp.client\n"})
    message = str(check_layer_rules(src)[0])
    assert "bad.py" in message
    assert "[domain-solo-domain]" in message
