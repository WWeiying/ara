# Complete Q/V/K projection gate

The preparation-only RTL gain is 1.7114x. This successor measures its net effect
on the complete accepted Qwen2.5 projection slice, not a product of ratios.

Both ABBA paths use the same exact-byte activation cache. Each trial has one
cold production, two hits, one fill and explicit release. Only the cold producer
changes from the current packed RVV quantizer to the parallel group-sum version.
The cache does not persist across trials. Namespace producer labels do not
permit reuse between numerically unverified producers.

Work is M=4, K=1536, with Q/V/K output widths 1536/256/256. Q and K use Q4_K;
V uses Q6_K. Every trial computes all 8192 FP32 outputs using 64 QBS commands.
All four trials retain packed-byte equality to the accepted golden, per-output
model-reference tolerance checks, bit-exact paired outputs, FCSR/VCSR equality,
input/weight integrity, output guards and SDK/plan status checks.

The separate trace checker requires exactly 256 native M4 commands and 512
result bytes per command, without duplicate or missing result byte addresses.
Independent UVM protocol acceptance and immutable input/image checks are also
required. A preparation-only or functional-only log cannot satisfy this gate.

`build.py` uses the old archive for command recipes, data and golden identity;
it recompiles all 12 bare-metal objects from their current sources. It does not
reuse archived RTL or quantizer object files. Compilation uses production-style
FP contraction equally for both candidate and baseline.

The standalone preparation result used a smaller program and must not be
subtracted directly from earlier projection timings to claim measured gain.
Only paired timing from this executable is accepted. Until final validation,
the production quantizer and hardware remain unchanged.

## Accepted result

`verification/out/m4-sums-qkv-vcs-20261029-01` completed PASS. Independent
replay verified all 1040 sealed inputs, reran the numerical/activity and result
trace checkers, and confirmed the independent UVM result. All trials have
FCSR=17, VCSR=5, two cache hits, one miss, one store and zero errors.

| Path | Trial total cycles | Paired total | Mean |
| --- | --- | ---: | ---: |
| Current packed producer + reuse | 583574, 582025 | 1165599 | 582799.5 |
| Parallel group sums + reuse | 551126, 550602 | 1101728 | 550864 |

Full-slice speedup is **1.0579735x**, with **5.47967%** fewer cycles. This is
the measured incremental gain above the current packed producer and reuse,
not the gain over ordinary RVV or an end-to-end model speedup.

| Mean phase cycles | Baseline | Candidate |
| --- | ---: | ---: |
| Admission | 6219.5 | 6114.5 |
| Preparation, including cache handling | 97447.5 | 65924.5 |
| QBS execution interval | 478183.5 | 477909 |
| Complete slice | 582799.5 | 550864 |

The preparation reduction is consistent with the intended change, while
execution remains nearly unchanged. Preparation here includes cache lookup,
copy/fill/release work; it is not the same region as the standalone quantizer
timing. Phase means are diagnostic and must not be turned into a claim of
precisely isolated causal contributions.

The trace checker accepts exactly 256 M4 commands across the four trials and
131072 written result bytes, with no missing or duplicate result positions.

- ELF SHA256: `ef66be1e29bae12c63dd780b296bec441a348e6c608bdb2202daa8ca64556a60`.
- Result SHA256: `7e91adb371f8e126b7d978ae240534c4ac838c3ee634b1ae700e7623007d902f`.
- Log SHA256: `f9026d5ccb0bd042a1a92b68f44cc926e9d87ac710871dedf9f4bfb2351a7921`.

Decision: the complete-call gain warrants llama.cpp integration after preserving
the measured preimage and repeating model-level byte/logit/CSR regression.
No wider dot array, deeper queue or new instruction is justified by this
software result. Production integration is a subsequent gate, not implied by
this standalone acceptance.
