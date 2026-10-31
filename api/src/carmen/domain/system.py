"""Sistemas de la compañía que poseen datos (5.14.1)."""

import re

from carmen.domain.ids import PatternId


class SystemId(PatternId):
    """Sistema propietario de datos (6.2: ^[a-z][a-z0-9_-]{1,31}$)."""

    __slots__ = ()
    pattern = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
