# Bifröst NoC Router
## Architectural and Functional Requirements Specification v0.2

**Project:** Hephaestus Agentic RTL-to-PPA Forge  
**Design under test:** Bifröst NoC Router  
**Revision:** 0.2  
**Date:** August 03, 2026  
**Status:** Core v0.2 behavior and RTL interface/encoding contract frozen

---

# 1. Purpose

Bifröst is a parameterized, wormhole-switched Network-on-Chip router for a rectangular two-dimensional mesh connecting compute, memory, and I/O tiles in an AI accelerator. It receives packet flits from neighboring routers or a local network interface, determines their required direction, arbitrates for shared output resources, and forwards them without loss, duplication, corruption, or illegal reordering.

The block is deliberately control-heavy. It exposes architectural tradeoffs in routing, virtual channels, buffering, arbitration, flow control, pipeline placement, timing, area, and power. It is the hardware target for the Hephaestus agentic design flow.

This revision separates a trustworthy core from later exploration:

- **Core baseline:** deterministic XY routing, two virtual channels, credit flow control, round-robin arbitration, and one five-port router.
- **QoS extension:** weighted service and bounded aging, enabled only after the core baseline passes all correctness gates.
- **Agentic optimization:** enabled only after a frozen hand-written baseline and independent verification oracle exist.

The governing principle is: **the language model proposes; deterministic engineering tools judge.**

# 2. System Context

Each tile in the assumed accelerator contains a compute or memory subsystem, a network interface, and one Bifröst router. Routers are connected in a rectangular 2D mesh.

```text
+--------+     +--------+     +--------+
| Tile   |-----| Tile   |-----| Tile   |
| Router |     | Router |     | Router |
+---+----+     +---+----+     +---+----+
    |              |              |
+---+----+     +---+----+     +---+----+
| Tile   |-----| Tile   |-----| Tile   |
| Router |     | Router |     | Router |
+--------+     +--------+     +--------+
```

Bifröst provides five bidirectional logical ports in this fixed order and
numeric encoding:

| Array index / port ID | Port |
|---:|---|
| 0 | Local |
| 1 | North |
| 2 | South |
| 3 | East |
| 4 | West |

The Local port connects to the tile's network interface. The directional ports connect to adjacent routers.

Bifröst transports packets but does not interpret payload semantics. Coherency, memory ordering, request/response matching, address translation, retry, and end-to-end error recovery belong to higher protocol layers.

# 3. Architectural Terminology

| Term | Meaning |
|---|---|
| Packet | A complete message consisting of one or more flits |
| Flit | The atomic unit transferred across one NoC link in one cycle |
| Header flit | First flit of a packet; carries destination and QoS information |
| Body flit | Intermediate packet flit containing payload |
| Tail flit | Final flit; releases packet-level reservations |
| Virtual channel | Independent logical FIFO and packet state sharing a physical link |
| Input VC | Buffer and control state receiving one packet stream at an input port |
| Output VC | Downstream virtual channel reserved for a packet |
| Credit | Permission representing one free entry in a downstream input VC |
| Wormhole switching | Packet forwarding where flits may span multiple routers while resources remain reserved |
| Unloaded latency | Router latency when no contention or downstream blocking exists |

# 4. Normative Profiles and Baseline Configuration

Requirements labeled **Core** are mandatory for the first public release. Requirements labeled **QoS Extension** are staged and shall not block the core baseline.

| Parameter | Core baseline | Exploration after core freeze |
|---|---:|---|
| Physical ports | 5 | Fixed: Local, North, South, East, West |
| Flit width | 128 bits | 64, 128, 256 bits |
| Virtual channels per port | 2 | 1, 2, 4 |
| Buffer depth per VC | 4 flits | 2, 4, 8 flits |
| Traffic classes | 1 | 4 in QoS Extension |
| Routing algorithm | Deterministic XY | Fixed in Version 1 |
| Flow control | Credit-based | Fixed in Version 1 |
| Switching | Wormhole | Fixed in Version 1 |
| Physical-link arbitration | Per-flit round-robin | Weighted/aged in QoS Extension |
| Reference clock period | 2.0 ns | Fixed PPA comparison target |

The 128-bit, two-VC, four-entry configuration is the primary implementation and verification target. Parameter sweeps, QoS, mesh traffic studies, and agent-proposed changes begin only after this profile passes lint, simulation, formal safety checks, synthesis, and timing.

## 4.1 Staged Delivery

1. **Milestone 0 — Contract:** freeze this specification, machine-readable parameters, and requirement-to-test matrix.
2. **Milestone 1 — Core router:** implement and verify one hand-written five-port router.
3. **Milestone 2 — Mesh evidence:** integrate a 2x2 or 3x3 mesh and publish traffic/PPA sweeps.
4. **Milestone 3 — QoS:** add weighted service and bounded aging without weakening core guarantees.
5. **Milestone 4 — Agentic optimization:** permit one bounded, evidence-traceable change per iteration.

