# Isolated Shared Reader Integration

Successor source snapshot only. No canonical RTL, Bender file, accepted candidate,
resident store, software or sealed verification helper is edited. Preparation
copies the complete accepted image source/header closure into a fresh directory,
then mechanically replaces **three complete production modules**: `vlsu.sv`,
`qbs_engine.sv`, `akv_engine.sv`. All other copied bytes are unchanged. The accepted
`qbs_akv_shared_reader.sv` and its types are copied byte-for-byte from unit03 pins.

## Plumbing

- Both engine readers are removed. Engines expose `reader_req_o` / `reader_rsp_i`
  using new type parameters; all command schedulers, context state, compute, fault
  processing and VRF commit/replay code is retained. QBS tags stay 16 bits; AKV
  requests explicitly zero-extend 8 bits, responses explicitly cast low 8 bits.
- VLSU owns exactly one physical reader via `i_shared_reader.i_read_engine`.
  Its two-range/two-burst capacity and algorithm are unchanged. There is no
  arbitration, pipeline or new functional ownership state.
- `shared_read_clk_en = qbs_clk_en || akv_clk_en` feeds a new clock gate on the
  original clock. Gated clocks are never ORed. Acceptance while owner=0 clears
  counters, including resident load/release commands with no memory requests.
  The enable remains asserted through the original command terminal edge.
- Existing registered owners, normal-VLSU drain test, AXI cut and ownership mux,
  normal write path, MMU mux, early ack and QBACC seed router are unchanged.
  Per-owner bus aliases preserve existing monitors. One PMA function invocation
  supplies the shared reader. No AXI/MMU cancellation is added for illegal owner.
- Reader metrics are zero for the inactive client and valid through the active
  terminal edge. They are not persistent per-client last-command counters.
  Existing terminal summaries remain on their original sampling edge.
- QBS internal XMRs become explicit **simulation-only** reader probe inputs;
  VLSU `[QBS_PERF]` reader probes point to the new physical hierarchy without
  dropping or substituting counters. Old external wave paths containing
  `i_qbs_engine.i_read_engine` or `i_akv_engine.i_read_engine` must migrate to
  `i_shared_reader.i_read_engine` and qualify records with the existing owner.
  Engine state/context/compute and top-level owner interface paths do not move.

New assertions check release only after reader/AR/drain idle and clock/owner
presence during live read work. They do **not** assert `context_write_busy==0`
on every AKV fault or alter storage abort behavior. Own-fault QBS context policy
and AKV invalidation remain the production controller's responsibility.
Successor `admission_assertions.svh` checks owner/fire known bits and no AKV write
pipeline busy/write-valid on a new command fire, not on the prior fault terminal.

## Reproducible Preparation

```sh
python3 verification/akv/shared_reader_integration/prepare.py \
  --manifest verification/out/qbacc-soc-20261023-02/build/sim/vcs_source_manifest.json \
  --output verification/akv/shared_reader_integration/snapshot-02
python3 -B -m unittest discover \
  -s verification/akv/shared_reader_integration -p 'test_*.py' -v
```

The snapshot refuses source drift against the accepted image manifest, ambiguous
anchors, unrecognized filelist tokens and output reuse. `manifest.json` records
original/source/tooling pins, every original-to-private path, and all generated
artifact hashes. `overlay.patch` is the exact three-module diff. `sources.f`
retains original defines and ordering, changes source/include paths to private
copies and inserts the unchanged candidate immediately after the original reader.
The inherited `TARGET_VERILATOR` preprocessor symbol is part of the accepted VCS
filelist; this procedure never invokes Verilator.
`vlsu_sources.f` is a separate compile-only view excluding `hardware/tb/` and
`verification/uvm/` units; exact exclusions are recorded as `compile_omitted`.
The complete closure and `sources.f` retain those sources for a future SoC build.

## Bounded Compile, Not a SoC Run

```sh
python3 verification/akv/shared_reader_integration/compile.py \
  --snapshot verification/akv/shared_reader_integration/snapshot-02 \
  --output verification/out/shared-reader-integration-compile-20261024-02
```

This compiles/elaborates the actual complete VLSU and its children only, with
VLEN1024, four lanes, 128-bit AXI and the production PE/exception type headers.
The compile top uses the built base CVA6 config (not the SoC's PMA region override);
no behavioral PMA coverage is claimed. No CPU, SoC memory, firmware or simulation
is elaborated/run. Timeout is 600s with process-group cleanup. All snapshot and
input pins are checked before/after. A compile receipt means compile-only PASS,
never functional equivalence, SoC acceptance, timing or PPA proof.

Preserved attempt01 failed at elaboration: the full filelist included `ara_tb.sv`
whose `$unit` DPI exports reference an `ara_tb` top absent from a VLSU-only build.
Snapshot-01 and its logs are unchanged; this is not passing evidence. Successor02
fixes only the compile scope and adds the requested admission-only assertions;
no routing or production algorithm changes were made in response to that error.

Future full-SoC build must consume this mapped filelist, not regenerate canonical
Bender paths, and use a fresh directly owned systemd worker with new image pins.
Do not launch it as part of this preparation. Required behavioral gates remain
the accepted handoff fixture (normal reads/writes/cut, QBS read fault then AKV and
QBS recovery, both context-survival directions), representative QBS/AKV success
and MMU/AXI/PMA fault suites, local no-memory commands, QBACC and early-ack loads.
Unit03 proves finite-stimulus mux transparency against one original reader with
the same history, not complete two-engine system equivalence.
