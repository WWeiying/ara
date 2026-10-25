# Shared-reader/storage runtime acceptance

This successor records completed raw audits without rewriting inputs pinned by
other workers. It supplements `qbs_akv_resource_acceptance_20261025.md`; historical
pending statements there refer to the earlier checkpoint. Production RTL and
Bender configuration remain unchanged. No synthesis or PPA claim is made.

## Resource change and complete-call results

The candidate shares one physical QBS/AKV read engine and uses a 2 KiB Q store
plus one 32 KiB K/V store. Relative to the original 6 KiB legacy plus 32 KiB v2
payload storage, it removes 4 KiB of logical capacity. The comparison baseline
is the original full QBS+AKV implementation, not ordinary RVV/no-QBS.

| Raw-audited gate | Calls | Command records | Complete-call result |
| --- | ---: | ---: | --- |
| Shared reader only, Prefill | 4 | 13380 | Every call cycle-identical |
| Shared reader + unified storage, original Decode | 12 | 3680 | Outputs/CSRs/counters identical; original fixture has no complete-call timer |
| Shared reader + unified storage, timed Decode successor | 12 | 3680 | Every call cycle-identical |
| Shared reader + unified storage, Prefill | 4 | 13380 | Every call cycle-identical |

Timed Decode covers D64/H3/T1, D96/H3/T65, D128/H6/T7 and D128/H2/T64,
each with paired-head selection OFF/ON/OFF. Both images execute the same ELF,
SHA256 `9eb83100b745d0d70a7f9493d04feafca90365030830c38c6f219163fb98b5b8`.

| Decode case | Original cycles, OFF/ON/OFF | Unified cycles, OFF/ON/OFF |
| --- | --- | --- |
| D64/H3/T1 | 8710 / 8206 / 8360 | 8710 / 8206 / 8360 |
| D96/H3/T65 | 30774 / 25349 / 30798 | 30774 / 25349 / 30798 |
| D128/H6/T7 | 13629 / 13545 / 13471 | 13629 / 13545 / 13471 |
| D128/H2/T64 | 19517 / 14217 / 19476 | 19517 / 14217 / 19476 |

The existing real four-query/nine-head Prefill slice is not a full-model run.
Its four OFF/ON/ON/OFF calls are 202315 / 190069 / 190352 / 201779 cycles on
the original, shared-reader-only and unified-storage images alike. Source/image
pins, raw output/CSR records, command ledgers and independent protocol receipts
were rechecked rather than accepting worker PASS labels alone. Numerical scope
remains that of the original fixtures; protocol checking is not a separate
full-Attention mathematical oracle.

Portable summary:
`verification/akv/results/shared-storage-runtime-closure-summary-20261025.json`.
It records every measured call and binds the four full audit receipts by SHA256.
The detailed timed audit retains both raw command ledgers locally; its larger
receipt is not duplicated into the portable summary. Do not add repeated runs
of the same fixture as independent workload coverage.

## Quantized-KV tail aggregation correction

All four Q4/Q8, 5/33-token tail workers passed their original raw checks. The
first fast-hex coordinator then failed aggregation, before launching downstream
simulations: the old combiner incorrectly required identical Query bytes across
independent Q4 and Q8 model captures. Different earlier generated tokens make
these activations legitimately different. This was not an RTL mismatch.

The successor binds each profile's exact F32 capture to its ELF Query data and
linked production quantizer, and reconstructs the exported quantization for the
captured finite-normal domain. Within-profile prefix identity is required;
cross-profile equality or inequality is not. Individual raw, golden, QK,
protocol, image and source-pin checks remain intact. The four tests are not
rerun, and failed historical receipts are not overwritten.

`combine_v2.py` and the V3 routing have 14 passing host tests. The fresh
coordinator input inspection completed with
`INSPECTED_NOT_WAITED_NOT_LAUNCHED`. The independent background service is:

```text
akv-quantkv-tail-fasthex-v3-coordinate-20261025-01.service
```

Its actual Python owner, PID 1200775, was confirmed in the matching systemd
control group. This is preparation/queue ownership, not confirmation that a
downstream VCS simulator has started. Its output is
`verification/akv/quantized_kv/tail_split/out/coordinator-fasthex-v3-01/`.
After checked aggregation and both preflights, it can launch the two same-ELF
H/S/B/B/S/H attribution runs. Each simulator keeps the 10800-second bound.
The fast hex formatter only reduces untimed printing cost, not kernel work.

## Remaining gates

1. Complete legacy-engine accept/first-valid/terminal-fire latency comparison.
   Its first attempt stopped on a compilation-warning contract, before any
   simulation; preserve the failed attempt and admit no unrelated warnings.
2. Finish shared-reader quantized-KV real-input regressions and H/S/B attribution.
   Do not infer performance from preparation, partial logs or service creation.
3. Once live canonical source-pin consumers finish, promote the reviewed RTL,
   support modules and build graph coherently and test the actual canonical
   configuration. Snapshot acceptance does not prove production promotion.
4. Continue runtime/model and attribution requirements in
   `qbs_akv_efficiency_execution.md`; this resource checkpoint does not complete
   the full prioritized objective. Native F16 whole-GGML/model execution remains
   distinct from these real-input slices.
