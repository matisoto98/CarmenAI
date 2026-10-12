# ADR-012: k de N, inestabilidad, línea base y modo sombra

- Estado: Aceptado
- Origen: v1.0 (reconstruido)
- Referencia: Documento Maestro v4.8, sección 10.2, 10.6, 10.7

> Reconstruido en la v4.8 a partir de la matriz de trazabilidad (15.12). El texto original de la v1.0 no está en el paquete de entrega; si aparece, sustituye a este. La numeración 001 a 012 también es reconstruida, salvo ADR-010, que el documento cita expresamente (6.10.6).

## Contexto

Con un modelo no determinista, una ejecución aislada no demuestra nada y un cambio de modelo puede degradar en silencio.

## Decisión

Las pruebas de evaluación se ejecutan k de N veces, se mide la inestabilidad, se mantiene una línea base y los cambios de modelo pasan por modo sombra.

## Consecuencias

Se conservan íntegros (la revisión de la v2.0 los omitía). La línea base solo se registra contra el servidor.
