"""Deterministic per-flit round-robin arbitration.

Selection and commitment are separate operations because router matching may
reject an output's proposal due to a shared physical-input conflict. Only a
transfer that actually commits is allowed to advance history.
"""

from __future__ import annotations

from collections.abc import Sequence


class ArbitrationError(ValueError):
    """Raised for malformed eligibility or grant transitions."""


class RoundRobinArbiter:
    """One-hot-or-zero arbiter with successful-grant-only pointer updates."""

    def __init__(self, requester_count: int) -> None:
        if (
            isinstance(requester_count, bool)
            or not isinstance(requester_count, int)
            or requester_count < 1
        ):
            raise ArbitrationError("requester_count must be a positive integer")
        self._requester_count = requester_count
        self._pointer = 0

    @property
    def requester_count(self) -> int:
        return self._requester_count

    @property
    def pointer(self) -> int:
        return self._pointer

    def _validated(self, eligible: Sequence[bool]) -> tuple[bool, ...]:
        """Normalize eligibility while rejecting implicit truthy values."""

        selected = tuple(eligible)
        if len(selected) != self._requester_count:
            raise ArbitrationError(
                f"expected {self._requester_count} eligibility entries"
            )
        if any(type(value) is not bool for value in selected):
            raise ArbitrationError("eligibility entries must be booleans")
        return selected

    def choose(self, eligible: Sequence[bool]) -> int | None:
        """Select a winner without changing history."""

        selected = self._validated(eligible)
        # Search from the pointer and wrap exactly once, which makes the first
        # eligible requester deterministic.
        for offset in range(self._requester_count):
            requester = (self._pointer + offset) % self._requester_count
            if selected[requester]:
                return requester
        return None

    def record_grant(self, winner: int) -> None:
        """Commit a successful transfer and advance behind its winner."""

        if (
            isinstance(winner, bool)
            or not isinstance(winner, int)
            or not 0 <= winner < self._requester_count
        ):
            raise ArbitrationError("winner is outside the requester range")
        self._pointer = (winner + 1) % self._requester_count

    def grant(self, eligible: Sequence[bool]) -> int | None:
        """Choose and immediately commit a winner for standalone arbitration."""

        winner = self.choose(eligible)
        if winner is not None:
            self.record_grant(winner)
        return winner

    def reset(self) -> None:
        """Restore the documented initial requester position."""

        self._pointer = 0
