# gap29 FP16 RNE: read-only RTL investigation

## Scope and evidence identity

- Existing run: `verification/out/fp16-rne-current-20260928-01`.
- No RTL or formal test was edited. No simulation was started.
- The old run uses `phase-reset-coverage-20260928-01/sim/simv`.
  Its manifest hashes match the current fpnew sources, VMFPU, dispatcher,
  and sequencer inspected here.
- The subsequently authorized image is
  `verification/out/dispatcher-state-reset-20260928-01/sim/simv`.
  All 457 files in its source manifest matched at inspection time.
  This is source provenance, not a claim that the new image passed this test.
- The archived ELF's `input`, `golden`, `golden_wide`, and `golden_flags`
  bytes match the generated C arrays exactly (readelf `.rodata` inspection).
- `gold_results.txt` is empty. This investigation does not claim an independent
  Spike result from that file.

## Exact first failure

The archived scalar trace does not disassemble these vector instructions
(it prints `INVALID`), but their encodings and the C assembly identify them:

| PC | Encoding | Instruction |
| --- | --- | --- |
| 0x8000024c | 0x488a1857 | `vfncvt.f.f.w v16, v8, v0.t` |
| 0x80000258 | 0x49061c57 | `vfwcvt.f.f.v v24, v16, v0.t` |

Configuration: four Ara lanes, VLEN=1024, e16/m4, tu/mu, frm=RNE,
vstart=0, full VL=65. The 32-bit source has EMUL=8 in v8-v15; the
16-bit destination v16-v19 and widening destination v24-v31 do not overlap it.

`work/trace_hart_0.log:612`: pass 0 reads narrowing fflags at PC
0x80000250, scalar cycle 2169 / 2184 ns: actual **0x07**, expected **0x17**.
The first executed failing comparison is at line 2511, PC 0x8000030e,
5125 ns: `bne s7,s10` compares 0x07 with 0x17. Lines 2512-2513 increment
and store num_failed=1. Thus the first failure is an instruction-level missing
NV flag, not an identified half-precision numerical mismatch.

| Pass | Active VL / predicate | Narrow actual / expected | Wide actual / expected |
| --- | --- | --- | --- |
| 0 | 65 / all | 07 / 17 | XX / 00 |
| 1 | 64 / all | 07 / 17 | 00 / 00 |
| 2 | 65 / even indices | 07 / 17 | XX / 00 |
| 3 | 65 / none | 00 / 00 | 00 / 00 |
| 4 | 1 / all | 00 / 00 | 00 / 00 |
| 5 | 0 / all | 00 / 00 | 00 / 00 |

The corresponding fflags-read trace lines are 612/615, 3014/3017,
5408/5411, 7654/7657, 9729/9732, and 11367/11370.
`XX` denotes unknown hexadecimal digits in the existing four-state trace;
it is not a numeric flag value or proof that all five flag bits are unknown.

All six passes execute 65 half and 65 wide data comparisons; all **780**
compare equal, including masked and tail-preserved elements. This includes
the alternate half comparison at PC 0x800002cc, not just PC 0x800002f4.
The formal expression `flags != expected_flags || wide_flags != 0`
short-circuits on the first term in passes 0-2, so each contributes one
failure and the wide X is not separately counted. `tohost=3` alone does not
provide this diagnosis.

## Inputs and floating-point semantics

Pass 0 values below are both expected and observed in the scalar comparisons:

| Index | FP32 source | FP16 result | Re-widened FP32 | Expected per-element narrowing flags |
| --- | --- | --- | --- | --- |
| 12 | 33000000 | 0000 | 00000000 | 03 |
| 14 | 33000001 | 0001 | 33800000 | 03 |
| 16 | 00000001 | 0000 | 00000000 | 03 |
| 18 | 387fffff | 0400 | 38800000 | 01 |
| 28 | 7fc00001 | 7e00 | 7fc00000 | 00 |
| 29 | 7f800001 | 7e00 | 7fc00000 | 10 |
| 30 | ff800001 | 7e00 | 7fc00000 | 10 |
| 32 | 33800000 | 0001 | 33800000 | 00 |
| 33 | 387fc000 | 03ff | 387fc000 | 00 |
| 34 | 38800000 | 0400 | 38800000 | 00 |
| 64 | 7f800000 | 7c00 | 7f800000 | 00 |

Negative counterparts at indices 13/15/17/19/36/37 also match. Source
0x33000000 is the tie at 2^-25 and rounds to zero; 0x33000001 rounds up to
the minimum half subnormal. Source 0x387fffff rounds to the minimum normal
half, so after-rounding tininess requires NX but not UF. Exact half subnormal
values at indices 32/33 need no flags. Aggregate 0x07 cannot prove that each
individual UF/NX contributor was delivered: other elements can hide a lost flag.

Indices 29 and 30 are the only sNaNs: exponent=255, nonzero fraction,
quiet bit 22=0. Both must contribute NV=0x10; canonicalization to 0x7e00
does not excuse dropping NV. Pass 2 still selects index 30. Widening sees
quiet canonical half NaNs and exactly representable finite half values, so
its expected flags are zero.