# 5. Functional Overview

For every incoming flit, the router performs the following logical work:

1. Identify the physical input port and input virtual channel.
2. Store the flit in the corresponding input FIFO.
3. For a header flit, decode destination coordinates and compute the required output port.
4. Allocate an available downstream output virtual channel.
5. Record the route and output-VC reservation for the packet.
6. Request access to the required physical output port.
7. Apply QoS-aware arbitration among eligible requesters.
8. Transfer the winning flit through the crossbar.
9. Consume one downstream credit for the selected output VC.
10. Return one credit upstream when the local input FIFO entry is released.
11. Release route and output-VC reservations after the tail flit is transmitted.

Multiple non-conflicting transfers shall occur concurrently. A flit moving from North to East shall not prevent an unrelated flit from moving from Local to West during the same cycle.

# 6. Packet and Flit Model

## 6.1 Packet Structure

A packet consists of one of these legal sequences:

```text
Single-flit packet:  HEAD+TAIL
Multi-flit packet:   HEAD, zero or more BODY flits, TAIL
```

Each packet shall remain associated with one input VC from its header through its tail. A source shall not interleave flits from different packets within the same VC.

The design permits bubbles between flits of a packet. A header, body, or tail may wait for later body/tail arrival, contention, or downstream credit without losing its cached route or output-VC ownership. Under continuous arrival, no contention, and available credits, the router shall not introduce avoidable bubbles.

## 6.2 Required Flit Information

The packed flit encoding is frozen from the most-significant bit downward. Bit
ranges are inclusive:

| Field | Range | Width | Meaning |
|---|---:|---:|---|
| `head` | `[127]` | 1 | Header marker on every flit |
| `tail` | `[126]` | 1 | Tail marker on every flit |
| `destination_x` | `[125]` | `X_W=1` | Header only |
| `destination_y` | `[124]` | `Y_W=1` | Header only |
| `source_x` | `[123]` | `X_W=1` | Header only |
| `source_y` | `[122]` | `Y_W=1` | Header only |
| `packet_id` | `[121:106]` | `PKT_ID_W=16` | Header only |
| `qos_class` | `[105:104]` | `QOS_W=2` | Header only; Core accepts only `2'b00` |
| `payload` | `[103:0]` | `PAYLOAD_W=104` | Uninterpreted payload bits on every flit |

The selected width arithmetic is:

```text
PAYLOAD_W = FLIT_W
          - (HEAD_W + TAIL_W
             + 2*X_W + 2*Y_W
             + PKT_ID_W + QOS_W)
          = 128 - (1 + 1 + 2 + 2 + 16 + 2)
          = 104
```

For every supported parameter combination, `PAYLOAD_W` shall be derived by this
formula and shall be positive. The fields shall cover exactly `[FLIT_W-1:0]`
without gaps or overlap.

The marker encodings are `2'b10` for a multi-flit header, `2'b00` for a body,
`2'b01` for a tail, and `2'b11` for a single-flit packet. On a header or
single-flit packet, all coordinate, packet-ID, and QoS fields are meaningful.
On body and tail flits those header-only ranges are reserved, shall be zero at
the source, and shall not be used by the router. Payload is meaningful and
forwarded unchanged for every flit.

The two QoS bits reserve representation for the staged four-class extension;
they do not enable QoS behavior. Core sources shall encode class 0, Core routers
shall reject header values 1 through 3 as protocol errors, and Core arbitration
remains ordinary per-flit round robin.

The semantic Python model deliberately continues to carry arbitrary Python
payload objects. Its objects are not reinterpreted as 104-bit values. The
independent integer pack/unpack helper is a representation contract for future
RTL and verification only.

The router shall store the selected route, QoS class, and output-VC assignment
as packet state so body and tail flits do not repeat routing information.

## 6.3 Packet Identifier

The packet identifier is opaque to the router. It is transported without modification and is intended for end-to-end correlation, debug, and verification.

The router shall not use the packet identifier to make routing or arbitration decisions.

## 6.4 Legal Packet Rules

A well-formed packet stream shall obey these rules:

- An idle input VC begins a packet only with a header.
- A second header shall not appear before the current packet's tail.
- A tail shall not appear without an active packet.
- A single-flit packet asserts both head and tail.
- All flits of a packet use the same input VC.
- Destination and traffic class are established by the header.
- Packet flits may be separated by idle cycles but may not be interleaved with another packet in the same VC.

Malformed-packet recovery is outside Version 1. Such traffic is a protocol violation. Simulation and formal environments shall detect it and fail the run; production recovery behavior is not claimed.

# 7. Routing Requirements

## 7.1 Deterministic XY Routing

Version 1 shall use dimension-ordered XY routing.

The route decision is:

1. If the destination X coordinate is greater than the current router X coordinate, select East.
2. If the destination X coordinate is less than the current router X coordinate, select West.
3. Otherwise, if the destination Y coordinate is greater than the current router Y coordinate, select North.
4. Otherwise, if the destination Y coordinate is less than the current router Y coordinate, select South.
5. Otherwise, select Local.

