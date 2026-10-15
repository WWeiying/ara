# SpMV indexed-operand lifetime fix

## Scope and result

The SpMV failure in the frozen paper Base and Full configurations is an indexed-memory protocol defect shared by both configurations, not a failure exclusive to the RCE. The correction changes `lane_sequencer.sv` and `addrgen.sv`. It does not change the benchmark, reduction arithmetic, reference results, scheduling eligibility, or architectural dependencies.

The S/M/L SpMV executables that previously stopped making progress now complete and pass all row-result checks in both configurations. Each pair uses the same original ELF, the same inputs and the same cycle-measurement region. These are simulation cycles, not measured execution time at a synthesized frequency.

| Scale | Rows | Nonzeros | Base + fix | Full + fix | Base/Full cycle ratio |
|---|---:|---:|---:|---:|---:|
| S | 64 | 255 | 7371 | 6489 | 1.136 |
| M | 128 | 1023 | 16768 | 14908 | 1.125 |
| L | 256 | 4088 | 50073 | 44313 | 1.130 |

The ordered-index, LMUL=2 S variant also passes: 7371 Base cycles and 6297 Full cycles. The focused `spmv_indexed_regression` application independently generates its input and reference results, then verifies all 64 rows; it passes in both corrected configurations. `SPMV_SCALES=2/3` enables larger sizes in this regression, but the larger-scale results above come from the original paper ELFs, not those optional builds.

## Cause

An indexed memory instruction processes one index for each vector element. Its index EEW need not equal the loaded/stored data SEW. The lane sequencer already sets the index operand request length to `ceil(VL / NrLanes)`, counting index elements, including the common last packet required by the shared Lane interface.

However, the request inherited `scale_vl` from the memory instruction. The operand requester then treated that element count as a data-byte length and converted it from data SEW to index EEW a second time. For SpMV, data SEW is 64 and index EEW is 32. At VL=5 with four Lanes, the intended request is two index elements per Lane, but the old request becomes four. At the opposite width ratio the same mistake can request too few indices.

The address generator consumes only the architecturally required VL indices. It can therefore finish while surplus index operands and their command remain in the Lane queues. The shared SLDU/ADDRGEN egress selector cannot retire the index command, and a subsequent reduction cannot access that egress. This is why the symptom appears to be a reduction that never finishes.

A 5000-cycle watchdog and a separate UCLI snapshot established the failing state in the old Full build:

- The fifth SpMV row has VL=5; earlier rows have completed.
- The only globally in-flight vector instruction is `VFREDUSUM`.
- Both address-generation state machines are idle and their remaining-byte count is zero.
- All four Lane egress selectors still select `ADDRGEN`; their index operand queues remain valid, with no command-pop event.
- The index-address spill register still holds an invalid/unknown extra address.

Base produces the same watchdog signature. Earlier buffered trace tails were insufficient to identify the exact failing row; the watchdog flush and UCLI snapshot supersede that preliminary interpretation.

## Correction

1. Set `scale_vl=0` specifically for the indexed load and indexed store **index operand** requests. Their length is already in index elements. Preserve the existing length rounding, data-store requests, dependencies, and all other operand conversions.
2. In `ADDRGEN_IDX_OP`, allow index consumption only while `idx_op_cnt_q != 0`. The final address can remain in the spill buffer while the downstream address transaction completes. That interval must not admit another index or underflow the counter.

The second change closes the over-consumption path exposed by the oversized request. It does not discard an outstanding final address: the existing spill-register valid/ready protocol still delivers that address downstream.

No new support for indexed `vstart > 0` is claimed. That pre-existing boundary is unchanged.

## Verification and provenance

Evidence is under `hardware/build/rce/spmv_debug_v1/`. The parent simulators and all source-file hashes in their manifests were checked before evaluating the correction:

- Base: `hardware/build/rce/paper_iv_cumulative_v1/base_commit_build`.
- Full: `hardware/build/rce/paper_iscas_v2/full`.
- Corrected builds: `spmv_debug_v1/base_fixed` and `full_fixed`.
- Original failing snapshots: `watch_base`, `watch_full`, and `ucli/probe2.log`.
- Successful paper workloads: `base_test`, `full_test`, `base_sizes`, `full_sizes` (check individual test entries; these directories also contain separate regression attempts).
- Focused committed regression: `base_spmv_reg` and `full_spmv_reg`.

The builds replace only the two corrected modules in the frozen source lists. The working-tree versions of those modules differ from the tested corrected copies only in explanatory comments. Other uncommitted area/synthesis changes in the working tree were not incorporated into these simulations and are not validated by this report.

`indexed_egress_regression` additionally checks indexed loads and stores followed by integer reduction: data SEW and index EEW each range over 8/16/32/64; ordered/unordered accesses and masked/unmasked cases are exercised at requested AVL 1/3/5/7/9/16/17/31. Actual VL follows `vsetvli` and is capped by VLMAX. The 512 checks can be split into 16 width-pair programs (`hardware/scripts/build_indexed_egress_shards.py`; recorded run: `full_split_reg`) to avoid a long serial run. All 16 sharded programs passed in the corrected frozen Full configuration, covering 512 checks. Their results are recorded in `spmv_indexed_deadlock_fix_evidence.json`. An interrupted monolithic run is not counted as a pass.

## Separate historical Base limitation

The expanded regression exposes another short-vector failure in the historical Base configuration. It occurs both before and after this patch. At its watchdog snapshot, `VLXE` and `VMERGE` remain in flight, the address generator is still active, and there are no valid index operands. This differs from the completed-address-generator/stale-egress state of the SpMV defect.

Removing the integer reduction from that expanded test still reproduces the Base stall. It must therefore not be attributed to reduction arithmetic from the instruction list alone. The reproducer includes short index accesses and mask/ordinary-vector setup. Its exact root cause remains open; the evidence is preserved in `base_old_reg_watch`, `base_reg_watch`, `base_memory_watch`, and `ucli/base_reg2.log`. No timeout or interrupted run is reported as successful. The passing SpMV workloads do not certify every historical Base instruction combination.
