# ADR-015: QueryPlan con pasos, dependencias y paralelismo

- Estado: Aceptado
- Origen: Revisión v2.0 (C3)
- Referencia: Documento Maestro v4.8, sección 2.6, 6.2

## Contexto

El plan de la v1.0 era de un solo paso, pero el planificador debe componer dossiers de varias llamadas y rondas.

## Decisión

QueryPlan versionado con pasos, dependencias y ejecución en paralelo. El planificador deja de ser un bucle implícito.

## Consecuencias

Las rondas son explícitas en los límites y en la máquina de estados.
