# Current NaN / Minmax Independent Review

Date: 2026-10-12. Read-only RTL/evidence review; no build, Host/Spike test,
DUT simulation, live-process query, or change to existing artifacts.

## Conclusion

1. **VFREDMAX narrowing collision is repaired, with measured coverage.**
   The historical `mode10` here is binary `cvt_resize=2'b10`, not decimal
   scenario10. Current min/max module tests exercise this encoding. There is
   no evidence from this review that the old narrowing defect remains.
2. **All-off seed preservation is repaired and measured on identical current
   VMFPU/operand-queue RTL**, including exact sNaN payload and zero exceptions
   at FP16/32/64. Activity ownership has additional consecutive-operation
   tests. This is stronger than merely finding the bypass in source.
3. **Active all-NaN min/max has the corrective qNaN neutral values in current
   RTL, but direct current-version measured acceptance was not established
   in the reviewed suites.** An all-off NaN test is not this test. This is
   an evidence gap, not a newly observed DUT failure or proven remaining root.

`CURRENT_REPAIRS.md:22-23` and `CURRENT_SCOPE.md:239` describe ordered flags
and unordered activity repairs. Neither the ordered166 nor original RVV-07
op0 single-scope passes establish min/max all-NaN acceptance. Original op1/op2
helpers being present in those ELFs does not mean they were invoked.

## Current RTL And Historical Causes

All references below are in this integration tree and refer to the reviewed
current file, not line numbers in an older snapshot.

| Problem | Current implementation / exact references | Assessment |
| --- | --- | --- |
| VFREDMAX interpreted as narrowing | `hardware/src/ara_dispatcher.sv:3418-3421` still emits binary10. `hardware/src/lane/vmfpu.sv:304-310` excludes the complete FP-reduction opcode range from `narrowing`. Its functional call sites at1892/1895/1904/1913/2025/2035/2049/2064 pass both opcode and resize. Format selection at1157-1196 also qualifies conversion by operation. | Old cause was shared neutral/conversion encoding, not min/max arithmetic. The guard predates this campaign; it is not a new M6 repair. |
| Active all-NaN becomes infinity | `vmfpu.sv:1128-1151` uses canonical qNaNs for both min/max neutral operands; `processed_red_operand` at749-752 substitutes them for inactive/tail inputs, consumed at2184-2185. `hardware/src/lane/operand_queue.sv:287/293/300` supplies qNaN for both neutral encodings at FP16/32/64, including seed/empty-lane padding. | An infinity is not a neutral operand when all real operands are NaN: minimum/maximumNumber can select that numerical infinity. Both current fill sites use qNaN, so this old static cause is absent. No newly proven residual cause. |
| All-off canonicalizes seed or raises NV | `vmfpu.sv:2118-2121` derives activity from actual source count/predicate, not arithmetic-fill BE;2266-2274 captures seed and accumulates activity. `hardware/src/ara.sv:455-457` ORs lane activity. VMFPU2631-2634 snapshots that epoch at accepted first tree return;2658-2661 bypasses only architectural writeback for empty reductions. Flags1590-1603 are retained then gated by that same epoch. | qNaN filling alone cannot preserve arbitrary seed payload. The exact-seed bypass and delayed flag qualification are essential. Current epoch snapshot avoids a younger reduction changing an older reduction's decision. |

Current SHA256:

- VMFPU: `e9b8c8c2aa952b76661b01fa0a4b53d87e2f1d7219beb40a42a4d6998c5f7b12`
- operand_queue: `eafc82bfe3bd7413aa549015a2145e977d1ce01a9bd52c369993e5dac10e453d`

## Actual Existing Measurements

Primary current-version evidence:
`/home/wangwy/fpga_runs/reduction_epoch_unit_20261010/preserve80/`.
Read `status.json`, all80 `results.csv` rows, retained test/source definitions,
and terminal console. Status is `PASS_REDUCED_RTL`, failures empty; console
ends `REDUCTION_COMPLETE cases=80` and normal VCS `$finish`.
All59 retained pins were rehashed; all55 hardware inputs that exist in the
current tree match exactly, including VMFPU, operand_queue and FPnew inputs.

| Actual CSV IDs / names | Actual result / flags | Scope |
| --- | --- | --- |
| 9/12 min/max_all_masked_snan_seed | `7ff0000000000001 / 00`, exact expected | FP64, VL65, mask0; raw seed preserved |
| 64/66 alloff_fp16_op2/op3 | `7c01 / 00` | FP16 min/max, exact sNaN payload |
| 70/72 alloff_fp32_op2/op3 | `7f800001 / 00` | FP32 min/max, exact sNaN payload |
| 76/78 alloff_fp64_op2/op3 | `7ff0000000000001 / 00` | FP64 min/max, delayed operand delivery |
| 65/67,71/73,77/79 remote_fp{16,32,64}_op{2,3} | finite2.0 / `10` | Active remote finite source with sNaN seed: bypass must not occur, NV must occur |
| 11/14 min_finite/max_finite | `4000000000000000 / 00` | Finite control |

