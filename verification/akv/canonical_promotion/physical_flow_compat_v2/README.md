# Physical Flow Compatibility V2

Prospective packaging only. No canonical changes, EDA invocation, actual DB
inspection, synthesis, area measurement or PPA closure. The frozen v1 renderer
and its semantic test fixtures are reused read-only and pinned in the receipt.

## Scope

The fresh `physical_flow.patch` targets exactly:

- `backend/syn/ara_soc/v1-dc/global_scripts/dc.tcl`
- `verification/akv/synthesis/akv_engine_dc.tcl`
- `hardware/scripts/akv/check-synthesis-preflight.py`
- `hardware/scripts/akv/collect-synthesis-results.py`
- `hardware/Makefile`

Separate `standalone_caller.patch` targets `verification/akv/Makefile` relative
to the frozen `standalone_package/verification/akv/Makefile`, not current canonical.
Apply in manifest order: the existing `standalone_makefiles.patch`, then
`physical_flow.patch`, then `standalone_caller.patch`. Already-applied first-stage
packaging must not be applied twice. Tests apply both successor patches to a
temporary fixture and reverse them back to exact original bytes.

Global metrics rendering is byte-identical to v1. The collector
retains all strict organization/count/capacity checks and historical report
support. Unified requires Q64x256=1, KV128x256=8, legacy V1=0, total=9 and
278528 bits; Q is not classified as legacy V1.

## Standalone Selection

Absent `AKV_STORAGE_ORGANIZATION`, standalone Tcl selects
`split_v1_96x256_v2_128x256`: required/linked SRAM DBs are only 96 and 128.
Explicit `AKV_STORAGE_ORGANIZATION=unified_q64x256_kv128x256` selects only 64
and 128, without requiring or linking a removed 96 DB. Standard-cell and
synthetic-library dependencies are unchanged. Empty, unknown and historical
64-only selections are rejected; historical 64-only reports remain readable.

Actual postcompile hierarchy classification must equal the selection before
summary metrics are written. The collector recognizes only the exact generated
selection block, and collects its active branch according to the validated
report organization. Changed/duplicate blocks or missing/unknown organization
fail. Library declarations elsewhere are not filtered or weakened.

## Promoted Makefile Caller

`hardware/Makefile` gains `dc_akv_storage_organization`, defaulting to unified
when either `akv=1` or `akv_v2=1`, otherwise split, and passes it when AKV is enabled.
Explicit `dc_akv_storage_organization=split_v1_96x256_v2_128x256` permits a legacy
source graph. QBS-only calls omit the new argument. The existing DC lock,
`dc_flist_locked` prerequisite, source generation, feature/configuration flags,
and downstream DC/report commands are unchanged. The separate caller successor
preserves `synth-preflight: synth-wrapper-compile` and its recipes, adding the
same variable to BOTH recursive hardware preflight and direct Python preflight.
That caller always requests v2, so defaults to unified with explicit legacy
override. No original Makefile or frozen package is modified. This Makefile
variable does not change the standalone Tcl default:
standalone unified execution must explicitly set the environment option above.

## Legacy Commands Use Unified Storage

The promoted snapshot03 `source/hardware/src/vlsu/akv/akv_engine.sv:577`
unconditionally instantiates `akv_unified_context`. The snapshot's
`support/akv_unified_context.sv:75` routes legacy K/V writes into the shared KV
path, and `:119` unconditionally instantiates `akv_v2_context i_kv_store`.
Neither instance is protected by `ARA_AKV_V2_ENABLE`. Therefore disabling v2
commands does not restore the old physical split storage.

Unified preflight requires explicit AKV selection (`--require-akv` or
`--require-akv-v2`) and the actual `ARA_AKV_ENABLE=1` define. It does not require
v2 commands to be enabled. All unified dependencies, including v2_context before
unified_context before engine and reader before shared reader before VLSU,
remain mandatory and ordered. Macro mode still requires Q64 and KV128 blackboxes,
existing DBs and setup inclusion even for legacy-only commands. The v2 command
define is required only when `--require-akv-v2` is requested. Explicit split is
still accepted for a legacy source graph, not a promoted unified graph. QBS-only
calls do not force unified or v2 command selection.

## Reproduce

From the signoff root:

```sh
python3 -B -m unittest discover -s verification/akv/canonical_promotion/physical_flow_compat_v2 -p test_compat.py
python3 -B verification/akv/canonical_promotion/physical_flow_compat_v2/render.py --output verification/akv/canonical_promotion/physical_flow_compat_v2/prospective-02
```

The initial `prospective/` is preserved as historical output, with its original
helper hashes; it is not the current acceptance receipt. Output must be fresh.
`prospective-02/manifest.json` records original before hashes, five
candidate after hashes, the separate caller before/after/patch hashes, serial
apply order, and v1/v2/package helper pins. The patches are not
applied. Tests evaluate Tcl with mocked cells/files, synthetic library receipts
and an isolated `make -n` recipe with an inert prerequisite, never the real
Bender/DC/container dependency graph. Legacy host suites run against v2-rendered
Python. No actual library availability or future DC behavior is claimed.
