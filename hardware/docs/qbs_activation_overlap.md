# QBS next-block activation overlap

## Scope and hypothesis

Baseline: `03743c61`. This experiment changes no ISA, descriptor, arithmetic,
weight layout, activation quantization, or result-commit rule. AKV is separate.

The compute scheduler clears both activation banks at every K-block boundary.
M <= 4 uses only the first bank; the other bank is reserved for the second
context wave of M = 5..8. Consequently each new K block waits for activation
reads even when its predecessor has many weight tiles left to compute.

Hypothesis: reuse the idle activation bank for the next K block of a DIRECT
M <= 4 command. With weight reads taking priority over speculative activation
reads, activation loading can overlap existing work without adding payload
SRAM, arithmetic units, memory traffic, or changing accumulation order.

## Design

- Each accepted command selects one mode: context waves for M = 5..8, or
  alternating K-block banks for eligible narrow commands. Context FILL,
  REUSE and RELEASE retain their existing scheduling.
- Activation requests have an independent K cursor, separate from weight-row
  advancement. Returned beats retain their accepted K tag. K parity selects
  the bank only in alternating mode.
- A block is ready only when all required bytes have committed and ingress
  writes have drained. The current read bank cannot be overwritten.
- At a K transition, clear the retired bank, not the prefetched bank. Keep
  the existing weight ping-pong policy and synchronous SRAM read latency.
- Each adapter has separate weight and activation SRAM planes. A weight read
  and an activation write in the same adapter do not compete for one SRAM
  port. The activation read and write must still target different adapters
  during computation; the accepted-response assertion checks this explicitly.
- Next-block requests are bounded by the command's K dimension. Current
  activation takes priority; speculative activation is issued only when no
  weight range is eligible. Shared AXI responses must not wait on a bank that
  cannot drain independently of the active compute tile.
- Faults stop admission, drain accepted arithmetic and memory work, and clear
  both banks before another command. No partial result is committed.

## Evidence and acceptance

Use the existing full QBS command testbench, not a replacement arithmetic
model. Compare baseline/candidate using identical vectors and AXI/commit
backpressure. Check every result bit, fflags, traffic, dot issue count, and
atomic failure behavior. Add next-block MMU/AXI/PMA fault followed by replay.
Real-model Q4_K/Q6_K slices retain their full reduction dimension. M=5..8 and
context-reuse tests are required controls.

Record cycles, activation-wait cycles, accepted next-block beats during
compute, and ready-at-boundary events. These are command-level results, not
end-to-end model speedups. Historical M4 activation wait is about 6.5% of
command cycles; eliminating it is an upper bound, not a promised gain.

Do not merge until correctness and performance measurements are available.

## Ownership and ordering invariants

| Situation | Read bank | Allowed activation writes | Clear action |
|---|---|---|---|
| Narrow DIRECT command | Current K parity | Current incomplete block or next block only | Both at command start; retired bank at K transition |
| Narrow context command | Bank 0 | Existing replay/fill path | Both at each K transition |
| Wide M5..8 command | Context wave 0 or 1 | Existing M8 layout fans out into both banks | Both at each K transition |
| Fault | No new computation admitted | No new compute-buffer writes | Both after arithmetic drains |

The activation cursor changes only with the requested activation K block.
Advancing to another group of output columns must not reset this cursor.
Byte-offset multiplication remains registered before address formation.
The accepted response tag, not the current scheduler state, selects a narrow
command's write bank. A complete block is never written again. The last K
block cannot request K+1, including K=255 in a 256-block command.

The optimization does not reorder reductions, introduce approximate arithmetic,
or change the FP accumulator. It changes when existing bytes reach storage.
Two activation banks already exist; their word count, width, ports, and the
integer/FP arithmetic resources are unchanged. Added control includes a mode
bit and an independent 8-bit activation scheduler cursor. Physical area and
timing have not been measured for this change.

## Reproduction

From the feature worktree, run:

