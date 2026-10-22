# M9 sc0/sc3 Closed-CSV Recovery

**ARCHITECTURAL_RESULTS_ACCEPTED_OFFLINE_OLD_BATCH_NOT_ACCEPTED**

Independent delta approval:
`../unit_fof_e64_sc0_sc3_recovery_review01/result.json`, SHA256
`9956cc5fd2ea1dac061f715078f88366a649b0c3ce1a66a2cb83242e2cfb195e`.

Actual offline audit PID2756457 exited0 after24.275942 seconds. Receipt:
`audit_process01/execution.json`, SHA256
`0d4c1e6f77d9530965429d4895fb10bdd541238ee9311f79040a915f9d84b5df`.
Result: `closed_audit01/result.json`, SHA256
`f85942d662bab18098147cef3606fd38cc9755ba982ab1c18fa6201cb0eb892e`.

| Original e64 single | Actual simv rc / seconds | CSV rows / retired | Checks | Returned VL/start |
|---|---|---|---:|---|
| sc0 active FOF crossing protection boundary | 0 / 246.556700 | 167122 / 167018 | 5477 | 4/0 |
| sc3 ordinary alloff protected-page load | 0 / 246.998061 | 166267 / 166163 | 5481 | 8/0 |

Each closed CSV had exactly one new complete semantic pass, with every row
passed unchanged to the successor and inherited oracle/owner checker. Total:
333389 rows,333181 retirements,10958 scalar comparisons,4 full checkpoints,
8 nonempty memory owners including6 non-target helper owners. Original generic
VALID summaries were pinned and full row/retire/cycle counts cross-checked;
they were not falsely described as independently recomputed.

Both preserve the original11-instruction helper and3-instruction capacity
window, unused-helper veto, all original source values/mask bytes/output
initialization/guards,8KiB data and12KiB page-table oracle, actual handler CSR
records and14 CSR-restoration readbacks per case. sc0 alone leaves final
out[5..8] undefined as required by the original source; its initial130-element
output and final126 defined allocation elements remain strict. sc3 checks all
130 final allocation elements, including all8 results. sc0 returns VL4 before
the original helper restores VL8 for its output store and completion ecall;
sc3 retains VL8 throughout. Neither target produces an architectural fault.

## Checker Cause And Narrow Repair

The old checker tracked only known GPRs but indexed x8 at the main-entry caller
save without an opaque-input contract. Both stopped at row12989, before any
source oracle: sc0 PC800003a2/cycle19660; sc3 PC8000035c/cycle19649. This was
KeyError8 at csv_check.py:57, not a data mismatch or measured RTL failure.

New files inherit the sealed business checker. Opaque input capture is limited
to actual ELF main14-entry/224-byte frame (12 callee-saved registers), and the
actual completion-ecall handler17-entry/128-byte frame (only x7,x28..x31).
Every capture uses the real RVFI store value, exact PC/register/address/BE,
and first-save ownership. Unknown is never defaulted to0. Known registers and
all business writes remain strict. Both cases checked all16 handler restores
against their actual saved values and original slots before MRET. Main restore
loads remain checked against the inherited actual-memory shadow. Host12 main
and10 handler negatives exited0; no reference or simulation was repeated.

The original894 plan pins plus recovery/evidence pins total936 were verified
before and after the complete pass. Ledger `closed_audit01/pins_before.json`:
`6f6a4f705c826013f5845807fa3723aa159888c5175ff517c865e58342eaf41a`.
No original file, ELF, production RTL, original checker or old output changed.

## Preserve Original Outcome

Original plan11521664380ef491f6db4823b8ccd99865a25df2011fd6ed1f12b52ee0e995b1
still has statusNOT_ACCEPTED_LATE_ABORT, aborted=true, retries0 and its original
pins_unchanged=false field. Actual original systemd facts remain exited/1/
exit-code. Those are not rewritten as a successful worker. Both durable simv
child/monitor receipts actually record numeric0 with no simulator timeout,
failure marker or cancellation; raw console/run logs retain the original
oracle PASS and successful finish. Acceptance here is the separate offline
architectural recovery, not a replacement batch outcome.

Scope is exactly these two source-derived real-Sv39 singles on frozen M9,
not Linux fork/wait/signal closure, all historical scenarios, or proof of zero
internal MMU/AXI requests. No DUT launch, reference rerun, retry or RTL edit
occurred during recovery; no further DUT dispatch was made.
