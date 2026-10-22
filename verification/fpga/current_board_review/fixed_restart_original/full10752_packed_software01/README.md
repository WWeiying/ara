# Full10752 Packed Source Implementation

Status: **SOURCE_WRITTEN_NOT_GENERATED_NOT_TESTED**.
Only the single reviewed source proposal is implemented here. The generator has
not been run, imported, syntax-checked by execution, or used to emit a model.
No Host test, preprocessing, compilation, reference, DUT, or service action was
performed. No old input, helper, report or sealed preparation was edited.

Basis: `../full10752_static_cost_plan02/README.md` and
`../full10752_static_cost_plan02/static_review01/STATIC_REVIEW.md`.
The latter authorizes source implementation/review only. Full <=3M cost and
<=3h DUT runtime remain unproven. This directory has no compile/reference/DUT
driver, no automatic next stage, and no PASS/READY file.

## Actual Review Inputs

- `generate.py`: original identity verification, source port/optimization edits,
  integer-only full-source model, symbolic source-key checks, exact-value row/block
  interning, all10752 indices plus separate saturation bytes, mask-write source,
  exclusive output creation, source diffs and before/after pins. It never imports
  an old prepare script or invokes subprocesses.
- `packed.h`: the actual scalar implementation.64 fixed-size memcpy SD candidates
  plus one SH candidate initialize precisely514 bytes each call.64 actual LD
  candidates plus one LHU candidate always execute, including row0 and mismatch.
  Static inline memcpy operations avoid pointer-cast aliasing and unaligned C
  dereferences. Memory clobbers retain ordered writes/actual reads, without fences.
- `port.h`: the existing prefix's bare replay_write ABI and explicit tty-drain
  substitution, not a claim that Linux TCSBRK was exercised. No new synthetic
  success marker is injected. The caller/runtime must later supply actual exit.

Generated `case.c` does not yet exist. Review the source transformations directly:
they require unique exact anchors in hash-bound reconstructed C and copy the full
original error-loop substring unchanged into the packed mismatch branch. Original
`failure()`, `extra_value()`, `rounded()`, `selected()`, diagnostic formatting,
helper calls, loop ordering and28 trace statements remain source-identical.
`original_port.c` will be emitted alongside it for an independent original-C Host
comparison, with only the same runtime/capacity qualifications, not packed logic.

## Identity and Source Mapping

Canonical original: `../recovery01/successor_oracle.c`, SHA
`ab82b4891f9e926e37ef4d9f10fc44b0f953136deef2173b84427c0447e81006`.
This is binary-equivalent reconstructed C, not the missing historical C text.
Original ELF SHA
`ca6937f7969cb2664becfe53fac5e49111415929e96220874568964b293b85cc`.
`scenario.S` SHA
`9b4552c734a6f456d094bf77dd1510495df3c5421b6bb05bc3492b5e5ecac2c0`;
`operations.h` SHA
`adec2fb8c81bc1b2f9173c7928dd2d3dabbae932596cb139e058b6f11cb98fb9`.
Both helper files will be copied byte-for-byte, not regenerated or text-normalized.
Each op remains24 instructions; capacity3 and all CSR save/set/sample/restore
instructions remain in original assembly. Linked bytes are a later actual gate.

| Original location | Implementation and preserved obligation |
| --- | --- |
| C244-252 capacity/vlenb | Require capacity512 and vlenb128; preserve actual vlenb CSR read on RV64 and max_start1023. Host receives an explicit callback, not implicit zero/default. |
| C253-264 input loops | Original three xorshift statements stay in C, once per512 elements per seed. Ordered memcpy1+barrier replaces each source assignment, including overwritten random writes and b-only case3 override:4416 byte stores. Higher backing halves untouched. |
| C275-304 tuple loops | Original3 seeds,4ops,7VL slots,4 masks,4 start slots,8 controls remain unchanged. No call/start/sticky deduplication or prefix stop. |
| C285-287 mask | Generate16 exact zero stores per128B epoch, then original selected-i cumulative SB sequence. Mode0/1/2 have512/256/73 stores; mode3 still clears.336 epochs,5376 SD+70644 SB, upper64 bytes zero; actual vlm consumes64B. |
| C326-329 output init | Merge adjacent identical sentinel loops. Full1026 backing retained/aligned8; exact514B per-call write footprint, out+1 helper destination unchanged. |
| C330-348 traces/call/vstart | Preserve all28 boundary records before original helper calls, tty caveat, and full low32 vstart failure before data fallback. |
| C349-401 element/sat/guard oracle | On any packed byte mismatch, run this exact original block over existing output, no helper rerun or initialization. On exact packed equality, add512 elements and compare full high32 saturation to separate per-call byte; guards are included in packed equality. |
| C402-410 counters/summary | One checks increment per helper, original error count/first20 diagnostics and final original summary remain. Return the original exit code to the runtime rather than a Linux exit ecall. |

