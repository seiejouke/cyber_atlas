"""Real 3D meshes, depth buffering and surface picking, rendered by VTK.

The GUI receives an in-memory PPM frame. This keeps native-window embedding
out of the prototype and avoids needing a second GUI framework. Rendering is
on demand, not a continuously running animation loop.
"""
from __future__ import annotations

from enum import Enum
from math import atan2, cos, exp, hypot, pi, sin

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

from .geometry import LAYER_HEIGHT, RADIAL_WIDTH, Mesh, layout_meshes, node_position, wedge_mesh
from .model import ANGULAR_SLOTS, BANDS, Design, LayerId, Node


class ProtocolFilter(Enum):
    UNASSIGNED = "unassigned"


NO_PROTOCOL_FILTER = ProtocolFilter.UNASSIGNED
NODE_RADIUS = .065


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


class Scene:
    def __init__(self, design: Design = Design()) -> None:
        self.design = design
        self.mode = "blocks"
        self._axis_actors: list[vtkActor] = []
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
        self._actor_ids: dict[str, str] = {}
        self.actors: dict[str, tuple[vtkActor, vtkActor]] = {}
        self.guides: dict[tuple[LayerId, int], vtkActor] = {}
        self.meshes: dict[str, Mesh] = {}
        sphere = vtkSphereSource()
        sphere.SetRadius(NODE_RADIUS)
        sphere.SetThetaResolution(24)
        sphere.SetPhiResolution(16)
        self._sphere_mapper = vtkPolyDataMapper()
        self._sphere_mapper.SetInputConnection(sphere.GetOutputPort())
        self._sphere_mapper.ScalarVisibilityOff()
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
        for position, intensity in (((0, 0, 1), 0.80), ((-1, 0.6, 0.7), 0.45)):
            light = vtkLight()
            light.SetLightTypeToCameraLight()
            light.SetPosition(*position)
            light.SetFocalPoint(0, 0, 0)
            light.SetIntensity(intensity)
            self.renderer.AddLight(light)
        self._reference_axis()
        self.reset_camera()

    def _line(self, start: tuple, end: tuple, width: float = 1.0) -> None:
        source = vtkLineSource()
        source.SetPoint1(*start)
        source.SetPoint2(*end)
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(source.GetOutputPort())
        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(rgb("#476579"))
        actor.GetProperty().SetLineWidth(width)
        actor.GetProperty().LightingOff()
        actor.PickableOff()
        self.renderer.AddActor(actor)
        self._axis_actors.append(actor)

    def _reference_axis(self) -> None:
        for actor in self._axis_actors:
            self.renderer.RemoveActor(actor)
        self._axis_actors.clear()
        self._line((0, 0, self.design.z_base - .3), (0, 0, -self.design.z_base + .3), 1.5)
        for i in range(len(self.design.layers) + 1):
            z = self.design.z_base + i
            self._line((-0.10, 0, z), (0.10, 0, z))

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
        preview, valid = self.preview_node, self.preview_valid
        self.mode = mode
        self.set_nodes(self.nodes)
        self.set_preview(preview, valid)

    def node_anchor(self, node: Node) -> tuple[float, float, float]:
        return node_position(node, self.design)

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
        self.set_selected(self.selected)
        self.set_layer_filter(self.layer_filter)

    def set_selected(self, node_id: str | None) -> None:
        self.selected = node_id
        for node in self.nodes:
            solid, outline = self.actors[node.id]
            selected = node.id == node_id
            color = self.design.layer(node.layer).color
            solid.SetScale(1.15 if self.mode == "nodes" and selected else 1.0)
            solid.GetProperty().SetColor(rgb(color, 1.10 if selected else 1.0))
            outline.GetProperty().SetColor(rgb("#fff0c2") if selected else rgb(color, 0.65))
            outline.GetProperty().SetLineWidth(2.0 if selected else 0.85)

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
        for node in self.nodes:
            solid, outline = self.actors[node.id]
            visible = self.is_visible(node)
            solid.SetVisibility(visible)
            outline.SetVisibility(visible and self.mode == "blocks")
        self._update_guides()
        self.renderer.ResetCameraClippingRange()

    def set_protocol_filter(self, protocol: str | ProtocolFilter | None) -> None:
        self.protocol_filter = protocol
        self.set_layer_filter(self.layer_filter)

    def is_visible(self, node: Node) -> bool:
        protocol_matches = self.protocol_filter is None or (
            node.protocol is None if self.protocol_filter is NO_PROTOCOL_FILTER else self.protocol_filter == node.protocol)
        return self.layer_filter in (None, node.layer) and protocol_matches

    def reset_camera(self) -> None:
        self.yaw = 135 * pi / 180
        self.elevation = 19 * pi / 180
        self.scale = max(4.80, len(self.design.layers) * .62)
        self.target = [0.0, 0.0, 0.0]
        self._apply_camera()

    def _apply_camera(self) -> None:
        camera = self.renderer.GetActiveCamera()
        radius = max(30.0, len(self.design.layers) * 1.5)
        direction = (cos(self.elevation) * cos(self.yaw), cos(self.elevation) * sin(self.yaw), sin(self.elevation))
        camera.SetPosition(*(self.target[i] + radius * direction[i] for i in range(3)))
        camera.SetFocalPoint(*self.target)
        camera.SetViewUp(0, 0, 1)
        camera.ParallelProjectionOn()
        camera.SetParallelScale(self.scale)
        self.renderer.ResetCameraClippingRange()

    def rotate(self, dx: float, dy: float) -> None:
        self.yaw -= dx * 0.007
        self.elevation = max(-1.30, min(1.30, self.elevation + dy * 0.006))
        self._apply_camera()

    def pan(self, dx: float, dy: float) -> None:
        units = 2 * self.scale / max(self.height, 1)
        right = (-sin(self.yaw), cos(self.yaw), 0)
        up = (-sin(self.elevation) * cos(self.yaw), -sin(self.elevation) * sin(self.yaw), cos(self.elevation))
        for i in range(3):
            self.target[i] += units * (-dx * right[i] + dy * up[i])
        self._apply_camera()

    def zoom(self, steps: float) -> None:
        self.scale = max(1.2, min(max(14.0, len(self.design.layers)), self.scale * exp(-steps * 0.10)))
        self._apply_camera()

    def frame(self, width: int, height: int) -> bytes:
        """Return a P6 PPM image in memory, understood directly by Tk PhotoImage."""
        self.width, self.height = max(1, width), max(1, height)
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
        angle = (atan2(wy, wx) + pi / 2) % (2 * pi)
        angular_slot = angle / (2 * pi) * ANGULAR_SLOTS
        slot = round(angular_slot - span / 2) if self.mode == "nodes" else int(angular_slot)
        return band, slot % ANGULAR_SLOTS

    def pick(self, x: float, y: float) -> str | None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return None
        if self.picker.Pick(x, self.height - 1 - y, 0, self.renderer):
            actor = self.picker.GetActor()
            if actor is not None:
                return self._actor_ids.get(actor.GetAddressAsString(""))
        return None

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.window.Finalize()
