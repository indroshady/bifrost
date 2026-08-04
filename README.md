# Bifröst NoC Router

Bifröst is a parameterized, wormhole-switched router for a rectangular 2D
network-on-chip. This repository contains the accepted Milestone 0 contract
and the complete Milestone 1 Python architectural oracle for observable Core
v0.2 behavior.

The normative source is [`spec/BIFROST_SPEC.md`](spec/BIFROST_SPEC.md).
Machine-readable configuration and requirement traceability live beside it in
[`spec/`](spec/). The Markdown specification takes precedence if generated or
curated documentation disagrees with it.

The Python package layout, component responsibilities, cycle semantics, and
test commands are documented in [`spec/MODEL_GUIDE.md`](spec/MODEL_GUIDE.md).

## Frozen selected configuration

| Parameter | Core v0.2 selection |
|---|---:|
| Physical ports | Local, North, South, East, West |
| `FLIT_W` | 128 bits |
| `NUM_VCS` | 2 per input |
| `VC_DEPTH` | 4 flits |
| `MESH_X` × `MESH_Y` | 2 × 2 |
| `X_W` × `Y_W` | 1 × 1 bits |
| `ROUTER_X`, `ROUTER_Y` | 0, 0 |
| `PKT_ID_W` | 16 bits |
| `PORT_ID_W` / `VC_ID_W` | 3 / 1 bits |
| `QOS_W` | 2 representation bits; Core accepts class 0 only |
| `QOS_CLASSES` | 1 |
| `QOS_WEIGHTS` | `[1]` |
| Routing | Deterministic XY |
| Flow control | Registered credit, no zero-credit bypass |
| Reference clock | 2.0 ns |

The mesh dimensions, coordinate widths, router location, and packet-ID width
were required by the specification but not selected by its original sample
YAML. This repository now freezes the selected Core profile and independent RTL
representation contract.

The 128-bit flit layout is `HEAD[127]`, `TAIL[126]`, destination X/Y
`[125:124]`, source X/Y `[123:122]`, packet ID `[121:106]`, QoS class
`[105:104]`, and payload `[103:0]`. The fields are contiguous and sum to 128
bits. Port order and IDs are Local=0, North=1, South=2, East=3, West=4; 5-7 are
invalid. VC0=0 and VC1=1 use a one-bit sideband.

QoS behavior is disabled in the Core profile. Accordingly, the selected
configuration has one semantic traffic class with unit weight and accepts only
encoded class 0. The two-bit field reserves compatibility with the staged
four-class weighted/aged policy; it does not add a scheduler.

## Current milestone

Milestone 1 includes:

- JSON-Schema-validated configuration and cross-file traceability checks.
- Typed semantic flit and packet-marker validation plus an independent integer
  pack/unpack helper for the frozen representation.
- Bounded independent input-VC FIFOs and deterministic XY route caching.
- Packet-lifetime output-VC allocation with exact tail and head+tail release.
- Per-flit round-robin arbitration and concurrent nonconflicting transfers.
- Cycle-level crossbar, registered-credit, reset, and protocol-error behavior.
- Requirement-linked directed tests and a recorded-seed conservation test.

The model remains an architectural oracle and intentionally does not mirror
future RTL signals or reinterpret arbitrary Python payload objects as packed
bits. RTL, RTL simulation, formal proof, synthesis, PPA evidence, mesh studies,
QoS behavior, and agentic optimization remain deferred; no placeholder or
fabricated RTL artifact is committed.

## Setup and commands

Python 3.12 is the CI reference version.

```text
python -m venv .venv
python -m pip install -e ".[test]"
make check
```

Available targets:

| Command | Purpose |
|---|---|
| `make spec-check` | Validate schema, configuration, requirements, and mappings |
| `make model-test` | Run the Python model tests |
| `make check` | Run all gates available at this milestone |
| `make clean` | Remove generated Python/build artifacts |

On Windows without `make`, run:

```text
py scripts\validate_spec.py
py -m pytest model\tests
```

## Repository map

```text
.
├── spec/                  Normative and machine-readable contract
├── scripts/               Deterministic validation entry points
├── model/bifrost_model/   Executable Core v0.2 behavior
├── model/tests/           Requirement-linked unit tests
└── .github/workflows/     Clean-checkout CI
```

Directories from the mature repository plan are added only with their first
real, reviewed artifact.

## Development order

1. Freeze and independently review the observable contract.
2. Complete the executable Python router oracle.
3. Add a clear hand-written RTL baseline.
4. Add independent simulation and formal verification.
5. Establish reproducible timing, area, power, and traffic evidence.
6. Stage QoS, then permit bounded agent-proposed optimizations.

No `spec-v0.2` tag is created until independent spec acceptance is complete.

## Requirement traceability

Every Section 25 Core and staged QoS ID is present in
[`spec/requirements.yaml`](spec/requirements.yaml) and mapped in
[`spec/requirements_to_tests.csv`](spec/requirements_to_tests.csv).
Implemented rows must resolve to an existing artifact and, for unit tests, an
existing requirement-named test. Planned rows remain explicit rather than
overstating current coverage. `make spec-check` enforces these rules.

Specification/oracle changes must be reviewed separately from candidate RTL
changes that they evaluate.
