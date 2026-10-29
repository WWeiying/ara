# Remaining QBS headroom after software integration

## New evidence, no new simulation

`verification/qbs/m4_group_sums/projection/analyze_headroom.py` replays the
accepted latest projection's output and command/result-byte checks, independent
UVM receipt, raw-log hash, executable hash and measured counter RTL identity.
It reconciles 256 command records with their four accepted trial records.
The original worker's software identities were verified at collection time;
later reviewed llama.cpp integration changed software. This retrospective
analysis explicitly does not claim all current software hashes still match.

Output: `verification/out/m4-sums-qkv-headroom-20261029-01/result.json`.
The analyzer preserves both paths' real cache statistics. Its internal
normalization uses the older analyzer's `reuse` field only as an ABBA position
label, not as a claim that the new baseline disables reuse. Tests reject
changed trial values, wrong ABBA order and duplicate logs.

## Latest optimized pair

| Quantity | Two candidate trials |
| --- | ---: |
| Complete projection cycles | 1101728 |
| QBS busy | 894825 |
| Dot issue | 786432 |
| Compute without dot issue | 36864 |
| Tiles | 6144 |

For the first candidate trial, QBS busy is 447414, dot issue 393216, and every
issued multiplication slot is populated. Dot issue/busy is 87.8864%; this is
not physical functional-unit utilization. Every tile has six compute cycles
without new dot issue. Strict weight wait, context-start blocked, profile
result blocked and FP-input blocked counters are zero.

There are 221184 correction-pending and 49152 result-pending cycles in that
trial. These are in-flight occupancy, not mutually exclusive stalls. They do
not justify larger buffers. The count of FP entries without schedulable uops
is 6144; this alone does not establish a resource shortage either.

Conditional same-work estimates:

| Idealization | Estimated complete-slice speedup |
| --- | ---: |
| Remove all compute-without-dot-issue cycles | 1.034619x |
| Remove all QBS busy cycles without dot issue | 1.109120x |

Neither is an achievable guarantee or a measured optimization. The second
also removes necessary loads, setup, drain and commit work. The estimates
do not apply to architectural changes that alter work or arithmetic capacity.

## RTL interpretation

`qbs_profile_engine_int.sv` admits a tile only when `compute_active_q` is clear,
the selected context is free, and a narrow tail wave satisfies correction-drain
requirements. Integer completion waits for issue, s0, three-stage dot metadata
and dot output to empty. `qbs_compute_engine.sv` advances tile/bank control only
after that completion. Context validity can persist for correction/result drain.

The waiting is therefore not an arbitrary busy bit. Permitting earlier input
for a new tile requires distinguishing at least three events:

1. The last input read from the old activation/weight bank has been captured.
2. The old tile's final dot and metadata have reached their tagged accumulator.
3. Correction and result consumers have released that context's storage.

Only event 1 can permit reuse of input issue machinery. Event 2 still governs
integer completion, and event 3 still governs context reuse. Collapsing them
would risk wrong metadata, bank overwrite, lost completion or correction-slot
overflow. The M1/M2 subgroup-16 tail guard must not be bypassed.

## Next hardware gate

Before modifying RTL, trace one tile boundary and a narrow-tail boundary using
a focused window: integer start/ready/done, input read bank/address/valid,
s0 valid/context, dot metadata valid/context, dot valid/context, correction
pending/drain, context-valid bits, weight-bank owner and parent FSM/tile index.
The falsifiable hypothesis is that a free second context and captured old
inputs permit the next input issue while the old dot tail drains, without
changing output/correction ordering. If bank ownership or start metadata cannot
support that, reject the shortcut rather than remove safety conditions.

Keep the current dot latency and arithmetic order. Use existing two contexts,
bounded metadata and explicit ownership, not an unbounded queue. First validate
local context/data/completion invariants and faults/reset, then a real-data
complete-call pair. Require a useful net gain; a small estimate alone is not
permission for a risky redesign. No RTL change or new simulation was made in
this analysis, and no PPA improvement is claimed.
