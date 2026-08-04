"""Load the machine-readable Core v0.2 configuration into typed model state.

JSON Schema catches document-shape errors first. ``BifrostConfig`` then checks
relationships that span sections of the YAML and enforces the selected Core
profile, including the frozen wire contract and deliberate absence of QoS behavior.
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


def _shape_tuple(
    mapping: Mapping[str, Any], key: str, path: str
) -> tuple[int | str, ...]:
    value = mapping.get(key)
    if not isinstance(value, list) or any(
        not isinstance(item, (int, str)) or isinstance(item, bool) for item in value
    ):
        raise ConfigError(f"{path}.{key} must be a list of integers or names")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class FlitField:
    """One inclusive bit range in the frozen packed-flit contract."""

    name: str
    msb: int
    lsb: int
    width: int
    meaningful_on: str


@dataclass(frozen=True, slots=True)
class InterfaceSignal:
    """One external cycle-interface signal and its logical array shape."""

    name: str
    direction: str
    shape: tuple[int | str, ...]


@dataclass(frozen=True, slots=True)
class BifrostConfig:
    """Validated configuration values consumed by the architectural model.

    The semantic router consumes only the behavioral fields. Encoding fields
    are typed here so future RTL and verification can share one checked contract
    without changing the semantic :class:`Flit` payload representation.
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
    port_id_width: int
    vc_id_width: int
    qos_width: int
    payload_width: int
    encoding_frozen: bool
    flit_fields: tuple[FlitField, ...]
    port_encoding: tuple[tuple[str, int], ...]
    invalid_port_ids: tuple[int, ...]
    vc_encoding: tuple[tuple[str, int], ...]
    invalid_vc_ids: tuple[int, ...]
    port_dimension: str
    data_dimensions: str
    transfer_edge: str
    has_rx_ready: bool
    has_tx_ready: bool
    interface_signals: tuple[InterfaceSignal, ...]
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
        mesh_dimensions = _mapping(mesh.get("dimensions"), "mesh.dimensions")
        router_coordinate = _mapping(
            mesh.get("router_coordinate"), "mesh.router_coordinate"
        )
        flit = _mapping(document.get("flit"), "flit")
        virtual_channels = _mapping(
            document.get("virtual_channels"), "virtual_channels"
        )
        arbitration = _mapping(document.get("arbitration"), "arbitration")
        flow_control = _mapping(document.get("flow_control"), "flow_control")
        external_interface = _mapping(
            document.get("external_interface"), "external_interface"
        )
        signal_document = _mapping(
            external_interface.get("signals"), "external_interface.signals"
        )
        interface_signals: list[InterfaceSignal] = []
        for name, value in signal_document.items():
            signal = _mapping(value, f"external_interface.signals.{name}")
            interface_signals.append(
                InterfaceSignal(
                    name=name,
                    direction=_string(
                        signal, "direction", f"external_interface.signals.{name}"
                    ),
                    shape=_shape_tuple(
                        signal, "shape", f"external_interface.signals.{name}"
                    ),
                )
            )

        ports_value = mesh.get("ports")
        if not isinstance(ports_value, list) or not all(
            isinstance(port, str) for port in ports_value
        ):
            raise ConfigError("mesh.ports must be a list of strings")

        field_document = _mapping(flit.get("fields"), "flit.fields")
        flit_fields: list[FlitField] = []
        for name, value in field_document.items():
            field = _mapping(value, f"flit.fields.{name}")
            flit_fields.append(
                FlitField(
                    name=name,
                    msb=_integer(field, "msb", f"flit.fields.{name}"),
                    lsb=_integer(field, "lsb", f"flit.fields.{name}"),
                    width=_integer(field, "width_bits", f"flit.fields.{name}"),
                    meaningful_on=_string(
                        field, "meaningful_on", f"flit.fields.{name}"
                    ),
                )
            )

        port_ids = _mapping(mesh.get("port_encoding"), "mesh.port_encoding")
        port_values = _mapping(port_ids.get("values"), "mesh.port_encoding.values")
        vc_ids = _mapping(
            virtual_channels.get("id_encoding"),
            "virtual_channels.id_encoding",
        )
        vc_values = _mapping(
            vc_ids.get("values"), "virtual_channels.id_encoding.values"
        )
        invalid_port_ids = _integer_tuple(
            port_ids, "invalid_values", "mesh.port_encoding"
        )
        invalid_vc_ids = _integer_tuple(
            vc_ids, "invalid_values", "virtual_channels.id_encoding"
        )

        duplicate_fields = {
            "parameters.PORTS vs mesh.ports": (
                _integer(parameters, "PORTS", "parameters"),
                len(ports_value),
            ),
            "parameters.FLIT_W vs flit.width_bits": (
                _integer(parameters, "FLIT_W", "parameters"),
                _integer(flit, "width_bits", "flit"),
            ),
            "parameters.PKT_ID_W vs flit.packet_id_width_bits": (
                _integer(parameters, "PKT_ID_W", "parameters"),
                _integer(flit, "packet_id_width_bits", "flit"),
            ),
            "parameters.NUM_VCS vs virtual_channels.count_per_input": (
                _integer(parameters, "NUM_VCS", "parameters"),
                _integer(virtual_channels, "count_per_input", "virtual_channels"),
            ),
            "parameters.VC_DEPTH vs virtual_channels.depth_flits": (
                _integer(parameters, "VC_DEPTH", "parameters"),
                _integer(virtual_channels, "depth_flits", "virtual_channels"),
            ),
            "parameters.MESH_X vs mesh.dimensions.x": (
                _integer(parameters, "MESH_X", "parameters"),
                _integer(mesh_dimensions, "x", "mesh.dimensions"),
            ),
            "parameters.MESH_Y vs mesh.dimensions.y": (
                _integer(parameters, "MESH_Y", "parameters"),
                _integer(mesh_dimensions, "y", "mesh.dimensions"),
            ),
            "parameters.ROUTER_X vs mesh.router_coordinate.x": (
                _integer(parameters, "ROUTER_X", "parameters"),
                _integer(router_coordinate, "x", "mesh.router_coordinate"),
            ),
            "parameters.ROUTER_Y vs mesh.router_coordinate.y": (
                _integer(parameters, "ROUTER_Y", "parameters"),
                _integer(router_coordinate, "y", "mesh.router_coordinate"),
            ),
            "parameters.PORT_ID_W vs mesh.port_encoding.width_bits": (
                _integer(parameters, "PORT_ID_W", "parameters"),
                _integer(port_ids, "width_bits", "mesh.port_encoding"),
            ),
            "parameters.VC_ID_W vs virtual_channels.id_encoding.width_bits": (
                _integer(parameters, "VC_ID_W", "parameters"),
                _integer(vc_ids, "width_bits", "virtual_channels.id_encoding"),
            ),
            "parameters.QOS_CLASSES vs arbitration.qos_classes": (
                _integer(parameters, "QOS_CLASSES", "parameters"),
                _integer(arbitration, "qos_classes", "arbitration"),
            ),
            "parameters.QOS_WEIGHTS vs arbitration.qos_weights": (
                _integer_tuple(parameters, "QOS_WEIGHTS", "parameters"),
                _integer_tuple(arbitration, "qos_weights", "arbitration"),
            ),
        }
        for label, (left, right) in duplicate_fields.items():
            if left != right:
                raise ConfigError(f"{label} disagree: {left!r} != {right!r}")

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
            port_id_width=_integer(parameters, "PORT_ID_W", "parameters"),
            vc_id_width=_integer(parameters, "VC_ID_W", "parameters"),
            qos_width=_integer(parameters, "QOS_W", "parameters"),
            payload_width=_integer(flit, "payload_width_bits", "flit"),
            encoding_frozen=_boolean(flit, "encoding_frozen", "flit"),
            flit_fields=tuple(flit_fields),
            port_encoding=tuple(
                (name, _integer(port_values, name, "mesh.port_encoding.values"))
                for name in ports_value
            ),
            invalid_port_ids=invalid_port_ids,
            vc_encoding=tuple(
                (name, _integer(vc_values, name, "virtual_channels.id_encoding.values"))
                for name in ("vc0", "vc1")
            ),
            invalid_vc_ids=invalid_vc_ids,
            port_dimension=_string(
                external_interface, "port_dimension", "external_interface"
            ),
            data_dimensions=_string(
                external_interface, "data_dimensions", "external_interface"
            ),
            transfer_edge=_string(
                external_interface, "transfer_edge", "external_interface"
            ),
            has_rx_ready=_boolean(
                external_interface, "has_rx_ready", "external_interface"
            ),
            has_tx_ready=_boolean(
                external_interface, "has_tx_ready", "external_interface"
            ),
            interface_signals=tuple(interface_signals),
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
        if _string(
            external_interface, "port_array_order", "external_interface"
        ) != "mesh.ports":
            raise ConfigError("external interface must use mesh.ports array order")
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
        if not self.encoding_frozen:
            raise ConfigError("Core v0.2 packed-flit encoding must be frozen")
        if (self.port_id_width, self.vc_id_width, self.qos_width) != (3, 1, 2):
            raise ConfigError("Core v0.2 requires PORT_ID_W=3, VC_ID_W=1, QOS_W=2")
        expected_ports = (
            ("local", 0),
            ("north", 1),
            ("south", 2),
            ("east", 3),
            ("west", 4),
        )
        if self.port_encoding != expected_ports or self.invalid_port_ids != (5, 6, 7):
            raise ConfigError("Core v0.2 port IDs must encode Local..West as 0..4")
        if self.vc_encoding != (("vc0", 0), ("vc1", 1)):
            raise ConfigError("Core v0.2 VC IDs must encode VC0=0 and VC1=1")
        if self.invalid_vc_ids:
            raise ConfigError("one-bit Core v0.2 VC IDs have no reserved bit patterns")
        if (
            self.port_dimension,
            self.data_dimensions,
            self.transfer_edge,
            self.has_rx_ready,
            self.has_tx_ready,
        ) != ("unpacked", "packed", "rising", False, False):
            raise ConfigError("Core v0.2 external interface conventions are frozen")
        expected_signals = (
            InterfaceSignal("clk", "input", (1,)),
            InterfaceSignal("rst_n", "input", (1,)),
            InterfaceSignal("port_enable", "input", ("PORTS",)),
            InterfaceSignal("rx_valid", "input", ("PORTS",)),
            InterfaceSignal("rx_flit", "input", ("PORTS", "FLIT_W")),
            InterfaceSignal("rx_vc", "input", ("PORTS", "VC_ID_W")),
            InterfaceSignal("tx_valid", "output", ("PORTS",)),
            InterfaceSignal("tx_flit", "output", ("PORTS", "FLIT_W")),
            InterfaceSignal("tx_vc", "output", ("PORTS", "VC_ID_W")),
            InterfaceSignal("credit_out_valid", "output", ("PORTS",)),
            InterfaceSignal("credit_out_vc", "output", ("PORTS", "VC_ID_W")),
            InterfaceSignal("credit_in_valid", "input", ("PORTS",)),
            InterfaceSignal("credit_in_vc", "input", ("PORTS", "VC_ID_W")),
        )
        if self.interface_signals != expected_signals:
            raise ConfigError("Core v0.2 external signal directions and shapes are frozen")

        fields = {field.name: field for field in self.flit_fields}
        expected_names = (
            "head",
            "tail",
            "destination_x",
            "destination_y",
            "source_x",
            "source_y",
            "packet_id",
            "qos_class",
            "payload",
        )
        if tuple(fields) != expected_names:
            raise ConfigError("flit fields must use the frozen MSB-to-LSB order")
        expected_widths = {
            "head": 1,
            "tail": 1,
            "destination_x": self.x_width,
            "destination_y": self.y_width,
            "source_x": self.x_width,
            "source_y": self.y_width,
            "packet_id": self.packet_id_width,
            "qos_class": self.qos_width,
            "payload": self.payload_width,
        }
        next_msb = self.flit_width - 1
        for name in expected_names:
            field = fields[name]
            if field.width != expected_widths[name]:
                raise ConfigError(f"flit field {name} has the wrong width")
            if field.msb != next_msb or field.lsb != field.msb - field.width + 1:
                raise ConfigError("flit fields must cover FLIT_W without gaps or overlap")
            next_msb = field.lsb - 1
        if next_msb != -1:
            raise ConfigError("flit fields must cover FLIT_W without gaps or overlap")
        derived_payload = self.flit_width - (
            2
            + 2 * self.x_width
            + 2 * self.y_width
            + self.packet_id_width
            + self.qos_width
        )
        if self.payload_width != derived_payload or self.payload_width <= 0:
            raise ConfigError("payload width must be the positive derived FLIT_W remainder")
        for field in self.flit_fields:
            expected_meaning = (
                "all_flits" if field.name in {"head", "tail", "payload"} else "headers_only"
            )
            if field.meaningful_on != expected_meaning:
                raise ConfigError(f"flit field {field.name} has wrong meaning scope")
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
