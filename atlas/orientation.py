"""Camera directions shared by the scene and its orientation compass."""
from math import cos, pi, sin


DEFAULT_YAW = 135 * pi / 180
DEFAULT_ELEVATION = 19 * pi / 180


def camera_basis(yaw, elevation):
    """Screen right, screen up and toward the viewer, including both poles."""
    return (
        (-sin(yaw), cos(yaw), 0.0),
        (-sin(elevation) * cos(yaw), -sin(elevation) * sin(yaw), cos(elevation)),
        (cos(elevation) * cos(yaw), cos(elevation) * sin(yaw), sin(elevation)),
    )


def aligned_view(yaw, elevation):
    direction = camera_basis(yaw, elevation)[2]
    for index, axis in enumerate("XYZ"):
        if abs(direction[index]) > 1 - 1e-10:
            return axis, 1 if direction[index] > 0 else -1
    return None


def axis_orientation(axis, sign=1):
    """Look from a signed world axis; top and bottom keep world Y upright."""
    return {
        ("X", 1): (0.0, 0.0), ("X", -1): (pi, 0.0),
        ("Y", 1): (pi / 2, 0.0), ("Y", -1): (-pi / 2, 0.0),
        ("Z", 1): (-pi / 2, pi / 2), ("Z", -1): (pi / 2, -pi / 2),
    }[(axis.upper(), sign)]


def view_title(yaw, elevation):
    view = aligned_view(yaw, elevation)
    if view is None:
        return "SPATIAL VIEW"
    axis, sign = view
    name = {"X": "SIDE", "Y": "FRONT", "Z": "TOP" if sign > 0 else "BOTTOM"}[axis]
    return f"{name} VIEW / {'+' if sign > 0 else '-'}{axis}"
