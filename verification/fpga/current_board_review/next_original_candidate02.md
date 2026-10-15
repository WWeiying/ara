# Next Original Candidate 02: Exact Unboxed FP Compare Failure

Status: **STATIC SELECTION ONLY; NOT PREPARED, NOT RUN, NOT A NEW RTL BUG CLAIM.**
Only one program is selected. No compiler, reference, simulator, build, or live
service query was run for this note. Merge98's reported executor PASS is awaiting
the separate independent audit; it is not re-audited or included here.

## Selection and Measured Failure

Select `rvv_fp_compare_unboxed_unmasked_e16_mf4`, RVV-09, destination v24.
Reproduce its **first 265 natural calls**, ending at the exact original failure:

```text
op=4 (vmfeq.vf), seed=0, VL=15, mask=0, sticky=0, vstart=0, capacity=16
RVV_FP_COMPARE_DETAIL op=4 seed=0 vl=15 mask=0 sticky=0 expected_flags=0 actual_flags=16 errors=1
```

This is a measured numerical/flags mismatch, not `last_trial=NULL` or an inferred
stall boundary. The original report's matching result has `status=failed`, exit1,
4.691078499890864 board seconds, and the final line
`RVV_FP_COMPARE_FAIL sew=16 cases=17920 errors=832`. Only20 error details were
retained. Those832 errors are not832 independently identified bugs. Board time
is not a VCS throughput estimate.

Paths below use:

- `C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`
- `R=/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix`
- `V=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review`

| Original evidence | Actual path relative to the roots above | SHA256, rechecked for this note |
| --- | --- | --- |
| Linux parent ELF | `C/rvv_additions46/binaries/rvv_fp_compare_unboxed_unmasked_e16_mf4` | `404b2c0bb8f9224dc5e281ad1ef83faee238dec1989b26b36d7dbc12e4c3b152` |
| Original manifest | `C/rvv_fp_comparisons_unboxed_v24_unmasked_01/manifest.json` | `13a460255abd3e2349c8a6108c3ed5f2a9174dc30648d347d7e7fb3900c0a489` |
| Parent assembly | `C/rvv_fp_comparisons_unboxed_v24_unmasked_01/rvv_fp_compare_unboxed_unmasked_e16_mf4.S` | `33abaa5c662a3780ac82ea631fec6909a035ccbb6b9d656896ce0cb356808bbe` |
| Shared original C, exact manifest hash | `R/fp_compare_oracle.c` | `03cc50313dee7cda6476658bbe025409617242c06cd06cdaff8d83d2812e9bad` |
| Archived fixtures | `C/rvv_small_fp_compare02/rvv_small_fp_compare_unboxed_unmasked_e16_mf4/fixtures.h` | `5664c1a4546bb402fe64ef190ca8e4910efa21fc35daea5229a187377eba7cb1` |
| Archived operations | Same directory, `operations.h` | `cd0e50739a57ccd54ead1092113528d6535ec62468e8fe4863dbb64fbf2fee64` |
| Raw measured board report | `C/rvv_recovery08_11/terminal_scene/report.json`, `.results[]` selected by exact name | `78feb29c49c69ee6d4e6dd7803a3bccf8d8c88566b10cbbfd639f630c1cda3e1` |

The archive also has the genuine reduced single, ELF SHA
`38d7c5a999231e7fc20a104ded6cd9e0b1489eb435d911332cfee42d07271261`,
under `C/rvv_small_fp_compare02/binaries/rvv_small_fp_compare_unboxed_unmasked_e16_mf4`.
Its recorded provenance is `V/fp_comparison_original/provenance01/singles.json`.
Use it as a tuple/source cross-check, **not** as evidence that the original264
preceding vector calls are unnecessary. The proposed executable is the parent
prefix, not another reconstructed isolated test.

## Source-Faithful Boundary

Original defines: `SEW=16`, `UNMASKED_COMPARISONS=1`,
`UNBOXED_COMPARISONS=1`, `RESTART_COMPARISONS=0`, `DESTINATION_KIND=0`.
At VLEN1024, mf4 capacity is16 and lengths are `[0,1,2,3,8,15,16]`.
Loop order is seed, op, length, mask mode, sticky (one nonrestart trial).
The first failure ordinal is `4*7*4*2 + 5*4*2 + 1 = 265`:
op0..3 each56 calls, then op4's first40 calls, then the failing call.
Do not filter away those264 predecessors, omit their oracle, reset between
calls, or invent warmup. Stop only after call265's complete original checks.

Original ELF disassembly, inspected without recompilation:

- capacity `0x10538..0x1053e`, `vsetvli` encoding `00e2f557`;
- op4 `0x10640..0x10686`, **19 instructions**, including the otherwise unused
  v16 load, v24 and v0 mask loads, scalar `lhu`, and `fmv.d.x`;
- target `0x10668`, encoding **`62805c57`**, `vmfeq.vf v24,v8,ft0`;
- immediate result reads `0x1066c` vstart and `0x10670` fflags, followed by
  packing/restoring the caller's flags and the original `vsm.v`;
- op0..3 have17 instructions each. The proposed prefix executes each56 times
  and op4 41 times: **4587 original helper instructions**, plus capacity once.
  op5..9 remain present but unexecuted, including their internal PCs.

Keep the complete128-byte mask initialization,16-element a/b initialization,
130-byte output initialization, every original result-bit check, both original
guard checks, returned vstart, sticky flags and fflags save/restore. This source
uses deterministic fixture rotations, **not a random generator**. Keep the full
fixture table and source index formulas. The prefix has4240 result-bit checks,
530 guard checks,265 returned-vstart and265 returned-flags checks. Do not replace
the original permitted mask-tail alternatives with a fixed expected tail byte.