The design shall use one documented coordinate convention for North/South direction and apply it consistently across RTL, reference models, diagrams, and tests.

## 7.2 Routing Properties

The routing function shall:

- Produce exactly one legal output direction for every legal destination.
- Never route a packet back to the input direction as an adaptive detour.
- Deliver a packet to Local only when destination coordinates equal the router coordinates.
- Never modify destination fields.
- Cache the selected route until the packet tail departs.
- Reject unsupported adaptive or nonminimal paths in Version 1.

## 7.3 Mesh Boundary Assumptions

Routers at mesh boundaries shall not receive legal routes toward nonexistent neighbors. System integration may tie off unused physical ports or configure them as disabled.

Packets with coordinates outside the configured mesh are protocol errors. Error recovery for invalid destinations is outside Version 1.

# 8. Input Buffering

Each physical input port contains one FIFO per virtual channel.

The input-buffer architecture shall maintain, for each VC:

- Flit storage
- Read and write position
- Occupancy
- Packet-active state
- Cached output route
- Assigned output VC
- QoS state

An incoming flit shall be accepted whenever its upstream sender has a valid credit for the selected input VC. Because the link is credit-controlled, the receive interface has no ready signal. A valid presented flit must be stored.

The router shall guarantee:

- No FIFO write when the selected VC is full.
- No FIFO read when the selected VC is empty.
- Occupancy remains between zero and configured depth.
- Flit order within each VC is preserved.
- State for one VC cannot corrupt another VC.
- An input FIFO entry is released only when its flit successfully traverses the crossbar.

# 9. Virtual-Channel Lifecycle

An input VC moves through these conceptual states:

```text
IDLE -> ROUTE/ALLOCATE -> ACTIVE -> IDLE
```

## 9.1 IDLE

The VC has no active packet-level reservation. Its head flit, if present, must be a header.

## 9.2 ROUTE/ALLOCATE

The header is buffered. The router computes its output direction and requests a free output VC tracked by the corresponding output port.

The header shall not transmit until:

- Its route is known.
- An output VC has been assigned.
- The assigned downstream VC has at least one credit.
- The packet wins physical-output arbitration.

The first implementation shall use a two-step allocate-then-traverse sequence. Speculative same-cycle allocation and traversal is an optional optimization and must preserve identical externally visible behavior.

## 9.3 ACTIVE

The route and output VC remain associated with the packet. Body and tail flits use the cached assignment. Output-VC ownership is packet-level, while access to the physical output link is arbitrated per flit.

A packet may therefore retain its downstream VC while another packet uses the physical link during cycles in which the owner is empty, blocked, or loses arbitration.

## 9.4 Release

When the tail flit successfully transmits from this router:

- The input VC packet state returns to IDLE.
- The output-VC reservation is released exactly once.
- A following header may begin allocation.

For a single-flit packet, allocation, transmission, and release apply to the same flit. Sequential next-state logic shall ensure the resource is never observed as simultaneously owned by two packets.

# 10. Output-VC Allocation

For each physical output port, the router shall maintain a local allocation table containing one free/owned bit and one owner identifier per downstream VC. Because one physical link has exactly one upstream sender, this table is authoritative for allocations made across that link. Credit counters independently represent free storage entries.

A downstream VC may contain serialized flits from consecutive packets; it shall never contain interleaved flits from different packets. Releasing the local reservation after a tail transmission permits a later packet to follow that tail, subject to available credits.

The allocator shall:

- Assign no output VC to more than one local packet at a time.
- Allocate only VCs belonging to the selected physical output port.
- Allocate only a currently free output VC.
- Preserve allocation until the owning tail flit transmits.
- Release the VC exactly once.
- Keep allocation state independent from credit count.
- Avoid permanent starvation among continuously eligible allocation requests.

The core allocation policy shall be round-robin among eligible header requests, with the pointer advancing only on a successful allocation. With `R` continuously eligible requests and a free compatible output VC becoming available, each request shall be selected within at most `R` successful allocation decisions, assuming the eligible set does not grow without bound.

# 11. Switch Arbitration and QoS

## 11.1 Request Eligibility

An input VC may request a physical output only when:

- Its FIFO is nonempty.
- Its route has been determined.
- It owns an output VC.
- The selected downstream output VC has a positive credit count.
- The physical output port is enabled.

If speculative allocation and traversal is later enabled, a header may also request when it can be proven to receive a unique output VC in the same cycle.

## 11.2 One Winner per Output and Input

Each physical output port may transmit at most one flit per cycle. Arbitration shall produce a one-hot-or-zero grant for every output.

One input VC shall not transmit to multiple outputs in the same cycle. Because every input VC has one cached deterministic route, independent per-output arbiters cannot legally select the same VC for different outputs.

The selected flit is dequeued, consumes credit, and generates an upstream credit return only when the final grant is valid and transmission occurs.

