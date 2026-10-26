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
