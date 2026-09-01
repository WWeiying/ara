# QBS/AKV Next-Step Evidence

- Frozen RTL baseline: `05ac96ca86e130972ba0378352a5d86b2c5deb82`.
- Scope: one-token Decode; no synthesis, PPA, timing closure, or place-and-route.
- Nominal optimistic QBS scheduling envelope: 9.791%.
- Required QBS-cycle reduction: 10.0%.
- Decision: `DO_NOT_CHANGE_RTL_FOR_MINIMAL_SCHEDULER`.

The envelope is intentionally generous: it treats every setup/scheduler/drain/commit/terminal cycle, every WAIT_WEIGHT cycle without a useful R transfer, and all eligible activation-context replay as fully removable. It therefore is a screening bound, not an expected speedup.
The Q5_0 proxy sensitivity reaches 10.26% only when its projected cost is multiplied by four. This narrow, unmeasured corner prevents a mathematical impossibility claim, but it also is not evidence for changing RTL; a real Q5_0 profile trace is the required discriminator.

## Bounded cycle trace

| Profile | Compute run | Weight-wait run | R transfer samples | Interpretation |
|---|---:|---:|---:|---|
| Q4_K | 36 | 2 | 184/200 | compute and transfer are nearly balanced |
| Q6_K | 36 | 19 | 189/200 | sustained weight transfer extends beyond compute |

## Context-length projection

Only Qwen has a complete calibrated QBS/AKV/remaining-RVV component projection. Long-KV AKV values are explicitly extrapolated and must not be presented as measured RTL cycles.

| KV | QBS cycles | AKV cycles | RVV cycles | QBS share | AKV share | Calibration |
|---:|---:|---:|---:|---:|---:|---|
| 16 | 97055000 | 946372 | 3700824 | 95.43% | 0.93% | measured |
| 128 | 97055000 | 2814840 | 3700824 | 93.71% | 2.72% | measured |
| 512 | 97055000 | 10613316 | 3700824 | 87.15% | 9.53% | extrapolated_above |
| 1024 | 97055000 | 21011284 | 3700824 | 79.71% | 17.26% | extrapolated_above |

## Action decision

No functional RTL change is justified in this step. A deeper request queue cannot exceed the existing 16 B/cycle R channel, and increasing `N` beyond 32 changes the destination-register/commit ABI rather than merely changing scheduling. The next architectural study should first close the real Q5_0 profile uncertainty, then evaluate a combined activation-quantization/context-fill pipeline with command chaining. Fused quantization alone is not sufficient at model level, even though it occupies 9.7% of the measured Q4 point and 31.0% of the measured Q6 point.

Q8_0 is a separate boundary: its representative run records profile-result/FP-slot blocking, but Q8_0 contributes only 2.44% of the nominal three-model QBS projection. It merits a focused profile-engine study, not a claim that the Q4_K/Q6_K weight-supply diagnosis applies to every profile.

All raw bounded trace samples, strict counter summaries, model/KV counts, sensitivity results, and input hashes are stored beside this file.
