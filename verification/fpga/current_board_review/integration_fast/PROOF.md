# Filter Traversal Proof

This is a successor architectural port, not an original Linux program replay.
The input is the SHA-pinned `integration/prepared` tree. Only three adapted
`case.c` files change. All original files, assembly, capacity calls, CSR reads,
input generators, register setup, filters, output initialization, guard checks,
expected-value functions, fixtures, flag checks and PASS counts remain intact.
The compiler flags still forbid compiler-generated vectorization. Runtime,
trap handling and SoC/HTIF completion are unchanged. No timeout is increased.

## Permutations

`maskslide`: seed=0, op=16, s=0, l=4, mode=0, trial=1.
`gather_original`: seed=0, op=0, s=0, l=2, mode=0, trial=0.
These tuples are explicitly enforced by the unchanged original reduced-case
filters and recorded against their original identities in derived provenance.

For each variable the new interval is `[selected, selected+1)`. In the old
innermost body the operation-mask guard, local `vl`/`start` calculations, and
single-case filter precede every mask/output store, log, operation call and
oracle check. Rejected iterations cannot execute a vector instruction or CSR
write. The `capacity()` architectural call and `vlenb` read precede the loops
and are retained. The selected seed-0 xorshift generation is unchanged and
runs exactly once with the same capacity, including indices and indices16.

The old later seed-1/2 passes only overwrite private input/index arrays after
the selected target; all their targets are rejected. They have no logs, CSR
writes or operation calls. No oracle reads their results. The next invocation
fully regenerates the arrays. Removing them does not preserve arbitrary dead
scalar memory or timing, but preserves the selected architectural operation,
its inputs, checks and externally reported result. Architectural scalar PCs,
retirement counters, cache traffic and instruction timing are not equivalent.

At OP_COUNT=21 the original loop visits 56,448 inner tuples, versus one after
narrowing. Maskslide has 14,401 rejected inner tuples before its target and
42,046 after; gather has 32 before and 56,415 after. This is a source-loop
count, not a measured retirement or VCS speedup.

## Reduction

Selected scenario=3, l=4, mode=3, rm=0, op=0, sticky=0. Scenario 0-2 setup
uses only integer table lookup, private input/seed stores and scalar arithmetic
(`fp_reduction_inputs.h`); scenario 3 overwrites every subsequently read input
and seed element. Later scenarios likewise have no accepted operations. The
single-case filter precedes all output setup, operation calls and checks.

Before the sticky filter the old loop reads a const fixture, increments a
local scalar `index`, and fills all 64 mask bytes. Skipped masks are completely
overwritten by the selected mode-3 fill (0x24), which remains unchanged. No
skipped fixture/mask iteration writes vector or FP architectural state. The
original assembly saves/restores frm/fflags and initializes the requested rm
and sticky immediately before the target; that assembly is unchanged.

Unlike discarded mask fills, the scalar fixture cursor is live. Preserve its
original `unsigned index=0` initializer and advance it by exactly
`((4*4+3)*5+0)*3+0 = 285` before the narrowed loops. The original fixture read
`fixtures[vlenb==128][scenario*420+index++]` is unchanged: selected row index
1545, or flattened entry 4905 at VLEN1024. It is still canonical qNaN
0x7fc00000 with NV=16. Not advancing this cursor would silently change the
oracle and is forbidden. This scalar cursor advance is the only non-bound
edit and preserves the original selected iteration's live state.

The original eight scenarios visit 3,360 fixture/mask iterations and 6,720
sticky-filter tuples; the derived program visits one of each. No nonselected
target operation existed in the reduced input, so no preceding architectural
test execution or sticky flags are elided.

## Acceptance

Host differential tests compile both old and derived C at VLEN512 and VLEN1024
with scalar-only operation mocks. They require exactly one selected call and
byte-identical complete input/index/seed/output/mask arrays at that boundary,
identical operation parameters, selected fixture bits/flags, diagnostics and
return value. The mocks do not execute RVV and are not architectural PASS
evidence; they test the traversal transformation independently of Spike.

The adapter verifies every sealed source pin before importing the sealed
compiler. Replacements require exact unique source patterns and exact filter
tuples. The copy must differ in precisely the three listed files. Original
case records/hashes are retained verbatim; parent provenance is copied and
new per-file pins cover the derived tree and unified source diff.

Spike must pass all 14 HTIF programs. A derived SoC `programs.json` remains
compatible with sealed `run.py`, including unchanged required oracle markers.
Do not use the old pipeline's pinned artifact receipt for this successor.
Parent decides whether to execute it against the existing image. No RTL,
snapshot, simulator image or running service is changed by preparation.
