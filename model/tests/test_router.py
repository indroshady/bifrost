from __future__ import annotations

import random
from collections import deque
from pathlib import Path

import pytest

from bifrost_model.config import load_config
from bifrost_model.flit import Flit, FlitValidationError, HeaderFields
from bifrost_model.router import (
    BifrostRouter,
    DownstreamCredit,
    FlitArrival,
    RouterProtocolError,
    UpstreamCredit,
)
from bifrost_model.routing import Port, route_xy


ROOT = Path(__file__).resolve().parents[2]
CONFIG = load_config(ROOT / "spec" / "bifrost.yaml")
RANDOM_SEED = 0xB1F205E


def _router(
    *,
    port_enable: dict[Port, bool] | None = None,
) -> BifrostRouter:
    return BifrostRouter(CONFIG, port_enable=port_enable)


def _header(
    packet_id: int,
    *,
    destination_x: int = 1,
    destination_y: int = 0,
    qos_class: int = 0,
) -> HeaderFields:
    return HeaderFields(
        destination_x=destination_x,
        destination_y=destination_y,
        source_x=0,
        source_y=0,
        packet_id=packet_id,
        qos_class=qos_class,
    )


def _single(
    packet_id: int,
    *,
    destination_x: int = 1,
    destination_y: int = 0,
) -> Flit:
    return Flit(
        head=True,
        tail=True,
        payload=("single", packet_id),
        header=_header(
            packet_id,
            destination_x=destination_x,
            destination_y=destination_y,
        ),
    )


def test_FUNC_001_forward_without_modification() -> None:
    router = _router()
    flit = _single(1)

    assert not router.step(
        arrivals=(FlitArrival(Port.LOCAL, 0, flit),)
    ).transfers
    assert not router.step().transfers
    result = router.step()

    assert len(result.transfers) == 1
    transfer = result.transfers[0]
    assert transfer.output_port is Port.EAST
    assert transfer.input_port is Port.LOCAL
    assert transfer.input_vc == 0
    assert transfer.flit is flit
    assert result.upstream_credits[0].input_port is Port.LOCAL
    assert result.upstream_credits[0].input_vc == 0


def test_FUNC_002_five_physical_ports_and_two_vcs() -> None:
    router = _router()

    assert router.ports == (
        Port.LOCAL,
        Port.NORTH,
        Port.SOUTH,
        Port.EAST,
        Port.WEST,
    )
    for port in router.ports:
        for vc in range(CONFIG.num_vcs):
            assert router.fifo_occupancy(port, vc) == 0
            assert router.input_state(port, vc).route is None


def test_FUNC_003_multiflit_packet_bubbles_retain_route_and_order() -> None:
    router = _router()
    head = Flit(head=True, tail=False, payload="head", header=_header(2))
    tail = Flit(head=False, tail=True, payload="tail")

    router.step(arrivals=(FlitArrival(Port.NORTH, 1, head),))
    router.step()
    head_result = router.step()
    head_transfer = head_result.transfers[0]
    state = router.input_state(Port.NORTH, 1)
    assert state.route is Port.EAST
    assert state.output_vc == head_transfer.output_vc

    assert not router.step().transfers
    assert not router.step().transfers
    assert router.output_vc_owner(Port.EAST, head_transfer.output_vc) == (
        Port.NORTH,
        1,
    )

    assert not router.step(
        arrivals=(FlitArrival(Port.NORTH, 1, tail),)
    ).transfers
    tail_result = router.step()
    assert [transfer.flit for transfer in (head_transfer, tail_result.transfers[0])] == [
        head,
        tail,
    ]
    assert tail_result.transfers[0].output_vc == head_transfer.output_vc
    assert not router.input_state(Port.NORTH, 1).active
    assert router.output_vc_owner(Port.EAST, head_transfer.output_vc) is None


def test_VC_004_head_tail_releases_reservation_once() -> None:
    router = _router()
    flit = _single(3)

    router.step(arrivals=(FlitArrival(Port.LOCAL, 0, flit),))
    router.step()
    state = router.input_state(Port.LOCAL, 0)
    assert state.output_vc is not None
    output_vc = state.output_vc
    assert router.output_vc_owner(Port.EAST, output_vc) == (Port.LOCAL, 0)

    result = router.step()
    assert result.transfers[0].flit is flit
    assert router.output_vc_owner(Port.EAST, output_vc) is None
    assert router.is_idle
    assert not router.step().transfers


