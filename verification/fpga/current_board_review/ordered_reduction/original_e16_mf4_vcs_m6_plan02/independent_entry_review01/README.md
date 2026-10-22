# Independent entry review — M6 e16/mf4 plan02

**CLEAR / NO BLOCKER for this exact successor plan.** The predecessor's P2
alternate-helper interior gap is closed in plan02. This is independent code/
checker review clearance, **not launch authorization** or current resource/
service admission. Parent retains launch authority.

Reviewed plan SHA256:
`51711836aab45fa44a34f16e80801fb9ac0dbf2412cf6660577e0737c17f013c`.
All **738 successor pins** matched independent hashes before and after review.
All **733 predecessor pins** were separately verified unchanged. Predecessor
plan SHA remains
`a9a60cc30f3d88d4b15441ec3d2da2bd7367f9334c9cb36731b262bbade50d3e`.
`PREDECESSOR_STATUS.json` records NOT_ADMITTED_CHECKER_GAP separately; neither
the old seal nor its independent finding/evidence was changed or cleared.

Only this directory and owned temporary host fixtures were written. No DUT,
Spike/reference run, compiler/build, producer prepare/run, service launch or
live process/service/resource query was performed. Host fixtures copy existing
ELF bytes and produce synthetic checker protocol records; they do not execute
that ELF or claim a new architectural result.

## Finding disposition and scope repair

No open blocking findings identified.

The complete op_1 and op_2 half-open PC ranges are derived from their pinned
21-instruction windows (`../checker.py:45–50`) and rejected before any phase
or target accounting (`:133`). Their final compressed returns are included.
The prior entry-only exclusion has therefore been replaced by complete range
exclusion, covering integer/CSR/vector/load/store/return interiors.

The original two counterexamples were independently rebuilt from the full
positive host fixture and inserted after all144 original oracle bytes, before
CTRL exit. Matching CVX transport remains present; the generic validator still
accepts the protocol. The successor now rejects both through **strict checking
and the complete artifact gate**:

| Former false-PASS retirement | PC / encoding | New strict and artifact result |
| --- | --- | --- |
| op_1 interior vfredmin | `0x80000754` / `14881c57` | REJECTED: Unused helper PC range |
| op_2 interior vfredmax | `0x800007a4` / `1c881c57` | REJECTED: Unused helper PC range |

