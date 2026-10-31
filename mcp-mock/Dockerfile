# Servidor MCP simulado de Carmen (Prompt 9). Solo biblioteca estándar: sin dependencias.
# python:3.12.12-slim-bookworm, índice multiarquitectura (amd64 y arm64) fijado por digest,
# el mismo que PYTHON_IMAGE en ops/versions.env.
FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c

RUN useradd --create-home --uid 10001 mock
WORKDIR /srv/mcp-mock
COPY --chown=mock:mock . .
USER mock

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8765
HEALTHCHECK --interval=5s --timeout=2s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=2)"
CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8765"]
