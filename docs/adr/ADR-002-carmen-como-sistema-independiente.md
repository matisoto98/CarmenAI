# ADR-002: Carmen como sistema independiente

- Estado: Aceptado
- Origen: v1.0 (reconstruido)
- Referencia: Documento Maestro v4.8, sección 2.1, 15.12

> Reconstruido en la v4.8 a partir de la matriz de trazabilidad (15.12). El texto original de la v1.0 no está en el paquete de entrega; si aparece, sustituye a este. La numeración 001 a 012 también es reconstruida, salvo ADR-010, que el documento cita expresamente (6.10.6).

## Contexto

Carmen consulta a varios sistemas de la compañía y no debe acoplarse a ninguno.

## Decisión

Carmen es un sistema propio, con repositorio, base de datos y registro de decisiones independientes de los sistemas que consulta.

## Consecuencias

No se toca el repositorio ni la configuración de VigIA ni de ningún otro sistema. Incorporar un sistema no exige modificar el núcleo.
