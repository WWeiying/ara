# Snapshot03 canonical promotion checklist

Read-only preparation plus this NEW note only. No canonical, pinned helper, or
previous receipt was edited. No service/process polling, build, simulation,
synthesis, PPA analysis, or commit was performed. This is NOT promotion approval.
Paths below are relative to ara_dsa_signoff_integration.

## Evidence already closed

Parent reports commit d0987469 containing independently raw-audited resource
receipts. The following saved fields were read, not freshly re-audited here:

| Receipt in verification/akv/results | Accepted scope |
| --- | --- |
| shared-storage-timed-decode-pair-20261025.json | PASS; same ELF; 12 complete calls with identical cycles; all 3680 command records identical |
| shared-reader-real-prefill-20261025.json | Shared-reader-only; four complete calls; 13380 command records identical; complete-call no regression |
| shared-storage-real-prefill-20261025.json | Unified storage; four complete calls; 13380 command records identical; complete-call no regression |
| shared-storage-real-decode-20261025.json | Unified storage; 12 calls/3680 command records identical; this earlier fixture itself lacks complete-call cycles, supplied by the separate timed receipt |
| shared-storage-handoff-20261025.json | Same-ELF 71-command exact counter comparison, resident contexts, real one-reader wave routing |
| shared-storage-reverse-fault-20261025.json | Same-ELF 14-command opposite-owner PMA fault/recovery and preserved QBS context |
| shared-storage-component-audit-20261025.json | Accepted unit/source-overlay evidence, with explicitly limited component scope |

Do not repeat the obsolete assertion that Prefill or timed Decode is pending.
Do not turn these receipts into ordinary-RVV acceleration, whole-model, area,
or timing-closure claims. Earlier docs are historical and remain unchanged.

## Exact production source changes

Copy byte-identical accepted files from snapshot03, not freshly re-rendered files
against a potentially changed canonical input. Retain manifest/diff identities.

Replace these THREE canonical modules from snapshot-03/source/:

```
hardware/src/vlsu/qbs/qbs_engine.sv
hardware/src/vlsu/akv/akv_engine.sv
hardware/src/vlsu/vlsu.sv
```

Map snapshot03's support files to these SEVEN destinations:

```
hardware/src/vlsu/qbs_akv_shared_reader.sv
hardware/src/vlsu/akv/akv_legacy_repacker.sv
hardware/src/vlsu/akv/akv_q_store.sv
hardware/src/vlsu/akv/akv_unified_context.sv
hardware/include/shared_reader_types.svh
hardware/include/vlsu_shared_reader.svh
hardware/include/admission_assertions.svh
```

No qbs_read_engine algorithm, old context implementation, package/ABI, Lane,
dispatcher, or sequencer edits are required. Keep old context module definitions
available for independent reference/unit tests; do not instantiate the old legacy
context alongside the unified store in production.

### Precise Bender ordering

Keep the existing package section and hardware/include export. In Bender.yml,
insert the shared reader immediately after qbs/qbs_read_engine.sv (currently line
66). Preserve the intervening QBS sources and qbs_engine entry. Replace the current
AKV source block with this dependency-first sequence (old definitions retained):

```
hardware/src/vlsu/akv/akv_context.sv
hardware/src/vlsu/akv/akv_v2_context.sv
hardware/src/vlsu/akv/akv_legacy_repacker.sv
hardware/src/vlsu/akv/akv_q_store.sv
hardware/src/vlsu/akv/akv_unified_context.sv
hardware/src/vlsu/akv/akv_engine.sv
```

Both engines and shared reader precede vlsu.sv. The three .svh files are include
fragments, not independent compilation units. No Bender dependency version change
or Bender.lock regeneration is needed. config/sram.mk already has 64x256 support;
do not change memory mode or add unrelated configuration churn.

## Scoped old-port instance inventory

Source scan covered hardware/, verification/, apps/ .sv/.svh files, excluding
generated out/build/snapshot trees. Bind statements and archived header module
declarations are not instances.

