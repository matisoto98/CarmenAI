# ADR-049: Concreciones de la migración 0002 y la persistencia del turno

- Estado: Aceptado
- Origen: Prompt 8
- Referencia: Documento Maestro v4.8, secciones 5.15.7, 6.3, 6.9.2, 6.12.5, 6.12.6, 6.12.8, 7.3.1, 7.4 y 7.11.2

## Contexto

El Prompt 8 pide la migración 0002 con el SQL de 7.3.1 y los repositorios de turno, ejecuciones,
aprobaciones, llamadas externas y ciclo de vida. La unidad de trabajo 1 de 7.4 se amplía con el
turno, sus ejecuciones, las decisiones de política y las llamadas externas. El resultado esperado
es poder reconstruir desde la base un turno multiagente: quién preguntó, en qué modo, con qué
agentes, con qué herramientas y a qué coste. El SQL de 7.3.1 no basta para devolver un
`ConversationTurn` igual al guardado, y el puerto `TurnRepository` del Prompt 5 no dice a qué
mensaje pertenece el turno. El modo de trabajo (2.9) exige registrar cada concreción.

## Decisión

1. **El mensaje del asistente es el turno.** 7.3.1 añade las columnas del turno a `messages`.
   Por eso `TurnRepository.save` recibe además `message_id`, el mensaje del asistente ya guardado
   con sus llamadas, y `results`, los `AgentResult` en el mismo orden que `turn.runs`. Estos
   aportan lo que `AgentRun` no lleva: la tarea, la versión del agente y el estado. El doble en
   memoria aplica las mismas reglas.
2. **Comprobaciones antes de escribir.** `save` falla con `ValidationError`, sin escribir nada,
   si:
   - los resultados no son las ejecuciones del turno;
   - el mensaje no existe, no es del asistente, o es de otra conversación u otro principal;
   - su estado no es el del turno;
   - la pregunta del turno no es el último mensaje del usuario anterior a la respuesta;
   - las aprobaciones del turno, o las de una ejecución, no son las guardadas;
   - una traza de herramienta no coincide con la llamada guardada;
   - la evidencia o una afirmación apuntan a una llamada o un hecho que no son del mensaje.

   Un turno ya guardado no se reescribe. Todo ocurre en la unidad de trabajo de quien llama: si
   falla cualquier paso, también se deshacen el mensaje y sus llamadas.
3. **Identificadores del dominio en texto**, como en ADR-048: `trn_`, `run_` y `apr_`, con el
   patrón del dominio. Las filas internas (`external_calls`, pasajes, adjuntos, historial del
   ciclo de vida) son `uuid`.
4. **Orden explícito.** El dominio guarda tuplas ordenadas, así que cada fila lleva su orden:
   - `ord` en ejecuciones, hechos, pasajes, adjuntos y afirmaciones;
   - `run_ord` en las llamadas, decisiones y llamadas externas de una ejecución.

   `get` ordena por ellos y nunca por un orden implícito.
5. **Columnas y tablas añadidas para reconstruir el turno.**
   - `evidence_passages` y `evidence_media` guardan los pasajes y los adjuntos, que 7.3.1 no
     declara. Un adjunto nunca lleva `data:` en `uri`, y un procedimiento exige `updated_at`.
   - `evidence_facts` añade el sistema, la métrica, el nombre de la entidad, la procedencia y
     `value_kind`, para devolver el valor con su tipo exacto.
   - `grounding_claims` añade `claim_key` y el tramo del texto (`span_start`, `span_end`).
   - `policy_decisions` añade `agent_run_id`, `run_ord` y los `scopes` concedidos.
   - `tool_calls` añade `agent_run_id` y `run_ord`.
6. **La evidencia pasa al puerto.** `append_evidence`, propio del adaptador desde ADR-048,
   desaparece: la evidencia y el anclaje se escriben con `TurnRepository.save`.
7. **Re-delegación derivada.** `agent_runs.redelegated` es verdadero cuando la tarea no está en
   el plan del turno (6.12.5). No hace falta pedírselo a quien llama.
8. **Aprobaciones por turno, no por mensaje.** Una aprobación se crea antes de que exista la
   respuesta, así que `approvals.turn_id` no referencia `messages`. Al guardar el turno, cada
   aprobación de una ejecución queda enlazada con ella (`agent_run_id`, `ON DELETE SET NULL`).
   `ck_decided` exige quien decide en approved y rejected, y lo prohíbe en pending y expired.
   Un disparador (`approvals_only_from_pending`) impide salir de un estado que no sea pending,
   aunque se escriba la tabla sin pasar por el repositorio. `decide` es una sola sentencia
   condicionada a pending y al plazo, y `expire_due` vence todas las vencidas en una sentencia.
9. **Llamadas externas.** La traza del dominio aún no lleva la decisión de exportación (6.12.7),
   así que `export_decision` admite nulo. `provider` también, porque una búsqueda web solo tiene
   dominios: `ck_ext_target` exige uno de los dos. En v1 la tabla debe seguir vacía.
10. **Ciclo de vida con historial.**
    - `register` solo da de alta en DISCOVERED y escribe la primera fila del historial, con motivo
      "alta".
    - `transition` bloquea la fila, comprueba la transición contra 7.11.2 y escribe el historial
      con autor y motivo no vacío.
    - `agent_lifecycle_history.seq` ordena dos cambios del mismo instante.
    - `ck_certified` exige responsable, fecha e informe para CERTIFIED.
11. **El plan como JSON explícito.** `messages.delegation_plan` se convierte campo a campo, con el
    dinero como texto. Se reconstruye con el constructor del plan, que vuelve a validar sus reglas.
12. **Módulos por agregado.** Los repositorios nuevos siguen 7.2:
    - `conversation/turns.py`, con `agent_runs.py`, `external_calls.py`, `evidence.py` y
      `delegation_plan.py` al lado;
    - `approvals/`;
    - `lifecycle/`.

## Consecuencias

Una consulta SQL sin el dominio responde quién preguntó, el modo, los agentes, las herramientas y
el coste de un turno, y `get` devuelve un `ConversationTurn` igual al guardado. La 0001 no cambia:
una prueba fija su sha256. La prueba de esquema compara también las tablas y las enumeraciones de
la 0002. Quien persista un turno (el supervisor, a partir de los Prompts 16 y 17) lo hace en la misma unidad de
trabajo que la respuesta y le pasa los `AgentResult` que obtuvo.
