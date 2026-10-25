# Legacy AKV Unit Latency Pair

No original RTL, TB, assertions, expected values, stimulus, snapshot, shared
helper or existing evidence is modified. Execution requires explicit review and
authorization; preparation alone does not invoke the compiler or simulator.

The preserved `akv-legacy-latency-pair-20261025-01` attempt failed the harness
warning contract after successful compilation, before running the suite. Its
IPDW is the inherited CVA6 shared-TLB `genvar i` redeclaration at lines 168/458,
also present verbatim in accepted `shared-storage-standalone-akv-20261025-01`.
The successor admits exactly one such complete diagnostic, only for the exact
snapshot path and fixed source SHA256. The accepted log/receipt are pinned;
each new compile records its admission. Changed names, lines, source bytes,
duplicates, other IPDW and all PCWM/PINMISSING remain failures. This does not
waive implicit-net or width warnings and does not relabel the old FAIL.

## Question

Do the original private-reader/legacy+v2-storage engine and the composed
shared-reader/unified-storage engine preserve per-command latency and counters
on the **complete unchanged original AKV unit suite**? Matching store pipeline
depth alone does not establish this. The existing 71-command SoC fixture does
not exercise v1 row loads, whereas this original suite includes v1 D64/D128,
FULL/REFILL/RELEASE, Q preservation, replay stalls, 2-byte-offset compact
fragments, validation/read faults and recovery, as well as its complete v2 suite.

This is a unit-level resource-regression gate, not new workload acceleration,
SoC ownership/clock/AXI-cut proof, full operator/model timing or PPA evidence.

## Passive Observation

The identical `monitor.sv` binds to `akv_engine_tb` on both sides, with inputs
only. It neither accesses `dut.*` nor changes any assertion/expectation/task.
Its clocking block uses `input #1step` at posedge: the sampled handshake/counters
are the values consumed at the edge, before DUT NBA updates. This is intentional
edge observation, not a claim to export post-NBA settled wave samples.

At command acceptance it captures the command/id/dimension/address/selector and
translation setting. It observes first terminal valid and prints on actual
terminal fire, before the composed wrapper releases ownership or switches its
idle counter observation. It reports acceptance-to-first-valid latency,
acceptance-to-fire latency, terminal hold cycles and existing `command_cycles`.
The latter increments while busy and may include terminal ACK waiting; it is not
silently equated with intrinsic execution latency. Absolute ticks are retained
but not required equal across the pair.

All existing exposed counters are recorded, plus cumulative original TB VRF
write/early-ACK counts and busy. Fault fields are checked only on fault; MMU
exception fields are used only on MMU fault. Inactive fields are emitted as zero.
Unknown valid metadata, resets after first acceptance, overlapping commands,
unowned/disappearing terminals or incomplete completion reject the observation.
Original TB functional assertions still decide their original expectations.

The final monitor summary must have accepted=completed=record count, pending=0,
errors=0, following the original exact suite PASS. Missing/duplicate/unknown
records and invalid arithmetic are rejected. Every record's identity, outcome,
qualified metadata, relative latencies and counters must match exactly across
the pair; even an improvement is a reported REGRESSION/difference requiring
review, not silently accepted. Raw per-command differences and both full ledgers
are preserved. No aggregate can hide one slower command.

## Paired Source Identity

Preparation validates the existing storage snapshot manifest and its full pins.
Candidate uses its unchanged production filelist. Baseline replaces exactly the
three copied overlay units (QBS engine, AKV engine, VLSU) with their hash-pinned
canonical originals. Both retain every other source, include, define, order and
the exact admitted duplicate UART entry. Added shared-storage modules remain in
both lists; they are not instantiated by the original baseline engine.

Baseline compiles a byte-exact copy of the original TB. Candidate compiles the
existing archived-header composition and strictly reversible module/XMR-only
TB adaptation. SRAM sources/defines, clock and response/backpressure stimulus
are therefore identical. This does not independently qualify another SRAM mode.

Source/header inventories, tool/helper identities, original/adapted TB, observer,
lists and manifest are pinned. Inventories are rechecked before each compile,
after compile and after each unit run. Logs, exits, generated files and simv are
bound in the final receipt. Both profiles have separate build directories.

## Later Commands

Preparation does not invoke VCS (requires the installed tool for identity pins):

```sh
python3 -B verification/akv/legacy_latency/run.py \
  --snapshot verification/akv/shared_reader_integration/snapshot-03 \
  --output verification/out/akv-legacy-latency-pair-NEW
```

Only after parent review/authorization, under a direct-owned service:

```sh
python3 -B verification/akv/legacy_latency/run.py \
  --output verification/out/akv-legacy-latency-pair-NEW \
  --execute-reviewed MANIFEST_SHA256
```

Two sequential compile+suite pairs, each phase bounded at 600 seconds. Nonzero
exit, compilation/port-width error, source drift, original-suite failure or
observer failure stops the pair. Partial/terminal attempts cannot rerun in place.
Process-group cleanup is inherited from the pinned standalone execution helper;
no service/queue creation, polling or automatic downstream execution is added.

Host-only tests, using synthetic records and static source mappings:

```sh
python3 -B -m unittest discover -s verification/akv/legacy_latency -p 'test_*.py' -v
```

Passing host tests is not SV elaboration, arithmetic or latency evidence.