def test_ARB_001_contention_has_one_winner_and_per_flit_rotation() -> None:
    router = _router()
    a_head = Flit(head=True, tail=False, payload="a-head", header=_header(10))
    b_head = Flit(head=True, tail=False, payload="b-head", header=_header(11))
    a_tail = Flit(head=False, tail=True, payload="a-tail")
    b_tail = Flit(head=False, tail=True, payload="b-tail")

    router.step(
        arrivals=(
            FlitArrival(Port.LOCAL, 0, a_head),
            FlitArrival(Port.NORTH, 0, b_head),
        )
    )
    router.step(
        arrivals=(
            FlitArrival(Port.LOCAL, 0, a_tail),
            FlitArrival(Port.NORTH, 0, b_tail),
        )
    )
    winners = []
    for _ in range(4):
        result = router.step()
        assert len(result.transfers) == 1
        winners.append(result.transfers[0].flit.payload)

    assert winners == ["a-head", "b-head", "a-tail", "b-tail"]


def test_FLOW_001_zero_credit_blocks_and_return_has_no_same_cycle_bypass() -> None:
    router = _router()
    flits = (
        Flit(head=True, tail=False, payload="head", header=_header(20)),
        Flit(head=False, tail=False, payload="body-1"),
        Flit(head=False, tail=False, payload="body-2"),
        Flit(head=False, tail=False, payload="body-3"),
        Flit(head=False, tail=True, payload="tail"),
    )

    router.step(arrivals=(FlitArrival(Port.LOCAL, 0, flits[0]),))
    router.step(arrivals=(FlitArrival(Port.LOCAL, 0, flits[1]),))
    sent = []
    for flit in flits[2:]:
        result = router.step(arrivals=(FlitArrival(Port.LOCAL, 0, flit),))
        sent.extend(transfer.flit for transfer in result.transfers)
    sent.extend(transfer.flit for transfer in router.step().transfers)
    assert sent == list(flits[:4])

    state = router.input_state(Port.LOCAL, 0)
    assert state.output_vc is not None
    output_vc = state.output_vc
    assert router.credit_count(Port.EAST, output_vc) == 0
    assert not router.step().transfers
    returned = router.step(
        downstream_credits=(DownstreamCredit(Port.EAST, output_vc),)
    )
    assert not returned.transfers
    assert router.credit_count(Port.EAST, output_vc) == 1
    assert router.step().transfers[0].flit is flits[-1]


def test_FLOW_003_one_upstream_credit_per_released_input_entry() -> None:
    router = _router()
    first = _single(30, destination_x=1, destination_y=0)
    second = _single(31, destination_x=0, destination_y=1)

    router.step(
        arrivals=(
            FlitArrival(Port.LOCAL, 1, first),
            FlitArrival(Port.NORTH, 0, second),
        )
    )
    router.step()
    result = router.step()

    assert len(result.transfers) == 2
    assert set(result.upstream_credits) == {
        UpstreamCredit(Port.LOCAL, 1),
        UpstreamCredit(Port.NORTH, 0),
    }


def test_PERF_002_nonconflicting_outputs_transfer_concurrently() -> None:
    router = _router()
    east = _single(40, destination_x=1, destination_y=0)
    north = _single(41, destination_x=0, destination_y=1)

    router.step(
        arrivals=(
            FlitArrival(Port.LOCAL, 0, east),
            FlitArrival(Port.NORTH, 1, north),
        )
    )
    router.step()
    result = router.step()

    assert {transfer.output_port for transfer in result.transfers} == {
        Port.EAST,
        Port.NORTH,
    }
    assert {transfer.flit for transfer in result.transfers} == {east, north}


