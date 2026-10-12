# ADR-028: DelegationPlan y QueryPlan; cruce solo con mapa

- Estado: Aceptado
- Origen: v4.0
- Referencia: Documento Maestro v4.8, sección 6.11, 6.12

## Contexto

La v3.0 usaba un plan único que mezclaba a quién delegar y qué herramientas llamar.

## Decisión

DelegationPlan es del supervisor y habla de agentes; QueryPlan es del especialista y habla de sus herramientas. El cruce entre agentes solo ocurre con mapa de entidades.

## Consecuencias

El supervisor nunca compone un QueryPlan.
