"""Identidad simulada y RBAC propio del servidor (6.9.8, 7.8.1).

El simulado acepta tokens con la forma `sim:<ROL>:<usuario>[:<zona>]`, con uno de los cuatro roles
de Carmen. No hay firma: es un servidor de desarrollo, y nunca recibe un token real. Cualquier
otro token es 401.

El RBAC es del sistema, no de Carmen, igual que en los reales:
  - cada herramienta declara sus roles en el catálogo, y tools/list solo ofrece las del rol;
  - llamar a una herramienta que el rol no tiene es 403 (sin ADMIN no hay correlate_events);
  - un OPERATOR ve solo las sedes de su zona (por defecto «centro»): las cifras de red se
    calculan sobre su zona, con aviso, y una sede de otra zona es 403.
"""

from dataclasses import dataclass
from typing import Final

from dataset import ZONES, Dataset, Site
from mock_errors import ForbiddenError, UnauthorizedError

ROLES: Final = ("ADMIN", "MANAGER", "OPERATOR", "AUDITOR")
DEFAULT_ZONE: Final = "centro"
_PREFIX: Final = "Bearer "
WITH_ZONE: Final = 4


@dataclass(frozen=True, slots=True)
class Principal:
    role: str
    user: str
    zone: str | None

    def visible_sites(self, data: Dataset) -> tuple[Site, ...]:
        if self.zone is None:
            return data.sites
        return tuple(s for s in data.sites if s.zone == self.zone)

    def require_site(self, site: Site) -> None:
        if self.zone is not None and site.zone != self.zone:
            msg = f"{self.user} ({self.role}, zona {self.zone}) no puede leer la sede {site.id}"
            raise ForbiddenError(msg)

    def require_role(self, tool: str, roles: list[str]) -> None:
        if self.role not in roles:
            msg = f"el rol {self.role} no tiene permiso para {tool}"
            raise ForbiddenError(msg)


def authenticate(header: str | None) -> Principal:
    if not header or not header.startswith(_PREFIX):
        msg = "falta el token Bearer"
        raise UnauthorizedError(msg)
    parts = header[len(_PREFIX) :].strip().split(":")
    if (
        len(parts) not in (WITH_ZONE - 1, WITH_ZONE)
        or parts[0] != "sim"
        or parts[1] not in ROLES
        or not parts[2]
    ):
        msg = "token no reconocido por el simulado"
        raise UnauthorizedError(msg)
    role, user = parts[1], parts[2]
    zone = parts[3] if len(parts) == WITH_ZONE else None
    if role == "OPERATOR":
        zone = zone or DEFAULT_ZONE
    elif zone is not None:
        msg = "solo un OPERATOR lleva zona"
        raise UnauthorizedError(msg)
    if zone is not None and zone not in ZONES:
        msg = f"zona desconocida: {zone}"
        raise UnauthorizedError(msg)
    return Principal(role, user, zone)
