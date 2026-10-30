"""`python -m carmen.migrations [--check]`: aplica o comprueba las migraciones de api/migrations.

La base se toma de CARMEN_DATABASE_URL. Sin ella, la del entorno local (4.6.2).
"""

import argparse
import asyncio
import os
import sys

from carmen.adapters.persistence.migrator import MigrationError, apply, check

DEFAULT_URL = "postgresql://carmen:carmen@localhost:5432/carmen"  # pragma: allowlist secret


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m carmen.migrations")
    parser.add_argument(
        "--check",
        action="store_true",
        help="no aplica nada: falla si hay pendientes, modificadas o desconocidas",
    )
    args = parser.parse_args(argv)
    url = os.environ.get("CARMEN_DATABASE_URL", DEFAULT_URL)
    if args.check:
        report = asyncio.run(check(url))
        lines = [
            f"aplicadas: {', '.join(report.applied) or '-'}",
            f"pendientes: {', '.join(report.pending) or '-'}",
            f"modificadas: {', '.join(report.changed) or '-'}",
            f"desconocidas: {', '.join(report.unknown) or '-'}",
        ]
        sys.stdout.write("\n".join(lines) + "\n")
        return 0 if report.ok else 1
    try:
        done = asyncio.run(apply(url))
    except MigrationError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    sys.stdout.write(f"aplicadas ahora: {', '.join(done) or 'ninguna'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
