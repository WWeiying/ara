# Constructive Positive-Path Cost, Not GCC Evidence

This counts a feasible scalar schedule for the single integrated source,
not subtraction from e32/m2 or the earlier3.699M analogy. All source events
come from the accepted full5985 model. Instruction selection, allocation and
branching below are explicit **hypotheses for a legal lowering**, not an
actual compiler result or a proven upper on arbitrary GCC output. Error
paths keep all actual reads and fallback; their cost is not a positive bound.

## Cache Function: 1072047 Instructions

On each call, the first block unconditionally fills the cache. Later blocks
use LHU for their ID and a BEQ to the compare body on a hit. On a miss, copy
ID to the tag, shift by6, add the pool base and load8 expected words. The
compare body for each word is LD actual; BEQ actual,expected,next. Unequal
falls through `li mismatch,1`; equal skips it. Both paths execute the next
read. The final word uses an uncached ID/address/expected LD. No per-block
loop instructions are required because the source is fully unrolled.

| Item | Positive instructions |
| --- | ---: |
|65 actual LD/call |389025|
|65 equality BEQ/call |389025|
|9 ID LHU/call |53865|
|8 expected LD/miss +1 tail/call |124041|
|7 tag decisions/call |41895|
|Tag assignment/miss |14757|
|SLLI+ADD per miss/tail |41484|
|Mismatch=0/call |5985|
|Move result + RET/call |11970|
|Total |1072047|

This placement does not need a jump after miss fill: the hit branches over
the fill into the common compare. Tag assignment can precede fill address
arithmetic, since the old tag is dead after the miss decision. That frees the
ID temporary to hold the computed expected address without changing observable
memory behavior. All canonical IDs are in-bounds and source expected memory
does not trap under the fixture prerequisites.

A concrete leaf register allocation uses exactly15 caller-saved registers:
a0 output base, a1 IDs, a2 pool, a3 mismatch, a4 tag; a5..a7/t0..t4 hold the
eight expected values; t5 actual value and t6 current ID/address. ra remains
the return link. No cache array or expected-value stack spill is intrinsically
required. This demonstrates existence, not that GCC chooses the allocation.
If GCC spills the cache or emits XOR/SNEZ/OR on every word, its actual costs
replace this schedule; do not count stack loads as free cached reuse.

## Other Component Schedules

| Component | Calculation | Instructions |
| --- | --- | ---: |
|Output initialization + caller |5985*(65 SD +3 sentinel materialization +RET +2 caller) |424935|
|FP refresh + caller |1890*(256 SW +8 LWU +6 dispatch +RET +6 caller) |523530|
|Mask setup + caller |154350*(LI+SB)+35280 clear SD+2205*(6 dispatch+RET+3 caller) |366030|
|Original helper windows |5985*13 |77805|
|RNG/seed setup allowance |Detailed below |16000|
|Per-call driver, excluding above calls |5985*48 |287280|
|Per-group loop/setup allowance |2205*8 |17640|
|Per-op/seed outer-control allowance |105*12 |1260|
|Startup/stack/normal return/text allowance |Detailed below |50000|

Output sentinel needs `li 0x5b; slli32; addi0x5b`, then65 SD. Source barriers
do not emit instructions. The leaf uses only a0 and a temporary. The FP leaf
uses8 input registers, two output pointers, seed/dispatch temporaries; all
store offsets are0..508 and directly encodable. Six caller instructions cover
two destination moves, two input-base materialization instructions, seed move
and call. Mask uses a pointer, mode and small temporaries; constants<=255 fit
single LI, all selected offsets<=15. The16 clear SD use x0. No selected LBU
or ORI is part of this **new shape's** source contract. Saving constant reloads
across repeated bytes is not assumed in these totals.

### Driver/Stack Accounting

The48/call allowance is independent of the separately counted output/FP/mask
caller instructions. One explicit positive route uses:

- FP-op test2 and original start calculation at most7.
- Original helper argument setup7 and function table/address/indirect call6.
- Returned-vstart decision1, preserved even when data matches.
- Cache caller10: output move1; ID base materialization2; ordinal*18 plus
  base4; pool base materialization2; call1.
- Mismatch/fallback decision1; elements/checks/start-counter/loop updates4.
- checks<5985 guard2 and up to4 extra counter load/store instructions.

These total44, leaving4 for trial-limit load/temporary handling within48.
At group boundaries, the8 allowance covers kinds/trial setup, mode advance
and branches. The105 outer iterations reserve12 each for VL-array setup,
length/op transitions and bounds. This is an example route through the fixed
source loops, not a disassembly claim. A different compiler route must be
counted in full, including all stack loads/stores.

The driver can retain seed,op,li,mode,si,ordinal,VL,start and four buffer bases
in s0..s11. A constructive160B frame holds saved s0..s11/ra, the7 lengths and
trial spill/spare slots. The leaf functions above need no frames. Saving and
restoring that driver frame occurs once, not per tuple, and is charged to
startup allowance. The formatting fallback is not executed on a positive
run. The existing64KiB stack reserve remains mandatory in the future real map.

For RNG,384 iterations at25 instructions is9600: six xorshift operations,
one right-shift for b, two original stores, up to12 special-case selection
and override instructions, four pointer/index/branch instructions. Add initial
64-bit seed-constant materialization, array addressing and transition overhead;
16000 is the constructive allowance, not a scalar-GCC measurement.

The50000 runtime allowance is explicit, not omitted firmware:20000 for BSS/
runtime initialization,20000 for normal final decimal/text/backend return,
10000 for startup/capacity3/frame save-restore/alignment glue. The original
private backing is12448B before layout padding; a direct8B zero loop with
four instructions/word needs6224 instructions, fitting the first allowance.
There is no per-call logging when TRACE_OP0 is undefined. The actual mature
backend and any additional initialization must be pinned and counted before
using this as an actual cost gate; the allowance does not prove that backend.

## Result and Limits

```text
1072047 +424935 +523530 +366030 +77805 +16000
        +287280 +17640 +1260 +50000 = 2836527
nominal remaining room to3000000 = 163473
```

This demonstrates a roughly2.84M inexpensive positive lowering **can be
described without dropping any required data/write/read/call**. It is neither
a machine-code lower bound nor an audited upper. For example, replacing each
successful compare branch by XOR+SNEZ+OR adds instructions; extra caller saves,
unrelaxed calls, cache spills or backend work can consume the margin. Original
helper/global-order and memory-event obligations cannot be weakened to fit it.

The old3.699M relative estimate is not used as a new lower bound. Likewise
this2.836M schedule does not admit reference or DUT. Only an independently
reviewed source proposal followed by the separately authorized single Host/
actualcompile and actual CFG/map gates can establish the next-stage budget.
