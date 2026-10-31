# Carmen

Plataforma de gobierno y orquestación de agentes de Plenergy. La especificación que manda es el
Documento Maestro v4.8 (9 de octubre de 2026); este repositorio se construye prompt a prompt
según su sección 9.

Estado: **Prompt 0** (bootstrap y puertas de calidad). Todavía no hay lógica de negocio.

## Herramientas

| Herramienta | Versión |
|---|---|
| Python | 3.12 (fijado en `pyproject.toml` y `ops/versions.env`) |
| Node | 20 (`web/.nvmrc`) |
| uv | 0.11 o superior |
| Asistente de desarrollo | Claude Code 2.1.296 (8.5) |

`ops/versions.env` es la única fuente de versiones de imágenes y modelos (4.3). En el perfil
`prod` la aplicación no arranca si queda algún marcador como `<digest>`.

## Arranque local en macOS (4.6)

Todo es nativo arm64. Ajusta Docker Desktop antes de arrancar nada: Memory 6 GB, Swap 1 GB, CPUs 6.

```bash
brew install python@3.12 node@20 uv jq
brew install --cask docker

python3.12 -c "import platform; print(platform.machine())"   # -> arm64
node -p "process.arch"                                        # -> arm64

git clone https://github.com/matisoto98/CarmenAI.git && cd CarmenAI
uv sync                          # crea .venv con las dependencias bloqueadas de uv.lock
source .venv/bin/activate
pre-commit install
cd web && npm ci && cd ..
```

Si prefieres pip, `api/requirements-dev.lock` es la exportación de `uv.lock`:
`uv venv --python 3.12 && uv pip install -r api/requirements-dev.lock`.

PostgreSQL con pgvector corre en contenedor (`ops/docker-compose.dev.yml`, 4.6.2). Las migraciones
son SQL explícito en `api/migrations/` y se aplican y comprueban con:

```bash
docker compose -f ops/docker-compose.dev.yml up -d postgres
cd api && python -m carmen.migrations && python -m carmen.migrations --check
cd api && pytest tests/repositories -v
```

Las pruebas de repositorio usan su propia base, `carmen_test`, que crean si falta y borran y
migran al empezar: nunca tocan la de desarrollo. Sin PostgreSQL arrancado se saltan; en CI, que
define `CARMEN_TEST_DATABASE_URL`, fallan.

El servidor MCP simulado (`mcp-mock/`, Prompt 9) sirve un sistema de métricas y uno documental
conformes al contrato de 6.4, sin VPN. La batería de contrato lo arranca sola, o se apunta a
cualquier servidor con `CARMEN_MCP_TARGETS`:

```bash
docker compose -f ops/docker-compose.dev.yml up -d mcp-mock
uv run pytest api/tests/contract -v
```

Detalles de identidad simulada, modos de fallo y datos en `mcp-mock/README.md`.

El diagnóstico del MCP real de VigIA (Prompt 10) usa la misma batería en modo informe, a través
del puente de 4.6.6. Solo desde el Mac, con la VPN y la sesión del puente ya iniciada:

```bash
nc -vz 172.27.12.15 8443                     # si falla, es la VPN
node ~/bin/vigia-mcp-bridge.mjs --login      # solo si el puente pide iniciar sesión
export VIGIA_MCP_CERT=~/certs/<certificado>.pem VIGIA_MCP_KEY=~/certs/<clave>.pem \
       VIGIA_MCP_CA=~/certs/ca-root.pem
cd api && CARMEN_PROFILE=dev CARMEN_CONTRACT_TARGET=vigia-real \
    uv run pytest tests/contract -v --report docs/conformance/vigia.md
```

El informe se escribe en `docs/conformance/vigia.md` aunque fallen pruebas, y no lleva
credenciales. Las concreciones están en ADR-051. La API y el
frontend llegan en los Prompts 21 y 29.

## Validaciones

```bash
cd api && ruff check . && mypy src --strict && pytest -q
cd web && npm ci && npm run lint && npx tsc --noEmit && npm test
pre-commit run --all-files
```

La cobertura se exige por módulo (8.2), no globalmente:

```bash
pytest --cov --cov-report=json:coverage.json && python ops/scripts/check_coverage.py coverage.json
```

## Secretos

Ninguno en el repositorio. `ops/secrets.example.env` lista solo los nombres. Los valores viven en
el Llavero (Mac) o en el gestor de secretos (servidor). `detect-secrets` corre en pre-commit y en
CI y bloquea cualquier clave con forma de JWT o token. Si un falso positivo bloquea un commit,
se revisa con quien lleve la seguridad antes de actualizar `.secrets.baseline`.

## Integración continua (8.4)

Once etapas en `.github/workflows/ci.yml`. Las etapas 1 a 4 corren en cada push; de la 5 en
adelante, en `main` y en cada pull request. Una etapa sin pruebas todavía pasa e indica qué
prompt la llena.

## Material de referencia

- `docs/reference/carmen_simulador_whatsapp.html`: comportamiento de referencia del canal
  WhatsApp (5.17.11). Se abre en el navegador y no se modifica.
