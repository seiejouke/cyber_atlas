"""Independent, non-pickable world-space process arrows and referenced children."""
from math import sqrt

from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.vtkFiltersSources import vtkConeSource
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

from .flow import flow_curve
from .geometry import orbit_position


class FlowScene:
    def _init_flows(self):
        self.flow_note = None
        self.flow_concepts = frozenset()
        self.flow_concept_id = self.flow_step_id = self.flow_edge_id = self.flow_arrival = None
        self.flow_actors, self.flow_child_actors, self.flow_paths = {}, {}, {}
        self._flow_signature = None

    def concept_point(self, identity):
        node = next((n for n in self.nodes if n.id == identity), None)
        if node is not None:
            return self.node_anchor(node)
        child = next((c for c in self.subconcepts if c.id == identity), None)
        parent = next((n for n in self.nodes if child is not None and n.id == child.parent_id), None)
        return orbit_position(parent, child.orbit_slot, self.design) if parent else None

    def concept_visible(self, identity):
        node = next((n for n in self.nodes if n.id == identity), None)
        if node is None:
            child = next((c for c in self.subconcepts if c.id == identity), None)
            node = next((n for n in self.nodes if child is not None and n.id == child.parent_id), None)
        return node is not None and self.is_visible(node)

    def set_flow(self, flow=None, *, current=None, chosen=None, arrival=None, linked=None):
        self.flow_note, self.flow_step_id = flow, current
        step = flow.step(current) if flow else None
        self.flow_concept_id = linked or (step.concept_id if step else None)
        self.flow_edge_id, self.flow_arrival = chosen, arrival
        self.flow_concepts = frozenset(({s.concept_id for s in flow.steps} | ({linked} if linked else set())) if flow else ())
        self.sync_flow_overlay()

    def _clear_flow_actors(self):
        for actors in self.flow_actors.values():
            for actor in actors:
                self.renderer.RemoveActor(actor)
        for actor in self.flow_child_actors.values():
            self._actor_ids.pop(actor.GetAddressAsString(""), None)
            self.renderer.RemoveActor(actor)
        self.flow_actors.clear()
        self.flow_child_actors.clear()
        self.flow_paths.clear()

    def sync_flow_overlay(self):
        key = (self.flow_note, self.flow_step_id, self.flow_concept_id, self.flow_edge_id, self.flow_arrival,
               self.mode, self.layer_filter, self.protocol_filter, id(self.nodes), id(self.subconcepts),
               id(self.heat_metrics), self.heat_enabled, self.heat_ceiling, self.expanded_parent,
               tuple(self.orbit_actors))
        if key == self._flow_signature:
            return
        self._flow_signature = key
        self._clear_flow_actors()
        for node in self.nodes:
            self._style_node(node, self.actors[node.id][0])
        if self.flow_note is None or self.mode != 'nodes':
            return
        from .scene import rgb
        for child in self.subconcepts:
            if child.id not in self.flow_concepts or child.id in self.orbit_actors or not self.concept_visible(child.id):
                continue
            parent = next(n for n in self.nodes if n.id == child.parent_id)
            actor = vtkActor()
            actor.SetMapper(self._sphere_mapper)
            actor.SetPosition(*self.concept_point(child.id))
            actor.SetScale(.70)
            actor.GetProperty().SetColor(rgb(self.concept_color(child.id, parent.layer)))
            actor.GetProperty().SetAmbient(.45)
            actor.GetProperty().SetDiffuse(.65)
            actor.GetProperty().SetSpecular(.4)
            self.renderer.AddActor(actor)
            self.flow_child_actors[child.id] = actor
            self._actor_ids[actor.GetAddressAsString('')] = child.id
        for index, edge in enumerate(self.flow_note.connections):
            source = self.flow_note.step(edge.source_id)
            target = self.flow_note.step(edge.target_id)
            start = self.concept_point(source.concept_id)
            if start is None or not self.concept_visible(source.concept_id):
                continue
            if target is not None:
                end = self.concept_point(target.concept_id)
                if end is None or not self.concept_visible(target.concept_id):
                    continue
            else:
                end = start[0]+.45, start[1]+.25, start[2]+.22
            curve = flow_curve(start, end, bend=.18 + (index % 3)*.04)
            points, cells = vtkPoints(), vtkCellArray()
            for point in curve:
                points.InsertNextPoint(*point)
            cells.InsertNextCell(len(curve))
            for i in range(len(curve)):
                cells.InsertCellPoint(i)
            data = vtkPolyData()
            data.SetPoints(points)
            data.SetLines(cells)
            mapper = vtkPolyDataMapper()
            mapper.SetInputData(data)
            line = vtkActor()
            line.SetMapper(mapper)
            delta = tuple(e-s for s, e in zip(curve[-2], curve[-1]))
            length = sqrt(sum(d*d for d in delta))
            direction = tuple(d/max(length, 1e-9) for d in delta)
            cone = vtkConeSource()
            cone.SetResolution(12)
            cone.SetHeight(.11)
            cone.SetRadius(.035)
            cone.SetDirection(*direction)
            cone.SetCenter(*(e-d*.055 for e, d in zip(curve[-1], direction)))
            mapper = vtkPolyDataMapper()
            mapper.SetInputConnection(cone.GetOutputPort())
            head = vtkActor()
            head.SetMapper(mapper)
            active = edge.id in (self.flow_edge_id, self.flow_arrival)
            for actor in (line, head):
                actor.PickableOff()
                actor.GetProperty().SetColor(rgb('#70cbd8' if active else '#52788e'))
                actor.GetProperty().SetOpacity(.95 if active else .25)
                actor.GetProperty().LightingOff()
                self.renderer.AddActor(actor)
            line.GetProperty().SetLineWidth(2.5 if active else 1)
            self.flow_actors[edge.id] = line, head
            self.flow_paths[edge.id] = curve
        self.renderer.ResetCameraClippingRange()
