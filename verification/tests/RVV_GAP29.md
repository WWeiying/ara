# FP16 Gap29 Preparation

Six unique `vrvv_gap29_fp16_*_m4` cases, sharing `vrvv_gap29_body.h`.
All six Ara ELFs built and all six HTIF Spike selfchecks passed. Four host
oracle/generator unit tests passed, including 10,000 deterministic binary32
RNE comparisons and exhaustive non-NaN binary16 widening comparisons.

Each ELF executes six bounded passes (65, 64, sparse mask, zero mask, one,
and zero active elements). Checks cover FP32-to-FP16 narrowing followed by
FP16-to-FP32 widening, exact result bits, accrued exception flags, and
tail/mask-undisturbed preservation. RNE, RTZ, RDN, RUP, RMM and round-to-odd
are separate cases. Integer-generated references include signed zero,
subnormals, halfway rounding, overflow, infinities and quiet/signaling NaNs.
There are no deliberate traps, indexed segments, or nonzero-vstart ALU ops.

## Coverage Targets

Original 473 hierarchy identifies MFPU operand A/B/C branches at roughly
71/70/66 percent and VMFPU FSM at 56.41 percent. This supplement targets
legal FP16 narrowing/widening conversion routing, partial packets, masked
FP flags, and dispatcher VL=0 handling with LMUL4/EMUL8 groups. It does not
claim generic conversion zeros are reachable: FP8 and disabled parameter
branches are explicitly outside scope. Offline raw point candidates are in
`verification/out/rvv-gap29-prepare-20260928/baseline473_line_points.json`;
raw XML bit orientation is not vendor-validated and is not coverage credit.

The 521 report is still the next comparison baseline. No measured new-bin
benefit is claimed, and final selection may be reassessed against that DVE.

## Handoff

`rvv_gap29_ready.json` has the aggregate-compatible READY shape with absolute
selection, tests, SHA256 file pins, Spike results path and count. READY means
preflight-ready, not launch authorization: `vcs_authorized` is false and
`manual_launch_required` is true. Append only after the original-image
521-case campaign completes AND the user explicitly signals launch. Use only
that original frozen image, never the repaired image. Proposed per-case VCS
bound is 300 seconds; no VCS timing claim has been measured.

No RTL or existing campaign files were edited. Sources, runtime/header inputs,
compiler/linker/Spike executables, both ELF forms, logs and build commands are
pinned; source/tool pins were checked before and after the final preflight.

Validation:
```
python3 -m unittest discover -s verification/tests -p test_generate_rvv_gap29.py
python3 verification/tests/generate_rvv_gap29.py --check --selection verification/tests/rvv_gap29_selection.json
```
