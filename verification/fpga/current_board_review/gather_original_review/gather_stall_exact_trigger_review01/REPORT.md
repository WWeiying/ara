# Gather11 Exact-Trigger Evidence Review

Static/archive review, 2026-10-12. No DUT, reference, compilation, RTL edit,
live-job query, or repeated accepted-trace parsing. `collect.py` exited0:
11 original records, 100 input hashes rechecked unchanged. `evidence.json`
contains exact paths, ELF instruction-byte checks, both snapshots, UART tails,
report output and recorded preceding processes. This is not new DUT acceptance.

## Conclusion

**0/11 have a recovered exact unreturned tuple or VID-qualified backend
acceptance/completion trace. All11 do have genuine two-snapshot scalar
no-retirement evidence at a user gather/next-vstart-CSR boundary.** They must
not be dismissed as a slow oracle or reclassified as the separate three
kernel CSR waits. However, the snapshots alone do not prove which vector
request remained outstanding, its parameters, or the responsible RTL mechanism.

Nine identities now have accepted source-prefix architectural evidence; none
of those acceptances closes its original2688-call child or its unknown stall.
The two without such exact-child prefix evidence in the reviewed ledger are
e8/m4/VI0 and e16/m8/VI0. An uncovered opcode/shape is not a recovered trigger.
**No new evidence-supported authentic stall reproduction with a defensible
under3h budget is selected.** Another arbitrary prefix would not resolve the
question asked here.

## Exact Original Evidence

Roots used below:

- `C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`
- `P=C/rvv_permute_partitions01`
- `R(N)=C/rvv_recovery08_N/terminal_scene`
- `H=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/gather_original_review`
- `M6=/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src`

Authoritative membership is `C/stall_family_triage02/triage.json`, group
`gather_operand_stream`, exactly11. Names below have prefix
`rvv_permute_restart_`. For **each row**, original ELF is
`P/release/binaries/<name>`, identical scene ELF is `R(N)/<name>`, source
assembly/header are `P/<name>/operations.S` and `operations.h`. Evidence is
`R(N)/report.json`, `batch_uart.bin` and the report's two progress snapshots.
All canonical/scene ELF hashes and report hashes match the triage ledger.
The collector also reads ELF PT_LOAD bytes at both PCs, not just disassembly.

| Original suffix | R(N) | Last/head PC, hex | Last report DETAIL VL/start | Accepted prefix to reuse |
| --- | ---: | --- | --- | --- |
| e8_m4_ops1 | 154 | 105dc/105e0 | 256/128 | M5 first98 |
| e8_m4_ops2 | 155 | 10600/10604 | 256/128 | None identified |
| e8_m4_ops3 | 168 | 1063e/10642 | 256/128 | M6 first66, offline architectural recovery |
| e8_m4_ops20 | 169 | 10980/10984 | 256/128 | M5 first98 |
| e8_m8_ops1 | 171 | 105dc/105e0 | 3/1 | M6 first66 |
| e8_m8_ops2 | 172 | 10600/10604 | 3/1 | M6 first112 |
| e8_m8_ops3 | 173 | 1063e/10642 | 3/1 | M6 first66 |
| e16_m8_ops1 | 175 | 105ee/105f2 | 256/128 | M6 first98 |
| e16_m8_ops2 | 176 | 1060e/10612 | 256/128 | None identified |
| e16_m8_ops3 | 177 | 1064a/1064e | 256/128 | M6 first98 |
| e16_m8_ops20 | 178 | 10994/10998 | 256/128 | M6 first98 |

Last-PC instruction bytes are respectively op1 `308e4c57` (vx), op2
`30803c57` (vi0), op3 `308fbc57` (vi31), op20 `38880c57` (ei16.vv).
Every head is target+4, `00802573`, `csrr a0,vstart`. The last/head PCs,
retired counter and trap counter are unchanged across both samples; cycles
advance559824418..598691642, or11.19648836..11.97383284s at50MHz. DDR
outstanding/error counts are zero, which does not establish internal liveness.

`console.log` is empty in all11 scenes; **the actual output is in
`batch_uart.bin`**, which was read. UART often ends inside a DETAIL string.
For R178 the unterminated final fragment even contains a further complete
set of fields (`element=4 expected=91 actual=61881`), beyond the report's
last row. It is retained separately, not discarded, and is still a
post-return oracle observation, not evidence of the later stopped call.

## What Can And Cannot Be Reconstructed

The shared complete C is
`C/rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c`, SHA256
`b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca`.
`P/manifest.json` and `parent_mapping.json` bind the partition source and
parent identities. Each selected child keeps2688 calls: three seeds, eight
scalar slots, seven VLs, four masks and four starts, with fullcap RNG/input,
all128 predicate bytes, full output/guards and returned-vstart checking.

At original.c:76 the only pre-call TRIAL print is guarded by `!op` as well
as seed/scalar/mask restrictions. **None of these11 nonzero-op children
prints its current trial before the helper.** The helper call is at line80;
DETAIL printing is inside the subsequent complete-capacity oracle at81..94.
Thus the printed tuple proves a helper returned and an output mismatch was
read, not that its entire oracle finished or that the immediately next call
is the stalled one. Printing also stops after the first20 errors.

Under the source's board-VLEN1024 configuration, VL256/start128 is returned
call66 for cap512. VL3/start1 for cap1024 admits call49 or50. These are source
ordinal deductions, not captured current VL/vstart/vlenb. All11 original
`last_trial` values remain null. The companion op0 pre-call VL512/start256
records R153/R170/R174 are different programs; copying their tuple to these
eleven would invent evidence.

