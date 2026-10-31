# ADR-051: Concreciones del diagnóstico del MCP real de VigIA

- Estado: Aceptado
- Origen: Prompt 10
- Referencia: Documento Maestro v4.8, secciones 4.6.6, 5.16.1.1, 6.4, 7.8.1 y 7.11.3

## Contexto

El Prompt 10 pide ejecutar la batería de contrato del Prompt 9 contra el MCP real de VigIA en
modo informe, con un perfil `vigia-real` desactivado en CI. La única vía de acceso desde el Mac
es el puente `vigia-mcp-bridge.mjs` de 4.6.6, que habla MCP por stdio, presenta el certificado de
cliente y pone el token de Entra. El documento no fija cómo se habla stdio desde la batería, qué
lleva el informe ni cómo se mide lo que la batería no puede ver. El modo de trabajo (2.9) exige
registrar cada concreción.

## Decisión

1. **Transporte stdio en el cliente de la batería.** Con `command`, `McpClient` lanza el proceso
   y le habla JSON-RPC, un mensaje por línea. Descarta las líneas que no son JSON-RPC y espera
   cada respuesta con plazo, así que un puente mudo es un error de transporte y no un cuelgue.
   - La salida de error del puente se descarta, porque puede llevar detalles de su sesión.
     `CARMEN_BRIDGE_STDERR=1` la muestra para depurar.
   - La batería nunca ve el token: lo pone el puente.
2. **Dos maneras de elegir el destino.**
   - `CARMEN_MCP_TARGETS` admite `sistema=stdio:<orden>` además de `sistema=url`.
   - `CARMEN_CONTRACT_TARGET=vigia-real` lanza el puente: `node ~/bin/vigia-mcp-bridge.mjs` por
     defecto, o la orden de `CARMEN_VIGIA_BRIDGE`. Antes de lanzarlo comprueba tres cosas, y si
     falta alguna para con un error de uso:
     - el perfil dev (`CARMEN_PROFILE=dev`), porque el puente está prohibido fuera de dev (4.6.6);
     - que existan los ficheros de `VIGIA_MCP_CERT`, `VIGIA_MCP_KEY` y `VIGIA_MCP_CA`;
     - que exista el script del puente.
   - CI no define ninguna de las dos variables, y una prueba comprueba que los workflows no
     nombran el perfil.
   - Contra un destino externo se omiten las pruebas del propio simulado (marca `mock_only`).
3. **`--report RUTA` en conftest.py.** Una ruta relativa se toma desde la raíz del repositorio, así
   que la orden del Prompt 10, lanzada desde `api/`, escribe `docs/conformance/vigia.md`.
   - El informe se escribe al terminar la sesión aunque fallen pruebas.
   - Recoge el resultado de cada prueba con su motivo.
   - Por HTTP, el token se tacha antes de escribir.
   - Para que un fallo no corte la batería, la prueba de sobres del Prompt 9 anota el error de
     una herramienta y sigue con la siguiente.
4. **Pruebas de diagnóstico en `test_conformance.py`.** Cada herramienta se llama una vez por
   sesión con argumentos de ejemplo y las demás pruebas reutilizan esas llamadas. Cada prueba
   responde a una pregunta del Prompt 10:
   - forma del sobre frente a 6.4: claves, las que faltan y las que sobran;
   - hechos identificables con procedencia: key única, unidad y entidad en los hechos; versión y
     fecha en los pasajes;
   - `period_interpreted` en toda herramienta con periodo;
   - control de acceso del usuario (7.8.1): lo que no se lista y, pedido, se niega;
   - catálogo frente al golden set.
5. **Requisitos del golden set leídos de `eval/golden/**/*.yaml`.** Cada herramienta de
   `steps_min` y cada valor de `argumentos` se contrasta con el `inputSchema` publicado.
   - Bloquea un requisito no cubierto, salvo dos casos que solo se anotan como pendientes:
     - el caso declara `depende_de`, como F06 con P12;
     - la herramienta tiene roles restringidos en el catálogo de fixtures y la identidad del
       puente no la ve, como `correlate_events` sin ADMIN.
6. **Reglas de 5.16.1.1 como sondas sobre el catálogo observado.**
   - Una sonda que necesita una herramienta o un valor que no existe queda «no comprobable»;
     nunca se inventa.
   - Las cifras de la guía caducan y solo se anotan, «coincide» o «cambió».
   - Bloquean solo las reglas de comportamiento en las que se apoya Carmen:
     - el tope de periodos;
     - `correlate_events` negada sin ADMIN;
     - lavaderos con dos definiciones;
     - el recorte a 500 filas con aviso.
7. **Lo que la batería no puede medir se dice en el informe.** La audiencia y el scope del token
   de Entra viven en el puente. El informe da la orden para leerlos de la configuración del puente
   sin tocar el token. Una prueba aparte, solo en `vigia-real`, mide el TLS mutuo contra
   `CARMEN_VIGIA_URL` (por defecto `https://vigia.plenergy.local:8443/mcp`):
   - sin certificado de cliente debe cortarse el TLS;
   - con certificado y sin token, el servidor debe responder 401 o 403.

   Si la clave está cifrada, esa prueba se anota como no comprobable en vez de pedir la frase.
8. **`stdio_bridge.py`, un puente stdio → HTTP de pruebas.** Hace con mcp-mock lo que el puente
   real hace con VigIA. Así el transporte stdio y el perfil se prueban en CI sin VPN.

## Consecuencias

- La misma orden sirve para el simulado, para un servidor por URL y para VigIA real.
- El informe, el catálogo real en fixtures y la redacción de P11 y P12 dependen de una ejecución
  en el Mac con VPN y la sesión del puente iniciada. Hasta entonces `docs/conformance/vigia.md`
  no existe y ADR-034 sigue reservado.
- Ninguna prueba toca `api/src/` ni el servidor de VigIA.
