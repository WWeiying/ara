# FP32 Generator Source Review

Decision: **SOURCE_GENERATOR_NO_BLOCKER** for generator4390b89f... only.
Static review, not generation/model acceptance. No numerical Host, compiler,
reference or DUT executed by this reviewer. Parent's conditional software-only
pipeline can proceed; independent original-C Host must pass before compilation.

## Source And Reuse

Read the complete generator and its imported `port`, `source_row`, `elf_bytes`
implementations, packed core and copied runtime/startup/linker sources. Import
does not invoke the base main. The FP16 classifier, FP16 model main and old
helper locator are not called. `source_row` uses the supplied FP32 fixture and
input integers, not FP16 masks. Its fixed16 iteration count refers to CAP16
mask bits, not source element width. Original C03cc... matches this CAP16,
unmasked, restart0, DK0 specialization.

`source_port` preserves original loop nesting, helper arguments, sticky flags,
error total/first20 diagnostics, and complete final report. Only syscall/startup
plumbing, fresh initialization and scalar oracle evaluation are replaced.
Compile guards specialize SEW32; original `word` becomes uint32_t, retaining
both1024-element backings. The original `.S` and headers are copied unchanged.
The helper reader uses actual original e32 ELF bytes and pinned hashes; e16
metadata supplies instruction lengths only, not e16 opcode values or PCs.
All original185 instructions/696 bytes remain required in the future ELF audit.

## Packing And Oracle

- Eight uint64 period words pack pairs of unsigned FP32 values with a Python
  integer shift32. Inverse unpack checks all16 values. C emits uint64 literals,
  avoiding uint32 shift UB and preserving sign/NaN payload bits exactly.
- Deduplication is confined to immutable input periods. All17920 rows remain
  seed/op/VL/mode/sticky ordered; each call still performs eight A/B SD pairs,
  sixteen mask SD, sixteen output SD and final SH at128. The code never reuses
  the untouched upper4032B of either original input bank as scratch.
- Record packing uses only16-bit result predicates; this is correct despite
  SEW32. FP32 fixture values are not narrowed to16 bits. Baseflags derive from
  original fixtures, vf rhs index14 and the active range, then OR original
  sticky. Raw b[] remains the actual32-bit source, including zero seeds0/16.
- DK0 old mask0x5b5b, VL0 old-only and nonempty tail {old,1,wanted} are preserved.
  The unchanged core popcounts invalid bits, separately checks vstart/flags,
  and counts either/both guards as one original error. Output LWU at aligned
  output0 checks exactly guards0/3 and result1/2; bytes4..129 stay fresh but
  outside the original result oracle. No all-tail-zero restriction is added.
- Generated rows/packing self-checks are representation checks only. They do
  not independently prove the oracle. The planned numerical Host must use
  unchanged original C/fixture logic for helper outcomes and error expectations,
  including all allowed-tail choices, mixed errors and first20/21 diagnostics.

## Gate And Limits

The generator requires the exact reviewed binding file and all44 pins, then
this status and its own SHA before creating exclusive generated01. It checks
input hashes again after generation and records artifacts. Failed partial output
must remain; no automatic retry or reuse. Additional runtime files below were
read/hashed here and are included by generation in its pre/post inputs.

Parent permits one generation plus independent numerical Host (each child<=120s),
then only on success one fixed-flags compile per backend and complete CFG<=600s.
Actual width/load/ABI/helper/extra-RVV/map and cost evidence remains outstanding.
49 fresh stores and16 ROM LD are source obligations, not measured lowering.
Cost>3M means HOLD. Neither this review nor generation authorizes reference/DUT.

See review.json for exact generator, imported source and runtime hashes.
