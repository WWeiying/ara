# QBS and AKV Model-Level Closure

## 1. Scope

This closure establishes functional, numerical, coverage, logical-traffic,
and representative RTL-cycle evidence for QBS plus AKV-v2. It deliberately
excludes synthesis, area, power, timing closure, place-and-route, and any claim
that a complete model was simulated cycle accurately in RTL.

The authoritative entry point is:

```bash
python3 hardware/scripts/akv/check-goal-closure.py
```

The checker reads `hardware/scripts/akv/goal-closure-manifest.json`, validates
the raw artifacts, and writes `hardware/qbs_akv_model_closure_20260831/`.
The generated `ablation.csv` and `support_matrix.csv` are derived from the same
checked artifacts rather than manually copied tables.

## 2. QBS Activation Lifetime

The real Qwen trace identifies reusable activations by graph epoch, source
tensor and data object, activation profile, shape, and byte content. Q/K/V and
gate/up reuse is admitted only when this semantic identity is equal; pointer
equality alone is insufficient. The optimized and baseline traces retain an
identical QBS matrix-command stream.

| Metric | Per operation | Cross operator | Eliminated |
|---|---:|---:|---:|
| Quantizations | 394 | 309 | 85 |
| F32 quantization-input bytes | 21,971,968 | 21,449,728 | 522,240 |
| Quantized Q8_K bytes | 6,265,444 | 6,116,524 | 148,920 |

The controlled three-operation RTL workload holds matrix work constant. It
reduces cycles from 48,634 to 25,480 (`1.91x`) and removes exactly 15,792
logical read bytes. The complete Decode projection improves by only `0.94%`,
which bounds the mechanism's model-level importance honestly.

## 3. AKV Shape and Fallback Closure

The derived-real matrix covers:

- head dimensions `64` and `128`;
- GQA ratios `1`, `4`, `6`, and `8`;
- KV lengths `16`, `63`, `64`, `65`, `128`, `256`, and `1024`;
- scalar-reference and ordinary-RVV execution.

All `112/112` case/mode pairs pass. KV lengths around 64 exercise both exact
tiles and tails. SmolLM2 uses GQA ratio 3, which is intentionally unsupported;
all 60 candidates report `fallback_shape`, with no partial AKV execution.

Four real-model RTL leaves additionally prove command and traffic identities:

| Shape | Cycles | Commands | Q bytes | K/V bytes | Read payload | Replay bytes |
|---|---:|---:|---:|---:|---:|---:|
| D64/G8/KV64 | 43,353 | 1,026 | 1,024 | 16,384 | 17,472 | 131,072 |
| D128/G6/KV128 | 52,984 | 387 | 1,536 | 65,536 | 67,136 | 65,536 |
| D128/G4/KV63 | 37,129 | 766 | 1,024 | 32,256 | 33,344 | 129,024 |
| D64/G1/KV65 | 12,742 | 196 | 128 | 16,640 | 16,832 | 16,640 |

For every point, external Query bytes equal `GQA*D*2`, K/V bytes equal
`KV*D*4`, and read payload equals Query plus K/V plus the 64-byte descriptor.
The checker also verifies FULL/REFILL, row/column load, RELEASE, replay, success,
fault, rejection, and final zero-mismatch conditions.

## 4. Real-Model Closure

| Model | QBS profiles observed | QBS nodes | AKV candidates | AKV executed | Explicit fallback |
|---|---|---:|---:|---:|---:|
| Qwen2.5-1.5B | Q4_K, Q6_K | 394 | 56 | 28 | 28 Prefill shape |
| TinyLlama-1.1B | Q4_K, Q6_K | 310 | 44 | 22 | 22 Prefill shape |
| SmolLM2-135M | Q4_K, Q5_0, Q6_K, Q8_0 | 422 | 60 | 0 | 60 GQA3 shape |

Each run contains one Prefill and one Decode graph. The QBS/RVV token and
Top-1 checks pass, QBS-only and QBS+AKV outputs are identical, every selected
QBS profile has zero fallback and zero emulated command, and every non-executed
AKV candidate is explained by one fallback counter.

## 5. Decode Cycle Attribution

The Qwen fixed-prompt Decode trace contains 197 QBS nodes, 28 AKV calls, and
340 calibrated ordinary-RVV nodes. Applying exact activation-lifetime decisions
and representative real-model RTL rates gives:

| Component | Instances | Projected cycles | Share |
|---|---:|---:|---:|
| QBS quantized MUL_MAT | 197 | 97,055,000 | 95.51% |
| AKV-v2 Decode Attention | 28 | 862,958 | 0.85% |
| Remaining ordinary RVV | 340 | 3,700,824 | 3.64% |
| Total | 565 | 101,618,782 | 100.00% |

These are RTL-calibrated component projections. They exclude scheduler,
sampling, operating-system work, and uncalibrated Prefill operators. Exact
dynamic logical traffic for this run is 2,720,342,016 QBS weight bytes,
6,116,524 effective quantized-activation bytes after lifetime reuse, 86,016
AKV Query bytes, and 315,392 AKV K/V bytes.

## 6. Regression and Support Boundary

All nine QBS RTL profiles pass 432 profile cases, and the command, descriptor,
read, commit, context, SRAM-macro-context, and end-to-end fault suites pass.
The formal Q4_K context point is 119,894 cycles versus 119,883 previously
(`+0.009%`); Q6_K remains exactly 208,863 cycles. An ordinary-RVV Attention
leaf also passes with zero mismatch, preserving the fallback path.

AKV-v2 currently admits Decode F32 Query, F16 K/V and mask, F32 output, one
batch, D64/D128, GQA 1/4/6/8, and arbitrary positive KV lengths tiled by 64.
Unsupported GQA, sinks, ALiBi, softcap, incompatible layout, malformed mask,
or unavailable capability returns to ordinary RVV before hidden AKV state is
modified. Generic admitted shapes are correctness-complete but do not imply
the same speedup as the specialized D128/GQA6 arithmetic path.
