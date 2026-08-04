#!/usr/bin/env python3
"""Validate the Bifröst machine-readable contract and traceability."""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = ROOT / "spec"
CONFIG_PATH = SPEC_DIR / "bifrost.yaml"
SCHEMA_PATH = SPEC_DIR / "schema" / "bifrost.schema.json"
REQUIREMENTS_PATH = SPEC_DIR / "requirements.yaml"
MAPPINGS_PATH = SPEC_DIR / "requirements_to_tests.csv"
NORMATIVE_SPEC_PATH = SPEC_DIR / "BIFROST_SPEC.md"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a YAML mapping")
    return value


def json_path(parts: list[Any]) -> str:
    return ".".join(str(part) for part in parts) or "<root>"


def extract_normative_requirements(text: str) -> dict[str, tuple[str, str]]:
    section_match = re.search(
        r"^# 25\. Requirements Traceability\s*$"
        r"(?P<section>.*?)"
        r"^# 26\.",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if section_match is None:
        raise ValueError("could not locate Section 25 requirements table")

    requirements: dict[str, tuple[str, str]] = {}
    row_pattern = re.compile(
        r"^\| `(?P<id>[A-Z]+-\d{3})` "
        r"\| (?P<profile>Core|QoS) "
        r"\| (?P<description>.+?) \|$",
        flags=re.MULTILINE,
    )
    for match in row_pattern.finditer(section_match.group("section")):
        requirement_id = match.group("id")
        if requirement_id in requirements:
            raise ValueError(f"duplicate Section 25 ID {requirement_id}")
        requirements[requirement_id] = (
            match.group("profile"),
            match.group("description"),
        )
    if not requirements:
        raise ValueError("Section 25 requirements table is empty")
    return requirements


def validate_cross_fields(config: dict[str, Any], errors: list[str]) -> None:
    parameters = config["parameters"]
    mesh = config["mesh"]
    flit = config["flit"]
    vcs = config["virtual_channels"]
    arbitration = config["arbitration"]
    external_interface = config["external_interface"]

    comparisons = {
        "parameters.PORTS vs mesh.ports": (
            parameters["PORTS"],
            len(mesh["ports"]),
        ),
        "parameters.FLIT_W vs flit.width_bits": (
            parameters["FLIT_W"],
            flit["width_bits"],
        ),
        "parameters.PKT_ID_W vs flit.packet_id_width_bits": (
            parameters["PKT_ID_W"],
            flit["packet_id_width_bits"],
        ),
        "parameters.NUM_VCS vs virtual_channels.count_per_input": (
            parameters["NUM_VCS"],
            vcs["count_per_input"],
        ),
        "parameters.VC_DEPTH vs virtual_channels.depth_flits": (
            parameters["VC_DEPTH"],
            vcs["depth_flits"],
        ),
        "parameters.MESH_X vs mesh.dimensions.x": (
            parameters["MESH_X"],
            mesh["dimensions"]["x"],
        ),
        "parameters.MESH_Y vs mesh.dimensions.y": (
            parameters["MESH_Y"],
            mesh["dimensions"]["y"],
        ),
        "parameters.ROUTER_X vs mesh.router_coordinate.x": (
            parameters["ROUTER_X"],
            mesh["router_coordinate"]["x"],
        ),
        "parameters.ROUTER_Y vs mesh.router_coordinate.y": (
            parameters["ROUTER_Y"],
            mesh["router_coordinate"]["y"],
        ),
        "parameters.QOS_CLASSES vs arbitration.qos_classes": (
            parameters["QOS_CLASSES"],
            arbitration["qos_classes"],
        ),
        "parameters.QOS_WEIGHTS vs arbitration.qos_weights": (
            parameters["QOS_WEIGHTS"],
            arbitration["qos_weights"],
        ),
        "parameters.PORT_ID_W vs mesh.port_encoding.width_bits": (
            parameters["PORT_ID_W"],
            mesh["port_encoding"]["width_bits"],
        ),
        "parameters.VC_ID_W vs virtual_channels.id_encoding.width_bits": (
            parameters["VC_ID_W"],
            vcs["id_encoding"]["width_bits"],
        ),
    }
    for label, (left, right) in comparisons.items():
        if left != right:
            errors.append(f"{label} disagree: {left!r} != {right!r}")

    mesh_x = parameters["MESH_X"]
    mesh_y = parameters["MESH_Y"]
    if parameters["X_W"] != max(1, (mesh_x - 1).bit_length()):
        errors.append("X_W must be the minimum positive width for MESH_X")
    if parameters["Y_W"] != max(1, (mesh_y - 1).bit_length()):
        errors.append("Y_W must be the minimum positive width for MESH_Y")
    if not 0 <= parameters["ROUTER_X"] < mesh_x:
        errors.append("ROUTER_X must be within the configured mesh")
    if not 0 <= parameters["ROUTER_Y"] < mesh_y:
        errors.append("ROUTER_Y must be within the configured mesh")

    expected_port_values = {
        "local": 0,
        "north": 1,
        "south": 2,
        "east": 3,
        "west": 4,
    }
    if mesh["ports"] != list(expected_port_values):
        errors.append("physical port order must be Local, North, South, East, West")
    if mesh["port_encoding"]["values"] != expected_port_values:
        errors.append("physical port IDs must encode Local..West as 0..4")
    port_width = parameters["PORT_ID_W"]
    valid_port_ids = set(expected_port_values.values())
    expected_invalid_ports = sorted(set(range(1 << port_width)) - valid_port_ids)
    if mesh["port_encoding"]["invalid_values"] != expected_invalid_ports:
        errors.append("reserved port IDs must contain every unused PORT_ID_W code")

    if vcs["id_encoding"]["values"] != {"vc0": 0, "vc1": 1}:
        errors.append("VC IDs must encode VC0=0 and VC1=1")
    vc_width = parameters["VC_ID_W"]
    if vc_width != max(1, (parameters["NUM_VCS"] - 1).bit_length()):
        errors.append("VC_ID_W must be the minimum positive width for NUM_VCS")
    expected_invalid_vcs = sorted(
        set(range(1 << vc_width)) - set(range(parameters["NUM_VCS"]))
    )
    if vcs["id_encoding"]["invalid_values"] != expected_invalid_vcs:
        errors.append("reserved VC IDs must contain every unused VC_ID_W code")

    if flit["encoding_frozen"] is not True:
        errors.append("Core v0.2 flit encoding must be frozen")
    expected_field_order = (
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
    fields = flit["fields"]
    if tuple(fields) != expected_field_order:
        errors.append("flit fields must use the frozen MSB-to-LSB order")
    field_widths = {
        "head": 1,
        "tail": 1,
        "destination_x": parameters["X_W"],
        "destination_y": parameters["Y_W"],
        "source_x": parameters["X_W"],
        "source_y": parameters["Y_W"],
        "packet_id": parameters["PKT_ID_W"],
        "qos_class": parameters["QOS_W"],
        "payload": flit["payload_width_bits"],
    }
    next_msb = parameters["FLIT_W"] - 1
    for name in expected_field_order:
        field = fields[name]
        width = field_widths[name]
        if field["width_bits"] != width:
            errors.append(f"flit field {name} width disagrees with its parameter")
        if field["msb"] != next_msb or field["lsb"] != field["msb"] - width + 1:
            errors.append(f"flit field {name} creates a gap, overlap, or wrong range")
        expected_meaning = (
            "all_flits" if name in {"head", "tail", "payload"} else "headers_only"
        )
        if field["meaningful_on"] != expected_meaning:
            errors.append(f"flit field {name} has wrong meaning scope")
        next_msb = field["lsb"] - 1
    if next_msb != -1:
        errors.append("flit fields do not cover every bit in FLIT_W")
    derived_payload = parameters["FLIT_W"] - (
        2
        + 2 * parameters["X_W"]
        + 2 * parameters["Y_W"]
        + parameters["PKT_ID_W"]
        + parameters["QOS_W"]
    )
    if flit["payload_width_bits"] != derived_payload or derived_payload <= 0:
        errors.append("payload width must be the positive derived FLIT_W remainder")
    if parameters["QOS_W"] != 2:
        errors.append("QOS_W must reserve two header bits for four-class compatibility")

    expected_signals = {
        "clk": {"direction": "input", "shape": [1]},
        "rst_n": {"direction": "input", "shape": [1]},
        "port_enable": {"direction": "input", "shape": ["PORTS"]},
        "rx_valid": {"direction": "input", "shape": ["PORTS"]},
        "rx_flit": {"direction": "input", "shape": ["PORTS", "FLIT_W"]},
        "rx_vc": {"direction": "input", "shape": ["PORTS", "VC_ID_W"]},
        "tx_valid": {"direction": "output", "shape": ["PORTS"]},
        "tx_flit": {"direction": "output", "shape": ["PORTS", "FLIT_W"]},
        "tx_vc": {"direction": "output", "shape": ["PORTS", "VC_ID_W"]},
        "credit_out_valid": {"direction": "output", "shape": ["PORTS"]},
        "credit_out_vc": {"direction": "output", "shape": ["PORTS", "VC_ID_W"]},
        "credit_in_valid": {"direction": "input", "shape": ["PORTS"]},
        "credit_in_vc": {"direction": "input", "shape": ["PORTS", "VC_ID_W"]},
    }
    if external_interface["signals"] != expected_signals:
        errors.append("external signal directions or logical shapes disagree")
    if external_interface["port_array_order"] != "mesh.ports":
        errors.append("external port arrays must use mesh.ports ordering")
    if external_interface["transfer_edge"] != "rising":
        errors.append("external transfers must occur on the rising edge")
    if (
        external_interface["port_dimension"] != "unpacked"
        or external_interface["data_dimensions"] != "packed"
    ):
        errors.append("external interface dimensions must use unpacked ports and packed data")
    if external_interface["has_rx_ready"] or external_interface["has_tx_ready"]:
        errors.append("credit-controlled Core interface has no ready sidebands")

    if arbitration["qos_enabled"]:
        errors.append("Core profile must not enable QoS")
    if arbitration["aging_enabled"]:
        errors.append("Core profile must not enable QoS aging")
    if parameters["QOS_CLASSES"] != 1 or parameters["QOS_WEIGHTS"] != [1]:
        errors.append("disabled Core QoS requires one class with weights [1]")
    if len(parameters["QOS_WEIGHTS"]) != parameters["QOS_CLASSES"]:
        errors.append("QOS_WEIGHTS length must equal QOS_CLASSES")


def validate() -> list[str]:
    errors: list[str] = []

    try:
        config = load_yaml(CONFIG_PATH)
        requirements_doc = load_yaml(REQUIREMENTS_PATH)
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        normative = extract_normative_requirements(
            NORMATIVE_SPEC_PATH.read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        return [str(exc)]

    schema_errors = sorted(
        Draft202012Validator(schema).iter_errors(config),
        key=lambda error: list(error.absolute_path),
    )
    errors.extend(
        f"bifrost.yaml:{json_path(list(error.absolute_path))}: {error.message}"
        for error in schema_errors
    )
    config_is_valid = not schema_errors
    if config_is_valid:
        validate_cross_fields(config, errors)

    profiles = requirements_doc.get("profiles")
    requirements = requirements_doc.get("requirements")
    if not isinstance(profiles, dict):
        errors.append("requirements.yaml: profiles must be a mapping")
        profiles = {}
    if not isinstance(requirements, list):
        errors.append("requirements.yaml: requirements must be a list")
        requirements = []

    if requirements_doc.get("source") != NORMATIVE_SPEC_PATH.name:
        errors.append("requirements.yaml source must name BIFROST_SPEC.md")
    if config_is_valid:
        if requirements_doc.get("spec_revision") != config["design"]["spec_revision"]:
            errors.append("requirements and selected configuration revisions disagree")
        core_profile = profiles.get(config["design"]["profile"], {})
        if not isinstance(core_profile, dict) or core_profile.get("stage") != "current":
            errors.append("selected profile must be declared current in requirements.yaml")
        if core_profile.get("qos_enabled") is not False:
            errors.append("selected Core profile must declare qos_enabled: false")
    qos_profile = profiles.get("qos_extension_v0_2", {})
    if not isinstance(qos_profile, dict) or qos_profile.get("stage") != "staged":
        errors.append("QoS extension profile must remain staged")

    structured_ids: list[str] = []
    structured_by_id: dict[str, dict[str, Any]] = {}
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            errors.append(f"requirements[{index}] must be a mapping")
            continue
        requirement_id = requirement.get("id")
        if not isinstance(requirement_id, str):
            errors.append(f"requirements[{index}].id must be a string")
            continue
        structured_ids.append(requirement_id)
        structured_by_id.setdefault(requirement_id, requirement)
        profile = requirement.get("profile")
        methods = requirement.get("verification_methods")
        if profile not in profiles:
            errors.append(f"{requirement_id}: unknown profile {profile!r}")
        if not isinstance(methods, list) or not methods:
            errors.append(f"{requirement_id}: verification_methods must be nonempty")

    duplicates = sorted(
        requirement_id
        for requirement_id, count in Counter(structured_ids).items()
        if count > 1
    )
    if duplicates:
        errors.append(f"duplicate requirement IDs: {', '.join(duplicates)}")

    normative_ids = set(normative)
    structured_id_set = set(structured_ids)
    missing_structured = sorted(normative_ids - structured_id_set)
    extra_structured = sorted(structured_id_set - normative_ids)
    if missing_structured:
        errors.append(
            "Section 25 IDs missing from requirements.yaml: "
            + ", ".join(missing_structured)
        )
    if extra_structured:
        errors.append(
            "requirements.yaml IDs absent from Section 25: "
            + ", ".join(extra_structured)
        )

    expected_profiles = {"Core": "core_v0_2", "QoS": "qos_extension_v0_2"}
    for requirement_id, (normative_profile, normative_description) in normative.items():
        structured = structured_by_id.get(requirement_id)
        if structured is None:
            continue
        if structured.get("profile") != expected_profiles[normative_profile]:
            errors.append(f"{requirement_id}: profile disagrees with Section 25")
        if structured.get("description") != normative_description:
            errors.append(f"{requirement_id}: description disagrees with Section 25")

    try:
        with MAPPINGS_PATH.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            expected_columns = {
                "requirement_id",
                "profile",
                "verification_method",
                "status",
                "artifact",
                "test_name",
                "notes",
            }
            if reader.fieldnames is None or set(reader.fieldnames) != expected_columns:
                errors.append(
                    "requirements_to_tests.csv has unexpected columns; expected "
                    + ", ".join(sorted(expected_columns))
                )
                mappings: list[dict[str, str]] = []
            else:
                mappings = list(reader)
    except OSError as exc:
        errors.append(str(exc))
        mappings = []

    mapped_ids: set[str] = set()
    for row_number, mapping in enumerate(mappings, start=2):
        requirement_id = mapping["requirement_id"]
        mapped_ids.add(requirement_id)
        requirement = structured_by_id.get(requirement_id)
        if requirement is None:
            errors.append(
                f"requirements_to_tests.csv:{row_number}: unknown ID {requirement_id}"
            )
            continue
        if mapping["profile"] != requirement.get("profile"):
            errors.append(
                f"requirements_to_tests.csv:{row_number}: profile mismatch "
                f"for {requirement_id}"
            )
        if mapping["verification_method"] not in requirement.get(
            "verification_methods", []
        ):
            errors.append(
                f"requirements_to_tests.csv:{row_number}: undeclared verification "
                f"method for {requirement_id}"
            )
        if mapping["status"] not in {"implemented", "planned"}:
            errors.append(
                f"requirements_to_tests.csv:{row_number}: status must be "
                "implemented or planned"
            )
        if mapping["status"] != "implemented":
            continue

        artifact = ROOT / mapping["artifact"]
        if not artifact.is_file():
            errors.append(
                f"requirements_to_tests.csv:{row_number}: implemented artifact "
                f"does not exist: {mapping['artifact']}"
            )
            continue
        if mapping["verification_method"] == "unit_test":
            test_name = mapping["test_name"]
            if not test_name:
                errors.append(
                    f"requirements_to_tests.csv:{row_number}: implemented unit "
                    "test requires test_name"
                )
                continue
            test_source = artifact.read_text(encoding="utf-8")
            if re.search(rf"^def {re.escape(test_name)}\s*\(", test_source, re.MULTILINE) is None:
                errors.append(
                    f"requirements_to_tests.csv:{row_number}: test {test_name} "
                    f"not found in {mapping['artifact']}"
                )
            token = requirement_id.replace("-", "_")
            if token not in test_name:
                errors.append(
                    f"requirements_to_tests.csv:{row_number}: test name must "
                    f"contain {token}"
                )

    unmapped = sorted(structured_id_set - mapped_ids)
    if unmapped:
        errors.append("requirements without mappings: " + ", ".join(unmapped))

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Bifrost specification validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    requirements = load_yaml(REQUIREMENTS_PATH)["requirements"]
    with MAPPINGS_PATH.open(newline="", encoding="utf-8") as stream:
        implemented = sum(
            row["status"] == "implemented" for row in csv.DictReader(stream)
        )
    print(
        f"Bifrost specification validation passed: "
        f"{len(requirements)} requirements, {implemented} implemented mappings"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
