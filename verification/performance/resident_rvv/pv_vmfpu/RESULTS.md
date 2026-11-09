# Actual VMFPU ownership gate: accepted results

Date: 2026-11-08. Scope: lane-local resident PV arithmetic and native/private
ownership, using host VCS. No synthesis or FPGA run was performed.

## Production changes

`hardware/src/lane/vmfpu.sv` adds a default-disabled `EnableResidentPv` interface
around its existing `i_fpnew_bulk`. Acquisition requires native queues, results,
reduction traffic, arithmetic and flags to drain. Native offers have priority.
During ownership, private FP16 FMA operands and retained slot tags select the
existing FPU; private results cannot enter native consumers. Release waits for
actual arithmetic/output drain. It does not use a fixed latency or flush.

`hardware/src/lane/vector_fus_stage.sv` explicitly ties this interface inactive.
Thus the production SoC still cannot execute the resident operation. With the
parameter zero, owner is constant zero and the added muxes/gates reduce to the
original native connections. This is a static argument, not a synthesis report
or a replacement for later SoC regressions.

No AXI/DDR interface, lane count, FPU latency selection, QBS operation, instruction
encoding, SDK or llama.cpp backend was changed in this step. The PV controller
remains the previously validated verification prototype. The extra original
VMFPU in the testbench is a reference instance, not added production hardware.

## Accepted runs

Root: `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/`.

| Check | `resident_pv_vmfpu_20261108_04` | `resident_pv_vmfpu_20261108_05` |
| --- | ---: | ---: |
| Existing FMA configuration | `SharedFma=0` | `SharedFma=1` |
| Final state | PASS | PASS |
| PV cases | 899 | 899 |
| Real-model operand cases, included above | 12 | 12 |
| Accepted private FMA beats | 85533 | 85533 |
| Returned private FMA beats | 85532 | 85532 |
| Deliberately reset-cancelled beats | 1 | 1 |
| Acknowledged PV result words | 4465 | 4465 |
| Checked native instruction completions | 4382 | 4382 |
| Native accepted / reset-cancelled | 4384 / 2 | 4383 / 1 |
| Ownership acquisitions / releases / resets | 877 / 874 / 3 | 877 / 874 / 3 |
| Native/acquire collisions | 3510 | 3507 |
| Native writeback stall cycles | 13146 | 13146 |
| Native exceptional-flag events | 877 | 877 |

The 899 cases executed under two configurations are 1798 executions, not 1798
unique cases. The corpus contains normal, invalid-command, malformed-packet,
reset and precommit-abort cases. Each active private FMA input, result, mask,
rounding mode, flag and final accumulator write is checked against independent
SoftFloat-derived records. Actual FPU returns are stalled and reordered by the
test harness, rather than replaced with precomputed outputs.

Native probes exercise exact FP16 FMA, multiply, divide, and maximum with an
sNaN, plus deferred multiply after owner release. Each native result, accepted
flag update, completion and writeback timing is compared to the frozen original
VMFPU. The candidate also checks zero flag data while invalid in these tested
traces. Native acquisition collisions, private backpressure, reset cancellation
and final ownership drain have explicit accounting. The native probes are not
full ISA, comparison, reduction or multilaned architectural coverage.

Both runs use identical candidate RTL, adapter and corpus. The parent separately
rechecked both raw logs, all recorded artifact hashes, source pins, image hashes,
case records and native/private conservation. No throughput or model speedup is
derived from these randomized-stall testbench cycle totals.

## Evidence identity

| Artifact | SHA256 |
| --- | --- |
| Candidate `vmfpu.sv` | `bca69c9dff37b3b0da7750d54fdbf4153aea030e6f775ac9a66c75be71e4fb99` |
| Test adapter | `04b69d17f0458a194d0b7880b12c74adc7fa22b5b4d67031faca458ead762c99` |
| Accepted corpus `vectors.txt` | `223a8fa9cbc1ccb14a6cafc593fdc681fabb1d40188701bf1625d96d6111ff60` |
| Run 04 `report.json` | `e961b8b23dbbd3dd1df76e9f949dd330cbd3f41033059b5d7400e4a5ae5c1207` |
| Run 05 `report.json` | `01ed0d7f0ca229a4a28f72e7a994e716e61c7c5f3f62db4c9b16e4352da76854` |

The frozen baseline manifest referenced a build helper later updated in Git.
The new gate reconstructs that helper from recorded revision
`640862d2d0fdb209e4a0a2412c317e1d9bd68928`, checks its original digest, and records
the current-path mismatch explicitly. It does not execute that helper or rewrite
the original receipt. RTL and dependency pin mismatches remain fatal. See each
run's `historical-provenance.json` and `source-selection.json`.

## Failures retained and resolved

- Run 01: compilation included SoC testbench global functions referring to
  `ara_tb`; that top is absent in this standalone gate. Only SoC testbench files
  were removed from the derived list. RTL and dependencies stayed pinned.
- Run 02: the adapter relied on an unelaborated user configuration as a hardware
  configuration. The native divider consequently had zero transaction-ID width.
  The adapter now uses `build_config_pkg::build_config`, as the SoC does, and
  asserts legal XLEN/ID width. This was a test instantiation error.
- Run 03: all 899 original case checks passed, but the independent adapter
  counted 85534 private accepts versus the checker's 85533. The reset driver
  waited for an extra negedge after the checker recorded its cancellation count,
  allowing one unchecked posedge/FMA. The derived bench removes only that entry
  wait; runtime reset calls already occur at negedge. The initial reset hold and
  all numerical/conservation checks remain. Runs 04/05 close the discrepancy.

No failure above was closed by relaxing a comparison, increasing a timeout or
changing the workload. No original failed report was relabeled PASS. Review of
potential invalid-flag leakage prompted a stricter test; the tested traces passed
without an additional RTL flag patch. That review concern is not a confirmed
production bug.

Host checks: 11 runner tests pass, including exact derived-bench reversibility,
module labels, file-list selection, pin-drift rejection and count conservation;
the 16 existing PV generator/extraction tests also pass.

## Next gate

Complete the parent obligations in `SOC_INTEGRATION.md`: upstream pulse/operand
drain, separate source geometry and reshuffle bounds, mode-qualified resident
payload delivery, all-lane irreversible commit, generated ABI and FP/CSR rules.
Then compare complete real-model attention calls against the accepted
rotation-and-loop software control, including preparation/import/drain costs.
Only measured cross-shape benefit justifies enabling the runtime path. QK and
llama.cpp integration remain pending; this endpoint gate does not complete the
overall resident-execution goal.
