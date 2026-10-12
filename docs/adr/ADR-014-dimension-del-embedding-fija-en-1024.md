# ADR-014: Dimensión del embedding fija en 1024

- Estado: Aceptado
- Origen: Revisión v2.0 (C2)
- Referencia: Documento Maestro v4.8, sección 2.6, 4.3

## Contexto

La v1.0 declaraba la dimensión configurable, pero la migración fija vector(1024).

## Decisión

La dimensión es FIJA en v1: 1024, la de bge-m3. La variable EMBED_DIM pasa a ser una comprobación de arranque que falla si el modelo devuelve otra dimensión.

## Consecuencias

Cambiar la dimensión exige migración y reindexado.
