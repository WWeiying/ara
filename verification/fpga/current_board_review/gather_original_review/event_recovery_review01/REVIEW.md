# Gather Six-Event Recovery Static Review

**APPROVED_FOR_ONE_OFFLINE_RECOVERY_PARSE. No blocking finding in this scope.**
This is static entry review, not DUT architectural acceptance. No actual CSV or
case log was read, no Host test/ref/compiler/simulation was run, and no Main/
sealed helper was edited. Only this new review directory is written.

## Exact Reviewed Inputs

| Artifact | SHA256 |
| --- | --- |
| recovery/checker.py | 598693ed6140878cace26d521f69e7a6d59efeb8196ce0251be2116a1ff276fd |
| recovery/test_recovery.py | 7755c036acf0bd7b1ab14bcde8968d251a844aed6995e3e105b2bca9929fb6d9 |
| recovery/host.json | f81ffb08ec9db680a992961cc208198ab6a1e05d382099a252bd78c7ebf555b3 |
| recovery/recover.py | 90bc2c22e46d055aa935d8038cdf4fa6623db9ec23bcb3a75b6e4cec53a61a1a |
| old sealed checker.py | 959689ad2d2a26d1a879b5c0f9fe7d1b1b8f7f03071a8101a5058fa5a5841b59 |
| mature lossless Observer | 7d15ce50da9918fa9b1d3bb1cea59871b4312385576da1fd6c8d5940dbad650f |
| frozen M6 trace.py | b5751d25426ba78893c52359519d3b6f1df6bc9c77eb341c91cdca1ff75b506a |

recovery means `gather_original_review/e8_m4_ops3_prefix66_event_recovery01`.
All five host.json input pins matched actual files. Host evidence reports7 tests,
0failures/0errors,8.519s; it was not rerun here. AST syntax checks passed.

## No Oracle Weakening

Exact old/new checker diff is only the old absolute HERE binding, addition of
`arch_start/uop_alloc/uop_done` to the existing3-event whitelist, and a trailing
newline. Old source/REF/newscope/runtime identity therefore remain bound; no
model, memory decoder, CSR, helper, result, guard, failure-veto or exit gate changed.

Every original requirement remains: e8/m4/cap512,66 natural calls/65 predecessors,
13 helper instructions each/858total, actual args and original order,
2178 setup values/2690 bytes percall, predicate128 physical bytes including
upper64zero,33792 full byte results/132guards/33924LBU reads, prestart/inactive/
tail preservation,66 returned-vstart0 checks, two actual vlenb128 reads/one
capacity512 return, original CTRL0 and side-effect-free original park. Unknown
events/cycle reversal still fail. Source label is not substituted for runtime ID.

## Six Events Still Have Strict Protocol Checks

Corrected retirement checker intentionally skips non-retirement events **only
after** the recovery pipeline's `observer.rows()` calls inherited `observe()`:

- Exact CSV fields, monotonic cycles and trap0 on every row.
- CVX requests must be vector instructions with unique inflight transaction IDs;
  responses require a matching pending transaction.
- arch_start order must equal the next architecture-request ordinal.
- uop_alloc requires a known architecture request, matching instruction and
  unused backend VID; uop_done requires matching VID/order/instruction metadata.
- EOF rejects pending CVX/backend operations. Frozen trace sequence matcher
  checks actual retire/request and architecture/request streams, retaining only
  its existing permitted transport replay semantics.
- Original dictionaries are forwarded unchanged; before/after row digests and
  delivered-row counts must agree. Recomputed generic must exactly equal frozen
  trace_summary VALID data, and strict/generic row/cycle/retirement counts agree.

`Observer.retirement()` being empty is not an oracle bypass: corrected full
retirement checker receives every unchanged row and enforces the old numerical
oracle. Protocol checks run in the inherited observer; there is no call to the
standalone corrected checker as the sole production recovery validator.

Host tests cover old rejection/new known-event acceptance, unknown events,
cycle reversal, original prestart/tail/inactive/guards/vstart negative cases,
and frozen generic positive/negative metadata protocols. The protocol tests call
the frozen generic validator, not a full integrated recovery execution. Static
inspection confirms production Observer wiring; no integrated test result or
actual recovered-data PASS is invented.

## Original Failure Is Preserved

Admission requires original plan5de3a259... and unchanged old checker, original
NOT_PASS/abortedTrue/retries0 and one ERROR with the exact postcheck reason.
The first-cause record must be POSTCHECK_EXCEPTION with numeric monitor and
runner rc0. Actual monitor itself must be integer0/no-timeout/no-failure and
match private work/command, runtime +TESTCASE, original private ELF and fixed
seed/5400s bound. Raw success/failure veto and frozen generic VALID/no-exceptions
are gates before parsing. Other ERROR causes or failed simulator outcomes do not
gain acceptance from this repair.

Only new `offline01/` files are written. Existing complete/first-cause/run/log/
ELF/source/plan are pinned before and verified after; original NOT_PASS/ERROR is
not rewritten. New potential result is explicitly
ARCHITECTURAL_PREFIX66_ACCEPTED_OLD_WORKER_ERROR_PRESERVED, not whole1 worker PASS.

## One Attempt / Acceptance Boundary

Exclusive offline01 creation plus invocation record prevents retry/overwrite.
Actual DUT CSV is opened once, raw bytes hashed during that traversal, with
device/inode/size/mtime/ctime checked before/after. Generic protocol and complete
oracle are recomputed in that same pass. Failure writes NOT_ACCEPTED without
automatically retrying. Main must run this reviewed recover.py, without -O,
with explicit --authorize-recovery and exact checker/host SHA arguments; Main
should preserve actual subprocess wait exit/logs independently of result.json.

This approves only the upcoming offline architectural-data recovery attempt.
Until it returns actual exit0 and passes all checks, no architectural acceptance
exists from this review. Never infer outer service/worker exit0 from GC or absent
PID. Scope stays numerical prefix66, not unknown stall reproduction/closure,
full2688 child, original Linux schedule/execution or parent history.
