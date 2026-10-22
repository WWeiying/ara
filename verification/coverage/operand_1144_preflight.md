# Operand 1144 Offline Binding Preflight

This is a diagnostic evidence seal and capture input plan, not an exclusion
receipt, corpus application, native-format qualification, or launch approval.
No historical receipt, RTL, frozen helper, or original replay checker is changed.

## Reproduce

Run from the integration repository root:

```sh
python3 -B -m unittest discover -s verification/coverage -p test_seal_operand_1144_preflight.py -v
python3 -B verification/coverage/seal_operand_1144_preflight.py --verify verification/out/operand-1144-binding-689-preflight-20261006-02 --seal 8bde8a159443af197b876b9c035c59e1a5b69bd8103c093e796c64e1d2abb596
```

The external manifest seal above binds `evidence.json` and `capture-plan.json`.
Verification rehashes all pinned inputs, rereads all 689 raw branch files,
reconstructs the per-scope union and definition bindings, and compares the
complete regenerated documents. A changed source, helper, test, tool, input,
capture directory membership, or selected hit fails verification. The initial
`...-01` output preceded capture input/tool additions; use only `...-02` with
the final tool version.

## Binding

The accepted coordinates and source expectations come from the fixed GAP56
manifest seal. Operand queue, operand queue stage, and Ara package bytes must
match both historical review pins and old-image build pins. Design and branch
shape must match the historical review and the 689 raw-union cache.

All 36 scopes bind through compiled Design ownership to `operand_queue`
source checksum `1532764271`, then to one branch definition with checksum
`1417162425` and width 101. Missing per-instance checksums do not qualify by
themselves: the definition ID must uniquely match that scope's source owner.
Generated LZC children are different owners/definitions, not replacement scopes.

Each accepted raw index, vector, spec checksum, and constant-proof demand is
checked against the compiled shape. The script does not independently derive
new reachability proofs; it binds the existing sealed static proof. The 1269
retained coordinates remain retained, not asserted reachable or waived.

## Capture Boundary

`capture-plan.json` prepares all 1144 exact selectors across 36 scopes, including
their full sealed review records. It pins the old Design VDB and one explicit
seed1417 test VDB, with exact directory membership. All 2492 unselected branch
vectors are protected, including 1269 retained and 16 previously reviewed
coordinates. The isolated format capture must start and end globally empty;
previously reviewed points are not imported into this session.

Host tool preparation seals the wrapper, xvfb-run, architecture selector and
DVE ELF, but does not inventory shared libraries or qualify a live process.
No runner/Tcl implementation is delivered here (`runner_prepared=false`).
Before any reviewed launch, a runner must integrate controlled environment,
fresh tool revalidation, and launch-bound live executable verification.

The required capture is export/reset/import/export with strictly 1144 records,
full native header/directive/signature equality, one selected test, three empty
states, and singleton vector exclusion queries for protection audits. Unknown
native signatures are not synthesized from shape. The old 18-point pilot does
not substitute for capturing the remaining signatures. A passing offline
preflight alone must never start DVE or authorize application.

## First Actual Capture

The independent `capture_operand_1144.py` and Tcl capture were implemented;
nine tests passed. Actual prepare sealed config
`82a7b92ccf8906db8326a3e25000dc5b5869311dc4bfbe3de8b4dcb563815e48`.
The managed service `ara-operand-native-1144-capture-20261006-01.service`
terminated FAILED. Preserve its output in
`verification/out/operand-native-1144-capture-20261006-01/`.

The live DVE executable identity gate passed. The Tcl log then reported that
`op1144_keys(scope)` did not exist: sourcing the selection inside a procedure
without declaring this array global created a local array. This is a capture
environment failure, not a processor test or an unreachable-point proof failure.
It occurred before exclusion selection; the initial and final exclusion files
are empty. No first/second roundtrip files exist and neither the 1144 targets
nor the 2492 protected leaves were qualified by this attempt.

Retry requires an independently pinned fixed hook, a real Tcl scope regression,
and a fresh output directory. Do not overwrite the failed output or issue an
application receipt from this attempt.

The independently versioned v2 attempt in
`verification/out/operand-native-1144-capture-20261006-02/` also terminated
before capture. It fixed array scope but DVE resolved `[info script]` relative
to the output directory, so the frozen v1 helper was not loaded. The GUI log
records EK-CMD-015 and missing `op1144_require`/audit/save procedures. This
is another environment rejection; no native qualification was produced.
The next retry must bind an explicit absolute helper path and prove helper
procedures exist before entering the capture session. Both failures stay
preserved; a standard Tcl scope test alone did not reproduce DVE's loading
context and was insufficient for launch validation.

## Verified Native Capture

The v3 hook supplies an absolute, pinned helper path and checks all required
procedures before capture. Its 13 unit tests passed. The managed third service
terminated successfully; artifacts are in
`verification/out/operand-native-1144-capture-20261006-03-ready/`.
The sibling directory ending in `-03/` is preparation only, not this result.

An independent parent verification reran `config_read()` with the external seal
`720329af55eaa0995c65016af5560f8a071c14b5ed213099e8012f7a22a8de8a`
and `verify_artifacts()` against the actual files. Both checks passed:

- Exactly 1144 native records match the source-bound target identities in both
  exports; roundtrip comparison uses parsed records, not identical file hashes.
- All 2492 protected branch points retain their required exclusion states.
- Five stages contain 18180 singleton queries in total.
- Initial, reset and final exclusion files are empty.
- The launch-bound executable identity, successful process exit and before/after
  input integrity evidence match the sealed configuration.

This is a one-test native capture, not an application approval or a 690-test
coverage report. Independent reachability/signature review and a compatible
full-population application remain necessary before reporting waived coverage.
The two earlier failed attempts remain preserved. No processor RTL, original
VDB or historical FAIL result was changed.

## Full Historical690 Application

Independent source/native qualification was completed in
`verification/out/operand-native-static-qualification-690-20261006-01/`.
The first application attempt failed before exclusions: serialized Tcl paths
retained literal braces in DVE's load API. The successful raw690 report used
the same actual VDBs, distinguishing a loader error from database corruption.
The failed directory remains preserved.

The independently pinned v2 driver rebuilds canonical path lists before the
load API and requires the successful load gate. Its second application is in
`verification/out/operand-exact1144-application-690-20261006-02/`, externally
sealed config `0e6823417d483e68abd19ac31aef915c8d9ceb18315efa6860600034bf7231c3`.
The parent independently reran `read_config()` and `verify_artifacts()`:
exact690 selected tests, exact1144 new exclusions, all2492 protected points,
unchanged evidence pins and final reset all passed. The prior16 exclusions were
not automatically imported. Raw and reset summaries are identical.

The actual top `ara_tb` Branch column is 77.59% raw and 78.43% applied.
However, child `i_system` and `i_ara` columns still display their raw values.
This hierarchy-display behavior remains under investigation, also seen in the
separate LZC application. Do not substitute the top-level increase for child
coverage, infer denominators or label this the692-test report. The file is an
exact690 application artifact, not current RTL signoff or an automatic policy
for future builds.
