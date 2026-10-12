# ADR-005: Enrutado en dos etapas con un modelo

- Estado: Aceptado
- Origen: v1.0 (reconstruido)
- Referencia: Documento Maestro v4.8, sección 5.7

> Reconstruido en la v4.8 a partir de la matriz de trazabilidad (15.12). El texto original de la v1.0 no está en el paquete de entrega; si aparece, sustituye a este. La numeración 001 a 012 también es reconstruida, salvo ADR-010, que el documento cita expresamente (6.10.6).

## Contexto

Exponer todas las herramientas de todos los sistemas en una sola llamada satura el contexto del modelo y empeora la elección.

## Decisión

El enrutado se hace en dos etapas con el mismo modelo: la primera elige sistemas (agentes) y la segunda herramientas.

## Consecuencias

Se añade la comprobación de conflicto entre ambas etapas. Con ADR-024 la segunda etapa pasa al especialista.