def test_PERF_001_continuous_packet_transmits_one_flit_per_cycle() -> None:
    router = _router()
    packet = (
        Flit(head=True, tail=False, payload="head", header=_header(42)),
        Flit(head=False, tail=False, payload="body-1"),
        Flit(head=False, tail=False, payload="body-2"),
        Flit(head=False, tail=False, payload="body-3"),
        Flit(head=False, tail=True, payload="tail"),
    )
    results = [
        router.step(arrivals=(FlitArrival(Port.LOCAL, 0, packet[0]),)),
        router.step(arrivals=(FlitArrival(Port.LOCAL, 0, packet[1]),)),
    ]
    downstream_returns: tuple[DownstreamCredit, ...] = ()
    for flit in packet[2:]:
        result = router.step(
            arrivals=(FlitArrival(Port.LOCAL, 0, flit),),
            downstream_credits=downstream_returns,
        )
        results.append(result)
        downstream_returns = tuple(
            DownstreamCredit(transfer.output_port, transfer.output_vc)
            for transfer in result.transfers
        )
    while not router.is_idle:
        result = router.step(downstream_credits=downstream_returns)
        results.append(result)
        downstream_returns = tuple(
            DownstreamCredit(transfer.output_port, transfer.output_vc)
            for transfer in result.transfers
        )

    transfer_cycles = [
        cycle
        for cycle, result in enumerate(results)
        if result.transfers
    ]
    assert transfer_cycles == list(
        range(transfer_cycles[0], transfer_cycles[0] + len(packet))
    )
    assert [
        transfer.flit
        for result in results
        for transfer in result.transfers
    ] == list(packet)


def test_ARB_001_one_physical_input_cannot_drive_two_outputs() -> None:
    router = _router()
    east = _single(50, destination_x=1, destination_y=0)
    north = _single(51, destination_x=0, destination_y=1)

    router.step(arrivals=(FlitArrival(Port.LOCAL, 0, east),))
    router.step(arrivals=(FlitArrival(Port.LOCAL, 1, north),))
    first = router.step()
    second = router.step()

    assert len(first.transfers) == 1
    assert len(second.transfers) == 1
    assert {first.transfers[0].flit, second.transfers[0].flit} == {east, north}


def test_ARB_002_output_round_robin_bound_survives_input_conflicts() -> None:
    router = _router()
    def packet(
        prefix: str,
        packet_id: int,
        *,
        destination_x: int,
        destination_y: int,
        length: int = 20,
    ) -> deque[Flit]:
        return deque(
            [
                Flit(
                    head=True,
                    tail=False,
                    payload=f"{prefix}-head",
                    header=_header(
                        packet_id,
                        destination_x=destination_x,
                        destination_y=destination_y,
                    ),
                ),
                *[
                    Flit(
                        head=False,
                        tail=sequence == length - 1,
                        payload=f"{prefix}-{sequence}",
                    )
                    for sequence in range(1, length)
                ],
            ]
        )

    north_x = packet("x", 52, destination_x=0, destination_y=1)
    north_y = packet("y", 53, destination_x=0, destination_y=1)
    east = packet("e", 54, destination_x=1, destination_y=0)
    north_winners = []
    downstream_returns: tuple[DownstreamCredit, ...] = ()
    local_turn = 0
    for _ in range(200):
        arrivals = []
        local_streams = ((0, north_x), (1, east))
        for offset in range(2):
            vc, stream = local_streams[(local_turn + offset) % 2]
            if stream and router.fifo_occupancy(Port.LOCAL, vc) < CONFIG.vc_depth:
                arrivals.append(FlitArrival(Port.LOCAL, vc, stream.popleft()))
                local_turn = (vc + 1) % 2
                break
        if north_y and router.fifo_occupancy(Port.NORTH, 0) < CONFIG.vc_depth:
            arrivals.append(FlitArrival(Port.NORTH, 0, north_y.popleft()))

        all_contenders_ready = (
            all(
                router.input_state(port, vc).active
                and router.fifo_occupancy(port, vc) > 0
                for port, vc in (
                    (Port.LOCAL, 0),
                    (Port.LOCAL, 1),
                    (Port.NORTH, 0),
                )
            )
        )
        result = router.step(
            arrivals=arrivals,
            downstream_credits=downstream_returns,
        )
        downstream_returns = tuple(
            DownstreamCredit(transfer.output_port, transfer.output_vc)
            for transfer in result.transfers
        )
        if all_contenders_ready:
            north_winners.extend(
                transfer.input_port
                for transfer in result.transfers
                if transfer.output_port is Port.NORTH
            )
        if len(north_winners) >= 8:
            break

    assert len(north_winners) >= 8
    assert all(
        left is not right
        for left, right in zip(north_winners, north_winners[1:])
    )


