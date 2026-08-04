from __future__ import annotations

import pytest

from bifrost_model.arbitration import ArbitrationError, RoundRobinArbiter


def test_ARB_001_at_most_one_eligible_winner() -> None:
    arbiter = RoundRobinArbiter(4)

    assert arbiter.grant((False, False, False, False)) is None
    assert arbiter.pointer == 0
    assert arbiter.grant((False, True, True, True)) == 1
    assert arbiter.pointer == 2
    assert arbiter.grant((True, True, False, True)) == 3
    assert arbiter.pointer == 0


def test_ARB_002_round_robin_bound() -> None:
    requester_count = 5
    arbiter = RoundRobinArbiter(requester_count)
    winners = [
        arbiter.grant((True,) * requester_count)
        for _ in range(requester_count * 3)
    ]

    assert winners == list(range(requester_count)) * 3
    for start in range(len(winners) - requester_count + 1):
        assert set(winners[start : start + requester_count]) == set(
            range(requester_count)
        )


def test_ARB_002_pointer_advances_only_after_successful_transfer() -> None:
    arbiter = RoundRobinArbiter(3)

    assert arbiter.choose((False, True, True)) == 1
    assert arbiter.choose((False, True, True)) == 1
    assert arbiter.pointer == 0
    assert arbiter.grant((False, False, False)) is None
    assert arbiter.pointer == 0
    arbiter.record_grant(1)
    assert arbiter.pointer == 2
    arbiter.reset()
    assert arbiter.pointer == 0


def test_ARB_001_rejects_malformed_eligibility_and_winners() -> None:
    with pytest.raises(ArbitrationError, match="positive integer"):
        RoundRobinArbiter(0)
    arbiter = RoundRobinArbiter(2)
    with pytest.raises(ArbitrationError, match="expected 2"):
        arbiter.grant((True,))
    with pytest.raises(ArbitrationError, match="booleans"):
        arbiter.grant((True, 1))  # type: ignore[arg-type]
    with pytest.raises(ArbitrationError, match="outside"):
        arbiter.record_grant(2)
