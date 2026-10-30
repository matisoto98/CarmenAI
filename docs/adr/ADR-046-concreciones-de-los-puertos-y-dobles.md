# ADR-046: Concreciones de los puertos y sus dobles

- Estado: Aceptado
- Origen: Prompt 5
- Referencia: Documento Maestro v4.8, secciones 5.5, 5.13.4, 5.15.6, 6.4, 6.5, 6.6, 7.3, 7.4 y 7.9.3

## Contexto

El Prompt 5 declara los protocolos del inventario de 5.5 en `application/ports/` y un doble por puerto
en `api/tests/support/fakes/`. El inventario da las firmas y las excepciones de cada método, pero
deja sin definir los tipos que viajan por ellos, dónde viven las excepciones nuevas y cómo se
verifica la conformidad. El modo de trabajo (2.9) exige registrar estas decisiones.

## Decisión

1. **Excepciones de los puertos.** Cada «Lanza:» de 5.5 que no está en la taxonomía de 6.6 es un
   refinamiento en `application/errors.py` de una clase del dominio, y hereda su código
   (`McpToolError` es un `McpUnavailableError` y viaja como `mcp_unavailable`). Son 20 y ninguno
   define `code`, así que `errors.json` no cambia. Los nombres llevan el sufijo `Error` (N818). La
   prueba del catálogo de errores solo compara las clases del módulo del dominio.
2. **`PolicyPort` nunca lanza.** Sin regla aplicable, devuelve una decisión de denegación con su
   motivo (7.9.3). El doble aplica el mismo orden: deny explícito, sin grant, grant.
3. **`LlmPort.stream_text` es un `def` que devuelve `AsyncIterator`**, no una corrutina, para que el
   llamante itere directamente con `async for`.
4. **El token delegado viaja en `ToolInvocation`.** `TokenExchangePort` devuelve un `DelegatedToken`
   con audiencia, scopes y caducidad; el adaptador MCP lo recibe con cada llamada. El valor nunca
   aparece en `repr`.
5. **`UserToken` y `Requester` viven en `application/context.py`**, junto al `ExecutionContext`.
   El supervisor necesita el contexto y la prueba de arquitectura le prohíbe `ports.identity`.
6. **Los registros de cada puerto viven en su fichero** (`McpEnvelope` en `ports/mcp.py`,
   `NewMessage` en `ports/repositories.py`). Solo los usa quien usa el puerto.
7. **Eventos del dominio.** `application/events.py` define una carga tipada por cada evento de SSE
   1.1 con los mismos campos que el esquema, y la prueba de contratos los alinea campo a campo.
   `DomainEvent` lleva correlación, secuencia, instante y carga. `event_id` y `schema_version` los
   añade presentación, así que la raíz SSE sigue fijada por tabla.
8. **El sobre MCP pasa a tener tipo.** `McpEnvelope` y sus `Envelope*` sustituyen la tabla de campos
   de ADR-045 (punto 13). Las reglas de pasajes y adjuntos se aplican al convertirlos en evidencia.
9. **`MessageId` entra en el dominio**, con el patrón `msg_`, porque lo usan el contexto, los
   eventos y los repositorios.
10. **Repositorios.** Los métodos y sus registros salen de las tablas de 7.3 y 7.4. Un hilo de otra
    persona se devuelve como `None`, igual que uno inexistente. El feedback es idempotente por
    mensaje y persona, y un turno guardado no se reescribe.
11. **Dobles.** Cada doble recibe el reloj como el protocolo `Clock`. `FrozenClock` avanza con un
    paso fijo y nunca retrocede. `SeqIdGenerator` devuelve `000000000001`, `000000000002`, etc.
    `FakeEgress` registra el intento y deniega siempre. El cliente MCP en memoria sigue un guion
    hasta que el Prompt 9 traiga `mcp-mock`.
12. **Conformidad con mypy.** `test_conformance.py` asigna cada doble a una variable tipada con su
    protocolo y mypy estricto lo comprueba. mypy cubre `api/tests/support`. El resto de pruebas
    pasa tipos erróneos a propósito para probar la validación y queda fuera.
13. **Etapa de CI.** La etapa 3 ejecuta también `api/tests/support`.

## Consecuencias

Un puerto nuevo, un método nuevo o una excepción nueva hacen fallar la prueba de inventario hasta que
se actualizan `INVENTORY` y `EXPECTED_RAISES`. Una carga SSE nueva sin su clase en `events.py` hace
fallar la prueba de contratos. Los adaptadores de los Prompts 7, 9, 11 y 15 implementan estos
protocolos sin tocarlos. Si un adaptador necesita otra firma, se cambia aquí con un ADR.
