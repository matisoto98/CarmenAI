# ADR-025: Modo de respuesta antes de cualquier plan

- Estado: Aceptado
- Origen: v4.0
- Referencia: Documento Maestro v4.8, sección 2.3.2

## Contexto

Convertir cada saludo en una consulta a un sistema de producción consume recursos y toca sistemas sin necesidad.

## Decisión

El modo de respuesta (SUPERVISOR_DIRECT, DELEGATE_SINGLE, DELEGATE_MULTI, CLARIFY, REFUSE) se clasifica antes de construir cualquier plan.

## Consecuencias

Un saludo nunca delega.
