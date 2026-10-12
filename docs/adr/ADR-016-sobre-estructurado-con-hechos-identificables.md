# ADR-016: Sobre estructurado con hechos identificables

- Estado: Aceptado
- Origen: Revisión v2.0 (C4)
- Referencia: Documento Maestro v4.8, sección 2.6, 6.3, 6.4

## Contexto

La v1.0 persistía el resultado como result_brief saneado, pero el anclaje debe enlazar cada cifra con su origen.

## Decisión

El resultado de herramienta es un sobre estructurado con hechos identificables (EvidenceFact). result_brief se conserva solo como campo derivado para depuración.

## Consecuencias

El anclaje verifica por referencia a fact_id, no por coincidencia de texto.
