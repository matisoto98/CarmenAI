"""Fijaciones de la base de pruebas: migrada una vez por sesión y vacía antes de cada prueba.

Sin CARMEN_TEST_DATABASE_URL y sin PostgreSQL local, las pruebas de repositorio se saltan con
el comando que lo arranca: así `uv run pytest` sigue sirviendo en un portátil sin Docker. Con la
variable definida (CI la define) una base inaccesible es un fallo, nunca un salto.
"""

import asyncio
import os

import pytest

from repositories.pg import Pg, database_url, reset, truncate

START_HINT = "docker compose -f ops/docker-compose.dev.yml up -d postgres"


@pytest.fixture(scope="session")
def migrated() -> str:
    url = database_url()
    try:
        asyncio.run(reset(url))
    except OSError as error:
        if "CARMEN_TEST_DATABASE_URL" in os.environ:
            raise
        pytest.skip(f"PostgreSQL no disponible ({error}); arráncalo con: {START_HINT}")
    return url


@pytest.fixture
def pg(migrated: str) -> Pg:
    asyncio.run(truncate(migrated))
    return Pg(migrated)