## 11.3 Core Round-Robin Policy

The core router shall use per-output, per-flit round-robin arbitration. Its pointer advances only after a successful transmission.

Under the assumptions that an output remains enabled, a downstream credit is available whenever the requester is considered, and the set contains at most `R` continuously eligible requesters, each requester shall be granted within at most `R` successful transmissions on that output.

This is the normative bounded-service guarantee for the core. Time spent with no downstream credit is excluded because no requester can make progress.

## 11.4 QoS Extension

The QoS extension supports four traffic classes encoded in the header and cached as packet state. It shall use weighted round-robin plus a bounded aging override rather than strict priority.

The policy shall provide:

- Higher long-term service share for classes with larger nonzero weights.
- Round-robin fairness among requesters within the same class.
- A configurable maximum wait measured in eligible output-service opportunities.
- Promotion of a requester when its age reaches the configured threshold.
- Deterministic behavior for identical request histories.

Weights, the accounting window, and the aging threshold shall be frozen in the build manifest. A QoS claim is valid only when measured service ratios and maximum waits are checked under documented traffic and credit assumptions.

# 12. Crossbar Requirements

The crossbar connects five physical input ports to five physical output ports.

It shall support simultaneous non-conflicting transfers. Every output selects at most one input, while different outputs may select different inputs during the same cycle.

The crossbar shall:

- Forward the complete flit without modification.
- Forward the allocated output-VC identifier as sideband metadata.
- Use only valid arbitration grants.
- Never duplicate one flit onto multiple outputs.
- Never combine fields from different input flits.
- Prevent ungranted inputs from being dequeued.
- Meet the same clock target as routing and arbitration logic.

Crossbar mux depth and grant fanout are expected timing targets for agentic optimization.

# 13. Credit-Based Flow Control

## 13.1 Credit Meaning

One credit represents one free flit entry in a specific downstream input VC.

The sender maintains a credit counter for every output port and output VC. A flit may transmit only when the corresponding counter is greater than zero.

## 13.2 Credit Consumption

A successful transmitted flit consumes exactly one downstream credit.

Credit consumption occurs only when the flit is actually sent. Arbitration without transmission shall not consume credit.

## 13.3 Credit Return

When a flit leaves an input FIFO and releases its entry, the router returns one credit to the upstream neighbor for that physical port and VC.

The credit-return channel may return at most one credit per physical input port per cycle because each input port can dequeue at most one flit per cycle.

## 13.4 Credit Invariants and Simultaneous Events

For each output VC:

```text
0 <= available_credits <= downstream_buffer_depth
```

Let `send` mean that one flit transmits on an output VC, and `return` mean that one downstream credit arrives for that same VC. The next count is normative:

```text
00: credit_next = credit
01: credit_next = credit + 1
10: credit_next = credit - 1
11: credit_next = credit
```

A same-cycle return may offset a transmission only when the current count is already positive. The core interface shall not use a credit that arrives in the current cycle to authorize a transmission from a current count of zero; this avoids a combinational path through the neighboring router. A registered-credit optimization may be evaluated later without changing safety.

The design shall guarantee:

- No transmission with zero registered credit.
- No credit underflow or overflow.
- No double or lost credit return.
- Credit accounting remains independent across ports and VCs.
- Credit returns on disabled links are protocol errors.

## 13.5 Reset Assumption

All routers and attached network interfaces in the mesh participate in a coordinated reset held for the documented minimum number of cycles. No flit or credit event is legal while reset is asserted.

At reset, each enabled output-VC credit counter is initialized to the configured downstream buffer depth because every downstream input FIFO is reset empty. A disabled output port initializes its credits to zero and may not transmit.

After reset deassertion, both endpoints use the same `VC_DEPTH` and VC numbering. Asynchronous link initialization, independent endpoint reset, and credit resynchronization are outside Version 1.

# 14. External Interfaces

The router uses one clock domain. Every port array uses the fixed outer unpacked
dimension order Local, North, South, East, West. `PORT_ID_W` is the minimum
positive width `ceil(log2(PORTS))=3`: Local=`3'd0`, North=`3'd1`,
South=`3'd2`, East=`3'd3`, and West=`3'd4`. Codes 5 through 7 are reserved and
invalid.

`VC_ID_W` is the minimum positive width `ceil(log2(NUM_VCS))=1`. VC0 is
`1'b0` and VC1 is `1'b1`; both one-bit patterns are valid. Any integer VC value
outside 0 through 1 is invalid before truncation to the sideband.

Logical shapes below list the unpacked port dimension first and any packed data
width second. Thus `[PORTS][FLIT_W]` means one unpacked array entry per port,
each containing a packed `FLIT_W` vector. This convention, the directions, and
the absence of ready signals are part of the frozen contract.

## 14.1 Global Inputs

| Signal | Direction | Description |
|---|---|---|
| `clk` | Input `[1]` | Rising-edge router clock |
| `rst_n` | Input `[1]` | Active-low synchronous reset |
| `port_enable` | Input `[PORTS]` | Enables each physical port; boundary ports may be disabled |

