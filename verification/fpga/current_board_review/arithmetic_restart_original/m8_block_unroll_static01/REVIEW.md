# E8/M8 Fixed Loop Unroll Cost

Static only. No compilation, Host test, new reference, raw-reference reparse,
DUT, service query or RTL change. Original HOLD and all sealed inputs remain
unchanged. Parent directory names below are relative to arithmetic_restart_original.

## Evidence And Exact Old Path

Baseline `full_e8_m8_block_prepare01/reference_successor01/reference01/result.json`
records3271926 firmware instructions,4095 complete calls,528255 unique exact
output reads (=4095*129), and fresh exact1026B initialization per call. The
accepted lifecycle requires128 SDs followed by SH, in order, at fixed PCs.
Together with actual disassembly, this establishes16 positive-path iterations
for BOTH loops on EVERY call: each backedge executes16 times,15 taken plus one
fallthrough. These counts are reconstructed from accepted coverage and compiled
control flow, not a new independently measured raw PC histogram.

Actual Spike PCs and opcodes:

| Loop/control PC | Instruction | Per call | All4095 |
| --- | --- | ---: | ---: |
| init 0x80000516 /04078793 | addi a5,a5,64 |16|65520|
| init 0x8000051a /ff7796e3 | bne a5,s7,0x80000506 |16|65520|
| compare 0x800005c0 /040a0a13 | addi s4,s4,64 |16|65520|
| compare 0x800005c4 /0709 | addi a4,a4,2 |16|65520|
| compare 0x800005c6 /f97a1de3 | bne s4,s7,0x80000560 |16|65520|

Initializer body0x80000506..0x80000514 is8 compressed SDs (16 text bytes).
Each iteration is8 stores+2 controls=10 instructions;16 iterations=160.
Only32 are removable. All128 stores remain, as does SH at0x80000524 for the
last data byte and trailing guard. Do not count the SH or its scalar setup as
removable. Existing AUIPC/ADDI/base moves outside the loop are not credited.

Comparison body0x80000560..0x800005bc is29 instructions/96 text bytes:
8 actual LDs+8 expected LDs+8 conditional mismatch branches (24), one LHU ID,
one SLLI6, one dictionary-base ADD and two pool-base materialization instructions
(AUIPC at0x80000564, ADDI at0x80000568). Three loop controls make32 instructions
per iteration,512 for16. Only48 controls are credited as removable. The eight
mismatch branches are correctness checks, NOT loop overhead to delete.

Tail0x800005ca..0x800005e2 has8 instructions, retained: ID16, expected address,
actual LHU at0x800005d6, expected LHU at0x800005de, and mismatch branch.
This covers actual output offsets1024..1025, never a rounded8-byte read.
No hoisting of the repeated dictionary AUIPC/ADDI is included in the saving.

## Options

Predictions below hold all non-control dynamic instructions unchanged; they
are feasibility arithmetic, NOT guaranteed compiler output or a new execution.

| Initializer | Comparison | Removed/call | Removed total | Predicted firmware | Below3M |
| --- | --- | ---: | ---: | ---: | ---: |
| Full128-store straight line | Existing16 iterations |32|131040|3140886|No|
| Existing16 iterations | Full16-block straight line |48|196560|3075366|No|
| Four blocks/group | Four blocks/group |60|245700|3026226|No|
| Full128-store straight line | Four blocks/group |68|278460|2993466|6534|
| Full128-store straight line | Full16-block straight line |80|327600|2944326|55674|

For grouped comparison, four iterations retain12 controls instead of48, saving36;
paired with fully unrolled initialization this saves32+36=68, NOT60.60 is the
different option where initialization is ALSO only fourfold (saves24+36).
A syntactic one-iteration16-block loop that somehow retains its final three
controls saves77/call overall, not80; the recommended option removes the loop
entirely and uses fixed offsets. Do not silently apply the grouped formula to
a genuinely straight-line body or count a final branch twice.

**Select only full initialization + full comparison as a candidate plan.**
It covers the required271926 reduction with55674 instructions of headroom.
13 extra instructions/call consume53235, leaving2439 for all other overhead;
14 extra/call consume57330 and exceed the margin. Four-block comparison leaves
only6534, less than two extra instructions/call, so is not a robust first choice.
Single-loop and dual-fourfold options are insufficient and should not be built.

## Text, RAM And Preserved Behavior

128 literal SD offsets0,8,...,1016 fit signed12-bit immediates from one base;
SH1024 also fits. Store text is at most512B using32-bit SDs, replacing the old
24B body+control, a delta at most488B before register/setup changes. Some stores
may compress; do not require that. Fixed output LD offsets0..1016 and ID offsets
0..30 likewise fit existing immediate fields, so unrolling intrinsically needs
no new per-block actual-pointer increments or loop counters.

The existing comparison loop occupies106B including controls. Cloning its
29-instruction payload16 times at the current encoding mix gives1536B, delta1430B.
Ignoring compression entirely gives16*29*4=1856B, delta1750B. Thus the two body
changes suggest about1918B extra text with current encodings, or2238B without
compression, before compiler relocation/register-allocation effects. A4KiB
planning reserve is more defensible than promising exactly2KiB. This is code
size arithmetic, not a linked-layout or branch-relaxation guarantee.

Current SoC/Spike stack gaps are658088/649632B; charging4KiB leaves653992/645536B,
well above the existing64KiB exclusion. Pool241152B, indices139230B and masks384B
are unchanged. a/b/out/mask arrays, RNG and4095-call sequence are unchanged.
No new big buffers, partial output, mask truncation or rounded access is needed.

Source proposal: explicit fixed-offset memcpy initializers, then16 lexical
comparison blocks, each loading its own ID once and comparing the same8 words
in increasing address order; keep narrow tail and original mismatch return/fallback
unchanged. The pool pointer need not be live across helper calls. Preserve all
128 SD+SH and128 full actual loads+tail, all expected comparisons, original
13-instruction helpers, original three-seed input history and all original error
semantics. No new vector operations, compiler flags or time/step increases.

Risk: larger code can alter register allocation, compressed encodings, spills,
long branches, scalar setup or call-loop layout. Moving helper PCs is legal only
with byte-identical helper bodies and newly bound actual PCs. A future approved
single compile must calculate the actual successful-path net delta including
these effects; require final estimate <=3M with positive margin before considering
any new reference. This review alone neither compiles nor clears a reference.

## Pins And Independent Check

- Existing Spike disassembly SHA c2060717a33dffef2f1bcca986625df24a51d604fb9e1c19344568b3ac4d8a2f.
- Existing packed.h SHA5c9a4a84be382955d13f70260632d2fbb9148b7c65d94d51f42fbaebcdbb11de.
- Accepted full reference result SHA4d665c6ca2cf4fe1cc1a389cf45c13403dfa6c84176bfde5d965d83ba5c02605.
- Original HOLD SHA5810fde35a84bdccdc752797362160f70775a5ac34b11870280c02a09d48f5ae.
- Original proof SHA66c9c708c38b7246b9c3fe4c81a92d2c5a218e8e9bceef9a1cb755be08e7e161.

Tesla independently confirmed the counts and the distinction between full/4 and
4/4 in `full_e8_m8_block_reference_entry01/CONTROL_COUNT_REVIEW01.md`.
No raw parse, build or reference was used for that independent check either.
