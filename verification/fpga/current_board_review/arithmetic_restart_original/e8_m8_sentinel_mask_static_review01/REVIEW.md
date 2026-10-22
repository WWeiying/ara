# e8/m8 Sentinel And Mask Static Review

Decision: **NO_BLOCKER_SOURCE_STATIC_ONLY** for Zeno's single proposed successor.
This is not software readiness, a certified runtime bound, or authorization to
compile, run Host/reference/DUT, or extend any budget. No candidate exists yet.

## Exact Entry

- Proposal: `../e8_m8_sentinel_mask_static_audit01/SOURCE_PLAN.md`, SHA256
  `05165743d78d875406e86006bbbf3120d3338a4a1d3f7658d8ab386eac17efdb`.
- Authoritative facts: `../e8_m8_sentinel_mask_static_audit01/ARTIFACT_AUDIT02.json`,
  SHA256 `f1654fae1b3a8e3dc243125380109542ef831b9a70a829ccba62df57e54c9179`.
- Existing e8 SoC ELF: `../full_e8_m8_block_unrolled01/soc/program.elf`, SHA256
  `847bdfe2e4d261225c06df8de0de2535af60500f272e725d91f42f1900da0c67`.
- Existing provenance records original/reconstructed Linux ELF byte equality:
  `ee9874270f50735cb04da599bb477d3d9da2bbeba0e77cbec9e1eb1ea0f8310f`.
  This review reuses that source proof; it does not rebuild the original binary.

## Independent Checks

Read-only inspection independently matched all 22 facts-file pins. A separate
ELF PT_LOAD reader matched both backends' complete dictionary and all 4095x17
linked IDs to dictionary.h/sequence.json. The eight ID0 words are exactly
`0x5b5b5b5b5b5b5b5b`, not e16's halfword sentinel. Full-block ID0 counts are
52335/65520; per block:
`2613,3447,3450,3456,3276,3279,3279,3279,3051,3315,3315,3315,3315,3315,3315,3315`.
Tail-ID0 count is zero. Coincidence with e16's aggregate is not imported evidence.

Independent successful-edge walks of the two old linked comparator listings
each yield 451 instructions, including 256 LD and 19 LHU. The latter are 17 ID
reads plus actual-tail and expected-tail reads. SoC entry is `0x80000076`;
actual tail at `0x800006c0` reads out+1024 with LHU, expected tail at
`0x800006c8` also uses LHU. Old main's frame is 304 bytes, not an e16 frame.
These are static CFG checks, not executed firmware or Host tests.

## Semantic Contract

The proposal preserves e8/CAP1024/m8/vtype3, eight physical registers per group,
4095 calls and their RNG/history, 4193280 result bytes, 8190 byte guards, 4095
returned-vstart checks, and 53235 original helper instructions. Only a successor
packed.h may differ; case.c and its full scalar error fallback remain identical.

ID0 specialization is valid because every selected expected word is the same
immutable full-width constant. It must still load and compare each actual word;
it is not permission to skip all-sentinel output or mask-off results. Nonzero
IDs retain their exact dictionary comparisons. No XOR/checksum cancellation or
altered error aggregation is introduced. On a comparator mismatch, original
fallback recomputes all 1024 element expectations and the original guard/error
rules. The original failure counter continues after the first 20 printed errors.

Successful calls retain 128 actual LD plus one LHU, 528255 reads overall.
The 1026-byte object starts with a guard, then 1024 output bytes, then a guard;
the last LHU contains result element1023 and the rear guard. It must never become
a 4/8-byte actual load. The proposal retains original early mismatch fallback:
"all129 reads" is the successful packed path, not a promise that the packed
comparator continues all reads after failure. Full source fallback still applies.

Mask expansion retains all 128 bytes: 16 eight-byte stores in each of 1575
original group epochs, 25200 stores. e8 uses the high64 bytes too; the e16
upper-half-zero shortcut is invalid here. All three table patterns must be
preserved, including mode2's changing words, not one repeated constant. memcpy
retains defined unaligned/alias-safe C semantics without typed-pointer casts.
The seed-only e8 a/b setup and CAP-based gather/slide oracle remain unchanged;
uint8 gather indices are valid within CAP1024, not an imported OOR case.

## Cost And Remaining Gates

The old *e8* full reference records 2825046 firmware instructions. Its comparator
contributes 451x4095=1846845 successful instructions. Zero blocks offer removal
of 418680 gold LDs and up to 104670 address operations. Remaining gold reads
would be 105480 fullword LD plus 4095 LHU, not 109575 LD. The successor facts
correct that initial naming issue without changing the old artifact.

The proposed ledger `457830 - materialization - joins - layout_delta` is only
conditional: it assumes those address operations actually disappear and charges
one branch for each full block. e8 constant lowering, branch expansion, literal
loads, spills and rematerialization require actual later linked evidence. The
old comparator already uses BEQ/BNE, so a sticky XOR/OR rewrite is not a saving
justified by this baseline.

Old mask-loop body `0x80000b2a..0x80000b36` costs 4x16+2x15=94 instructions
per group. Ideal 16LD+16SD gives a 97650-instruction core opportunity, not net
whole-program savings: first-word setup, addressing, allocation and all other
main changes still count. No budget-neutral or <3h guarantee is established.

Old actual DUT timed out at 10800.112584 seconds with child255. Existing closed
prefix evidence validates 2601 calls, not all4095; 1494 remain unvalidated there.
Its EOF at a finite mask-copy loop is neither proof of deadlock nor the actual
last simulated cycle. Do not derive a full-runtime bound from that frontier.

Later authorization must require actual dual-backend source/ELF/helper/geometry
and CFG evidence, retained full-width mask stores and 2B tail, scalar error
fallback, no added RVV, and complete cost including new spills/joins. This review
ran no Host, compilation, model, reference or DUT and read no raw/active trace.
No existing files or production RTL were changed. Full source-port scope, not
original Linux closure, remains the prospective acceptance boundary.
