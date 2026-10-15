# Joint Load Regression Accepted Locally

Actual command from repository root:
`python3 -B verification/fpga/current_board_review/masked_translation/multiword_fault_liveness01/regression02/run.py`

Runner PID1888865 exited0 (terminal tool chunk937794). Exactly one compile
and one simulator batch per version; no retry. Baseline compile0/29.684829s,
run0/10.791148s; candidate compile0/29.182323s, run0/10.691370s. Each host
run limit60s includes startup; each instruction has a separate200-clock
progress bound. All39 original-input pins and35 snapshot pins per version
remain unchanged. The only input difference between versions is VLDU,
candidate SHA256 `92f9ebbeb136cd3ff11ae1a8ea92ce31b3aac077ae0667f79d82e919a3603401`.

## Normal Path Comparison

M6 and candidate produce BYTE-IDENTICAL full normal traces:120 sampled clock
rows,43 columns, including idle cycles, request/response, AR/R, descriptor,
mask owner/window, requester/final grants, BE/data, done and global idle.
SHA256 `1e09fc99d37eb955cac1c90d8d8ac3b733bfa19154cc4bba3af2e5ed78831a04`.

| Primary scenario | AR/R | Skip | Written bytes | Last bank write | Load done |
| --- | --- | --- | --- | --- | --- |
| vm0 VL9 alternate predicate | 5/5 | 4 | 40 | c42 | c43 |
| vm1 VL9 burst | 1/3 | 0 | 72 | c18 | c19 |

Each primary is followed without reset by a masked VL5 load with active
elements1/3 and inactive last element4, writing16bytes with2AR/2R/3skip.
The complete normal traces include these two successor instructions. No
normal-path cycle or transaction-count regression is observed in this scope.

## Exception Boundaries

| Scenario | VL/start/fault | Prefix bytes | WAIT_RESULT_QUEUE | Final writes | DRAIN | Done/response |
| --- | --- | --- | --- | --- | --- | --- |
| Partial starting word | 9/3/5 | 16 | c27..67 | c66,67 | c68,69 | c71 |
| Nonzero first mask window | 13/5/7 | 16 | c25..66 | c66 | c67..69 | c71 |
| Fault in terminal word | 9/0/8 | 64 | c53..67 | c66,67 | c68 | c70 |
| FOF later element | 9/0/5 | 40 | c39..67 | c66,67 | c68,69 | c71 |
| FOF first element | 9/0/0 | 0 | c17 | none | c18..20 | c22 |

The first four cases hold actual public stream-register bank outputs until
c66. Requester acceptance occurs at c17/c25/c29, well before the final bank
grant. Offline CSV checks establish WAIT_RESULT_QUEUE before the first final
write, DRAIN strictly after the last final write, and load-done after DRAIN.
The reported blocked counts192/160/144/144 are lane-cycles, NOT instruction
latencies. No prefix final-write wait was bypassed by predicate disposal.

Real sequencer exception_vstart is5/7/8/5/0 respectively. Backend FOF flag
is1 only for the later-element FOF scenario; first-element FOF remains0.
Backend exception cause13 remains present in both, as required for the
dispatcher to distinguish suppression/VL shortening from a first fault.

All seven candidate scenarios (14 instructions,590 CSV rows) pass. For every
instruction the TB verifies every enabled write's real owner, address, data
and BE, rejects duplicates/out-of-range writes, then checks both entire
512-byte groups at vd24/vd28. Thus candidate performs14336 full-byte oracle
comparisons, including preserved prestart/masked/suffix/tail bytes. Every
fault case reaches global idle with MASKU commit0, no mask valid, and empty
VLDU spill BEFORE any modeled external flush. Its independent masked
successor completes without reset and preserves the previous group exactly.

## Provenance and Limits

Real modules: M6 AddrGen/MASKU/sequencer plus selected VLDU. MMU page fault is
a controlled response to real requests at an actual4KiB boundary. AXI R is
generated only from queued real AR handshakes; declared beats return in
order. Per-lane stream_register is the existing consumer fixture's public
requester/final-grant model. No internal force, synthetic fault descriptor,
fabricated mask completion, or early flush is used.

CPU, dispatcher, physical VRF banks and page-table walker are not present.
FOF backend qualification is measured, not actual architectural VL CSR
update or trap suppression. Owner tags and sequential reused-VID history
are checked; this is not an overlapping foreign-owner stress test. No STORE,
indexed early-illegal, actual kernel CSR or archived original16 root claim.
The baseline exception defect remains preserved separately; only normal
paths are compared cycle-for-cycle here. These are local correctness and
normal-performance regression points, not SoC/Linux closure.

Result status `NORMAL_AB_IDENTICAL_AND_SEVEN_CANDIDATE_SCENARIOS_PASS_NOT_SOC`:
`measurement01/result.json` SHA256
`620b0d80fc38346106092f05d5bede0aede2ecdf1a5d2a962ebad5a849f4b8da`.
Candidate CSV SHA256:
`2908c705bcce2ed0f9ba0bde57cfa60f9dbca9332ab7b7e0e4ca48b174a2fd1a`.
Input ledger SHA256:
`bb327da5d4f12dc690113a79e99df805992d1fb37b35637ffd4bb3c21cacae67`.
