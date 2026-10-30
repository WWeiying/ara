# Prepared activation reuse after parallel quantization

## Decision

Keep exact-input prepared-cache reuse. On the captured four-row K=1536 input,
reuse remains substantially cheaper than three parallel quantizations. This
does not justify dropping byte comparisons, weakening graph lifetime guards,
or claiming a new optimization: both paths already exist.

## VCS measurement

The accepted retirement SoC image runs a single ELF with four ABBA trials.
Both paths produce three independent 7008-byte outputs from the same real
model activation; the same parallel quantizer is used throughout. Cache fill,
lookup, byte comparisons, copies, fflags restoration and final release are
inside the measured preparation region. Numerical checking and prints are
outside. No matrix computation is executed in this experiment.

| Path | First trial total | Second trial total | Mean cycles |
| --- | ---: | ---: | ---: |
| Three quantizations | 135884 | 135797 | 135840.5 |
| One quantization, two cache hits | 66802 | 65878 | 66340 |

Preparation speedup is 2.047641x; cycle reduction is 51.163313%. This cannot
be multiplied into the earlier full-projection speedup: that measurement
already used the cache on both sides. Nor is this a full-model speedup.

| Per-consumer cost | Direct mean | Reuse mean |
| --- | ---: | ---: |
| First, including cache fill when enabled | 45344 | 51773 |
| Second | 45163.5 | 6878 |
| Third, including release when enabled | 45153 | 7495 |

The reuse path spends approximately 6429 extra first-call cycles, then saves
approximately 38285.5 and 37658 cycles on later calls. These are complete-call
differences, not isolated allocator or comparison latency. Small loop/timestamp
overhead means the sum of phase times is less than total time.

Each reuse trial records one producer, one miss, one store, two hits, 49152
requested comparison bytes and 45600 copied payload bytes. Those counters are
not physical bus traffic. Consecutive preparation calls also lack intervening
matrix work, so they are not a replacement for full operator measurements.

## Correctness and identity

All three outputs per trial match every byte of the independent captured golden.
Canaries and original input remain intact. All four signatures are
`11063712579336838553`, FCSR=17, VCSR=5, errors=0. Source/image pins match after
execution. Independent protocol checking passes with no issues:

- 35783 requests and responses; zero outstanding or protocol errors.
- 26588 backend allocations and completions.
- 5351 completed AXI reads; zero pending.
- 3322 matched AXI write bursts and B responses; zero pending.

Evidence under `verification/out/cache-cost-vcs-20261029-01/`:

- `result.json`: SHA256 `adc909d128e352f15e4da1ab0588d6d2b7313164a07b44554dd0405fefbc90a8`.
- `work/run.vcs.log`: SHA256 `d0640d81f3ecdd1bd512ebe403548adb0fc2ff69e855eeb310780d9ac374d6d3`.
- `work/uvm_result.json`: independent transaction checks.

ELF SHA256: `ad270cbbd9a052597b3dc2de90f0f30e4f2cbe8e2c239a91b49a74a113601d18`.
Sources/build/checker: `verification/qbs/cache_cost/`.

## Next decision

Further cache tuning has a smaller remaining budget than the quantization
already eliminated. Prioritize full GGML call-level attribution and selection
coverage, keeping the proven cache and shared quantizer unchanged. Prefill
allocation overhead remains unmeasured; this experiment says nothing about it.