Only **R168** records uninterrupted prior processes in its same batch results:
e8_m4_ops8 -> ops9 -> ops10 -> ops11, each PASS2688, then ops3 stalls.
The other10 list the stalled program first. `previous_report` and
`continuation.previous_attempts` links are restart/administrative history,
not proof of preserved vector state. Do not fabricate a short warmup to
replace R168's four full processes, or silently remove them from a purported
exact original reproduction.

## Kernel Wait Versus Vector Completion

`STALL_TRIAGE.md` sectionD and `ALL_FAILURE_REVIEW.md`'s Stall records section
already limit these11 to opcode-family candidates. The separate
`kernel_vector_state_wait` records are zero-stride fault replay e64/m2,m4,m8,
at last/head `ffffffff80013a16/ffffffff80013a18`; their exact report paths are
included in `evidence.json`. Gather11's PCs are instead in the verified user
ELF. Latched old kernel trap PCs/cause9 and unchanged trap counts do not put
the currently stopped execution in a kernel handler.

The inspected debug generator
`/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/host_debug_fpga.py:30`
counts `commit_ack && !commit_drop` and exports commit port0's head PC
without a validity qualifier. `ara_fpga_debug.sv:121` latches last_pc only on
retirement and trap fields only on a trap. **Exact original deployed debug
build identity was not established in this review**; these files explain
the intended probe semantics, not a new cycle trace of the archived image.

Under those semantics, the observed gather last_pc supports scalar-side
retirement, while the next CSR has not retired. It does not expose Ara
`valid && ready`, VID, acceptance time, done, or current queue ownership.
M6 dispatcher:4661..4677 waits for Ara idle before CSR response, so an
outstanding vector operation can produce this symptom. The unqualified head
PC alone cannot prove that CSR was accepted, nor that the gather rather than
an earlier operation is the remaining backend owner.

## Present RTL And Discriminating Evidence

Fresh SHA comparison found the working lane_sequencer, masku, dispatcher and
sequencer byte-identical to these four M6 frozen files. This is a scoped
comparison, not a claim about every production file.

- Lane:973 sets gather/index AluA origin0. Lane:1223..1240 supplies the complete
  zero-origin packed predicate stream for MaskUnit. Both address known
  coordinate contracts; passed source prefixes do not prove all old stalls fixed.
- MASKU:1481..1490 permits OOR tokens without MaskB data;1569/1578 gate data
  consumption with `!vrgat_idx_oor_q`. Corresponding gates are also present
  in handoff02 `deployed_rtl/masku.sv:1533/1542`; do not describe their mere
  existence as a new, measured repair of these eleven incidents.
- Lane:213..273 arbitrates ad-hoc gather requests, command capacity and
  last/no-data tokens. None of the archived snapshots samples those events.

Two alternatives remain hypotheses, not established current bugs: a missing
predicate word versus a gather request/response or completion-token imbalance.
To distinguish them on a genuinely localized incident, first bind PC/VID,
architectural VL/vstart/vtype/scalar/index inputs and backend valid&&ready.
Then count accepted MaskM words; index FIFO push/pop and OOR; per-lane gather
request valid&&ready with last/no_data; MaskB command acceptance/pop and data
valid&&ready; result/final-grant and the same VID's done/running bits. A request
blocked before acceptance, a kernel idle wait, and an accepted unfinished
vector instruction are different classifications. No such signal trace for
the original stopped call was found here. There is **no newly proved remaining
RTL root cause** from these archives.

## Reuse And Next Decision

Existing terminal evidence, all relative to H, is pinned in `evidence.json`:

- `gather_repair05/m5_successor01/prefix_terminal_audit01/TERMINAL.md`: two M5
  first98 prefixes,50176 results/196 guards each; not automatically M6 scope.
- `e16_m8_ops1_prefix98_terminal_audit01/REVIEW.md`,
  `e16_m8_ops20_prefix98_terminal_audit01/REPORT.md`,
  `e16_m8_ops3_prefix98_terminal_audit01/REPORT.md`: M6 first98 each.
- `e8_m8_ops1_prefix66_terminal_audit01/REPORT.md` and
  `e8_m8_ops3_prefix66_terminal_audit01/REPORT.md`: M6 first66 each.
- `extra_helper_terminal_gate01/terminal01/REVIEW.md`: M6 VI0 first112,
  114688 results/224 guards; not the full2688-call child.
- `event_recovery_review01/TERMINAL_REVIEW03.md`: M6 e8/m4/VI31 first66
  architectural-data acceptance; original worker ERROR remains unchanged.

The fastest cited e16 first98 took2856.396s; e8 VI0 first112 took8372.604s.
Naive call-count scaling to2688 gives about21.8h and55.8h respectively. This
is **not a reliable bound** (setup, VL, instruction choice and host speed
vary), but it supplies no credible under3h admission for an exact full child.
R168 would additionally need its authentic predecessor process history.

**Recommendation: do not launch a new Gather11 replay from this evidence.**
First seek an already-captured register/CSR/VID trace or valid pre-call marker
from the same incident, if one exists outside these handoffs. The missing
artifact is the stopped call's identity and acceptance/completion history,
not another compiler or generic small test. If it cannot be recovered, keep
all11 original stalls explicitly unresolved; neither a guessed short prefix
nor current source inspection closes them. The two remaining VI0 shapes can
be recorded as numerical coverage gaps, but are not nominated as exact stall
reproductions under the current request.
