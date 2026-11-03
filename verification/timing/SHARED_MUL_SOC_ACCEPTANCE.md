# Shared multiplier complete-SoC acceptance

## Goal and exit conditions

Keep the selected Booth+Dadda multiplier intact and compare complete CVA6+Ara
SoCs with identical source contents, memory geometry and ELF files. Only
`ARA_SHARED_SIMD_MUL` differs. This is not a substitute for physical signoff.

Acceptance requires:

- All integer multiply, multiply-high, mixed-sign, fixed-point and widening
  multiply/MAC instruction tests pass their architectural result checks.
- Dedicated mixed-SEW firmware passes with real Lane operand queues, VMFPU
  issue/processing state, result queues and VRF writeback in the path.
- Mixed firmware covers all SEW transitions and LMUL 1/2/4, non-full VL,
  masked destination preservation, RAW and destination read/modify/write.
- Per-Lane multiply acceptance/completion counts balance. Activity must be
  nonzero; a successful ELF that bypassed multiplication is not evidence.
- Independently checked real integer dot-product and integer matrix-multiply
  applications pass. Compare each reported timed region, not just boot time.
- The existing llama.cpp real-data micro ELF passes six captured-golden checks
  (Q8_K activation quantization and Q4_K/Q6_K dot products, 1536/8960 lengths),
  with paired cycle and activity comparison. This is a microkernel workload,
  not complete model execution or QBS/AKV custom-instruction acceptance.
- Investigate any extra cycles or stalls. Do not declare performance acceptance
  from unit-level II=1 or merely from architectural PASS.

## Current campaign

Outputs under the single verification worktree `verification/out/`:

- `shared_mul_soc_20261103_01`: two full SoC builds, 16 instruction-test ELF
  pairs, plus existing `dotproduct` and `imatmul` ELF pairs. Build input manifests,
  command lines, source pins and ELF hashes are retained. A new failure stops
  subsequent dispatch, rather than silently continuing a broken acceptance.
- `shared_mul_mixed_20261103_01`: generated assembly and independently calculated
  expected memory contents, compiled without ZCC; 96 mixed-SEW phases.
- `shared_mul_mixed_soc_20261103_01`: runs that same mixed ELF on both images.
- `shared_mul_llama_soc_20261103_01`: the existing `llama_q4km_micro` ELF on
  both images; frozen ELF/hash, six golden-result outcomes, individual region
  cycles and complete-VMFPU multiply activity. No new simulator build.

`shared_mul_soc_monitor.sv` is read-only. It observes the complete VMFPU request
and result handshakes, not the extracted multiplier bank. Its counters show word
acceptance/completion, SEW composition and input blocking; they do not prove
arithmetic correctness alone. Firmware memory checks provide that evidence.

VCS runs on the host. No Verilator, URG, synthesis or FPGA update is involved.
The shared multiplier remains opt-in. Both builds enable the same QBS/AKV options;
these initial applications do not establish QBS/AKV application acceptance.

## Status

Final acceptance is PASS for this planned campaign. Final raw-log/hash audit:
`../ara_dsa_signoff_integration/verification/out/shared_mul_soc_final_audit_20261103_02/audit.json`.
`evidence_hashes.json` in that directory records the audited original logs,
commands and ELFs. It independently rechecks architectural exits, actual mode,
per-Lane activity, selected RTL hashes, build manifests, image identities and
application regions rather than trusting supervisor PASS labels alone.

Both complete SoC builds finished with passing source-manifest checks. The
96-phase mixed-SEW firmware passed both variants. Per-Lane accepted/completed
word counts match between variants and balance within each variant. Aggregate
input-blocked observations are 26 in both variants, and hardware-counted cycles
are 19256 in both variants. This is scoped evidence of no additional stalls for
this mixed-width workload, not proof for all applications or arbitrary streams.

Authoritative mixed result:
`../ara_dsa_signoff_integration/verification/out/shared_mul_mixed_soc_20261103_01/results.json`
(relative to the repository root).

The initial instruction matrix passed. Its original matrix task timed out and
is not relabeled as PASS. Final paired matrix success comes from the disclosed
fast build below. `collect_shared_mul_soc.py` correctly rejected the incomplete
original campaign. The final consolidated report is
`shared_mul_soc_fast_20261103_02/report.json`; functional and performance status
are both PASS. Four application parser tests and four llama parser tests pass.
Monitor counts are whole-run word-level observations, not a per-region causal
stall breakdown. The legacy `gold_results.txt` is not an architectural oracle;
firmware compares results internally against scalar/captured golden values.

The llama microkernel report is independent:
`shared_mul_llama_soc_20261103_01/report.json`. Its four host parser tests reject
incomplete regions, duplicate regions and zero cycles. Final goal acceptance
reviews this report as well as the consolidated matrix/application evidence;
neither is a full-model llama.cpp execution claim.
Source data declarations identify captured Qwen2.5-1.5B Q4_K_M inputs, including
Q6_K tensors in that mixed-format model. The measured legacy ELF is copied
unchanged, not rebuilt from potentially newer local helper sources.

## Completed application evidence

All 16 instruction-test pairs have passed, as has the mixed-SEW pair. Integer
dotproduct passed its scalar-reference checks for all nine regions below;
complete-VMFPU accepted/completed counts match and input-blocked counts are zero
in both variants. Matrix multiplication also completed its full sweep and
original n128 golden check on both variants. Full simulated finish time is the
same (12019315000 simulator time units). Each Lane accepted and completed
599184 multiply words; each Lane observed8 blocked input cycles in both images.

