# Shared-reader plus unified-storage successor

NEW helper files only. Canonical RTL, snapshot-02, accepted storage/repacker and
reader candidates, old preparation/compiler/SoC builder/worker/wave helpers remain
unchanged. No simulator is launched by these preparation/build commands.

## Exact transformation

`prepare_storage.py` first calls the immutable shared-reader `prepare.prepare`
into a fresh output. It then changes ONLY the copied AKV engine storage-instance
block and removes the old combined-busy assignment. Old named-port expressions
are mechanically carried into one `akv_unified_context i_unified_context`.

- `.legacy_row_bytes_i(9'(payload_row_bytes))` uses the SAME range length as
  `form_read_range`. Canonical `akv_engine.sv:440` derives it from latched
  `context_head_dim_q`; lines 1017-1033 latch a validated FULL descriptor before
  PAYLOAD. REFILL retains those fields. No unvalidated live descriptor is used.
- `.abort_i(read_fault_valid && read_fault_ready)` is the existing reader-fault
  acceptance event (canonical lines 1054-1061). It cancels unconsumed storage
  writes at that edge. No new fault state, pipeline, drain loop, or readiness
  dependency is added. Committed Q is NOT cleared; failed REFILL still invalidates
  context-ready according to the unchanged controller.
- Candidate aggregate busy drives `context_write_busy`. Per-path busy outputs
  retain existing engine names. `payload_complete`, metadata, command states,
  replay state/valid/VRF commits, and fault publication remain byte-identical.
- Existing legacy replay condition `REPLAY_READ && !replay_use_v2_q &&
  !replay_column_q` and v2 row/column bindings are transferred verbatim. Despite
  its name, `replay_use_v2_q` selects the old v2 KV path; Q stays on legacy replay.
- Direct v2 writes remain combinational; pending Q can drain concurrently into
  its separate SRAM. Only repacked legacy KV shares the single direct-KV port.
- QBS context, VLSU ownership, reader, clocks, AXI cut, MMU, seed and completion
  logic are exactly the prior shared-reader transformation. Existing admission
  and wave probes use engine-level storage signals, not deleted SRAM instances.

The source graph adds THREE production SV files, copied byte-identically:
`akv_legacy_repacker.sv`, `akv_q_store.sv`, `akv_unified_context.sv`. The unit TB is
proof input only, NEVER a SoC compilation unit. Old context module definitions
remain in the complete closure, but the AKV engine no longer instantiates either.
Physical context hierarchy is now `i_akv_engine.i_unified_context.i_q_store` and
`i_akv_engine.i_unified_context.i_kv_store` (one 2 KiB Q plus one 32 KiB KV store).

## Evidence and review boundaries

Both accepted tc/macro unit results must be PASS with unchanged manifests,
compiled/log artifacts, exact exit=0 and rechecked strict terminal counts. All
accepted source pins, including the three real macro models, are merged with the
full original image closure and new helper pins. Conflicting/missing pins reject.
The macro unit is functional only, not timing signoff. The SoC filelist keeps
its accepted macro-selection defines; adding support does not switch SRAM modes.

`reader-overlay.patch` preserves the first-stage reader diff. `storage.patch`
contains only the additional AKV storage diff. `overlay.patch` gives the complete
three-module canonical-to-successor diff. Every artifact gets a refreshed pin.
No prior snapshot or build result is edited or reused as a new acceptance claim.

Compile wrappers validate the storage snapshot type and pre-pins, then call the
immutable original build implementations. Their bounds, cleanup, exact accepted
flags, original SoC UVM units, elfloader, and post-pin/closure checks are retained.
The full-SoC build requires a passing VLSU compile of this exact manifest.

## Commands

```sh
python3 -B -m unittest discover -s verification/akv/shared_reader_integration \
  -p test_prepare_storage.py -v
python3 -B verification/akv/shared_reader_integration/prepare_storage.py \
  --manifest verification/out/qbacc-soc-20261023-02/build/sim/vcs_source_manifest.json \
  --output verification/akv/shared_reader_integration/snapshot-03
python3 -B verification/akv/shared_reader_integration/compile_storage.py \
  --snapshot verification/akv/shared_reader_integration/snapshot-03 \
  --output verification/out/shared-storage-integration-compile-20261025-01
python3 -B verification/akv/shared_reader_integration/build_storage_soc.py \
  --snapshot verification/akv/shared_reader_integration/snapshot-03 \
  --compile-receipt verification/out/shared-storage-integration-compile-20261025-01/result.json \
  --accepted-sim verification/out/qbacc-soc-20261023-02/build/sim \
  --output verification/out/shared-storage-integration-soc-build-20261025-01
```

Long builds must be directly owned by independent systemd user services, with
fresh outputs and actual compiler PID confirmation. The last two commands only
compile; they do not run SoC firmware. Do not stage generated snapshot files.

After parent review and a successful full build, existing parameterized immutable
workers can consume the new image for 71-command handoff, opposite-owner 14-command
fault, and real runtime gates. No SoC simulation is authorized by these scripts.
Expected row/terminal latency is unchanged on complete payloads, but this remains
a measurement obligation, not a promised equality: actual AXI fragment patterns
and abort timing must be tested at the integrated engine boundary. Unit results
are not SoC context-survival proof, area evidence, or performance measurements.