## Tables and Mathematical Contract

The Python specialization uses integer xorshift64, byte truncation, signed8
conversion and exact rounding. For vsmul, floor quotient/residue by128 matches
the original signed arithmetic shift and unsigned low-bit test, including
negative ties and round-to-odd. The other operators are signed saturating add,
unsigned saturating add and signed saturating subtract. No floating computation,
approximation, hostfloat, final-value-only input reuse or original host suite is
substituted for future independent C equivalence tests.

Each row is generated from the complete original tuple. Its source key is
`(seed,op,op0_rounding_or_zero,active_indices)`, with one empty-active sentinel
key. Each block adds its original block position and active indices within that
block. Repeated source keys must have identical generated bytes, otherwise the
generator fails. Block values are then interned bytewise and descriptors are
interned by all9 block IDs. The generator reconstructs every514-byte output from
its descriptor and checks exact equality. Saturation starts at control>>2 and ORs
all active saturation events; it is stored per call, never deduplicated with rows.

Block0 is64 sentinel bytes. Block1 is the two tail sentinel bytes plus62 zero ROM
padding bytes. Row0 is eight block0 IDs and block1; only exact full sentinel
output can use row0. Nonempty active calls whose numerical output is coincidentally
sentinel may share row0, but still execute every helper/read/store and keep their
own saturation entry. No model activity count becomes an owner waiver.

Full blocks use8 uint64 values; the last block has only2 relevant bytes. Its ROM
padding never authorizes a tail actual64 access: actual offset512 is always2B,
covering result511 and rear guard. First LD includes front guard and results0..6.
All514 bytes are checked exactly;514..1025 are neither initialized nor accessed
by the scalar per-call oracle. Dictionary bound442 rows/716 blocks/86036B is
asserted by the generator but not yet measured here. All10752 index/saturation
entries remain even when their values repeat.

## Failure and Freshness Contract

The inline RV64 comparator uses the already-reviewed scalar BEQ/LI sticky form,
with a +r mismatch operand and memory clobber; Host uses ordinary C inequality.
Neither path returns early on mismatch, skips later actual loads, or changes the
vector helpers. Actual linked load/store widths, branch topology, registers and
spills are not asserted before compilation. No new RVV, CSR, or hardware fence is
intended outside the original helper/boot contracts.

On a bad packed result the exact original per-element loop still increments
elements512 times and calls failure once for each bad byte in ascending order.
It then checks saturation and the original combined guard diagnostic, which
prints the rear guard even for a front-only failure. A preceding bad vstart is
reported once before this block. A correct packed result takes elements+=512,
which is equivalent for this bounded counter; status failures still use original
failure(). No generic one-error replacement for a multi-byte mismatch is used.
Sticky/mask/state is never reset between cases except by original operations.

## Next Review and Execution Boundaries

Tesla reviews these files now, without running them. A later explicit parent
authorization is needed for one generation into a new directory, bounded Host
equivalence/negative checks and fixed-flags dual-backend compilation. The intended
configuration is SEW8,FRACTIONAL_SUITE1 and the original operations.h defaults;
disable auto-vectorization. Do not use compiler flag trials. The generated port
can link the mature replay runtime; supply a real64KiB stack and explicit main
adapter/actual SoC or Spike endpoint in that later stage, with separate identities.
No runtime/endpoint/stack-layout acceptance is claimed by this source-only step.

Future checks must compare the independent original C and packed C over all10752
calls and all source-write/mask/CSR/history events, all5505024 result bytes and
21504 guards, plus first/middle/last/multiple data errors, both guards, saturation,
vstart and failure print suppression. Mutation tests must distinguish dictionary
integrity from output oracle correctness: a corrupted expected-ROM value can
invoke the original fallback and still pass if actual output is correct; table
fidelity must independently fail its generation/identity check, not alter original
failure counts. Delete same-value input/init/mask events, corrupt mask intermediate
values, and test exact514B end protection. Validate RV64 compare on equal/unequal
with bad0/bad1 and all65 reads. These are review obligations, not executed tests.

Future command shape (not run and not presently authorized):

```sh
python3 generate.py --authorize-generate --out /absolute/new/exclusive/generated01
```

Generation alone writes `SOURCE_GENERATED_UNTESTED_NO_COMPILE_REFERENCE_DUT`, never
PASS. Only a reviewed full-CFG upper bound <=3M can lead to a separately authorized
bounded reference; even that does not establish <=3h DUT runtime. Original Linux
tty/scheduler/CSR-stall history is not reproduced by this source port.
