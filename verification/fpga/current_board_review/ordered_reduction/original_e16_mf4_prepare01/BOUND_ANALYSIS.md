# Pre-Execution Reference Bound

No Spike execution preceded this analysis. The original 1M-step authorization
is **NOT_RUN_STATIC_BOUND_INSUFFICIENT**, not a failed reference and not PASS.
The user then explicitly authorized one independent reference03M execution:
3,000,000 steps, 256 MiB raw, 120 seconds. No retry, ELF recompilation, source,
oracle, loop, DUT timeout, or ISA-semantic change accompanies this resource
decision. The original sourceproof retains the historical 1M limit; the new
approval, not that historical field, governs reference03M.

## Actual Compiled Control Flow

Addresses below refer to the unchanged `spike/program.elf` and `program.dis`.
RV64 compressed instructions count as one retired instruction, not half.
All counts concern the one reduced single, including its original skipped
scalar traversal, not 6720 vector calls.

| Work | Derivation from actual assembly | Retirements |
| --- | --- | ---: |
| Mask initialization | 3360 rows x64 bytes; 2520 rows use 8 instructions/byte, 840 mode3 rows use 6 | 1,612,800 exact |
| Seed initialization | 8 scenarios x64 words; each word calls original memcpy(32), 227 instructions, plus 12 caller instructions | 122,368 exact |
| Fixture fetch and per-row mask setup | 18 instructions at 0x800004ec..0x8000051a, once per row | 60,480 exact |
| Output sentinel initialization | 144 x4 instructions at 0x80000562..0x8000056c | 576 exact |
| Original output reads alone | 144 LBU instructions at 0x800005d6; excludes comparison/control | 144 minimum |
| Original op0 helper | One complete 21-instruction call | 21 exact |
| Startup BSS loop | 9600 bytes /8 x4 + last exit branch | 4,801 exact |
| **Combined lower bound** | Omits input initialization, nested-loop control, original comparisons, printing and other startup | **1,801,190** |

Mask loop PCs: 0x8000051c,520, optionally524/526,52a,52e,532,534.
Modes0/1/2 execute the two table-load instructions; mode3 skips them.
Seed caller PCs: 0x8000041c..0x8000043e; memcpy at0x80000082
is `7*32+3=227` instructions. Even the mask loop alone rules out1M.

## Conservative Successful-Path Upper Envelope

This is a static admission estimate for this exact ELF, not a measured cost
or a guarantee of reference success. It deliberately overcounts small blocks.

| Work | Conservative allocation |
| --- | ---: |
| Mask byte loops, exact as above | 1,612,800 |
| Seed word loops and their memcpy calls, exact | 122,368 |
| All128 input elements, <=100 instructions each including scenario setup | 12,800 |
| Every row's fixture/setup, both sticky branches and all outer controls, <=80 per row | 268,800 |
| Boot ROM, startup/BSS, wrapper/prologue/epilogue and fixed setup | 10,000 |
| Output initialization, helper, 144 comparisons (<=20 each), call argument setup | 4,000 |
| Original final output and wrapper output, decimal conversion and even one DETAIL path | 30,000 |
| HTIF polling/parking allowance | 10,000 |
| **Upper envelope** | **2,070,768** |

For the row allowance, the18-instruction fixture block plus the two original
sticky-selector paths and row/round/mask/length/scenario transitions remain
below80 instructions; there is no other unaccounted loop in those paths.
The longest input switch path is below100 instructions/element. The seed
switch's repeated32-byte memcpy is accounted separately, not overlooked.
The output loop is below20 instructions/byte including the two numeric bytes.
Only one helper can execute, so the error DETAIL path also executes at most
once. Scalar diagnostic string walks are covered by the30k allocation.
Spike's retained source uses INTERLEAVE=5000 and silent debug runs yield every
INTERLEAVE; the10k allowance covers the final polling/park interval.

Normal scalar commit records have one register write and/or a memory field;
112 bytes per record is a conservative textual envelope for those fields.
2,070,768 x112 +1 MiB reserve for vector/CSR records =232,974,592 bytes,
below268,435,456. Full raw commit data is retained; no truncation is accepted.
The120-second wall bound remains hard and is not derived from RTL throughput.

Thus the new3M/256MiB authorization has static headroom. The software and its
original full oracle remain unchanged. Admission does not claim ReferencePASS
or DUT readiness; actual HTIF success, all144 checked bytes, full setup/helper,
CSR/flags and unchanged pins must still be established from the one raw run.
