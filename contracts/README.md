# Contratos canónicos

Estos esquemas son la fuente. Python y TypeScript se verifican contra ellos y no se generan a partir
de ellos (ADR-021). Todos son JSON Schema 2020-12 con `$id` estable bajo
`https://plenergy.internal/carmen/` y se referencian entre sí por ese `$id`.

**Regla (6.12.9):** cambiar la forma de un contrato exige subir su `schema_version` y añadir una fila a
la matriz de compatibilidad de este fichero. Añadir un evento o un campo opcional es menor y no sube
la versión (6.5). Quitar un campo, hacerlo obligatorio o cambiar su significado sí la sube.

## Ficheros

| Fichero | Sección | Qué fija |
|---|---|---|
| `common.schema.json` | 6.2, 6.12 | Identificadores, instantes, importes y enumeraciones compartidas |
| `plan.schema.json` | 6.2 | QueryPlan local de un agente sobre sus herramientas |
| `evidence.schema.json` | 6.3, 6.9.2 | Evidencia (hecho, pasaje, adjunto) y resultado del grounding |
| `mcp-envelope.schema.json` | 6.4 | Sobre de respuesta de una herramienta MCP |
| `mcp-servers.schema.json` | 7.5 | Registro de servidores MCP (`config/mcp_servers.yaml`) |
| `errors.json` | 6.6 | Taxonomía única de errores con su traducción a HTTP y SSE |
| `sse-events.schema.json` | 6.5 | Eventos SSE 1.1, una carga por `event_type` |
| `agent-task.schema.json` | 6.12.4 | Encargo autocontenido a un agente |
| `delegation-plan.schema.json` | 6.12.3 | Plan de delegación del supervisor |
| `agent-result.schema.json` | 6.12.4 | Resultado de un agente con su ejecución y trazas |
| `agent-card.schema.json` | 5.14.3 | Ficha del agente; el AgentRegistry es una lista de fichas |
| `conversation-turn.schema.json` | 6.12.8 | Turno completo, la unidad de registro |
| `registry/agent-mcp-bindings.schema.json` | 7.10 | Agente ↔ servidor MCP con sus scopes |
| `registry/agent-provider-bindings.schema.json` | 7.10.1 | Agente ↔ proveedor de modelo con propósito y clase de dato |
| `registry/model-providers.schema.json` | 7.10 | Proveedores de modelo |
| `registry/external-sources.schema.json` | 7.10 | Fuentes externas gobernadas |
| `registry/egress-policy.schema.json` | 7.10 | Política de salida; sin política aplicable, deny |
| `registry/entities.schema.json` | 6.11 | Mapa de entidades canónicas por agente |

`examples/` guarda, por esquema, ejemplos positivos y negativos con el motivo de cada negativo.
Los de 6.2.3 y 6.12.3 están completos (ADR-045).

## Matriz de compatibilidad

Versión vigente de cada contrato y qué versiones acepta cada lado. «Productor» es quien emite el
documento; «consumidor», quien lo lee. Un consumidor rechaza una versión que no aparece en su columna.

| Contrato | Vigente | Productor | Consumidor | El consumidor acepta | Desde |
|---|---|---|---|---|---|
| plan | 1.0 | Planificador del agente | Validador y ejecutor del plan | 1.0 | Prompt 4 |
| evidence | 1.0 | Adaptador MCP (a partir del sobre) | Grounding, narrador, auditoría, frontend | 1.0 | Prompt 4 |
| mcp-envelope | 1.0 | Servidor MCP de cada sistema | Adaptador MCP de Carmen | 1.0 (`contract.min_envelope_version` por servidor) | Prompt 4 |
| mcp-servers | 1.0 | Operación (`config/`) | Composición y registro MCP | 1.0 | Prompt 4 |
| errors | 1.0 | Dominio (códigos estables) | Presentación (HTTP y SSE), frontend | 1.0 | Prompt 4 |
| sse-events | 1.1 | API (`/chat/stream`) | Frontend | 1.0 y 1.1 (ignora eventos y campos que no conoce) | Prompt 4 |
| agent-task | 1.0 | Supervisor | Agente | 1.0 | Prompt 4 |
| delegation-plan | 1.0 | Supervisor | Orquestador, auditoría | 1.0 | Prompt 4 |
| agent-result | 1.0 | Agente | Supervisor, auditoría | 1.0 | Prompt 4 |
| agent-card | 1.0 | Registro de agentes | Router, catálogo, administración | 1.0 | Prompt 4 |
| conversation-turn | 1.0 | Orquestador | Persistencia, auditoría, KPIs | 1.0 | Prompt 4 |
| registry/* | 1.0 | Operación (`config/`) | Políticas y composición | 1.0 | Prompt 4 |

### SSE 1.0 → 1.1

La 1.1 solo añade, así que un cliente 1.0 sigue funcionando (6.5). El documento marca como 1.1 los
cuatro eventos nuevos; los campos de orquestación de los eventos existentes se deducen de que solo
tienen sentido con delegación (ADR-045).

| Cambio | Tipo | Efecto en un cliente 1.0 |
|---|---|---|
| Eventos `mode`, `delegation`, `agent_result` y `approval_required` | Añadido | Los ignora |
| Campos `task_id` y `agent_id` en `tool_call` y `tool_result` | Añadido | Los ignora |
| Campos `response_mode`, `agents_used` y `missing_agents` en `done` | Añadido | Los ignora |
| Campo `agent_id` en `warning` | Añadido, opcional | Lo ignora |

### Historial

| Fecha | Contrato | De → a | Cambio | ADR |
|---|---|---|---|---|
| Prompt 4 | Todos | — → vigente | Publicación inicial | ADR-021, ADR-045 |

## Cómo se verifica

- `ops/scripts/validate_schemas.py` comprueba que cada esquema es JSON Schema válido (CI, etapa 1).
- `api/tests/contract/test_schema_alignment.py` valida los ejemplos positivos y negativos, compara
  cada objeto con su tipo del dominio campo a campo (nombres y obligatorios), y comprueba los
  enumerados, los patrones de identificador y los códigos de error. Los contratos que aún no tienen
  tipo en el dominio quedan fijados por tablas de campos. Todo objeto de todo esquema está en una
  de las dos listas.
- `web/src/contracts/alignment.test.ts` hace lo mismo con los tipos de TypeScript. Cada tipo tiene
  una tabla de claves cuyo tipo (`KeySpec<T>`) obliga a tsc a que coincida con el tipo, y la
  prueba compara la tabla con el esquema. La unión `SseEvent` cubre exactamente los tipos de
  evento de SSE 1.1.

Añadir un campo obligatorio a cualquier esquema sin tocar los tipos hace fallar las dos pruebas.
