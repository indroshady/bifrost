from __future__ import annotations

import pytest

from bifrost_model.fifo import FIFOProtocolError, VirtualChannelFIFO
from bifrost_model.flit import Flit, FlitValidationError, HeaderFields


def _header(packet_id: int = 1) -> HeaderFields:
    return HeaderFields(
        destination_x=1,
        destination_y=0,
        source_x=0,
        source_y=0,
        packet_id=packet_id,
    )


def test_VC_001_independent_vc_state() -> None:
    vc0 = VirtualChannelFIFO(depth=4)
    vc1 = VirtualChannelFIFO(depth=4)
    first = Flit(head=True, tail=True, payload="vc0", header=_header(0))
    second = Flit(head=True, tail=False, payload="vc1-head", header=_header(1))

    vc0.enqueue(first)
    vc1.enqueue(second)

    assert vc0.occupancy == vc1.occupancy == 1
    assert not vc0.incoming_packet_active
    assert vc1.incoming_packet_active
    assert vc0.dequeue() is first
    assert vc1.peek() is second
    assert vc0.empty
    assert vc1.occupancy == 1


def test_VC_001_fifo_bounds_order_and_reset() -> None:
    fifo = VirtualChannelFIFO(depth=3)
    flits = (
        Flit(head=True, tail=False, payload="head", header=_header()),
        Flit(head=False, tail=False, payload="body"),
        Flit(head=False, tail=True, payload="tail"),
    )
    for flit in flits:
        fifo.enqueue(flit)

    assert fifo.full
    with pytest.raises(FIFOProtocolError, match="overflow"):
        fifo.enqueue(Flit(head=True, tail=True, payload="next", header=_header(2)))
    assert tuple(fifo) == flits
    assert [fifo.dequeue() for _ in flits] == list(flits)
    with pytest.raises(FIFOProtocolError, match="underflow"):
        fifo.peek()
    with pytest.raises(FIFOProtocolError, match="underflow"):
        fifo.dequeue()

    fifo.enqueue(Flit(head=True, tail=False, payload="discard", header=_header(3)))
    fifo.reset()
    assert fifo.empty
    assert fifo.occupancy == 0
    assert not fifo.incoming_packet_active
    fifo.enqueue(Flit(head=True, tail=True, payload="new", header=_header(4)))


def test_FUNC_003_fifo_rejects_invalid_packet_transitions() -> None:
    fifo = VirtualChannelFIFO(depth=4)

    with pytest.raises(FlitValidationError, match="must begin with a header"):
        fifo.enqueue(Flit(head=False, tail=False, payload="body"))
    fifo.enqueue(Flit(head=True, tail=False, payload="head", header=_header()))
    with pytest.raises(FlitValidationError, match="second header"):
        fifo.enqueue(
            Flit(head=True, tail=True, payload="second", header=_header(2))
        )
    assert fifo.occupancy == 1
    assert fifo.incoming_packet_active


def test_VC_001_fifo_constructor_and_entry_types_are_strict() -> None:
    with pytest.raises(FIFOProtocolError, match="positive integer"):
        VirtualChannelFIFO(depth=0)
    fifo = VirtualChannelFIFO(depth=1)
    with pytest.raises(FIFOProtocolError, match="Flit instances"):
        fifo.enqueue("not-a-flit")  # type: ignore[arg-type]
