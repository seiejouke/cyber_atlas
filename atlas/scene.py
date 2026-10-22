"""Real 3D meshes, depth buffering and surface picking, rendered by VTK.

The GUI receives an in-memory PPM frame. This keeps native-window embedding
out of the prototype and avoids needing a second GUI framework. Rendering is
on demand, not a continuously running animation loop.
"""
from __future__ import annotations

from math import cos, exp, pi, sin

import vtkmodules.vtkRenderingOpenGL2  # noqa: F401: register OpenGL factories
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.vtkFiltersCore import vtkFeatureEdges, vtkPolyDataNormals
from vtkmodules.vtkFiltersSources import vtkLineSource
from vtkmodules.vtkRenderingCore import (
    vtkActor, vtkCellPicker, vtkLight, vtkPolyDataMapper, vtkRenderer,
    vtkRenderWindow, vtkWindowToImageFilter,
)

from .geometry import Mesh, Z_BASE, wedge_mesh
from .model import COLORS, Node


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
    def __init__(self) -> None:
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
        self.meshes: dict[str, Mesh] = {}
        self.nodes: tuple[Node, ...] = ()
        self.selected: str | None = None
        self.layer_filter: int | None = None
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

    def _reference_axis(self) -> None:
        self._line((0, 0, -3.8), (0, 0, 3.8), 1.5)
        for i in range(8):
            z = Z_BASE + i
            self._line((-0.10, 0, z), (0.10, 0, z))

    def set_nodes(self, nodes: tuple[Node, ...]) -> None:
        # No empty grid cells are ever constructed or rendered.
        for solid, outline in self.actors.values():
            self.renderer.RemoveActor(solid)
            self.renderer.RemoveActor(outline)
        self.actors.clear()
        self.meshes.clear()
        self._actor_ids.clear()
        self.nodes = nodes
        for node in nodes:
            mesh = wedge_mesh(node)
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
            solid.GetProperty().SetColor(rgb(COLORS[node.layer - 1], 1.10 if selected else 1.0))
            outline.GetProperty().SetColor(rgb("#fff0c2") if selected else rgb(COLORS[node.layer - 1], 0.65))
            outline.GetProperty().SetLineWidth(2.0 if selected else 0.85)

    def set_layer_filter(self, layer: int | None) -> None:
        self.layer_filter = layer
        for node in self.nodes:
            visible = layer is None or node.layer == layer
            for actor in self.actors[node.id]:
                actor.SetVisibility(visible)
        self.renderer.ResetCameraClippingRange()

    def reset_camera(self) -> None:
        self.yaw = 135 * pi / 180
        self.elevation = 19 * pi / 180
        self.scale = 4.80
        self.target = [0.0, 0.0, 0.0]
        self._apply_camera()

    def _apply_camera(self) -> None:
        camera = self.renderer.GetActiveCamera()
        radius = 30.0
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
        self.scale = max(1.2, min(14.0, self.scale * exp(-steps * 0.10)))
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
