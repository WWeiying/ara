# Whole1134 Continuous History Plan

Read-only analysis of sealed inputs; no simulation or RTL change. This note is
outside `prepared01/` and `vcs_candidate04_01/` and authorizes no launch.

## Exact Remaining Scope

The original loop order is seed, operation, mode, start. `prepared01/tuples.json`
contains 1134 executed tuples and 366 original exclusions at VLENB128. The twenty
partitions retain the tuple multiset and full per-call oracle, but each runs all
three seeds of only one operation after a fresh simulator/runtime start.

Independent adjacency enumeration using `(seed, op, mode, index)` gives:

| Executed-call adjacency | Count |
| --- | ---: |
| Original continuous sequence | 1133 |
| Original edges retained inside partitions | 1074 |
| Original edges missing from partitions | 59 |
| Artificial edges introduced inside partitions | 40 |

The 59 missing edges are the 19 op-to-next-op boundaries in each of three seeds
(57), plus op19/seed0 -> op0/seed1 and op19/seed1 -> op0/seed2 (2). The 40
artificial edges are two same-op cross-seed jumps in each of twenty partitions.
These counts describe adjacent executed calls, not microarchitectural-state
equivalence or accepted DUT results. Partition terminal acceptance is still a
separate prerequisite; no terminal file existed at this analysis snapshot.

The distinction is observable in the source: `original/whole.S` preloads v8-v15
and v24-v31 with EEW8 whole loads before establishing the next call's vtype.
For example, each full-sequence op16 inherits op15's VILL, whereas later seeds
of isolated op16 inherit its own mode3 e64/m1. Resetting input/output and setting
the target vstart/vtype does not recreate predecessor layout, queue, or timing
history. The original 1024-byte input and 1088-byte output checks must remain.

## Bounded Supplemental Regression

After partition terminal audit, the missing 59 edges may motivate a separately
reviewed, bounded supplement. Derive both calls of every pair from the exact
original sequence, including original setup, assembly, input, full output
oracle, vstart readbacks, and intervening original exclusions/control flow.
Do not substitute arbitrary register warmups or altered target instructions.
Record the pair's fresh-start context, exact tuple IDs, and exercised transition.

Such a supplement checks local predecessor effects only. Its first call still
lacks the original earlier history. Passing all 59 pairs must be labeled
boundary-supplement acceptance, never full-history or original Linux closure.
No supplement source, ELF, budget, or launch is prepared by this note.

## Continuous Closure

The existing `prepared01/soc/whole_all.elf` executes all original tuples in order:
SHA256 `1bc25e3b43097c0611fc3307a157460eae1552d4eecef609a795b76073e4a925`.
A separately approved plan should use this unchanged full port once, jobs1,
on the reviewed frozen M4 image, without inter-partition reset or new warmup.
Preserve all original setup, full byte oracle, and 366 exclusions. The continuous
Spike result already passes; it is not a DUT result.

Before launch, pin all consumed inputs, runtime, checker, actual simulator image
and compiled-source identities. Review a checker for exact 1134 target-PC/opcode
retirements in original operation order, per-op counts, complete/trap-free trace,
and exact `RVV_WHOLE_PASS cases=1134 skips=366 errors=0`, case/replay markers,
zero raw exit/tohost and finish. Reject any failure marker, cancellation,
interrupted runner, deadline, pin drift, or inconsistent terminal evidence.
Use a directly owning, bounded service with cgroup teardown and independent
terminal audit; check startup advancement once, not repeated progress polling.

## Budget Prerequisites

Existing full Spike evidence reports `minstret=0x1ff20dd`, or 33,497,309 retired
instructions. At an assumed 500 retirements/second this implies about 66,995
seconds (18.6 hours) serial. **This is not measured full DUT runtime.** The earlier
roughly three-hour estimate divided work among six independent partitions;
that parallel speedup cannot be applied to a single authentic continuous run.

Wait for audited partition results and derive a serial estimate from their
actual elapsed times, retired counts and observed contention. Include explicit
uncertainty plus trace I/O, validation and teardown overhead in separate inner
and service limits. Obtain user budget consideration and parent authorization
before contemplating a long run; do not launch an 18-hour job from this estimate.

Even a passing continuous source port establishes only the original source
sequence on M4. Original Linux ELF/OS execution remains a separate claim, and
the 366 excluded tuples remain excluded rather than newly verified behavior.
