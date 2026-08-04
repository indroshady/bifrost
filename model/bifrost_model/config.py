"""Load the machine-readable Core v0.2 configuration into typed model state.

JSON Schema catches document-shape errors first. ``BifrostConfig`` then checks
relationships that span sections of the YAML and enforces the selected Core
profile, including the deliberate absence of QoS behavior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, cast

import yaml
from jsonschema import Draft202012Validator


class ConfigError(ValueError):
    """Raised when the selected Bifröst configuration is invalid."""


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{path} must be a mapping")
    return cast(Mapping[str, Any], value)


def _integer(mapping: Mapping[str, Any], key: str, path: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{path}.{key} must be an integer")
    return value


def _boolean(mapping: Mapping[str, Any], key: str, path: str) -> bool:
    value = mapping.get(key)
    if type(value) is not bool:
        raise ConfigError(f"{path}.{key} must be a boolean")
    return value


def _string(mapping: Mapping[str, Any], key: str, path: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise ConfigError(f"{path}.{key} must be a string")
    return value


def _integer_tuple(mapping: Mapping[str, Any], key: str, path: str) -> tuple[int, ...]:
    value = mapping.get(key)
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in value
    ):
        raise ConfigError(f"{path}.{key} must be a list of integers")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class BifrostConfig:
    """Validated configuration values consumed by the architectural model.

    The dataclass contains semantic parameters only. It does not assign a wire
    encoding or expose implementation-specific RTL controls.
    """

    profile: str
    ports: tuple[str, ...]
    flit_width: int
    num_vcs: int
    vc_depth: int
    x_width: int
    y_width: int
    router_x: int
    router_y: int
    mesh_x: int
    mesh_y: int
    packet_id_width: int
    qos_classes: int
    qos_weights: tuple[int, ...]
    qos_enabled: bool
    north_is_increasing_y: bool
    registered_credit: bool
    allow_same_cycle_zero_credit_bypass: bool

    @classmethod
    def from_mapping(cls, document: Mapping[str, Any]) -> "BifrostConfig":
        """Build and cross-check a configuration from a parsed YAML mapping."""

        # Parse each contract section explicitly so malformed values fail at
        # their source path rather than being coerced by Python.
        design = _mapping(document.get("design"), "design")
        parameters = _mapping(document.get("parameters"), "parameters")
        mesh = _mapping(document.get("mesh"), "mesh")
        arbitration = _mapping(document.get("arbitration"), "arbitration")
        flow_control = _mapping(document.get("flow_control"), "flow_control")

        ports_value = mesh.get("ports")
        if not isinstance(ports_value, list) or not all(
            isinstance(port, str) for port in ports_value
        ):
            raise ConfigError("mesh.ports must be a list of strings")

        config = cls(
            profile=_string(design, "profile", "design"),
            ports=tuple(ports_value),
            flit_width=_integer(parameters, "FLIT_W", "parameters"),
            num_vcs=_integer(parameters, "NUM_VCS", "parameters"),
            vc_depth=_integer(parameters, "VC_DEPTH", "parameters"),
            x_width=_integer(parameters, "X_W", "parameters"),
            y_width=_integer(parameters, "Y_W", "parameters"),
            router_x=_integer(parameters, "ROUTER_X", "parameters"),
            router_y=_integer(parameters, "ROUTER_Y", "parameters"),
            mesh_x=_integer(parameters, "MESH_X", "parameters"),
            mesh_y=_integer(parameters, "MESH_Y", "parameters"),
            packet_id_width=_integer(parameters, "PKT_ID_W", "parameters"),
            qos_classes=_integer(parameters, "QOS_CLASSES", "parameters"),
            qos_weights=_integer_tuple(
                parameters, "QOS_WEIGHTS", "parameters"
            ),
            qos_enabled=_boolean(arbitration, "qos_enabled", "arbitration"),
            north_is_increasing_y=_boolean(
                mesh, "north_is_increasing_y", "mesh"
            ),
            registered_credit=(
                _string(flow_control, "mode", "flow_control")
                == "registered_credit"
            ),
            allow_same_cycle_zero_credit_bypass=_boolean(
                flow_control,
                "allow_same_cycle_zero_credit_bypass",
                "flow_control",
            ),
        )
        config._validate()
        return config

    def _validate(self) -> None:
        """Enforce cross-field and frozen-profile invariants."""

        if self.profile != "core_v0_2":
            raise ConfigError(f"unsupported profile {self.profile!r}")
        if self.ports != ("local", "north", "south", "east", "west"):
            raise ConfigError("Core v0.2 requires the frozen five-port ordering")
        if (self.flit_width, self.num_vcs, self.vc_depth) != (128, 2, 4):
            raise ConfigError("Core v0.2 requires FLIT_W=128, NUM_VCS=2, VC_DEPTH=4")
        if self.mesh_x < 1 or self.mesh_y < 1:
            raise ConfigError("mesh dimensions must be positive")
        if self.x_width != max(1, (self.mesh_x - 1).bit_length()):
            raise ConfigError("X_W must be the minimum positive width for MESH_X")
        if self.y_width != max(1, (self.mesh_y - 1).bit_length()):
            raise ConfigError("Y_W must be the minimum positive width for MESH_Y")
        if not 0 <= self.router_x < self.mesh_x:
            raise ConfigError("ROUTER_X is outside MESH_X")
        if not 0 <= self.router_y < self.mesh_y:
            raise ConfigError("ROUTER_Y is outside MESH_Y")
        if self.packet_id_width < 1:
            raise ConfigError("PKT_ID_W must be positive")
        if self.qos_enabled:
            raise ConfigError("QoS is staged and cannot be enabled in Core v0.2")
        if self.qos_classes != 1 or self.qos_weights != (1,):
            raise ConfigError("disabled QoS requires QOS_CLASSES=1 and QOS_WEIGHTS=[1]")
        if not self.north_is_increasing_y:
            raise ConfigError("Core v0.2 defines North as increasing Y")
        if not self.registered_credit:
            raise ConfigError("Core v0.2 requires registered-credit flow control")
        if self.allow_same_cycle_zero_credit_bypass:
            raise ConfigError("Core v0.2 forbids same-cycle zero-credit bypass")


def load_config(
    path: str | Path,
    schema_path: str | Path | None = None,
) -> BifrostConfig:
    """Load, schema-check, and type-check a Bifröst configuration.

    ``schema_path`` is injectable for validator tests; normal callers use the
    schema adjacent to ``spec/bifrost.yaml``.
    """

    config_path = Path(path)
    selected_schema = (
        Path(schema_path)
        if schema_path is not None
        else config_path.parent / "schema" / "bifrost.schema.json"
    )
    with config_path.open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream)
    if not isinstance(document, Mapping):
        raise ConfigError("configuration root must be a mapping")

    # Schema diagnostics are collected and sorted to keep failures stable
    # across runs and Python versions.
    schema = json.loads(selected_schema.read_text(encoding="utf-8"))
    validation_errors = sorted(
        Draft202012Validator(schema).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    if validation_errors:
        diagnostics = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: "
            f"{error.message}"
            for error in validation_errors
        )
        raise ConfigError(diagnostics)
    return BifrostConfig.from_mapping(document)
