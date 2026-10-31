"""Prompt 5: ningún doble importa un adaptador, ni presentación, ni la composición."""

import ast
from pathlib import Path
from typing import Final

import pytest

pytestmark = pytest.mark.application

SUPPORT: Final = Path(__file__).resolve().parent
FORBIDDEN: Final = ("carmen.adapters", "carmen.presentation", "carmen.bootstrap")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize(
    "path", sorted(SUPPORT.rglob("*.py")), ids=lambda p: str(p.relative_to(SUPPORT))
)
def test_support_does_not_import_infrastructure(path: Path) -> None:
    bad = sorted(n for n in _imports(path) if n.startswith(FORBIDDEN))
    assert bad == []


def test_the_scan_sees_every_double() -> None:
    scanned = {p.stem for p in (SUPPORT / "fakes").glob("*.py")}
    assert {"agents", "egress", "llm", "mcp", "policy", "repositories", "system"} <= scanned
