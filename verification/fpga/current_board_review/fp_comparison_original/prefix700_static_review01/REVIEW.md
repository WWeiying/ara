# Original FP Alias Retained Boundary: Independent Static Review

Scope: source/report/accepted-result metadata and RTL reads only. No reference,
Host execution, compilation, DUT run, closed CSV traversal, or RTL modification.
Zeno independently confirmed the same mapping and is preparing a fresh700
successor, not modifying or rerunning accepted682. This review supports source
selection; it does not accept an unexecuted prefix or authorize a new simulation.

## Exact Historical Mapping

Parent: `rvv_fp_compare_unmasked_alias_v8_e16_m8`, SEW16/M8/cap512,
UNMASKED=1, RESTART=0, UNBOXED=0, DESTINATION_KIND=1 (vd=v8=lhs).
Original ELF:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_additions45/binaries/rvv_fp_compare_unmasked_alias_v8_e16_m8`,
fresh SHA256 `266467e6d61dc7334a83e62ce6ee8d2d0cfac5050811be026329c46eb3816754`.

Direct original board evidence (not merely a reconstructed tuple list):
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_recovery08_11/terminal_scene/report.json`,
selected result `name` above, status failed, actual exit1, original full17920
summary errors1472. Its20 retained DETAIL lines are exactly consecutive681..700.
The log truncation policy is20 errors, so700 is **last retained**, not last failure
of the full parent and not a newly measured current-RTL failure.

Original order: seed/op/length/mode/sticky. Lengths0,1,2,3,256,511,512.
One-based ordinal = `1 + seed*560 + op*56 + length_index*8 + mode*2 + sticky`.

| Ordinals | seed/op | VL | mode | sticky | expected/actual flags |
| --- | --- | --- | --- | --- | --- |
| 681/682 | 1/2 | 1 | 0 | 0/1 | 0/16, 1/17 |
| 683/684 | 1/2 | 1 | 1 | 0/1 | 0/16, 1/17 |
| 685/686 | 1/2 | 1 | 2 | 0/1 | 0/16, 1/17 |
| 687/688 | 1/2 | 1 | 3 | 0/1 | 0/16, 1/17 |
| 689/690 | 1/2 | 2 | 0 | 0/1 | 0/16, 1/17 |
| 691/692 | 1/2 | 2 | 1 | 0/1 | 0/16, 1/17 |
| 693/694 | 1/2 | 2 | 2 | 0/1 | 0/16, 1/17 |
| 695/696 | 1/2 | 2 | 3 | 0/1 | 0/16, 1/17 |
| 697/698 | 1/2 | 3 | 0 | 0/1 | 0/16, 1/17 |
| 699/700 | 1/2 | 3 | 1 | 0/1 | 0/16, 1/17 |

All20 report errors1. Original C increments errors once for the shown flags
mismatch, so that exhausts each reported call's error count: no additional
bit/guard/vstart mismatch was reported for these calls. This is distinct from
the earlier call50 errors64 symptom.

## Oracle And Incremental Value

Original helper op2 is unmasked `vmflt.vv v8,v8,v16`, encoding `6e881457`.
It saves fflags; loads full-capacity lhs/rhs and v0; selects requested VL;
writes sticky to fflags; compares; immediately reads vstart then fflags;
restores saved fflags; restores cap512 and stores the full64-byte mask result.
The original16-instruction vv helper and original allowed tail-bit sets remain
required. There is no scalar FP boxing consumer in op2.

For seed1 the source indices are `(i+1)%16` and `(3*i+5)%16`.
Decoded directly from original fixtures:

| i | lhs/rhs FP16 bits | LT bit | flags |
| --- | --- | --- | --- |
| 0 | 8000 / 4000 (-0 / +2) | 1 | 0 |
| 1 | 3c00 / 0001 | 0 | 0 |
| 2 | bc00 / 7bff | 1 | 0 |
| 3 | 3800 / 7e55 (rhs qNaN) | 0 | 16 |

Thus VL1/2/3 must exclude the first NaN at index3. With four lanes, balanced
comparison requests can deliver index3 as lane3's first local element despite
its architectural inactivity. This is a discriminating tail-NV source, not an
active NaN that should raise NV.

Accepted M8 strict metadata explicitly records call681 flags0 and call682 flags1,
vstart0, same target encoding, at cycles2995619 and3000030 respectively. These
are already successful current-path counterparts of the first two retained
historical failures. Call683 changes loaded mask FF to AA and sticky1 to0, but
the target has vm=1: all modes must be ignored for comparison predication.
It adds a useful stale-predicate/flags-transition check, not a new LT operation.
Source inputs, aliased old-vd layout, and tail NaN distribution are unchanged.

Recommend one continuous original prefix1..700, preserving699 predecessors,
358400 result-bit checks,1400 guards,700 flags/vstarts and original allowed sets.
Only18 positions are new beyond accepted682. Do not launch683 and then repeat
the same prefix per retained line; do not replace full history by a detached
singleton and claim equivalent acceptance.

## Current NV Path And Residual Hypotheses

- `hardware/src/lane/lane_sequencer.sv:1027`: FP comparisons request balanced
  lane operands with zero stream origin; relevant source hazards are preserved.
- `hardware/src/lane/vmfpu.sv:1222`: format-specific classifiers carry per-element
  NV through tag.operand_a. LT/LE use any NaN; EQ/NE only sNaN. Returning bit2 is
  element metadata, not an already predicated exception.
