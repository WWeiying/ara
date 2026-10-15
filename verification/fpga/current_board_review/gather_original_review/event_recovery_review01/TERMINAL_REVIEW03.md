# Prefix66 Recovery Terminal Review

Decision: ACCEPT_RECOVERED_ARCHITECTURAL_PREFIX66_ONLY. No blocking findings.

This is an independent static terminal review of the previously reviewed
`recover02.py` execution and its metadata, not another raw-CSV audit. No DUT
CSV or reference raw was opened; no simulation, reference, compilation, Host
test, live-process query, or producer modification was performed.

## Execution And Identity

- Main's actual-exit witness records session 82008, final chunk 41ef5c,
  integer exit 0 and a 900-second outer bound. Its result/input-pins hashes
  match the actual files. This reviewer did not personally wait that process.
- Recovery reports one CSV traversal, 94.335351326 seconds. The preceding
  admission attempt was exit 1 before any raw read, not a second CSV traversal.
- Invocation binds the reviewed successor, checker and Host hashes. No
  recovery `NOT_ACCEPTED.json` exists. No automatic numerical retry occurred.
- Durable original monitor records integer simulator rc0, 1639.143087192
  seconds, no timeout or failure marker, within the original 5400-second bound.
  Its command/private CWD and ELF metadata match the sealed plan and runtime id.
- M6 image: `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
  Plan: `5de3a259e330825548009fbe17a4f80da34c3a6b816b495a695564621ea4ddbb`.

## Accepted Data Scope

The 66 reported ordered tuples exactly match the frozen source scope: original
`rvv_permute_restart_e8_m4_ops3`, runtime `gather_prefix_e8_m4_ops3`, e8/m4,
cap512, with 65 predecessors retained. Endpoint is `[0,3,0,4,0,1]`, VL256,
vstart128. All reported targets are original opcode `308fbc57` at `80000758`,
immediate31, scalar0, source31 byte177; all returned vstarts are zero.

- 13 original helper instruction counts are each 66: 858 retirements total.
- Full-cap scalar oracle: 33792 results plus 132 guards, 33924 output loads.
- Each call checks 2178 setup values / 2690 bytes, preserving physical
  predicate storage128 bytes (logical active mask extent64 bytes).
- Actual vlenb reads128 twice and capacity return512 once are recorded.
- SoC CTRL exit0 and six original post-exit park retirements are recorded.
- Generic validation matches the stored VALID summary exactly: 1317045 rows,
  1314151 retirements, final cycle1862392; 730 CVX request/response pairs,
  352 uop allocation/completion pairs, zero exceptions or replay counts.

These conclusions rely on the reviewed strict full-oracle/protocol traversal;
this terminal review compares its resulting metadata, not raw values again.

## Pins And Preserved Failure

All 744 original plan pins are inherited without digest changes in the
761-entry recovery input map. Eighteen relevant metadata/code pin hashes were
freshly verified; the current review did not rehash all761 inputs or raw CSV.
Recovery's before/after checks report all pinned inputs unchanged. The raw CSV
digest was accumulated during that single traversal, not recomputed here.

Original complete/run/summary/first-cause hashes still match REVIEW02. Their
`NOT_PASS`, aborted=true, `INTERRUPTED`, ERROR1 and postcheck exception remain
unchanged. Original `pins_unchanged=false` is not relabelled; recovery's separate
pin result does not rewrite the old terminal record. No outer service exit0
is inferred from GC, process absence, or the recovered result.

## Bound Evidence

- Result: `c86bf85d2b4f6215675b8cccd41f3545b1f2ad79b0873c0470a13dc2f81b6d6e`.
- Input pins: `5eab54355c0d0877befafac247785fba64f9a9cfd833f40fe5d2bb9a15eb38ab`.
- Actual exit: `de1a9ca9a503a48c0ff033dc2d5c6fb9ac0bf53d8d2ee987ad6a1b813cb2998a`.
- Invocation: `f2e4a9f32ba9c084cdfe35c821ffa9a8dc26c316d2d4416648d8e5e06ea42543`.
- Reviewed successor: `c3e84a7c26f50625582cd9aee582c226e844f9b2b1585e8251488f6ee82d67b4`.

Acceptance is recovered architectural data for this authentic numeric prefix66
only. It is not acceptance of the original worker/service, a historical stopped
tuple, unknown Gather stalls, the full2688 child/full parents, or Linux execution.
No new DUT runs or RTL changes were introduced by recovery or this review.
