# ADR-045: Concreciones de los contratos canónicos

- Estado: Aceptado
- Origen: Prompt 4
- Referencia: Documento Maestro v4.8, secciones 6.2, 6.3, 6.4, 6.5, 6.6, 6.11, 6.12, 7.5 y 7.10

## Contexto

El Prompt 4 publica los esquemas de `contracts/` y las pruebas que verifican Python y TypeScript contra
ellos (ADR-021). Al escribirlos aparecen ejemplos abreviados, campos que el documento no define y
diferencias entre secciones. El modo de trabajo (2.9) exige registrarlos como ADR.

## Decisión

1. **Raíz versionada.** Todo contrato lleva `schema_version` (6.12.9), pero un `AgentTask` embebido en
   un `DelegationPlan` no lo repite. Cada contrato define su objeto en `$defs` sin versión. La raíz lo
   envuelve con `$ref`, añade `schema_version` y se cierra con `unevaluatedProperties: false`. Quien lo
   embebe lo cierra igual. El `DelegationPlan` y el `QueryPlan` ya llevan `schema_version` en el
   dominio y su raíz es el propio objeto.
2. **`systems` del plan es opcional.** 6.2 lo pone entre los obligatorios, pero ADR-043 lo deriva de los
   pasos. El esquema lo admite y la lectura del dominio comprueba que coincide.
3. **`arguments` es obligatorio en el cable.** Un paso siempre declara sus argumentos, aunque sean `{}`.
   El dominio lo rellena por defecto al construir un paso en memoria.
4. **Nombres del cable frente al dominio.** El esquema conserva los nombres de 6.2 y 6.3: `$ref_step`,
   `$ref_fact` y `$ref_field` de la referencia a un hecho; `from` y `to` del periodo; `type` como
   discriminador de la evidencia. En Python son `step_id`, `fact` y `field`; `start` y `end`, porque
   `from` es palabra reservada; y `evidence_type` como `ClassVar`. Las equivalencias están escritas una
   a una en la prueba de alineación. TypeScript usa los nombres del cable.
5. **Importes.** El cable usa `number` y el dominio `Decimal`. La conversión es del adaptador.
6. **Ejemplos completos.** Los planes de 6.2.3 llevan `agent` en cada paso (ADR-044). Las tareas de
   6.12.3 se completan con `locale`, `budgets` y `delegated_identity`, que el dataclass de 6.12.4 exige
   y el JSON omite. El sobre documental de 6.4 está abreviado en el documento. El ejemplo positivo
   lleva todas las claves obligatorias.
7. **Servidores MCP.** El `id` de un servidor en `mcp_servers.yaml` (7.5) es el `SystemId` (`vigia`).
   Los bindings y las fichas de agente lo nombran como `McpServerId`, `mcp.<id>` (`mcp.vigia`). El
   sobre limita `rows` a 500, el mismo tope que `limits.max_rows`.
8. **`kill_switch` es booleano** en la ficha del agente. El documento lo escribe como `enabled`, que no
   distingue entre activado y desactivado.
9. **Mapa de entidades.** Las claves de `mapeo` en `entities.yaml` son `AgentId` (`agent.vigia`), no el
   nombre del sistema. El join cruza resultados de agentes (6.11, 6.12.3).
10. **Registros de 7.10 sin forma en el documento.** Los campos de `model-providers` (kind, region,
    models, retention_days, contract_ref) y de `external-sources` (kind, reliability, domains, agents)
    son una propuesta inicial. La política de salida declara `default: "deny"` como constante y solo
    admite el método GET. `DataClass` y `Purpose` siguen siendo provisionales (ADR-044, punto 9).
11. **Catálogo de errores.** `errors.json` lleva `schema_version` y, por código, su clase, su grupo, el
    HTTP y la secuencia SSE de 6.6. Incluye `invalid_plan` (Prompt 2) e `invalid_transition` (ADR-044).
    Las familias abstractas (`carmen_error`, `mcp_error`, `llm_error`) no viajan y no están.
    `cancelled` no tiene código HTTP, porque el cliente ya se fue.
12. **SSE 1.1.** Las doce cargas son objetos cerrados con todos los campos de 6.5 obligatorios salvo
    los marcados con `?`. En `done`, `plan_id` es el `DelegationPlanId` del turno o `null` si no se
    delegó, y `grounding_ok` es `null` si no hubo cifras que comprobar. El documento marca como 1.1
    los cuatro eventos nuevos. Los campos `task_id` y `agent_id` de `tool_*`, y `response_mode`,
    `agents_used` y `missing_agents` de `done`, se registran también como añadidos de la 1.1 en la
    matriz de compatibilidad, porque solo existen con delegación.
13. **Contratos sin tipo de dominio todavía.** El sobre MCP, el registro de servidores, las cargas SSE y
    los registros de 7.10 no tienen dataclass en el dominio: llegan con sus adaptadores. Hasta
    entonces, la prueba de Python los fija con tablas de campos, y la de TypeScript con sus tipos.
    Los registros de política (Principal, PolicyRole, RoleAssignment, RoleAgentGrant),
    `HumanApprovalRequest` y `DataExportDecision` son estado guardado, no contratos de intercambio;
    su forma la fija la migración del Prompt 7.
14. **Alineación en TypeScript sin generación de código.** Cada tipo tiene una tabla de claves de tipo
    `KeySpec<T>`, que tsc obliga a coincidir con el tipo en claves y obligatoriedad. La prueba compara
    la tabla con el esquema. Los identificadores son tipos de plantilla (`agent.${string}`,
    `pln_${string}`), sin repetir los patrones completos.
15. **Validación de esquemas recursiva.** `ops/scripts/validate_schemas.py` recorre también
    `contracts/registry/`.

## Consecuencias

Un campo obligatorio nuevo en cualquier esquema hace fallar la prueba de Python y la de TypeScript
hasta que se actualizan los tipos. Una excepción que deja de hacer falta también hace fallar la prueba
y se tiene que borrar. Los Prompts 7, 11 y 21 sustituyen las tablas de campos por tipos de dominio
cuando creen los adaptadores. Los campos de los registros del punto 10 se revisarán con Plenergy.