At the target, a[0..15] are the16 original inputs in order; b is all zero.
`ft0=0x0000000000000000` is deliberately **not** a boxed half-precision +0.
The oracle substitutes fixture column14 (qNaN `0x7e55`) for that scalar. All15
active result bits must be0 and flags0. a[14]=`0x7e55` is active qNaN;
a[15]=`0x7c55` is tail sNaN. Result bit15 retains the original allowed alternatives.
Element0 distinguishes a correctly canonicalized qNaN (false) from wrongly
using low-half zero (true); the NV flag independently distinguishes tail leakage.

## Current Path and Coverage Gap

Read against M6 frozen sources under
`/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/`:

- `hardware/src/ara_dispatcher.sv:4076`: malformed scalar boxing is replaced
  with half qNaN `0x7e00` before execution.
- `hardware/src/lane/vmfpu.sv:1222`: per-element comparison NV classifier
  assumes that dispatcher normalization, distinguishes equality from ordered
  comparisons, and carries NV metadata to MASKU.
- `hardware/src/masku/masku.sv:449`: accepted comparison metadata is gated by
  the active window and predicate before registered flag publication.

There is **no static proof these current paths are broken**. The old record has
only the flags error: its data oracle passed. That is evidence against declaring
an old scalar-boxing defect, and is consistent with the now-repaired tail-NV
path. A PASS is plausible. The useful unresolved question is whether the actual
malformed scalar transport, fractional-group packing and accumulated source
history satisfy that repaired end-to-end contract, not whether NV gating exists.

Non-duplication evidence:

- `V/comparison/README.md` identifies its accepted VL15 tail single as **boxed**
  scalar `ffffffffffff0000`, **v0** destination, a different original ELF.
- `V/fp_comparison_original/TERMINAL08.md` accepts two e16/m2 restart130 programs:
  all260 targets are op0 vv, not this vf/unboxed parent or its predecessor chain.
- `V/fp_comparison_original/README.md` explicitly lists this unboxed e16/mf4
  context as selected-but-unprepared/unrun; its held682 e16/m8 alias case is
  both different and too expensive for this admission objective.
- Producer-unit scalar tests and reconstructed comparison matrices are useful
  controls, not acceptance of this Linux parent's authentic first265 calls.

If the target fails on a future authorized run, discriminate using its exact
accepted scalar payload/canonicalization, VMFPU operand/element-NV metadata,
MASKU accepted element15 active-window bit, and immediate CSR result. Correct
data plus NV16 points toward flags/window/ownership; bit0=1 instead points toward
scalar transport/boxing. Do not change RTL or repeat timeouts without that evidence.

## Environment and Bounded Cost

Reuse the existing M6 host-VCS image, four lanes/VLEN1024 with vector FP16.
A future software-only adapter may replace Linux entry/write/exit and add the
post-oracle stop. It must not replace `fmv.d.x` with a half load or box the scalar.
Use the established explicit FP16 reference profile if later authorized; do not
infer an RTL fault from an environment lacking Zvfh. No page-fault/Linux service
semantics are needed by this C program, but the port will not preserve Linux
scheduling, original virtual addresses, or cross-process history. A relocated
ELF address map and original helper-byte proof remain preparation gates.

Static instruction estimate from the **actual original ELF**, not another
program's call count:

| Per-call work | Original PC region | Conservative instruction allowance |
| --- | --- | ---: |
| Mask initialization,128 iterations | `0x10346..0x1035e` | 128*10 =1280 |
| a/b initialization,16 iterations | `0x10370..0x103ae` and loop transfer | 16*32 =512 |
| Output initialization,130 iterations | `0x103bc..0x103c8` | 130*5 =650 |
| Complete16-bit scalar oracle | `0x1041e..0x10474`, `0x1023a..0x10250` | 16*40 =640 |
| Helper, call setup, flags/guards/outer control | remaining successful path | 400 |

Total successful-path allowance: `265*3482 = 922730` instructions.
Allowing a further100000 for startup, final output/termination and adapter work
gives about **1.02M**, rounded upward to **1.2M planning envelope**. This is not
a measured reference count or a formal bound on a not-yet-built port; future
compiled code and one authorized reference must confirm it before DUT admission.
Error printing is not used to predict a successful full run; first failure stops
acceptance. Original17,920-call execution is not proposed.

For throughput evidence, the authentic FP130 programs in
`V/fp_comparison_original/TERMINAL08.md` retired1,147,283/1,146,548 instructions
in1647.307/1633.255 seconds (696/702 retired/s). At the slower established planning
proxy273 retired/s,1.2M with20% allowance is **5275s (88min)**; at696/s it is
2069s (35min). These are proxies, not a performance guarantee. A future reviewed
single-case7200s/whole-service9000s cap would stay below3h without increasing
timeouts on failure. No budget or launch is enacted by this note.

## Decision Boundary

Recommend only this first265-call, exact-failure-boundary program for the next
software preparation review. It preserves all needed *within-program* history
through the measured failure and is substantially smaller than the held682 case.
If it passes, accept only those265 original calls on the tested image: not the
17,920-call parent, all208 RVV-09 records, Linux replay, or a newly discovered bug.
If the priority requires an already-proven **current** bug rather than an exact
historical counterexample with a coverage gap, this static selection cannot supply
that proof and should not be represented as doing so.
