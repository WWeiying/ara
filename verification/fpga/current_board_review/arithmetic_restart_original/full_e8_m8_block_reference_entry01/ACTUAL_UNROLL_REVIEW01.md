# Actual Full-Unroll Code Review

Decision: actual-code cost and software equivalence support reference entry
preparation. This is not measured reference PASS. Final relocated lifecycle,
Host and exact entry pins still require binding before the sole reference.
No compilation, Host rerun, reference execution or large raw parse was performed
by this reviewer.

## Corrected Net Count

The first static_cost.py regex allowed whitespace to span lines after a
no-operand ret at0x800000b6. It swallowed the following ld at0x800000b8.
The independent line-based parse and all-equal CFG walk establish451 executed
instructions in the comparison leaf, not450. Old static_cost evidence must
remain; static_cost02 carries the correction without recompilation.

| Success path | Old instructions/call | New instructions/call | Total change |
| --- | ---: | ---: | ---: |
| Initializer plus helper-call setup | 176 | 140 | -147420 |
| Comparison, including actual caller and leaf return | 530 | 457 | -298935 |
| VL setup,525 occurrences | 21 | 23 | +1050 |
| After-mask control,1575 occurrences | 7 | 6 | -1575 |
| Remaining enumerated scalar paths | unchanged counts | unchanged counts | 0 |

Corrected net reduction:446880, exceeding the required271926.
Baseline3271926 minus446880 predicts2825046 firmware instructions; with the
proposed10000-instruction allowance,2835046 remains below3M. This is a static
success-path prediction, not an observed new firmware count or a guarantee.
It includes the out-of-line comparator call, return and scalar argument setup,
not merely elimination of the two former backedges.

## Actual Instructions And Memory Coverage

- Comparator all-equal CFG visits451 instructions and terminates at0x800006de:
  one taken equality branch skips the failure li/ret;127 mismatch branches
  fall through. No success-path backedge, nested call, stack load/store or
  stack frame exists in the leaf.
- Actual LDs are256:128 output words using a3 at all unique offsets0..1016,
  and128 expected words using a4. Nineteen LHUs cover17 dictionary IDs plus
  the actual and expected two-byte tail. No widened actual tail load.
- Initialization contains exactly128 SDs at offsets0..1016 plus one SH at1024.
  The SH is the101st store:100 SDs precede it,28 follow. It is still before the
  original helper call and does not overlap any SD. The successor lifecycle
  must accept this exact compiled order, not assume the SH is last.
- Initializer has the same four stack reloads as before, not new spill traffic.
  Main frame remains304 bytes. Actual helper bytes match the old originals in
  both new ELF load segments;26 routines/328 static helper instructions.
- Other common functions have identical opcode sequences. The original C,
  adapted case.c, model, host.c, dictionary, seed inputs, full sequence and
  original assembly are byte-identical to the accepted predecessor.

## Text And Layout

Actual ELF section sizes, distinguished from rounded allocated extent:

- SoC .text4826 ->6824 bytes: +1998.
- Spike .text4930 ->6924 bytes: +1994.
- .rodata and .bss sizes unchanged; alignment makes allocated extent grow1984.
- SoC/Spike stack gaps656104/647648 bytes, both above64KiB, all load segments
  remain within the1MiB link region.
- SoC SHA:847bdfe2e4d261225c06df8de0de2535af60500f272e725d91f42f1900da0c67.
- Spike SHA:8b32f84fd05e8ff61acd6417770fe5d4154aa93d5fe180171af4ca9022d35fba.

## Existing Host Evidence

Original and unrolled variants each have actual recorded exits0, seven1s and
intentional UBSan trap-4. Their complete positive and semantic-negative stdout
matches byte-for-byte. Full4095 order,4193280 result bytes,8190 guards, MASK128,
original fallback diagnostics and1026-byte boundaries remain covered. These
Host outcomes are not hardware evidence.

The old measured3271926 reference and its HOLD are unchanged. No old raw was
reparsed. Next step is only final review of the newly relocated reference
observer/lifecycle and its actual small Host evidence, then exact-entry binding
for the already-authorized single bounded reference.
