"""Packet-lifetime output-VC allocation for one physical output."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .arbitration import RoundRobinArbiter


class VCAllocationError(ValueError):
    """Raised for an invalid output-VC ownership transition."""


@dataclass(frozen=True, slots=True)
class VCAllocation:
    owner: int
    output_vc: int


class OutputVCAllocator:
    """Allocate one free output VC per decision and retain packet ownership."""

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
        self._validate_output_vc(output_vc)
        return self._owners[output_vc]

    def allocated_vc(self, owner: int) -> int | None:
        self._validate_owner(owner)
        matches = [vc for vc, assigned in enumerate(self._owners) if assigned == owner]
        if len(matches) > 1:
            raise VCAllocationError("one owner holds multiple output VCs")
        return matches[0] if matches else None

    def allocate(self, eligible: Sequence[bool]) -> VCAllocation | None:
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
