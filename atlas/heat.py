"""Recorded-information metrics. Spatial adjacency is intentionally not an input."""
from collections import Counter
from dataclasses import dataclass
from math import log1p

from .model import Atlas

SUPPORT_WEIGHT = .25
CHILD_SUPPORT_LIMIT = 1.0
CLUSTER_SUPPORT_LIMIT = 4.0
HEAT_STOPS = ((0, "#78899b"), (1, "#6799ed"), (2, "#5bc9df"),
              (4, "#69c5b3"), (8, "#e6c46c"), (16, "#eea05d"), (32, "#e17951"))


@dataclass(frozen=True, slots=True)
class InformationHeat:
    own: int = 0
    support: float = 0.0

    @property
    def blended(self) -> float:
        return self.own + self.support


def information_heat(atlas: Atlas) -> dict[str, InformationHeat]:
    counts = Counter(entry.concept_id for entry in atlas.information_entries)
    support = Counter()
    for child in atlas.subconcepts:
        support[child.parent_id] += min(CHILD_SUPPORT_LIMIT, counts[child.id] * SUPPORT_WEIGHT)
    return {concept.id: InformationHeat(counts[concept.id], min(CLUSTER_SUPPORT_LIMIT, support[concept.id]))
            for concept in (*atlas.nodes, *atlas.subconcepts)}


def heat_color(value: float) -> str:
    """Anchored, bounded logarithmic palette; filters never alter the scale."""
    if value <= 0:
        return HEAT_STOPS[0][1]
    for (lower, start), (upper, end) in zip(HEAT_STOPS, HEAT_STOPS[1:]):
        if value <= upper:
            fraction = (log1p(value) - log1p(lower)) / (log1p(upper) - log1p(lower))
            channels = [round(int(start[i:i+2], 16) * (1 - fraction) + int(end[i:i+2], 16) * fraction)
                        for i in (1, 3, 5)]
            return "#" + "".join(f"{channel:02x}" for channel in channels)
    return HEAT_STOPS[-1][1]
