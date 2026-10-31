# ADR-044: Concreciones del dominio de orquestación

- Estado: Aceptado
- Origen: Prompt 3
- Referencia: Documento Maestro v4.8, sección 2.3.2, 5.14.3, 5.14.4, 6.12, 7.9.2, 7.11.2

## Contexto

Al implementar los tipos de orquestación y gobierno del Prompt 3 aparecen contradicciones entre secciones y detalles que el documento maestro deja abiertos. El modo de trabajo (2.9) exige registrarlos como ADR.

## Decisión

1. `AgentId` lleva el prefijo de 5.14.3, 6.12.3 y 7.9.6: `agent.vigia`, `agent.zoho-desk`. El patrón de 6.2 (`^[a-z][a-z0-9_-]{1,31}$`) no admite el punto; se usa un solo tipo de identificador en todo el dominio y el `agent` de cada paso del QueryPlan pasa a escribirse `agent.vigia`. `SystemId` no cambia (`vigia`).
2. El Role de plataforma (ADMIN, MANAGER, OPERATOR, AUDITOR; `carmen.role` en SQL) sigue en `domain/role.py`. El rol versionado de la política de 7.9.2 se llama `PolicyRole` para no tener dos tipos `Role`. La concesión se llama `RoleAgentGrant`, como en 7.9.2.
3. `AgentTask` incluye `depends_on` y `optional`, que el JSON de 6.12.3 pone en cada tarea y el dataclass de 6.12.4 omite. El `DelegationPlan` lleva tuplas de `AgentTask`.
4. "Un AgentTask no admite nombres de herramienta" se aplica de dos formas. El tipo no tiene campo de herramienta. Además, el objetivo se rechaza si contiene un identificador con guion bajo (`query_metric`) o una llamada (`fn()`), porque el objetivo se escribe en lenguaje de dominio. La comprobación contra el catálogo real es del validador de application.
5. La identidad delegada viaja como `DelegatedIdentityRef` (`idr_…`), no como `DelegatedToken`. El patrón no admite puntos ni espacios, así que un JWT o un «Bearer …» no se pueden construir como referencia (6.12.9).
6. La suma de presupuestos de las tareas se compara con el global así. Los tokens y el coste se suman. El tiempo se suma solo a lo largo de las cadenas de dependencias (camino crítico), porque las tareas independientes van en paralelo. Además, el número de agentes distintos no puede superar `max_agents`.
7. Un `AgentResult` `ok` o `partial` exige al menos un elemento de evidencia; `partial` exige además avisos, como el sobre de 6.4. `no_data`, `denied` y `failed` no llevan evidencia. Así "texto libre como resultado principal" no se puede construir: un resultado con solo `ModelOutput` es imposible.
8. `NeedDelegation.reason` y `suggested_domain` son enumeraciones con valores iniciales. `reason` toma needs_procedure, needs_complementary_data, needs_legal_review u out_of_scope. `suggested_domain` toma monitorizacion, economico, documental, soporte, legal o contractual. Su texto (`context_ref`, `rationale`) no puede nombrar un `agent.*`.
9. `DataClass` toma la taxonomía provisional que usan los ejemplos de 7.10, ordenada: PUBLICO < INTERNO < CONFIDENCIAL. Se sustituirá cuando Plenergy valide la suya (P2, P18). `Purpose` toma routing, narration y analysis, los valores de los bindings de 7.10.1.
10. `TurnStatus` son los seis valores de `carmen.msg_status`. AWAITING_APPROVAL es una fase de la máquina del turno (6.8.1), no un estado persistido.
11. `ConversationTurn` aplica `ck_direct_sin_agentes` a los tres modos que no delegan (SUPERVISOR_DIRECT, CLARIFY y REFUSE): sin agentes, sin plan, sin ejecuciones, sin agentes ausentes y sin re-delegaciones. En los modos de delegación exige un plan del mismo turno y modo, y que toda ejecución esté en `agents_used`. Las re-delegaciones van de 0 a 1 (`ck_redelegations`).
12. Una `AgentCard` no puede declarar `write` en v1 (invariante 5, solo lectura). Las transiciones de ciclo de vida son exactamente las cuatro de 7.11.2. Cualquier otra lanza `InvalidTransitionError`, un `ValidationError` con código `invalid_transition` que se añade a la taxonomía.
13. Un `PolicyDecision` exige `reason_code` siempre y no concede scopes cuando deniega. Un `RoleAgentGrant` con `deny` exige motivo (`ck_deny_reason`).

## Consecuencias

El DelegationPlan de 6.12.3 y el turno de un saludo se construyen sin infraestructura, y los estados que el documento declara imposibles no se pueden representar. Los cambios de identificador del punto 1 tocan las pruebas del Prompt 2. El Prompt 7 genera de estas enumeraciones las restricciones SQL.
