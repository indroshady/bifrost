"""Public API for the executable Bifröst Core v0.2 architectural model.

The package exports semantic data types and independently testable components
alongside :class:`BifrostRouter`, the cycle-level integration oracle.
"""

from .arbitration import ArbitrationError, RoundRobinArbiter
from .config import BifrostConfig, ConfigError, load_config
from .credits import CreditCounter, CreditProtocolError
from .encoding import (
    FIELD_RANGES,
    FLIT_WIDTH,
    INVALID_PORT_IDS,
    PORT_IDS,
    PORT_ID_WIDTH,
    QOS_WIDTH,
    VC_IDS,
    VC_ID_WIDTH,
    EncodingError,
    PackedFlit,
    PackedHeader,
    decode_port_id,
    decode_vc_id,
    encode_port_id,
    encode_vc_id,
    pack_flit,
    unpack_flit,
)
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
    "EncodingError",
    "FIELD_RANGES",
    "FIFOProtocolError",
    "FLIT_WIDTH",
    "Flit",
    "FlitArrival",
    "FlitTransfer",
    "FlitValidationError",
    "HeaderFields",
    "InputVCState",
    "INVALID_PORT_IDS",
    "OutputVCAllocator",
    "PacketMarker",
    "PacketStreamValidator",
    "PackedFlit",
    "PackedHeader",
    "Port",
    "PORT_IDS",
    "PORT_ID_WIDTH",
    "QOS_WIDTH",
    "RoundRobinArbiter",
    "RouterProtocolError",
    "RoutingError",
    "UpstreamCredit",
    "VC_IDS",
    "VC_ID_WIDTH",
    "VCAllocation",
    "VCAllocationError",
    "VirtualChannelFIFO",
    "decode_port_id",
    "decode_vc_id",
    "encode_port_id",
    "encode_vc_id",
    "load_config",
    "pack_flit",
    "route_xy",
    "unpack_flit",
]
