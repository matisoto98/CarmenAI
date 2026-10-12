"""Lectura y comprobación de ops/versions.env, única fuente de versiones (4.3)."""

import re
from enum import StrEnum
from pathlib import Path

# <digest>, <commit> y cualquier otro marcador pendiente, como <proxy-inferencia>.
_PLACEHOLDER = re.compile(r"<[^<>]+>")


class Profile(StrEnum):
    """Perfiles de composición (4.6.3, 4.6.4)."""

    DEV = "dev"
    DEV_OLLAMA = "dev-ollama"
    PROD = "prod"


class UnpinnedVersionError(ValueError):
    """versions.env contiene marcadores sin fijar en un perfil que no los admite."""

    def __init__(self, keys: list[str]) -> None:
        self.keys = keys
        super().__init__(f"versiones sin fijar en perfil prod: {', '.join(keys)}")


def parse_versions(text: str) -> dict[str, str]:
    """Convierte el contenido de versions.env en un diccionario clave → valor."""
    versions: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            msg = f"línea sin '=' en versions.env: {raw!r}"
            raise ValueError(msg)
        versions[key.strip()] = value.split(" #", 1)[0].strip()
    return versions


def load_versions(path: Path) -> dict[str, str]:
    """Lee versions.env desde disco."""
    return parse_versions(path.read_text(encoding="utf-8"))


def unpinned_keys(versions: dict[str, str]) -> list[str]:
    """Claves cuyo valor aún contiene un marcador, como <digest> o <commit>."""
    return sorted(key for key, value in versions.items() if _PLACEHOLDER.search(value))


def ensure_pinned(versions: dict[str, str], profile: Profile) -> None:
    """En prod no se admite ningún marcador; en dev sí (Prompt 0)."""
    if profile is not Profile.PROD:
        return
    keys = unpinned_keys(versions)
    if keys:
        raise UnpinnedVersionError(keys)
