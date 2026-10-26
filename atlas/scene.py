"""Real 3D meshes, depth buffering and surface picking, rendered by VTK.

The GUI receives an in-memory PPM frame. This keeps native-window embedding
out of the prototype and avoids needing a second GUI framework. Rendering is
on demand, not a continuously running animation loop.
"""
from __future__ import annotations

from enum import Enum
from math import atan2, exp, hypot, pi, sqrt

import vtkmodules.vtkRenderingOpenGL2  # noqa: F401: register OpenGL factories
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.vtkFiltersCore import vtkFeatureEdges, vtkPolyDataNormals
from vtkmodules.vtkFiltersSources import vtkLineSource, vtkRegularPolygonSource, vtkSphereSource
from vtkmodules.vtkRenderingCore import (
    vtkActor, vtkCellPicker, vtkLight, vtkPolyDataMapper, vtkRenderer,
    vtkRenderWindow, vtkWindowToImageFilter,
)

from .geometry import LAYER_HEIGHT, RADIAL_WIDTH, Mesh, adjacent_node_pairs, layout_meshes, node_position, wedge_mesh
from .model import ANGULAR_SLOTS, BANDS, CENTER_DEPTH, Design, LayerId, Node
from .orbit_scene import OrbitScene
from .flow_scene import FlowScene
from .heat import DEFAULT_HEAT_MAX, HEAT_PRESETS, InformationHeat, heat_color, information_heat
from .orientation import DEFAULT_ELEVATION, DEFAULT_YAW, camera_basis


class ProtocolFilter(Enum):
    UNASSIGNED = "unassigned"


NO_PROTOCOL_FILTER = ProtocolFilter.UNASSIGNED
NODE_RADIUS = .065
AXIS_NODE_RADIUS = .055


def rgb(hex_color: str, factor: float = 1.0) -> tuple[float, float, float]:
    return tuple(min(1.0, int(hex_color[i:i + 2], 16) / 255 * factor) for i in (1, 3, 5))


def polydata(mesh: Mesh) -> vtkPolyData:
    points = vtkPoints()
    for point in mesh.points:
        points.InsertNextPoint(*point)
    polygons = vtkCellArray()
    for face in mesh.faces:
        polygons.InsertNextCell(len(face))
        for index in face:
            polygons.InsertCellPoint(index)
    result = vtkPolyData()
    result.SetPoints(points)
    result.SetPolys(polygons)
    return result


