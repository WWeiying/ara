# STORE Conditional Waiter Review

Decision: NO_BLOCKER_STATIC_CONDITIONAL_WAITER. This is not a DUT result or a
launch authorization. Attachment remains subject to main authorization.

## Exact Inputs

- Waiter READY: `5bffde8df05035dd95e0d9b0ebda0145a503129fd3d71c7920aea79b33fc0742`.
- Waiter code: `af52daa013f0edcb65849128ef0ef8ac0c7d9cedd3eb22c69c4ac8a28cca0736`.
- Test code: `1ba0a489c1246c7912eefc52b208a2251cb0757cadbbeb402e198e0016818710`.
- Plan: `ea7add04987278b6c92bdcb720663ee5689021b26384f23111204b6938ed7a81`.
- Existing worker review: `WORKER_PLAN_REVIEW01.json`, SHA256
  `414992a5728d51b5814f8eb345784d070a31313070a6c04ee835a12589454bb7`.

The metadata-only identity check independently hashed all 17 READY pins,
confirmed both existing entry decisions unchanged, and exited 0 (tool chunk
`00dae2`, 0.464296996 s). No raw reference, active CSV, producer terminal
output, process list, or service state was inspected during this review.
No tests or producer tools were executed.

## Reviewed Gates

`waiter.py:45` requires the exact one-case whole PASS, integer numeric zero
in summary, durable child receipt and monitor receipt, identical elapsed
time within 5400 s, no timeout/failure/abort, exact plan and membership.
Null, boolean or nonzero return codes cannot qualify. Missing fields fail
closed. A completion marker alone is insufficient.

`waiter.py:305` checks private ELF/runtime command, both real console logs,
image binding, exact terminal evidence membership, source/input and approval
pins, and strict-result/CSV/outcome binding before opening CSV. Evidence and
input pins are checked again after the pass. The earlier worker review
already established that `NEGATIVE_STRIDE_STORE_SINGLE_PASS` exists in the
actual ELF and is selected by its real exit path; neither this waiter nor
the worker requires a synthetic absent `BOARD_CASE_BEGIN` string.

`CombinedPath` opens one binary CSV stream, computes its byte SHA, sends
each decoded row to the independent numerical observer, then yields the
unaltered line to the existing generic validator. Exact header/column count,
complete generic result equality and unchanged inode/size/mtime are required.
The generic validator consumes its reader to EOF. First failure is retained;
there is no retry or second parse.

The independent numerical contract covers 17275 scalar equality calls,
four complete 4096-halfword page scans, 64 original results, two original
guards and 64 additional sentinels, 2048 refill writes, capacity sequence,
ten original helper instructions, actual PC/code and unused-range rejection.
STORE-specific checks retain prefix127 before repair, poison36 afterward,
retry destination166, actual cause15/tval P-18/vstart5, same-PC MRET with
original base P+22 and stride -8, returned vstart0, and both target owners'
backend completions before handler entry. It does not substitute LOAD values.

Inotify registration precedes the existence check. Bounds remain wait7800 /
audit600 / child8420 / service8500 seconds. Direct supervisor MainPID and
cgroup ownership are checked at attachment. The supervisor persists its own
actual child wait outcome and accepts only numeric exit0 plus successful
result and unchanged pins. A result file alone is not terminal acceptance.
No missing/GC service state is converted into historical exit0.

## Existing Host Evidence And Limits

Existing host execution SHA256
`81ee19f506bc8fc8b525d8710b0910085e76a43bf6d92b234ac72aed620cd9bf`
records actual wait0, no timeout, 22.267316045239568 s. Its sealed log records
six passing tests: numeric/abort admission negatives, full synthetic STORE
data plus six corruptions, actual child exits0/7, killed-child timeout,
single-stream parsing, and terminal rename/already-present events. These
were read, not rerun; no actual service-launch behavior is claimed tested here.

The worker's complete source/initialization oracle remains trusted through
its reviewed checker and bound `strict_prefix.json`; the independent waiter
does not reexecute that entire source oracle. Its numerical and protocol
checks are an additional independent pass, not a claim of independent
reconstruction of every initialization byte. No direct AXI B handshake,
Linux signal-frame behavior or original parent96 closure is established.
No producer budget, helper, source, sealed review, or RTL was modified.
