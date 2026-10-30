"""Orden topológico por niveles, común al QueryPlan y al DelegationPlan."""

from collections.abc import Callable, Hashable, Mapping
from typing import TypeVar

_K = TypeVar("_K", bound=Hashable)


def topological_waves(
    dependencies: Mapping[_K, frozenset[_K]], order: Callable[[_K], int]
) -> tuple[tuple[_K, ...], ...] | None:
    """Nodos agrupados en oleadas (Kahn); los de una oleada no dependen entre sí.

    Devuelve None si hay un ciclo. Cada oleada sale ordenada por `order` para ser estable.
    """
    pending = {node: set(deps) for node, deps in dependencies.items()}
    done: set[_K] = set()
    waves: list[tuple[_K, ...]] = []
    while pending:
        ready = sorted((n for n, deps in pending.items() if deps <= done), key=order)
        if not ready:
            return None
        waves.append(tuple(ready))
        done.update(ready)
        for node in ready:
            del pending[node]
    return tuple(waves)