Generator/oracle: `verification/tests/generate_rvv_gap29.py:9` and `:53`.
The generator's host-half unit test skips NaNs and compares result bits, not
all flags; it is not alone sufficient to validate exception propagation.
The RTL classifier explicitly detects signalling NaNs at
`hardware/deps/fpnew/src/fpnew_classifier.sv:65`; the cast special path sets
NV from `info_q.is_signalling` at `fpnew_cast_multi.sv:678`.

## Request, execution, and completion path

1. The dispatcher decodes narrowing as VFCVTFF/CVT_NARROW, eew_vs2=EW32
   (`hardware/src/ara_dispatcher.sv:3560`). Widening instead promotes the
   internal destination vsew to EW32 and requests OpQueueAdjustFPCvt (:3519).
2. The VMFPU instruction queue and operand readiness gate issue. Source,
   predicate and remaining-element count determine issue_be. Narrowing
   issues two elements per Ara lane beat and toggles its packing selector
   (`hardware/src/lane/vmfpu.sv:1793`, :1816).
3. Widening's operand queue gathers the two selected half values into the low
   32 bits before CONV (`hardware/src/lane/operand_queue.sv:442`).
4. VMFPU sends F2F with FP32->FP16 or FP16->FP32 into the merged CONV slice.
   Within a 64-bit fpnew instance, these operations use sublanes 0 and 1.
   `lane_is_used` depends on source/destination format, not the element mask
   (`fpnew_opgroup_multifmt_slice.sv:217`).
5. Numerical results and status take different paths. Status is reduced with
   lane_masks (:674); result packing and VRF byte enables can be correct
   while status masking is wrong. VMFPU publishes flags on an accepted FPU
   output (`vmfpu.sv:1545`), then registers flags/valid one cycle later.
6. Result queue/VRF grants decrement commit count and eventually assert
   mfpu_vinsn_done. Dispatcher forwards lane flags; CVA6 ORs accelerator
   flags into FCSR (`csr_regfile.sv:2018`). FP CSR reads wait on queued work,
   backend busy and pending flag updates (`acc_dispatcher.sv:121`).

`vector_trace.csv` reports granted VRF writes, not internal FPU transactions:
source=1 is MFPU, source=4 is VLDU (`operand_requester.sv:176`). Its `be`
is the write byte enable, not a directly measured fpnew exception mask.
Its cycle counter resets with the commit monitor; do not equate it blindly
with the scalar trace cycle counter. Old pass-0 narrow alloc/done are vector
cycles 2144/2165, widening 2178/2199; scalar fflags reads are 2169/2203.

## Primary falsifiable hypothesis: CONV exception-mask layout mismatch

This is strongly supported by static RTL plus the archived architectural
observations, but internal masks/status were not captured in this run.

**Narrowing:** `be(2, EW16)=0x33`, because half element byte starts are
0,4,2,6 (`ara_pkg.sv:472`, :1047). VMFPU samples issue_be[0,2,4,6], giving
`vfpu_simd_mask[3:0]=0101` (`vmfpu.sv:1214`). CONV instead connects
`mask_i=simd_mask_i[lane]` directly (:464), despite slicing FP32 input at
32*lane bits (:223). Actual sublane 1 therefore receives mask=0, although
the second converted element is active. NV generated there is discarded
by `lane_status[i] & {5{lane_masks[i]}}` (:680).

The source writes prove index 29 is the upper FP32 value in Ara lane 1
(`vector_trace.csv:20`, wdata=7f800001c7800000), and index 30 is the upper
value in Ara lane 2 (:21, wdata=ff8000017f800000). Both are fpnew sublane 1,
precisely the masked-out position. Their result bits still become 0x7e00
and are committed. This accounts for missing NV in passes 0, 1, and 2.

**Widening tail:** the internal EW32 single-element tail has
`issue_be=0x0f`, sampled into `vfpu_simd_mask=0011`. CONV sublane 1 is
thus allowed to contribute status although only sublane 0 is architectural.
The old granted tail write is `xxxxxxxx7f800000`, be=0x0f
(`vector_trace.csv:159`; also :481 for pass 2). The high result is not
written, but a wrongly enabled high-sublane status can still contaminate
fflags. VL=64 has no such tail; all-off masking suppresses it. This explains
the X correlation without claiming the trace proves which individual
internal status bit first became X.

Alternatives to discriminate:

- Test/oracle bug: rejected for the observed missing NV by raw sNaN bits,
  matching ELF data, active masks, and the specified classifier semantics.
  No known test bug explains the observed delta 0x10. The test's coarse
  diagnostics and short-circuiting are limitations, not this root cause.
- Classifier/boxing bug: if active sNaN reaches CONV but
  info.is_signalling or raw op_status.NV is zero, the primary mask-loss
  hypothesis is falsified at that boundary. Check is_boxed as well.
- CSR ordering/accumulation bug: if masked CONV status contains NV and it
  reaches VMFPU valid output, but FCSR lacks it, follow dispatcher/CSR
  updates rather than changing rounding logic.
