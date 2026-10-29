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

## Complete-call RTL result and decision

The real-data Q4_0 experiment completed PASS in
`verification/out/register-prefill-q4-vcs-20261028-01`, followed by independent
summary replay. It uses Qwen3 queries 16..19, GQA=2, D=128, causal visible
prefixes 17/18/19/20 and Q8_0 values. The existing grouped Prefill is the
baseline; it already uses the shared RVV value decoder.

| Implementation | ABBA trial cycles | Mean cycles |
| --- | --- | ---: |
| Current grouped Prefill | 141165, 140680 | 140922.5 |
| Register-resident Prefill | 139636, 139699 | 139667.5 |

Measured speedup is 1.0089856x, or 0.89056% fewer cycles. Output words are
bit-exact across all four trials; each trial emits 1024 words, four QBS
commands, one K panel of 1440 bytes, and processes 20 value rows. FCSR=1 and
VCSR=5 throughout. The complete C-call region includes admission, preparation,
execution and scatter, not whole-model execution or C++ dispatch/allocation.

The experiment does not establish a broadly significant Prefill improvement.
Decode's larger gain cannot be transferred to this already value-sharing
schedule. Vector-memory reductions alone do not prove that the critical path
improves proportionally. More scalar work, register packing, per-row softmax
and other costs remain; this pair does not isolate each contribution.

Do not compare its absolute cycle counts against a different executable's
earlier grouped-Prefill mean or multiply those gains. The valid comparison is
the paired baseline in this executable. Baseline repetition range is 485
cycles and candidate range 63 cycles; this small experiment is not a
statistical characterization of all shapes.

Decision: retain the existing production Prefill implementation. Keep this
candidate isolated; do not add a runtime branch or launch a larger format
matrix for this marginal gain. The accepted Decode integration is unchanged.

- ELF SHA256: `7a476f8d0163ceee958754e16d03700e34ae6b6ad39dcb02f26d2311441bc8cf`.
- Receipt SHA256: `8a32db0ca352e08fc676b88a640967066b857d3235fe81cc607a57e900f1fac5`.
- Log SHA256: `97d53be38755ec95088d58d1f02312492b4333fdcb256705f980072b0220836d`.

Replay with `summarize_prefill_pair.py --run <run-directory>` from this
experiment's directory. The replay rechecks sealed source/ELF identities,
protocol acceptance and captured-golden output, not just cycle arithmetic.
