# QBS Decode Root-Cause and Next-Step Decision

## 1. Scope

This audit freezes functional RTL at commit `05ac96ca` and asks one narrow
question: can a small QBS queue, scheduling, or replay-overlap change produce a
model-weighted QBS cycle reduction of at least 10% without changing the current
128-bit memory interface, `N <= 32` result contract, profile semantics, or
ordinary RVV fallback?

The audit does not run synthesis, timing closure, PPA analysis, or place and
route. Its evidence is kept in `qbs_next_step_evidence_20260831/` and consists
of:

- real llama.cpp one-token Decode traces from Qwen2.5-1.5B, TinyLlama-1.1B,
  and SmolLM2-135M at effective KV lengths 16, 128, 512, and 1024;
- a 12-shape set covering 95.00% of nominal projected QBS cycles and 92.23%
  under the recorded Q5_0 sensitivity test;
- current Q4_K and Q6_K RTL runs with strict phase and wait counters; and
- 200-cycle bounded traces beginning at the first integer tile of one real
  Q4_K command and one real Q6_K command.

Measured RTL cycles, model-derived dynamic counts, and calibrated projections
are reported separately. A projection is never described as a measured
full-model RTL cycle count.

## 2. Counter semantics

The command phases are an exclusive and exhaustive partition of QBS busy
cycles. The checked fields are setup, activation, weight, compute, overlap,
drain, scheduler, commit, fault, and terminal. Both current representative runs
satisfy:

```text
sum(command phase cycles) == qbs_busy_cycles
```

`weight_prefetch_wait_cycles` is narrower than general read occupancy. It
counts only `QBS_WAIT_WEIGHT`, entered after the current integer tile finishes
while the next ping-pong weight bank is incomplete. Those wait cycles are
partitioned into exactly one of:

1. no outstanding burst;
2. outstanding burst but no `RVALID`;
3. useful `RVALID && RREADY` transfer; or
4. `RVALID && !RREADY` local receive blocking.

The Q4_K and Q6_K runs also report zero profile-result, FP-slot,
FP-accumulator, FP-input, and AR-ready blocked cycles. Consequently, their
measured steady-state wait cannot be attributed to the FP accumulator or to an
unaccepted address request. Q8_0 is different and is treated separately.

## 3. Static throughput bound

For `M=1`, one tile covers four output rows and one 256-element K block. The
integer engine consumes 32 dot-issue cycles and occupies the compute state for
about 36 cycles after fixed pipeline effects. The current QBS read interface is
128 bits, hence at most 16 payload bytes can arrive per cycle.

For R4 block-major weights:

| Profile | Bytes per row block | Bytes per 4-row tile | Payload floor | Compute interval | Expected steady wait |
|---|---:|---:|---:|---:|---:|
| Q4_K | 144 | 576 | 36 cycles | 36 cycles | approximately 0 |
| Q5_K | 176 | 704 | 44 cycles | 36 cycles | approximately 8 cycles |
| Q6_K | 210 | 840 | 52.5 cycles | 36 cycles | approximately 16.5 cycles |

Ping-pong weight banks already overlap the current tile's calculation with the
next tile's transfer. Increasing outstanding depth can hide request latency,
but it cannot raise sustained payload bandwidth above 16 B/cycle.

## 4. Current measured evidence

### 4.1 Aggregate counters

| Counter | Q4_K, K1536 N1536, context | Q6_K, K8960 N256, direct |
|---|---:|---:|
| Command busy cycles | 105,141 | 143,541 |
| Dot-active cycles | 73,728 | 71,680 |
| Weight bytes consumed | 1,327,104 | 1,881,600 |
| `QBS_WAIT_WEIGHT` cycles | 3,459 | 36,804 |
| Wait with useful R transfer | 1,730 | 34,844 |
| Wait with no outstanding burst | 288 | 280 |
| Wait with no R response | 25 | 40 |
| Wait with local R blocking | 1,416 | 1,640 |
| Setup/scheduler/drain/commit/terminal | 5,136 | 2,848 |
| Activation-context replay | 5,640 | 0 |
| Replay overlapped with compute | 0 | 0 |
| Profile/FP blocked cycles | 0 | 0 |

Q6_K spends 94.67% of its weight-wait cycles transferring useful data. A third
outstanding slot or earlier AR generation cannot remove that sustained
transfer time. Q4_K has little steady-state wait, but command control and
context replay remain visible around an otherwise balanced tile pipeline.

### 4.2 Bounded cycle trace

| Profile | Median complete compute run | Median weight-wait run | R transfer samples | Result |
|---|---:|---:|---:|---|
| Q4_K | 36 | 2 | 184/200 | compute and next-tile transfer are nearly balanced |
| Q6_K | 36 | 19 | 189/200 | weight payload continues well after compute completes |

The trace directly distinguishes payload bandwidth from request-generation
latency. In Q6_K the engine repeatedly computes for 36 cycles, waits 18 to 20
cycles while R beats continue, spends one cycle in `QBS_START_WEIGHT`, and then
starts the next tile. This is the expected signature of the 840-byte tile on a
16 B/cycle path.

### 4.3 Q8_0 boundary

