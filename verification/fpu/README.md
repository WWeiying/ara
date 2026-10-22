# Dirty MVP patch audit

2026-09-30 follow-up: the sources have been repaired; the original runner's
snapshot guard intentionally rejects the changed patch. Use
`run_mvp_repair.py --output <new-directory>` for the repaired bounded regression.
The original frozen audit remains failure evidence, not a current-source PASS.
See `MVP_REPAIR_20260930.md` for the 178-case result and remaining scope.

This is a diagnostic reproduction, not an IEEE conformance or DUT PASS gate.
It compiles the frozen, unmodified original dirty MVP sources, not the
verification dependency. It neither applies nor repairs the quarantined patch.

## Pre-run hypothesis and evidence matrix

| Hypothesis | Discriminating observations at completion | Architectural oracle |
| --- | --- | --- |
| H1: raw non-restoring remainder is not exactness | FP64 1/1 has exact quotient, raw remainder = -(normalized denominator << 4), explicit lower/round bits zero, remainder_nonzero=sticky=1. RUP increments; RNE does not, but both set NX. | FP64 1/1 is 0x3ff0000000000000, flags 0, for both modes. |
| H2: overflow infinity is rounded again | Positive maxfinite/0.5 RUP and negative maxfinite/0.5 RDN have OF=1, overflow_to_inf=1, normalized exponent all ones/mantissa zero, sticky=roundUp=1, rounded mantissa 1. | Signed infinity, flags OF|NX=0x05. |
| H3: FP32 overflow loses NX | FP32 positive maxfinite/0.5 RNE has OF=1 but lower/sticky/roundUp=0. | Boxed positive infinity, flags 0x05. This is a known pre-existing residual, not attributed to the patch. |
| Wrong reset, input capture, or completion sampling | Reset must clear count/quotient/remainder and Done; exactly one start/ready acceptance and one Done consumption per reset epoch; latched format/RM/operands must match stimulus. | Harness failure, never defect reproduction. |
| Wrong oracle | Independent exact-rational operand decoding must agree with every fixed bit/flag oracle before compilation. | These vectors are restricted to exact 1 and overflow by a factor of two; no host floating-point rounding is used. |
| Global bench or format failure | FP32 exact RNE, FP64 overflow RNE, and FP64 overflow RTZ controls. | Exact 1/flags 0; infinity/flags 5; maxfinite/flags 5. |

The eight cases and frozen predictions are in `cases.json`. The bench receives
literal format, RM, input, result and flag values generated from that manifest.
It drives DIV directly: no architectural PC/opcode, conversion, queue, tag,
backpressure, or retirement interface exists at this standalone boundary.
Each case ID is a unique reset epoch. Precision control is zero (full precision),
sqrt and kill are zero, format 01 means FP64 and 00 means FP32. FP32 inputs and
outputs are NaN-boxed. This audit makes no claim about CVA6/VMFPU integration.

## Sampling and bounds

- Drive reset and operands/start on falling edges; hold inputs through completion.
- Record rising-edge pre-NBA start, ready, fire and Done. The single pending slot
  is allocated only by start && ready and consumed only by Done. This top has no
  output-ready input; its result must be consumed while Done is high.
- Record all probes again at rising edge + 1 ns, after NBA and combinational
  settling. Save the first post-NBA Done-high result/flags and require equality
  immediately before the next rising edge (the consumption edge).
- At consumption, verify known data, latched format/RM, sign, full precision,
  the two normalized mantissas and exponents, and exactly one completion. Require
  Done to clear the following post-NBA phase and two quiet drain cycles.
- Probe raw signed remainder, quotient, signed normalized denominator and its
  shifted value, control count/final-state/enable, Done/Ready, special-case gate,
  rounding bits/sticky/roundUp, normalization and rounded exponent/mantissa,
  result and all five flags. CSV has pre/post phases for the entire short run.
- A focused VCD contains only top-level probe aliases, not recursive DUT scopes.
  Capture is bounded by 64 wait cycles per case and a 600-cycle global watchdog.
  CSV is the primary evidence; no FSDB/PLI dependency is needed for this tiny run.
- One compile (180 s bound), one simulation (30 s bound), no retry loop. On any
  unexpected output, preserve and analyze the same trace, reset/capture checks,
  snapshots and rational oracle before contemplating another run.

## Invocation and records

Run from the verification workspace:

```sh
python3 -B verification/fpu/run_mvp_audit.py --output verification/out/mvp-patch-audit-20260922
```

The output must not exist. The runner requires the reviewed MVP HEAD and
canonical full-index diff SHA-256. It freezes all seven MVP modules, the original
common_cells math package, leading-zero counter and assertion header, and the
bench/manifest/runner/plan. `inputs.json` records source paths and SHA-256 values;
snapshot files are read-only. Compile/run commands, logs, return codes, frozen
patch, CSV and VCD stay in that independent output directory. Both original and
verification dependency contents are fingerprinted before and after execution.

`summary.json` distinguishes `DEFECT_REPRODUCED`, `CONTROL_MATCH`,
`HYPOTHESIS_NOT_REPRODUCED`, `UNEXPECTED_DUT_MISMATCH`, and `HARNESS_ERROR`.
Expected defects yield `AUDIT_REPRODUCED_DUT_FAILURES` and
`dut_status=FAIL_ARCHITECTURAL_ORACLE`, never DUT PASS. A zero runner exit code
means the audit reproduced its predeclared evidence, not that the divider passed.
