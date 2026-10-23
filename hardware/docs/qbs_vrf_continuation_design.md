# QBS long-K continuation through architectural vector registers

Status: the raw accumulator restore port and compute seed phase are implemented
behind default-disabled parameters and pass unit-level acceptance. Commit/VRF
mapping also passes. The instruction, actual lane operand route and production
runtime described below are not implemented. This is not yet a supported ISA
feature or a demonstrated full-projection speedup.

## Why this alternative is being examined

The original long-K panel proposal in `qbs_activation_tile_context.md` retains
two output-tile checkpoints in private storage. Another option is to use the
VRF that already holds completed QBS results. A four-input N32 result occupies
four vector registers; two such output tiles require eight architectural
registers rather than an additional private 1 KiB checkpoint array.

This is not register renaming. A continuation explicitly reads an
architectural vector source and writes its destination, like an ordinary
read-modify-write vector operation. Context save/restore can preserve those
partial sums as vector state. The existing activation-context ownership and
cache-miss behavior remain a separate issue; this proposal does not magically
make that hidden cache process-safe.

The numerical requirement is to load the previous raw FP32 bits and continue
the existing ordered FMADD sequence. It must not add independently accumulated
stripe totals afterward. Contributions `2^25, -2^25, 1` give FP32 result 1
sequentially; grouping the final two into their own stripe rounds their sum
to `-2^25`, so a later addition can give 0 instead. Raw-bit restoration permits
the sequential answer without executing an extra floating-point add.

## Current-code feasibility

| Boundary | Actual current behavior | Required extension |
| --- | --- | --- |
| Dispatcher | `VQBEXEC` writes `vd`, forces EW32 and M-dependent destination EMUL, and waits for older Ara work | A distinct capability-gated accumulate form must also declare the old `vd` as a vector source |
| Sequencer | `no_src_vrf()` treats all current QBS requests as source-free | The seeded form must participate in source readiness and ordinary RAW/WAR/WAW checks |
| Lane sequencer | Store operands use the existing StA queue; LoadUnit does not request StA for QBS | Add a targeted seeded-QBS StA request under LoadUnit; do not invent a real store transaction |
| VLSU | QBS excludes normal memory clients and consumes no store operands | Route the owned StA payload to a seed consumer and gate it away from VSTU |
| Compute engine | Default-disabled `SeedRestoreEnable` adds an initialized seed phase and suppresses first-block zeroing for continuation | Connect the owned lane stream and hold fault completion until that external stream drains |
| FP accumulator | Default-disabled `RawSeedEnable` adds idle-only raw restore into the existing eight banks of sixteen FP32 words | No new checkpoint array or second FP arithmetic pipeline; real source dependencies still need integration |
| Commit | Final arithmetic values pass through the existing LDU result writer | Retain existing fault-before-write and completion behavior for each instruction |

No encoding is allocated by this prototype. Current qbexec funct7 bits[6:3]
are reserved and checked. Reusing a reserved bit requires an explicit new
capability, decoder validation, model support and fallback selection; it must
not silently change the meaning of existing binaries.

## Architectural and software contract

The first stripe uses ordinary QBS initialization. A continuation takes the
previous partial sums as an explicit vector operand. Both use the same scale
formation, integer conversion and dot/min correction sequence. Only the
global first contribution starts from zero; local K=0 in a later stripe does
not reset the accumulator.

Each instruction publishes its own result and FP flags. Sticky architectural
fflags across the sequence must equal those of the corresponding uninterrupted
arithmetic sequence. This is different from a private BEGIN/FINALIZE design
that hides all flags until FINALIZE; no such hidden-flag promise is made here.
A failing later stripe must leave its old vector destination unchanged, so
the previous completed stripe remains architectural state. Atomicity is per
instruction, not an all-or-nothing entire projection.

Two output tiles can consume one resident activation stripe while retaining
their separate partial sums in distinct vector groups. Software owns global
K ordering, matrix layout and tile identity, just as it owns ordinary vector
MAC loops. Current segmented-R4 weight storage must be respected; reducing
descriptor K alone still does not fix global row-group strides.

Architectural registers are not automatically preserved across arbitrary C
calls: the vector ABI permits caller-saved registers to be clobbered. A real
runtime must use a bounded assembly panel driver or compiler-visible live
vector operands. Merely changing a C callback and assuming v8 survives later
packing calls is incorrect. Any spills, final stores, descriptor preparation
and command overhead must be included in the performance comparison.

## Lane mapping must invert the actual commit path

For four lanes and EW32, `qbs_commit.sv` writes each lane word as:

```text
lane L low 32 bits  = element L
lane L high 32 bits = element L+4
```

The inverse is therefore seed bank `b` from lane `b % 4`, half `b / 4`.
Concatenating lane0 low/high followed by lane1 low/high permutes the values
and is wrong.

The accumulator and architectural register strides also differ by command:

| Shape family | Accumulator stride per input row | Architectural register allocation |
| --- | --- | --- |
| M1–M4 | 32 FP32 values | One register per input row; inactive N positions written as zero |
| M5–M8 | 16 FP32 values | One register per input row, but only active N positions are written; tails preserved |

The VRF/store stream for an entire input row still contains four aggregate
words of eight FP32 values. For wide M, only the first one or two words contain
active accumulators. The remaining words must be drained and ignored, not
written to the next accumulator row. Even for N<=8, a stale upper half is not
a valid additional partial sum. A descriptor-derived mask must distinguish
active N elements. The first integration should not claim M/N-tail coverage
from a raw dense M4/N32 bank-copy test.

## Ownership, backpressure and faults

- QBS admission retains its existing exclusive VLSU ownership and older-work
  drain. A seeded request must not bypass true source dependencies.
- Each lane's operand queue must receive the correct old-EEW/EMUL metadata,
  after any required existing layout repair. Seeded requests are not source-free.
- Aggregate consumption is atomic across four balanced lane words. Stalled
  source valid/data must remain stable; no word may be consumed twice.
- VSTU must not see the seed valid stream. Selecting only a different ready
  signal while still feeding valid to both consumers is insufficient.
- Descriptor faults may occur before seeding starts. The command must drain or
  explicitly flush its own outstanding StA stream before returning an exception
  and before a later normal store can own that untagged interface.
- An abort during seeding discards working accumulator state, drains remaining
  owned seed payload and commits no destination bytes. Existing FP work and
  memory reads must also drain before the terminal response.
- Reset must invalidate the seed transaction and flush the corresponding lane
  queue state. Mapper reset alone does not prove a whole-SoC reset is safe.
- No compute request starts before the required raw partial sums are valid.
  Early payload prefetch may overlap seeding only when the existing buffer
  clear/write and fault invariants remain satisfied.

## Implemented prototype and measured evidence

`qbs_fp_accumulator` has an idle-only eight-bank raw restore port controlled by
`RawSeedEnable=0` by default. Its write mux targets the existing bank words; it
adds no private checkpoint array and executes no floating-point operation for
a restore. `run_seed_restore.py` derives a separately named instance by changing
only the module name and the enable parameter when the production port is
present; anchor checks reject drift. The production QBS controller still ties
off the new compute inputs and does not enable this feature.

VCS run `verification/out/qbs-seed-restore-production-20261023-02/` passed:

- 128 arbitrary FP32 raw-word copies, including NaN encodings and signed zero;
- masked validity restoration without arithmetic or flag updates;
- nine current weight profiles, all 128 accumulator locations, and two ordered
  contributions per location;
- 2432 checked word comparisons in total;
- exact monolithic versus clear/restore result bits and accumulated flag union;
- arithmetic-update counts excluding raw restores; and
- the `2^25,-2^25,1` order witness, yielding `0x3f800000` with continuation.

Four temporal protocol checks additionally cover waiting for older FP work,
seed/arithmetic arbitration, clear and reset. A pending seed blocks new
arithmetic admission but cannot overwrite an in-flight operation. Clear and
reset prohibit seed handshakes. Restore changes neither flags nor arithmetic
update counts. The receipt is `verification/qbs/results/raw-seed-production-20261023.json`.

The independently accumulated second stripe produces `0xcc000000`, confirming
why software addition of stripe totals is not interchangeable with continuation.
This port test does not by itself validate the lane queue, actual VRF readback,
new instruction or a full-projection performance gain.

### Commit/VRF mapping acceptance

`qbs_vrf_seed_mapper.sv` now implements the inverse mapping as an independent
four-lane, VLEN1024 building block. It is deliberately not in Bender and has
no effect on the current instruction decoder or execution path. It owns no
checkpoint storage: eight combinational bank outputs feed the idle restore
port. Lane words are consumed together only when all four are present and
the active bank write is accepted. Empty N-tail words are drained without
waiting for an accumulator write. Abort suppresses the seed write immediately,
latches discard mode and drains every remaining owned word before completion.
The completion handshake retains ownership until accepted. This is not an
untagged-interface arbiter: the future VLSU owner must exclude VSTU valid as
well as ready and must arrange source queue flushing on reset.