Router X/Y coordinates and mesh dimensions are compile-time parameters in Version 1 rather than runtime inputs.

## 14.2 Incoming Flit Interface

For each physical input port:

| Signal | Direction | Description |
|---|---|---|
| `rx_valid` | Input `[PORTS]` | Indicates one incoming flit during this cycle |
| `rx_flit` | Input `[PORTS][FLIT_W]` | Complete frozen packed flit |
| `rx_vc` | Input `[PORTS][VC_ID_W]` | Destination input-VC identifier |

There is no `rx_ready`. The upstream router may assert `rx_valid` only when it owns a registered credit for the selected VC. Signals are sampled on the rising clock edge. When `rx_valid` is asserted on an enabled port, Bifröst shall accept the flit on that edge.

At most one flit may arrive per physical input port per cycle. The source shall hold `rx_flit` and `rx_vc` stable for the full setup/hold interval around the accepting edge. An arrival to a disabled port, an out-of-range VC, or a full VC is a protocol violation.

## 14.3 Outgoing Flit Interface

For each physical output port:

| Signal | Direction | Description |
|---|---|---|
| `tx_valid` | Output `[PORTS]` | Indicates one outgoing flit during this cycle |
| `tx_flit` | Output `[PORTS][FLIT_W]` | Complete frozen packed flit |
| `tx_vc` | Output `[PORTS][VC_ID_W]` | Allocated downstream input-VC identifier |

`tx_valid` shall assert only when the router has a positive registered credit for `tx_vc` on that output port. A transfer occurs on the rising edge when `tx_valid` is asserted; there is no downstream ready signal. The downstream router is required to accept every legal valid transfer.

At most one flit may transmit per physical output port per cycle. Outputs are not required to remain valid while locally blocked because `tx_valid` itself denotes an unconditional transfer. A flit waiting inside the router must, however, remain unchanged until it is selected.

## 14.4 Credit Return to Upstream

For each physical input port:

| Signal | Direction | Description |
|---|---|---|
| `credit_out_valid` | Output `[PORTS]` | Returns one credit to the upstream sender |
| `credit_out_vc` | Output `[PORTS][VC_ID_W]` | Identifies the upstream VC receiving the credit |

A valid credit-return event corresponds to one local input FIFO entry released on that cycle.

## 14.5 Credits Received from Downstream

For each physical output port:

| Signal | Direction | Description |
|---|---|---|
| `credit_in_valid` | Input `[PORTS]` | Indicates one returned downstream credit |
| `credit_in_vc` | Input `[PORTS][VC_ID_W]` | Identifies which output VC receives the credit |

A valid credit input increments exactly one output-VC credit counter unless the same cycle also transmits on that VC, in which case the implementation shall apply the net update correctly.

## 14.6 Deferred Observability Outputs

The required Core v0.2 external interface ends with the credit sidebands above.
The following nonfunctional outputs are deferred and are not part of this
frozen RTL interface:

- Router idle indication
- Per-port activity indication
- Sticky protocol-error indication
- Sticky credit-error indication

If added by a later independent contract revision, these outputs shall not
participate in routing or flow-control decisions. Performance counters and a
CSR interface are deferred.

# 15. Reset and Initialization

`rst_n` is active-low and synchronous.

While reset is asserted, the router shall:

- Clear all input FIFO occupancy.
- Clear packet-active state.
- Clear route and output-VC reservations.
- Clear arbiter history to a documented initial state.
- Deassert all transmit-valid signals.
- Deassert all credit-return-valid signals.
- Initialize output credit counters to downstream buffer depth.

After reset deassertion:

- No packet accepted before reset may emerge.
- The router may accept legal incoming flits immediately.
- All output VCs begin unallocated.
- Empty buffer storage bits need not be reset because their contents are invalid.

Reset behavior shall not depend on uninitialized flit memory contents.

# 16. Performance Requirements

## 16.1 Throughput

The router shall support:

- One arriving flit per physical input port per cycle.
- One departing flit per physical output port per cycle.
- Concurrent transfers on different outputs.
- One flit per cycle for a continuous packet when there is no contention and downstream credits remain available.
- No bubbles caused solely by avoidable local control behavior.

## 16.2 Latency

For an uncontended header with an available output VC and positive downstream credit, preferred input-to-output router latency is three cycles or less.

The hard maximum unloaded latency is four cycles for the baseline configuration.

Latency may increase because of:

- Output contention
- Output-VC unavailability
- Downstream credit exhaustion
- QoS arbitration

The implementation shall distinguish structural pipeline latency from queueing latency in reports.

## 16.3 Fairness and Service

For the core round-robin arbiter, if an output has at most `R` continuously eligible requesters and remains able to transmit, each requester shall be granted within `R` successful output transmissions. Newly arriving traffic shall enter behind the current round-robin position rather than resetting it.

For the QoS extension:

