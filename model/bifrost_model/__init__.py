"""Executable architectural behavior for the Bifröst Core v0.2 profile."""

from .arbitration import ArbitrationError, RoundRobinArbiter
from .config import BifrostConfig, ConfigError, load_config
from .credits import CreditCounter, CreditProtocolError
from .fifo import FIFOProtocolError, VirtualChannelFIFO
from .flit import (
    Flit,
    FlitValidationError,
    HeaderFields,
    PacketMarker,
    PacketStreamValidator,
)
from .routing import Port, RoutingError, route_xy
from .router import (
    BifrostRouter,
    CycleResult,
    DownstreamCredit,
    FlitArrival,
    FlitTransfer,
    InputVCState,
    RouterProtocolError,
    UpstreamCredit,
)
from .vc_allocator import OutputVCAllocator, VCAllocation, VCAllocationError

__all__ = [
    "ArbitrationError",
    "BifrostConfig",
    "BifrostRouter",
    "ConfigError",
    "CreditCounter",
    "CreditProtocolError",
    "CycleResult",
    "DownstreamCredit",
    "FIFOProtocolError",
    "Flit",
    "FlitArrival",
    "FlitTransfer",
    "FlitValidationError",
    "HeaderFields",
    "InputVCState",
    "OutputVCAllocator",
    "PacketMarker",
    "PacketStreamValidator",
    "Port",
    "RoundRobinArbiter",
    "RouterProtocolError",
    "RoutingError",
    "UpstreamCredit",
    "VCAllocation",
    "VCAllocationError",
    "VirtualChannelFIFO",
    "load_config",
    "route_xy",
]
