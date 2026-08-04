from __future__ import annotations

import pytest

from bifrost_model.flit import (
    Flit,
    FlitValidationError,
    HeaderFields,
    PacketMarker,
    PacketStreamValidator,
)


def _header() -> HeaderFields:
    return HeaderFields(
        destination_x=1,
        destination_y=0,
        source_x=0,
        source_y=0,
        packet_id=7,
    )


def test_FUNC_003_legal_packet_marker_sequences() -> None:
    validator = PacketStreamValidator()
    validator.accept(Flit(head=True, tail=True, payload="single", header=_header()))
    assert not validator.packet_active

    validator.accept(Flit(head=True, tail=False, payload="head", header=_header()))
    assert validator.packet_active
    validator.accept(Flit(head=False, tail=False, payload="body"))
    assert validator.packet_active
    validator.accept(Flit(head=False, tail=True, payload="tail"))
    assert not validator.packet_active

    validator.accept(Flit(head=True, tail=False, payload="head", header=_header()))
    validator.accept(Flit(head=False, tail=True, payload="tail"))
    assert not validator.packet_active


@pytest.mark.parametrize(
    ("head", "tail", "expected"),
    [
        (True, False, PacketMarker.HEAD),
        (False, False, PacketMarker.BODY),
        (False, True, PacketMarker.TAIL),
        (True, True, PacketMarker.HEAD_TAIL),
    ],
)
def test_FUNC_003_all_legal_marker_flag_combinations(
    head: bool,
    tail: bool,
    expected: PacketMarker,
) -> None:
    assert PacketMarker.from_flags(head=head, tail=tail) is expected


@pytest.mark.parametrize(
    "flit",
    [
        Flit(head=False, tail=False, payload="body"),
        Flit(head=False, tail=True, payload="tail"),
    ],
)
def test_FUNC_003_idle_vc_rejects_non_header(flit: Flit) -> None:
    with pytest.raises(FlitValidationError, match="must begin with a header"):
        PacketStreamValidator().accept(flit)


@pytest.mark.parametrize(
    "second",
    [
        Flit(head=True, tail=False, payload="second-head", header=_header()),
        Flit(head=True, tail=True, payload="single", header=_header()),
    ],
)
def test_FUNC_003_active_packet_rejects_second_header(second: Flit) -> None:
    validator = PacketStreamValidator()
    validator.accept(Flit(head=True, tail=False, payload="head", header=_header()))

    with pytest.raises(FlitValidationError, match="second header"):
        validator.accept(second)


def test_FUNC_003_marker_and_header_metadata_validation() -> None:
    with pytest.raises(FlitValidationError, match="must be booleans"):
        PacketMarker.from_flags(head=1, tail=False)  # type: ignore[arg-type]
    with pytest.raises(FlitValidationError, match="require HeaderFields"):
        Flit(head=True, tail=False, payload="missing")
    with pytest.raises(FlitValidationError, match="cannot carry HeaderFields"):
        Flit(head=False, tail=False, payload="body", header=_header())
    with pytest.raises(FlitValidationError, match="nonnegative integer"):
        HeaderFields(-1, 0, 0, 0, 0)