| Integer matrix size | Baseline cycles | Shared cycles |
|---|---:|---:|
| 4 x 4 | 825 | 825 |
| 8 x 8 | 1030 | 1030 |
| 16 x 16 | 2797 | 2797 |
| 32 x 32 | 11993 | 11993 |
| 64 x 64 | 87468 | 87468 |
| 128 x 128 | 712456 | 712456 |

The matrix app verifies its final full-size result; smaller intermediate timing
points are not separately golden-checked by that original app. Its smaller
regions provide timing comparisons, not standalone numerical acceptances.

| Dotproduct region | Baseline cycles | Shared cycles |
|---|---:|---:|
| e64, AVL8 | 167 | 167 |
| e64, AVL64 | 156 | 156 |
| e32, AVL8 | 216 | 216 |
| e32, AVL64 | 226 | 226 |
| e16, AVL8 | 208 | 208 |
| e16, AVL64 | 107 | 107 |
| e8, AVL8 | 204 | 204 |
| e8, AVL64 | 99 | 99 |
| e8, AVL512 | 353 | 353 |

The six llama.cpp microkernel regions passed their captured-golden comparisons.
Paired numerical output strings match exactly; quantized output is checked by
bytes, while dot results use the original explicit tolerance to the capture.
This does not claim every floating result is bit-identical to captured QEMU
golden values. All six have unchanged cycles, and both complete runs report
zero multiply input blocking.

| Captured microkernel region | Baseline cycles | Shared cycles |
|---|---:|---:|
| Q8_K quantization, K1536 | 13098 | 13098 |
| Q8_K quantization, K8960 | 73659 | 73659 |
| Q4_K x Q8_K dot, K1536 | 5738 | 5738 |
| Q4_K x Q8_K dot, K8960 | 31769 | 31769 |
| Q6_K x Q8_K dot, K1536 | 4838 | 4838 |
| Q6_K x Q8_K dot, K8960 | 27392 | 27392 |

These cycle comparisons use identical ELFs, not separately tuned software.
They demonstrate area-oriented resource sharing without observed software
slowdown for the measured regions; they are not claims of application speedup.

## Matrix wall-time handling

During the live matrix sweep, measured simulation speed showed that the initial
1800-second wall bound could truncate the original 128x128 workload. The
original worker and its source pins are not edited or relabeled. Both original
simulators continue to their original bounded terminal state.

`complete_shared_mul_soc.py` is scheduled independently and waits for that
terminal state. If and only if the original failure consists exclusively of
matrix timeouts (return code124, no printed arithmetic/assertion failures), it
reuses the same two images and identical frozen ELF in a new directory with a
7200-second per-image bound. It does not repeat the 16 completed instruction
pairs, dotproduct, mixed test, llama tests or hardware compilation. Other
failure classes stop consolidation rather than triggering blind replay.

Consolidated evidence is written to
`shared_mul_soc_complete_20261103_01/report.json`, explicitly recording whether
matrix replay was needed and retaining the original campaign status. Acceptance
requires the full matrix sweep through n128 and its original golden check;
smaller already-timed points are not substituted for that requirement. The
earlier collector may legitimately reject a timed-out original campaign; that
historical rejection must not be rewritten as PASS.

The original matrix runs have now both terminated at their original wall bound
with returncode124, without a reported arithmetic/assertion failure. The first
four printed kernel cycle counts match exactly (n4=825, n8=1030, n16=2797,
n32=11993). Baseline also completed n64=87468, while shared was still executing
n64 at timeout. These are incomplete runs, not full matrix PASS. Different host
simulation progress rates must not be mistaken for different target cycles.
The same-image/ELF matrix replay is now running in the consolidated directory;
no RTL/source modification or hardware recompilation was performed.

## Measured simulation-speed improvement

The debug-enabled replay was superseded after a measured, checked simulation
build improvement. This is a host simulation optimization, not a processor
optimization. Both new VCS builds use identical sources, macros and parameters;
only `-kdb` and `-debug_access+all` are removed from both command lines. All
source contents are checked against the original accepted pair.

On the same `vmul` control ELF, final simulated time remains 454975000 and all
per-Lane accepted/completed/blocked counts match exactly. Simulator CPU time
falls from 49.32 to14.63 seconds for baseline (3.371x), and from52.67 to15.20
seconds for shared (3.465x). The initial fast supervisor conservatively stopped
because it compared Python tuples to JSON lists; raw values were identical.
That original ERROR and the original helper are preserved. The successor
normalizes container representation without relaxing any numeric comparison,
and reuses both completed builds/control logs instead of recompiling.

`shared_mul_soc_fast_20261103_02` now runs the unchanged full matrix ELF against
the fast pair, with a10800-second bound. Only after the measured control passed
was the slow replay service stopped; its status is explicitly SUPERSEDED, not
PASS. Its partial logs remain available. The original 30-minute campaign also
remains CASE_FAILED with two matrix timeouts. Final consolidated results, if
successful, will be written to the fast successor's `report.json` with the
original evidence paths and compiler-option change disclosed. No result is
reclassified as an original-image matrix PASS.
