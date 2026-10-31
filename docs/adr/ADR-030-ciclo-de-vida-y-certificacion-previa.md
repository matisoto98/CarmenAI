# ADR-030: Ciclo de vida y certificación previa

- Estado: Aceptado
- Origen: v4.0
- Referencia: Documento Maestro v4.8, sección 7.11

## Contexto

Cumplir el contrato MCP no basta: un servidor puede devolver cifras que no reconcilian, aceptar instrucciones inyectadas o no tener dueño.

## Decisión

Cuatro estados (DISCOVERED, COMPATIBLE, CERTIFIED, QUARANTINED). Nada responde en producción sin certificar.

## Consecuencias

Un agente sin dueño no se certifica.
