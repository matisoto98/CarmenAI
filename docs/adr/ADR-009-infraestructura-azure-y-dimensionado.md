# ADR-009: Infraestructura Azure y dimensionado

- Estado: Aceptado
- Origen: v1.0 (reconstruido)
- Referencia: Documento Maestro v4.8, sección 4, 15.12

> Reconstruido en la v4.8 a partir de la matriz de trazabilidad (15.12). El texto original de la v1.0 no está en el paquete de entrega; si aparece, sustituye a este. La numeración 001 a 012 también es reconstruida, salvo ADR-010, que el documento cita expresamente (6.10.6).

## Contexto

Carmen necesita una plataforma de despliegue reproducible.

## Decisión

La infraestructura se declara como código en Azure.

## Consecuencias

Se añaden digests fijados y perfiles por entorno (ADR-018). La inferencia reutiliza SRVAZMG002FYB01 (ADR-033); el host de la aplicación queda pendiente (ADR-035).
