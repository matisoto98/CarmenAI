# ADR-048: Concreciones de la migración 0001 y la persistencia por agregado

- Estado: Aceptado
- Origen: Prompt 7
- Referencia: Documento Maestro v4.8, secciones 4.6.2, 5.3, 7.1, 7.2, 7.3, 7.4, 7.8.4, 7.9.3 y 7.9.7

## Contexto

El Prompt 7 pide la migración 0001 con todo lo que 7.3, 7.8.4 y 7.9.7 declaran, un módulo de
persistencia por agregado y pruebas contra PostgreSQL real. El SQL de esas secciones se escribió
antes que los puertos del Prompt 5 y no siempre coincide con ellos: identificadores, tablas que
el puerto no lee y restricciones que el dominio ya impone. El modo de trabajo (2.9) exige registrar
cada concreción.

## Decisión

1. **Identificadores del dominio en texto.** El SQL de 7.3 usa `uuid` para todo. Los puertos usan
   identificadores con prefijo (`cnv_`, `msg_`, `mem_`, `gap_`, `top_`, y `trn_` en las decisiones
   de política). Esas columnas son `text` y llevan la misma restricción de patrón que el dominio.
   Las filas internas sin identificador de dominio siguen siendo `uuid` con `gen_random_uuid()`:
   `tool_calls`, `evidence_facts`, `grounding_claims`, `glossary_history`, `knowledge_chunks` y
   `policy_decisions`.
2. **Temas antes que mensajes.** `messages.topic_id` referencia `topics`, así que `topics` se crea
   antes. Su `centroid` admite nulo, porque el registro `Topic` del puerto no lo lleva: lo escribirá
   el agrupamiento, no este repositorio.
3. **Restricciones añadidas.** Se añaden las que el dominio ya impone, para que la base no acepte
   lo que el dominio rechaza:
   - `ck_topic_counts`: resueltas más no resueltas no superan las preguntadas;
   - `ck_tc_error`: `ok = (error_code IS NULL)`;
   - `ck_fact_one_value`: un hecho tiene valor numérico o de texto, no los dos;
   - `CHECK` de valores cerrados en `glossary_terms.source`, `role_assignments.source`,
     `gaps.status`, `topics.status` y `role_agent_grants.actions` (no vacío, dentro de
     discover/describe/invoke);
   - `ck_deny_reason`: un deny sin motivo, o con un motivo en blanco, se rechaza.

   `glossary_history` añade `seq` (identidad) para ordenar dos cambios del mismo instante.
4. **Ejecutor de migraciones propio.** `python -m carmen.migrations [--check]` aplica cada
   `NNNN_nombre.sql` una vez, en orden y en su propia transacción, bajo un bloqueo consultivo. Lo
   registra en `carmen_meta.schema_migrations` con su sha256. `--check` falla si hay pendientes,
   modificadas o desconocidas, y `apply` se niega a seguir con una modificada o desconocida. La URL
   sale de `CARMEN_DATABASE_URL`. Se usa asyncpg directo y no Alembic: el documento quiere SQL
   explícito, y una herramienta de autogeneración no aporta nada aquí.
5. **Unidad de trabajo por variable de contexto.** `Database.unit_of_work()` abre la transacción y
   la deja en una `ContextVar`. Los repositorios toman la conexión con `connection()` y fallan si
   no hay ninguna. Dos unidades de trabajo no se anidan. Así ningún repositorio abre una
   transacción, como pide 7.4, y cada tarea de asyncio tiene la suya.
6. **Escrituras sin carreras.**
   - Laguna: `ON CONFLICT DO UPDATE` con `occurrences + 1`. `last_seen` toma el mayor entre el
     guardado y el nuevo, en vez de `:now`, para que una llegada tardía no lo retrase.
   - Memoria: `hits + 1` por `(question_norm, locale)`. Además reactiva el ejemplo y sustituye
     plan y embedding por los del último.
   - Feedback: el upsert solo actualiza si cambian voto o comentario
     (`IS DISTINCT FROM`). `RETURNING (xmax = 0)` distingue creado, actualizado y sin cambios.
   - Mensajes: `seq` se calcula con la conversación bloqueada (`FOR UPDATE`).
