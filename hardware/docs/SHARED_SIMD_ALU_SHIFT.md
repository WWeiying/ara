# Shared integer ALU shift and selection paths

## Scope

This is the successor to `SHARED_SIMD_ALU.md`. Its comparison baseline is
`59ad2869f`, which already contains the accepted shared arithmetic ALU. This
revision changes only `hardware/src/lane/simd_alu.sv` in the processor datapath.
It does not change integer multiplication, floating-point execution, rounding
mode generation, queues, issue/retirement, QBS/AKV, or FPGA RTL copies.

The implementation is a candidate until the component synthesis and paired SoC
acceptance finish. The previous `shared_alu_selected.json` remains the selected
checkpoint; its area and acceptance results must not be attributed to this new
source. No area saving or clock closure is inferred from shorter RTL.

## Shared hardware

### One segmented shift network

Nine operations use one six-stage, 64-bit right-shift network:

| Operation | Source element width | Fill | Result |
| --- | --- | --- | --- |
| VSLL | SEW | Zero, with input/output bit reversal | Full element |
| VSRL | SEW | Zero | Full element |
| VSRA | SEW | Original element sign | Full element |
| VNSRL | 2 x SEW | Zero | Low half |
| VNSRA | 2 x SEW | Original element sign | Low half |
| VSSRL | SEW | Zero | Rounded full element |
| VSSRA | SEW | Original element sign | Rounded full element |
| VNCLIPU | 2 x SEW | Zero | Rounded and unsigned-saturated low half |
| VNCLIP | 2 x SEW | Original element sign | Rounded and signed-saturated low half |

Each stage has a constant distance of 1, 2, 4, 8, 16 or 32 bits. Wiring that
would cross an element boundary selects fill instead of an adjacent element.
Each element retains its own shift amount; a vector shift is not replaced by a
single scalar shift amount for the entire word. Shift amounts are masked to
the source element width, including the doubled source width for narrowing.

Left shift uses reversal of the entire 64-bit word before and after the network.
This reverses element order as well as bits, so the shift-amount controls are
reversed by element too. The reversal itself is fixed wiring plus direction
selection; it does not need a separately variable reversal network for each SEW.
Left shifts always use zero fill.

The original arithmetic path and its carry prefix are unchanged. All elements
remain concurrent: eight EW8, four EW16, two EW32 or one EW64 element per normal
evaluation. Narrowing still processes the same number of double-width inputs
as before. No registers, handshakes, execution slots or extra cycles are added.
Combinational delay still requires synthesis measurement.

### One segmented rounding incrementer

`fixed_p_rounding` remains the producer of the per-element increment bits for
RNU/RNE/RDN/ROD. The ALU consumes `rm[element_index]`, not `rm[byte_index]`.

The shared incrementer consists of byte-local increments and a three-level
carry prefix. Carry cannot cross a destination-width boundary. For narrowing,
only the low destination-width half receives the increment; the high half is
not incremented. The carry out of the low half is retained separately.

Clipping uses the unrounded high half, the rounded low half, and that low-half
carry. This preserves the distinction between a negative value rounded toward
zero and an actual overflow. Signed clipping cannot be implemented by simply
testing the rounded low sign bit, and unsigned clipping must also detect a
rounding carry when all upper bits were zero.

Narrowing output placement is shared by shift and clip operations. The result
is written into alternating destination elements selected by
`narrowing_select_i`; unused halves remain zero, and saturation flags retain
their original byte-level replication. Unsupported SEWs and disabled fixed-point
operations retain the previous zero-output behavior.

### Shared operand selection

Merge and signed/unsigned min/max now share a byte-wise operand-A/operand-B
selection network. Selection is replicated from the first byte of each element.
The existing signed/unsigned comparison predicates and mask semantics are
unchanged. Basic AND/OR/XOR and mask logic remain simple expressions; no extra
generic truth-table mux is added merely to make the source look more shared.

## Verification and acceptance

All EDA inputs are copied into independent output directories under the sole
verification worktree, `ara_dsa_signoff_integration`. No historical report is
overwritten. VCS runs on the host and DC runs in `synopsys_workspace`.

The component campaign combines:

- An exact old/new miter across all opcode and SEW encodings, both fixed-point
  configurations, and all output/saturation bits.
- An independent shift oracle using signed wide integer arithmetic rather than
  the candidate's segmented mux/prefix structure.
- Every legal shift amount, all four rounding modes, unequal shifts and signs
  across elements, walking bits, signed/unsigned clipping limits, and both
  narrowing output positions.
- Every 16-bit narrowing input at every shift and rounding mode for both signed
  and unsigned clip. Four distinct values are packed per stimulus word.
- Arbitrary externally injected `rm` bits as well as the real rounding producer,
  including invalid cycles and disabled fixed-point support.
- The existing independent averaging and narrowing boundary tests.

These are component tests, not a formal proof over all possible 64-bit inputs.
The new shift-specific test covers 2,915,328 input words in both configurations;
the generic arithmetic miter and original edge suite are separate checks.

SoC acceptance uses `run_shared_alu_shift_soc.py`. It checks the prior source,
image, ELF and final acceptance identities before reusing the accepted shared-
arithmetic image as baseline. Only the candidate is rebuilt. Its RTL snapshot
differs only in `simd_alu.sv`; its read-only comparison module uses the preceding
accepted ALU. Both images run the same firmware and retain the same configuration.

There are 62 paired firmware cases: the previous accepted 61-case suite, with
its explicitly checked VADD replacement, plus a new 256-phase shift program.
The new program covers all nine shift/clip operations, SEW8/16/32/64 where legal,
LMUL1/2, every rounding mode, masked/unmasked execution, nonzero restart, sticky
`vxsat`, and undisturbed tails. It checks complete destination groups against
scalar-generated expected values, `vstart` completion, and `vxsat`.

The four real VALUs also compare old/new ALU outputs on every valid evaluation.
Acceptance requires checked firmware success and identical paired completion
time, application timers, ALU evaluation beats and interface activity. The two
previously identified non-ALU cases remain collateral tests, not ALU activity
evidence. DOTP requires all nine checked SEW/length regions in its actual output
format. Failure or timing differences stop further dispatch.

## Evidence and commands

Component evidence:

```text
../ara_dsa_signoff_integration/verification/out/shared_alu_shift_20261103_01/
```

Inspect its `test.status.json`, `shift/run.log`, `miter/run.log`, and
`rounding/run.log`. After the functional gate passes, matched baseline/candidate
DC uses the same 1 ns clock, 0.15 ns setup uncertainty, library set and registered
wrapper as the preceding ALU comparison:

```bash
python3 verification/timing/run_shared_alu.py \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared_alu_shift_20261103_01 \
  --start-dc
```

Do not execute that launch a second time. Read `baseline.status.json` and
`candidate.status.json`, then their `area.rpt`, `qor.rpt` and `clk_i_max.tim`.
The entire matched wrapper and the ALU hierarchy must both be compared. Any
material timing regression is part of acceptance, not hidden by reporting only
area. Whole-chip PPA and FPGA validation remain separate.

## Current checkpoint

The component worker completed successfully on 2026-11-04 at 07:09:13 UTC
(2026-11-03 Pacific time). The original logs and immutable input manifest are
retained at the component evidence path above.

| Check | Result |
| --- | --- |
| Shift-specific miter and independent oracle, two configurations | 2,915,328 input words PASS |
| Complete-opcode ALU miter, two configurations | 2,127,872 input words PASS |
| Independent arithmetic model within that miter | 2,437,120 configuration checks PASS |
| Existing averaging/narrowing directed suite | 22,528 PASS |
| Python evidence/checker and golden-model unit tests | 28 PASS |
| New mixed shift firmware generation | 256 phases, ELF built |

Do not add the independent arithmetic check count to the miter input-word count:
they overlap. The test count is not an architectural instruction count.

The two component DC jobs were launched after this PASS. SoC acceptance is owned
by service `shared-alu-shift-soc-20261103-01`. Its output is:

```text
../ara_dsa_signoff_integration/verification/out/shared_alu_shift_soc_20261103_01/
```

Check progress without restarting or altering inputs:

