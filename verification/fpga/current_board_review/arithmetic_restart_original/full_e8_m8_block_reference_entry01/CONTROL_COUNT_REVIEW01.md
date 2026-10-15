# E8/M8 Scalar Control Cost Review

Static result: a full-unroll proposal has sufficient theoretical headroom to
justify a narrowly scoped plan. This is not a measured saving, authorization
to build/run, or a change to the completed reference's HOLD status.

## Existing Evidence

Sources under `full_e8_m8_block_prepare01/`:

- `reference_successor01/reference01/result.json`: complete4095 calls,
  528255 packed output reads,4193280 results,8190 guards,3271926 firmware
  instructions to software exit. The complete reference remains above3M.
- `spike/program.dis`: actual compiled initializer and comparison backedges.
- `lifecycle.py`: exact128 SD plus tail SH required for every call.
- `reference_successor01/reference_check.py`: each completed call requires
  the129 unique output read coordinates,128 eight-byte reads plus the final
  two-byte read; original full bitwise comparisons and exact ELF code retained.

No raw trace was re-read or re-parsed. The dynamic loop counts below are
derived from accepted full-scope coverage plus actual compiled control flow,
not newly measured per-PC counters. Complete positive read coverage and the
compiled early-failure branches establish that all16 comparison blocks were
traversed on this successful execution.

## Exact Baseline Control Instructions

Initializer body `0x80000506..0x80000514` contains eight SD instructions.
The129-store lifecycle establishes16 body iterations and a separate SH.
`0x80000516 addi a5,a5,64` and `0x8000051a bne` each execute16 times per call.
The branch is taken15 times and falls through once. Control cost is32/call,
131040 instructions over4095 calls.

Comparison body `0x80000560..0x800005bc` checks eight actual/expected words.
`0x800005c0 addi s4,s4,64`, `0x800005c4 addi a4,a4,2`, and
`0x800005c6 bne` each execute16 times per call. Control cost is48/call,
196560 instructions total. The17th block uses the separate exact tail LHU,
not another eight-word iteration. Do not remove that tail or any error branch.

Thus loop-control-only cost is80/call =327600 total. The minimum required
reduction to reach3M is271926. It is not valid to count a branch only on taken
iterations: its final fall-through also retires.

## Ideal Savings, Before New Code Costs

Here a factor4/8 means four/eight original64-byte blocks per residual iteration.
Full means all16 blocks with no residual loop.

| Init factor | Compare factor | Control saved/call | Total saved | Predicted firmware | Headroom below3M |
| --- | --- | ---: | ---: | ---: | ---: |
| 4 | 4 | 60 | 245700 | 3026226 | -26226 |
| full | 4 | 68 | 278460 | 2993466 | 6534 |
| 8 | 8 | 70 | 286650 | 2985276 | 14724 |
| full | 8 | 74 | 303030 | 2968896 | 31104 |
| full | full | 80 | 327600 | 2944326 | 55674 |

The full/full estimate allows only13 additional instructions per call plus
2439 aggregate instructions elsewhere before exceeding3M. Fourteen extra
instructions on every call would consume57330 and miss the target.
Dictionary-base AUIPC/ADDI currently occur within the comparison body; any
future hoisting is additional unproven benefit and is not included above.

## Recommended Single Plan

Prefer a full/full scalar-unroll plan over the fragile full/4 option. Retain
all128 SDs plus SH, all128 actual LDs and corresponding expected comparisons,
all17 uint16 IDs with required dictionary addressing, exact tail2 access,
ordered early mismatch branches and verbatim original fallback. Original
helpers/RNG/history/mask initialization remain unchanged; no extra RVV.

All output offsets0..1024 and ID offsets0..32 fit ordinary12-bit addressing,
so constant offsets can avoid pointer fixups in principle. This is not a
guarantee of GCC lowering. Approximate text growth around2KiB is plausible,
not a bound proved before compilation; compression, branch reach, register
allocation and inlining can change it.

A subsequent explicitly authorized compilation must inspect the actual ELF
before any new reference: count added pointer operations, spills/reloads,
far-branch sequences, loop setup changes and altered scalar paths against the
55674-instruction total margin. Preserve per-call fresh1026 setup and every
oracle byte. If a conservative net count does not reach<=3M, stop without
reference; do not compensate by shrinking the4095 scope or enlarging limits.

No compilation, Host rerun, Spike invocation, DUT execution, RTL edit, or live
simulation query was performed for this review.
