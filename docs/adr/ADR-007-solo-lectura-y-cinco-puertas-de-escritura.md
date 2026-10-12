# ADR-007: Solo lectura y cinco puertas de escritura

- Estado: Aceptado
- Origen: v1.0 (reconstruido)
- Referencia: Documento Maestro v4.8, sección 2.2.2, 5.10

> Reconstruido en la v4.8 a partir de la matriz de trazabilidad (15.12). El texto original de la v1.0 no está en el paquete de entrega; si aparece, sustituye a este. La numeración 001 a 012 también es reconstruida, salvo ADR-010, que el documento cita expresamente (6.10.6).

## Contexto

Pasar de informar a actuar cambia la categoría del sistema y su riesgo.

## Decisión

En v1 no se registra ninguna herramienta de escritura. La escritura queda diseñada con cinco puertas, fuera de v1, y exigirá entrega y ADR propios.

## Consecuencias

El registro rechaza al arrancar un servidor con capacidad de escritura.
