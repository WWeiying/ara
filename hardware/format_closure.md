# Real-model RVV/QBS format closure

All points use one captured decode activation and the first 256 output rows of `blk.0.attn_q.weight`. Both paths passed the same llama.cpp golden with zero mismatches. Offline weight repacking is excluded.
All RVV points use simulator image `3350e0289a7c4365287fd0340439a2483f7408d1c94171b915daf4b8777b6ebe`; all QBS points use `40ff01f6c00587a04965ff7bf97b242462225f4557e4f96b70e7f1933ef50d8e`.

| Format | KxNxM | Compute speedup | Matmul speedup | Logical read reduction | QBS dot active | QBS input phases | QBS read-full | QBS response idle |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Q3_K | 1536x256x1 | 44.20x | 72.73x | 69.7% | 70.7% | 16.0% | 64.1% | 3.9% |
| Q5_K | 1536x256x1 | 60.61x | 92.49x | 59.9% | 57.2% | 31.7% | 69.5% | 3.0% |
| Q6_K | 1536x256x1 | 34.96x | 50.69x | 55.9% | 49.4% | 41.4% | 72.6% | 2.7% |
| Q8_0 | 896x256x1 | 17.31x | 20.38x | 48.1% | 26.9% | 37.2% | 36.4% | 17.3% |

Across these four representative points, the geometric-mean speedup is 35.68x for dynamic quantization plus matrix computation and 51.34x for the matrix phase alone. These are operator-slice results against the standard RVV path, not an end-to-end model speedup.

## Bottleneck evidence

| Format | K blocks | QBS quant share | Weight-prefetch wait | Profile-result blocked | FP-input blocked | FP uops/output |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Q3_K | 6 | 39.6% | 0.0% | 0.0% | 0.0% | 18.0 |
| Q5_K | 6 | 34.7% | 15.2% | 0.0% | 0.0% | 36.0 |
| Q6_K | 6 | 31.6% | 25.4% | 0.0% | 0.0% | 18.0 |
| Q8_0 | 28 | 15.7% | 17.1% | 23.3% | 5.8% | 84.0 |

## Measured signatures

- Pair utilization is 100% for every format, so the measured QBS commands do not lose work to partially filled arithmetic pairs.
- `Q6_K` spends the largest fraction in activation/weight input phases (41.4%). This is phase occupancy, not a stall classification.
- `Q8_0` has the lowest dot-active fraction (26.9%); this metric is reported together with input and read-state counters rather than being treated as a standalone execution-unit utilization claim.
- `Q8_0` has the largest read-response-idle fraction (17.3%), which identifies the format most exposed to response gaps in this workload.
- Q5_K and Q6_K expose increasing weight-prefetch wait as native block size grows. Q6_K combines 25.4% weight-prefetch wait with 72.6% read-outstanding-full activity and only 2.7% response-idle activity; the evidence points to weight-stream service/serialization rather than an empty request pipeline.
- Q8_0 has 28 K blocks per output instead of 6 for the K-quant points. Its 23.3% profile-result-blocked and 5.8% FP-input-blocked activities, together with 84 FP uops per output, show that frequent per-block result scaling/accumulation and fragmented input service limit the dot array; increasing dot width alone would not remove this bottleneck.
- FP-table-full and commit-backpressure counters are zero for all four points. The listed block signals can overlap in a cycle and are diagnostic activities, not an additive stall decomposition.
- Compute speedup includes dynamic activation quantization; matmul speedup isolates the quantized matrix phase. QEMU emulation is excluded from all cycle comparisons.
