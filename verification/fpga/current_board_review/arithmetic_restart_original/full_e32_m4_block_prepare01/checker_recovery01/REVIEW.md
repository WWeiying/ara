# Closed-Raw Recovery Accepted: Reference Only

`closed01/complete.json` is **RECOVERY_COMPLETE_REFERENCE_FULL5985_PASS_SOFTWARE_ONLY_NOT_DUT**. The sole recovery audit, PID3429196, returned actual numeric0 in139.632570s, without timeout or retry. The supervising command also returned numeric0 (observed command-completion chunk068a3b). The original Spike execution remains the only execution: PID3424126, numeric0,8.339231s. Original audit1 and STOPPED remain unchanged.

## Exact Scope and Cost

- Full5985 original calls,766080 e32 results,11970 guards,5985 returned-vstart-zero checks; all13 helper positions appear5985 times,77805 total helper instructions.
- Each output is exactly520B,65 whole scalar LD:389025 actual reads and comparisons. Physical group4 spans512B; mask backing128B, actual vlm footprint16B.
- Immutable expected data:124041 LD,53865 ID loads,33123 cache hits and14757 misses including first fills. Per-call reset, tag/operand values and complete actual cache PC paths are checked.
- All1890 FP calls retain15120 fresh LW and483840 ordered A/B SW across all three actual seed paths, including VL0. Original RNG contributes1104 scalar stores.
- Mask lifecycle:2205 groups,35280 full-clear SD and154350 ordered constant SB. There is no inherited LBU requirement.
- Firmware-to-HTIF: **2759763**, below3000000 by240237 instructions. Five boot rows and232 exact post-HTIF pure-park rows produce2760000 actual raw rows; EOF is checked. The finite4M command is a bound, not a claim of4M observed rows.
- Exact original success marker, source/ELF bytes, complete failure-PC veto, input/output freshness, capacity and helper/CSR contexts passed. Original source has no fflags oracle; this result does not claim one.

The new audit parsed the existing305618403-byte raw once. Its SHA remains `4c570d9e9a24d3b0dd2a50dd865c999ac017a8d918efd17b190c30acc941ceee`. All536 prepared pins plus entry and independent review were verified before and after. No Spike, compilation, full Host suite or DUT was rerun.

## Corrected Contract

The FP store classifier now contains the768 actual store PCs from all three compiled seed paths. Classification alone never authorizes a write: the inherited matcher still selects `row.seed` and requires the complete exact event sequence. FP loads already used their source address range plus current-seed exact events; all three paths share the same eight load PCs, with no seed0-only classifier. Seven focused Host tests passed (numeric0,1.171632s), including original ordinals1366/3361/5356, each last b[127], wrong-seed/current-path PC, same-value omission, duplicates, width/bank/value errors, missing LW and RNG separation.

Future VCS use must independently derive these classes from its actual SoC ELF and retain call ownership; this Spike recovery is neither DUT-token validation nor VCS admission. Full source-port e32/m4 acceptance is not Linux replay or acceptance of other shapes.

## Frozen Identities

- Recovery entry: `b3c6347e7b21c9dd036fc5fabc7f9f699c6e643d9f2b6fb5a5f3b77be5e8a060`.
- Hilbert exact-entry NO_BLOCKER: `8df46989c462ea6fa1832e56f2dc0b476dd85adeaa4b1329ea18bf227425c59b`.
- Actual recovery audit receipt: `27a558d624492233a225ea8e209b91521f071097ab053449a1403851c2532d38`.
- Result: `0c889b678ab3a0df9925422139b9eb95f717ec49468d8114e27f91ddfefa9c6b`.
- Complete: `cf6fc263caf017c09303215b55bac810ea94bbf7ea735ea36879981470d7ae4b`.

Invocation: `python -B -u recovery.py execute --review /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/arithmetic_restart_original/full_e32_m4_static_review01/RECOVERY01_ENTRY_REVIEW.json --review-sha 8df46989c462ea6fa1832e56f2dc0b476dd85adeaa4b1329ea18bf227425c59b`.