| Instance | Required action |
| --- | --- |
| hardware/src/vlsu/vlsu.sv:1032 QBS and :1144 AKV | Replace with accepted snapshot03 VLSU plumbing |
| verification/qbs/qbs_engine_tb.sv:235 | Keep original TB; generated test-only composed DUT and hierarchy remap |
| verification/akv/akv_engine_tb.sv:120 | Same; preserve original assertions/tasks/expectations |
| verification/akv/synthesis/akv_engine_synth_wrapper.sv:123 | Adapt production external-reader interface; details below |
| hardware/fpga/ara_dsa_vcu118/rtl/ara/hardware/src/vlsu/vlsu.sv:837 and :944 | Separate vendored FPGA source tree, not current canonical Bender closure |

The FPGA tree also has its own engine definitions and scripts/sources.tcl:425-428.
Do not silently promote that separate mirror or claim FPGA coverage. It needs an
explicit separate sync scope if that deployment is required. Existing module-bind
checkers keep the qbs_engine/akv_engine module names; the extraction does not rename
the production modules.

## Original standalone Makefile compatibility

verification/qbs/Makefile:65,72,205-215 and verification/akv/Makefile:8,54-75 still
compile the original engine TB directly. Merely adding modules to Bender does NOT
repair these old-port instantiations.

- Keep both TB files and vector expectations byte-identical. Use the accepted
  compose_canonical_standalone.py plus archived standalone_port_contracts/ headers.
  Never recover the old contract from the promoted engine header.
- Generate composed wrappers and adapted TBs in a fresh build directory; only DUT
  module naming and dut.* hierarchy prefixes may change. The production engine
  stays external-reader-only; do not add an internal-reader product parameter.
- QBS manual source list needs the shared reader and hardware/include path. Use
  the existing QBS ordered source graph, without unrelated AKV dependencies.
  AKV Bender lists need all four new modules and the same include directory.
- Route existing compile/check entrypoints to these generated sources while
  retaining vector-file overrides, engine defines, extra sources, timeout,
  top name and both generic/macro SRAM configurations. The reviewed runner offers
  explicit graph preparation and bounded compile+run; it is not a drop-in
  compile-only target. Preserve or deliberately document that Make target split.
- Use run_canonical_standalone.py with the actual canonical source root/filelist,
  not snapshot03 input pins. Keep its strict original QBS36+four-fault and full
  AKV suite checks and source-local/header inventory checks.
- Its post-terminal physical-reader counter observation is TEST-ONLY. Do not
  copy that XMR compatibility behavior into VLSU or a synthesis wrapper.

## Synthesis wrapper interface (static work only)

The current akv_engine_synth_wrapper's .i_akv_engine(.*) cannot supply reader_req_t,
reader_rsp_t or the new endpoint ports. Preserve its top-level command, commit,
AXI/MMU/PMA and metric boundary, but explicitly compose:

1. Shared request/response typedefs using wrapper VAddrWidth, AxiDataWidth and
   exception_t (opaque tag16; AKV conversion remains inside the production engine).
2. One akv_engine with reader_req_t/reader_rsp_t and explicit endpoint connections.
3. One qbs_akv_shared_reader; use endpoint1 for AKV, tie unused endpoint0 request
   to zero. Acquire owner on command_valid && command_ready; retain ownership
   through terminal acknowledgement. Pass acceptance fire even when owner was
   still zero or the command has no memory work. Wire actual AXI/MMU/PMA inputs
   and outputs without tying functional ports to constants.
4. Connect counters via real output ports, not the test-only XMR last-command
   observation. Any standalone metric-scope difference must be documented.

This wrapper has one top clock and does not replace VLSU's accepted OR-before-gate
clock logic. Production promotion must preserve acceptance/final-drain clock
coverage, counter-clear timing, endpoint-zeroing, tags and old AXI-cut ownership.

verification/akv/synthesis/akv_engine_dc.tcl:16,65-98 still requires two 96x256
legacy macros under i_context plus eight 128x256 under i_v2_context. Update the
organization/library/hierarchy contract for i_unified_context/{i_q_store,i_kv_store}
or explicitly retire that old synthesis entrypoint. Static physical capacity is
ONE 64x256 Q macro plus EIGHT 128x256 KV macros = 34 KiB, not an area estimate.
The global DC setup already contains the 64x256 library; the standalone Tcl's
explicit link-library list must also include it.

