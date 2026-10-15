# E16/M8 Closed Prefix Diagnosis

Status: **DIAGNOSTIC_ONLY_PARTIAL_EOF_NOT_PASS**. Original actual simulation
returncode255/timed_out=true/10800.076704017352s, NOT_PASS and service exit1 are
unchanged. No VCS/reference execution, RTL edit, timeout increase or long restart.

## Method and Actual Receipt

The bounded header/tail inspection located the last retirement at original
op12's helper setup, not E8/M8's scalar maskcopy. That alone could not distinguish
cost from a terminal stall, so the authorized single prefix traversal was used.

- Own original E16/M8 checker SHA:
  `8573b3191d1da5f7c1c14975976eaac3a9697c0ca2b1cc1b94a88e26da378992`.
- Private ELF and own SoC ELF both SHA:
  `f70831da5a87b07ff0c14852d4d38968226a35653a7568b775577b0a07948923`.
  Actual PT_LOAD bytes for all26 helper routines were checked against own spec,
  including vtype11/E16/M8 and typed vector load/store instructions.
- Own CAP512 typed16 gold, 1028-byte output, 128LD+tail4 actual LW, typed005b,
  physical8-register setup, upper64 mask zero and upper unused BSS checks retained.
  No E8 byte gold, helper PC or output footprint was substituted.
- Original Strict.consume and lossless generic observe/rows handle every row.
  Only exact original op19/38813c57/offset2>=VL owner eligibility is corrected.
  No other target/helper owner waiver. No completed-run finish is called.
- Small partial Host14 passed, actual OS wait0. Added explicit byte5b-vs-typed005b,
  tail4 upper guard corruption, tail2 mask rejection and own geometry checks.
- Exactly one CSV semantic traversal: PID3271019, actual OS wait0,
  422.68753072898835s, bound600s, no timeout/retry. This exit0 belongs to the
  diagnostic process, NOT the failed simulator or architectural whole result.
- All297787465 CSV bytes read once and hashed in that pass:
  `b7cca22f3c4524f14a2908cd9fe9d7a147bf6b74f8d92bda41e861f805e257b4`.
  Pre/post inode/size/mtime unchanged; all26 scoped input/import/spec/ELF/receipt
  pins unchanged. No large reference or another VCS CSV was read.

## Validated Prefix and Current Call

2580435 rows delivered unmodified, 2423998 retirements. Exact complete original
calls1..3534 passed their retained per-row numerical/setup/PC/CSR checks:

-1809408 typed16 result elements,7068 typed16 guards,455886 actual packed reads.
-Complete13-instruction helper and returned-vstart0 for each; all129 oracle reads.
-Actual source stores: checks3534, elements1809408, errors0.
-17670 compulsory memory-helper owners +2222 qualified targets =19892 completed
  necessary owners across these checked calls. Twelve precise VI2 elisions seen.

Last completed original call3534 is seed2/op12/li5/mode0/si2/VL511/start511.
Current original call3535 (zero-based3534) is seed2/op12/li5/mode1/si0/VL511/start0.
Its original initialization and arguments passed at helper entry, but it has
**zero result reads and no returned-vstart yet**. It is not counted as validated.
The result.json next_call field is the following original3536, not current3535.
Remaining561 calls include this partial call; they are not accepted.

EOF helper=`op_12`, next_helper_index=7:

| Index | Actual PC / instruction | Recorded state |
| --- | --- | --- |
| 0 | 80001700 / 00b772d7 | capacity512 vset retired |
| 1 | 80001704 / 02055407 | preload v8 retired; owner done |
| 2 | 80001708 / 0205d807 | preload v16 retired; last visible owner done |
| 3 | 8000170c / 02065c07 | preload v24 retired; owner pending |
| 4 | 80001710 / 02b78007 | mask load retired; owner pending |
| 5 | 80001714 / 00b6f2d7 | business VL511 vset retired |
| 6 | 80001718 / 4e1d | li t3,7 retired |
| 7 | 8000171a / 00881073 | vstart write has arch_start, no accepted CVX request |
| 8 | 8000171e / 94882c57 | original vmul target not retired or accepted yet |

Last retirement: order2423997/cycle18746662/PC80001718. Last *event*:
uop_done at cycle18746725, arch38878, VID1, preload-v16. These are distinct
frontiers, neither is proven to be the final simulator cycle.

