# Separating Shared Scheduling from QBS Contribution

The existing fair-decoder inquiry compares ordinary head-major RVV Attention
against QBS plus shared scheduling. Matching the decoder removes a decoding
implementation difference, but V reuse and QBS still change together. Its
speedup must not be labeled a pure hardware ablation.

A subsequent software-only control should use the identical online shared
schedule and score workspace. Its QK callback loops over the requested heads
and tokens, calls each production scalar-output RVV dot with `nrc=1`, and
stores results at `scores[h * stride + token]`. It reads K through its actual
token/head strides; it must not gather K just to imitate a QBS requirement.
Quantize each Query once and share the same RVV V row across Query heads.

| H6/D128/T128 per Trial | Head-Major RVV | Shared RVV | QBS / Shared |
| --- | ---: | ---: | ---: |
| Query quantizations | 6 | 6 | 6 |
| QK callback calls | 768 | 8 | 8 |
| Scalar-output RVV dots | 768 | 768 | 0 |
| Native QBS commands | 0 | 0 | 8 |
| V row decodes | 768 | 128 | 128 |
| K panels gathered | 0 | 0 | 4 |
| Logical QK outputs | 768 | 768 | 768 |
| PV element FMAs | 98304 | 98304 | 98304 |

Compare shared RVV and QBS/shared in one ELF with repeated paired order;
retain QBS admission and gather costs only where actually incurred. The
software control also needs exact comparison with ordinary head-major RVV,
including final flags. Each head's token order remains unchanged. QBS
arithmetic still needs its own numerical contract; shared scheduling does not
prove that RVV and QBS scores are universally bit-identical.

If the aim is a quantitative three-way attribution, measure H/S/B in the same
ELF. Do not subtract timings from different ELF layouts and call the difference
the isolated V-sharing contribution. This file records the reviewed control
design only; no such result or extra simulation is claimed here. The current
priority is to finish the real-cache latency inquiry and its RTL tail checks.
