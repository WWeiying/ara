# Integer SIMD ALU sharing

## Scope and acceptance

This change targets `hardware/src/lane/simd_alu.sv`. The comparison baseline is
commit `b69df88f0`. It does not modify the shared integer multiplier, FP units,
operand queues, instruction decode, architectural configuration, or FPGA copies.

The requested stopping point for this campaign is: implement the ALU change,
pass component functional tests, launch matched baseline/candidate component DC
synthesis, and stop without waiting for synthesis. Launching DC does not prove
an area saving or timing closure. Full SoC and FPGA acceptance are separate work.

## Resource organization

The previous RTL describes width-specific add, subtract, averaging and comparison
expressions. Some can already be merged by synthesis; source duplication alone
does not quantify silicon waste. The candidate makes the sharing explicit:

- One 64-bit arithmetic path for eight 8-bit, four 16-bit, two 32-bit, or one
  64-bit element. All elements still compute concurrently.
- Subtraction uses operand inversion and an element-local carry-in. `VRSUB`
  exchanges the input roles; ordinary subtraction computes operand B minus A.
- Mask carry/borrow uses the lowest-byte mask bit of each element, exactly as
  the original interface does. No arithmetic result is masked off inside ALU.
- A sparse correction operand holds carry-in at bit 0 and averaging round-up at
  bit 1. Carry-save compression combines the three operands without adding a
  second wide rounding adder.
- Eight byte-local sums feed a three-level carry prefix. Both carry-save and
  carry-propagation paths are cut at element boundaries selected by SEW.
- Element extension bits reconstruct the SEW+1 result. They serve unsigned
  overflow/borrow, signed averaging, and unsigned comparisons.
- Signed comparisons select the operand sign when signs differ; otherwise the
  unsigned borrow determines ordering. Equality is a direct bitwise comparison.
- Saturation and averaging share the arithmetic result but retain their own
  small formatting logic. Width-specific output slices are wiring and selection,
  not independent full-width arithmetic datapaths.

The module remains combinational and outputs 64 result bits per cycle. No state,
queue, handshake, or pipeline stage is introduced. This preserves architectural
latency and nominal throughput; physical frequency still needs measured timing.

Shift, narrowing/clip, logic, merge and move operations are unchanged. Sharing
their datapaths is not part of this revision.

## Arithmetic details

Let `x` be operand B and `y` operand A, except for reversed subtraction. Define
`sub` for subtract/compare operations. The low-width addition is:

```text
x + (sub ? ~y : y) + correction
correction[0] = sub XOR mask_carry_or_borrow
correction[1] = averaging_round_up
```

The correction is inserted independently at the start of each element. For
averaging, the addition includes `2*round_up`, then the SEW+1 result is shifted
right by one. RNU/RNE/RDN/ROD are selected from the unrounded low bits; signed
averaging also restores the sign-extension contributions of both operands.

Carry-save overflow at an element's top bit must not be lost. The extension bit
is the XOR of the inverted-subtract extension, the top carry-save majority bit,
and the final carry-propagation bit. Signed averaging further XORs the operand
sign extensions. Keeping only the carry from the final adder would be wrong.

`VSSUB` historically zero-extends its per-element saturation flag into the byte
mask field, while other saturation operations replicate that flag. The candidate
preserves this interface encoding, not just its OR reduction. The first miter
run caught this distinction: data matched, but VSSUB/SEW16 flags were `0c` versus
`04`. The corrected candidate retains the original byte-level encoding. This
was an optimization-interface mismatch, not evidence of a new baseline ISA bug.

SEW encodings above EW64 retain the original zero result for arithmetic
operations; ALU does not implement illegal-instruction detection itself.

## Verification

`verification/timing/shared_alu_tb.sv` instantiates the candidate and a renamed,
unaltered Git baseline for both fixed-point-enabled and disabled configurations.

Checks include:

- All 256 internal opcode encodings, all eight SEW encodings, random operands,
  mask, `vm`, valid, rounding mode and narrowing destination selection.
- Complete 8-bit operand pairs for 32 arithmetic/comparison operation encodings,
  all four rounding modes, and both incoming carry/borrow states per element.
  Eight distinct operand-A values are packed into each test word.
- Wide signed extrema, cross-byte carry/borrow and independently selected element
  boundaries for SEW8/16/32/64.
- Exact result and byte-level saturation equality, plus a separate signed
  66-bit arithmetic model for 34 arithmetic/comparison operations. This model
  uses integer addition/subtraction and inequalities, not the candidate prefix.
- Existing `simd_alu_equivalence_tb.sv` directed averaging/narrowing tests,
  including an independent clipping/rounding model.

These are sampled/exhaustive-component tests as described, not a formal proof
over all 64-bit inputs. The random seed is fixed in the test source. Original
failed runs are retained and are not relabeled PASS.

The runner freezes all packages, candidate/reference RTL, tests, DC script and
library setup into an independent verification output directory, records SHA256,
and checks those hashes before and after each worker. Functional failures block
DC dispatch. VCS runs on the host; DC runs in `synopsys_workspace`.

