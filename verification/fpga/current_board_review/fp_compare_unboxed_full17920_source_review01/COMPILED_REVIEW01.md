# Compiled Artifact and Cost Review

Decision: **NO_BLOCKER_COMPILED_SUCCESS_COST_GATE** for compile01/run02 and
linked_audit02. This accepts the static all-correct cost argument and existing
short C receipts, not a reference run or DUT. No compile, Host, model, reference
or simulation was rerun. The e32 observer was not queried or changed.

Actual existing receipts: SoC and Spike compile each numeric0/not timed out;
Host positive and details each numeric0,17920 calls/17920 LWU/412160 comparisons.
Three missing-fresh-write cases actually abort(-6) at event_count==41; wrong
raw seed actually aborts(-6) at the original b[i] formula assertion. These are
intentional negative outcomes, not ordinary rc0. Old run01 warning failure and
source_model01 Python failure remain separate and preserved.

## Actual Lowering

Independent metadata/ELF static checks matched60 before/after pinned files,
all699 SoC and720 Spike disassembly records to ELF load-segment bytes, and the
generated48 input periods/2240 oracle records to linked ROM bytes. No model or
instruction emulation was executed. One initial reviewer inspection command
failed on an incorrect relative header path (Path('.').parent); the corrected
absolute-path inspection returned0. It did not alter or execute any artifact.

Spike PCs show41 exact setup stores: mask16SD at0x80000184..0x800001a2,
input8SD interleaved at0x800001bc..0x800001e6, output16SD at0x800001f0..0x8000020e
and SH128 at0x80000212. Eight actual input LDs at0x800001b8/c6/ca/d0/d4/da/de/e4
are inside every call, including equal values and VL0:143360 dynamic input LDs,
734720 fresh stores. Output LWU at0x80000244 executes17920 times and reads0..3.
It is not skipped for status errors. Actual helper bytes retain all185 original
encodings; no extra vector/FP instruction appears in either linked program.

Record LD at0x800003c8 executes2240 times, once before the8 mode/sticky calls;
s6 preserves it through the original helper, whose code never writes s-registers.
Sticky s7 and live loop/error temporaries are spilled at56/48/40(sp) and restored
on return. Eight arguments, raw LHU/FMV.D.X, capacity and the complete original
17/19-instruction helper windows are unchanged; no boxing OR or alias golden was introduced.
The SoC addresses differ: do not reuse these Spike PCs in a future DUT checker.

The compiled mismatch expression uses XOR/AND/XOR rather than the source OR
form; for each bit it equals (r&Z)|(~r&O). Low16 truncation and low/high32 status
checks remain explicit. Bad-bit popcount and DETAIL failure branches remain
present, with all subsequent calls preserved. The first guard-failure branch
bypasses only the second guard comparison, correctly adding one combined error.

## CFG and Bound

The actual loop increments/branches agree with source trip counts: seed32,
op320, length2240, mode8960, sticky17920. Three nonzero mask modes enter the
mask-constant LD13440 times and the zero mode bypasses it4480 times. All17920
call windows contain the eight fresh input loads and41 stores. Record addressing
increments by7 per op and70 per seed; no predecessor is omitted.

Every harness instruction is partitioned into weighted successful blocks or
explicit error-only blocks. The producer's linked_audit02 adds actual CFG edge
flow conservation, not just a block sum; source trips and branch targets were
read independently. Independent byte-bound block summation gives core2335983
SoC /2318063 Spike. Adding326147 helper instructions (including capacity),
actual four-instruction-per-word BSS clearing plus fixed startup allowance, and
the conservative printing/wrapper bound yields:

| Backend | Static successful upper | Margin to3M |
| --- | ---: | ---: |
| SoC |2682862|317138|
| Spike |2669042|330958|

Printing bound covers fewer than256 successful output bytes, at most16 calls,
the eight decimal digits, scan/output loops and wrapper/startup fixed work.
Source frame224/main16/num48 yields288 normal nested bytes, below the conservative
512-byte requirement and linked64KiB reserve. Full a/b2048B each,mask128B,
output130B and ROM sizes/alignment remain bound by actual symbol/map evidence.

These bounds assume original allowed result/flags and a normally returning
helper. They are not bounds on arbitrary corrupt-result/error-printing execution,
hangs, firmware park, measured retirements or VCS time. Failure/partial reference
must remain a veto. Further parent-authorized reference entry must bind exact
backend ELF/actual PCs and validate all17920 order,185helper encodings/326144
dynamic helper instructions plus capacity3,41 stores,8 input LDs,LWU,raw scalar,
full oracle, numeric exit and pure post-exit park/EOF. Exact input-site/owner
checks cannot be replaced by numerical output equality. CSR restore instructions
and saved operands do not imply a nonexistent post-restore CSR readback.

No reference or DUT execution is authorized by this review alone. See the JSON
for exact artifact and ledger bindings.
