# Original473 Gap Expansion

User direction on 2026-09-28 supersedes the repair-regression campaign:
the repair service was stopped, with its output preserved. This exploration
uses only the original pre-segment-VL0-repair image and compatible coverage.
The live approved RTL fix is not reverted, compiled, or claimed as verified.

## Running Service

`ara-original473-gap28-20260928-01.service` runs
`queue_other_gap_exploration.py` in the sole signoff worktree.

- Image: `verification/out/repair-closure-coverage-20260927-01/sim/simv`.
- Baseline: `verification/out/vcs-memory-gap-20260928-01`, 473 PASS and 12 TIMEOUT.
- New selection: `verification/tests/rvv_queue_gap28_selection.json`, 36 tests.
- Curie readiness/input pins: `verification/tests/rvv_queue_gap28_ready.json`.
- Output: `verification/out/vcs-original473-gap28-20260928-01`.
- Queue/source archive: same output name with `-queue` appended.
- Service log: same output name with `.service.log` appended.

All 485 old outcomes remain evidence, but only their 473 checked PASS VDBs
enter DVE. The 12 known old timeouts are not rerun or counted as coverage.
36 new tests run with eight workers, a 300-second simulation budget, and the
existing exploration scheduler's global lock. Ordinary FAIL/TIMEOUT evidence
is retained and dispatch continues. Infrastructure, checker, and identity
failures stop dispatch. No serial repair gate, RTL build, retry, or URG is used.
Final DVE merges compatible old PASS and independently audited new PASS only.
The result ledger has 521 entries and at most 509 PASS.

## Historical Source Validation

The unchanged baseline plan pins dispatcher SHA256
`30681ec394e7cb4104b4803cbf6d3d8b0d003bbe0db07512cb0b1197dc7e4f78`.
The live patched dispatcher has a different hash. Rechecking live RTL as if
it were the old compiled image would be incorrect.

`archive_original_coverage_sources.py` creates an explicit archive of all 458
original manifest inputs. Unchanged files are copied exactly. Only the
dispatcher requires reconstruction: removing precisely the reviewed eight-line
no-op reservation block from an in-memory copy gives the exact original
build-manifest hash. The live file is never written. Any additional mismatch
or non-identical reconstructed hash rejects preparation.

Each archive entry records original path, original SHA256, archived path,
capture-time live SHA256, and copy/reconstruction method. Validation requires
the complete archived inventory to equal the original manifest, every archived
byte hash to match, and the immutable simulator/runtime image hashes to match.
The existing baseline plan, source manifest, checker, and prior outcomes are
not modified. In this new entry point only, historical source pins resolve to
those exact archived bytes; unrelated tool, ELF, outcome, and VDB pins retain
their original checks. The validator accepts only the designated original
manifest and never recollects current RTL for the historical-image claim.

Existing extension APIs freeze the new selection and reuse audited compatible
outcomes. Existing workers retain selfcheck, independent trace audit, runtime
image/ELF identity checks, and strict VDB admission. The DVE input list and
before/after VDB hashes are checked. Plans and collection metadata explicitly
say `ORIGINAL_PRE_SEGMENT_VL0_REPAIR_IMAGE`, `current_rtl_claim=false`, and
`repaired_vdb_reuse=false`. This is old-version coverage, not repaired-RTL
signoff. No repaired-image VDB can enter this merge.

## Status

```sh
systemctl --user status ara-original473-gap28-20260928-01.service --no-pager
cat verification/out/vcs-original473-gap28-20260928-01-queue/status.json
```

After preparation, read `checkpoint.json` and `scheduler/status.json` inside
the output. Final PASS-only evidence is `collection.json`, `dve-inputs.txt`,
and `dve/summary_waived.csv` alongside the raw summary. Keep frozen Curie
sources, binaries, helpers, and READY pins unchanged until completion.