```bash
python3 verification/timing/run_shared_alu.py \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/NEW_RUN

# Only after test.status.json says PASS:
python3 verification/timing/run_shared_alu.py \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/NEW_RUN \
  --start-dc
```

## Synthesis comparison

Both variants use the same registered `simd_alu_timing` wrapper, unchanged
`fixed_p_rounding`, packages, libraries and constraints. Only the ALU source
differs. The wrapper is a measurement boundary, not a new processor pipeline.

- TSMC28 BWP12T typical libraries selected by the repository setup.
- 1.0 ns clock, 0.15 ns setup uncertainty, 0.075 ns hold uncertainty.
- Fixed-point support enabled for both variants.
- `compile_ultra -no_autoungroup -no_seq_output_inversion -gate_clock`.
- Independent reports and DDC files for baseline and candidate.

`area.rpt`, `qor.rpt`, `clk_i_max.tim`, `check_post.rpt` and `metrics.tsv` must
be inspected before making any PPA claim. The total includes the matched wrapper
and rounding unit; the hierarchical ALU area is also reported. No full-chip area
saving, power saving, or application speedup is inferred from this experiment.

## Validated candidate and dispatched synthesis

The final component run is:

```text
/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared_alu_20261103_02
```

Candidate `simd_alu.sv` SHA256:
`d8e07ad7b101d1182d47d4a898df06cc647737d7aa7d2b20c6dfa1f4ab6b82c6`.

| Check | Result |
| --- | --- |
| Input vectors, exact old/new outputs in both fixed-point configurations | 2,127,872 PASS |
| Independent arithmetic model checks, configuration counted separately | 2,437,120 PASS |
| Existing averaging/narrowing directed checks | 22,528 PASS |
| Evidence-runner unit tests | 6 PASS |
| Candidate/source snapshot hash match | PASS |
| Shift and subsequent opcode source section byte-identical to baseline | PASS |

The first row is 4,255,744 output comparisons across the two configurations,
not 2,127,872 processor instructions. Test elapsed time including compilation was
about 3 min 30 s. Testing unsupported SEW encodings deliberately triggers the
baseline's missing-default `unique case` warnings; these are retained in the
raw log, with no fatal or mismatch in the passing run.

The earlier `shared_alu_20261103_01` failed on VSSUB flag encoding as described
above and remains a failed run. Its evidence is not used as functional acceptance.

After the passing run, baseline and candidate DC workers were dispatched with
the same frozen input set. Their state and reports are in:

```text
baseline.status.json          candidate.status.json
baseline/dc.log               candidate/dc.log
baseline/area.rpt             candidate/area.rpt
baseline/clk_i_max.tim        candidate/clk_i_max.tim
```

Both local synthesis jobs subsequently completed. These are component estimates,
not whole-processor physical signoff:

| Metric | Baseline | Shared ALU |
| --- | ---: | ---: |
| ALU hierarchy area, um2 | 8510.8799 | 6087.6479 |
| Registered wrapper total area, um2 | 10190.039891 | 7808.135922 |
| clk_i setup slack, ns | 0.0000203848 | 0.0000565648 |
| clk_i hold violating paths | 1 | 33 |

ALU area decreased by 28.47%; matched wrapper area decreased by 23.37%.
Setup margin is essentially zero, and the candidate has a worst hold violation
of approximately -0.04 ns. Therefore the area result is promising, but timing
closure is not complete. No FPGA files have been modified.

## Full-SoC integration campaign

The next user-authorized verification stage uses
`verification/timing/run_shared_alu_soc.py`. Its independent output is:

```text
/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared_alu_soc_20261103_02
```

The source inventory comes from the accepted fast shared-multiplier SoC build.
Before copying it, every recorded source hash is checked: only `simd_alu.sv`
may differ. The baseline ALU must match Git `b69df88f0`. Sources and headers are
copied, include paths are redirected to that snapshot, and firmware is copied
and hashed. No live RTL is changed during this campaign.

Both images use four lanes, VLEN=1024, a 2 MiB simulation L2, enabled QBS/AKV-v2,
and the selected shared multiplier. Only their ALU implementations differ.
This campaign tests the current main-source configuration, not a new FPGA image.

There are 61 firmware cases, each run on both images:

- 57 existing ISA/edge programs: addition, subtraction, carry/borrow, saturation,
  averaging, comparison, widening, integer reductions, shifts, narrowing, masks,
  source dependencies, restart and load/store tails.
- One independently generated 128-phase mixed program: all ordered SEW changes
  across LMUL 1/2/4/8, dependent arithmetic, masked/restarted signed saturation,
  unsigned saturation, all four rounding modes, comparison and merge. Scalar
  checks compare full destination groups, including undisturbed tail elements,
  and explicitly inspect `vxsat` after subtraction.
- `vvaddint32`, `dotproduct`, and `llama_q4km_micro`. The latter checks six real
  captured-data quantization/dot-product regions, not an end-to-end model run.

