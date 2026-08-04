"""Independent packed-bit contract helpers for the frozen Core v0.2 flit.

The architectural router continues to transport arbitrary Python payload
objects. These helpers operate only on integer wire images for RTL, testbench,
and integration use.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


FLIT_WIDTH = 128
PORT_ID_WIDTH = 3
VC_ID_WIDTH = 1
QOS_WIDTH = 2

PORT_IDS: Mapping[str, int] = MappingProxyType(
    {"local": 0, "north": 1, "south": 2, "east": 3, "west": 4}
)
INVALID_PORT_IDS = (5, 6, 7)
VC_IDS: Mapping[str, int] = MappingProxyType({"vc0": 0, "vc1": 1})

FIELD_RANGES: Mapping[str, tuple[int, int]] = MappingProxyType(
    {
        "head": (127, 127),
        "tail": (126, 126),
        "destination_x": (125, 125),
        "destination_y": (124, 124),
        "source_x": (123, 123),
        "source_y": (122, 122),
        "packet_id": (121, 106),
        "qos_class": (105, 104),
        "payload": (103, 0),
    }
)
_HEADER_ONLY_FIELDS = (
    "destination_x",
    "destination_y",
    "source_x",
    "source_y",
    "packet_id",
    "qos_class",
)
_HEADER_ONLY_MASK = sum(
    ((1 << _width) - 1) << lsb
    for msb, lsb in (FIELD_RANGES[name] for name in _HEADER_ONLY_FIELDS)
    for _width in (msb - lsb + 1,)
)


class EncodingError(ValueError):
    """Raised when a value cannot be represented by the frozen contract."""


@dataclass(frozen=True, slots=True)
class PackedHeader:
    """Integer header fields decoded from or supplied to a packed flit."""

    destination_x: int
    destination_y: int
    source_x: int
    source_y: int
    packet_id: int
    qos_class: int = 0


@dataclass(frozen=True, slots=True)
class PackedFlit:
    """Decoded integer representation of one frozen Core v0.2 wire flit."""

    head: bool
    tail: bool
    payload: int
    header: PackedHeader | None


def _width(name: str) -> int:
    msb, lsb = FIELD_RANGES[name]
    return msb - lsb + 1


def _checked_integer(name: str, value: object, width: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EncodingError(f"{name} must be an integer")
    if not 0 <= value < (1 << width):
        raise EncodingError(f"{name} does not fit in {width} bits")
    return value


def _insert(word: int, name: str, value: int) -> int:
    _, lsb = FIELD_RANGES[name]
    return word | (value << lsb)


def _extract(word: int, name: str) -> int:
    _, lsb = FIELD_RANGES[name]
    return (word >> lsb) & ((1 << _width(name)) - 1)


def encode_port_id(port: str) -> int:
    """Return the frozen numeric ID for one named physical port."""

    try:
        return PORT_IDS[port]
    except KeyError as exc:
        raise EncodingError(f"unknown physical port {port!r}") from exc


def decode_port_id(value: int) -> str:
    """Decode a legal three-bit physical-port ID and reject 5 through 7."""

    checked = _checked_integer("port_id", value, PORT_ID_WIDTH)
    for name, port_id in PORT_IDS.items():
        if checked == port_id:
            return name
    raise EncodingError(f"reserved physical port ID {checked}")


def encode_vc_id(vc: int) -> int:
    """Validate the selected VC index for the one-bit sideband."""

    checked = _checked_integer("vc_id", vc, VC_ID_WIDTH)
    if checked >= len(VC_IDS):
        raise EncodingError(f"reserved VC ID {checked}")
    return checked


def decode_vc_id(value: int) -> int:
    """Decode the one-bit VC sideband; both bit patterns are legal."""

    return encode_vc_id(value)


def pack_flit(
    *,
    head: bool,
    tail: bool,
    payload: int,
    header: PackedHeader | None = None,
) -> int:
    """Pack one legal integer wire image without touching semantic model flits."""

    if type(head) is not bool or type(tail) is not bool:
        raise EncodingError("head and tail must be booleans")
    if head != (header is not None):
        raise EncodingError("exactly header flits must provide PackedHeader")

    word = 0
    word = _insert(word, "head", int(head))
    word = _insert(word, "tail", int(tail))
    word = _insert(
        word,
        "payload",
        _checked_integer("payload", payload, _width("payload")),
    )
    if header is None:
        return word
    for name in (
        "destination_x",
        "destination_y",
        "source_x",
        "source_y",
        "packet_id",
    ):
        word = _insert(
            word,
            name,
            _checked_integer(name, getattr(header, name), _width(name)),
        )
    qos_class = _checked_integer("qos_class", header.qos_class, QOS_WIDTH)
    if qos_class != 0:
        raise EncodingError("Core v0.2 accepts only QoS class 0")
    return _insert(word, "qos_class", qos_class)


def unpack_flit(word: int) -> PackedFlit:
    """Decode one 128-bit wire image, enforcing Core header QoS semantics."""

    checked = _checked_integer("flit", word, FLIT_WIDTH)
    head = bool(_extract(checked, "head"))
    tail = bool(_extract(checked, "tail"))
    payload = _extract(checked, "payload")
    if not head:
        if checked & _HEADER_ONLY_MASK:
            raise EncodingError("body and tail flits must zero header-only fields")
        return PackedFlit(head=head, tail=tail, payload=payload, header=None)
    qos_class = _extract(checked, "qos_class")
    if qos_class != 0:
        raise EncodingError("Core v0.2 accepts only QoS class 0")
    return PackedFlit(
        head=head,
        tail=tail,
        payload=payload,
        header=PackedHeader(
            destination_x=_extract(checked, "destination_x"),
            destination_y=_extract(checked, "destination_y"),
            source_x=_extract(checked, "source_x"),
            source_y=_extract(checked, "source_y"),
            packet_id=_extract(checked, "packet_id"),
            qos_class=qos_class,
        ),
    )