Also review hardware/scripts/akv/check-synthesis-preflight.py:73-83,287-314 and
collect-synthesis-results.py:174-175: their legacy source/macro classification
cannot be presented as the unified resource configuration. Legacy context-only
synthesis can remain explicitly legacy. No synthesis/PPA execution is requested.

## Remaining acceptance boundaries

1. Finish the already planned legacy-latency and shared-reader quant audits; this
   note does not inspect their jobs or claim terminal results.
2. Ordinary RVV representative coverage is still missing in the inspected
   snapshot03 receipts. reader_handoff/main.c:141 tests a short integer
   load/add/store before/after ownership. Timed Decode still calls
   akv_attention_execute_v2_native (timed_decode/timed_spec.py:20,
   native_runtime_main.c:81); OFF/ON there means generic/paired native AKV, NOT
   ordinary RVV Attention. It does not close the normal-LSU representative gate.
3. Lowest-change ordinary gate: reuse a frozen real-data executable invoking
   apps/llama_q4km_operator/main.c:1873 run_attention_rvv. The existing
   paired_heads/threeway_main.c:27-28,97 supplies that actual path. Compare same ELF
   old image versus snapshot03/final canonical: original golden tolerance, exact
   within-variant repeats/CSR, memory guards, no accelerator commands during the
   RVV phase, independent protocol checks, and complete RVV-call cycle comparison.
   Do not create a new RVV kernel or conflate this with native OFF mode. Current
   quantized H/S/B runs on the old image do not validate snapshot03's VLSU.
4. Integrated non-PMA fault/translation drain remains a narrower functional gap:
   existing71/14 SoC faults are PMA; held-AR/error-drain and MMU behavior have unit
   evidence but not the same complete VLSU ownership/cut path. Before broad
   fault-path acceptance, require one discriminating bounded integration case
   with stalled AR/in-flight response and fault/recovery/owner switch, or record
   an explicit unresolved scope restriction. No trial RTL/timeout changes.
5. After migration, prove the actual canonical source graph, default/enabled
   configuration elaboration and generic/macro standalone compatibility. A short
   canonical-image ownership/fault smoke checks packaging; identical normalized
   source/flags plus existing evidence avoids blindly repeating all expensive
   model experiments. No broad coverage or PPA campaign is implied.

## Pin barrier and safe order

No process refresh was performed. Parent reports V3 coordinator owner1200775;
that observation is not independently polled here. Treat coordinator and any
downstream consumers as pin blockers until parent supplies terminal audits.

V3 inherits the old pre-wait/build/image pins through coordinate_v3/threeway_v2.
The previous inventory identified the shared 66-file canonical RTL/Bender/include
subset. Overlay-image runtime workers can still verify the original canonical
inputs; copied images do not make editing those inputs safe.
verification/ara_verify/vcs_source_manifest.py:23-39 also pins hardware/Makefile,
config/default.mk, config/sram.mk and rescans declared include directories.
Even adding the three new headers can invalidate an active consumer's inventory.

Safe sequence:

1. Finish all required consumers, dependent auto-launchers and raw post-pin audits.
   Do not edit the current V3 helpers or infer that finished tails free their
   downstream provenance dependencies.
2. Archive the old canonical source closure and immutable evidence associations
   before promotion. Keep historical failures and receipts unchanged.
3. Promote byte-identical snapshot03 modules/support plus minimal Bender ordering
   and standalone-entry compatibility changes together. Do not stage generated
   snapshots or silently switch FPGA mirrors or SRAM mode.
4. Verify source mapping, unique physical reader, storage hierarchy/capacity and
   revised probes; generate fresh canonical filelists/manifests and bounded gates
   only with separate execution authorization.
5. Publish new promotion evidence identifying its actual canonical source/image.
   Snapshot03 acceptance and this checklist are not that evidence.
