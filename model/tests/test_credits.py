from __future__ import annotations

import itertools

import pytest

from bifrost_model.credits import CreditCounter, CreditProtocolError


VC_DEPTH = 4


def test_FLOW_001_send_requires_registered_credit() -> None:
    counter = CreditCounter(VC_DEPTH, initial=0)

    with pytest.raises(CreditProtocolError, match="positive current registered"):
        counter.apply(send=True, credit_return=False)
    with pytest.raises(CreditProtocolError, match="positive current registered"):
        counter.apply(send=True, credit_return=True)
    assert counter.count == 0


def test_FLOW_002_credit_boundaries() -> None:
    with pytest.raises(CreditProtocolError, match="positive integer"):
        CreditCounter(0)
    with pytest.raises(CreditProtocolError, match=r"within \[0, depth\]"):
        CreditCounter(VC_DEPTH, initial=-1)
    with pytest.raises(CreditProtocolError, match=r"within \[0, depth\]"):
        CreditCounter(VC_DEPTH, initial=VC_DEPTH + 1)

    full = CreditCounter(VC_DEPTH)
    with pytest.raises(CreditProtocolError, match="overflow"):
        full.apply(send=False, credit_return=True)
    assert full.count == VC_DEPTH


@pytest.mark.parametrize("initial", [0, 1, VC_DEPTH])
@pytest.mark.parametrize(
    ("send", "credit_return"),
    list(itertools.product([False, True], repeat=2)),
)
def test_FLOW_004_all_simultaneous_events_at_boundary_counts(
    initial: int,
    send: bool,
    credit_return: bool,
) -> None:
    counter = CreditCounter(VC_DEPTH, initial=initial)
    invalid_zero_send = initial == 0 and send
    invalid_full_return = initial == VC_DEPTH and credit_return and not send

    if invalid_zero_send or invalid_full_return:
        with pytest.raises(CreditProtocolError):
            counter.apply(send=send, credit_return=credit_return)
        assert counter.count == initial
        return

    expected = initial - int(send) + int(credit_return)
    assert counter.apply(send=send, credit_return=credit_return) == expected
    assert counter.count == expected


def test_FLOW_002_disabled_link_and_invalid_events_are_rejected() -> None:
    disabled = CreditCounter(VC_DEPTH, enabled=False)
    assert disabled.count == 0
    assert not disabled.can_send
    assert disabled.apply(send=False, credit_return=False) == 0

    with pytest.raises(CreditProtocolError, match="disabled link"):
        disabled.apply(send=True, credit_return=False)
    with pytest.raises(CreditProtocolError, match="disabled link"):
        disabled.apply(send=False, credit_return=True)
    with pytest.raises(CreditProtocolError, match="must be booleans"):
        CreditCounter(VC_DEPTH).apply(send=1, credit_return=False)  # type: ignore[arg-type]
    with pytest.raises(CreditProtocolError, match="initialize with zero"):
        CreditCounter(VC_DEPTH, enabled=False, initial=1)
