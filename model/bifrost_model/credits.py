"""Registered downstream-credit state for one output VC.

Authorization always uses the current registered count. A return arriving in
the same cycle may offset a send only when that current count is already
positive; it can never provide a zero-credit combinational bypass.
"""

from __future__ import annotations


class CreditProtocolError(ValueError):
    """Raised when a credit event violates the Core v0.2 contract."""


class CreditCounter:
    """Bounded counter implementing the Core v0.2 credit truth table."""

    def __init__(
        self,
        depth: int,
        *,
        initial: int | None = None,
        enabled: bool = True,
    ) -> None:
        if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
            raise CreditProtocolError("depth must be a positive integer")
        if type(enabled) is not bool:
            raise CreditProtocolError("enabled must be a boolean")
        expected_initial = depth if enabled else 0
        selected_initial = expected_initial if initial is None else initial
        if (
            isinstance(selected_initial, bool)
            or not isinstance(selected_initial, int)
            or not 0 <= selected_initial <= depth
        ):
            raise CreditProtocolError("initial credit must be within [0, depth]")
        if not enabled and selected_initial != 0:
            raise CreditProtocolError("a disabled link must initialize with zero credits")

        self._depth = depth
        self._count = selected_initial
        self._enabled = enabled

    @property
    def depth(self) -> int:
        return self._depth

    @property
    def count(self) -> int:
        return self._count

    @property
    def can_send(self) -> bool:
        return self._enabled and self._count > 0

    def next_count(self, *, send: bool, credit_return: bool) -> int:
        """Validate one cycle and return its next count without committing it."""
        if type(send) is not bool or type(credit_return) is not bool:
            raise CreditProtocolError("send and credit_return must be booleans")
        if not self._enabled and (send or credit_return):
            raise CreditProtocolError("events on a disabled link are protocol errors")
        if send and self._count == 0:
            raise CreditProtocolError(
                "send requires positive current registered credit"
            )
        if credit_return and not send and self._count == self._depth:
            raise CreditProtocolError("credit return would overflow the counter")

        next_count = self._count - int(send) + int(credit_return)
        if not 0 <= next_count <= self._depth:
            raise CreditProtocolError("credit update would exceed legal bounds")
        return next_count

    def apply(self, *, send: bool, credit_return: bool) -> int:
        """Apply one cycle and return the new registered credit count."""

        next_count = self.next_count(send=send, credit_return=credit_return)
        self._count = next_count
        return self._count

    def reset(self) -> None:
        """Restore an enabled link to full capacity and a disabled link to zero."""

        self._count = self._depth if self._enabled else 0
