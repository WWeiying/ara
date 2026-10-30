# Private Decode Q8_K block-sum candidate

The actual single-row RVV quantizer already uses vector min/max, multiplication,
conversion and sums. Do not replace its signed-maximum selection with the M4
helper: equal positive/negative magnitudes currently select the negative
extremum, unlike the first-element rule of the M4 generic implementation.

This candidate changes only how sixteen-element integer sums are extracted
from an existing e8,m2 vector. The old implementation repeatedly slides the
whole active vector by 16. The candidate selects the relevant m1 subregister
and slides only 16 active elements by the intra-register offset. It adds no
memory traffic and does not change quantization, rounding, scales or format.

The hypothesis is reduced slide work on the ordinary RVV slide unit; register
extraction and compiler moves may offset the gain. It is not yet a measured
optimization. Do not integrate it based only on a shorter operation count.

`test.c` compares the original register algorithm and an independent scalar
sum, including full/tail chunks, int8 extrema, canaries and CSR preservation.
Run it with multiple VLEN values before using a real captured single-row
activation in a complete preparation/projection RTL comparison. Each VLEN
should perform 33,280 checks. Production source and RTL are unchanged.

## Functional gate, 2026-10-26

`run.py --output verification/out/<new-directory>` builds a private static
guest and runs it under system QEMU. Source, tools and guest artifacts are
hashed before and after execution; both the exact test marker and guest exit
status must succeed. QEMU timing is not a hardware performance measurement.

The completed run `verification/out/q8k-decode-sums-20261026-01` passed at
VLEN 128, 256, 512 and 1024: 33,280 checks each, 133,120 total. The systemd
worker exited zero. Its `result.json` records log hashes and the source-pin
manifest digest. This establishes helper correctness only: full quantizer,
real-data projection timing and runtime integration remain outstanding.

## Complete-function comparison

`run_full.py` extracts the current single-row function from the actual runtime
source and retains it unchanged as the reference. The private second function
replaces only the block-sum section. Generated source and the actual GGML block
definition are pinned. This is an extracted-function gate, not a link test of
the full runtime translation unit or an independent quantization oracle.

`full_test.c` checks all output bytes, surrounding canaries, input preservation,
FCSR and VCSR equivalence. An independent scalar loop checks sums against the
produced int8 values. It covers lengths 0, 256, 512, 1536, 1792 and 8960,
12 finite input patterns, five legal rounding modes and eight VCSR values:
2,880 comparisons per VLEN. Special floating-point input behavior beyond these
finite patterns is not claimed. Real captured data and VCS latency remain
required before promotion.

## Runtime and captured-data gates

The complete extracted-function run
`verification/out/q8k-decode-full-20261026-01` passed 2,880 comparisons at each
of the four VLEN values (11,520 total).

`compile_runtime.py` uses the recorded production compile flags to compile
both entire `arch/riscv/quants.c` translation units, with only the private
candidate's block-sum section changed. The run
`verification/out/q8k-decode-runtime-compile-20261026-01` passed for the
combined RVV/Zfh/Zvfh configuration. Compilation is not a full runtime
execution test. The type table in `ggml-cpu.c` maps Q8_K `from_float` to this
function; the repack path calls it for single rows when activation reuse does
not eliminate preparation. Existing reuse must remain intact.

`run_real.py` additionally generates exact bit-pattern inputs from all seven
captured Decode projections of Qwen2.5-1.5B Q4_K_M: attention Q/K/V/output
and FFN gate/up/down. Metadata, finite values, byte sizes and contiguous
single-row geometry are checked before compilation. K is 1536 or 8960.
The run `verification/out/q8k-decode-real-20261026-01` passed all 280
comparisons per VLEN, 1,120 total, across VLEN 128/256/512/1024. These are
captured-input function comparisons, not complete model executions. Source
pins and log digests are retained with each result.

No latency improvement is established yet. Next measure complete preparation
with the same captured data on VCS, then a complete projection if preparation
improves. Keep original and candidate in the same ELF, use ABBA order and
include all conversion and block-sum work inside the measured interval.

## VCS measurement

`soc_test.c` measures the entire original/candidate quantizer in ABBA order for
captured Decode Q (K1536) and FFN-down (K8960). Eight calls retain output-byte,
input, guard, block-sum and CSR checks. `run_soc_golden.py` generates independent
QEMU output digests using the same harness. Its cycle field is a dummy ordinal,
not a QEMU performance measurement: user-mode cycle CSR reads are disabled in
this guest. The first golden attempt retained its illegal-instruction failure
in `q8k-decode-soc-golden-20261026-01`; the corrected golden passed in `-02`.

`build_soc.py` builds the bare-metal ELF; its cycle probe uses fenced `rdcycle`.
`run_soc.py` checks the eight complete records against the QEMU digests and CSR
values, then reports per-shape summed ABBA cycles. UVM protocol checks and
source/image identity checks are also required. `test_check_soc.py` includes
negative cases for malformed records, incorrect identity, failed results,
changed outputs and a mismatching golden digest.

Run directories for the pending hardware measurement:

- `verification/out/q8k-decode-soc-build-20261026-01`
- `verification/out/q8k-decode-soc-vcs-20261026-01`

The latter is owned directly by `q8k-decode-soc-vcs-20261026-01.service`.
No production kernel or RTL was changed. These measurements exclude matrix
execution, GGML graph scheduling and model loading; do not label the result as
complete projection or end-to-end speedup.
