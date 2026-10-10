# Gap37 CSR Admission Handoff

Only new gap37 code/evidence is added. Original case/build/checker files and the
rejected counter preflight are unchanged. No simulator is launched by this module.

## Parent API

Import `gap37_csr_admission as csr` alongside the parent's existing coverage imports.

```python
csr.NAME                       # "gap37_csr_alias_tvm" (runner/outcome stem)
csr.TEST                       # "rvv:gap37_csr_alias_tvm"
csr.FORMAT                     # "gap37-csr-spike-v1"
csr.handles(item)              # explicit precheck.format match only
csr.precheck(item, proof)      # same Evidence API/return shape as evidence.precheck
csr.runtime_proof(output, plan, row)  # read-only, returns status/schema/files
```

The parent owns `run_fence_rvfi_checked_extension.py` and its worker/summarizer.
Example dispatch inside that **new parent-owned wrapper**, not a frozen collector:

```python
def precheck(item, proof):
    if csr.handles(item):
        return csr.precheck(item, proof)
    return legacy.precheck(item, proof)
```

Keep the parent's existing FENCE/RVFI path as the delegate in the actual combined
dispatcher. The optional `wrap_precheck(delegate)` and `install(evidence, delegate)`
helpers affect only an in-memory hook; they are not invoked by import or preparation.
The explicit dispatcher API above is preferred for this integration.

## Selection

`verification/out/gap37-csr-analysis-20261004-01/selection-checked.json` contains
exactly one PASS case, explicit format, immutable record/manifest hashes, source
hashes, original ELF path/hash and the 600 s budget. `selection-draft.json` remains
untouched. `admission-01/` holds new metadata and `precheck-dry.json`.

The parent composer may replace the top-level `baseline` and `baseline_bits` with
the latest completed checked corpus, and add its independently admitted FENCE.T
case. Do not change the CSR case's precheck, sources, evidence or hash fields.
The 630-PASS source audit remains historical target-selection evidence, not a
requirement that the parent keep using that baseline. No anticipated 638 count is
asserted by this adapter; checked baseline admission remains the parent's job.

Generic legacy admission is insufficient: `coverage_evidence.precheck` only infers
gap35 names; its explicit `csr-spike-v1` branch hardcodes `build_gap35_csr.py` and a
different record schema. The new format is intentionally rejected by that code.

## Preflight Contract

The adapter anchors the original build source/tool manifests, command list, PASS
record, Spike log and original selection to literal reviewed SHA256s. It verifies
all compiler/runtime/C/header inputs, Spike/compiler tools, original DUT/Spike
ELFs, own builder/helper/audit/finalizer/test/adapter files, and frozen RTL pins.
New admission manifests bind the adapter/producer/test/documentation files too.
All checked hashes enter `proof.files`, then the normal checked plan's freeze map.

The hashed source of **build_gap37_csr.py**, not the old gap35 checker and not a
cached bytecode file, is imported without executing main. Its strict validator is
replayed against the original Spike log and fixed ELF stub coordinate: all 52
phases, encodings, privileges, legal/illegal results, rd, cause, EPC and TVAL,
626 checks, 7 illegal, 45 legal, zero failures. Counters and renamed cases are
rejected. Reading the original all-source manifest does not admit its counter case.

## Runtime Contract

The frozen DUT ELF has no `G35_TRACE`; **do not require PROBE lines on VCS UART**.
No rebuilding or UART-only instrumentation is needed. `validate_runtime_log(text)`
requires exactly one line:

```text
gap37_csr_alias_tvm phases=52 checks=626 illegal=7 legal=45 failures=0
PASSED: gap37_csr_alias_tvm
```

It rejects duplicate/incorrect summaries, missing/extra PASS markers, FAIL/FAILED,
Fatal and Error markers. This is deliberately **not** called a VCS per-phase replay.
The unchanged C selfchecks execute every exact state/trap check; the runtime gate
binds that C, builder/helper and frozen ELF to preflight, then additionally requires
the existing strict directed trace audit (`require_complete`, `require_trace`),
matching artifact and binary/image metadata, VALID nonempty retirement trace and
independent PASS outcome. No vector/full-match requirement is fabricated for this
scalar directed case. No new RVFI value oracle or observed-value calibration.

The parent calls the runtime hook only after its normal worker/audit has passed:

```python
if row["status"] == "PASS" and row["name"] == csr.NAME:
    extra = csr.runtime_proof(output, plan, row)
    # Parent saves extra to a new results/<NAME>/gap37_csr_runtime_audit.json.
    # Merge extra["files"] AND that report's hash into row["files"].
```

Any exception must downgrade/block the case before PASS publication and coverage
collection, preserving the first failure. The parent summarizer must require the
runtime report's PASS/schema, bound report hash, and `full.check(extra["files"])`.
This module does not publish outcomes or alter queues. Both worker and summary
gates are necessary; installing only `precheck` is not full runtime admission.

`runtime_proof` returns artifact-bound `files` including VCS log, summary,
inputs/input.elf, generic audit, commit_trace.csv, trace_summary.json, frozen ELF,
composed selection and checked preflight sources. It permits a newer top-level
baseline while requiring all CSR precheck pins to remain in `plan["files"]`.

## Local Checks

```sh
python3 -B -m unittest verification.tests.test_gap37_csr_admission -v
python3 -B verification/tests/prepare_gap37_csr_admission.py
```

The producer is one-shot and uses new files; do not rerun over an existing delivery.
Tests use temporary generated manifests/artifacts; they never modify original
sources, builds or logs. Runtime fixtures are synthetic rejection/contract tests,
not a DUT PASS claim. Actual gap37 runtime validation remains pending parent VCS.
