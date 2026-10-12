# ADR-001: Los cinco invariantes

- Estado: Aceptado
- Origen: v1.0 (reconstruido)
- Referencia: Documento Maestro v4.8, sección 5.2

> Reconstruido en la v4.8 a partir de la matriz de trazabilidad (15.12). El texto original de la v1.0 no está en el paquete de entrega; si aparece, sustituye a este. La numeración 001 a 012 también es reconstruida, salvo ADR-010, que el documento cita expresamente (6.10.6).

## Contexto

Carmen accede a datos reales de sistemas de producción. Hacen falta reglas que ninguna implementación pueda relajar.

## Decisión

Se fijan cinco invariantes no negociables: el modelo no calcula; la autorización vive en el sistema; el cálculo va junto al dato (con 3 bis, el supervisor no llama a herramientas, y 3 ter, no hay salida al exterior salvo por adaptador certificado); no se unifica lo que no es equivalente; solo lectura en v1.

## Consecuencias

Cada invariante tiene una prueba que falla si se rompe. Las reglas de capa de 5.3 y estos invariantes no se renegocian.
