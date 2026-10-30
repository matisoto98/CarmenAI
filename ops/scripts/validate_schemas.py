"""Valida que cada esquema de contracts/ sea un JSON Schema correcto (etapa 1 de 8.4).

Recorre contracts/ y sus subcarpetas (registry/). Los ejemplos los valida la etapa de contrato.

Uso: python ops/scripts/validate_schemas.py [fichero ...]
"""

import json
import sys
from pathlib import Path

from jsonschema.validators import validator_for

REPO_ROOT = Path(__file__).resolve().parents[2]


def main(paths: list[str]) -> int:
    files = [Path(p) for p in paths] or sorted((REPO_ROOT / "contracts").rglob("*.schema.json"))
    failed = False
    for path in files:
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
            validator_for(schema).check_schema(schema)
        except Exception as exc:  # noqa: BLE001 - se informa cualquier fallo y se sigue
            sys.stderr.write(f"{path}: {exc}\n")
            failed = True
    sys.stdout.write(f"{len(files)} esquema(s) revisado(s)\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
