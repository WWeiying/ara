# Prefill production-binding RTL acceptance

## Result

Both current-production-binding experiments passed on the same VCS RTL image.
The baseline already uses the shared RVV Q8_0 value decoder. These measurements
supersede the earlier scalar-value-binding experiment for this comparison.

| K / V format | Baseline cycles (A, A) | Grouped cycles (B, B) | Mean A | Mean B | Speedup | Cycle reduction |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Q4_0 / Q8_0 | 174179, 174450 | 147523, 147415 | 174314.5 | 147469 | 1.182042x | 15.4006% |
| Q8_0 / Q8_0 | 179685, 179767 | 149120, 148649 | 179726 | 148884.5 | 1.207151x | 17.1603% |

Trial order is ABBA. Speedup is mean(A)/mean(B), not an average of
individual speedup ratios. Both implementations use the existing QBS hardware;
this experiment measures software scheduling and reuse, not a new RTL feature.

## Workload and scope

Real Qwen3-1.7B captured inputs: query positions 16 through 19, two query heads
sharing one KV head, head dimension 128, visible causal prefixes 17/18/19/20.
Physical KV storage is token-major with eight KV heads and capacity 256.
Each trial produces 1024 FP32 output words. The baseline makes four per-query
Decode calls; the candidate makes one grouped Prefill call.

Cycle regions include the complete C entry call, admission and output scatter.
They do not include GGML C++ dispatch, its allocation overhead, or other model
operators. These ratios are not end-to-end model speedups and must not be
multiplied by the independently measured Decode Register-PV ratio.

## Why reuse helps

`software/akv/experimental/quantized_kv/prefill/prefix_schedule.h` groups QK
requests only when rows have equal visible lengths. It then visits each token
once, decodes its value once, and updates only rows for which that token is
visible. Per-row online-softmax token ordering is retained.

| Measured work per trial | Per-query | Grouped |
| --- | ---: | ---: |
| QBS commands | 4 | 4 |
| K panels | 4 | 1 |
| Q4_0 K copy bytes | 5328 | 1440 |
| Q8_0 K copy bytes | 10064 | 2720 |

The schedule requires 74 value-row visits for independent queries versus 20
for the grouped call. This is reuse of overlapping causal prefixes, not removal
of required QK arithmetic. Copy-byte counters describe software panel copies,
not total AXI traffic. The experiment does not isolate the cycles attributable
to each source of reuse.

## Correctness and identity gates

Both receipts have `state=PASS`, `performance_measured=true`,
`independent_protocol_checked=true`, and `post_pins_match=true`.
Each trial checks output guards, protocol behavior, CSR state and captured
reference outputs; paired outputs are bit-exact. FCSR is 1 in all four trials
of both formats. Maximum absolute differences from the captured model outputs
are 3.5762786865234375e-7 (Q4_0) and 2.477318048477173e-7 (Q8_0).

The independent summary replay rehashed sealed inputs and ELFs, checked the
production RVV value binding, and reran the output checker against the original
log and captured golden data. Both returned `ACCEPTED`.

RTL image SHA256:
`71bb0f7a22208cf9eb02a40298f8b96404eef6724050a86ab685a92958edb565`.

| Evidence | Q4_0 | Q8_0 |
| --- | --- | --- |
| Run directory under `verification/out/` | `prefill-production-q4-vcs-20261028-01` | `prefill-production-q8-vcs-20261028-01` |
| ELF SHA256 | `669e41a0aa21bdfef10b2ea5fa19bb618278f19b2f1c7af49b28639bc8fe6b77` | `9cb226566b8ccfe1fd404ed439dd0dc0a1af94b42b048fe049983af336bd7bb2` |
| Receipt SHA256 | `358e5f7007a12927ae741458a36a5e45344e82486203c3d898b6d40b8b8ae17e` | `9a6d303f409031f2fa320eaa28c664d741e39e07c6e2859bf2b6fdfa01f5cc8c` |
| Log SHA256 | `b6ba6215e3d8d4cd9f85d952f8607d13e566b28a36fb1026216cfbd1cd6a73cb` | `ad0904cb9c5476649ce93e3641bafb18f91a3147ffd49b892821b14fb5a65397` |

Replay from the repository root, substituting q8 for q4 for the second run:

```sh
python3 -B verification/akv/quantized_kv/summarize_optimization_pair.py \
  --run verification/out/prefill-production-q4-vcs-20261028-01 \
  --mechanism prefill
```

## Integration decision

The existing opt-in grouped Prefill path now has a current-RVV-baseline RTL
performance result for both supported K formats. Keep capability and shape
selection and the ordinary RVV fallback. This result does not justify enabling
unsupported masks, dimensions, threading modes or quantization formats.

Register-PV is a separate Decode candidate: its Q4_0 20-token point passed,
while the Q8_0 and shorter-context experiments were still executing when this
record was created. Do not switch the production value path based only on the
first point. Preserve the running experiments' pinned inputs until completion.
