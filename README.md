# Bifröst NoC Router

Bifröst is a parameterized, wormhole-switched router for a rectangular 2D
network-on-chip. This repository currently contains the Milestone 0 contract
and an executable Python model for the observable Core v0.2 flit-marker,
deterministic-XY-routing, and registered-credit behavior.

The normative source is [`spec/BIFROST_SPEC.md`](spec/BIFROST_SPEC.md).
Machine-readable configuration and requirement traceability live beside it in
[`spec/`](spec/). The Markdown specification takes precedence if generated or
curated documentation disagrees with it.

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
| `QOS_CLASSES` | 1 |
| `QOS_WEIGHTS` | `[1]` |
| Routing | Deterministic XY |
| Flow control | Registered credit, no zero-credit bypass |
| Reference clock | 2.0 ns |

The mesh dimensions, coordinate widths, router location, and packet-ID width
were required by the specification but not selected by its sample YAML. This
repository selects concrete, internally consistent values for the executable
Core profile. They are configuration choices subject to independent spec
review, not invented wire-format allocations. Flits are represented
semantically; no RTL bit encoding is defined yet.

QoS is disabled in the Core profile. Accordingly, the selected configuration
has one traffic class with unit weight. The four-class weighted/aged policy and
its traceability requirements remain staged.

## Current milestone

Milestone 0 includes:

- JSON-Schema-validated configuration and cross-file traceability checks.
- Typed semantic flit and packet-marker validation.
- Deterministic XY routing, where increasing Y routes North.
- Exact registered-credit state transitions and boundary checks.
- Targeted unit tests linked to requirement IDs.

RTL, integrated FIFO/allocator/arbitration/router models, simulation, formal
proof, synthesis, PPA evidence, mesh studies, QoS, and agentic optimization are
deliberately excluded from this commit. The PDF rendering and architecture SVG
listed in the implementation plan were not provided and are deferred; no
placeholder or fabricated artifact is committed.

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
