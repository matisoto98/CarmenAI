"""Glosario transversal: no se unifica lo que no es equivalente (invariante 4, 10.5.8).

Una métrica con el mismo nombre en dos sistemas es un CONFLICTO salvo que exista una equivalencia
declarada que las una. Solo una equivalencia declarada como agregable permite sumar sus cifras.
Lo declarado vive en config/glossary.yaml y se revisa en pull request; aquí está la regla.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from carmen.domain.errors import MetricConflictError, ValidationError
from carmen.domain.system import SystemId


@dataclass(frozen=True, slots=True, order=True)
class MetricUse:
    """Una métrica tal y como la nombra un sistema."""

    system: SystemId
    metric: str

    def __post_init__(self) -> None:
        if not self.metric.strip():
            msg = "el nombre de métrica no puede estar vacío"
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class MetricEquivalence:
    """Métricas de sistemas distintos que significan lo mismo."""

    name: str
    members: frozenset[MetricUse]
    aggregable: bool
    definition: str

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.definition.strip():
            msg = "una equivalencia exige nombre y definición"
            raise ValidationError(msg)
        systems = [m.system for m in self.members]
        if len(set(systems)) != len(systems):
            msg = f"equivalencia {self.name}: un sistema aparece dos veces"
            raise ValidationError(msg)
        if len(systems) < 2:
            msg = f"equivalencia {self.name}: necesita al menos dos sistemas"
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class MetricConflict:
    """Conflicto declarado: mismo nombre, significado distinto en cada sistema."""

    metric: str
    systems: frozenset[SystemId]
    definitions: tuple[tuple[SystemId, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.metric.strip():
            msg = "un conflicto exige el nombre de la métrica"
            raise ValidationError(msg)
        if len(self.systems) < 2:
            msg = f"conflicto {self.metric}: necesita al menos dos sistemas"
            raise ValidationError(msg)
        unknown = {s for s, _ in self.definitions} - self.systems
        if unknown:
            msg = f"conflicto {self.metric}: definición de un sistema ajeno {sorted(unknown)}"
            raise ValidationError(msg)

    def definition_for(self, system: SystemId) -> str | None:
        return next((text for s, text in self.definitions if s == system), None)


@dataclass(frozen=True, slots=True)
class Glossary:
    equivalences: tuple[MetricEquivalence, ...] = ()
    conflicts: tuple[MetricConflict, ...] = ()

    def __post_init__(self) -> None:
        seen: dict[MetricUse, str] = {}
        for equivalence in self.equivalences:
            for member in equivalence.members:
                if member in seen:
                    msg = f"{member.system}.{member.metric} está en dos equivalencias"
                    raise ValidationError(msg)
                seen[member] = equivalence.name
        for conflict in self.conflicts:
            for system in conflict.systems:
                if MetricUse(system, conflict.metric) in seen:
                    msg = (
                        f"{system}.{conflict.metric} no puede ser a la vez equivalente "
                        "y conflictivo"
                    )
                    raise ValidationError(msg)

    def equivalence_of(self, use: MetricUse) -> MetricEquivalence | None:
        return next((e for e in self.equivalences if use in e.members), None)

    def conflicts_in(self, uses: Iterable[MetricUse]) -> tuple[MetricConflict, ...]:
        """Conflictos entre las métricas que va a usar un plan, antes de ejecutarlo.

        Una métrica homónima en dos o más sistemas es conflicto salvo que una misma equivalencia
        las cubra a todas. El conflicto aparece sin declararlo: basta con añadir el sistema.
        """
        by_name: defaultdict[str, set[SystemId]] = defaultdict(set)
        for use in uses:
            by_name[use.metric].add(use.system)
        found: list[MetricConflict] = []
        for metric in sorted(by_name):
            systems = by_name[metric]
            if len(systems) < 2:
                continue
            covering = {self.equivalence_of(MetricUse(s, metric)) for s in systems}
            if len(covering) == 1 and None not in covering:
                continue
            declared = next(
                (c for c in self.conflicts if c.metric == metric and systems <= c.systems), None
            )
            definitions = declared.definitions if declared is not None else ()
            kept = tuple((s, text) for s, text in definitions if s in systems)
            found.append(MetricConflict(metric, frozenset(systems), kept))
        return tuple(found)

    def ensure_no_conflicts(self, uses: Iterable[MetricUse]) -> None:
        conflicts = self.conflicts_in(uses)
        if conflicts:
            names = ", ".join(f"{c.metric} ({', '.join(sorted(c.systems))})" for c in conflicts)
            msg = f"métricas homónimas sin equivalencia declarada: {names}"
            raise MetricConflictError(msg)

    def can_aggregate(self, uses: Iterable[MetricUse]) -> bool:
        """Solo se suman métricas de varios sistemas si una equivalencia agregable las une."""
        distinct = set(uses)
        if len({u.system for u in distinct}) < 2:
            return len({u.metric for u in distinct}) <= 1
        covering = {self.equivalence_of(u) for u in distinct}
        if len(covering) != 1:
            return False
        (equivalence,) = covering
        return equivalence is not None and equivalence.aggregable