- Stale/invalid status leakage: dispatcher ORs lane flags without per-lane
  valid gating (:1115), while valid is an OR of lane valid bits. Keep this
  as a secondary X-propagation alternative; trace does not prove it caused
  the observed X.

## Minimal bounded signal plan (not run)

For the original ELF, one approximately 2.10-2.25 us FSDB window includes
both conversions and both reads. Time bounds must be re-anchored to the
actual acceptance events on a different image/diagnostic ELF, with a hard
cap of about 200 clocks. Avoid whole-design recursive dumping.

VMFPU hierarchy prefix:
`ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[L].i_lane.i_vfus.i_vmfpu`.
Start with Ara lanes L=2 (index 30 sNaN) and L=0 (widen tail). Observe:

- `vinsn_issue_q.{id,op,cvt_resize,vtype,vl,vstart}`, `issue_cnt_q`,
  `narrowing_select_in_q`, `operand_a`, `mask_i`, `issue_be`,
  `fpu_gen.vfpu_simd_mask`, `vfpu_in_valid`, `vfpu_in_ready`.
- `fp_src_fmt`, `fp_dst_fmt`, `fp_rm` within `fpu_gen`; FPU output
  `vfpu_out_valid`, `vfpu_out_ready`, `vfpu_tag_out`, `vfpu_ex_flag_fn`,
  `vfpu_ex_flag`, `fflags_ex_q`, `fflags_ex_valid_q`.
- In `fpu_gen.i_fpnew_bulk.gen_operation_groups[3].i_opgroup_block.
  gen_merged_slice.i_multifmt_slice`, capture `lane_out_valid`, `lane_masks`,
  `lane_status`, `status_o`, plus sublanes 0/1 `local_operands`, `in_valid`,
  `out_valid`, `op_status`; in their `lane_instance.i_fpnew_cast_multi`,
  capture `src_fmt_q`, `dst_fmt_q2`, `info_q`, `fp_special_status`,
  `fp_status`, `mask_o`, and `status_o`. For the tail-X path add
  `fp_round_sticky_bits`, `uf_after_round`, `of_after_round` only on sublane 1.
- At the boundary capture all four Ara lane `fflags_ex`/`fflags_ex_valid`
  buses, dispatcher `acc_resp_o.{fflags,fflags_valid,fp_csr_busy}`, CVA6
  `fp_csr_access`, `fp_csr_wait`, and CSR `fcsr_q/fcsr_d`, CSR address/op/data
  and accelerator flag input/valid. This separates masking loss from
  downstream accumulation and CSR serialization.

Decisive signature: active sNaN on sublane 1 -> info.signalling=1 ->
raw NV=1 -> returned lane_mask=0 -> reduced NV=0. Tail signature:
sub-lane 1 is outside VL, mask=1, raw status contains X, aggregate gains X;
VRF high-byte be remains zero. Align observations by accepted transactions
and tags, not assumed fixed latency.

## Optional independent diagnostic, compiled but not simulated

New files only:

- `verification/diagnostics/gap29_fp16_rne_diag.c`
- `verification/diagnostics/build_gap29_fp16_rne_diag.py`

Build passed using the existing `install/riscv-llvm/bin/clang` (resolves to
the shared Ara LLVM clang-22 installation), not ZCC. Only linker warning:
non-allocatable `.comment` section ignores its memory-region assignment.
Build output, command list, input hashes and disassembly:
`verification/out/gap29-fp16-rne-diagnostic-build-20260928-01`.

The diagnostic preserves the six original vector sequences and saves results
before printing. It prints every data mismatch plus indices 0/29/30/64,
with pass/index/source/actual and expected half/wide results and expected
element flags. Each pass also prints actual/expected aggregate narrowing
and widening flags and the number of data mismatches. Fflags are per
instruction, not per-element measured flags. Unknown CSR values must still
be checked in the four-state scalar trace; a software printf is not an
X-aware oracle.

Two additional VL=8/all-mask-on probes move the sole sNaN between global
index 0 and index 4 (Ara lane 0, fpnew sublane 0 versus 1). Both should
produce half=7e00 and flags=10. The primary hypothesis predicts flags=10
for index 0 but flags=00 for index 4, with correct result bits in both.
These probes are in the same ELF, not separate simulation runs.

If a runtime confirmation is subsequently chosen, use exactly one fresh
output directory and the authorized runner/image. No command below has
been executed as part of this investigation:

```sh
ARA_VCS_TIMEOUT_SECONDS=600 PYTHONDONTWRITEBYTECODE=1 \
  bash verification/uvm/run_real_dut_case.sh \
  verification/out/dispatcher-state-reset-20260928-01/sim/simv \
  verification/out/gap29-fp16-rne-diagnostic-build-20260928-01/gap29_fp16_rne_diag.elf \
  gap29_fp16_rne_diag \
  verification/out/gap29-fp16-rne-diagnostic-vcs-20260928-01
```

The existing runner disables FSDB; the proposed internal signal window is
a separate instrumentation plan, not a claim this command enables it.
Expected self-check failure must remain a failure, not be reclassified as
signoff passing coverage. No latest-image runtime result is asserted here.
