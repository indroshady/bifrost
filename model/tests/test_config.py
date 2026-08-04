from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from bifrost_model.config import BifrostConfig, ConfigError, load_config


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "spec" / "bifrost.yaml"


def _document() -> dict[str, object]:
    loaded = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_VER_002_core_config_matches_frozen_profile() -> None:
    config = load_config(CONFIG_PATH)

    assert config.profile == "core_v0_2"
    assert config.ports == ("local", "north", "south", "east", "west")
    assert (config.flit_width, config.num_vcs, config.vc_depth) == (128, 2, 4)
    assert (config.mesh_x, config.mesh_y) == (2, 2)
    assert (config.x_width, config.y_width) == (1, 1)
    assert (config.router_x, config.router_y) == (0, 0)
    assert config.packet_id_width == 16
    assert config.north_is_increasing_y
    assert config.registered_credit
    assert not config.allow_same_cycle_zero_credit_bypass


def test_VER_002_core_config_keeps_staged_qos_disabled() -> None:
    config = load_config(CONFIG_PATH)

    assert not config.qos_enabled
    assert config.qos_classes == 1
    assert config.qos_weights == (1,)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (
            lambda doc: (
                doc["parameters"].update({"MESH_X": 3}),
                doc["mesh"]["dimensions"].update({"x": 3}),
            ),
            "X_W must be the minimum positive width",
        ),
        (
            lambda doc: (
                doc["parameters"].update({"ROUTER_X": 2}),
                doc["mesh"]["router_coordinate"].update({"x": 2}),
            ),
            "ROUTER_X is outside MESH_X",
        ),
        (
            lambda doc: doc["arbitration"].update({"qos_enabled": True}),
            "QoS is staged",
        ),
        (
            lambda doc: doc["flow_control"].update(
                {"allow_same_cycle_zero_credit_bypass": True}
            ),
            "forbids same-cycle zero-credit bypass",
        ),
        (
            lambda doc: doc["flit"].update({"encoding_frozen": False}),
            "must be frozen",
        ),
        (
            lambda doc: doc["flit"].update({"packet_id_width_bits": 15}),
            "PKT_ID_W vs flit.packet_id_width_bits disagree",
        ),
        (
            lambda doc: (
                doc["parameters"].update({"VC_ID_W": 2}),
                doc["virtual_channels"]["id_encoding"].update({"width_bits": 2}),
            ),
            "PORT_ID_W=3, VC_ID_W=1, QOS_W=2",
        ),
        (
            lambda doc: doc["mesh"]["port_encoding"]["values"].update({"west": 5}),
            "port IDs",
        ),
        (
            lambda doc: doc["flit"]["fields"]["payload"].update({"msb": 102}),
            "without gaps or overlap",
        ),
        (
            lambda doc: doc["external_interface"]["signals"]["rx_flit"].update(
                {"shape": ["PORTS", "VC_ID_W"]}
            ),
            "signal directions and shapes",
        ),
    ],
)
def test_VER_002_invalid_cross_profile_config_is_rejected(
    mutation: object,
    match: str,
) -> None:
    document = copy.deepcopy(_document())
    assert callable(mutation)
    mutation(document)

    with pytest.raises(ConfigError, match=match):
        BifrostConfig.from_mapping(document)
