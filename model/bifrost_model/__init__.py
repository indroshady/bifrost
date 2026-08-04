"""Executable architectural behavior for the Bifröst Core v0.2 profile."""

from .config import BifrostConfig, ConfigError, load_config
from .credits import CreditCounter, CreditProtocolError
from .flit import (
    Flit,
    FlitValidationError,
    HeaderFields,
    PacketMarker,
    PacketStreamValidator,
)
from .routing import Port, RoutingError, route_xy

__all__ = [
    "BifrostConfig",
    "ConfigError",
    "CreditCounter",
    "CreditProtocolError",
    "Flit",
    "FlitValidationError",
    "HeaderFields",
    "PacketMarker",
    "PacketStreamValidator",
    "Port",
    "RoutingError",
    "load_config",
    "route_xy",
]