```bash
cat /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared_alu_shift_soc_20261103_01/status.json
systemctl --user status shared-alu-shift-soc-20261103-01 --no-pager
```

`BUILDING` means the candidate simulator is compiling, not that firmware tests
have passed. `RUNNING` identifies the active batch and completed paired cases.
Only final `report.json` with PASS establishes the full bounded suite result.
The selected checkpoint must not be advanced until both PPA and SoC results have
been inspected; a component functional PASS alone does not establish area benefit.

## Measured PPA and SoC observation follow-up

Both matched component DC jobs completed successfully. The baseline was
re-synthesized under exactly the same constraints as the candidate:

| Metric | Shared arithmetic baseline | Shared shift candidate |
| --- | ---: | ---: |
| ALU hierarchy area, um2 | 6087.6479 | 3136.0560 |
| Registered wrapper total area, um2 | 7808.135922 | 4855.367958 |
| clk_i setup slack, ns | 0.0000565648 | 0.000139296 |
| clk_i hold violating paths | 33 | 7 |

The incremental ALU area reduction is 48.48%; the matched wrapper reduction is
37.82%. Relative to the pre-arithmetic-sharing ALU (8510.8799 um2), the cumulative
local ALU reduction is 63.15%. These are local cell-area results, not whole-chip
savings. Setup margin remains very small. The candidate still has hold
violations (worst approximately -0.03 ns); physical timing signoff is not claimed.

The first SoC campaign passed 40 paired cases, including the 256-phase shift
program, then stopped on three clip programs. Its original status, logs and
failed pairs remain unchanged. The first failing trace contains:

```text
cycle=605 op=VNCLIP sew=EW8
operand_a=00xx00xx00xx0007 operand_b=0000000000000320
candidate=0000000000000006/00 reference=00xx00xx00xx0006/XX
```

A built-in variable shift returns all X for an unknown shift amount. A mux
network can instead resolve some or all result bits when all possible choices
agree, for example a zero input. Matching those simulator X patterns is not
equivalent to comparing architecturally observed data. The processor RTL was
not changed in response to this observation.

The successor monitor explicitly observes `result_write.be`, the narrowing
half selection, and the existing prestart/masked-destination preservation
gates. Those same byte enables control VRF writeback and mask accumulated
saturation flags at retirement. Its comparison rule is deliberately restrictive:

- Any 0-versus-1 disagreement still fails, even on an inactive byte.
- Any unknown bit on an observed shift result or saturation flag fails.
- X-pattern differences are allowed only for a disabled byte, a shift-family
  operation, and an unknown operand/shift/round input belonging to that same
  element. Unknown enables or controls fail.
- Non-shift operations retain full-word four-state comparison.
- Every tolerated difference is counted; initial events record cycle, operation,
  operands, raw and effective byte enables, data and saturation results.

`shared_alu_observation_tb.sv` passes eight checks, including deliberately
injected known-bit errors, active-byte X, unknown enables, and missing eligibility.
The Python collector/model suite passes 29 tests, including mandatory evidence
that all four new monitors executed. This is an observation-boundary correction,
not permission to treat arbitrary X as a wildcard or to count the stopped run
as PASS. The original programs must still complete their own numerical checks.

The successor service is `shared-alu-shift-soc-20261103-02`, with output:

```text
../ara_dsa_signoff_integration/verification/out/shared_alu_shift_soc_20261103_02/
```

It reruns the three original failing clip programs first, then the full 62-pair
suite. Candidate functional RTL and component PPA inputs are unchanged. Runtime
probes must confirm the byte-enable classification before the three old failures
can be closed. Full-SoC acceptance remains pending until this successor reports
PASS; no physical/FPGA acceptance or application speedup is claimed.

## Final bounded SoC acceptance

`shared_alu_shift_soc_20261103_02/report.json` now records PASS for all 62 paired
cases, with exact result, cycle and activity equivalence. The selected
`simd_alu.sv` SHA-256 is
`33a941e7eeaf8d3818fd74f108231573214040fdc6f483cdaeb1919abc767e57`.
This closes the pending successor regression, including the original clip
failures under the reviewed observation boundary. It does not relabel the
stopped first run or constitute physical, FPGA or coverage signoff.
