"""Coordinate and pole conventions do not require Tk or VTK."""
from math import pi
import unittest

from atlas.orientation import aligned_view, axis_orientation, camera_basis, view_title


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


class OrientationTests(unittest.TestCase):
    def test_all_six_views_look_from_the_requested_axis(self):
        for index, axis in enumerate("XYZ"):
            for sign in (-1, 1):
                with self.subTest(axis=axis, sign=sign):
                    angles = axis_orientation(axis, sign)
                    self.assertEqual(aligned_view(*angles), (axis, sign))
                    direction = camera_basis(*angles)[2]
                    for i in range(3):
                        self.assertAlmostEqual(direction[i], sign if index == i else 0)

    def test_basis_stays_orthonormal_and_right_handed_at_and_near_poles(self):
        for yaw in (0, pi / 3, pi / 2, pi, 15 * pi):
            for elevation in (-pi / 2, -pi / 2 + 1e-8, -.3, 0, .3, pi / 2 - 1e-8, pi / 2):
                right, up, toward = camera_basis(yaw, elevation)
                for vector in (right, up, toward):
                    self.assertAlmostEqual(dot(vector, vector), 1)
                self.assertAlmostEqual(dot(right, up), 0)
                self.assertAlmostEqual(dot(right, toward), 0)
                self.assertAlmostEqual(dot(up, toward), 0)
                cross = (right[1]*up[2] - right[2]*up[1], right[2]*up[0] - right[0]*up[2],
                         right[0]*up[1] - right[1]*up[0])
                for actual, expected in zip(cross, toward):
                    self.assertAlmostEqual(actual, expected)

    def test_side_front_and_top_have_the_preview_screen_directions(self):
        side = camera_basis(*axis_orientation("X"))
        front = camera_basis(*axis_orientation("Y"))
        top = camera_basis(*axis_orientation("Z"))
        self.assertAlmostEqual(side[0][1], 1)  # +Y to the right
        self.assertAlmostEqual(front[0][0], -1)  # +X to the left
        self.assertAlmostEqual(side[1][2], 1)
        self.assertAlmostEqual(front[1][2], 1)
        self.assertAlmostEqual(top[0][0], 1)  # +X right, +Y up
        self.assertAlmostEqual(top[1][1], 1)
        bottom = camera_basis(*axis_orientation("Z", -1))
        self.assertAlmostEqual(bottom[0][0], -1)
        self.assertAlmostEqual(bottom[1][1], 1)

    def test_free_rotation_is_not_mislabeled_as_an_axis_view(self):
        self.assertIsNone(aligned_view(pi / 4, .3))
        self.assertIsNone(aligned_view(0, .001))
        self.assertEqual(view_title(pi / 4, .3), "SPATIAL VIEW")

    def test_view_titles_distinguish_signed_views_and_the_bottom(self):
        self.assertEqual(view_title(*axis_orientation("X")), "SIDE VIEW / +X")
        self.assertEqual(view_title(*axis_orientation("Y", -1)), "FRONT VIEW / -Y")
        self.assertEqual(view_title(*axis_orientation("Z")), "TOP VIEW / +Z")
        self.assertEqual(view_title(*axis_orientation("Z", -1)), "BOTTOM VIEW / -Z")


if __name__ == "__main__":
    unittest.main()
