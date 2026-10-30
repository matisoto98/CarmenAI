"""Valores JSON tipados para lo que cruza un puerto como JSON: esquemas y argumentos (5.5)."""

from collections.abc import Mapping, Sequence

type JsonValue = str | int | float | bool | None | Sequence[JsonValue] | Mapping[str, JsonValue]
type JsonObject = Mapping[str, JsonValue]
