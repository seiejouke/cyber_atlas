"""Stable, screen-space label placement without GUI or renderer dependencies."""
from dataclasses import dataclass
from math import hypot


@dataclass(frozen=True)
class LabelRequest:
    key: str
    anchor: tuple[float, float]
    size: tuple[float, float]
    gap: float = 12
    priority: int = 0


def overlaps(a, b, padding=4):
    return not (a[2]+padding <= b[0] or b[2]+padding <= a[0]
                or a[3]+padding <= b[1] or b[3]+padding <= a[1])


def inside(box, bounds):
    return bounds[0] <= box[0] and bounds[1] <= box[1] and box[2] <= bounds[2] and box[3] <= bounds[3]


class LabelLayout:
    def __init__(self):
        self.offsets = {}

    @staticmethod
    def box(request, offset):
        x, y = (a+b for a, b in zip(request.anchor, offset))
        return x, y, x+request.size[0], y+request.size[1]

    def prune(self, keys):
        self.offsets = {key: offset for key, offset in self.offsets.items() if key in keys}

    def _candidates(self, request, bounds):
        ax, ay = request.anchor
        width, height = request.size
        old = self.offsets.get(request.key)
        left, top, right, bottom = bounds
        if width > right-left or height > bottom-top:
            return []
        side = -1 if old is not None and old[0] < 0 else 1 if old is not None else (-1 if ax < (left+right)/2 else 1)
        offsets = []
        if old is not None:
            offsets.append(old)
        for step in range(9):
            shifts = (-height/2,) if step == 0 else (-height/2-step*(height+6), -height/2+step*(height+6))
            for dy in shifts:
                for direction in (side, -side):
                    offsets.append((request.gap if direction > 0 else -width-request.gap, dy))
        offsets.extend(((-width/2, -height-request.gap), (-width/2, request.gap)))
        # Edge callouts and wider columns use genuinely free space away from the node.
        xs = {left, right-width, max(left, min(right-width, ax-width/2))}
        columns = max(1, int((right-left)/(width+8)))
        xs.update(left + (right-left-width)*i/columns for i in range(columns+1))
        rows = max(1, int((bottom-top)/(height+6)))
        for x in sorted(xs):
            for row in range(rows+1):
                y = top + (bottom-top-height)*row/rows
                offsets.append((x-ax, y-ay))
        candidates = []
        seen = set()
        for dx, dy in offsets:
            x, y = max(left, min(right-width, ax+dx)), max(top, min(bottom-height, ay+dy))
            box = (x, y, x+width, y+height)
            if box in seen:
                continue
            seen.add(box)
            offset = x-ax, y-ay
            change = hypot(offset[0]-old[0], offset[1]-old[1]) if old else 0
            wrong_side = (offset[0] < 0) != (side < 0)
            score = change*4 + hypot(x+width/2-ax, y+height/2-ay)*.1 + (45 if wrong_side else 0)
            candidates.append((score, box))
        return [box for _, box in sorted(candidates, key=lambda entry: entry[0])]

    def place(self, requests, bounds, reserved=(), obstacles=(), *, moving=False):
        placed, occupied = {}, []
        requests = sorted(requests, key=lambda request: (-request.priority, request.key not in self.offsets, request.key))
        for request in requests:
            old = self.offsets.get(request.key)
            x, y = request.anchor
            radius = max(4, request.gap-12)
            marker = (x-radius, y-radius, x+radius, y+radius)
            if old is not None:
                box = self.box(request, old)
                hard = [*reserved, marker] + [b for b, priority in occupied if not moving or priority > 0]
                if inside(box, bounds) and not any(overlaps(box, other) for other in hard):
                    if moving or not any(overlaps(box, other) for other in obstacles):
                        placed[request.key] = box
                        occupied.append((box, request.priority))
                        continue
            candidates = self._candidates(request, bounds)
            blockers = [*reserved, marker] + [box for box, _ in occupied]
            box = next((box for box in candidates if not any(overlaps(box, other) for other in (*blockers, *obstacles))), None)
            # A selected/hovered callout may displace decorations, never controls or another label.
            if box is None and request.priority:
                box = next((box for box in candidates if not any(overlaps(box, other) for other in blockers)), None)
            if box is not None:
                placed[request.key] = box
                occupied.append((box, request.priority))
                self.offsets[request.key] = box[0]-request.anchor[0], box[1]-request.anchor[1]
        return placed
