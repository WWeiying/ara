# Special-Scale Same-Image Gate

PASS closed 2026-11-09 21:01:00 PST. Output:
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_matrix_special_vcs_20261109_02`.
388 source/image/input pins match before and after. The owning service exited
successfully; this agent's active helper leases are released. Parent-owned SoC
workers and their production pins are unaffected.

## Cases And Results

Both exact queue01 images, q0 and q16, each ran the six cases once. No RTL,
C-ref, canonical SV checker or existing log checker was edited or recompiled.
All cases are Q4_K/M8/N5/Kb2. fill_q4 initializes row/K blocks; only d/dmin
change. Original Q8 activation fill and ordered C-ref arithmetic are retained.

| Case | Scale class | Checked command flags |
|---|---|---:|
| 0 | qNaN d=0x7e00 | 0x00 |
| 1 | sNaN d=0x7c01 | 0x00 |
| 2 | +Inf d=0x7c00 | 0x10 |
| 3 | -Inf d=0xfc00 | 0x10 |
| 4 | Mixed signed-zero d/dmin | 0x00 |
| 5 | FP16 subnormal d/dmin | 0x01 |

The original checker passed all result bits, flags, geometry, counters and
tail/write guards. Every case takes 1159 cycles at q0 and 1052 at q16. Each
image executes 3072 native and 3072 real borrowed beats over the six commands.
q16 accepts/pops 480 queued FP requests; exact payload order and terminal drain
checks pass. These are six scenarios in two configurations, not 12 new shapes.

## Explicit Oracle Adapter

The parent approved the RISC-V F2.2 canonical-NaN rule:
https://docs.riscv.org/reference/isa/v20260120/unpriv/f-st-ext.html#_nan_generation_and_propagation

`run_matrix_special_v2.py` changes only final O records whose FP32 exponent is
all ones and fraction is nonzero, to 0x7fc00000. Inf, signed zero, finite bits,
raw operand records and flags are unchanged. Compared with the preserved
cooperative `raw_evidence/vectors.txt`, all C counter lines are byte-identical;
the runtime vector equals its NaN-only adaptation. The earlier candidate_vector
dot adjustment is retained, not changed by this ISA adapter.

All 88 NaN changes are listed in `nan-differences.json`: 40 sNaN-derived payloads
and 48 negative NaN results from the two Inf cases. Twelve host tests passed,
including mutations that must reject changed flags, non-NaNs, Inf, signed zero,
shape, counts or an arbitrary noncanonical NaN result.

## Preserved Limitations

The original `_01/host-tests.log` FAIL, raw vectors and raw reference outputs
remain untouched and are copied under `raw_evidence/`. That preflight never
launched a simulator. Its added host assertion incorrectly required sNaN NV;
the inherited half expansion quiets NaNs without independently setting NV,
as documented in `hardware/docs/qbs_half_scale_issue.md` lines 38--40.
This gate preserves that behavior; it is not independent IEEE validation of
the inherited half sNaN conversion rule. No flags were patched or masked.

The finite/real queue PASS and original failed workers remain separate records.
No further production or helper edits, tests, optimizations or SoC launches
are planned by this agent.
