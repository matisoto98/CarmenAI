# mcp-mock — servidor MCP simulado de Carmen

Servidor determinista que cumple el contrato de 6.4 y 6.9.4 para desarrollar y ejecutar la
integración continua sin VPN. Solo usa la biblioteca estándar de Python 3.12 y no importa nada de
`carmen`.

## Arranque

```bash
docker compose -f ops/docker-compose.dev.yml up -d mcp-mock      # puerto 8765
python mcp-mock/server.py --port 8765                            # o sin contenedor
```

| Sistema    | Endpoint MCP        | Contenido                               |
|------------|---------------------|-----------------------------------------|
| `vigia`    | `/vigia/mcp`        | métricas: facts                         |
| `plenmind` | `/plenmind/mcp`     | documental: passages y media            |

También sirve `/health`, `/media/<documento>/<figura>` (PNG, con token) y `/doc/<documento>`.

## Protocolo

MCP 2025-11-25 sobre HTTP transmitible: JSON-RPC 2.0 por POST, `initialize` devuelve
`Mcp-Session-Id` y las demás peticiones lo exigen (400 si falta, 404 si no existe). Métodos:
`initialize`, `ping`, `tools/list` y `tools/call`. El resultado de `tools/call` lleva el sobre en
`structuredContent` y también como texto JSON.

## Identidad simulada y RBAC

Token `Bearer sim:<ROL>:<usuario>[:<zona>]` con ADMIN, MANAGER, OPERATOR o AUDITOR. Cualquier
otro es 401.

- `tools/list` solo ofrece las herramientas del rol, según el catálogo.
- Una herramienta fuera del rol es 403 (sin ADMIN no hay `correlate_events`).
- Un OPERATOR ve solo su zona (por defecto `centro`): las cifras de red salen de su zona, con el
  aviso `ambito_zona`, y una sede de otra zona es 403.

## Configuración

| Variable              | Por defecto              | Efecto                                   |
|-----------------------|--------------------------|------------------------------------------|
| `MCP_MOCK_SEED`       | `20260727`               | semilla del conjunto de datos            |
| `MCP_MOCK_NOW`        | `2026-07-27T09:14:22Z`   | instante de referencia de los periodos   |
| `MCP_MOCK_FAILURES`   | vacío                    | modos de fallo (`failure_modes.py`)      |
| `MCP_MOCK_PUBLIC_URL` | la del `Host`            | base de los enlaces a documentos y media |

Modos de fallo: `slow:<ms>`, `error`, `forbidden`, `down` e `invalid`, por
`sistema.herramienta`, `sistema.*` o `*`. Ejemplo: `vigia.query_metric=slow:3000;*=down`.

## Datos

- `dataset.py`: 40 sedes en cinco zonas. Las alarmas de 430 días se generan con la semilla.
  Cada cifra se agrega en la llamada.
- `documents.py`: los runbooks RB-041, RB-017 y RB-009 (este último, de 2023 y fuera de vigor),
  el manual MAN-112, un glosario y una imagen.
- Hay un registro con instrucciones embebidas en cada dominio, para las pruebas de inyección:
  una alarma de Alcorcón y la sección 9.9 de MAN-112.
- `catalogs/`: copia de `eval/fixtures/catalog_*.json`. Una prueba impide que se separen.

## Batería de contrato

```bash
uv run pytest api/tests/contract -v      # arranca su propio mcp-mock
CARMEN_MCP_TARGETS="vigia=https://…/mcp" CARMEN_MCP_TOKEN=… uv run pytest api/tests/contract/test_mcp_contract.py -v
```
