# ADR-006: Glosario con conflictos declarados

- Estado: Aceptado
- Origen: v1.0 (reconstruido)
- Referencia: Documento Maestro v4.8, sección 5.2 (invariante 4), 6.11

> Reconstruido en la v4.8 a partir de la matriz de trazabilidad (15.12). El texto original de la v1.0 no está en el paquete de entrega; si aparece, sustituye a este. La numeración 001 a 012 también es reconstruida, salvo ADR-010, que el documento cita expresamente (6.10.6).

## Contexto

Dos sistemas pueden usar el mismo nombre para métricas distintas.

## Decisión

Un glosario declara equivalencias y CONFLICTOS entre términos de distintos sistemas. No se unifica lo que no tiene equivalencia declarada.

## Consecuencias

La comprobación pasa al validador del plan, antes de ejecutar (invariante 4).
