"""Modos de fallo del simulado, activados por configuración (Prompt 9).

`MCP_MOCK_FAILURES` es una lista separada por `;` de reglas `destino=modo[:argumento]`:

    vigia.query_metric=slow:3000;plenmind.get_procedure=error;*=down

El destino es `sistema.herramienta`, `sistema.*` o `*`. Gana la regla más concreta.

| Modo        | Efecto declarado                                                            |
|-------------|------------------------------------------------------------------------------|
| slow:<ms>   | Responde lo mismo, `ms` milisegundos más tarde (3000 si no se indica).       |
| error       | tools/call devuelve isError=true con «error interno simulado».              |
| forbidden   | HTTP 403 sea cual sea el rol.                                               |
| down        | Cierra la conexión sin responder. Con `*` o `sistema.*`, desde el saludo.    |
| invalid     | Devuelve un sobre que incumple el contrato: sin `passages` y con             |
|             | partial=true sin avisos. Carmen debe tratarlo como McpContractViolation.    |

Una regla mal escrita impide arrancar el simulado: un fallo silencioso no probaría nada.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

DEFAULT_SLOW_MS: Final = 3000


class Mode(StrEnum):
    SLOW = "slow"
    ERROR = "error"
    FORBIDDEN = "forbidden"
    DOWN = "down"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class Failure:
    mode: Mode
    delay_ms: int = 0


class FailureConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FailurePlan:
    rules: dict[str, Failure]

    @classmethod
    def parse(cls, text: str) -> "FailurePlan":
        rules: dict[str, Failure] = {}
        for raw in text.split(";"):
            rule = raw.strip()
            if not rule:
                continue
            target, sep, spec = rule.partition("=")
            if not sep or not target.strip():
                msg = f"regla de fallo sin destino: {rule!r}"
                raise FailureConfigError(msg)
            mode_name, _, argument = spec.strip().partition(":")
            try:
                mode = Mode(mode_name)
            except ValueError as error:
                msg = f"modo de fallo desconocido en {rule!r}; admitidos: {[m.value for m in Mode]}"
                raise FailureConfigError(msg) from error
            delay = 0
            if mode is Mode.SLOW:
                if argument and not argument.isdigit():
                    msg = f"slow espera milisegundos: {rule!r}"
                    raise FailureConfigError(msg)
                delay = int(argument) if argument else DEFAULT_SLOW_MS
            elif argument:
                msg = f"{mode} no lleva argumento: {rule!r}"
                raise FailureConfigError(msg)
            rules[target.strip()] = Failure(mode, delay)
        return cls(rules)

    def for_call(self, system_id: str, tool: str) -> Failure | None:
        for key in (f"{system_id}.{tool}", f"{system_id}.*", "*"):
            if key in self.rules:
                return self.rules[key]
        return None

    def server_down(self, system_id: str) -> bool:
        """Caída del servidor entero: ni siquiera responde al saludo."""
        for key in (f"{system_id}.*", "*"):
            failure = self.rules.get(key)
            if failure is not None:
                return failure.mode is Mode.DOWN
        return False
