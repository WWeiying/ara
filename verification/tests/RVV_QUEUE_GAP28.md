# Queue/dependency supplement, 2026-09-28

## Scope and image

36 new `vqueue_gap28_*` directed cases, independent scalar selfchecks, no RTL
change, no indexed segments, no catalog/Makefrag changes. Run against the
original immutable image underlying the 473-PASS memory coverage collection.
Do not use a repaired image or mix image identities. Nietzsche owns the
separate bounded 8-worker runner and PASS-only DVE collection; ordinary failures
and timeouts are evidence for later triage, not permission to change RTL.

## Coverage targets

Baseline: `verification/out/vcs-memory-gap-20260928-01/dve/summary_waived.csv`.
MaskM branch coverage is 32.59%; SlideAddrGenA 33.33%; Store/MaskA 34.81%;
ALU-A 49.63--51.85%; dispatcher FSM 44.87%. These are hierarchy scores, not
proof that any particular uncovered conversion branch is legally reachable.
`operand_queues_stage.sv` enables integer extension on ALU-A, but the mask,
slide/address and store queues do not enable all generic conversion modes.
Their meaningful targets are data layout, word boundaries and dependencies,
not forced unsupported conversion controls or flush waivers.

Existing `vpolicy_type_matrix`, `vsext`, `vslide_mask_edges`, and store mask/tail
tests provide single-operation/policy baselines. This supplement combines:

| Family | Count | Cross and independent checks |
| --- | --- | --- |
| widen | 12 | signed/unsigned widening add, SEW 8/16/32, LMUL 1/4; immediate masked narrowing shift and ALU consumer; check wide intermediate and narrow result |
| slide | 12 | SEW 8/16/32/64, LMUL 1/2/4; masked slide down then masked slide up with RAW dependency and distinct destination groups; check both stages |
| store | 12 | same SEW/LMUL cross; load source in a different EEW, then masked unit and strided stores; compare every initialized byte including untouched holes and guards |

Each ELF runs six fixed subcases: full VL, tail VL with alternating mask,
aggregate-word boundary with sparse mask, VL=1/all-zero mask, VL=0, and a
second tail subcase (with nonzero memory vstart for stores). Maximum checked
VL is 65, not an unbounded/random kernel. Slides preload every referenced
source element, including beyond the active VL, instead of assuming tail
register contents. Stores cover prefix, mask, tail and stride-hole preservation.
The arithmetic and slide cases use vstart=0: the installed Spike traps the
nonzero-vstart widening operation. Memory restart remains in the store family.

Unsigned C bit patterns implement sign extension and modular widening sums;
the reference never relies on signed overflow, signed right shift, or a shift
by the type width. The chained oracle is computed from inputs, never from a
previous observed vector result. Volatile arrays and the inherited build flags
disable auto-vectorization of initialization and checks.

## Reproduction and handoff

```sh
python3 verification/tests/generate_rvv_queue_gap28.py --selection verification/tests/rvv_queue_gap28_selection.json
python3 -m unittest discover -s verification/tests -p test_generate_rvv_queue_gap28.py -v
python3 verification/tests/build_rvv_queue_gap28.py --output verification/out/queue-gap28-preflight-ready-20260928 --spike --ready verification/tests/rvv_queue_gap28_ready.json
```

The wrapper reuses `build_rvv_memory_gaps.py` unchanged and builds runtime objects
only in its independent output directory. It verifies source/tool pins before
and after compilation/Spike, requires all 36 exact selfcheck PASS logs, rejects
duplicate ELF hashes, and emits an exclusive-create READY file. READY pins the
selection, wrappers, shared header, generators, both build helpers, runtime
sources, tools, Ara/HTIF ELFs, command list and Spike results/logs. The existing
300-second per-case RTL budget is retained; Spike PASS is not RTL PASS and no
coverage gain is claimed before the compatible-image runner measures it.
