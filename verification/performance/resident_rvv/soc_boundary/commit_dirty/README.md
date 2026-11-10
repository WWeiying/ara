# ACCEL Dirty-State Candidate

This successor preserves the original boundary FAIL and every old checker. It
does not edit shared dependencies. The registered, reviewable
`accel_dirty_retirement.patch` changes only the ACCEL/vfp dirty-state term in
the complete locked CVA6 `commit_stage.sv`. It requires actual commit ACK, no
drop and no entry exception. Native-FP dirty and fflags logic is byte-identical.

The locked dependency revision is `b29fd3cf906e7f4c71da4c2f46451c4c60a4487f`.
The exact preimage is
`bf59bfa36960ec6227cb49d86e60f8b8f9507590f64ecfafffa9d8d8f94abb60`.
The preparation receipt `overlay.json` registers patch SHA and postimage SHA.
This is a candidate overlay, not automatic registration in any FPGA exporter.
The existing exporter emits `cva6_local.patch` from its chosen checkout; it will
not discover this candidate automatically.

For an explicitly reviewed successor SoC build, call
`run.apply_to_snapshot(fresh_source_root)` **after** copying the frozen sources,
before closing include/source pins. It modifies only
`hardware/deps/cva6/core/commit_stage.sv`, rejects the shared worktree and old
SOC03, rejects unknown/already-patched bytes, checks and applies the registered
patch, and returns the exact before/after/patch identity record. The caller must
pin the patch/helper, original preimage and patched target in its new receipt.
Do not relabel current HEAD as the old image or modify old source-pins. A new
SoC image must still run the unchanged strict 21-case/33-attempt boundary oracle.

The component test instantiates complete original and patched commit stages
against the real frozen packages, with two commit ports and both WT/WB cache
configurations. It covers 36 directed
observations including stale-invalid, held/halt, store/flush stalls, exceptions,
exception ACK-on-drop, cancellation, actual ACCEL retirement, native FP on both
ports, native read-only operations and exact fflags union. All non-dirty outputs
must equal the original (72 observations). Eleven WT and twelve WB observations
must reproduce the original dirty defect and be clean in the candidate.
Existing native-FP ACK-on-drop dirty
behavior is intentionally preserved, not newly accepted as architectural proof.
`flush_dcache` can accompany real retirement and must not indiscriminately
suppress dirty. It waits for pending stores only in WB, not the historical
SoC's WT configuration. There is no generic external flush input to this module;
scoreboard flush is represented by invalid entries retaining stale classification.

Historical inputs are the SOC03 frozen source and image, plus original FAIL log
and real CSR retirement data. Live production RTL is not an execution pin.
The original id16 before-FS-Off / trap-FS-Dirty sequence occurs before handler
FCSR reads. This component run is not a corrected SoC or full-boundary PASS.

```sh
python3 -B verification/performance/resident_rvv/soc_boundary/commit_dirty/test_run.py
python3 -B verification/performance/resident_rvv/soc_boundary/commit_dirty/run.py prepare --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_commit_dirty_20261110_01
```

Launch the resulting `inputs/test/run.py exec --output ...` as the direct
systemd service owner, with stdout/stderr files. Worker deadline is 300 seconds;
service deadline is 420 seconds. No SoC simulation, synthesis or FPGA run.
