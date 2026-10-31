"""Catálogos de herramientas del simulado y validación de argumentos.

Los catálogos son copia de eval/fixtures/catalog_<sistema>.json, los mismos que usa el golden
set; una prueba comprueba que no se separan. El validador cubre el subconjunto de JSON Schema que
usan esos inputSchema (type, enum, anyOf, pattern, longitudes, mínimos y máximos, required y
additionalProperties) para que el simulado no dependa de nada fuera de la biblioteca estándar.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from envelope import Json
from mock_errors import InvalidParamsError

CATALOGS: Final = Path(__file__).resolve().parent / "catalogs"
_TYPES: Final[dict[str, tuple[type, ...]]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
}


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    result_kind: str
    roles: list[str]
    input_schema: dict[str, Json]

    def descriptor(self) -> dict[str, Json]:
        """Descriptor ampliado de 6.9.4: MCP más result_kind y roles."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "result_kind": self.result_kind,
            "roles": list(self.roles),
        }

    @property
    def has_period(self) -> bool:
        properties = self.input_schema.get("properties", {})
        return isinstance(properties, dict) and "period" in properties


@dataclass(frozen=True, slots=True)
class Catalog:
    system_id: str
    version: str
    tools: tuple[Tool, ...]

    def tool(self, name: str) -> Tool:
        for tool in self.tools:
            if tool.name == name:
                return tool
        msg = f"herramienta desconocida en {self.system_id}: {name}"
        raise InvalidParamsError(msg)


def load(system_id: str) -> Catalog:
    data = json.loads((CATALOGS / f"{system_id}.json").read_text(encoding="utf-8"))
    tools = tuple(
        Tool(t["name"], t["description"], t["result_kind"], t["roles"], t["input_schema"])
        for t in data["tools"]
    )
    return Catalog(data["system_id"], data["catalog_version"], tools)


def validate(schema: dict[str, Json], value: Json, path: str = "arguments") -> None:
    """Lanza InvalidParamsError con la ruta del primer argumento que no cumple el esquema."""
    problem = _problem(schema, value, path)
    if problem is not None:
        raise InvalidParamsError(problem)


def _type_ok(kind: str, value: Json) -> bool:
    if isinstance(value, bool) and kind in ("integer", "number"):
        return False
    return isinstance(value, _TYPES[kind])


def _problem(schema: dict[str, Json], value: Json, path: str) -> str | None:
    if "anyOf" in schema:
        branches = schema["anyOf"]
        assert isinstance(branches, list)
        if all(_problem(b, value, path) for b in branches if isinstance(b, dict)):
            return f"{path}: no cumple ninguna de las formas admitidas"
        return None
    if "enum" in schema:
        allowed = schema["enum"]
        assert isinstance(allowed, list)
        return None if value in allowed else f"{path}: {value!r} no está en {allowed}"
    kind = schema.get("type")
    if kind is not None:
        kinds = kind if isinstance(kind, list) else [kind]
        if not any(_type_ok(str(k), value) for k in kinds):
            return f"{path}: se esperaba {kinds}"
    if isinstance(value, str):
        minimum, maximum = schema.get("minLength"), schema.get("maxLength")
        if isinstance(minimum, int) and len(value) < minimum:
            return f"{path}: mínimo {minimum} caracteres"
        if isinstance(maximum, int) and len(value) > maximum:
            return f"{path}: máximo {maximum} caracteres"
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and not re.search(pattern, value):
            return f"{path}: no cumple {pattern}"
    if isinstance(value, int | float) and not isinstance(value, bool):
        low, high = schema.get("minimum"), schema.get("maximum")
        if isinstance(low, int | float) and value < low:
            return f"{path}: mínimo {low}"
        if isinstance(high, int | float) and value > high:
            return f"{path}: máximo {high}"
    if isinstance(value, dict) and schema.get("type") == "object":
        properties = schema.get("properties", {})
        assert isinstance(properties, dict)
        required = schema.get("required", [])
        assert isinstance(required, list)
        missing = [str(r) for r in required if r not in value]
        if missing:
            return f"{path}: faltan {missing}"
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                return f"{path}: parámetros no admitidos {extra}"
        for name, item in value.items():
            sub = properties.get(name)
            if isinstance(sub, dict):
                found = _problem(sub, item, f"{path}.{name}")
                if found:
                    return found
    return None
