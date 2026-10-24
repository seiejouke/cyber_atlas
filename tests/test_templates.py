"""Built-in templates remain ordinary, editable Atlas documents."""
import unittest

from atlas.model import ANGULAR_SLOTS, CENTER_DEPTH, Atlas
from atlas.templates import TEMPLATES, find_template


class TemplateTests(unittest.TestCase):
    def test_catalog_has_general_topics_and_blank_start(self):
        self.assertEqual(
            tuple(template.name for template in TEMPLATES),
            ("Blank atlas", "Python", "TypeScript", "Web application", "Solar system", "Project planning"),
        )
        self.assertFalse(find_template("blank").atlas.nodes)

    def test_every_template_uses_the_normal_atlas_schema(self):
        for template in TEMPLATES:
            with self.subTest(template=template.name):
                self.assertEqual(Atlas.from_dict(template.atlas.to_dict()), template.atlas)
                self.assertTrue(template.atlas.design.layers)
                self.assertTrue(template.atlas.design.layer_caption)
                self.assertTrue(template.atlas.design.protocol_caption)

    def test_topics_have_varied_axis_and_node_counts(self):
        nonblank = TEMPLATES[1:]
        self.assertGreater(len({len(template.atlas.design.layers) for template in nonblank}), 1)
        self.assertGreater(len({len(template.atlas.nodes) for template in nonblank}), 1)
        for template in nonblank:
            with self.subTest(template=template.name):
                self.assertTrue(all(node.notes for node in template.atlas.nodes))
                centers = [node for node in template.atlas.nodes if node.depth == CENTER_DEPTH]
                self.assertEqual(len(centers), len(template.atlas.design.layers))
                self.assertTrue(all(node.span == ANGULAR_SLOTS and node.slot == 0 for node in centers))

    def test_template_node_ids_are_stable_and_unique_across_catalog(self):
        ids = [node.id for template in TEMPLATES for node in template.atlas.nodes]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(find_template("python").atlas.nodes[0].id, "template-python-1")

    def test_unknown_template_key_is_rejected(self):
        with self.assertRaises(KeyError):
            find_template("missing")


if __name__ == "__main__":
    unittest.main()