- Every class with a nonzero weight shall receive service under continuous eligibility.
- Measured service ratios should converge toward configured weights over the declared accounting window.
- The aging threshold shall bound wait in eligible output-service opportunities.
- Any reported bound shall state traffic, credit, packet-length, and arbitration assumptions.

Wall-clock delay cannot be bounded while downstream credits are withheld indefinitely.

## 16.4 Network-Level Evaluation

A multi-router mesh shall be evaluated using:

- Uniform random traffic
- Nearest-neighbor traffic
- Transpose traffic
- Hotspot traffic
- Bursty injection
- Mixed QoS traffic

Required measurements include average packet latency, tail latency, delivered throughput, offered load, per-port utilization, per-class service, and saturation behavior.

# 17. Correctness Requirements

The router shall satisfy these fundamental invariants:

- Every transmitted flit corresponds to one previously accepted flit.
- No accepted flit is transmitted more than once.
- Flit payload is not modified.
- Packet flit order is preserved.
- Routing follows deterministic XY rules.
- Local delivery occurs only at the destination router.
- Input buffers never overflow or underflow.
- Credit counters never overflow or underflow.
- No output receives more than one flit per cycle.
- No input sends more than one flit per cycle.
- No output VC has more than one owning packet.
- An output-VC reservation remains until the owning tail departs.
- Reset removes all pre-reset traffic.
- Disabled physical ports neither transmit nor accept legal traffic.

# 18. Deadlock and Livelock Requirements

Deterministic XY routing provides the deadlock argument for the core network; the mere presence of multiple virtual channels does not. Every legal route consumes X-dimension channels before Y-dimension channels and never returns from Y to X. Within each dimension, the fixed direction of a minimal route does not reverse. The resulting channel-dependency graph shall be documented and shown acyclic for the supported rectangular mesh.

The two baseline VCs reduce head-of-line blocking and provide independent buffering. They are not claimed as the reason routing deadlock is absent.

The router shall not create local protocol deadlock through incorrect reservation or credit handling. In particular:

- A packet shall not wait for a resource it already owns to be released by itself.
- A tail shall release its output-VC reservation exactly once after successful transmission.
- Credits shall return when buffered flits advance.
- Arbitration state shall not permanently exclude an eligible requester under its stated assumptions.
- No control path shall require a same-cycle response from a neighboring router to make progress.

End-to-end protocol deadlocks involving request/response dependencies above the router layer are outside Version 1. If separate protocol traffic classes are later required for protocol-level deadlock avoidance, their mapping to virtual channels shall be specified and verified as a new architectural contract.

# 19. Timing Requirements

The reference implementation shall target:

```text
Technology library: Nangate45
Implementation flow: OpenROAD
Reference clock period: 2.0 ns
Reference condition: documented typical corner
```

The final baseline configuration shall have:

- Nonnegative post-route setup slack.
- Zero total negative setup slack.
- No unconstrained sequential paths.
- No combinational loops.
- No output-arbitration or crossbar path exempted merely because it is control logic.
- No full-router combinational credit or grant loop between neighboring routers.

Expected critical structures include route decode, VC eligibility generation, arbitration, crossbar selection, wide-flit muxing, and high-fanout grant or enable signals.

# 20. Area Requirements

Area shall be evaluated using the same library, constraints, synthesis options, and physical-flow settings for every candidate.

Primary area contributors are expected to be:

- Input VC buffers
- Crossbar datapath
- Output-VC and packet-state storage
- Arbitration logic
- Credit counters
- Pipeline registers

The design shall demonstrate:

- Approximately linear buffer-area growth with flit width, VC count, and depth.
- No unintended replication of the entire crossbar per VC.
- No disproportionate control growth when increasing VC count.
- Explicit reporting of storage area versus logic area.
- Comparison of area, timing, and network performance rather than area alone.

The frozen hand-designed baseline becomes the normalization reference. Agent-generated candidates should remain within 1.25 times baseline area unless they provide a documented performance benefit that justifies the increase.

# 21. Power Requirements

The router architecture shall reduce unnecessary switching by:

- Writing a FIFO only when a flit arrives.
- Reading a FIFO only when a flit wins and transmits.
- Avoiding arbitration activity for empty VCs.
- Holding stalled flits and state stable.
- Preventing unused crossbar paths from toggling unnecessarily.
- Updating credit counters only on credit or transmit events.
- Using synthesis-recognizable clock enables rather than manually gated clocks.
- Allowing inactive physical ports to remain quiescent.

Power evaluation shall use identical activity traces across candidates and report energy per delivered flit in addition to estimated dynamic power.

Required activity profiles include idle, low-load bursty, sustained noncontending, hotspot-congested, and mixed-QoS traffic.

# 22. Verification Requirements

## 22.1 Block-Level Simulation

Simulation shall cover:

