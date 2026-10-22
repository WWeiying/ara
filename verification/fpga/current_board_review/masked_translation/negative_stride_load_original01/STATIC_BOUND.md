# Pre-Reference Static Bound

One source-derived NF1 negative-stride load, not the 96-case Linux parent.
No reference has been executed at the time this bound is prepared. Software
compilation and Host oracle checking are not reference/DUT acceptance.

## Actual Compiled Paths

`software01/spike.dis` is the actual executable used for the following count.
Its `check` successful path has seven instructions. The check_memory halfword
loop starts at 0x80000218 and ends at 0x80000250. Phases0/1 take20 instructions
per halfword including check; allow22. Phases2/3 additionally execute the
five-instruction logical-element loop at0x80000234..0x80000242 at most8 times.
Allow70 total per halfword, covering match/poison branches as well. Original
final logical-element search and all4096 memory comparisons are retained.

| Work | Conservative successful-path instruction allowance |
| --- | ---: |
| Phase0/1 memory halfwords: 2*4096*22 | 180224 |
| Phase2/3 memory halfwords: 2*4096*70 | 573440 |
| Four complete512-entry triple page-table checks, 61 per entry | 124928 |
| check_memory prologues, guards and checkpoint tails | 4000 |
| Actual startup BSS 4441 doublewords, 4 per word plus setup | 18000 |
| Initial4096 halfword fills and lower2048 refill, including setup | 40000 |
| Three full192-element snapshot comparisons, guard checks and setup | 30000 |
| Remaining initialization, input/offset/output loops, zero page tables | 30000 |
| Trap records, frame saves/restores, scalar oracle, CSR save/restore, runtime | 30000 |
| Subtotal | 1030592 |
| Additional straight-line/branch allowance | 69408 |
| Admission upper estimate | **1100000** |

The allowance is for the correct terminating path, not a proof that arbitrary
failure/trap loops terminate. The hard instruction cap remains1500000 and
wall cap120 seconds; abnormal outcomes are retained, never retried.
The original64 outputs and2 guards are checked. Extra physical-allocation
sentinels output66..129, neighbor-register snapshots and extra checkpoints
are adapter safeguards, not additional historical failures.

For raw sizing, reserve210 bytes per ordinary retired instruction plus8MiB
for vector payload, CSR-rich lines, reset and exception records:
1100000*210+8388608=239388608 bytes, below256MiB (268435456).
The independent hard RLIMIT_FSIZE remains256MiB even on a nonterminating path.
The reference engine is the existing non-ZCC restart-golden Spike with
rv64gcv_zfh_zvfh_zvl1024b, M/S/U privileges, no PMP regions and2MiB RAM.
Both actual process wait status and any timeout/file/instruction failure will
be persisted before the full raw observer runs. Exactly one invocation.

## Source And Observer Boundaries

Source/reference changes are limited to replacing Linux mmap/signal delivery
with real Sv39 leaf invalidation, M-mode observation, lower-page remap/refill
and same-PC MRET. Original helper code is linked unchanged, including unused
store helper (which the observer rejects if executed). No invented predecessor.
Source physical input128 initializes only first64; offsets128 and mask16 are
retained. Base staysP+22, signed stride stays-8 at actual retry; only the
hardware-effective resumed address isP-18. Prefix sourceP+6 is poisoned only
after all2048 lower-page words have been refilled.

The observer checks all retired firmware PC/encodings, original helper order,
two target access lists, initial/fault/repaired/final byte maps, actual MRET
GPR/CSR context, all17274 scalar comparisons, restored CSRs and HTIF success.
Initialized data comes from the actual ELF PT_LOAD bytes; BSS remains absent
until actual startup stores it. No invented memory bytes are permitted.

Reference time is not VCS time. Prior M6 NF2pilot4 retired1307708 instructions
in1759.4446 seconds (~743/s). A deliberately slower273/s proxy with20% margin
places1100000 instructions near4835 seconds (81min). Different shape and
memory traffic make this only a planning estimate, not an authorized DUT
budget or predicted pass. No VCS/image/RTL work is performed here.
