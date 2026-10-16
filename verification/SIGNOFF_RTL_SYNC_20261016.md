# Signoff RTL Import

## Scope

Imported source: `ara_dsa_signoff_integration`, frozen commit
`5ee02215edd65967040c837e786b7e1f668fcc36`.
Destination: the existing `ara_dsa` working tree, including its pre-existing
uncommitted fixes. This is not a whole-branch merge.

- All 60 SV/SVH files in `hardware/src` and `hardware/include` now match the
  frozen commit byte for byte. Twelve files needed updates.
- Imported 14 dependency RTL updates: five CVA6, four AXI and five FPnew/C910
  files. Other dependency RTL checked during comparison was already identical.
- `Bender.yml` and `Bender.lock` were already identical and were not rewritten.
- Canonical dependency patches and their digest registry were synchronized.
  The dependency checker accepts all three registered packages as `applied`.
- Added the cache-invalidation collision reproducer, its testbench and checker
  tests. Its historical repair note describes earlier measurements; new results
  are stored separately below.

No FPGA export/package files, board configuration, synthesis runs, bitstreams,
Linux images or running board state were changed. Other user changes remain.
The FPGA package must be regenerated using its existing integration/export flow
and verified separately; raw source identity does not establish FPGA timing or
board correctness. This import does not claim a full SoC/Linux regression pass.

## Checks

```bash
PYTHONPATH=verification python3 -m pytest -q \
  verification/tests/test_signoff_rtl_sync.py \
  verification/tests/test_dependency_patches.py \
  verification/tests/test_wt_inval_collision.py
```

The source identity tests pin the full commit, check the complete main-RTL file
set, compare every byte, check the build lists and lock, and verify that the
approved dependency patches are actually applied. They are not RTL simulation.
All 35 checks in the command above passed after the import.

New focused RTL measurements:

- Cache collision: `verification/out/rtl_absorb_5ee02215_20261016_035834_wt/`.
  All 30 repaired scenarios passed; the original four expected failures were
  reproduced, and one original control passed. Ordinary-read cycle records
  match across variants. Inputs remained unchanged. Inspect `summary.json`,
  `cases.json`, frozen inputs and per-case logs.
- FP16 conversion/mask: 200 transactions with output/input backpressure,
  zero failures. Sources, configuration and result hashes are recorded under
  `/home/wangwy/fpga_runs/rtl_absorb_5ee02215_20261016_035834/fp16_conversion/`.

## Recovery Evidence

Before editing, the 34 replaced/added source, patch and test files were listed
with original and target SHA256 values in
`/home/wangwy/fpga_runs/rtl_absorb_5ee02215_20261016_035834/manifest.json`.
`before.tar.gz` in the same directory preserves all files that already existed.
`after.json` records every main-RTL hash and verifies all 34 imported files
against their target hashes; all comparisons passed.
No automatic rollback or worktree reset is performed.

These changes are uncommitted. Dependency source edits live in their separate
checkouts; the canonical patches and registry preserve the reproducible delta.
