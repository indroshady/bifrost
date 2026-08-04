"""Packet-lifetime output-VC allocation for one physical output.

Ownership and downstream credit availability are independent state. Allocation
uses round-robin selection for both requesters and free VCs, then ownership is
retained until the owning packet's transmitted tail explicitly releases it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .arbitration import RoundRobinArbiter


class VCAllocationError(ValueError):
    """Raised for an invalid output-VC ownership transition."""


@dataclass(frozen=True, slots=True)
class VCAllocation:
    """A successful binding between an input-VC owner and an output VC."""

    owner: int
    output_vc: int


class OutputVCAllocator:
    """Own the allocation table and fairness pointers for one output port."""

    def __init__(self, *, num_vcs: int, requester_count: int) -> None:
        if isinstance(num_vcs, bool) or not isinstance(num_vcs, int) or num_vcs < 1:
            raise VCAllocationError("num_vcs must be a positive integer")
        self._num_vcs = num_vcs
        self._requester_count = requester_count
        self._owners: list[int | None] = [None] * num_vcs
        self._requester_arbiter = RoundRobinArbiter(requester_count)
        self._vc_pointer = 0

    @property
    def num_vcs(self) -> int:
        return self._num_vcs

    @property
    def requester_pointer(self) -> int:
        return self._requester_arbiter.pointer

    @property
    def vc_pointer(self) -> int:
        return self._vc_pointer

    def owner_of(self, output_vc: int) -> int | None:
        """Return the requester that owns ``output_vc``, if any."""

        self._validate_output_vc(output_vc)
        return self._owners[output_vc]

    def allocated_vc(self, owner: int) -> int | None:
        """Return the single output VC held by ``owner``, if any."""

        self._validate_owner(owner)
        matches = [vc for vc, assigned in enumerate(self._owners) if assigned == owner]
        if len(matches) > 1:
            raise VCAllocationError("one owner holds multiple output VCs")
        return matches[0] if matches else None

    def allocate(self, eligible: Sequence[bool]) -> VCAllocation | None:
        """Allocate at most one free VC to one eligible requester."""

        selected = tuple(eligible)
        if len(selected) != self._requester_count:
            raise VCAllocationError(
                f"expected {self._requester_count} eligibility entries"
            )
        if any(type(value) is not bool for value in selected):
            raise VCAllocationError("eligibility entries must be booleans")
        for owner, requested in enumerate(selected):
            if requested and self.allocated_vc(owner) is not None:
                raise VCAllocationError("an owner cannot request a second output VC")

        # A missing free VC is not a protocol error; requesters remain pending
        # and neither fairness pointer advances.
        free_vc = self._choose_free_vc()
        if free_vc is None:
            return None
        owner = self._requester_arbiter.grant(selected)
        if owner is None:
            return None

        self._owners[free_vc] = owner
        self._vc_pointer = (free_vc + 1) % self._num_vcs
        return VCAllocation(owner=owner, output_vc=free_vc)

    def release(
        self,
        *,
        output_vc: int,
        owner: int,
        tail_transmitted: bool,
    ) -> None:
        """Release ownership after, and only after, a successful tail transfer."""

        self._validate_output_vc(output_vc)
        self._validate_owner(owner)
        if type(tail_transmitted) is not bool:
            raise VCAllocationError("tail_transmitted must be a boolean")
        if not tail_transmitted:
            raise VCAllocationError("output VC may be released only by a transmitted tail")
        assigned = self._owners[output_vc]
        if assigned is None:
            raise VCAllocationError("cannot release an unallocated output VC")
        if assigned != owner:
            raise VCAllocationError("only the current owner may release an output VC")
        self._owners[output_vc] = None

    def reset(self) -> None:
        """Clear ownership and restore both round-robin pointers."""

        self._owners = [None] * self._num_vcs
        self._requester_arbiter.reset()
        self._vc_pointer = 0

    def _choose_free_vc(self) -> int | None:
        for offset in range(self._num_vcs):
            output_vc = (self._vc_pointer + offset) % self._num_vcs
            if self._owners[output_vc] is None:
                return output_vc
        return None

    def _validate_output_vc(self, output_vc: int) -> None:
        if (
            isinstance(output_vc, bool)
            or not isinstance(output_vc, int)
            or not 0 <= output_vc < self._num_vcs
        ):
            raise VCAllocationError("output_vc is outside the configured range")

    def _validate_owner(self, owner: int) -> None:
        if (
            isinstance(owner, bool)
            or not isinstance(owner, int)
            or not 0 <= owner < self._requester_count
        ):
            raise VCAllocationError("owner is outside the requester range")
