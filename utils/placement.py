"""Pure geometry and numeric helpers for interactive light placement.

This module intentionally has no :mod:`bpy` or :mod:`mathutils` dependency so
the placement contract can be tested without starting Blender.  Blender-facing
operators convert vectors to and from three-item tuples at the boundary.
"""

from dataclasses import dataclass
from enum import Enum
from math import isfinite, pi, sqrt


Vector3 = tuple[float, float, float]
_EPSILON = 1.0e-8


class PlacementMode(str, Enum):
    DIRECT = "DIRECT"
    REFLECT = "REFLECT"
    ORBIT = "ORBIT"


@dataclass(frozen=True)
class PlacementSolution:
    target: Vector3
    position: Vector3
    direction_from_target: Vector3


def _vector(value) -> Vector3:
    if len(value) != 3:
        raise ValueError("Expected a three-component vector")
    result = tuple(float(component) for component in value)
    if not all(isfinite(component) for component in result):
        raise ValueError("Vector components must be finite")
    return result


def add(a, b) -> Vector3:
    a = _vector(a)
    b = _vector(b)
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def subtract(a, b) -> Vector3:
    a = _vector(a)
    b = _vector(b)
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def multiply(value, scalar: float) -> Vector3:
    value = _vector(value)
    scalar = float(scalar)
    if not isfinite(scalar):
        raise ValueError("Scalar must be finite")
    return (value[0] * scalar, value[1] * scalar, value[2] * scalar)


def dot(a, b) -> float:
    a = _vector(a)
    b = _vector(b)
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def length(value) -> float:
    value = _vector(value)
    return sqrt(dot(value, value))


def normalize(value, *, fallback: Vector3 | None = None) -> Vector3:
    value = _vector(value)
    magnitude = length(value)
    if magnitude > _EPSILON:
        return multiply(value, 1.0 / magnitude)
    if fallback is not None:
        fallback = _vector(fallback)
        fallback_length = length(fallback)
        if fallback_length > _EPSILON:
            return multiply(fallback, 1.0 / fallback_length)
    raise ValueError("Cannot normalize a zero-length vector")


def reflect_light_direction(view_from_surface, surface_normal) -> Vector3:
    """Return the surface-to-light direction that reflects toward the viewer.

    ``view_from_surface`` points from the surface hit toward the viewer.  The
    returned direction points from the same hit toward the light.
    """

    view = normalize(view_from_surface)
    normal = normalize(surface_normal)
    if dot(view, normal) < 0.0:
        normal = multiply(normal, -1.0)
    return normalize(subtract(multiply(normal, 2.0 * dot(normal, view)), view))


def placement_direction(
        mode: PlacementMode | str,
        surface_normal,
        view_from_surface,
        orbit_direction=None) -> Vector3:
    mode = PlacementMode(mode)
    normal = normalize(surface_normal)
    if mode == PlacementMode.DIRECT:
        return normal
    if mode == PlacementMode.REFLECT:
        return reflect_light_direction(view_from_surface, normal)
    if orbit_direction is not None:
        return normalize(orbit_direction, fallback=normal)
    return normal


def solve_placement(
        target,
        surface_normal,
        view_from_surface,
        distance: float,
        mode: PlacementMode | str,
        orbit_direction=None) -> PlacementSolution:
    target = _vector(target)
    distance = max(_EPSILON, float(distance))
    direction = placement_direction(
        mode,
        surface_normal,
        view_from_surface,
        orbit_direction,
    )
    return PlacementSolution(
        target=target,
        position=add(target, multiply(direction, distance)),
        direction_from_target=direction,
    )


def ray_plane_intersection(ray_origin, ray_direction, plane_point, plane_normal) -> Vector3 | None:
    """Intersect a ray with a plane, returning ``None`` behind or parallel."""

    origin = _vector(ray_origin)
    direction = normalize(ray_direction)
    point = _vector(plane_point)
    normal = normalize(plane_normal)
    denominator = dot(direction, normal)
    if abs(denominator) <= _EPSILON:
        return None
    ray_distance = dot(subtract(point, origin), normal) / denominator
    if ray_distance < 0.0:
        return None
    return add(origin, multiply(direction, ray_distance))


def adaptive_size_distance(diagonal: float) -> tuple[float, float]:
    """Choose a useful light size and distance from a target bounding diagonal."""

    diagonal = float(diagonal)
    if not isfinite(diagonal):
        raise ValueError("Diagonal must be finite")
    diagonal = max(0.0, diagonal)
    return max(0.25, diagonal * 0.5), max(1.0, diagonal * 1.5)


def scale_by_stops(value: float, stops: float, *, minimum: float, maximum: float) -> float:
    value = float(value)
    stops = float(stops)
    if not isfinite(value) or not isfinite(stops):
        raise ValueError("Value and stops must be finite")
    return min(float(maximum), max(float(minimum), value * (2.0 ** stops)))


def adjust_energy(energy: float, wheel_steps: int, ev_per_step: float = 0.25) -> float:
    return scale_by_stops(
        energy,
        int(wheel_steps) * float(ev_per_step),
        minimum=0.0,
        maximum=1.0e12,
    )


def adjust_size(size: float, wheel_steps: int) -> float:
    return scale_by_stops(size, int(wheel_steps) * 0.125, minimum=0.001, maximum=1.0e6)


def adjust_distance(distance: float, wheel_steps: int) -> float:
    return scale_by_stops(distance, int(wheel_steps) * 0.125, minimum=0.001, maximum=1.0e9)


def adjust_spot_size(spot_size: float, wheel_steps: int) -> float:
    return min(pi, max(0.001, float(spot_size) + int(wheel_steps) * (pi / 90.0)))


def adjust_roll(roll: float, wheel_steps: int) -> float:
    return float(roll) + int(wheel_steps) * (pi / 36.0)
