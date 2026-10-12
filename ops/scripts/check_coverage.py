"""Comprueba la cobertura mínima POR MÓDULO de la sección 8.2.

Lee los umbrales de [tool.carmen.coverage] en pyproject.toml y el informe JSON de coverage.
Un módulo sin código todavía se informa y no falla; uno con código por debajo de su umbral, sí.

Uso: python ops/scripts/check_coverage.py coverage.json
"""

import json
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _thresholds() -> tuple[float, dict[str, float]]:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    section = config["tool"]["carmen"]["coverage"]
    return float(section["default"]), {k: float(v) for k, v in section["modules"].items()}


def _module_for(path: str, modules: dict[str, float]) -> str | None:
    normalized = path.replace("\\", "/")
    matches = [m for m in modules if f"{m}/" in normalized or normalized.endswith(f"{m}.py")]
    return max(matches, key=len) if matches else None


def main(report_path: str) -> int:
    default, modules = _thresholds()
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    totals: dict[str, list[int]] = {}
    for path, data in report["files"].items():
        key = _module_for(path, modules) or "resto"
        covered, statements = totals.setdefault(key, [0, 0])
        totals[key] = [
            covered + data["summary"]["covered_lines"],
            statements + data["summary"]["num_statements"],
        ]

    failed = False
    for key in [*modules, "resto"]:
        minimum = modules.get(key, default)
        covered, statements = totals.get(key, [0, 0])
        if statements == 0:
            sys.stdout.write(f"  {key:<34} sin código todavía (mínimo {minimum:.0f} %)\n")
            continue
        percent = 100 * covered / statements
        ok = percent >= minimum
        failed |= not ok
        mark = "ok" if ok else "FALLA"
        sys.stdout.write(f"  {key:<34} {percent:5.1f} % (mínimo {minimum:.0f} %) {mark}\n")
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.stderr.write(__doc__ or "")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