```bash
python3 verification/qbs/run_activation_overlap.py \
  --output /absolute/new/output-directory \
  --real-root /home/wangwy/openproject/ara_dsa/hardware/timing_control_20260916/real
```

The runner builds the same RTL and testbench with activation lookahead disabled
and enabled. It writes `status.json`, `comparison.json`, input copies, source
hashes, a tracked diff, and separate compile/simulation logs. Each run has its
own directory. Failed, incomplete, or source-drifted runs are not accepted.
The real vectors are retained Qwen2.5 captures, not Qwen3 measurements.

The 36 functional vectors cover all nine supported weight profiles, row-major
and packed layouts, M1..8, N tails, multiple K blocks, and the 256-block limit.
Both fast responses and two idle cycles between response beats are tested.
Additional tests check activation context FILL/REUSE/RELEASE, atomic faults,
three next-block fault sources, reset during a second-block response, and
successful replay after every injected interruption.

For cycle-level evidence, the testbench accepts `+QBS_ACTIVATION_TRACE` (first
400 command cycles only) and `+QBS_REQUIRE_ACTIVATION_OVERLAP`. The trace records
command cycle, compute K, requested activation K, accepted range role/tag,
integer tile start, read bank, and completion bits. `ahead_beats` counts accepted
activation beats for K+1; `overlap_beats` further requires the compute phase;
`ready_boundaries` counts K transitions at which activation is already complete.

## Deliberate limits

This is a command-local delivery optimization, not a larger activation cache.
M5..8 needs both banks for current operands and therefore retains its context
wave schedule. Context FILL/REUSE/RELEASE is deliberately unchanged. That
exclusion limits the decode benefit when the runtime already reuses an M1
activation context, but avoids weakening its generation and recovery rules.

All accesses still use the translated QBS reader and its memory-order gates.
If more than one address would fault, prefetch may expose a different failing
address of the same command first; no partial architectural result is allowed.
The focused memory model is not a DDR performance model. Whole-model gains,
ordinary RVV coexistence in a rebuilt SoC, FPGA behavior, and physical results
remain separate integration checks.

## Measured command-level results

VCS, four lanes, VLEN=1024, identical captured vectors and memory model. The
off/on comparison is stored in
`ara_dsa_signoff_integration/verification/out/qbs-activation-overlap-20261022/paired_01/`.
The original `03743c61` image also reproduces the Q4_K M4 baseline of 7304 cycles.

| Format | M | N | K | Before (cycles) | After (cycles) | Cycle reduction |
|---|---:|---:|---:|---:|---:|---:|
| Q4_K | 1 | 32 | 1536 | 2287 | 2264 | 1.01% |
| Q6_K | 1 | 32 | 8960 | 17813 | 17709 | 0.58% |
| Q4_K | 4 | 32 | 1536 | 7304 | 6939 | 5.00% |
| Q6_K | 4 | 32 | 8960 | 42536 | 40053 | 5.84% |
| Q4_K | 8 | 16 | 1536 | 7742 | 7742 | 0.00% |
| Q6_K | 8 | 16 | 8960 | 45090 | 45090 | 0.00% |

In Q4_K M4, activation-wait cycles fall from 474 to 79; all five intermediate
K boundaries already have complete activations. In Q6_K M4 they fall from
2766 to 79; all 34 intermediate boundaries are ready. Accepted next-block
beats during compute are 355 and 2414 respectively. Weight bytes, activation
bytes, payload bytes, logical read ranges, dot cycles, results, and fflags
are unchanged. The M1 gain is smaller because activation reads still share
the translated reader with weight traffic; removing an activation wait does
not remove the corresponding memory bandwidth demand.

The paired run passes 36 functional cases under each of two response timings
for each setting, plus fault/context/recovery tests and the six real-data
commands. None of the 72 functional comparisons increases cycles. All M5..8
controls are cycle-identical. The standalone compute-engine API test passes
36 cases as well. Final constant-index payload selection passed replay against
the accepted on-mode logs in `final_replay/`: all eight groups match every
reported counter and PASS record, not merely the final output. The source
hashes in that replay were rechecked before committing this baseline.
