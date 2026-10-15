# Fixed Dualcompile and Linked Cost

Status: **short C Host and both fixed compilations complete; linked proof pending
independent review**. No Spike/reference, VCS, LLVM, ZCC, RTL edit or live query.
All source_model02 source/table/helper bytes remain unchanged. Source_model01's
earlier Python failure is untouched. This is not full original Linux acceptance.

## Commands and Outcomes

The exact fixed compiler argv is saved before execution in each backend's
`run02/{soc,spike}/compile.command.json`; actual numeric waits/log hashes are in
`compile.exit.json`. Each target compiled **once**, exit0, with the installed
Xuantie non-ZCC `riscv64-unknown-elf-gcc`14.1.1. Both use `-Os`,
`-march=rv64gcv_zfh_zvfh_zvl1024b`, lp64d, no auto-vectorization/SLP, medany,
freestanding/no builtins, function/data sections, identical five original defines
and the inherited1MiB linker script. The only backend define difference is
`SPIKE_REFERENCE=1`; each emits its own map. Fixed flags were written before
either target compile in [FIXED_CONFIGURATION.json](run02/FIXED_CONFIGURATION.json).

`-Wno-unused-const-variable` was selected up front because original fixtures are
retained for provenance but the packed candidate uses generated records. It does
not suppress input/oracle diagnostics and was not added after a target failure.
Compiler/cc1/as/ld and all reviewed source inputs are pinned pre/post unchanged.

The first Host compile stopped on the fixture's signed length comparison against
`sizeof`, before either target compile. [run01/CAUSE.md](run01/CAUSE.md) retains
the exact cause, failed files and compiler rc1. The successor casts the already
asserted-nonnegative length; no candidate/core/oracle/flags change was made.

## Short C Evidence

[Host result](run02/host/RESULT.json): positive and diagnostic runs each execute
the same full17920 candidate-C loop in about0.117s, with 412160 comparisons to
the original fixture oracle per run, 17920 result/guard reads and every fresh
setup checked. The C helper stub is explicitly a fixture oracle, NOT RVV execution.
Only scalar SD/SH/LWU are replaced with instrumented defined C memory copies;
`packed_errors` and candidate C are byte-identical to reviewed source. The exact
adaptation is [core_adapter.diff](run02/host/core_adapter.diff).

The C checks cover every single-bit inversion at every call, two-bit inversion,
each guard and both guards together, returned vstart, sticky and NV flags,
including VL0, active and legal/illegal tail cases. An injected21 failing calls
produces exactly20 original DETAIL lines and final `cases=17920 errors=21`.
Four independent processes delete an input store, mask store or final output SH,
or replace nonzero seed1 vf b[0] with zero; all reject at the exact expected
assertion, actual wait `-6`, with core dumps disabled. No arbitrary nonzero rc is
accepted as a successful negative test. The final error reporter and original
boxing behavior were not weakened to make the Host pass.

## Actual Lowering

All185 helper encodings match the source-reviewed actual original identities in
both linked ELFs. No extra RVV or FP instruction appears outside those helpers.
The complete17920 order remains, including2560 VL0,7168 vv,10752 vf, original
326144 dynamic op-helper instructions plus3 for capacity.

For each call the actual straight-line body has:

- 16 mask SD, 8 input SD, 16 output SD and final SH: **41 fresh stores**.
- **8 input-period LD**, each immediately feeding the corresponding input SD.
  This is actual compiled control-flow evidence, not inferred from memory clobbers.
  No dynamic-LD reuse waiver is needed. Total input LD143360, fresh stores734720.
- One aligned LWU at output0, covering guard0/result1+2/guard3. No unaligned
  cast/load or widened final store. Original initialized bytes4..129 remain
  outside the original post-result oracle.
- Oracle record LD is legally hoisted to once per seed/op/length, **2240** loads;
  all eight mask/sticky variants still perform their own fresh setup and helper.