- Every legal input-to-output route.
- Single-flit and multi-flit packets, including bubbles between flits.
- All supported input and output VCs.
- Simultaneous nonconflicting transfers.
- Maximum contention for one output.
- Downstream credit exhaustion and recovery.
- All four same-VC send/credit-return combinations.
- Credit return when the registered count is zero.
- Packet tails, single-flit release, and immediate following allocation.
- Reset with empty and nonempty buffers.
- Core bounded round-robin service.
- QoS ratios and aging bounds when the extension is enabled.
- Disabled boundary ports and injected protocol violations.

An independent reference model and scoreboard shall track each accepted flit by packet identifier, source port, VC, and sequence position. Random tests shall use recorded seeds and produce a minimal replay artifact on failure.

## 22.2 Formal Safety and Liveness Properties

Formal checking shall target:

- FIFO occupancy bounds.
- Credit bounds and the simultaneous-event truth table.
- One-hot-or-zero output grants.
- No dequeue without a valid flit.
- No transmit without positive registered credit.
- No duplicate output-VC ownership.
- Stable route and reservation before tail.
- Exactly-once release for tail and head+tail packets.
- Correct route selection.
- No Local delivery at the wrong coordinate.
- Reset clearing all valid state.
- Bounded round-robin service under explicit assumptions.

Formal environments shall distinguish assumptions on legal sources/downstream progress from assertions on router behavior. An assertion may not be converted into an assumption merely to obtain a proof.

## 22.3 Network-Level Verification

At least a 2x2 mesh and preferably a 3x3 mesh shall be simulated with randomized packet injection, packet lengths, destinations, traffic classes, and bounded endpoint backpressure. Larger meshes are optional performance studies rather than a correctness prerequisite.

The network scoreboard shall prove end-to-end packet conservation, payload integrity, legal path progression, and per-packet ordering.

## 22.4 Verification-Oracle Independence

The approved specification, machine-readable contract, reference model, assertions, test seeds, and acceptance thresholds form the verification oracle. The RTL/optimization agent shall have read-only access to these artifacts during a candidate run.

A candidate may modify only explicitly granted RTL or implementation files. Any proposed oracle change shall be a separate revision with human approval and independent review; it shall never be bundled with the RTL patch it would cause to pass.

Each candidate run shall preserve:

- Parent revision and candidate diff.
- Tool versions and commands.
- Retrieved sources and requirement IDs.
- Test, proof, synthesis, timing, and PPA results.
- Accept/reject decision and reason.

# 23. Required Parameters

| Parameter | Meaning |
|---|---|
| `FLIT_W` | Width of one transferred flit |
| `NUM_VCS` | Virtual channels per physical port |
| `VC_DEPTH` | Flit entries per input VC |
| `X_W` | X-coordinate width |
| `Y_W` | Y-coordinate width |
| `ROUTER_X` | Current router X coordinate |
| `ROUTER_Y` | Current router Y coordinate |
| `MESH_X` | Number of mesh columns |
| `MESH_Y` | Number of mesh rows |
| `PKT_ID_W` | Packet identifier width |
| `PORT_ID_W` | Minimum physical-port ID width; frozen to 3 |
| `VC_ID_W` | Minimum virtual-channel ID width; frozen to 1 |
| `QOS_W` | Header representation width; frozen to 2 while Core accepts class 0 only |
| `QOS_CLASSES` | Number of supported QoS classes |
| `QOS_WEIGHTS` | Weighted-round-robin service configuration |

All legal parameter combinations shall be statically checked. Unsupported combinations shall fail elaboration rather than produce silently incorrect hardware.

# 24. Scope Exclusions

Version 1 intentionally excludes:

- Adaptive routing
- Multicast or broadcast replication
- Cache-coherency semantics
- AXI, CHI, PCIe, or CXL protocol handling
- Address translation
- DMA descriptor processing
- Clock-domain crossing
- SerDes and physical-link training
- ECC and parity correction
- Packet retransmission
- Dynamic topology changes
- Runtime-programmable routing tables
- Performance-counter CSRs
- Asynchronous reset and independent link reset

These may become later extensions only after the baseline router is verified and timing clean.

# 25. Requirements Traceability

