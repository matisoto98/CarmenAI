# ADR-050: Concreciones del servidor MCP simulado y la batería de contrato

- Estado: Aceptado
- Origen: Prompt 9
- Referencia: Documento Maestro v4.8, secciones 5.16.1.1, 6.4, 6.9 y 7.8.1

## Contexto

El Prompt 9 pide un servidor MCP determinista que cumpla 6.4 con herramientas de los dos
dominios, documentos, modos de fallo e identidad simulada. También pide una batería de contrato
parametrizada por URL, con un cliente propio de las pruebas, que el Prompt 10 apuntará al MCP
real de VigIA. El documento no fija transporte, forma de los tokens, formato de los modos de fallo
ni conjunto de datos. El modo de trabajo (2.9) exige registrar cada concreción.

## Decisión

1. **MCP real sobre HTTP transmitible, con la biblioteca estándar.**
   - Versión de protocolo 2025-11-25, la del MCP de VigIA (5.16.1.1).
   - JSON-RPC 2.0 por POST y sesión en `Mcp-Session-Id`.
   - Métodos: `initialize`, `ping`, `tools/list` y `tools/call`.
   - El sobre va en `structuredContent` y repetido como texto JSON.

   El simulado no tiene dependencias, así que su imagen es la oficial de Python fijada por digest
   (`PYTHON_IMAGE` en `ops/versions.env`), sin instalar nada.
2. **Dos sistemas en un proceso:** `vigia` (métricas) y `plenmind` (documental), en
   `/<sistema>/mcp`. Sus catálogos son copia de `eval/fixtures/catalog_*.json`, los mismos que el
   golden set. Una prueba compara lo que sirve `tools/list` con esos ficheros.
3. **Descriptor ampliado de 6.9.4.** Cada herramienta de `tools/list` lleva `result_kind` y `roles`
   junto a los campos de MCP. La batería lo exige, y medirá si VigIA lo cumple.
4. **Identidad simulada `sim:<ROL>:<usuario>[:<zona>]`, sin firma.** El simulado nunca recibe un
   token real. El RBAC es del sistema:
   - el catálogo decide qué herramientas ve y puede llamar cada rol: fuera de su rol es 403, y sin
     ADMIN no hay `correlate_events` (5.16.1.1);
   - un OPERATOR tiene zona y solo ve sus sedes. El mismo recurso devuelve cifras distintas, con el
     aviso `ambito_zona`, o 403 para una sede ajena.
5. **Errores con forma fija:**
   - parámetros inválidos o herramienta desconocida: error JSON-RPC -32602;
   - una herramienta que falla, incluido un periodo fuera del tope de 400 días: resultado con
     `isError`;
   - sin token: HTTP 401; sin permiso: HTTP 403;
   - método desconocido: -32601.
6. **Modos de fallo por entorno.** `MCP_MOCK_FAILURES` admite `slow:<ms>`, `error`, `forbidden`,
   `down` e `invalid`, por herramienta, por sistema o para todo. `down` cierra la conexión sin
   responder. `invalid` quita `passages` y declara `partial` sin avisos. Una regla mal escrita
   impide arrancar.
7. **Datos generados, cifras agregadas.**
   - Universo escrito a mano: 40 sedes en cinco zonas, con proveedor, monitores y lavadero.
   - Las alarmas de 430 días se generan con `random.Random(seed)` frente a un instante de
     referencia fijo (`MCP_MOCK_NOW`). El instante fija también `generated_at`.
   - Toda cifra se agrega en la llamada, y las pruebas comprueban que cuadran entre herramientas.
   - Reproduce los rasgos de 5.16.1.1, con sus avisos: los códigos de Alvic que no se cierran,
     «Error de impresora» en un tercio del volumen y las sedes degradadas por acumulación.
   - `site_resolver` usa una distancia de edición en la que las confusiones fonéticas (r/l, b/v…)
     cuestan medio punto. Así «Arcorcon» resuelve directo y «Alconcon» pide confirmación, como
     en el catálogo semilla.
8. **Determinismo.** Con la misma semilla y el mismo instante, todo el sobre se repite salvo
   `call_id` y `correlation_id`. Se comprueba con veinte llamadas por herramienta y entre dos
   procesos.
9. **Batería independiente de Carmen.**
   - `api/tests/contract/mcp_client.py` usa solo `urllib` y entiende respuestas JSON y SSE.
   - La batería valida cada sobre contra `contracts/mcp-envelope.schema.json` y añade lo que el
     esquema no expresa: sistema, herramienta y correlación de la llamada, `result_kind`,
     `period_interpreted` y errores.
   - Destinos: `CARMEN_MCP_TARGETS` y `CARMEN_MCP_TOKEN`; por defecto, un mcp-mock propio en un
     puerto libre.
   - Lo que solo vale para el simulado está en `test_mcp_mock.py`: determinismo, fallos,
     documentos, RBAC, agregación e inyección.
   - Una prueba impide que el simulado o la batería importen `carmen`.
10. **CI.** La etapa 6 ejecuta la batería contra el mcp-mock que arranca ella misma. Después
    construye la imagen con `docker compose`, espera a su healthcheck y repite la batería
    contra el contenedor.

## Consecuencias

Carmen puede desarrollarse y probarse contra MCP sin VPN. El Prompt 10 añade el perfil del MCP
real a `conftest.py` y ejecuta la misma batería en modo informe. El Prompt 11 conecta el
adaptador al simulado. Cuando el catálogo real sustituya al provisional en `eval/fixtures`, el
simulado debe actualizar su copia: la prueba de catálogo lo exige.
