"""Shared labels that follow nodes during camera motion and settle afterward."""
from math import hypot
from time import monotonic

from . import theme
from .geometry import orbit_position
from .label_layout import LabelLayout, LabelRequest, inside, overlaps


class LabelManager:
    SETTLE_MS = 150
    TRANSITION_SECONDS = .12

    def __init__(self, app):
        self.app = app
        self.layout = LabelLayout()
        self._camera = None
        self._context = None
        self._moving_until = 0
        self._settle_job = self._animation_job = None
        self._visibility = {}
        self._shown_offsets = {}
        self._transitions = {}
        self.hidden_count = 0
        self.placements = {}

    def _settle(self):
        self._settle_job = None
        self.app.request_render()

    def _animate(self):
        self._animation_job = None
        self.app.request_render()

    def _motion(self):
        app, scene = self.app, self.app.scene
        camera = scene.yaw, scene.elevation, scene.scale, tuple(scene.target), scene.width, scene.height
        now = monotonic()
        if self._camera is not None and camera != self._camera:
            self._moving_until = now + self.SETTLE_MS/1000
            if self._settle_job is not None:
                app.root.after_cancel(self._settle_job)
            self._settle_job = app.root.after(self.SETTLE_MS+10, self._settle)
        self._camera = camera
        context = scene.mode, scene.layer_filter, scene.protocol_filter, scene.focused_parent, scene.expanded_parent
        if context != self._context:
            self._visibility.clear()
            self._context = context
        moving = bool(now < self._moving_until or app._pressed is not None or app.compass._job is not None)
        if moving and self._transitions:
            self.layout.offsets.update(self._shown_offsets)
            self._transitions.clear()
        return moving

    def _visible(self, concept, key, x, y, priority, moving):
        if priority:
            return True
        if not moving or key not in self._visibility:
            self._visibility[key] = self.app.scene.label_visible(concept, x, y)
        return self._visibility[key]

    def _text(self, concept, child):
        scene, document = self.app.scene, self.app.document
        if child:
            text = concept.name
            if scene.heat_active:
                metric = scene.heat_metrics.get(concept.id)
                text += f" ({metric.own if metric else 0})"
        else:
            text = document.design.block_label(concept)
            if document.design.label_mode == "combined":
                text = f"{concept.name}\n{document.design.layer(concept.layer).name} · {document.design.protocol_name(concept.protocol)}"
            if scene.heat_active and (metric := scene.heat_metrics.get(concept.id)) is not None:
                text += f"\n{metric.blended} total" + (f" ({metric.own} own + {metric.support} from subconcepts)" if metric.support else "")
        width = min(300, scene.width-50) if child or document.design.label_mode != "title" else 176
        lines = text.splitlines() or [""]
        for i, line in enumerate(lines):
            while self.app.label_font.measure(line) > width and len(line) > 2:
                line = line[:-2]+"…"
            lines[i] = line
        return "\n".join(lines), (max(self.app.label_font.measure(line) for line in lines)+14, 23+17*(len(lines)-1))

    def draw(self, nodes, width, height):
        app, scene = self.app, self.app.scene
        moving = self._motion()
        valid = {f"{mode}:{concept.id}" for mode in ("nodes", "blocks")
                 for concept in (*app.document.nodes, *app.document.subconcepts)}
        self.layout.prune(valid)
        self._shown_offsets = {key: offset for key, offset in self._shown_offsets.items() if key in valid}
        self._visibility = {key: value for key, value in self._visibility.items() if key in valid}
        specs, requests, obstacles = {}, [], []
        if scene.mode == "nodes":
            obstacles.extend(app.information.indicator_boxes)
        concepts = [(node, False) for node in nodes]
        parent = scene.orbit_parent() if scene.mode == "nodes" else None
        if parent is not None and app._template_origin is None:
            concepts.extend((child, True) for child in scene.subconcepts
                            if child.parent_id == parent.id and child.id in scene.orbit_actors and scene.orbit_actors[child.id].GetVisibility())
        for concept, child in concepts:
            if child:
                point = orbit_position(parent, concept.orbit_slot, scene.design)
                actor = scene.orbit_actors[concept.id]
                selected = concept.id == scene.selected_child
            else:
                point = scene.node_anchor(concept) if scene.mode == "nodes" else scene.meshes[concept.id].label_anchor
                actor = scene.actors[concept.id][0]
                selected = concept.id == app.selected
            x, y, depth = scene.project(point)
            if not (0 <= depth <= 1 and 0 < x < width and 0 < y < height):
                continue
            key = f"{scene.mode}:{concept.id}"
            priority = 3 if selected else 2 if concept.id == app._hovered_node else 0
            if selected and not child and scene.selected_child is not None:
                priority = 1
            if not self._visible(concept, key, x, y, priority, moving):
                continue
            text, size = self._text(concept, child)
            radius = .065*max(actor.GetScale())*scene.height/(2*scene.scale) if scene.mode == "nodes" else 0
            gap = max(12, radius+16) if scene.mode == "nodes" else 12
            request = LabelRequest(key, (x, y), size, gap, priority)
            requests.append(request)
            specs[key] = concept.id, text, selected, child
            if scene.mode == "nodes":
                obstacles.append((x-radius-4, y-radius-4, x+radius+4, y+radius+4))
        if parent is not None and app.document.children(parent.id) and scene.is_visible(parent):
            x, y, _ = scene.project(scene.node_anchor(parent))
            count_width = app.label_font.measure(f"{len(app.document.children(parent.id))} subconcepts")
            obstacles.append((x-count_width/2, y+14, x+count_width/2, y+31))
        bounds = 8, 36, width-8, height-82
        reserved = list(app._axis_label_boxes)
        # Count message uses its own space, so it cannot cover a label.
        reserved.append((8, 58, min(width-170, 350), 82))
        self._transitions = {key: value for key, value in self._transitions.items() if key in specs}
        placed = self.layout.place(requests, bounds, reserved, obstacles, moving=moving)
        self.hidden_count = len(requests)-len(placed)
        now = monotonic()
        animation = False
        drawn = {}
        for request in sorted(requests, key=lambda request: request.priority):
            box = placed.get(request.key)
            if box is None:
                self._transitions.pop(request.key, None)
                continue
            desired = box[0]-request.anchor[0], box[1]-request.anchor[1]
            previous = self._shown_offsets.get(request.key)
            if not moving and previous is not None:
                transition = self._transitions.get(request.key)
                if transition is None and hypot(previous[0]-desired[0], previous[1]-desired[1]) > 1:
                    transition = previous, desired, now
                    self._transitions[request.key] = transition
                elif transition is not None and transition[1] != desired:
                    transition = previous, desired, now
                    self._transitions[request.key] = transition
                if transition is not None:
                    start, target, started = transition
                    amount = min(1.0, (now-started)/self.TRANSITION_SECONDS)
                    eased = amount*amount*(3-2*amount)
                    offset = tuple(a+(b-a)*eased for a, b in zip(start, target))
                    intermediate = self.layout.box(request, offset)
                    if inside(intermediate, bounds) and not any(overlaps(intermediate, other) for other in reserved):
                        box = intermediate
                        if amount < 1:
                            animation = True
                        else:
                            self._transitions.pop(request.key, None)
                    else:
                        self._transitions.pop(request.key, None)
            self._shown_offsets[request.key] = box[0]-request.anchor[0], box[1]-request.anchor[1]
            drawn[request.key] = box
            concept_id, text, selected, child = specs[request.key]
            bx, by, ex, ey = box
            x, y = request.anchor
            end_x, end_y = min(ex, max(bx, x)), min(ey, max(by, y))
            color = theme.ACCENT if child and selected else theme.GOLD if selected else "#456279"
            app.canvas.create_line(x, y, end_x, end_y, fill=color, tags="overlay")
            app.canvas.create_rectangle(*box, fill=theme.PANEL if child else "#1b3044" if selected else "#101e2e",
                outline=theme.ACCENT if child and selected else "#9d8d69" if selected else "#2a4155", tags=("overlay", "concept-label"))
            app.canvas.create_text(bx+7, (by+ey)/2, text=text, anchor="w",
                fill=theme.ACCENT if child and selected else "#fff0ca" if selected else theme.TEXT,
                font=app.label_font, tags=("overlay", "concept-label-text"))
            app._label_hits.append((concept_id, box))
        self.placements = drawn
        if animation and self._animation_job is None:
            self._animation_job = app.root.after(16, self._animate)
        if self.hidden_count:
            app.canvas.create_text(18, 63, anchor="nw", text=f"{self.hidden_count} labels hidden · zoom in for space",
                                   fill=theme.MUTED, font=(app.family, 8), tags=("overlay", "labels-hidden"))

    def close(self):
        for job in (self._settle_job, self._animation_job):
            if job is not None:
                self.app.root.after_cancel(job)
        self._settle_job = self._animation_job = None
