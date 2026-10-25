"""Main-note counts, direct-child totals and a linear, green-free heat palette."""
from collections import Counter
from dataclasses import dataclass

from .model import Atlas

HEAT_PRESETS = {"A - Compact (1-9)": 9, "B - Balanced (1-16)": 16, "C - Extended (1-32)": 32}
DEFAULT_HEAT_PRESET = "B - Balanced (1-16)"
DEFAULT_HEAT_MAX = HEAT_PRESETS[DEFAULT_HEAT_PRESET]
# The neutral stop prevents RGB interpolation between cyan and yellow producing green.
HEAT_STOPS = ((1, "#2878ff"), (2, "#218fff"), (3, "#19a8ff"), (4, "#0fc3ff"),
              (5, "#00d2ff"), (6, "#9de8ff"), (6.5, "#f5f5f5"), (7, "#f5f0df"),
              (8, "#ffe58a"), (9, "#ffd940"), (10, "#ffbf3c"), (11, "#ffa638"),
              (12, "#ff8a35"), (13, "#ff7435"), (14, "#fb603a"), (15, "#f94f40"),
              (16, "#ef3f36"))


@dataclass(frozen=True, slots=True)
class InformationHeat:
    own: int = 0
    support: int = 0

    @property
    def blended(self) -> int:
        return self.own + self.support


def is_main_note_copy(entry, concept) -> bool:
    """Count exact main-note text copies once, even after a concept is renamed."""
    return entry.body.strip() == concept.notes.strip()


def information_heat(atlas: Atlas) -> dict[str, InformationHeat]:
    concepts = {concept.id: concept for concept in (*atlas.nodes, *atlas.subconcepts)}
    counts = Counter({identity: 1 for identity in concepts})
    counts.update(entry.concept_id for entry in atlas.information_entries
                  if not is_main_note_copy(entry, concepts[entry.concept_id]))
    support = Counter()
    for child in atlas.subconcepts:
        support[child.parent_id] += counts[child.id]
    return {concept.id: InformationHeat(counts[concept.id], support[concept.id])
            for concept in (*atlas.nodes, *atlas.subconcepts)}


def heat_color(value: float, ceiling: int = DEFAULT_HEAT_MAX) -> str:
    """Linearly map 1..ceiling onto blue..red; exact counts are never capped."""
    if ceiling not in HEAT_PRESETS.values():
        raise ValueError("Choose a heat ceiling of 9, 16 or 32.")
    if value <= 1:
        return HEAT_STOPS[0][1]
    value = 1 + (value - 1) * (DEFAULT_HEAT_MAX - 1) / (ceiling - 1)
    for (lower, start), (upper, end) in zip(HEAT_STOPS, HEAT_STOPS[1:]):
        if value <= upper:
            fraction = (value - lower) / (upper - lower)
            channels = [round(int(start[i:i+2], 16) * (1 - fraction) + int(end[i:i+2], 16) * fraction)
                        for i in (1, 3, 5)]
            return "#" + "".join(f"{channel:02x}" for channel in channels)
    return HEAT_STOPS[-1][1]
