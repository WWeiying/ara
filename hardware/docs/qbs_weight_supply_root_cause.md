# QBS Decode Weight-Supply Root-Cause Audit

## 1. Scope and evidence

This note records the static and measured evidence used to decide the next QBS
optimization. It is intentionally separate from the activation-context feature
commit and does not change RTL.

The measured rows come from `hardware/format_closure.csv`, generated at commit
`d4fc0032`. The current branch retains the same weight-buffer, dot scheduling,
and read-engine behavior; later changes only removed dynamic rounding state and
added activation-context control. The representative workload is real
Qwen2.5 `blk.0.attn_q.weight`, `M=1`, `N=256`, with Q3_K/Q5_K/Q6_K using
`K=1536`.

The evidence uses counters with strict event semantics:

- `qbs_weight_prefetch_wait_cycles` counts only cycles in
  `QBS_WAIT_WEIGHT`, after the current tile has completed while the inactive
  weight bank is still incomplete.
- `qbs_phase_compute_cycles + qbs_phase_overlap_cycles` is the time spent in
  `QBS_COMPUTE_TILE`; the second term differs only in whether a read is active.
- `probe_weight_wait_r_transfer_cycles` counts wait cycles with an outstanding
  read, `RVALID`, and `RREADY`. It therefore means that useful AXI R transfer is
  occurring, not that the read engine is idle.
- `probe_weight_wait_no_outstanding_cycles`,
  `probe_weight_wait_response_idle_cycles`, and
  `probe_weight_wait_r_blocked_cycles` distinguish missing requests, memory
  response gaps, and local receive backpressure, respectively.

## 2. Static throughput bound

For `M=1`, one physical tile contains four output rows and 256 K elements per
row. The 32-pair dot array processes `4 rows x 8 K positions` each cycle, so the
dot portion requires 32 cycles. Measured `QBS_COMPUTE_TILE` occupancy is about
36 cycles per tile after pipeline and result-drain overhead.

The QBS AXI data width is 128 bits, or 16 B/cycle. A native R4 tile therefore
has the following unavoidable payload-transfer time:

| Profile | Bytes/block | Bytes/4-row tile | Minimum transfer | Measured compute interval | Predicted steady wait | Measured wait/tile |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Q3_K | 110 B | 440 B | 27.5 cycles | 36.0 cycles | 0 | 0.00 |
| Q5_K | 176 B | 704 B | 44.0 cycles | 36.0 cycles | 8.0 cycles | 8.52 |
| Q6_K | 210 B | 840 B | 52.5 cycles | 36.0 cycles | 16.5 cycles | 16.44 |

The prediction uses `max(transfer_time - compute_interval, 0)`. Its close match
to measurement is the central result: Q5_K and Q6_K are limited by sustained
128-bit weight payload bandwidth in Decode, while Q3_K can hide its complete
tile transfer under computation.

## 3. Alternative hypotheses rejected by counters

For Q5_K, 3273 total weight-wait cycles are classified as 2937 cycles with an
R transfer, 284 cycles with R blocked, 48 cycles with no outstanding request,
and 4 response-idle cycles. For Q6_K, 6313 cycles are classified as 5977, 282,
48, and 6 cycles, respectively.

Consequently:

- **Insufficient AR lookahead is not the main cause.** Missing-outstanding and
  response-idle cycles are below 1% of total wait.
- **AXI address acceptance is not the cause.** The recorded AR-ready blocked
  count is zero. A full two-entry outstanding queue mostly means the R channel
  is already servicing useful payload.
- **The block adapter is not the main cause.** R-blocked and data-sink-blocked
  activity is small relative to cycles in which data transfers successfully.
- **A third outstanding slot cannot remove the steady-state gap.** It may hide
  a few startup cycles, but it cannot deliver more than 16 payload bytes per
  cycle over the existing R channel.
- **Fine-grain same-tile start has only a bounded tail benefit.** Ping-pong
  buffering already overlaps one tile's computation with the next tile's
  transfer. Starting computation before a tile is complete cannot change the
  steady-state `max(transfer, compute)` bound and can only reduce command or
  K-block startup/tail bubbles.

Changing timeout values, queue depth, or lookahead policy is therefore not a
valid Q5_K/Q6_K performance fix without evidence of a different bottleneck.

## 4. Architectural consequences

There are only three ways to materially improve M1 Q5_K/Q6_K steady-state
throughput:

1. increase effective weight bandwidth, for example with a wider or dedicated
   data path;
2. reduce bytes transferred per useful weight, which means a different model
   format or an additional lossless representation with demonstrated benefit;
3. reuse each fetched weight across more activation contexts, as Prefill does.

The third case explains why `M=4` is structurally different: the same weight
tile supports four activation rows, extending useful computation from roughly
32 to 128 dot cycles while transfer remains unchanged. Decode `M=1` has no such
in-command weight reuse.

## 5. Ranked next experiments

The next implementation should target overhead outside this proven bandwidth
floor rather than perturbing the working weight scheduler.

1. **Cross-operator activation lifetime reuse.** First trace whether Q/K/V and
   gate/up consume the same quantized activation object within one graph epoch.
   If confirmed, retain the existing explicit context across those operators
   and eliminate repeated quantization plus repeated activation traffic. This
   has model-level scope and does not alter weight numerical order.
2. **Larger output command tiles.** The current `N=32` limit causes repeated
   setup, context replay, and commit. A dynamic `M x N <= 128` contract could
   use the existing 128-result accumulator capacity, but it requires an
   explicit destination-register-group field and full VRF reservation/commit
   validation. It must not be inferred from unread descriptor memory.
3. **Format-aware range coalescing for 32-element formats.** Q8_0 issues many
   short 4-row ranges and shows scheduler/response-gap overhead not present in
   Q5_K/Q6_K. A separate contiguous-layout or stream-buffer experiment is
   justified for Q8_0/Q4_0/Q5_0/IQ4_NL; it must not be presented as a Q6_K
   bandwidth fix.
4. **Wider context replay.** The four physical activation SRAM macros have
   unused width/capacity, so a padded four-bank layout can reduce internal Q8_K
   replay cycles without adding macros. Its Amdahl bound is only the measured
   context-replay fraction, so it ranks below cross-operator reuse unless new
   traces show replay on the critical path.

Before any RTL change, experiment 1 must log activation identity, profile,
shape, graph epoch, quantization count, and QBS command sequence. The
falsifiable condition is that repeated operators use byte-identical Q8 data
with a lifetime that software can delimit. If that condition is absent, the
mechanism must not be implemented by pointer or address matching.
