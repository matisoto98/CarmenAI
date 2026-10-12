"""Roles de Carmen, derivados de los grupos del directorio activo (7.8.1)."""

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    OPERATOR = "OPERATOR"
    AUDITOR = "AUDITOR"
