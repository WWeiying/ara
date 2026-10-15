# Seven Fault Boundaries Accepted Locally

Actual runner PID1880760 exited0. One compile exited0 in28.932562s; seven
sequential simulator invocations each exited0 in10.59..10.69s. Host limit60s
per invocation is distinct from unchanged RTL2000ns watchdog. All snapshots
and original inputs passed the runner's post-check. No retry or RTL edit by
this reviewer. Only RTL substitution relative to M6 is parent-owned VLDU
SHA256 `92f9ebbeb136cd3ff11ae1a8ea92ce31b3aac077ae0667f79d82e919a3603401`.

| VL | Real accepted/popped mask words | Drain pop cycles | Load done | Global idle |
| --- | --- | --- | --- | --- |
| 1 | 1/1 | 14 | 16 | 17 |
| 4 | 1/1 | 14 | 16 | 17 |
| 5 | 2/2 | 14,15 | 17 | 18 |
| 8 | 2/2 | 14,15 | 17 | 18 |
| 9 | 3/3 | 14,15,16 | 18 | 19 |
| 12 | 3/3 | 14,15,16 | 18 | 19 |
| 16 | 4/4 | 14,15,16,17 | 19 | 20 |

All700 CSV cycle rows are present. Every pop is in state4 with issue-valid1;
TB assertions require matching real owner and ordered first0/4/... windows.
Every case has exactly one PE request, MMU response, exception descriptor,
MASKU-done, load-done and sequencer exception response. At load-done the
complete predicate stream has been consumed; at cycles80..100 both spill
slots, all mask valids, MASKU commit and global running bits are zero.
There are no AR/R/data writes in these first-element-fault cases. Result
queue is empty and final-grant bits are all set. No flush is injected.

This closes the local VL9 predicate-drain counterexample for these seven
e64m4/start0/stride0/all-active masked first-fault boundaries. It does not
measure normal data traffic, prefix final-grant delay, nonzero start, FOF,
STORE, CPU/kernel CSR or the archived RVV16 source sequence. Those remain
separate scopes; no broad architectural or Linux closure is claimed.

Result: `measurement01/result.json`, status
`SEVEN_MASKED_FIRST_FAULT_BOUNDARIES_PASS_NOT_SOC`, SHA256
`0a7a762e35f453bffbf4ffa7310daa9aa5a4f4e99aee540354bec30b556b3b68`.
The old ERROR and old VL9 defect reproduction are preserved in sibling
`../measurement01/` and `../startup_diagnostic01/` respectively.
