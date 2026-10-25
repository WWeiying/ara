# Quantized Attention: Retirement Attribution

## Purpose and Evidence

This diagnostic follows the complete Q4/Q8 H/S/B experiments. It explains
remaining software work rather than introducing another arithmetic pipeline.
The complete six-call experiments remain the accepted latency/repeatability
results; this new three-call diagnostic does not replace them.

Run: `verification/out/quantkv-phase-diagnostic-20261025-01/`.
The actual canonical VCS image executes H/S/B once each, using real captured
Q4_0 K and Q8_0 V data: six query heads, D=128, 128 visible tokens, K/V token
strides 144/272 bytes. The program reuses all sixteen original nonmain objects
and preserves their function addresses/bytes and the original data layout.
No RTL or hardware compilation changed. Measured source is preserved; main
machine code and warm state differ from the six-call program.

The worker completed in approximately 84 minutes. Its numerical checker checks
2304 outputs against the original model gold, H/S bit equality, finite values,
guards, work counts and FCSR/VCSR. All outputs are also bit-identical across
these three calls. The independent protocol checker reports no issues, 28929
completed reads and 7057 matched writes, with no pending transactions.

## What the Retirement Evidence Proves

The linked start/end cycle-read PCs are `0x80000b10` and `0x8000118e`.
All six cycle-read architectural retirements match the actual ELF bytes; their destination
values reproduce the printed cycle measurements exactly. Architectural order
is contiguous. Instruction counts exclude both boundary CSR instructions and
all backend/uop/reshuffle events.

The report also assigns each inter-retirement interval to the **next retired
PC's function**. This is a reproducible description of where the instruction
stream waits/progresses, not exclusive function execution time, a hardware stall
breakdown or functional-unit utilization. Simultaneous retirements have zero
gap. The end-CSR gap is kept separate. Here each monitor span equals its CSR
delta, but that is checked evidence, not a required architectural equivalence.

Main and `akv_quant_strided_execute` include several inlined operations and are
left as unclassified orchestration. A function label does not justify inventing
separate admission, normalization and gather times inside that function.

## Whole Calls and Retired Work

| Item | H: head-major RVV | S: shared RVV | B: shared + native QBS |
| --- | ---: | ---: | ---: |
| Application cycles | 1584411 | 880864 | 566605 |
| Retired instructions | 561123 | 270561 | 281981 |
| Scalar integer/control, including integer CSR operations | 417930 | 148607 | 227550 |
| Scalar FP | 75896 | 70017 | 46990 |
| RVV compute | 35530 | 27850 | 2506 |
| RVV configuration | 13953 | 11393 | 1425 |
| RVV memory | 17814 | 12694 | 3502 |
| QBS command instructions | 0 | 0 | 8 |
| QK callbacks | 768 | 8 | 8 |
| RVV dot calls | 768 | 768 | 0 |
| V row decodes | 768 | 128 | 128 |
| Query quantizations | 6 | 6 | 6 |

H-to-S reduces repeated callback validation and V decoding while preserving
768 RVV dots. B removes those RVV dots using eight native QBS commands, but its
admission and descriptor path adds scalar work. Thus B is faster than S despite
retiring more total instructions. Total instruction count alone is not a latency
or efficiency measure.

## PC-Context Intervals

Numbers below are next-PC inter-retirement gap cycles, with percentages of the
corresponding complete call. They must not be presented as exclusive computation
or memory-stall percentages.

| Context | H | S | B |
| --- | ---: | ---: | ---: |
| RVV QK dot | 474902 (29.97%) | 470213 (53.38%) | 0 |
| RVV QK callback validation/scheduling | 377612 (23.83%) | 28124 (3.19%) | 0 |
| Quantized V decode | 239978 (15.15%) | 43351 (4.92%) | 44514 (7.86%) |
| Exponential helpers | 151502 (9.56%) | 141008 (16.01%) | 136899 (24.16%) |
| PV vector update | 97569 (6.16%) | 98338 (11.16%) | 98328 (17.35%) |
| Shared memcpy | 116544 (7.36%) | 19577 (2.22%) | 101912 (17.99%) |
| Unclassified orchestration | 90122 (5.69%) | 63027 (7.16%) | 139390 (24.60%) |
| Native submission/result store | 0 | 0 | 10127 (1.79%) |

The remaining smaller contexts and eight-cycle end boundary are retained in
the machine-readable analysis; the table above is intentionally not a complete
additive stall chart. `strided_qk` is a composite gather/descriptor/scheduling
context. `output_rescale` includes both online rescaling and final normalization.
Shared memcpy calls must not all be called K-panel transfers: they include small
field reads, validation and other copies.

### Copy-Callsite Recount

A second offline audit streams the complete trace and identifies each memcpy
entry from its actual preceding call PC. Its totals reconcile exactly with
the function-level analysis, with unchanged input hashes. Source/disassembly
inspection separates these B callsites:

| Purpose | Calls | Memcpy-local retired instructions | Next-PC gap cycles |
| --- | ---: | ---: | ---: |
| Mask-prefix admission | 256 | 4864 | 6372 |
| Query-value admission | 768 | 22272 | 27689 |
| K/V scale-field admission | 1024 | 19456 | 35425 |
| Scalar option admission | 3 | 87 | 147 |
| Actual K-panel row copies | 128 | 6784 | 12506 |
| Value-decoder scale reads | 512 | 9728 | 19540 |
| Tensor op-parameter field reads | 3 | 87 | 193 |
| Online scale-validity read | 1 | 29 | 40 |
| Total | 2695 | 63307 | 101912 |

Admission accounts for 69633 of these gap cycles (68.3% of the memcpy bucket,
12.3% of the whole call); actual panel copying accounts for 12506 (12.3% of
the bucket, 2.2% of the call). This is evidence of repeated small source-field
reads compiling into generic out-of-line memcpy, not evidence of saturated
memory bandwidth. Sizes are established from source where applicable, not
inferred from instruction-count histograms. Argument preparation, caller loops
and return-to-caller gaps are not included in these memcpy-local intervals.

Evidence: `verification/out/quantkv-phase-copy-audit-20261025-01/report.json`
and `FINDINGS.md`; all 1506177 retirements consumed, three host tests passed.
These observations do not promise that eliminating a call recovers its entire
retirement gap or quantify a future optimized program's speedup.

## Implication for the Next Optimization

The B call has 8805 QBS command-active cycles, or approximately 1.55% of its
566605 application cycles. This activity is separate from and can overlap the
PC-context intervals. It cannot be added to the table as another disjoint part.
The trace does not support prioritizing another QBS arithmetic pipeline to
remove the large time outside QBS busy.

The first concrete follow-up is to avoid out-of-line tiny-field copies while
retaining aliasing/alignment, integer-only finite/range checks and unchanged
FP flags. This is a candidate, not an implemented or measured optimization.
More promising candidates to investigate also include runtime/admission overhead,
the exponential path and PV/vector delivery. Do not remove finite-domain,
layout, alias or exception checks merely to make the benchmark faster. A useful
follow-up must preserve the existing numerical/fallback contract and prove its
benefit on a complete operator, not only a helper.

This is one Q4 quantized-cache shape. These phase fractions are not Q8 or
whole-model measurements. Canonical QBS/AKV resource integration, accepted
F16/quantized slices and model functionality have their own evidence; none is
replaced by this diagnostic. No synthesis, PPA or FPGA result is implied.
