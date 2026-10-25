"""Local orbit geometry and rendering, separate from the fixed-slot grid."""
from math import hypot, pi

from vtkmodules.vtkFiltersSources import vtkRegularPolygonSource
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

from .geometry import ORBIT_RADIUS, node_position, orbit_position

CHILD_SCALE = .70


class OrbitScene:
    def _init_orbits(self):
        self.subconcepts = ()
        self.expanded_parent = None
        self.focused_parent = None
        self.selected_child = None
        self.orbit_actors = {}
        self._orbit_lines = []
        self._orbit_camera = None
        self.orbit_collision = False

    def set_subconcepts(self, children):
        self.subconcepts = children
        self._sync_orbits()

    def orbit_parent(self):
        parent = next((node for node in self.nodes if node.id == self.expanded_parent), None)
        if parent is not None and self.preview_valid and self.preview_node is not None and self.selected == parent.id:
            from dataclasses import replace
            parent = replace(self.preview_node, id=parent.id)
        return parent

    def expand_orbit(self, parent_id):
        if self.focused_parent is not None and self.focused_parent != parent_id:
            self.clear_orbit_focus()
        self.expanded_parent = parent_id
        self._sync_orbits()

    def collapse_orbit(self):
        self.clear_orbit_focus()
        self.expanded_parent = None
        self.selected_child = None
        self._sync_orbits()

    def focus_orbit(self):
        parent = self.orbit_parent()
        if parent is None or self.mode != "nodes" or not self.is_visible(parent):
            return
        if self._orbit_camera is None:
            self._orbit_camera = self.yaw, self.elevation, self.scale, tuple(self.target)
        self.focused_parent = parent.id
        self.target = list(node_position(parent, self.design))
        self.scale = .95
        self.elevation = pi / 3
        self._apply_camera()
        self.set_layer_filter(self.layer_filter)

    def clear_orbit_focus(self):
        self.focused_parent = None
        if self._orbit_camera is not None:
            self.yaw, self.elevation, self.scale, target = self._orbit_camera
            self.target = list(target)
            self._orbit_camera = None
            self._apply_camera()
        self.set_layer_filter(self.layer_filter)

    def _sync_orbits(self):
        from .scene import NODE_RADIUS, rgb
        for actor in self.orbit_actors.values():
            self._actor_ids.pop(actor.GetAddressAsString(""), None)
            self.renderer.RemoveActor(actor)
        for actor in self._orbit_lines:
            self.renderer.RemoveActor(actor)
        self.orbit_actors.clear()
        self._orbit_lines.clear()
        self.orbit_collision = False
        if self.mode != "nodes":
            return
        for node in self.nodes:
            visible = self.is_visible(node) and self.focused_parent in (None, node.id)
            self.actors[node.id][0].SetVisibility(visible)
        for actor in self._axis_actors:
            actor.SetVisibility(self.focused_parent is None)
        if self.focused_parent is None:
            self._style_axis()
            for actor in self._axis_connection_actors:
                actor.SetVisibility(self.connections_visible)
        for (layer, depth), actor in self.guides.items():
            actor.SetVisibility(self.focused_parent is None)
        for actor in self.connections.values():
            actor.SetVisibility(self.focused_parent is None)
        parent = self.orbit_parent()
        if parent is None or not self.is_visible(parent):
            return
        children = [child for child in self.subconcepts if child.parent_id == parent.id]
        if not children:
            return
        color = self.design.layer(parent.layer).color
        center = node_position(parent, self.design)
        circle = vtkRegularPolygonSource()
        circle.SetNumberOfSides(96)
        circle.SetRadius(ORBIT_RADIUS)
        circle.SetCenter(*center)
        circle.SetNormal(0, 0, 1)
        circle.GeneratePolygonOff()
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(circle.GetOutputPort())
        ring = vtkActor()
        ring.SetMapper(mapper)
        ring.PickableOff()
        ring.GetProperty().SetColor(rgb(color))
        ring.GetProperty().SetOpacity(.45)
        ring.GetProperty().LightingOff()
        self.renderer.AddActor(ring)
        self._orbit_lines.append(ring)
        for child in children:
            position = orbit_position(parent, child.orbit_slot, self.design)
            actor = vtkActor()
            actor.SetMapper(self._sphere_mapper)
            actor.SetPosition(*position)
            actor.SetScale(CHILD_SCALE * (1.2 if child.id == self.selected_child else 1))
            prop = actor.GetProperty()
            prop.SetColor(rgb("#70cbd8" if child.id == self.selected_child else color))
            prop.SetAmbient(.45)
            prop.SetDiffuse(.65)
            prop.SetSpecular(.4)
            self.renderer.AddActor(actor)
            self.orbit_actors[child.id] = actor
            self._actor_ids[actor.GetAddressAsString("")] = child.id
            start, end = self._trimmed_segment(center, position, NODE_RADIUS, NODE_RADIUS * CHILD_SCALE)
            self._line(start, end, 1.5 if child.id == self.selected_child else 1,
                       color=color, opacity=.8, collection=self._orbit_lines)
            if self.focused_parent is None:
                for other in self.nodes:
                    if other.id == parent.id or not self.is_visible(other):
                        continue
                    ox, oy, oz = self.node_anchor(other)
                    if abs(position[2] - oz) < NODE_RADIUS * 2 and hypot(position[0] - ox, position[1] - oy) < NODE_RADIUS * 2:
                        self.orbit_collision = True
        self.renderer.ResetCameraClippingRange()
