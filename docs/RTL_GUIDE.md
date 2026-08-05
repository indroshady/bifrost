# Core v0.2 RTL Architecture

## Scope and files

The hand-written baseline implements one five-port Core v0.2 router. It does not
implement QoS scheduling, adaptive routing, mesh integration, asynchronous link
initialization, formal proof, synthesis, or PPA claims.

| File | Responsibility |
|---|---|
| `rtl/bifrost_pkg.sv` | Frozen port IDs and packed-flit field positions |
| `rtl/bifrost_route_decode.sv` | Pure deterministic X-first route decode |
| `rtl/bifrost_input_vc.sv` | One bounded FIFO plus receive packet-boundary state |
| `rtl/bifrost_credit_counter.sv` | One registered downstream-VC credit truth table |
| `rtl/bifrost_crossbar.sv` | Explicit five-output complete-flit muxing |
| `rtl/bifrost_router.sv` | Output-VC ownership, matching, reset, protocol assertions, and block integration |
| `verification/rtl/tb_bifrost_router.sv` | Directed integrated Core transitions |
| `verification/rtl/tb_bifrost_routes.sv` | East/West/North/South/Local XY decode |
| `verification/rtl/tb_bifrost_random.sv` | Recorded-seed independent conservation/order scoreboard |
| `verification/rtl/tb_bifrost_protocol_error.sv` | Expected-failure malformed-stream assertion test |

The external arrays use the frozen unpacked order Local, North, South, East,
West. Each data entry is packed. There are no ready signals.

## State and cycle timing

There are ten independent input VCs: five physical inputs times two VCs. Each
has a four-entry FIFO and receive-side packet-boundary state. Packet route and
allocated output VC are cached separately so they survive an empty FIFO bubble.
Each physical output has two ownership entries, two downstream credit counters,
and independent allocation and switch round-robin histories.

One active cycle is evaluated in this order:

1. Current registered FIFO, route, ownership, arbitration, and credit state
   determine transfer proposals.
2. Each output proposes its strict round-robin winner.
3. Each physical input accepts at most one proposed output using a separate
   round-robin pointer. A losing output does not fall back in that cycle.
4. Independently, buffered unallocated headers request free output VCs.
5. The rising edge commits allocations, transfers, FIFO updates, credit updates,
   pointer updates, and exact tail release.

Consequently, a received header is buffered on its first edge, allocated on a
later edge, and can traverse only after that allocation is registered. A
downstream credit return is applied on the edge but is not visible to transfer
eligibility until the next cycle. The full flit and allocated VC sideband cross
the 5x5 datapath without modification. Every committed dequeue produces exactly
one upstream credit on its original input and VC.

`rst_n` is active-low and synchronous. Reset clears FIFO validity, packet state,
ownership, and all fairness pointers. Enabled output VCs initialize to
`VC_DEPTH` credits; disabled outputs initialize to zero. Transmit and upstream
credit valid outputs remain low while reset is asserted.

## Simulation checks

Immediate simulation assertions reject FIFO overflow/underflow, malformed
packet-marker sequences, nonzero body/tail header fields, nonzero Core QoS,
disabled-port traffic or credits, invalid ownership transitions, zero-credit
transmission, and credit overflow. These checks are verification aids, not a
formal-completeness claim.

The random test uses recorded seed `0x0B1F205E`, tracks every accepted flit in
an independent per-input-VC queue, derives XY output expectations directly from
the frozen header, and requires one matching dequeue credit for every transfer.

## Commands

CI uses Python 3.12 and the Ubuntu-packaged Verilator.

```text
make spec-check
make model-test
make rtl-lint
make rtl-test
make check
```

On Windows, install Verilator and run the equivalent lint command from
PowerShell:

```powershell
verilator --lint-only --timing --assert -Wall -Wno-fatal --top-module bifrost_router rtl\bifrost_pkg.sv rtl\bifrost_route_decode.sv rtl\bifrost_input_vc.sv rtl\bifrost_credit_counter.sv rtl\bifrost_crossbar.sv rtl\bifrost_router.sv
```
