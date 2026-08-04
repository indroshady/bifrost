"""Cycle-level architectural oracle for the Bifröst Core v0.2 router."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .arbitration import RoundRobinArbiter
from .config import BifrostConfig
from .credits import CreditCounter
from .fifo import VirtualChannelFIFO
from .flit import Flit
from .routing import Port, route_xy
from .vc_allocator import OutputVCAllocator


class RouterProtocolError(ValueError):
    """Raised when a cycle input or internal transition violates Core v0.2."""


@dataclass(frozen=True, slots=True)
class FlitArrival:
    input_port: Port
    input_vc: int
    flit: Flit


@dataclass(frozen=True, slots=True)
class DownstreamCredit:
    output_port: Port
    output_vc: int


@dataclass(frozen=True, slots=True)
class FlitTransfer:
    output_port: Port
    output_vc: int
    input_port: Port
    input_vc: int
    flit: Flit


@dataclass(frozen=True, slots=True)
class UpstreamCredit:
    input_port: Port
    input_vc: int


@dataclass(frozen=True, slots=True)
class CycleResult:
    transfers: tuple[FlitTransfer, ...] = ()
    upstream_credits: tuple[UpstreamCredit, ...] = ()


@dataclass(frozen=True, slots=True)
class InputVCState:
    route: Port | None
    output_vc: int | None

    @property
    def active(self) -> bool:
        return self.route is not None


@dataclass(slots=True)
class _MutableInputVCState:
    route: Port | None = None
    output_vc: int | None = None


class BifrostRouter:
    """Integrate buffering, routing, allocation, switching, and credits by cycle."""

    def __init__(
        self,
        config: BifrostConfig,
        *,
        port_enable: Mapping[Port, bool] | None = None,
    ) -> None:
        if not isinstance(config, BifrostConfig):
            raise RouterProtocolError("config must be a BifrostConfig")
        if config.qos_enabled or config.qos_classes != 1:
            raise RouterProtocolError("the Core router model does not implement QoS")

        self._config = config
        self._ports = tuple(Port(name) for name in config.ports)
        self._port_index = {port: index for index, port in enumerate(self._ports)}
        self._port_enable = self._validate_port_enable(port_enable)
        self._requester_count = len(self._ports) * config.num_vcs

        self._fifos = {
            (port, vc): VirtualChannelFIFO(config.vc_depth)
            for port in self._ports
            for vc in range(config.num_vcs)
        }
        self._input_states = {
            (port, vc): _MutableInputVCState()
            for port in self._ports
            for vc in range(config.num_vcs)
        }
        self._allocators = {
            port: OutputVCAllocator(
                num_vcs=config.num_vcs,
                requester_count=self._requester_count,
            )
            for port in self._ports
        }
        self._switch_arbiters = {
            port: RoundRobinArbiter(self._requester_count) for port in self._ports
        }
        self._input_arbiters = {
            port: RoundRobinArbiter(len(self._ports)) for port in self._ports
        }
        self._credits = {
            (port, vc): CreditCounter(
                config.vc_depth,
                enabled=self._port_enable[port],
            )
            for port in self._ports
            for vc in range(config.num_vcs)
        }

    @property
    def ports(self) -> tuple[Port, ...]:
        return self._ports

    @property
    def is_idle(self) -> bool:
        return all(fifo.empty for fifo in self._fifos.values()) and all(
            state.route is None for state in self._input_states.values()
        )

    def fifo_occupancy(self, input_port: Port, input_vc: int) -> int:
        key = self._input_key(input_port, input_vc)
        return self._fifos[key].occupancy

    def input_state(self, input_port: Port, input_vc: int) -> InputVCState:
        state = self._input_states[self._input_key(input_port, input_vc)]
        return InputVCState(route=state.route, output_vc=state.output_vc)

    def credit_count(self, output_port: Port, output_vc: int) -> int:
        return self._credits[self._output_key(output_port, output_vc)].count

    def output_vc_owner(self, output_port: Port, output_vc: int) -> tuple[Port, int] | None:
        port, vc = self._output_key(output_port, output_vc)
        owner = self._allocators[port].owner_of(vc)
        return None if owner is None else self._decode_owner(owner)

    def switch_arbiter_pointer(self, output_port: Port) -> int:
        port, _ = self._output_key(output_port, 0)
        return self._switch_arbiters[port].pointer

    def input_arbiter_pointer(self, input_port: Port) -> int:
        port, _ = self._input_key(input_port, 0)
        return self._input_arbiters[port].pointer

    def allocator_pointers(self, output_port: Port) -> tuple[int, int]:
        port, _ = self._output_key(output_port, 0)
        allocator = self._allocators[port]
        return allocator.requester_pointer, allocator.vc_pointer

    def step(
        self,
        *,
        arrivals: Iterable[FlitArrival] = (),
        downstream_credits: Iterable[DownstreamCredit] = (),
        reset: bool = False,
    ) -> CycleResult:
        if type(reset) is not bool:
            raise RouterProtocolError("reset must be a boolean")
        selected_arrivals = tuple(arrivals)
        selected_credits = tuple(downstream_credits)
        if reset:
            if selected_arrivals or selected_credits:
                raise RouterProtocolError("flit and credit events are illegal during reset")
            self.reset()
            return CycleResult()

        arrivals_by_port = self._validate_arrivals(selected_arrivals)
        credits_by_port = self._validate_downstream_credits(selected_credits)
        transfers_by_output = self._select_transfers()
        allocations_by_output = self._allocation_eligibility()

        send_by_vc = {
            (transfer.output_port, transfer.output_vc): True
            for transfer in transfers_by_output.values()
        }
        return_by_vc = {
            (credit.output_port, credit.output_vc): True
            for credit in credits_by_port.values()
        }
        for key, counter in self._credits.items():
            counter.next_count(
                send=send_by_vc.get(key, False),
                credit_return=return_by_vc.get(key, False),
            )

        for output_port in self._ports:
            allocation = self._allocators[output_port].allocate(
                allocations_by_output[output_port]
            )
            if allocation is not None:
                input_key = self._decode_owner(allocation.owner)
                state = self._input_states[input_key]
                state.route = output_port
                state.output_vc = allocation.output_vc

        upstream_credits: list[UpstreamCredit] = []
        for output_port in self._ports:
            transfer = transfers_by_output.get(output_port)
            if transfer is None:
                continue
            input_key = (transfer.input_port, transfer.input_vc)
            owner = self._owner_id(*input_key)
            dequeued = self._fifos[input_key].dequeue()
            if dequeued is not transfer.flit:
                raise RouterProtocolError("selected flit changed before transfer")
            self._switch_arbiters[output_port].record_grant(owner)
            self._input_arbiters[transfer.input_port].record_grant(
                self._port_index[output_port]
            )
            upstream_credits.append(
                UpstreamCredit(
                    input_port=transfer.input_port,
                    input_vc=transfer.input_vc,
                )
            )
            if transfer.flit.tail:
                self._allocators[output_port].release(
                    output_vc=transfer.output_vc,
                    owner=owner,
                    tail_transmitted=True,
                )
                state = self._input_states[input_key]
                state.route = None
                state.output_vc = None

        for key, counter in self._credits.items():
            counter.apply(
                send=send_by_vc.get(key, False),
                credit_return=return_by_vc.get(key, False),
            )

        for arrival in arrivals_by_port.values():
            self._fifos[(arrival.input_port, arrival.input_vc)].enqueue(arrival.flit)

        transfers = tuple(
            transfers_by_output[port]
            for port in self._ports
            if port in transfers_by_output
        )
        credits = tuple(
            sorted(
                upstream_credits,
                key=lambda credit: (
                    self._port_index[credit.input_port],
                    credit.input_vc,
                ),
            )
        )
        return CycleResult(transfers=transfers, upstream_credits=credits)

    def reset(self) -> None:
        for fifo in self._fifos.values():
            fifo.reset()
        for state in self._input_states.values():
            state.route = None
            state.output_vc = None
        for allocator in self._allocators.values():
            allocator.reset()
        for arbiter in self._switch_arbiters.values():
            arbiter.reset()
        for arbiter in self._input_arbiters.values():
            arbiter.reset()
        for counter in self._credits.values():
            counter.reset()

    def _validate_port_enable(
        self,
        port_enable: Mapping[Port, bool] | None,
    ) -> dict[Port, bool]:
        if port_enable is None:
            return {port: True for port in self._ports}
        if set(port_enable) != set(self._ports):
            raise RouterProtocolError("port_enable must define every physical port")
        selected = dict(port_enable)
        if any(type(value) is not bool for value in selected.values()):
            raise RouterProtocolError("port enable values must be booleans")
        return selected

    def _validate_arrivals(
        self,
        arrivals: tuple[FlitArrival, ...],
    ) -> dict[Port, FlitArrival]:
        by_port: dict[Port, FlitArrival] = {}
        for arrival in arrivals:
            if not isinstance(arrival, FlitArrival):
                raise RouterProtocolError("arrivals must be FlitArrival instances")
            input_key = self._input_key(arrival.input_port, arrival.input_vc)
            if arrival.input_port in by_port:
                raise RouterProtocolError(
                    "at most one flit may arrive per physical input per cycle"
                )
            if not self._port_enable[arrival.input_port]:
                raise RouterProtocolError("arrival on a disabled input port")
            if not isinstance(arrival.flit, Flit):
                raise RouterProtocolError("arrival flit must be a Flit")
            self._validate_header(arrival.flit)
            self._fifos[input_key].validate_enqueue(arrival.flit)
            by_port[arrival.input_port] = arrival
        return by_port

    def _validate_downstream_credits(
        self,
        credits: tuple[DownstreamCredit, ...],
    ) -> dict[Port, DownstreamCredit]:
        by_port: dict[Port, DownstreamCredit] = {}
        for credit in credits:
            if not isinstance(credit, DownstreamCredit):
                raise RouterProtocolError(
                    "downstream credits must be DownstreamCredit instances"
                )
            self._output_key(credit.output_port, credit.output_vc)
            if credit.output_port in by_port:
                raise RouterProtocolError(
                    "at most one credit may return per physical output per cycle"
                )
            if not self._port_enable[credit.output_port]:
                raise RouterProtocolError("credit return on a disabled output port")
            by_port[credit.output_port] = credit
        return by_port

    def _validate_header(self, flit: Flit) -> None:
        if not flit.head:
            return
        if flit.header is None:
            raise RouterProtocolError("header metadata is missing")
        header = flit.header
        route_xy(
            current_x=self._config.router_x,
            current_y=self._config.router_y,
            destination_x=header.destination_x,
            destination_y=header.destination_y,
            mesh_x=self._config.mesh_x,
            mesh_y=self._config.mesh_y,
        )
        if not 0 <= header.source_x < self._config.mesh_x:
            raise RouterProtocolError("header source_x is outside the configured mesh")
        if not 0 <= header.source_y < self._config.mesh_y:
            raise RouterProtocolError("header source_y is outside the configured mesh")
        if header.packet_id >= 1 << self._config.packet_id_width:
            raise RouterProtocolError("packet_id exceeds the configured width")
        if header.qos_class != 0:
            raise RouterProtocolError("QoS classes are disabled in Core v0.2")

    def _allocation_eligibility(self) -> dict[Port, tuple[bool, ...]]:
        eligible = {
            output_port: [False] * self._requester_count
            for output_port in self._ports
        }
        for input_key, state in self._input_states.items():
            fifo = self._fifos[input_key]
            if state.route is not None or fifo.empty:
                continue
            flit = fifo.peek()
            if not flit.head or flit.header is None:
                raise RouterProtocolError("an idle input VC must expose a header")
            output_port = route_xy(
                current_x=self._config.router_x,
                current_y=self._config.router_y,
                destination_x=flit.header.destination_x,
                destination_y=flit.header.destination_y,
                mesh_x=self._config.mesh_x,
                mesh_y=self._config.mesh_y,
            )
            if self._port_enable[output_port]:
                eligible[output_port][self._owner_id(*input_key)] = True
        return {port: tuple(values) for port, values in eligible.items()}

    def _select_transfers(self) -> dict[Port, FlitTransfer]:
        proposals: dict[Port, int] = {}
        for output_port in self._ports:
            if not self._port_enable[output_port]:
                continue
            eligible = [False] * self._requester_count
            for input_key, state in self._input_states.items():
                if state.route is not output_port or state.output_vc is None:
                    continue
                fifo = self._fifos[input_key]
                if fifo.empty:
                    continue
                if self._credits[(output_port, state.output_vc)].can_send:
                    eligible[self._owner_id(*input_key)] = True
            winner = self._switch_arbiters[output_port].choose(eligible)
            if winner is not None:
                proposals[output_port] = winner

        # Losing outputs deliberately do not fall back: every successful output
        # transfer must honor its strict RR winner and bounded-service sequence.
        selected: dict[Port, FlitTransfer] = {}
        for input_port in self._ports:
            requested_outputs = [False] * len(self._ports)
            for output_port, owner in proposals.items():
                proposed_input, _ = self._decode_owner(owner)
                if proposed_input is input_port:
                    requested_outputs[self._port_index[output_port]] = True
            output_index = self._input_arbiters[input_port].choose(requested_outputs)
            if output_index is None:
                continue
            output_port = self._ports[output_index]
            winner = proposals[output_port]
            _, input_vc = self._decode_owner(winner)
            state = self._input_states[(input_port, input_vc)]
            if state.output_vc is None:
                raise RouterProtocolError("eligible requester lacks an output VC")
            selected[output_port] = FlitTransfer(
                output_port=output_port,
                output_vc=state.output_vc,
                input_port=input_port,
                input_vc=input_vc,
                flit=self._fifos[(input_port, input_vc)].peek(),
            )
        return selected

    def _input_key(self, port: Port, vc: int) -> tuple[Port, int]:
        if not isinstance(port, Port) or port not in self._port_index:
            raise RouterProtocolError("input port is not configured")
        self._validate_vc(vc)
        return port, vc

    def _output_key(self, port: Port, vc: int) -> tuple[Port, int]:
        if not isinstance(port, Port) or port not in self._port_index:
            raise RouterProtocolError("output port is not configured")
        self._validate_vc(vc)
        return port, vc

    def _validate_vc(self, vc: int) -> None:
        if (
            isinstance(vc, bool)
            or not isinstance(vc, int)
            or not 0 <= vc < self._config.num_vcs
        ):
            raise RouterProtocolError("VC identifier is outside the configured range")

    def _owner_id(self, port: Port, vc: int) -> int:
        return self._port_index[port] * self._config.num_vcs + vc

    def _decode_owner(self, owner: int) -> tuple[Port, int]:
        port_index, vc = divmod(owner, self._config.num_vcs)
        return self._ports[port_index], vc
