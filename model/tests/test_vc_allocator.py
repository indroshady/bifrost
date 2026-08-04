from __future__ import annotations

import pytest

from bifrost_model.vc_allocator import OutputVCAllocator, VCAllocationError


def test_VC_002_unique_output_vc_ownership() -> None:
    allocator = OutputVCAllocator(num_vcs=2, requester_count=4)

    first = allocator.allocate((True, True, False, False))
    second = allocator.allocate((False, True, True, False))

    assert first is not None
    assert second is not None
    assert (first.owner, first.output_vc) == (0, 0)
    assert (second.owner, second.output_vc) == (1, 1)
    assert allocator.owner_of(0) == 0
    assert allocator.owner_of(1) == 1
    assert allocator.allocate((False, False, True, True)) is None
    with pytest.raises(VCAllocationError, match="second output VC"):
        allocator.allocate((True, False, False, False))


def test_VC_003_hold_ownership_until_tail() -> None:
    allocator = OutputVCAllocator(num_vcs=2, requester_count=2)
    allocation = allocator.allocate((True, False))
    assert allocation is not None

    assert allocator.owner_of(allocation.output_vc) == allocation.owner
    with pytest.raises(VCAllocationError, match="only by a transmitted tail"):
        allocator.release(
            output_vc=allocation.output_vc,
            owner=allocation.owner,
            tail_transmitted=False,
        )
    assert allocator.owner_of(allocation.output_vc) == allocation.owner


def test_VC_004_release_head_tail_and_multiflit_exactly_once() -> None:
    allocator = OutputVCAllocator(num_vcs=1, requester_count=2)
    single = allocator.allocate((True, False))
    assert single is not None
    allocator.release(
        output_vc=single.output_vc,
        owner=single.owner,
        tail_transmitted=True,
    )
    assert allocator.owner_of(single.output_vc) is None
    with pytest.raises(VCAllocationError, match="unallocated"):
        allocator.release(
            output_vc=single.output_vc,
            owner=single.owner,
            tail_transmitted=True,
        )

    multiflit = allocator.allocate((False, True))
    assert multiflit is not None
    assert multiflit.owner == 1
    allocator.release(
        output_vc=multiflit.output_vc,
        owner=multiflit.owner,
        tail_transmitted=True,
    )
    assert allocator.owner_of(multiflit.output_vc) is None


def test_VC_002_allocator_round_robin_and_reset() -> None:
    allocator = OutputVCAllocator(num_vcs=1, requester_count=3)
    winners: list[int] = []
    for _ in range(3):
        allocation = allocator.allocate((True, True, True))
        assert allocation is not None
        winners.append(allocation.owner)
        allocator.release(
            output_vc=allocation.output_vc,
            owner=allocation.owner,
            tail_transmitted=True,
        )

    assert winners == [0, 1, 2]
    allocator.reset()
    assert allocator.requester_pointer == 0
    assert allocator.vc_pointer == 0
    assert allocator.owner_of(0) is None


def test_VC_004_invalid_owner_and_release_transitions_are_rejected() -> None:
    allocator = OutputVCAllocator(num_vcs=1, requester_count=2)
    allocation = allocator.allocate((True, False))
    assert allocation is not None

    with pytest.raises(VCAllocationError, match="current owner"):
        allocator.release(output_vc=0, owner=1, tail_transmitted=True)
    with pytest.raises(VCAllocationError, match="configured range"):
        allocator.owner_of(1)
    with pytest.raises(VCAllocationError, match="booleans"):
        allocator.allocate((True, 1))  # type: ignore[arg-type]