| ID | Profile | Requirement |
|---|---|---|
| `FUNC-001` | Core | Forward legal packet flits without modification. |
| `FUNC-002` | Core | Implement five physical ports in a 2D mesh router. |
| `FUNC-003` | Core | Support wormhole packet switching and bubbles without packet interleaving in one VC. |
| `ENC-001` | Core | Encode every Core flit with the frozen gap-free 128-bit field layout. |
| `IFACE-001` | Core | Use the frozen physical-port and virtual-channel numeric encodings. |
| `IFACE-002` | Core | Expose the frozen credit-controlled cycle interface shapes and sidebands. |
| `ROUTE-001` | Core | Route all legal destinations using deterministic XY routing. |
| `ROUTE-002` | Core | Deliver packets locally only at matching coordinates. |
| `VC-001` | Core | Maintain independent FIFO and packet state per input VC. |
| `VC-002` | Core | Allocate each output VC to at most one local packet. |
| `VC-003` | Core | Hold output-VC ownership until the packet tail transmits. |
| `VC-004` | Core | Release head+tail and multi-flit packet reservations exactly once. |
| `FLOW-001` | Core | Transmit only with positive registered downstream credit. |
| `FLOW-002` | Core | Maintain credit counts within legal bounds. |
| `FLOW-003` | Core | Return exactly one credit for each released input entry. |
| `FLOW-004` | Core | Implement the specified simultaneous send/credit-return truth table. |
| `ARB-001` | Core | Grant at most one input to each physical output per cycle. |
| `ARB-002` | Core | Serve each continuously eligible requester within the stated round-robin bound. |
| `QOS-001` | QoS | Support weighted service among four traffic classes. |
| `QOS-002` | QoS | Enforce the configured bounded-aging threshold under stated assumptions. |
| `PERF-001` | Core | Sustain one flit per physical output per cycle. |
| `PERF-002` | Core | Support concurrent transfers on nonconflicting outputs. |
| `PERF-003` | Core | Meet four-cycle maximum unloaded router latency. |
| `DEAD-001` | Core | Preserve an acyclic XY channel-dependency order. |
| `TIM-001` | Core | Meet the 2.0 ns reference clock after implementation. |
| `PWR-001` | Core | Keep idle and disabled structures quiescent. |
| `RST-001` | Core | Flush all buffered and reserved traffic state on coordinated reset. |
| `VER-001` | Core | Demonstrate no loss, duplication, corruption, or illegal reordering. |
| `VER-002` | Core | Keep the verification oracle independent from candidate RTL changes. |

# 26. Agentic and RAG Integration Requirements

The approved specification remains the contractual source of truth. Agents may optimize architecture and RTL but shall not alter functional requirements, verification artifacts, or thresholds to make a candidate pass.

## 26.1 Candidate Loop

One candidate iteration shall:

1. Select one bounded objective and affected requirement IDs.
2. Record a hypothesis and expected functional/PPA effect.
3. Retrieve approved, source-cited engineering evidence.
4. Produce a scoped diff in an isolated revision.
5. Run formatting, lint, compile, directed and random tests, formal properties, synthesis, timing, and required PPA comparisons.
6. Accept or reject the candidate from parsed tool evidence.
7. Distill a reusable lesson only after the result is reproduced.

## 26.2 Storage Responsibilities

- **Approved specification:** contractual behavior and constraints.
- **Structured state store:** run state, revisions, metrics, tool versions, and pass/fail results.
- **Artifact store:** RTL, diffs, logs, waves, counterexamples, reports, and manifests.
- **Vector/keyword index:** source-citable guidelines, prior verified failures, and distilled engineering lessons.

The vector database shall not store authoritative workflow state or determine whether a run passes.

## 26.3 Retrieval

The engineering knowledge base should index routing rules, packet contracts, credit invariants, VC transitions, arbitration requirements, formal counterexamples, failure root causes, tool documentation, and accepted/rejected PPA transformations.

Retrieval shall combine metadata filters, keyword search, embeddings, and reranking. Metadata shall include requirement ID, module, stage, tool, profile, source revision, and approval status.

For example, an agent modifying the credit path shall retrieve `FLOW-001` through `FLOW-004`, associated assertions, previous credit failures, relevant tool documentation, and current timing evidence. Every used source shall be cited in the decision record.

# 27. Completion Criteria

## 27.1 Core Baseline Complete

The core baseline is complete when:

- The 128-bit, two-VC, four-entry configuration is implemented by hand.
- Machine-readable parameters and a requirement-to-test matrix are frozen.
- All legal routes, packet forms, bubble cases, resets, and simultaneous credit events pass regression.
- Credit, VC ownership, routing, grant, release, and reset properties pass formal checks.
- A multi-router mesh passes end-to-end randomized traffic tests with reproducible seeds.
- No packet loss, duplication, corruption, or illegal reordering is observed.
- Bounded round-robin service is demonstrated under its stated assumptions.
- The router sustains one flit per output per cycle under nonconflicting traffic.
- The design meets the reference timing target.
- Area and activity-based power reports are reproducible from a clean checkout.

## 27.2 QoS Extension Complete

The QoS extension is complete only after the core baseline remains green and weighted service ratios plus bounded aging are demonstrated under documented traffic, credit, and packet-length assumptions.

## 27.3 Agentic Demonstration Complete

The agentic portfolio milestone is complete when at least one agent-proposed optimization:

- Begins with an explicit hypothesis.
- Changes only authorized candidate files.
- Preserves the independent verification oracle.
- Passes the full deterministic gate sequence.
- Produces a measured, reproducible timing, area, power, or network-performance benefit.
- Is traceable to requirements, retrieved sources, its diff, tool outputs, and an accept/reject decision.

A single well-evidenced improvement is preferable to a larger multi-agent workflow with no measured engineering result.

---

**End of Bifröst NoC Router Specification v0.2**
