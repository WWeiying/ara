# Audit Efficiency Review

Static finding confirmed, not a new raw traversal or measured profiling claim.
The frozen `audit.py:137-140` calls `finish_call()` on every scalar input/output
initialization store while the previous completed `active` remains installed.
`finish_call` constructs `set(range(1088))` and compares full read coverage each
time. Actual O2 Spike disassembly has byte stores at0x800001f6 (1024 iterations)
and0x8000021a (1088 iterations). The first call initializes with active=None;
the1133 following transitions therefore cause2392896 redundant complete-call
checks. Their range construction alone handles2603470848 elements; full-set
comparison adds another comparable traversal. This is a concrete avoidable
complexity issue, not proof that it is the only contributor to audit latency.

## Narrow Successor Conditions

Hilbert owns implementation and Host tests; this reviewer does not duplicate
them. Preserve the old audit/source/raw/bounds and any actual timeout outcome.
Build the expected read set once. On first successful completion of one call,
perform every original check and freeze coverage as an immutable frozenset.
Retain a strong reference to the exact active object and frozen reads object,
plus the validated status signature (ordinal/start/returned/CSR values/preload
count/store count). Subsequent checks must require the same identities and
unchanged signature in constant work; a bare cached=true bypass is unsafe.
New active object means fresh validation, never inherited acceptance.

The existing per-read range/value/duplicate check remains before adding a read.
A frozen set cannot silently accept new reads. Any attempted mutation or
replacement of the frozen coverage, changed completion state, or early write
must reject, not fall back to trusting the cached result. Do not hash/compare
all1088 elements again on every cached check, which would retain the problem.
Do not change helper/tuple/console/exit/oracle checks or add data exemptions.

## Required Host Discriminators

1. Complete valid call; repeated post-completion finish checks accepted, with
   one full-coverage validation for that call.
2. Missing first/interior/final oracle byte, including a missing guard: reject.
3. Duplicate read through the actual per-read path: reject before completion.
4. Input/output initialization write before previous call's return or full
   reads: reject through the actual write-to-finish path.
5. After caching, replace coverage or alter returned/CSR/start/preloads/stores:
   reject. Frozen collection mutation cannot succeed silently.
6. A new incomplete active with identical ordinal/tuple values cannot reuse
   the previous active's cache. A valid next call revalidates normally.

These are small Host checks, not another full reference/raw parse. Host results
are pending Hilbert's implementation and actual test receipt at this review.

## Execution Decision

Wait for the original bounded audit's actual numeric terminal receipt. If it
passes, retain acceptance and do NOT reparse raw for this optimization. Only an
actual timeout permits consideration of one independently pinned successor
offline audit on the same immutable raw, after Host strictness review. No new
Spike execution, raw mutation, automatic retry or DUT launch is authorized by
this review. Continuous-DUT budget remains separately HOLD above3h.