def test_ARB_002_losing_output_does_not_skip_round_robin_winner() -> None:
    router = _router()
    x_head = Flit(
        head=True,
        tail=False,
        payload="x-head",
        header=_header(55, destination_x=0, destination_y=1),
    )
    x_body = Flit(head=False, tail=False, payload="x-body")
    fallback_head = Flit(
        head=True,
        tail=False,
        payload="fallback-head",
        header=_header(56, destination_x=0, destination_y=1),
    )
    fallback_body = Flit(head=False, tail=False, payload="fallback-body")
    east_head = Flit(head=True, tail=False, payload="east-head", header=_header(57))
    east_body = Flit(head=False, tail=False, payload="east-body")

    router.step(
        arrivals=(
            FlitArrival(Port.LOCAL, 0, x_head),
            FlitArrival(Port.NORTH, 0, fallback_head),
        )
    )
    router.step(
        arrivals=(
            FlitArrival(Port.LOCAL, 0, x_body),
            FlitArrival(Port.NORTH, 0, fallback_body),
        )
    )
    assert router.step(
        arrivals=(FlitArrival(Port.LOCAL, 1, east_head),)
    ).transfers[0].flit is x_head
    assert router.step().transfers[0].flit is fallback_head

    conflict = router.step(
        arrivals=(FlitArrival(Port.LOCAL, 1, east_body),)
    )
    assert [transfer.flit for transfer in conflict.transfers] == [east_head]
    following = router.step()
    assert [transfer.flit for transfer in following.transfers] == [x_body]


def test_RST_001_reset_flushes_traffic_reservations_history_and_credits() -> None:
    router = _router()
    head = Flit(head=True, tail=False, payload="discard", header=_header(60))

    router.step(arrivals=(FlitArrival(Port.LOCAL, 0, head),))
    router.step()
    assert router.input_state(Port.LOCAL, 0).active
    router.step()
    assert router.switch_arbiter_pointer(Port.EAST) != 0
    assert router.input_arbiter_pointer(Port.LOCAL) != 0
    assert router.allocator_pointers(Port.EAST) != (0, 0)
    reset_result = router.step(reset=True)

    assert not reset_result.transfers
    assert not reset_result.upstream_credits
    assert router.is_idle
    for port in router.ports:
        for vc in range(CONFIG.num_vcs):
            assert router.fifo_occupancy(port, vc) == 0
            assert router.input_state(port, vc).route is None
            assert router.output_vc_owner(port, vc) is None
            assert router.credit_count(port, vc) == CONFIG.vc_depth
        assert router.switch_arbiter_pointer(port) == 0
        assert router.input_arbiter_pointer(port) == 0
        assert router.allocator_pointers(port) == (0, 0)

    replacement = _single(61)
    router.step(arrivals=(FlitArrival(Port.LOCAL, 0, replacement),))
    router.step()
    state = router.input_state(Port.LOCAL, 0)
    assert state.output_vc == 0
    assert router.step().transfers[0].flit is replacement


def test_PERF_003_unloaded_latency_is_within_four_cycles() -> None:
    router = _router()
    flit = _single(70)

    observed = [
        router.step(arrivals=(FlitArrival(Port.LOCAL, 0, flit),)),
        router.step(),
        router.step(),
        router.step(),
    ]
    transfer_cycles = [
        cycle
        for cycle, result in enumerate(observed, start=1)
        if result.transfers
    ]
    assert transfer_cycles == [3]