- `vmfpu.sv:1585`: comparison lane flag data **and** valid are suppressed, so
  raw lane NV must not reach the dispatcher through the old direct path.
- `hardware/src/masku/masku_operands.sv:228`: bit2 uses the same shuffle/element
  compaction coordinate as comparison bit0, with zero outside the current slice.
- `hardware/src/masku/masku.sv:798`: architectural activity is exact [vstart,vl).
  At the first slice here only low1/2/3 bits qualify. `:450` publishes registered
  NV only at valid descriptor plus all input valid/ready, AND activity, AND
  `(predicate | replicated vm)`. For vm1, FF/AA/24/00 cannot affect flags.
- `masku.sv:1778`: descriptor replacement is guarded by queue capacity and empty
  mask queue; this retains the prior full-queue ownership repair.
- `hardware/src/ara.sv:256` routes MASKU flags into dispatcher. Dispatcher ORs
  lane flag data without individual valid gating (`ara_dispatcher.sv:1117`),
  making producer data suppression important; this is a contract to observe,
  not a newly proven bug in these calls.

No static contradiction requiring a new patch was found. Tail NV leakage through
the old lane aggregate is consistent with the historical symptom and is already
addressed by the current split producer/consumer path. Static consistency and
accepted681/682 do not prove every later history or establish historical root
cause from an absent old waveform.

If the next authorized700 run is intended for root-cause discrimination, use an
existing-image bounded capture around calls681..700, not a full-run dump:
accepted VMFPU op/ID, operand_a/b, fp_src_fmt, classifier bits/tag on in/out;
lane3 index3 result bit2; processing descriptor and lane fflags data/valid;
MASKU ID/op/vm/VL/start/eew, vrf_pnt/iteration, compact NV, active mask,
predicate and all-lane valid/ready; registered MASKU flags and routed dispatcher
flags; actual sticky clear, target retirement and immediate CSR read.
Expected active mask low bits are1/3/7 and NV remains0. Wrong input/tag identifies
source/owner corruption; correct lane3 NV mapped to bit0 identifies packing;
bit3 excluded but publishedNV identifies acceptance/descriptor gating; no MASKU
NV but CSR16 identifies direct/stale flag ownership or CSR ordering. Do not
infer completion/acceptance from raw out_valid alone, nor prescribe new RTL.

## Same RTL Identity

Fresh byte SHA comparison of each file below in the live integration tree and
both frozen roots showed equality (not inferred from image labels):
`/home/wangwy/fpga_runs/current_board_memory_candidate08/frozen/sources/` and
`/home/wangwy/fpga_runs/current_board_memory_candidate09/frozen/sources/`.

| Relative file (hardware/src/) | SHA256, identical live/M8/M9 |
| --- | --- |
| lane/vmfpu.sv | e9b8c8c2aa952b76661b01fa0a4b53d87e2f1d7219beb40a42a4d6998c5f7b12 |
| lane/lane_sequencer.sv | c11e2a871b91a7aaf940f9e4fb0ef79229a48a2a9b7e2db3fd1108e24dc01dcc |
| masku/masku.sv | 1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d |
| masku/masku_operands.sv | c907488c75b5051a917e61c5ac08bca15859f2f0506fd61dae07dd576569456f |
| ara.sv | 1d190744249603d6c3d6e2c9c21cd5ac121fee2a9c65f5b227be239c320286da |
| ara_dispatcher.sv | c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d |

This is scoped six-file identity, not whole-image identity or M9 acceptance of682.

## Cost And Evidence Pins

M8 measured682: actual child0,4259.165s,2120455 firmware retirements to exit.
Simple700/682 proportional proxy is4371.58s; +20% is5245.89s, below3h.
This is not a measured700 cost or runtime guarantee: require new bounded software
reference cost and fixed reviewed DUT budget. Do not reparse or rerun accepted682.

Evidence paths below, except board report above, are relative to
`verification/fpga/current_board_review/fp_comparison_original/`:

| Evidence | SHA256 |
| --- | --- |
| Original board report above | 78feb29c49c69ee6d4e6dd7803a3bccf8d8c88566b10cbbfd639f630c1cda3e1 |
| ready_audit01/original_contexts.json | 988a2ffe8230e63be1453eb84c29ad0bc5ba34d3199e8a7924a509d5fa1285c3 |
| prepared02/prepared/alias_v8_e16m8_prefix682/original/parent.c | 3652ca2d4f3f7b63995234bf624514dfb318db9cd781aeee0a7533d6c564491c |
| prepared02/prepared/alias_v8_e16m8_prefix682/original/scenario.S | eb5659c77622636492675c2ffd77b2e1a2fc93ede9471013d123f54151a02f86 |
| prepared02/prepared/alias_v8_e16m8_prefix682/original/fixtures.h | 5664c1a4546bb402fe64ef190ca8e4910efa21fc35daea5229a187377eba7cb1 |
| full682_vcs_m8_plan01/prepared01/complete.json | 1669b8c1eb6051015726431e69d665bf01a0678365b824970d2be2c077d71d86 |
| full682_vcs_m8_plan01/prepared01/replay/tests/alias_v8_e16m8_prefix682/strict_original.json | 1e17f1c6ede048f166f96c9a2dc404f9e0dafc16a6e117127941c1a2e3abeeab |