7. **Evidencia.** El puerto `ConversationRepository` no tiene método de evidencia. El adaptador
   añade `append_evidence(message_id, facts)`, que resuelve cada `call_id` contra las llamadas del
   mensaje y se usa en la misma unidad de trabajo. Un valor numérico va exacto a `value_num`; un
   texto o un booleano (`'true'`/`'false'`), a `value_text`. El Prompt 8 lo llevará al puerto con
   la persistencia del turno. Las afirmaciones de anclaje (`grounding_claims`) tienen tabla, pero
   su escritura llega con el anclaje.
8. **JSON sin floats.** Las columnas `jsonb` viajan como texto serializado por el mapeador y se leen
   como texto con `parse_float=Decimal`.
   - El plan se guarda en su forma canónica (`canonical_json`) y se reconstruye con
     `plan_from_dict`.
   - En el brief, cada valor de hecho lleva su tipo y un `Decimal` se guarda como texto, así no
     cambian ni precisión ni escala. La carga lleva `version: 1`.
9. **Búsqueda vectorial exacta.** Los índices `ivfflat` son los de 7.3. Con pocas filas por lista,
   sondear una sola deja fuera vecinos que superan el umbral. Por eso cada búsqueda fija
   `SET LOCAL ivfflat.probes` al número de listas del índice. La similitud es `1 - (embedding <=>
   v)` y se filtra por el umbral en la consulta. Por debajo del umbral no se devuelve nada.
   La memoria además descarta planes de otra `plan_schema_version`. Un vector de otra dimensión lo
   rechaza el adaptador antes de escribir (`EmbeddingDimensionMismatchError`) y también la base.
10. **Política persistida.** `PgPolicy` implementa `PolicyPort` con el algoritmo de 7.9.3, y una
    prueba lo compara decisión a decisión con el doble en memoria. No es un repositorio: decide
    también fuera de una unidad de trabajo. Por eso lee con su propia conexión corta. Solo cuentan
    los principales activos. Si la base no responde, deniega con `policy_unavailable`, porque el
    puerto nunca lanza. `PgPolicyStore` escribe principales, roles, asignaciones y concesiones con
    upsert, y registra cada `PolicyDecision` dentro de la unidad de trabajo. La clave de
    `role_agent_grants` es `(role_id, agent_id)`, como en 7.9.7: dentro de un mismo rol hay una
    concesión por agente, y el deny que prevalece viene de otro rol.
11. **Escritura del corpus.** `KnowledgeRepository` solo busca. El adaptador añade
    `upsert_chunk`, que sustituye el fragmento con el mismo `(source, chunk_ix)`, para la ingesta.
12. **Regla de capas.** Un adaptador puede importar, además de los puertos, el vocabulario de sus
    firmas: `application.context`, `application.errors` y `application.jsontypes`. Un caso de
    uso, la planificación o cualquier otro paquete de aplicación siguen prohibidos, y una prueba
    negativa lo comprueba.
13. **Base de pruebas propia.** Las pruebas de repositorio usan `CARMEN_TEST_DATABASE_URL`, que por
    defecto es `carmen_test` en el PostgreSQL local, y crean la base si falta. Al empezar borran sus
    esquemas y migran desde cero, y antes de cada prueba vacían las tablas: nunca tocan la base de
    desarrollo. Sin la variable y sin servidor se saltan, indicando cómo arrancarlo. Con la
    variable definida, como en CI, una base inaccesible es un fallo.
14. **Imagen fijada.** CI, `ops/docker-compose.dev.yml` y `POSTGRES_IMAGE` en `ops/versions.env`
    usan `pgvector/pgvector:0.8.1-pg16` por digest. La composición solo trae PostgreSQL; el
    servidor MCP simulado llega con el Prompt 9.
15. **CI y cobertura.** La etapa 5 ejecuta:
    - la migración y `--check`;
    - las pruebas de repositorio con cobertura de `adapters/persistence` y `migrations`, con los
      mínimos de 8.2;
    - las mismas pruebas diez veces seguidas, que es el criterio para continuar.

    La etapa 3 excluye esos módulos de su informe, porque se miden contra PostgreSQL real.

## Consecuencias

Un cambio de esquema exige una migración nueva: editar la 0001 hace fallar `--check` y bloquea
`apply`. La prueba de esquema compara columna a columna y por nulabilidad las tablas declaradas con
las migradas, así que un mapeador no puede escribir en una columna que no existe. Las enumeraciones
SQL se comparan con las del dominio. El Prompt 8 añade la 0002 y los repositorios de turno,
aprobación y ciclo de vida sobre esta misma unidad de trabajo, y entonces la evidencia y las
afirmaciones de anclaje pasan al puerto.
