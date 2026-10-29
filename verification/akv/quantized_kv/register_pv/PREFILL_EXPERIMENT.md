# Causal Prefill register-PV experiment

The accepted production Prefill schedule reuses K panels and V decoding across
query rows, but still materializes decoded V in FP32 scratch before per-row
updates. This internal candidate reuses the measured register-PV leaf to remove
that materialization. It adds no RTL, command, or production dispatch path.

## Scheduling contract

Visible prefix lengths must be positive and nondecreasing across rows, as in
the current query-major/GQA-minor Prefill packing. QK grouping is unchanged:
only equal-length row runs are grouped, in 4/2/1 rows. At a token index the
active rows form a suffix. The candidate decodes that token's Q8_0 value in
registers and updates only that suffix. Finished rows are not rescaled or
updated, and retain their own final normalization. Per-row maximum, sum and
FMA order remain unchanged.

The caller must establish finite supported inputs, disjoint immutable buffers,
production callbacks and masked floating-point traps. This is an internal
schedule, not a standalone untrusted-pointer admission API. Actual VLEN=1024,
RNE, vstart=0, supported row extent and ordered prefixes are checked before
output initialization. Callback errors after initialization are terminal.

## Functional evidence

Run `verification/out/register-prefill-prefix-reference-20261028-01` is PASS.
Compiler arithmetic matches production: no fast-math, FP contraction enabled.
The 1792 cases cover heads 1..8, dimensions 32..256 in steps of 32, lengths
1/2/20/31/32/33/65, uniform and increasing prefixes, and two initial sticky
flag states. Checks include exact output/padding, maximum/sum, final FCSR,
equal QK callback counts and absence of the materializing V callback.
Uniform prefixes also compare with an independent scalar head-major oracle.
Unordered-prefix rejection, QK failure and VLEN=256 rejection are tested.

ELF SHA256:
`0bbcc4ec19d6026e04c4d252125ba4db962238b41e76e520b52fb558a3c4e5b1`.

Reproduce in a fresh output directory:

```sh
python3 -B verification/akv/quantized_kv/register_pv/run_online.py \
  --prefill-prefix --fp-contract fast --execute-reviewed \
  --output verification/out/register-prefill-prefix-reference-new
```

QEMU establishes functionality only. No speedup is established. The next gate
is a complete-call, real-captured-data comparison against the current grouped
Prefill runtime, including admission, K panel work and scatter. Production
selection and the already accepted Decode path remain unchanged.
