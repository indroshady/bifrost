"""Pure deterministic XY routing for the Bifröst coordinate convention.

The function has no router state and is shared by allocation logic and tests.
Increasing Y means North, as frozen by Core v0.2.
"""

from __future__ import annotations

from enum import Enum


class RoutingError(ValueError):
    """Raised when coordinates or mesh dimensions are invalid."""


class Port(str, Enum):
    """Physical port names in the frozen package ordering."""

    LOCAL = "local"
    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"


def _coordinate(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RoutingError(f"{name} must be an integer")
    return value


def route_xy(
    *,
    current_x: int,
    current_y: int,
    destination_x: int,
    destination_y: int,
    mesh_x: int,
    mesh_y: int,
) -> Port:
    """Return the one legal X-first route; increasing Y is North.

    Coordinates are validated before route selection so an out-of-mesh packet
    fails as a protocol error instead of being sent toward a boundary.
    """

    coordinates = {
        "current_x": _coordinate("current_x", current_x),
        "current_y": _coordinate("current_y", current_y),
        "destination_x": _coordinate("destination_x", destination_x),
        "destination_y": _coordinate("destination_y", destination_y),
        "mesh_x": _coordinate("mesh_x", mesh_x),
        "mesh_y": _coordinate("mesh_y", mesh_y),
    }
    if coordinates["mesh_x"] < 1 or coordinates["mesh_y"] < 1:
        raise RoutingError("mesh dimensions must be positive")
    for coordinate_name, dimension_name in (
        ("current_x", "mesh_x"),
        ("destination_x", "mesh_x"),
        ("current_y", "mesh_y"),
        ("destination_y", "mesh_y"),
    ):
        if not 0 <= coordinates[coordinate_name] < coordinates[dimension_name]:
            raise RoutingError(
                f"{coordinate_name}={coordinates[coordinate_name]} is outside "
                f"{dimension_name}={coordinates[dimension_name]}"
            )

    # Dimension ordering is the deadlock-relevant rule: exhaust X before Y.
    if destination_x > current_x:
        return Port.EAST
    if destination_x < current_x:
        return Port.WEST
    if destination_y > current_y:
        return Port.NORTH
    if destination_y < current_y:
        return Port.SOUTH
    return Port.LOCAL
