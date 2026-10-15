# FP32 Linked Artifact And Cost Review

Decision: **ACCEPT_COMPILED_CONDITIONAL_COST_LT_3M**. No reference or DUT
authorization. This is a conditional all-correct terminating instruction bound,
not measured retirement, hardware latency, failure-path bound or Linux closure.

Independent review read the analyzer, inherited disassembly parser, actual linked
instruction listings and completed metadata. It did not rerun Host/compiler/CFG
analysis, build a model, execute reference/DUT, or read any raw trace.

## Evidence And Bound

Actual CFG supervisor wait0, timed_out=false,1.921528487s; command/log hashes
match its receipt. All163 pinned inputs rehashed unchanged; before/after maps
are identical. ELF identities remain the single authorized SoC520b652e... and
Spike9b6f3e8f... builds. Original185 helper encodings/696 bytes, linked immutable
tables and function-pointer order are checked against actual ELF contents.

| Component | SoC | Spike |
| --- | ---: | ---: |
| Complete successful source-function CFG |2622703|2604783|
| Original dynamic helpers plus capacity |326147|326147|
| Actual BSS words |1062|2087|
| Startup allowance,4*words+100 |4348|8448|
| Wrapper/printing allowance |18432|18432|
| Whole successful upper |2971630|2957810|
| Margin below3M |28370|42190|

Reviewed branch frequencies against actual induction/register updates:
17920 calls,8960 sticky pairs,2240 length records,320 operations,32 seeds;
nonzero mask constant load13440 and zero-mask path4480. Source CFG partitions
all instruction PCs into successful ranges or explicit failure-only ranges and
checks weighted incoming/outgoing edges. Indirect helper calls are counted at
the caller and charged their complete17/19-instruction bodies separately; the
actual ten-entry function table preserves op order. The SoC mask base costs
one extra instruction/call, accounting for17920 instruction core difference.

Successful popcount/detail paths have zero executions because every result,
flag, vstart and guard must match; those failure paths remain in the binary.
This bound must not be applied to erroneous or nonterminating executions.

Startup has the actual four-instruction zero-BSS loop. The remaining startup
and final exit instructions fit the100 allowance. Read actual text/num and
runtime printing loops: successful output is below256 characters with8 decimal
digits, no trap/detail printing, and no more than16 outer print/number calls.
The64-instruction/character plus128/call allowance conservatively covers length
scanning, decimal generation, log/UART output and wrapper overhead. Function
size checks alone would not prove a loop bound; the source/actual loop behavior
and bounded successful strings provide the needed reasoning here.

## Lowering And Scope

Actual setup contains16 mask SD,16 interleaved A/B SD,16 output SD plus exact SH:
49 stores/call,878080 total. Sixteen actual period LD feed all64B of each bank;
286720 total. B's last LD overwrites its address register only after earlier
loads, and then feeds its final SD. There is no source-data narrowing toFP16.
Output uses one aligned LWU/call; immutable record LD executes2240 times.

Record s6 and A-row pointer s2 remain callee-saved; original helpers use no
s-registers. Sticky, length pointer and prior errors are spilled/restored at
56/48/40(sp). Full flags comparison is retained, not truncated to low32 status.
Frames224+16+48 give288B normal depth, within reserved64KiB. Through-BSS extents
are32496B SoC and40888B Spike; both keep4096B A/B objects,128B mask,130B output
and20992B packed ROM within1MiB. No extra vector/FP instruction is introduced.

Each vf helper still has LWU t2 then FMV.D.X ft0,t2. These are linked static
sites only, not dynamic committed-FPR evidence. Future reference/DUT checking
must retain all17920 calls,286720 result bits,35840 guards, flags/vstarts, fresh
inputs and exact32-bit raw payload semantics. Required backend-owner totals
89600 memory+15360 nonempty target are future observer obligations, not measured
owner acceptance here;2560 VL0 target elisions remain qualified separately.

No blocker found in these exact artifacts. Narrow cost margin is real; no
additional code overhead can be silently absorbed by reusing this bound.
Future reference/DUT requires separate parent authorization and exact entry.

Hashes and immutable evidence identities are recorded in LINKED_RESULT_REVIEW.json.
