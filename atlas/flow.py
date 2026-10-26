"""Manual process traversal and world-space curves, independent of the UI."""
from math import sqrt

from .model import AtlasError


class FlowRun:
    def __init__(self, flow, step_id=None):
        self.flow = flow
        self.current = step_id if flow.step(step_id) else flow.start_step_id
        self.trail = []
        self.arrival = None
        self.finished = False

    @property
    def choices(self):
        return self.flow.outgoing(self.current) if not self.finished else ()

    def jump(self, step_id):
        if self.flow.step(step_id) is None:
            raise AtlasError("That step no longer exists.")
        self.trail.clear()
        self.current, self.arrival, self.finished = step_id, None, False

    def next(self, connection_id=None):
        choices = self.choices
        if not choices:
            if self.current is not None and not self.finished:
                self.trail.append((self.current, self.arrival, self.finished))
                self.finished = True
            return
        if connection_id is None and len(choices) != 1:
            raise AtlasError("Choose a branch before continuing.")
        edge = next((edge for edge in choices if edge.id == connection_id), None) if connection_id else choices[0]
        if edge is None:
            raise AtlasError("That connection does not leave the current step.")
        self.trail.append((self.current, self.arrival, self.finished))
        self.arrival, self.finished = edge.id, edge.target_id is None
        if edge.target_id is not None:
            self.current = edge.target_id

    def previous(self):
        if self.trail:
            self.current, self.arrival, self.finished = self.trail.pop()


def flow_curve(start, end, bend=.20, radius=.085):
    """A trimmed quadratic curve; repeated concepts get a visible local loop."""
    delta = tuple(b-a for a, b in zip(start, end))
    distance = sqrt(sum(d*d for d in delta))
    if distance < 1e-6:
        from math import cos, sin, pi
        return tuple((start[0]+.24*sin(t), start[1]+.24*(1-cos(t)), start[2]+.08*sin(t/2))
                     for t in (pi/8 + i*(2*pi-pi/4)/31 for i in range(32)))
    direction = tuple(d/distance for d in delta)
    trim = min(radius, distance*.2)
    a, b = tuple(s+d*trim for s, d in zip(start, direction)), tuple(e-d*trim for e, d in zip(end, direction))
    normal = (-direction[1], direction[0], .3)
    length = sqrt(sum(n*n for n in normal))
    offset = min(.7, max(.16, distance*bend))
    control = tuple((s+e)/2+n/length*offset for s, e, n in zip(a, b, normal))
    return tuple(tuple((1-t)**2*s + 2*(1-t)*t*c + t*t*e for s, c, e in zip(a, control, b))
                 for t in (i/31 for i in range(32)))
