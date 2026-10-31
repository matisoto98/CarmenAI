# ADR-032: Aprobación humana como protocolo; un salto de re-delegación

- Estado: Aceptado
- Origen: v4.0
- Referencia: Documento Maestro v4.8, sección 6.12.5, 6.12.6

## Contexto

Una aprobación escrita en el prompt es una sugerencia que el modelo puede ignorar.

## Decisión

La aprobación humana es un estado del protocolo (AWAITING_APPROVAL) que el código no puede saltar. NeedDelegation admite como máximo un salto de re-delegación por turno y no propone agent_id.

## Consecuencias

El modelo no puede saltarse la aprobación ni encadenar delegaciones.