Spike fresh body is PC`8000017a..80000234`; eight input LD sites are
`800001b8,1c6,1ca,1d0,1d4,1da,1de,1e4`. Output LWU is`80000244`.
SoC addresses are independently derived and checked in
[soc.json](linked_audit02/soc.json), not borrowed by a DUT observer.

Record lives in callee-saved `s6`; none of the original helpers uses any s register.
Sticky s7 is saved to56(sp) and reloaded into t0 before ORing baseflags from s6.
The loop pointer t1/prior-error t6 are saved at48/40(sp) and restored after return.
All original helper fflags save/restore and returned status assembly remain exact.
Caller frame224B + main16B + num48B gives288B normal deepest nesting;512B is a
conservative stack allowance, below the linker-reserved64KiB. Actual arrays stay
2048B each, mask128B, output130B; all relevant bases are8-aligned. Actual tables
are1536+17920B. Spike footprint through BSS is35192B, well within1MiB plus stack.

## Complete Successful CFG Cost

Authoritative ledger: [linked_audit02/RESULT.json](linked_audit02/RESULT.json).
Both backend reports partition EVERY source-function instruction into counted
successful blocks or explicit failure-only blocks. The computed edge weights
satisfy incoming/outgoing flow conservation at every actual instruction, including
the nested32/10/7/4/2 loop exits, zero-mask branch, sticky toggle and summary/return.
Original helper bodies are separately counted in full, including VL0 calls.

| Component | Spike instructions |
|---|---:|
| Complete successful harness CFG, calls and spills included | 2318063 |
| Original helpers including capacity | 326147 |
| Startup/BSS upper:1575 words*4 +100 | 6400 |
| Wrapper/output upper | 18432 |
| **Whole successful upper** | **2669042** |

Output upper is256 bytes*64 instructions +16 calls*128 setup/return allowance.
The actual successful output is below256 bytes; the largest runtime byte loop
is below64 including string-length scanning and decimal conversion. There are
only8 decimal digits across16/17920/0. Main/exit overhead is included in these
allowances. The successful all-correct path excludes diagnostic printing/popcount
iterations by definition; they remain executable checks, not removed source.
This is NOT a bound on a failing or nonterminating hardware execution, and final
parking-loop iterations are not firmware completion work.

SoC has one extra mask-address materialization per call and a smaller BSS/output
runtime; its conservative whole upper is **2682862**,317138 below3M.
Spike margin is330958. These are static compiled bounds, not actual retired counts
or a VCS walltime guarantee. Independent CFG/ABI review is still required, and
reference/DUT execution is not authorized by this report.

`linked_audit01` is the initial arithmetic ledger before edge-flow cross-checks.
Its exact analyzer bytes are archived as `linked_audit01/inspect_linked.executed.py`
with the original pinned hash`ce3e6997...`; the top-level analyzer subsequently
added the flow proof and wrote fresh `linked_audit02`. No compiler or reference
was rerun for that static-only refinement. Use audit02 as the current review entry.

## Exact Identity

- SoC ELF SHA `19afd0c6fd9c0810efbfdd9a635d092672554e6a1f3d4a3a537af00c4de13e37`
- Spike ELF SHA `0ecbd714c95e1aed2b1a6586cebdd7953e090d2da6d8c6521ee1101c2aec9671`
- Host RESULT SHA `3419eb82d2668ec63595178afd87e8d2fb679608256d2f1a427854d320a795fd`
- Compile RESULT SHA `f831bc06424b01f372d00ac37a3a549aaa7d86531034efdbde470154b84b0f0c`
- Linked RESULT SHA `ce1650dd885e74d7d5c4f1ab67c60e4692d396b361127b90b3559ad6029d95f8`

Actual top-level wait receipts are in [EXECUTION_RECEIPT.json](EXECUTION_RECEIPT.json);
they do not infer process success from files or from a missing PID.
