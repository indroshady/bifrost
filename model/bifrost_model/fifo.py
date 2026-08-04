"""Bounded input-VC FIFO behavior for the Bifröst Core v0.2 model."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator

from .flit import Flit, FlitValidationError, PacketMarker, PacketStreamValidator


class FIFOProtocolError(ValueError):
    """Raised when an input-VC FIFO operation violates the protocol."""


class VirtualChannelFIFO:
    """One bounded, ordered flit FIFO with independent arrival-stream state."""

    def __init__(self, depth: int) -> None:
        if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
            raise FIFOProtocolError("depth must be a positive integer")
        self._depth = depth
        self._entries: deque[Flit] = deque()
        self._stream = PacketStreamValidator()

    @property
    def depth(self) -> int:
        return self._depth

    @property
    def occupancy(self) -> int:
        return len(self._entries)

    @property
    def empty(self) -> bool:
        return not self._entries

    @property
    def full(self) -> bool:
        return len(self._entries) == self._depth

    @property
    def incoming_packet_active(self) -> bool:
        return self._stream.packet_active

    def validate_enqueue(self, flit: Flit) -> None:
        """Validate an enqueue without changing FIFO or packet-stream state."""

        if not isinstance(flit, Flit):
            raise FIFOProtocolError("FIFO entries must be Flit instances")
        if self.full:
            raise FIFOProtocolError("enqueue would overflow the FIFO")

        marker = flit.marker
        if not self._stream.packet_active:
            if marker not in {PacketMarker.HEAD, PacketMarker.HEAD_TAIL}:
                raise FlitValidationError("an idle VC must begin with a header")
        elif marker in {PacketMarker.HEAD, PacketMarker.HEAD_TAIL}:
            raise FlitValidationError("a second header arrived before the active tail")

    def enqueue(self, flit: Flit) -> None:
        self.validate_enqueue(flit)
        self._stream.accept(flit)
        self._entries.append(flit)

    def peek(self) -> Flit:
        if self.empty:
            raise FIFOProtocolError("peek would underflow the FIFO")
        return self._entries[0]

    def dequeue(self) -> Flit:
        if self.empty:
            raise FIFOProtocolError("dequeue would underflow the FIFO")
        return self._entries.popleft()

    def reset(self) -> None:
        self._entries.clear()
        self._stream.reset()

    def __iter__(self) -> Iterator[Flit]:
        return iter(tuple(self._entries))
