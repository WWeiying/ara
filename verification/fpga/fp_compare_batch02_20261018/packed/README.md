# Batch02 Packed Scalar Prefixes

Scope: the original two ELF programs only. No RTL edits, parent runner edits,
VCS execution, board access, or long reference execution. The original vector
helpers and all predecessor calls remain; scalar timing is deliberately changed.
This does not reproduce Linux scheduling, context switching, addresses, or cycles.

## Ready: 319

* Artifact: `out319_04/soc.elf`
* SHA256: `1371b771ba6b2addb92d694b122891b9f6cab3aa079e347dd67d7a2acd4e9015`
* Spike: `RVV_FP_COMPARE_PASS sew=32 cases=319 errors=0`, `BOARD_REPLAY_PASS`, exit 0.
* Actual retired instructions through HTIF exit: **332,948**. This includes boot,
  scalar checker, original vector helpers, and reference output/exit plumbing.
* Raw commit log: 26,067,409 bytes, bounded at 128 MiB and 120 seconds.
* `out319_04/trace_audit.json`: actual 319 helper entries in original order,
  VL/cap/vstart/sticky arguments and returned flags/vstart, and every helper
  instruction PC/encoding checked against the compiled original helpers.
* SoC ELF text/rodata: 19,288 bytes; BSS: 1,328 bytes; total: **20,616 bytes**.
  The reused linker reserves 64 KiB below its stack top in a 1 MiB region.
* SoC acceptance: process exit 0, exact 319-case oracle PASS, BOARD_REPLAY_PASS,
  Core SUCCESS, no COMPARE FAIL/DETAIL/CAPACITY_FAIL or REPLAY TRAP/SERVICE_FAIL.
  This directory does not launch VCS or infer DUT PASS from Spike PASS.

The old full700 reference retired 2,179,709 instructions and projected 4,371 s
from its measured M8 baseline (see the referenced full700 reference01/result.json).
An instruction-count-only extrapolation gives roughly 668 s for this prefix,
or 802 s with 20% margin. Different images, vector shapes, UART implementations,
and memory stalls make this a planning estimate, not a time guarantee. It is not
derived from the parent's original319 timeout by assuming the same throughput.

## Prepared Only: 15286

* Artifact: `out15286_01/soc.elf`
* SHA256: `225a57d8d6977dd23ba748d05b3c457a520ee9558721a6592177858196c49078`
* Endpoint: seed27/op2/VL32/mode2/sticky1, expected flags17.
* Host oracle equivalence and both ELF compilations passed; **no Spike/VCS run**.
* SoC text/rodata: 285,488 bytes; BSS: 560 bytes; total: **286,048 bytes**.
* Copy loops execute 16 packed iterations per call, output/mask initialization
  16 iterations, and checking 4 byte iterations. Static success-path budgeting
  suggests several million retired instructions (roughly 5-9 million, unmeasured),
  versus 332,948 measured for319. At the historical full700 throughput this is
  about 10,000-18,000 s before safety margin. It has no demonstrated 3-hour budget
  fit, so it is prepared but not admitted for execution here.

## Equivalence Evidence

`prepare.py` verifies prepared02's source/file pins, independently validates all
1,536 FP32 fixture comparisons using integer NaN/ordered-comparison semantics,
then emits packed tables. No floating-point/vector instructions implement the
new scalar checker. The only vector instructions outside startup CSR setup are
in the unchanged original capacity/op_0..9 helpers; disassembly checks their
instruction words against prepared02 for both backends.

Per call, complete active input arrays, all128 mask bytes, and all130 original
output initialization bytes are freshly written. Shared constant input rows are
ROM templates, not reused live input buffers or removed predecessor operations.
Vstart remains zero as in these original programs.

Each output bit has two rejection constraints: actual1 forbidden and actual0
forbidden. Popcount of rejected bits is exactly the original bit-error count,
not one error per byte. The tables retain every original allowed old/tail/result
alternative, including VL0 old-only behavior. Flags and vstart each contribute
one error on mismatch; the pair of guards contributes one error even if both fail.

For each prefix, host builds execute the original C oracle and packed checker
against one mock-helper implementation. Every call checks all input bytes,
mask bytes,130 initial output bytes, opcode, VL, cap, vstart, and sticky. The
complete console (including per-case errors) and input/argument fingerprint must
match for ten paired executions: three legal alternative patterns plus seven
negative variants (one/three illegal bits, NV, either/both guards, vstart, and
combined errors). See `original0..9.log`, `packed0..9.log` and exit receipts.

Exhaustive byte alternatives: 1,306,624 for319 and 15,652,864 for15286.
`test_masks.py` additionally exhausts all3^8 legal-set combinations times256
actual bytes (1,679,616 checks), covering all singleton/flexible bit masks,
including allowed tail/masked-off sets. Production cases remain unmasked; this
test does not claim to introduce masked vector coverage. See mask_selftest logs.

## Reproduction

Use a fresh output directory under packed for each preparation:

```sh
python3 -B verification/fpga/fp_compare_batch02_20261018/packed/prepare.py --case 319 --out verification/fpga/fp_compare_batch02_20261018/packed/NEW319 --spike
python3 -B verification/fpga/fp_compare_batch02_20261018/packed/audit_trace.py verification/fpga/fp_compare_batch02_20261018/packed/NEW319
python3 -B verification/fpga/fp_compare_batch02_20261018/packed/prepare.py --case 15286 --out verification/fpga/fp_compare_batch02_20261018/packed/NEW15286
```

Preserved failed attempts: out319_01 fixture-format assertion; out319_02 Python
version popcount API mismatch; out319_03 unsupported rdinstret probe (trap before
the tested prefix). The accepted out319_04 uses raw commit counting, no added
retirement CSR read. These failures are harness issues, not DUT results.
