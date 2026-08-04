# Bifröst Python Model Guide

## Purpose

`model/` contains the executable architectural oracle for the Bifröst Core
v0.2 profile. It models behavior visible at router boundaries and to a
verification scoreboard: accepted flits, packet state, routing, output-VC
ownership, arbitration, transfers, credits, reset, and protocol violations.

The model is intentionally independent of future RTL structure. It does not
define a packed flit encoding, reproduce pipeline registers, enable the staged
QoS policy, or expose candidate RTL implementation signals. The normative
behavior remains defined by [`BIFROST_SPEC.md`](BIFROST_SPEC.md).

## Directory structure

```text
model/
├── bifrost_model/             Importable architectural-model package
│   ├── __init__.py            Supported public API
│   ├── config.py              Typed configuration loading and validation
│   ├── flit.py                Semantic flits and packet-marker rules
│   ├── routing.py             Pure deterministic XY routing
│   ├── credits.py             Registered downstream-credit counters
│   ├── fifo.py                Bounded per-input-VC buffering
│   ├── arbitration.py         Deterministic round-robin arbitration
│   ├── vc_allocator.py        Packet-lifetime output-VC ownership
│   └── router.py              Cycle-level integration oracle
└── tests/                     Requirement-named pytest suite
    ├── test_config.py         Frozen profile and invalid configuration
    ├── test_flit.py           Flit metadata and packet-marker sequences
    ├── test_routing.py        XY direction and coordinate validation
    ├── test_credits.py        Credit truth table and boundary failures
    ├── test_fifo.py           FIFO order, bounds, independence, and reset
    ├── test_arbitration.py    One-winner and round-robin service behavior
    ├── test_vc_allocator.py   Ownership, fairness, and exact release
    └── test_router.py         Integrated cycles, packets, reset, and conservation
```

## Package files

| File | Responsibility |
|---|---|
| `__init__.py` | Re-exports the supported model API so callers do not depend on private package layout. |
| `config.py` | Loads `spec/bifrost.yaml`, validates it against JSON Schema, and checks cross-field Core v0.2 invariants. |
| `flit.py` | Represents flits semantically and rejects illegal head/body/tail sequences without assigning wire bits. |
| `routing.py` | Computes the pure X-first deterministic route. Increasing Y is North. |
| `credits.py` | Implements one bounded registered credit counter, including simultaneous send/return behavior and no zero-credit bypass. |
| `fifo.py` | Stores one input VC in order and tracks receive-side packet boundaries independently from occupancy. |
| `arbitration.py` | Selects one eligible requester in round-robin order and advances history only after a committed grant. |
| `vc_allocator.py` | Owns one physical output's VC allocation table and retains ownership until the transmitted tail releases it. |
| `router.py` | Composes every component into a synchronous five-port cycle model and emits transfer and upstream-credit events. |

## Router cycle semantics

`BifrostRouter.step()` models one active clock edge. Its ordering is deliberate:

1. Validate all arrivals, downstream credit returns, and reset inputs without
   changing state.
2. Select transfers from currently registered route, allocation, FIFO, arbiter,
   and credit state.
3. Determine allocation requests from headers that were already buffered.
4. Preflight every credit counter update so an invalid event cannot partially
   commit a cycle.
5. Commit at most one new output-VC allocation per physical output.
6. Commit transfers, dequeue their input entries, advance successful arbiters,
   return upstream credits, and release packet state on tails.
7. Apply registered downstream-credit updates.
8. Store newly arrived flits for consideration on the next cycle.

This ordering implements the required two-step allocate-then-traverse behavior.
A credit arriving when the registered count is zero cannot authorize a transfer
in that same cycle.

Each output first proposes its strict round-robin winner. If two output
proposals need the same physical input, that input accepts one using its own
round-robin arbiter. A losing output does not fall back to a later requester in
the same cycle, because doing so would count a successful output transmission
while skipping the next requester and could violate the Core bounded-service
guarantee.

## Basic use

```python
from pathlib import Path

from bifrost_model import BifrostRouter, FlitArrival, Port, load_config

config = load_config(Path("spec/bifrost.yaml"))
router = BifrostRouter(config)

result = router.step(
    arrivals=(FlitArrival(input_port=Port.LOCAL, input_vc=0, flit=my_flit),)
)
```

Headers are accepted first, allocated on a later `step()`, and transferred only
after allocation, arbitration, and positive registered credit all agree.
Malformed traffic raises the component-specific `ValueError` subclass rather
than being silently dropped.

## Running validation

Install the package and test dependency from the repository root:

```text
python -m pip install -e ".[test]"
```

Run every repository gate on systems with `make`:

```text
make check
```

Run the equivalent commands directly:

```text
python scripts/validate_spec.py
python -m pytest model/tests
```

On Windows with the Python launcher:

```text
py scripts\validate_spec.py
py -m pytest model\tests
```

Run one component or one requirement while developing:

```text
python -m pytest model/tests/test_router.py
python -m pytest model/tests -k ARB_002
```

Requirement-linked tests include the requirement ID in the function name.
`spec/requirements_to_tests.csv` marks a mapping implemented only when the
named test exists. The integrated conservation and ordering test records seed
`0xB1F205E` in its name and failure diagnostics for deterministic replay.