class Scene(FlowScene, OrbitScene):
    def __init__(self, design: Design = Design()) -> None:
        self.design = design
        self.mode = "blocks"
        self.block_appearance = "outline"
        self.hovered: str | None = None
        self._axis_actors: list[vtkActor] = []
        self._axis_connection_actors: list[vtkActor] = []
        self.axis_markers: dict[LayerId, vtkActor] = {}
        self.renderer = vtkRenderer()
        self.renderer.SetBackground(rgb("#080f1b"))
        self.renderer.SetBackground2(rgb("#14253b"))
        self.renderer.SetGradientBackground(True)
        self.window = vtkRenderWindow()
        self.window.SetOffScreenRendering(True)
        self.window.SetMultiSamples(4)
        self.window.AddRenderer(self.renderer)
        self.window.SetSize(800, 650)
        self.capture = vtkWindowToImageFilter()
        self.capture.SetInput(self.window)
        self.capture.SetInputBufferTypeToRGB()
        self.capture.ReadFrontBufferOff()
        self.capture.ShouldRerenderOff()
        self.picker = vtkCellPicker()
        self.picker.SetTolerance(0.0005)
        self._outline_picker = vtkCellPicker()
        self._outline_picker.SetTolerance(.005)
        self._outline_picker.PickFromListOn()
        self._block_picker = vtkCellPicker()
        self._block_picker.SetTolerance(.0005)
        self._block_picker.PickFromListOn()
        self._block_pick_actors: dict[str, vtkActor] = {}
        self._actor_ids: dict[str, str] = {}
        self.actors: dict[str, tuple[vtkActor, vtkActor]] = {}
        self.guides: dict[tuple[LayerId, int], vtkActor] = {}
        self.connections: dict[tuple[str, str], vtkActor] = {}
        # Spatial adjacency only; explicit orbital relationships live in subconcepts.
        self.connection_pairs: tuple[tuple[str, str], ...] = ()
        self._connection_nodes: dict[tuple[str, str], frozenset[str]] = {}
        self.connections_visible = True
        self.heat_enabled = False
        self.heat_ceiling = DEFAULT_HEAT_MAX
        self.heat_metrics: dict[str, InformationHeat] = {}
        self.meshes: dict[str, Mesh] = {}
        sphere = vtkSphereSource()
        sphere.SetRadius(NODE_RADIUS)
        sphere.SetThetaResolution(24)
        sphere.SetPhiResolution(16)
        self._sphere_mapper = vtkPolyDataMapper()
        self._sphere_mapper.SetInputConnection(sphere.GetOutputPort())
        self._sphere_mapper.ScalarVisibilityOff()
        axis_sphere = vtkSphereSource()
        axis_sphere.SetRadius(AXIS_NODE_RADIUS)
        axis_sphere.SetThetaResolution(20)
        axis_sphere.SetPhiResolution(12)
        self._axis_sphere_mapper = vtkPolyDataMapper()
        self._axis_sphere_mapper.SetInputConnection(axis_sphere.GetOutputPort())
        self._axis_sphere_mapper.ScalarVisibilityOff()
        self.preview_actor: vtkActor | None = None
        self.preview_node: Node | None = None
        self.preview_valid = True
        self._preview_pick_actor: vtkActor | None = None
        self._preview_picker = vtkCellPicker()
        self._preview_picker.SetTolerance(0.0005)
        self._preview_picker.PickFromListOn()
        self.nodes: tuple[Node, ...] = ()
        self.selected: str | None = None
        self.layer_filter: LayerId | None = None
        self.protocol_filter: str | ProtocolFilter | None = None
        self.width, self.height = 800, 650
        self.closed = False
        self._init_orbits()
        self._init_flows()
        for position, intensity in (((0, 0, 1), 0.80), ((-1, 0.6, 0.7), 0.45)):
            light = vtkLight()
            light.SetLightTypeToCameraLight()
            light.SetPosition(*position)
            light.SetFocalPoint(0, 0, 0)
            light.SetIntensity(intensity)
            self.renderer.AddLight(light)
        self._reference_axis()
        self.reset_camera()

    def _line(self, start: tuple, end: tuple, width: float = 1.0, *,
              color: str = "#476579", opacity: float = 1.0,
              collection: list[vtkActor] | None = None) -> vtkActor:
        source = vtkLineSource()
        source.SetPoint1(*start)
        source.SetPoint2(*end)
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(source.GetOutputPort())
        actor = vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(rgb(color))
        prop.SetLineWidth(width)
        prop.SetOpacity(opacity)
        prop.LightingOff()
        actor.PickableOff()
        self.renderer.AddActor(actor)
        (self._axis_actors if collection is None else collection).append(actor)
        return actor

    def _reference_axis(self) -> None:
        for actor in self._axis_actors:
            self.renderer.RemoveActor(actor)
        self._axis_actors.clear()
        self._axis_connection_actors.clear()
        self.axis_markers.clear()
        if self.mode == "blocks":
            self._line((0, 0, self.design.z_base - .3), (0, 0, -self.design.z_base + .3), 1.5)
            for i in range(len(self.design.layers) + 1):
                z = self.design.z_base + i
                self._line((-0.10, 0, z), (0.10, 0, z))
            return

        centers = [(layer, self.design.z_base + index + .5)
                   for index, layer in enumerate(self.design.layers)]
        for (lower, lower_z), (upper, upper_z) in zip(centers, centers[1:]):
            midpoint = (lower_z + upper_z) / 2
            self._axis_connection_actors.append(
                self._line((0, 0, lower_z + AXIS_NODE_RADIUS), (0, 0, midpoint), 1.25,
                           color=lower.color, opacity=.62))
            self._axis_connection_actors.append(
                self._line((0, 0, midpoint), (0, 0, upper_z - AXIS_NODE_RADIUS), 1.25,
                           color=upper.color, opacity=.62))
        for layer, z in centers:
            self._line((AXIS_NODE_RADIUS, 0, z), (.14, 0, z), 1.0,
                       color=layer.color, opacity=.72)
            marker = vtkActor()
            marker.SetMapper(self._axis_sphere_mapper)
            marker.SetPosition(0, 0, z)
            marker.PickableOff()
            prop = marker.GetProperty()
            prop.SetColor(rgb(layer.color))
            prop.SetAmbient(.55)
            prop.SetDiffuse(.55)
            prop.SetSpecular(.4)
            prop.SetSpecularPower(24)
            self.renderer.AddActor(marker)
            self._axis_actors.append(marker)
            self.axis_markers[layer.id] = marker
        self._style_axis()
        for actor in self._axis_connection_actors:
            actor.SetVisibility(self.connections_visible)

    def _style_axis(self) -> None:
        selected = next((node for node in self.nodes if node.id == self.selected), None)
        for layer in self.design.layers:
            marker = self.axis_markers.get(layer.id)
            if marker is None:
                continue
            center_note = self.center_node(layer.id)
            marker.SetVisibility(center_note is None or not self.is_visible(center_note))
            active = selected is not None and selected.layer == layer.id
            marker.SetScale(1.35 if active else 1.0)
            marker.GetProperty().SetOpacity(1.0 if self.layer_filter in (None, layer.id) else .22)

    def set_design(self, design: Design) -> None:
        self.set_preview(None)
        self.design = design
        self._reference_axis()
        self._update_guides()

    def set_mode(self, mode: str) -> None:
        """Change only the presentation, preserving atlas and camera state."""
        if mode not in ("blocks", "nodes"):
            raise ValueError("View mode must be 'blocks' or 'nodes'.")
        if self.mode == mode:
            return
        if mode != "nodes" and self.focused_parent is not None:
            self.clear_orbit_focus()
        preview, valid = self.preview_node, self.preview_valid
        self.mode = mode
        self.hovered = None
        self._reference_axis()
        self.set_nodes(self.nodes)
        self.set_preview(preview, valid)

    def set_block_appearance(self, appearance: str) -> None:
        if appearance not in ("solid", "outline"):
            raise ValueError("Choose Solid or Outline.")
        self.block_appearance = appearance
        self._style_blocks()

    def set_hovered(self, node_id: str | None) -> None:
        if self.hovered != node_id:
            self.hovered = node_id
            self._style_blocks()

    def _style_blocks(self) -> None:
        if self.mode != "blocks":
            return
        wire = self.block_appearance == "outline"
        selected = next((node for node in self.nodes if node.id == self.selected and self.is_visible(node)), None)
        self._outline_picker.InitializePickList()
        self._block_picker.InitializePickList()
        for node in self.nodes:
            solid, outline = self.actors[node.id]
            visible = self.is_visible(node)
            picked = node.id == self.selected
            hovered = node.id == self.hovered
            active = selected is not None and node.layer == selected.layer
            color = self.design.layer(node.layer).color
            solid.SetVisibility(visible and (not wire or picked))
            outline.SetVisibility(visible)
            outline.SetPickable(wire)
            prop = outline.GetProperty()
            if picked:
                prop.SetColor(rgb("#fff0c2"))
                prop.SetOpacity(1.0)
                prop.SetLineWidth(2.3 if wire else 2.0)
            elif wire:
                prop.SetColor(rgb("#70cbd8") if hovered else rgb(color, 1.1 if active else 1.0))
                prop.SetOpacity(1.0 if hovered else .95 if active else .58)
                prop.SetLineWidth(2.0 if hovered else 1.45 if active else 1.0)
            else:
                prop.SetColor(rgb(color, .65))
                prop.SetOpacity(1.0)
                prop.SetLineWidth(.85)
            proxy = self._block_pick_actors[node.id]
            proxy.SetVisibility(visible)
            if visible:
                self._block_picker.AddPickList(proxy)
                self._outline_picker.AddPickList(outline)
        # In Outline, only the selected solid can occlude other geometry.
        self.picker.InitializePickList()
        self.picker.SetPickFromList(wire)
        if wire and selected is not None:
            self.picker.AddPickList(self.actors[selected.id][0])
        self.renderer.ResetCameraClippingRange()

    def node_anchor(self, node: Node) -> tuple[float, float, float]:
        return node_position(node, self.design)

    @property
    def heat_active(self) -> bool:
        return self.mode == "nodes" and self.heat_enabled

    def set_information(self, atlas) -> None:
        self.heat_metrics = information_heat(atlas)
        self.set_selected(self.selected)

    def set_heat_enabled(self, enabled: bool) -> None:
        self.heat_enabled = bool(enabled)
        self.set_selected(self.selected)

    def set_heat_ceiling(self, ceiling: int) -> None:
        if ceiling not in HEAT_PRESETS.values():
            raise ValueError("Choose a heat ceiling of 9, 16 or 32.")
        self.heat_ceiling = ceiling
        self.set_selected(self.selected)

    def concept_color(self, concept_id: str, layer: LayerId) -> str:
        if not self.heat_active:
            return self.design.layer(layer).color
        metric = self.heat_metrics.get(concept_id, InformationHeat())
        return heat_color(metric.blended, self.heat_ceiling)

    def _style_node(self, node: Node, actor: vtkActor) -> None:
        selected = node.id == self.selected
        actor.SetScale(1.15 if self.mode == "nodes" and selected and not self.heat_active and self.flow_note is None else 1.0)
        actor.GetProperty().SetColor(rgb(self.concept_color(node.id, node.layer),
                                        1.10 if selected and not self.heat_active else 1.0))
        actor.GetProperty().SetOpacity(.18 if self.flow_note is not None and node.id not in self.flow_concepts else 1)

    def layer_anchor(self, layer: LayerId) -> tuple[float, float, float]:
        return 0.0, 0.0, self.design.z_base + self.design.layer_index(layer) + .5

    def center_node(self, layer: LayerId) -> Node | None:
        """Return the note that occupies a layer's complete center, if any."""
        return next((node for node in self.nodes
                     if node.layer == layer and node.depth == CENTER_DEPTH and node.span == ANGULAR_SLOTS), None)

    @staticmethod
    def _trimmed_segment(start: tuple[float, float, float], end: tuple[float, float, float],
                         start_radius: float, end_radius: float) -> tuple[tuple, tuple] | None:
        delta = tuple(end[index] - start[index] for index in range(3))
        length = sqrt(sum(value * value for value in delta))
        if length <= start_radius + end_radius:
            return None
        unit = tuple(value / length for value in delta)
        return (tuple(start[index] + unit[index] * start_radius for index in range(3)),
                tuple(end[index] - unit[index] * end_radius for index in range(3)))

    def _clear_connections(self) -> None:
        for actor in self.connections.values():
            self.renderer.RemoveActor(actor)
        self.connections.clear()
        self.connection_pairs = ()
        self._connection_nodes.clear()

    def _connection_actor(self, segments: list[tuple[tuple, tuple]], color: str,
                          emphasized: bool) -> vtkActor:
        points = vtkPoints()
        lines = vtkCellArray()
        for start, end in segments:
            first = points.InsertNextPoint(*start)
            second = points.InsertNextPoint(*end)
            lines.InsertNextCell(2)
            lines.InsertCellPoint(first)
            lines.InsertCellPoint(second)
        data = vtkPolyData()
        data.SetPoints(points)
        data.SetLines(lines)
        mapper = vtkPolyDataMapper()
        mapper.SetInputData(data)
        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.PickableOff()
        prop = actor.GetProperty()
        prop.SetColor(rgb(color))
        prop.SetOpacity(.78 if emphasized else .30)
        prop.SetLineWidth(1.7 if emphasized else .9)
        prop.LightingOff()
        self.renderer.AddActor(actor)
        return actor

    def _connection_candidates(self) -> tuple[Node, ...]:
        # Build topology before visibility filtering. Hiding a node never
        # makes its former neighbors connect across the newly hidden gap.
        candidates = list(self.nodes)
        preview = self.preview_node
        if self.preview_valid and preview is not None:
            if self.selected is not None:
                candidates = [node for node in candidates if node.id != self.selected]
            candidates = [node for node in candidates if node.id != preview.id]
            candidates.append(preview)
        return tuple(candidates)

    def _update_connections(self) -> None:
        self._clear_connections()
        if self.mode != "nodes" or not self.connections_visible:
            return
        nodes = self._connection_candidates()
        by_id = {node.id: node for node in nodes}
        buckets: dict[tuple[LayerId, bool], list[tuple[tuple, tuple, frozenset[str]]]] = {}

        def add(layer_id: LayerId, start: tuple, end: tuple, node_ids: frozenset[str],
                start_radius: float = NODE_RADIUS, end_radius: float = NODE_RADIUS) -> None:
            segment = self._trimmed_segment(start, end, start_radius, end_radius)
            if segment is None:
                return
            emphasized = self.selected in node_ids or "preview" in node_ids
            buckets.setdefault((layer_id, emphasized), []).append((*segment, node_ids))

        visible_pairs = []
        for left_id, right_id in adjacent_node_pairs(nodes):
            left, right = by_id[left_id], by_id[right_id]
            if not self.is_visible(left) or not self.is_visible(right):
                continue
            add(left.layer, self.node_anchor(left), self.node_anchor(right), frozenset((left_id, right_id)))
            visible_pairs.append((left_id, right_id))
        self.connection_pairs = tuple(visible_pairs)

        for (layer_id, emphasized), entries in buckets.items():
            key = (repr(layer_id), "emphasized" if emphasized else "normal")
            self.connections[key] = self._connection_actor(
                [(start, end) for start, end, _ in entries],
                "#476579" if self.heat_active else self.design.layer(layer_id).color, emphasized)
            self._connection_nodes[key] = frozenset().union(*(node_ids for _, _, node_ids in entries))

    def set_connections_visible(self, visible: bool) -> None:
        self.connections_visible = bool(visible)
        for actor in self._axis_connection_actors:
            actor.SetVisibility(self.connections_visible)
        self._update_connections()
        self._sync_orbits()
        self.renderer.ResetCameraClippingRange()

    def _update_guides(self) -> None:
        for actor in self.guides.values():
            self.renderer.RemoveActor(actor)
        self.guides.clear()
        if self.mode != "nodes":
            return
        layer_ids = {layer.id for layer in self.design.layers}
        for node in self.nodes:
            key = node.layer, node.depth
            # set_design is followed by set_nodes when entries are reassigned.
            if key in self.guides or node.layer not in layer_ids or not self.is_visible(node):
                continue
            x, y, z = self.node_anchor(node)
            circle = vtkRegularPolygonSource()
            circle.SetNumberOfSides(128)
            circle.SetRadius(hypot(x, y))
            circle.SetCenter(0, 0, z)
            circle.SetNormal(0, 0, 1)
            circle.GeneratePolygonOff()
            mapper = vtkPolyDataMapper()
            mapper.SetInputConnection(circle.GetOutputPort())
            actor = vtkActor()
            actor.SetMapper(mapper)
            actor.PickableOff()
            prop = actor.GetProperty()
            prop.SetColor(rgb(self.design.layer(node.layer).color))
            prop.SetOpacity(.10)
            prop.SetLineWidth(.8)
            prop.LightingOff()
            self.renderer.AddActor(actor)
            self.guides[key] = actor

    def set_nodes(self, nodes: tuple[Node, ...]) -> None:
        # No empty grid cells are ever constructed or rendered.
        for solid, outline in self.actors.values():
            self.renderer.RemoveActor(solid)
            self.renderer.RemoveActor(outline)
        self.actors.clear()
        self._block_pick_actors.clear()
        self._outline_picker.InitializePickList()
        self._block_picker.InitializePickList()
        self.picker.PickFromListOff()
        self.meshes = layout_meshes(nodes, self.design)
        self._actor_ids.clear()
        self.nodes = nodes
        for node in nodes:
            mesh = self.meshes[node.id]
            if self.mode == "nodes":
                actor = vtkActor()
                actor.SetMapper(self._sphere_mapper)
                actor.SetPosition(*self.node_anchor(node))
                prop = actor.GetProperty()
                prop.SetAmbient(.45)
                prop.SetDiffuse(.65)
                prop.SetSpecular(.45)
                prop.SetSpecularPower(30)
                prop.SetInterpolationToPhong()
                # Keep the public actor pair consistent across view modes.
                # The UI draws selection halos in screen coordinates.
                outline = vtkActor()
                outline.SetMapper(self._sphere_mapper)
                outline.SetPosition(*self.node_anchor(node))
                outline.PickableOff()
                outline.VisibilityOff()
                self.renderer.AddActor(actor)
                self.renderer.AddActor(outline)
                self.actors[node.id] = actor, outline
                self._actor_ids[actor.GetAddressAsString("")] = node.id
                continue
            data = polydata(mesh)
            normals = vtkPolyDataNormals()
            normals.SetInputData(data)
            normals.SetFeatureAngle(35)
            normals.SplittingOn()
            normals.ConsistencyOn()
            normals.AutoOrientNormalsOn()
            mapper = vtkPolyDataMapper()
            mapper.SetInputConnection(normals.GetOutputPort())
            mapper.ScalarVisibilityOff()
            actor = vtkActor()
            actor.SetMapper(mapper)
            proxy = vtkActor()
            proxy.SetMapper(mapper)
            self._block_pick_actors[node.id] = proxy
            prop = actor.GetProperty()
            prop.SetAmbient(0.30)
            prop.SetDiffuse(0.68)
            prop.SetSpecular(0.08)
            prop.SetSpecularPower(16)
            # Edges follow the solid's contours; no distracting triangle grid.
            edges = vtkFeatureEdges()
            edges.SetInputData(data)
            edges.SetFeatureAngle(25)
            edges.BoundaryEdgesOn()
            edges.FeatureEdgesOn()
            edges.ManifoldEdgesOff()
            edges.NonManifoldEdgesOff()
            edge_mapper = vtkPolyDataMapper()
            edge_mapper.SetInputConnection(edges.GetOutputPort())
            edge_mapper.ScalarVisibilityOff()
            edge_mapper.SetResolveCoincidentTopologyToPolygonOffset()
            outline = vtkActor()
            outline.SetMapper(edge_mapper)
            outline.PickableOff()
            outline.GetProperty().LightingOff()
            self.renderer.AddActor(actor)
            self.renderer.AddActor(outline)
            self.actors[node.id] = actor, outline
            self.meshes[node.id] = mesh
            self._actor_ids[actor.GetAddressAsString("")] = node.id
            self._actor_ids[outline.GetAddressAsString("")] = node.id
            self._actor_ids[proxy.GetAddressAsString("")] = node.id
        self.set_selected(self.selected)
        self.set_layer_filter(self.layer_filter)

    def set_selected(self, node_id: str | None) -> None:
        self.selected = node_id
        for node in self.nodes:
            solid, outline = self.actors[node.id]
            selected = node.id == node_id
            color = self.design.layer(node.layer).color
            self._style_node(node, solid)
            outline.GetProperty().SetColor(rgb("#fff0c2") if selected else rgb(color, 0.65))
            outline.GetProperty().SetLineWidth(2.0 if selected else 0.85)
        self._style_axis()
        self._update_connections()
        self._style_blocks()
        self._sync_orbits()

    def set_preview(self, node: Node | None, valid: bool = True) -> None:
        self.preview_node, self.preview_valid = node, valid
        self._preview_picker.InitializePickList()
        self._preview_pick_actor = None
        if self.preview_actor is not None:
            self.renderer.RemoveActor(self.preview_actor)
            self.preview_actor = None
        if node is not None:
            if self.mode == "nodes":
                mapper = self._sphere_mapper
            else:
                data = polydata(wedge_mesh(node, design=self.design))
                edges = vtkFeatureEdges()
                edges.SetInputData(data)
                edges.SetFeatureAngle(25)
                edges.BoundaryEdgesOn()
                edges.FeatureEdgesOn()
                edges.ManifoldEdgesOff()
                edges.NonManifoldEdgesOff()
                mapper = vtkPolyDataMapper()
                mapper.SetInputConnection(edges.GetOutputPort())
                mapper.SetResolveCoincidentTopologyToPolygonOffset()
            actor = vtkActor()
            actor.SetMapper(mapper)
            if self.mode == "nodes":
                actor.SetPosition(*self.node_anchor(node))
                actor.GetProperty().SetRepresentationToWireframe()
            actor.PickableOff()
            actor.GetProperty().LightingOff()
            actor.GetProperty().SetColor(rgb("#70cbd8" if valid else "#ee9a9a"))
            actor.GetProperty().SetLineWidth(2.0)
            self.renderer.AddActor(actor)
            self.preview_actor = actor
            # A separate, unrendered solid makes the whole draft clickable,
            # including its faces, while the visible preview stays an outline.
            self._preview_pick_actor = vtkActor()
            if self.mode == "nodes":
                self._preview_pick_actor.SetMapper(self._sphere_mapper)
                self._preview_pick_actor.SetPosition(*self.node_anchor(node))
            else:
                pick_mapper = vtkPolyDataMapper()
                pick_mapper.SetInputData(data)
                self._preview_pick_actor.SetMapper(pick_mapper)
            self._preview_picker.AddPickList(self._preview_pick_actor)
        self._update_connections()
        self._sync_orbits()
        self.renderer.ResetCameraClippingRange()

    def pick_preview(self, x: float, y: float) -> bool:
        if self._preview_pick_actor is None or not (0 <= x < self.width and 0 <= y < self.height):
            return False
        if not self._preview_picker.Pick(x, self.height - 1 - y, 0, self.renderer):
            return False
        # The draft cannot be picked through a nearer saved surface.
        if self.picker.Pick(x, self.height - 1 - y, 0, self.renderer):
            camera = self.renderer.GetActiveCamera().GetPosition()
            distance = lambda point: sum((point[i] - camera[i]) ** 2 for i in range(3))
            if distance(self.picker.GetPickPosition()) + 1e-4 < distance(self._preview_picker.GetPickPosition()):
                return False
        return True

    def set_layer_filter(self, layer: LayerId | None) -> None:
        self.layer_filter = layer
        if self.focused_parent is not None:
            parent = next((node for node in self.nodes if node.id == self.focused_parent), None)
            if parent is None or not self.is_visible(parent):
                self.clear_orbit_focus()
        for node in self.nodes:
            solid, outline = self.actors[node.id]
            visible = self.is_visible(node)
            solid.SetVisibility(visible)
            outline.SetVisibility(visible and self.mode == "blocks")
        self._update_guides()
        self._style_axis()
        self._update_connections()
        self._style_blocks()
        self._sync_orbits()
        self.renderer.ResetCameraClippingRange()

    def set_protocol_filter(self, protocol: str | ProtocolFilter | None) -> None:
        self.protocol_filter = protocol
        self.set_layer_filter(self.layer_filter)

    def is_visible(self, node: Node) -> bool:
        protocol_matches = self.protocol_filter is None or (
            node.protocol is None if self.protocol_filter is NO_PROTOCOL_FILTER else self.protocol_filter == node.protocol)
        return self.layer_filter in (None, node.layer) and protocol_matches

    def reset_camera(self) -> None:
        self.yaw = DEFAULT_YAW
        self.elevation = DEFAULT_ELEVATION
        self.scale = max(4.80, len(self.design.layers) * .62)
        self.target = [0.0, 0.0, 0.0]
        self._apply_camera()

    def _apply_camera(self) -> None:
        camera = self.renderer.GetActiveCamera()
        radius = max(30.0, len(self.design.layers) * 1.5)
        _, up, direction = camera_basis(self.yaw, self.elevation)
        camera.SetPosition(*(self.target[i] + radius * direction[i] for i in range(3)))
        camera.SetFocalPoint(*self.target)
        camera.SetViewUp(*up)
        camera.ParallelProjectionOn()
        camera.SetParallelScale(self.scale)
        self.renderer.ResetCameraClippingRange()

    def rotate(self, dx: float, dy: float) -> None:
        self.yaw -= dx * 0.007
        self.elevation = max(-pi / 2, min(pi / 2, self.elevation + dy * 0.006))
        self._apply_camera()

    def pan(self, dx: float, dy: float) -> None:
        units = 2 * self.scale / max(self.height, 1)
        right, up, _ = camera_basis(self.yaw, self.elevation)
        for i in range(3):
            self.target[i] += units * (-dx * right[i] + dy * up[i])
        self._apply_camera()

    def zoom(self, steps: float) -> None:
        self.scale = max(1.2, min(max(14.0, len(self.design.layers)), self.scale * exp(-steps * 0.10)))
        self._apply_camera()

    def frame(self, width: int, height: int) -> bytes:
        """Return a P6 PPM image in memory, understood directly by Tk PhotoImage."""
        self.width, self.height = max(1, width), max(1, height)
        self.sync_flow_overlay()
        if self.window.GetSize() != (self.width, self.height):
            self.window.SetSize(self.width, self.height)
        self.window.Render()
        self.capture.Modified()
        self.capture.Update()
        image = self.capture.GetOutput()
        pixels = vtk_to_numpy(image.GetPointData().GetScalars()).reshape(self.height, self.width, 3)
        # VTK starts with the bottom scanline; PPM starts with the top one.
        header = f"P6\n{self.width} {self.height}\n255\n".encode("ascii")
        return header + pixels[::-1].tobytes()

    def project(self, point: tuple[float, float, float]) -> tuple[float, float, float]:
        self.renderer.SetWorldPoint(*point, 1.0)
        self.renderer.WorldToDisplay()
        x, y, depth = self.renderer.GetDisplayPoint()
        return x, self.height - 1 - y, depth

    def position_at(self, x: float, y: float, layer: LayerId, span: int = 1) -> tuple[int, int] | None:
        """Intersect the pointer ray with the active mode's placement plane.

        Nodes snap their footprint midpoint to the pointer. Blocks retain the
        existing top-face hit test and slot-boundary behavior.
        """
        if not (0 <= x < self.width and 0 <= y < self.height):
            return None
        ray = []
        for depth in (0.0, 1.0):
            self.renderer.SetDisplayPoint(x, self.height - 1 - y, depth)
            self.renderer.DisplayToWorld()
            world = self.renderer.GetWorldPoint()
            ray.append(tuple(v / world[3] for v in world[:3]))
        near, far = ray
        dz = far[2] - near[2]
        if abs(dz) < 1e-8:
            return None
        layer_offset = .5 if self.mode == "nodes" else 1
        plane = self.design.z_base + (self.design.layer_index(layer) + layer_offset) * LAYER_HEIGHT
        t = (plane - near[2]) / dz
        # The clip range bounds the geometry currently on screen, not the
        # editor's whole work plane. Empty outer slots can lie beyond it;
        # intersect the extended orthographic ray so those remain placeable.
        wx, wy = (near[i] + t * (far[i] - near[i]) for i in (0, 1))
        radius = hypot(wx, wy)
        if radius >= (len(BANDS) + 1) * RADIAL_WIDTH:
            return None
        band = int(radius / RADIAL_WIDTH) - 1
        if band == CENTER_DEPTH and span == ANGULAR_SLOTS and radius < 1e-8:
            return CENTER_DEPTH, 0
        angle = (atan2(wy, wx) + pi / 2) % (2 * pi)
        angular_slot = angle / (2 * pi) * ANGULAR_SLOTS
        slot = round(angular_slot - span / 2) if self.mode == "nodes" else int(angular_slot)
        return band, slot % ANGULAR_SLOTS

    def pick(self, x: float, y: float) -> str | None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return None
        if self.mode == "blocks" and self.block_appearance == "outline":
            # Edges win over the empty interiors of nearer outlined blocks.
            # A selected, opaque surface still hides edges behind it.
            filled = self.picker.Pick(x, self.height - 1 - y, 0, self.renderer)
            if self._outline_picker.Pick(x, self.height - 1 - y, 0, self.renderer):
                edge_depth = self.project(self._outline_picker.GetPickPosition())[2]
                if not filled or edge_depth <= self.project(self.picker.GetPickPosition())[2] + 1e-5:
                    return self._actor_ids.get(self._outline_picker.GetActor().GetAddressAsString(""))
            if filled:
                return self.selected
            if self._block_picker.Pick(x, self.height - 1 - y, 0, self.renderer):
                return self._actor_ids.get(self._block_picker.GetActor().GetAddressAsString(""))
            return None
        if self.picker.Pick(x, self.height - 1 - y, 0, self.renderer):
            actor = self.picker.GetActor()
            if actor is not None:
                return self._actor_ids.get(actor.GetAddressAsString(""))
        return None

    def label_visible(self, node: Node, x: float, y: float) -> bool:
        if self.mode == "nodes":
            actor = self.actors.get(node.id, (None,))[0] or self.orbit_actors.get(node.id)
            if actor is None or not actor.GetVisibility():
                return False
            if self.pick(x, y) == node.id:
                return True
            radius = NODE_RADIUS*max(actor.GetScale())*self.height/(2*self.scale)
            # A nearer sphere can cover the centre while the labelled sphere's rim remains visible.
            for dx, dy in ((.9, 0), (-.9, 0), (0, .9), (0, -.9),
                           (.64, .64), (.64, -.64), (-.64, .64), (-.64, -.64)):
                if self.pick(x+radius*dx, y+radius*dy) == node.id:
                    return True
            return False
        if self.mode == "blocks" and self.block_appearance == "outline":
            if node.id == self.hovered:
                return True
            if not self.occludes(x, y):
                return True
            anchor_depth = self.project(self.meshes[node.id].label_anchor)[2]
            return self.project(self.picker.GetPickPosition())[2] >= anchor_depth - 1e-5
        return self.pick(x, y) == node.id

    def occludes(self, x: float, y: float) -> bool:
        """Whether a rendered solid covers this pixel; empty outlines do not."""
        return (0 <= x < self.width and 0 <= y < self.height
                and bool(self.picker.Pick(x, self.height - 1 - y, 0, self.renderer)))

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.window.Finalize()
