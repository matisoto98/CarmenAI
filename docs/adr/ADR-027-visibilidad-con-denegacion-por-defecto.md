# ADR-027: Visibilidad con denegación por defecto

- Estado: Aceptado
- Origen: v4.0
- Referencia: Documento Maestro v4.8, sección 5.14.4, 7.9

## Contexto

Conocer que un agente existe, que te lo expliquen y poder usarlo son cosas distintas.

## Decisión

Tres permisos (discover, describe, invoke) y cuatro niveles de visibilidad (PUBLIC_CATALOG, DISCOVERABLE, AUTHORIZED_ONLY, HIDDEN), con denegación por defecto.

## Consecuencias

Un agente oculto no se descubre ni por error ni por latencia.