Every real VALU contains a read-only baseline ALU observer. Each valid ALU
evaluation compares the complete 64-bit result and byte-level saturation flags.
The first mismatch prints cycle, operation, SEW, operands, mask, rounding mode,
and both outputs. This old/new comparison complements, rather than replaces,
the firmware's numerical checks and the independent component oracle.

The observer also records evaluation beats by SEW, writeback handshakes,
writeback-blocked cycles, pending-but-not-evaluating cycles, pending-and-full
cycles, and mask-result handshakes. These are not instruction counts; the two
pending counters are diagnostics, not mutually exclusive stall causes. Reduction
and narrowing mean that evaluation count need not equal writeback count.

Acceptance requires positive firmware success, four valid lane monitors, no
assertion/fatal/mismatch, and identical paired completion time, application
cycle measurements, results and activity counters. The mixed program and VADD
run first. Remaining tests run at up to six simulators concurrently (three
pairs). A failure or timing difference stops subsequent batch dispatch; already
running members finish and retain their evidence. Timeouts terminate the process
group and are failures, not passes or coverage credit.

The worker is owned directly by a systemd user service. Inspect without changing
or restarting the running input set:

```bash
cat /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared_alu_soc_20261103_02/status.json
systemctl --user status shared-alu-soc-20261103-02 --no-pager
tail -n 30 /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared_alu_soc_20261103_02.service.log
```

`results.json` contains individual simulation outcomes; `pairs.json` contains
functional and exact-cycle comparisons. A `BUILDING` or `RUNNING` state is not
acceptance. This campaign collects no code coverage and makes no physical,
Linux-boot or FPGA claim. The collector/model unit tests passed 8/8 before launch.
The preceding `_01` output is retained as a build failure: the renamed reference
module initially retained its original named `endmodule` label. This was fixed
in the generator with a regression test; no production RTL changed for that fix.

### Supplemental completion and test classification

The original `_02` worker stopped after 56 paired runs because its blanket
nonzero-VALU-activity requirement rejected `vwiden_lmul4_edges`. Both firmware
checks passed: this program performs widening MAC in VMFPU, not VALU. The original
worker reports remain unchanged. A successor audit preserves all numerical,
assertion, identity, four-lane monitor and paired-timing requirements but treats
this program as a collateral, non-ALU test. The same reviewed classification
applies to `vunit_vstart_edges`, which performs only vector memory operations.
Neither is counted as exercising the changed arithmetic datapath.

The first supplemental run also discovered that the pre-existing `vvaddint32`
ELF produced no VALU evaluations and supplied no measured kernel interval. Its
successful EOC is therefore not accepted as vector-add verification. Instead,
`build_shared_alu_vadd.py` builds an isolated, explicitly vectorized 1024-element
EW32/m2 strip-mined addition. Its two input arrays include wraparound values;
all 1024 outputs are checked against scalar-generated modulo-2^32 sums, and the
vector computation is timed separately from the output checks. The replacement
must produce both ALU activity and a positive timer. This substitution is recorded
explicitly, not represented as successful execution of the original application.

The completion worker is `verification/timing/finish_shared_alu_soc.py`. It audits
all existing logs, checks sealed source/ELF/image hashes, reuses successful runs,
and runs only missing cases with the same two images. No RTL or SoC rebuild is
needed. Its classification tests pass 6/6, including rejection of missing firmware
checks, assertions, duplicate lane evidence, and inactive/untimed vector addition.

Current supplemental evidence and progress:

```bash
cat /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared_alu_soc_finish_20261103_02/status.json
systemctl --user status shared-alu-soc-finish-20261103-02 --no-pager
```

`substitution.json` identifies the replacement ELF; `audit.json` identifies reused
evidence and classification changes; `pairs.json` contains completed comparisons.
`report.json` is written only after every required pair passes. The first
supplemental output `_finish_20261103_01` is retained as a stopped checker run.

### Final integration result

`shared_alu_soc_final_audit_20261103_01/report.json` records functional and
performance PASS for all 61 paired cases: 59 ALU-active and two collateral
non-ALU programs. Results, completion times, measured regions and monitor
activity match exactly between baseline and candidate. The mixed program takes
50062 cycles; the replacement 1024-element vector addition takes 1152 cycles
on both images. All nine DOTP regions and all six llama microkernel regions
match. The original inactive vector-add ELF is not accepted as ALU evidence.

The final read-only auditor is `verification/timing/audit_shared_alu_final.py`.
The supplemental worker stopped because the DOTP parser expected the wrong
format. Its actual output uses labeled `Vector runtime` / `Scalar runtime`
regions. The final audit checks the exact nine SEW/AVL pairs, positive timings,
firmware success and all ordinary monitor requirements against the existing
logs. No simulation or RTL change was needed to resolve this parser issue;
the original stopped-worker records are preserved.

Final evidence directory:

```text
/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared_alu_soc_final_audit_20261103_01
```

`verification/timing/shared_alu_selected.json` records the selected RTL hash,
component area results and acceptance scope for this checkpoint. Component hold
closure, whole-SoC synthesis and FPGA validation remain outside this acceptance.