The retained `reduction_tb.sv:304-315` explicitly drives VFREDMAX resize2 and
operand-queue neutral2. Thus these are real current-RTL binary10 tests, not
tests silently avoiding the collision. They use real operand queues,
VMFPU/FPnew and modeled predicate/SLDU transport, not a whole-SoC run.

`reduction_epoch_unit_20261010/after1-02`, `after2-02`, `after4-02` each record
`PASS_EPOCH_UNIT`,144 cases, zero failures and this same VMFPU SHA. They cover
consecutive sum/min/max activity transitions with seed sNaNs, finite active
sources and delayed grants. They do **not** contain active all-NaN sources.

Older whole-SoC evidence, not relabeled current-image acceptance:
`verification/out/integrated-rvv-reductions-20260925-01/summary.csv` records
vfredmin PASS/rc0/77.392962s and vfredmax PASS/rc0/88.651072s.
`verification/RVV1_DIFFERENTIAL_VALIDATION.md:3993-4055` records the original
VFREDMAX FP32 -15/+15, VL4/VL1 failure and boundary repair. Its referenced
`verification/out/vfredmax_boundary_fix_20260922_002206` is absent here, so
that direct-exit artifact was not independently rechecked. Section25.2 at1264
records the historical all-off seed `fffeedec -> 7fc00000` and repaired seed3/5
traces; those historical trace summaries are not a fresh current-RTL replay.

Evidence hashes (preserve80):

- status.json: `f90c9a33b158dac0c45ff1e4bdd085170a1c70eddecaef17e4a7c080bb29d661`
- results.csv: `858700b6a9f1e1eaea28e748b739518f0003637128b809caf7ff5a46a60a55df`
- pins.json: `0a37eb956d47d1837e167a8aea22854730a3b16a878b782aaea5d0aaf345f7fb`
- run.console.log: `ed7575adb42afb5ae54e3a3f8a751b9f7c0f0a7273b10baa43f240946b8febf0`

## One Discriminating Source Case For The Remaining Evidence Gap

This is an **authentic archived configuration**, not a demonstrated current
counterexample, and no execution is requested by this report. Do not repeat
the already-passing all-off matrix to answer active all-NaN behavior.

Archive base:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_fp_redspecial03`.
Original `overlay/opt/ara-tests/rvv_fp_redspecial_e32_m1` SHA, independently
hashed and matching manifest:
`6bdf00a1600f10ebfc7a8b519bfea655d31e6b6b2b62d89f9e459d266eb597bc`.

Select original zero-based call1294: scenario1, VL3, mask mode3 (`0x24`),
frm0, op2 VFREDMAX, sticky0; cap32 at VLEN1024, vstart0. All input elements
and seed are `0x7fc12345`; only source element2 is active. Original fixture
index647 independently reads `[0x7fc00000,0]`. Require canonical result,
fflags0, returned vstart0, and all remaining bytes of the original144-byte
output/guard oracle unchanged (`0x5b`). Noncanonical seed deliberately
distinguishes correct active reduction from an erroneous empty-set bypass.
Sparse VL3 also exercises empty lanes/padding and binary10 without a long
matrix. A selected call omits1294 predecessors and is not full-parent closure.

Archived `e32/m1/operations.S` SHA:
`64859679b372c4ab1f57e7c81d27af03eb41b727314fdf764e0bd342a9d68818`;
retain its complete21-instruction op2 helper and full source oracle.
Archived fixture SHA:
`59bd5276e2306391784b16263818f725424392421bebc355b1db6c25cbebd53a`.
The original oracle, input-generation header, fixture C, reductions generator
and special generator still match manifest hashes. `floating.py` does not;
use archived `e32/input_bits.h`, not regenerated current floating tables.
Archive `reference_1024.json` is explicitly QEMU reference, **not DUT**.

Minimal observations if this gap is later tested: accepted opcode/resize/SEW,
`narrowing(...)`, queue `ntr_red` and accepted seed/source words; per-lane
`source_element_cnt`, `source_be`, `mask_i`, `intra_op_rx_cnt_q`; FPnew
operands/result/flags plus valid-ready; `reduction_any_active_q`, global OR,
first accepted SLDU return and `reduction_epoch_any_active_q`; final
`mfpu_result_req_o/gnt_i/id_o/wdata_o/be_o`, and published flags.
Infinity predicts bad neutral injection; unchanged `7fc12345` predicts false
empty-set qualification; `7fc00000`/flags0 with intact tail is the expected
outcome. Do not infer a current hardware defect from the coverage gap alone.
