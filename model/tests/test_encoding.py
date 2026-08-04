from __future__ import annotations

import pytest

from bifrost_model.config import load_config
from bifrost_model.encoding import (
    FIELD_RANGES,
    FLIT_WIDTH,
    INVALID_PORT_IDS,
    PORT_IDS,
    PORT_ID_WIDTH,
    VC_ID_WIDTH,
    EncodingError,
    PackedFlit,
    PackedHeader,
    decode_port_id,
    decode_vc_id,
    encode_port_id,
    encode_vc_id,
    pack_flit,
    unpack_flit,
)

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG = load_config(ROOT / "spec" / "bifrost.yaml")


def test_ENC_001_frozen_fields_cover_flit_without_gaps_or_overlap() -> None:
    covered: list[int] = []
    for msb, lsb in FIELD_RANGES.values():
        covered.extend(range(lsb, msb + 1))

    assert len(covered) == FLIT_WIDTH
    assert sorted(covered) == list(range(FLIT_WIDTH))
    assert sum(msb - lsb + 1 for msb, lsb in FIELD_RANGES.values()) == FLIT_WIDTH
    assert CONFIG.payload_width == 104
    assert tuple(
        (field.name, field.msb, field.lsb) for field in CONFIG.flit_fields
    ) == tuple(
        (name, msb, lsb) for name, (msb, lsb) in FIELD_RANGES.items()
    )


@pytest.mark.parametrize(
    "packed",
    [
        PackedFlit(
            head=True,
            tail=False,
            payload=(1 << 104) - 1,
            header=PackedHeader(1, 0, 0, 1, 0xA55A),
        ),
        PackedFlit(
            head=True,
            tail=True,
            payload=0x1234,
            header=PackedHeader(0, 1, 1, 0, 0xFFFF),
        ),
        PackedFlit(head=False, tail=False, payload=0x55, header=None),
        PackedFlit(head=False, tail=True, payload=0xAA, header=None),
    ],
)
def test_ENC_001_pack_unpack_round_trip(packed: PackedFlit) -> None:
    word = pack_flit(
        head=packed.head,
        tail=packed.tail,
        payload=packed.payload,
        header=packed.header,
    )

    assert 0 <= word < (1 << FLIT_WIDTH)
    assert unpack_flit(word) == packed


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (
            lambda: pack_flit(
                head=True,
                tail=False,
                payload=0,
                header=PackedHeader(2, 0, 0, 0, 0),
            ),
            "destination_x",
        ),
        (
            lambda: pack_flit(
                head=True,
                tail=False,
                payload=0,
                header=PackedHeader(0, 0, 0, 0, 1 << 16),
            ),
            "packet_id",
        ),
        (
            lambda: pack_flit(
                head=True,
                tail=False,
                payload=0,
                header=PackedHeader(0, 0, 0, 0, 0, qos_class=1),
            ),
            "QoS class 0",
        ),
        (
            lambda: pack_flit(head=False, tail=False, payload=0, header=PackedHeader(0, 0, 0, 0, 0)),
            "exactly header flits",
        ),
        (
            lambda: pack_flit(head=True, tail=False, payload=0, header=None),
            "exactly header flits",
        ),
        (
            lambda: pack_flit(head=False, tail=False, payload=1 << 104),
            "payload",
        ),
    ],
)
def test_ENC_001_rejects_unrepresentable_or_illegal_fields(
    call: object, match: str
) -> None:
    assert callable(call)
    with pytest.raises(EncodingError, match=match):
        call()


def test_ENC_001_unpack_rejects_illegal_reserved_or_qos_bits() -> None:
    body_with_destination = 1 << FIELD_RANGES["destination_x"][1]
    with pytest.raises(EncodingError, match="zero header-only"):
        unpack_flit(body_with_destination)

    header_with_qos_class_1 = (1 << FIELD_RANGES["head"][1]) | (
        1 << FIELD_RANGES["qos_class"][1]
    )
    with pytest.raises(EncodingError, match="QoS class 0"):
        unpack_flit(header_with_qos_class_1)


def test_IFACE_001_port_order_width_and_numeric_encoding_are_frozen() -> None:
    assert tuple(PORT_IDS) == CONFIG.ports
    assert PORT_IDS == dict(CONFIG.port_encoding)
    assert PORT_ID_WIDTH == CONFIG.port_id_width == 3
    assert INVALID_PORT_IDS == CONFIG.invalid_port_ids == (5, 6, 7)
    assert [decode_port_id(encode_port_id(name)) for name in PORT_IDS] == list(PORT_IDS)
    for reserved in INVALID_PORT_IDS:
        with pytest.raises(EncodingError, match="reserved physical port"):
            decode_port_id(reserved)


def test_IFACE_001_vc_width_and_numeric_encoding_are_frozen() -> None:
    assert VC_ID_WIDTH == CONFIG.vc_id_width == 1
    assert dict(CONFIG.vc_encoding) == {"vc0": 0, "vc1": 1}
    assert CONFIG.invalid_vc_ids == ()
    assert [decode_vc_id(encode_vc_id(vc)) for vc in range(2)] == [0, 1]
    with pytest.raises(EncodingError, match="does not fit"):
        encode_vc_id(2)


def test_IFACE_002_external_cycle_interface_shapes_are_frozen() -> None:
    assert CONFIG.port_dimension == "unpacked"
    assert CONFIG.data_dimensions == "packed"
    assert CONFIG.transfer_edge == "rising"
    assert not CONFIG.has_rx_ready
    assert not CONFIG.has_tx_ready
    assert {
        signal.name: (signal.direction, signal.shape)
        for signal in CONFIG.interface_signals
    } == {
        "clk": ("input", (1,)),
        "rst_n": ("input", (1,)),
        "port_enable": ("input", ("PORTS",)),
        "rx_valid": ("input", ("PORTS",)),
        "rx_flit": ("input", ("PORTS", "FLIT_W")),
        "rx_vc": ("input", ("PORTS", "VC_ID_W")),
        "tx_valid": ("output", ("PORTS",)),
        "tx_flit": ("output", ("PORTS", "FLIT_W")),
        "tx_vc": ("output", ("PORTS", "VC_ID_W")),
        "credit_out_valid": ("output", ("PORTS",)),
        "credit_out_vc": ("output", ("PORTS", "VC_ID_W")),
        "credit_in_valid": ("input", ("PORTS",)),
        "credit_in_vc": ("input", ("PORTS", "VC_ID_W")),
    }