All **42 instruction PCs** across the two unused helpers were independently
tested and rejected, including both return instructions. The static RVV
classifier was cross-checked against the frozen generic decoder across all648
ELF instructions: the31 RVV sites comprise exactly11 allowed sites
(capacity's vset plus ten op_0 instructions) and20 forbidden sites in the other
two helpers. No other vector site in this ELF bypasses the allowlist.

## Phase requirements and false-rejection review

`checker.py:51–57,135–156,184–190,230–235` makes the original execution phases
explicit without reducing the oracle or scalar loops:

1. Seven exact CSR PCs/encodings occur once in source order: startup writes
   mie/mtvec/mstatus/fcsr/vstart, wrapper vlenb and original-C vlenb. The two
   vlenb reads must return128. These match the actual original startup.S,
   wrapper main.c, original case.c and pinned SoC disassembly; they are not
   inferred from a constant Spike-to-SoC offset.
2. Capacity's `li t0,-1`, e16/mf4 vset returning a0=16, and return execute
   consecutively once, after that CSR sequence and before op_0. Interior entry,
   interruption and later replay are rejected.
3. op_0 starts at its entry after the complete prelude/capacity, retires all21
   instructions consecutively once, and closes at return. Its internal PCs
   cannot appear before entry or after completion.
4. Exactly11 RVV retirements are required, one per allowed PC. CVX requests/
   responses never advance these architectural-retirement counters. The
   generic validator continues to check transport consistency.

Additional independent mutations for missing prelude CSR, wrong vlenb and
missing capacity return each failed at the intended phase check. The complete
positive host fixture passes with capacity3, prelude7, helper21, RVV11,
unused-helper0 and the original144-byte oracle. No static conflict with the
unchanged program's legitimate CSR/capacity path was found.

All predecessor specification fields remain equal; only unused_ranges,
capacity_routine and csr_prelude were added. All648 specification instruction
encodings were independently read from ELF64 load segments. Each of the three
21-instruction helper windows still matches the archived scenario ELF bytes.

## Preserved identity, oracle and runtime gates

The exact case entry equals plan01: same SoC ELF
`eed20f08a98ac66766a66810b6f5f8fc829d0603477d37b3d59d48c32669f162`,
same source/reference and frozen M6 image. The independent reference REVIEW,
result.json and READY remain pinned and accepted only under the disclosed
actual Zfh+Zvfh profile; no exact minimum-profile equivalence or DUT acceptance
is inferred.

Original input16/seed64/mask64/output144 setup, all3360 fixture rows/two fields,
loop store counts, exact helper arguments, NV16/vstart0, saved CSR values and
restore operands, packed flags, full144-byte scalar oracle, CTRL exit0 and
post-exit park checks remain unchanged. The data footprint is still0x7e00,
126 preserved destination-tail bytes and16 preserved guard bytes. This is a
scalar architectural oracle, not direct CSV vector-payload evidence.

The replay diff changes ownership to the new
`ara-redspecial-e16-mf4-original-m6-02.service` and adds successor preparation/
predecessor evidence pins; it does not weaken runtime checks. Partial raw
DETAIL still triggers the real monitor immediately. Both raw logs, private
ELF/command/image, COMPLETE/PASS:1, exact summary/returned membership, fresh
disk plan hash, late source/image/reference/approval pins and sticky abort are
retained. Loaded production project-module paths match the successor pin set.

Execution remains no-build, jobs1, case5400s, direct-service6600s, no FSDB and
no retry. New pinned parent authorization must accept this exact plan and
budget risk. Direct MainPID/cgroup/user-bus service ownership, no restart,
KillMode=control-group and deferred cap24/32GiB resource admission remain.
Sealed unused reservation0 still requires accurate parent coordination.

Terminal signal behavior is unchanged and was retested: real SIGINT/SIGTERM
before the publisher's last current pending-set snapshot produce NOT_PASS;
signals after that snapshot are after-decision events. This is not a promise
to revoke PASS for every signal arriving before the subsequent rename.

## Independent validation and evidence

All **41 supplied host tests** passed independently:31 retained methods plus
ten successor cases, including both former counterexamples through full
artifacts. Test-created temporary directories were relocated into this owned
review directory; production checker behavior was not patched.

Independent additional checks passed:

- 42 unused-helper instruction-PC rejections.
- 2 original interior counterexamples through generic, strict and full artifacts.
- 3 missing/incorrect phase negatives.
- 4 retained negatives: trap, backwards cycle, saved fflags, bad park encoding.
- 4 real terminal signal-boundary cases.
- Independent vector-classifier coverage,648 ELF instruction bytes and3×21
  original helper byte comparisons.

Evidence files:

- [host_review.py](host_review.py), [host_tests.log](host_tests.log),
  [evidence.json](evidence.json):41-test rerun, hashes, retained negatives,
  real signals, ELF bytes and module closure.
- [scope_review.py](scope_review.py), [scope_evidence.json](scope_evidence.json):
  independent full-range coverage, old-counterexample rejection and phase tests.
- [findings.json](findings.json): machine-readable clearance and scope.

Residual limits: no current service/worker/resource state was queried; runtime
admission and parent launch authorization remain outstanding. Host protocol
fixtures establish checker sensitivity, not DUT correctness or timing. The
47-minute estimate is unchanged planning evidence;5400s may still time out
under slower throughput, with no automatic extension or oracle reduction.
The checker is not a complete scalar control-flow proof or a guarantee against
fabricated traces; it operates with the pinned ELF, frozen producer, raw
completion and full original oracle. Clearance applies only to plan02.
