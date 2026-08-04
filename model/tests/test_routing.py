from __future__ import annotations

import pytest

from bifrost_model.routing import Port, RoutingError, route_xy


@pytest.mark.parametrize(
    ("destination_x", "destination_y", "expected"),
    [
        (0, 0, Port.WEST),
        (0, 1, Port.WEST),
        (0, 2, Port.WEST),
        (1, 0, Port.SOUTH),
        (1, 1, Port.LOCAL),
        (1, 2, Port.NORTH),
        (2, 0, Port.EAST),
        (2, 1, Port.EAST),
        (2, 2, Port.EAST),
    ],
)
def test_ROUTE_001_all_xy_relations(
    destination_x: int,
    destination_y: int,
    expected: Port,
) -> None:
    assert route_xy(
        current_x=1,
        current_y=1,
        destination_x=destination_x,
        destination_y=destination_y,
        mesh_x=3,
        mesh_y=3,
    ) is expected


def test_ROUTE_002_local_only_at_matching_coordinates() -> None:
    local = route_xy(
        current_x=1,
        current_y=1,
        destination_x=1,
        destination_y=1,
        mesh_x=3,
        mesh_y=3,
    )
    north = route_xy(
        current_x=1,
        current_y=1,
        destination_x=1,
        destination_y=2,
        mesh_x=3,
        mesh_y=3,
    )

    assert local is Port.LOCAL
    assert north is not Port.LOCAL


@pytest.mark.parametrize(
    "arguments",
    [
        {
            "current_x": -1,
            "current_y": 0,
            "destination_x": 0,
            "destination_y": 0,
            "mesh_x": 2,
            "mesh_y": 2,
        },
        {
            "current_x": 0,
            "current_y": 0,
            "destination_x": 2,
            "destination_y": 0,
            "mesh_x": 2,
            "mesh_y": 2,
        },
        {
            "current_x": 0,
            "current_y": 0,
            "destination_x": 0,
            "destination_y": 0,
            "mesh_x": 0,
            "mesh_y": 2,
        },
    ],
)
def test_ROUTE_001_rejects_invalid_coordinates(
    arguments: dict[str, int],
) -> None:
    with pytest.raises(RoutingError):
        route_xy(**arguments)


def test_ROUTE_001_rejects_boolean_coordinates() -> None:
    with pytest.raises(RoutingError, match="must be an integer"):
        route_xy(
            current_x=False,  # type: ignore[arg-type]
            current_y=0,
            destination_x=0,
            destination_y=0,
            mesh_x=2,
            mesh_y=2,
        )