Actual last relevant GPRs: a0=8005d720, a1=8005cf20, a2=8005c71a (out+2),
a3=511, a4=512, a5=8005c698 (mask), a6=0, t0=511, t3=7,
s2=005b005b005b005b, gp=8005ce50, sp=800ffec0.
Fresh a/b/mask/out sets are empty because begin_call consumed and verified them;
output_init_index0 is the reset-after-verified129-stores state, not missing setup.

## Protocol Frontier and Gaps

38883 arch_start,38882 accepted CVX requests and38882 responses. All38882 retired
offloads match accepted request sequence, replay0. No pending accepted CVX request.
One unmatched frontend arch_start is CSR00881073; arch_start is not handshake.

19896 uop allocations,19894 completions; two genuine observed pending owners:

| VID | Arch | Instruction | Allocation cycle | Age to last visible event |
| --- | --- | --- | --- | --- |
| 2 | 38879 | 02065c07, preload v24 | 18746591 | 134 cycles |
| 3 | 38880 | 02b78007, mask load | 18746596 | 129 cycles |

These four current-call preload owners account for alloc19892+4, done19892+2.
No completed prior call's owner remains pending. The visible ages are only lower
bounds on eventual lifetime, not wall-time stall durations or evidence of deadlock.

Largest event gap3280 cycles; largest retirement gap3282; largest *completed*
owner lifetime3306. They occur at original op24 masked unit loads, including
calls1357/2722 (seed0/1, VL512/mode0/start0); those requests completed.
All million-cycle bins within the recorded interval contain retirement and
completion events. The first3534 calls do not show an internal unbounded wait.

The lossless before/after row digest is identical:
`04618a39afdf62ec2fa3418e63933dea34cacaf5df3e0fbe81536d961e201a8e`.
No full4095 acceptance or fabricated EOF completion is implied by matched rows.

## Cost Versus Terminal Stall

Actual command again has no COMMIT_WATCHDOG; the frozen progress fflush is gated
off. Inspected run.vcs.log has startup only, no finish time/cycle. Hart tail ends
at the helper's last retirement. File mtime near timeout is not an end-cycle
checkpoint. Therefore **cost versus an unlogged terminal stall remains unresolved**.
Unlike E8/M8, this EOF contains two pending owners and an unaccepted CSR frontend,
which are explicit future probe coordinates, not an inferred root cause.

Metadata-only calculation from this pass's source-counter checkpoints:
first1365-call seed=7269441 cycles; second seed=7262762 cycles. Completed-call
interval median5133 cycles, mean5304.44, range5065..24544. These intervals include
scalar setup/checking and vector execution, not just target latency.

Matching the561 remaining tuples to seed0's same op/li/mode/si/VL/start intervals
predicts3048913 additional full-call cycles from the last completed-call boundary,
or21794803 total; current partial call has835 recorded cycles already. Assuming
stationary host throughput and comparable data timing, the crude projection is
12556s (~3h29m). It is neither a bound nor a claim that the original timeout was
pure cost: the actual final simulator cycle is unknown. It does not authorize
or support extending the old deadline or starting a long restart.

If further debugging is separately authorized, the minimal discriminator is a
real final simulator-cycle/last-retire checkpoint plus outstanding VLDU/SLDU/mask
owner state at that same instant: distinguish normal draining of arch38879/38880
from a long no-completion suffix holding CSR38882. No new probe or run was made.

## Receipt Hashes

- `diagnose_wait.json`:
  `694f1ce1dafbfe57378481565067b830f6aa847183661a8d50d1d6699ab6f527`
- `run01/result.json`:
  `c30c9e6a2accd1b4c628d9f1bd88536dde66eb0c138226d451a8014560b00689`
- `run01/inputs.json`:
  `f9f0df1af3809892d0ae7b34dd261a5fe6816369ebd12af2c46d86ac61ea3e64`
- `diagnostic.py`:
  `c07c28f4d6f499c3a027cf2501484eafe733382f24efb4211872f66b48020f40`
- `host.json`:
  `2d3406ab3a457dbe446ac7687082170fa50dbbf26c1e97b0480cec52cf44964f`

All original files, raw evidence, failures and limits remain unchanged. This is
the executor's partial-prefix diagnosis, not independent full-scope acceptance.