`run_vrf_seed_mapper.py` compiles the actual `qbs_commit`, the new mapper and
the raw-restore accumulator prototype. The test models only the VRF storage
and StA delivery. Actual commit byte enables populate the model, including
preserved wide-M tails. The resulting register words are fed back through
the mapper into the accumulator. Independent checks cover the forward VRF
placement, inverse bank mapping, active validity mask and raw accumulator bits.

VCS run `verification/out/qbs-vrf-seed-mapper-production-20261023-01/` passed 961 scenarios
and 162172 checks:

- All 192 supported shapes: M1--M4 with N1--N32, M5--M8 with N1--N16.
- Each shape runs with immediate input, staggered lane arrivals and sink
  backpressure, descriptor-style discard, mid-stream abort, and abort while
  the first active seed word is backpressured.
- Input streams retain valid/data until the four-lane handshake. Every stream
  drains exactly four words per input row, including wide-M inactive tails.
- Completion is held under response backpressure, then releases ownership.
- One additional M8/N15 run follows reset during a partially delivered stream;
  the test explicitly flushes its modeled source, rather than claiming mapper
  reset alone flushes actual lane queues.
- Restoring raw data does not change FP flags or arithmetic update counts.

Run01 was rejected because the fixture asserted completion-ready after a
readback delay and removed it at the next falling edge, without crossing a
rising edge. The corrected fixture drives that handshake on falling edges;
no mapper change was needed. The failed run is retained. This is still not
an actual Lane, operand requester, VLSU arbitration or SoC test.

### Compute continuation acceptance

`qbs_compute_engine` captures `command_seed_i` only when its default-disabled
`SeedRestoreEnable` parameter is set. Initialization still clears working state.
A seeded command then waits in `QBS_SEED`; no activation/weight work is requested
until all active accumulator values have arrived. Its first local K-block is
not marked as a global first block, so the existing integer/FP scheduler follows
the same ordered accumulation path as a later block in an unsplit command.

The seed interface consumes one complete active mask per accumulator row.
Raw restore replaces the row's validity mask; it is not a sequence of partial
masked inserts. The simulation ownership checks therefore reject duplicate
rows and incomplete active masks, and prove every active accumulator is present
before computation starts. Completion may accompany the last accepted row or
follow on the next cycle. Fault in the seed phase suppresses new seed writes,
drains any existing internal work, clears working state and exposes no result.
Draining the external lane stream remains the responsibility of the future
parent integration, not the compute engine.

`run_compute_continuation.py` derives its fixture from the ordinary compute
bench, retaining the independent C command-vector reference. It executes the
same 36 cases as both unsplit commands and one-command-per-K-block continuation.
It combines prefix flags/counters and compares the final raw output bits to
the original full-K oracle, rather than adding independently computed stripe
totals. The matrix includes all nine profiles, M1--M8, layout variants, N tails,
and a 256-block case. The gate checks active checkpoint validity/unknowns and
uses fail-closed four-state output, flag and counter comparisons.

Run `verification/out/qbs-compute-continuation-20261023-03/` passed both modes
with 362 restores in the split mode. The timing of final seed/done is alternated
across prefixes. Both modes additionally pass cancellation after a partial
restore, reset during restore, ordinary command abort, and four integer-pipeline
fault positions. The receipt is
`verification/qbs/results/compute-continuation-20261023.json`.

The full QBS controller was rebuilt separately with all new inputs tied off and
both parameters disabled, using `run_seed_default_engine.py`. Run
`verification/out/qbs-seed-default-engine-20261023-01/` passed all four groups:
36 direct cases, twelve capacity-boundary context cases, and real M4/N32/K896
with response gaps zero and four. Exact direct/FILL/REUSE cycles, input-vector
identities and accepted outputs match the pre-extension controller. Validation,
MMU, AXI, PMA and interrupted context replay checks are retained. The receipt is
`verification/qbs/results/seed-default-engine-20261023.json`. This establishes
unchanged default QBS controller behavior/cycles for that gate, not ordinary
RVV whole-SoC signoff or new-instruction acceptance.

## Next gates

1. Wire a capability-gated instruction and real lane/VLSU source route, then
   test old-vd dependencies, layout repair, invalid descriptors and page/AXI
   faults on the actual SoC.
2. Add the bounded shared runtime panel driver and independent model contract.
3. Measure an equal-output real long-K projection with unchanged FP order,
   including preparation, all seed/commit traffic, spills and command overhead.
   Do not deploy solely because activation traffic decreases.