def test_VER_001_packet_conservation_and_order_seed_B1F205E() -> None:
    rng = random.Random(RANDOM_SEED)
    router = _router()
    pending: dict[tuple[Port, int], deque[tuple[Flit, Port]]] = {
        (port, vc): deque()
        for port in router.ports
        for vc in range(CONFIG.num_vcs)
    }
    expected: dict[tuple[Port, int], deque[tuple[Flit, Port]]] = {
        key: deque() for key in pending
    }
    generated = 0
    for packet_id in range(60):
        key = rng.choice(tuple(pending))
        destination_x, destination_y = rng.choice(((0, 0), (1, 0), (0, 1), (1, 1)))
        length = rng.randint(1, 5)
        if length == 1:
            packet = [
                Flit(
                    head=True,
                    tail=True,
                    payload=(packet_id, 0),
                    header=_header(
                        packet_id,
                        destination_x=destination_x,
                        destination_y=destination_y,
                    ),
                )
            ]
        else:
            packet = [
                Flit(
                    head=True,
                    tail=False,
                    payload=(packet_id, 0),
                    header=_header(
                        packet_id,
                        destination_x=destination_x,
                        destination_y=destination_y,
                    ),
                ),
                *[
                    Flit(
                        head=False,
                        tail=sequence == length - 1,
                        payload=(packet_id, sequence),
                    )
                    for sequence in range(1, length)
                ],
            ]
        output = route_xy(
            current_x=CONFIG.router_x,
            current_y=CONFIG.router_y,
            destination_x=destination_x,
            destination_y=destination_y,
            mesh_x=CONFIG.mesh_x,
            mesh_y=CONFIG.mesh_y,
        )
        pending[key].extend((flit, output) for flit in packet)
        generated += len(packet)

    downstream_returns: tuple[DownstreamCredit, ...] = ()
    transmitted = 0
    for cycle in range(4000):
        arrivals = []
        for port in router.ports:
            candidates = [
                (port, vc)
                for vc in range(CONFIG.num_vcs)
                if pending[(port, vc)]
                and router.fifo_occupancy(port, vc) < CONFIG.vc_depth
            ]
            if candidates and rng.random() < 0.8:
                key = rng.choice(candidates)
                flit, output = pending[key].popleft()
                arrivals.append(FlitArrival(key[0], key[1], flit))
                expected[key].append((flit, output))

        result = router.step(
            arrivals=arrivals,
            downstream_credits=downstream_returns,
        )
        downstream_returns = tuple(
            DownstreamCredit(transfer.output_port, transfer.output_vc)
            for transfer in result.transfers
        )
        for transfer in result.transfers:
            key = (transfer.input_port, transfer.input_vc)
            assert expected[key], f"seed={RANDOM_SEED:#x}, cycle={cycle}"
            flit, output = expected[key].popleft()
            assert transfer.flit is flit, f"seed={RANDOM_SEED:#x}, cycle={cycle}"
            assert transfer.output_port is output, (
                f"seed={RANDOM_SEED:#x}, cycle={cycle}"
            )
            transmitted += 1

        if (
            all(not queue for queue in pending.values())
            and all(not queue for queue in expected.values())
            and router.is_idle
            and not downstream_returns
        ):
            break
    else:
        pytest.fail(f"random model run did not drain; seed={RANDOM_SEED:#x}")

    assert transmitted == generated


def test_router_rejects_invalid_cycle_and_packet_transitions_atomically() -> None:
    router = _router()
    body = Flit(head=False, tail=False, payload="body")
    with pytest.raises(FlitValidationError, match="must begin with a header"):
        router.step(arrivals=(FlitArrival(Port.LOCAL, 0, body),))
    assert router.fifo_occupancy(Port.LOCAL, 0) == 0

    with pytest.raises(RouterProtocolError, match="at most one flit"):
        router.step(
            arrivals=(
                FlitArrival(Port.LOCAL, 0, _single(80)),
                FlitArrival(Port.LOCAL, 1, _single(81)),
            )
        )
    assert router.fifo_occupancy(Port.LOCAL, 0) == 0
    assert router.fifo_occupancy(Port.LOCAL, 1) == 0

    with pytest.raises(RouterProtocolError, match="VC identifier"):
        router.step(arrivals=(FlitArrival(Port.LOCAL, 2, _single(82)),))
    with pytest.raises(RouterProtocolError, match="illegal during reset"):
        router.step(
            arrivals=(FlitArrival(Port.LOCAL, 0, _single(83)),),
            reset=True,
        )
    with pytest.raises(RouterProtocolError, match="QoS classes are disabled"):
        router.step(
            arrivals=(
                FlitArrival(
                    Port.LOCAL,
                    0,
                    Flit(
                        head=True,
                        tail=True,
                        payload="qos",
                        header=_header(84, qos_class=1),
                    ),
                ),
            )
        )


def test_router_rejects_disabled_port_and_fifo_overflow() -> None:
    enabled = {port: True for port in Port}
    enabled[Port.EAST] = False
    router = _router(port_enable=enabled)

    with pytest.raises(RouterProtocolError, match="disabled input"):
        router.step(arrivals=(FlitArrival(Port.EAST, 0, _single(90)),))
    flits = (
        Flit(head=True, tail=False, payload="head", header=_header(91)),
        Flit(head=False, tail=False, payload="body-1"),
        Flit(head=False, tail=False, payload="body-2"),
        Flit(head=False, tail=False, payload="body-3"),
    )
    for flit in flits:
        router.step(arrivals=(FlitArrival(Port.LOCAL, 0, flit),))
    assert router.fifo_occupancy(Port.LOCAL, 0) == CONFIG.vc_depth
    with pytest.raises(ValueError, match="overflow"):
        router.step(
            arrivals=(
                FlitArrival(
                    Port.LOCAL,
                    0,
                    Flit(head=False, tail=True, payload="tail"),
                ),
            )
        )
