"""Semantic flit representation and legal packet-marker validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class FlitValidationError(ValueError):
    """Raised for malformed semantic flits or packet-marker sequences."""


class PacketMarker(str, Enum):
    HEAD = "head"
    BODY = "body"
    TAIL = "tail"
    HEAD_TAIL = "head_tail"

    @classmethod
    def from_flags(cls, *, head: bool, tail: bool) -> "PacketMarker":
        if type(head) is not bool or type(tail) is not bool:
            raise FlitValidationError("head and tail markers must be booleans")
        if head and tail:
            return cls.HEAD_TAIL
        if head:
            return cls.HEAD
        if tail:
            return cls.TAIL
        return cls.BODY


def _nonnegative_integer(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FlitValidationError(f"{name} must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class HeaderFields:
    """Architecturally meaningful header metadata, without a bit encoding."""

    destination_x: int
    destination_y: int
    source_x: int
    source_y: int
    packet_id: int
    qos_class: int = 0

    def __post_init__(self) -> None:
        for name in (
            "destination_x",
            "destination_y",
            "source_x",
            "source_y",
            "packet_id",
            "qos_class",
        ):
            _nonnegative_integer(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class Flit:
    """One semantic flit; payload layout and RTL encoding are intentionally absent."""

    head: bool
    tail: bool
    payload: Any
    header: HeaderFields | None = None

    def __post_init__(self) -> None:
        marker = PacketMarker.from_flags(head=self.head, tail=self.tail)
        if marker in {PacketMarker.HEAD, PacketMarker.HEAD_TAIL}:
            if self.header is None:
                raise FlitValidationError("header flits require HeaderFields")
        elif self.header is not None:
            raise FlitValidationError("non-header flits cannot carry HeaderFields")

    @property
    def marker(self) -> PacketMarker:
        return PacketMarker.from_flags(head=self.head, tail=self.tail)


class PacketStreamValidator:
    """Track marker legality for one input VC; bubbles require no state change."""

    def __init__(self) -> None:
        self._packet_active = False

    @property
    def packet_active(self) -> bool:
        return self._packet_active

    def accept(self, flit: Flit) -> None:
        marker = flit.marker
        if not self._packet_active:
            if marker is PacketMarker.HEAD:
                self._packet_active = True
                return
            if marker is PacketMarker.HEAD_TAIL:
                return
            raise FlitValidationError("an idle VC must begin with a header")

        if marker in {PacketMarker.HEAD, PacketMarker.HEAD_TAIL}:
            raise FlitValidationError("a second header arrived before the active tail")
        if marker is PacketMarker.TAIL:
            self._packet_active = False

    def reset(self) -> None:
        self._packet_active = False
