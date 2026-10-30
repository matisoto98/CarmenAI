# ADR-047: Concreciones del golden set inicial

- Estado: Aceptado
- Origen: Prompt 6
- Referencia: Documento Maestro v4.8, secciones 2.3.2 a 2.3.6, 5.16.1.1, 5.17.7, 6.2.2, 6.9.4 y 10.4

## Contexto

El Prompt 6 fija el criterio de aceptación antes de escribir el orquestador. 10.4 da un caso de
ejemplo, pero no un esquema. Tampoco existe todavía el catálogo real de VigIA (Prompt 12) ni el de
Plenmind. El modo de trabajo (2.9) exige registrar lo que se decide para poder escribir los casos.

## Decisión

1. **Esquema de casos propio.** `eval/schemas/golden-case.schema.json` formaliza el caso de 10.4
   con las mismas claves en español y sus tres niveles: plan, propiedades y rúbrica. Añade:
   - `modo_esperado` y `agentes`, porque el modo se clasifica antes que el plan (2.3.2).
   - `negativa` con su motivo, a partir de la tabla de 2.3.6, y `aclaracion` con el dato que falta
     (2.3.5).
   - `catalogo` para los casos de WhatsApp y `variantes_por_rol` para el comportamiento diferencial.
   - `depende_de` y `canonicos`.

   Las propiedades son un conjunto cerrado de claves, así que una propiedad inventada no valida.
2. **Motivos y avisos con nombre.** Los motivos de negativa salen de 2.3.6, más tres:
   - `no_se_registra`, para lo que la guía de VigIA dice que no existe.
   - `periodo_no_disponible`, porque VigIA tiene un tope de 400 días.
   - `canal_no_autorizado`, para una clasificación que no sale por WhatsApp.

   Los avisos obligatorios son las reglas de 5.16.1.1.
3. **Las negativas obligatorias se clasifican como REFUSE.** Carmen sabe por las reglas del agente
   que el dato no se registra. Por eso la respuesta no espera ninguna cifra y no se crea ningún
   AgentRun.
4. **Catálogos provisionales.** `catalog_vigia.json` solo contiene las herramientas que el
   documento nombra en 6.2.3 y 5.16.1.1: `site_resolver`, `query_metric`, `top_n`, `build_dossier`,
   `correlate_events` (solo ADMIN) y `get_situation_brief`. Las métricas y argumentos son una
   propuesta. Las series y la comparación de periodos son argumentos de `query_metric`
   (`granularity`, `compare_to`), sin herramientas nuevas. El de Plenmind contiene las seis
   herramientas de 6.9.4 y el `query_metric` del ejemplo multisistema de 6.2.3. Los dos llevan
   `provisional: true`, y el Prompt 12 sustituye el de VigIA por el real.
5. **Incidencias.** Los casos de incidencias marcan `depende_de: [P12]`. Su plan nombra una métrica
   que el catálogo aún no tiene, y la prueba no valida sus argumentos hasta ese prompt.
6. **A01 sin `correlate_events`.** El caso de 10.4 es de un MANAGER, y el ejemplo analítico de 6.2.3
   incluye `correlate_events`, que solo puede usar ADMIN. El plan canónico de A01 lo omite y lo
   prohíbe. A03 (ADMIN) y C02 (por rol) cubren la correlación.
7. **Forma normal del DelegationPlan.** El dominio solo tiene serialización canónica para el
   QueryPlan. El DelegationPlan sigue la misma regla de 6.2.2:
   - claves ordenadas;
   - tareas por `task_id` y dependencias ordenadas;
   - sin los valores por defecto (`depends_on: []`, `optional: false`,
     `requires_human_approval: false`).

   La prueba de `eval/` aplica esa regla y lee cada fichero con el tipo del dominio. Los ficheros se
   guardan indentados con claves ordenadas para que se puedan leer.
8. **Ubicación.** `eval/` está en la raíz, fuera del runtime (árbol del repositorio, 5.4). La prueba es
   `eval/tests/test_golden_wellformed.py` y se ejecuta con `uv run pytest eval/tests`. El comando
   del documento empieza con `cd api`, pero el proyecto tiene un único `pyproject.toml` en la raíz.
   La etapa 11 de CI la ejecuta antes del arnés. mypy estricto la cubre. PyYAML pasa a ser una
   dependencia de desarrollo explícita.
9. **Casos del catálogo.** Los mensajes del simulador (5.17.11) están en `golden/vigia/catalogo.yaml`,
   con el prefijo VC:
   - las dos erratas, que resuelven a Alcorcón;
   - la estación ambigua («Madrid»), seguida de «@carmen 2»;
   - «@carmen ayuda»;
   - una pregunta fuera de catálogo y una de clasificación restringida;
   - un mensaje de grupo sin mención, que no abre turno y no lleva modo.

   Se añade un caso de plantilla correcta como referencia de su plan canónico.

## Consecuencias

Un caso que nombra una herramienta, un argumento o un valor fuera del catálogo hace fallar la
prueba. También falla un plan que no está en forma normal o una herramienta obligatoria que el rol
del caso no puede usar. Cuando el Prompt 12 traiga el catálogo real, los casos que dependen de P12
se tienen que validar ya, y cualquier diferencia de nombres se corrige en los casos. Las ampliaciones
del conjunto hacia los setenta casos de 10.4 usan este mismo esquema.