The measured Q8_0 K896 N256 point records 6,209 profile-result/FP-slot blocked
cycles and 1,557 FP-input blocked cycles. Therefore the Q4_K/Q6_K conclusion
must not be generalized to all profiles. Q8_0 has a profile-engine scheduling
issue, but contributes only 2.44% of the nominal three-model QBS projection.
It is a useful format-coverage follow-up, not by itself a path to a 10%
model-weighted QBS reduction.

## 5. Model-weighted workload

The equal-model one-token Decode projection contains 145,760,385 nominal QBS
cycles before crediting cross-operator activation reuse:

| Profile | Projected cycles | Share | Quantization cycles | Weight bytes |
|---|---:|---:|---:|---:|
| Q4_K | 95,947,349 | 65.83% | 5,304,750 | 1,110,638,592 |
| Q6_K | 41,404,228 | 28.41% | 1,795,923 | 516,848,640 |
| Q5_0 | 4,855,507 | 3.33% | 536,772 | 53,678,592 |
| Q8_0 | 3,553,301 | 2.44% | 48,504 | 31,726,080 |

Q4_K and Q6_K account for 94.23% of the projected QBS work. The 12 selected
shapes include all four observed profiles and cover at least 90% under every
recorded Q5_0 calibration sensitivity.

QBS work is invariant with KV length for a one-token Decode graph, whereas
AKV work grows with the active KV. For Qwen, the complete calibrated component
projection is:

| Effective KV | QBS cycles | AKV cycles | Remaining RVV cycles | QBS share | AKV share |
|---:|---:|---:|---:|---:|---:|
| 16 | 97,055,000 | 946,372 | 3,700,824 | 95.43% | 0.93% |
| 128 | 97,055,000 | 2,814,840 | 3,700,824 | 93.71% | 2.72% |
| 512 | 97,055,000 | 10,613,316 | 3,700,824 | 87.15% | 9.53% |
| 1024 | 97,055,000 | 21,011,284 | 3,700,824 | 79.71% | 17.26% |

KV16 and KV128 use measured AKV calibration endpoints. KV512 and KV1024
extrapolate the measured KV128-to-KV256 slope and are not measured full-model
RTL results. TinyLlama and SmolLM2 currently contribute strict dynamic counts
and traffic, but do not have complete shape-matched remaining-RVV cycle
calibration; no complete cycle share is claimed for them.

## 6. Minimal-scheduler screening bound

The screening analysis deliberately overestimates what a small scheduler or
replay change can recover. It assumes all of the following become free:

- every setup, scheduler, drain, commit, and terminal cycle;
- every `QBS_WAIT_WEIGHT` cycle without a useful R transfer; and
- all context replay for every eligible Q4_K/Q6_K shape, using the largest
  measured replay fraction even where a profile-specific context run is not
  available.

For Q5_0, the analysis uses the measured Q8_0 32-element-profile control/wait
ratio as an explicit proxy. Under nominal calibration, this optimistic envelope
is 9.79% of projected QBS cycles, below the 10% implementation threshold. With
Q5_0 cost multiplied by 0.5, 1, 2, and 4, the envelope is 9.70%, 9.79%, 9.96%,
and 10.26%, respectively.

This is not a proof that every imaginable QBS redesign is below 10%. The 4x
Q5_0 sensitivity crosses the threshold, and Q8_0 has a separate profile-engine
bottleneck. It is, however, enough to reject a current RTL change: the nominal
result misses the threshold despite assuming complete removal of cycles that
cannot all physically disappear, while the only crossing point depends on an
unmeasured Q5_0 proxy.

## 7. Decision and action plan

No functional RTL is changed in this step.

The following changes are specifically rejected as unsupported:

- adding another read-outstanding entry;
- changing AR lookahead or timeout values;
- starting a tile from an incomplete weight block without a new streaming data
  contract; and
- changing `N` from 32 to 64 as a parameter-only optimization. `N > 32`
  requires destination register-group allocation, reservation, and multi-VRF
  commit semantics, so it is an ABI and microarchitecture change.

The next non-physical goal should proceed in this order:

1. Add one real SmolLM2 Q5_0 K576 N1536 profile run with strict QBS counters to
   remove the only sensitivity that crosses the decision threshold.
2. Evaluate a coherent activation-stream mechanism, not isolated patches:
   quantize F32 activation blocks directly into an explicit Q8 context while
   the first weight tile is fetched, then chain subsequent `N=32` commands
   without repeated validation and full replay. Existing pointer-based Q8 and
   ordinary RVV paths remain fallbacks.
3. Require a combined model-weighted bound above 10% before implementation.
   Fused quantization alone is insufficient: nominal quantization accounts for
   only 5.27% of the three-model projected QBS cycles.
4. Treat wider or dedicated packed-weight ingress as a separate architectural
   study. It is the only direct way to improve Q6_K steady state, but it changes
   the memory interface and must later be evaluated for timing, area, and
   system bandwidth.
5. Study Q8_0/Q5_0 profile-result blocking separately. Even a large local
   speedup must be weighted by their measured model share before it is promoted
   into the main design.

This plan preserves the nine QBS profiles, activation-context generation
contract, AKV-v2 path, ordinary RVV behavior, and all software fallback paths
until a falsifiable mechanism exceeds the required model-level threshold.
