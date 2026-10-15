# M7 Mask-Drain Pair Terminal Acceptance

Both actual child receipts record numeric rc0, timed_out=false,
failure_seen=false and abort_set=false. Worker terminal records agree,
with retries0 and pins_unchanged=true. This review rehashed every input
pin and non-CSV evidence; no CSV was reread/reparsed and no process polled.

| Member | Child seconds | Checks | Retired rows | Final cycle | Pins rehashed |
| --- | ---: | ---: | ---: | ---: | ---: |
| LOAD | 177.29025372117758 | 914 | 114050 | 145030 | 674 |
| STORE | 182.56944536510855 | 914 | 117073 | 148655 | 674 |

Both complete real Sv39 fault -> actual vstart0 read -> PTE repair -> same
PC retry -> distinct masked load/add/store -> ecall -> full on-device oracle
and14 actual CSR restore readbacks. LOAD cause13; STORE cause15. All checks
and full source/tail/neighbor/data/page-table guard contracts remain intact.
Internal flush signals were not captured; software recovery is measured.
This accepts the new e64 VL9 boundary pair on frozen M7, not the original16
Linux root and not indexed early-illegal prefix recovery.

LOAD complete SHA256:
`8248fff95092b655ec2b9240a990930e5aa4a11771c6f17787b834afec021676`.
STORE complete SHA256:
`d4f472b252a9697f083b8724d0eede59dffb1257d55bdf331442fc67bff1971c`.
Receipt/input audit `result.json` SHA256:
`94a26fc2ad9b778d7628a87483652e35011a177c399e2dce7aadd9d71b99e090`.
Actual receipt-review command exit0: tool receipt7adca7. No inferred service
exit from unit GC. Each member's11 non-CSV evidence hashes also match.

Historical distinction: the old VL9 local counterexample demonstrated a
global-idle dependency cycle. Old VL8 reaching idle with spill_b/first4
still buffered is not itself corruption: existing lsu_ex_flush_q can clear
that spill once the real dispatcher allows the flush. Do not infer a VL8
successor failure or close the historical Linux stall from that transient
state. M7 drain-empty/recovery measurements are separate positive evidence.
