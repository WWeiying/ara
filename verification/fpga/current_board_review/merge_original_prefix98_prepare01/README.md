# Original Integer Merge Natural Prefix98

**REFERENCE_EXECUTOR_PASS_PENDING_INDEPENDENT_REVIEW_NOT_DUT**.
One software preparation and one bounded Spike execution; no VCS, RTL build,
Verilator, ZCC, live-simulation query, retry or modified frozen dependency.
READY.json is the new owned seal. Independent source/reference review and
any subsequent DUT admission remain separate.

## Scope And Source

Original child: `rvv_permute_restart_e16_m8_ops4`, first98 natural calls with
all97 predecessors, SEW16/m8, cap512. Endpoint tuple `[0,4,0,6,0,1]` means
seed0/op4/scalar-slot0/VL512/mask0/vstart256. Preserve the first96 calls at
VL0,1,2,3,256,511, including all original mask/start duplicates, and call97
at VL512/start1. Stop after the complete original oracle of call98, not at
target retirement. This is not the full2688-call child, unpartitioned parent,
Linux execution, or a known historical stopped tuple.

The old recovery159 report has empty console and no last tuple. Its actual
ELF identifies integer `vmerge.vvm`, not FP merge or gather. A bounded current
READY/reference/complete/README search found no equivalent successful integer
op4 prefix; the existing FP merge195 is different and was not rerun.

Campaign root: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.
Original ELF is `rvv_permute_partitions01/release/binaries/rvv_permute_restart_e16_m8_ops4`;
S/header are in `rvv_permute_partitions01/rvv_permute_restart_e16_m8_ops4/`.
Authentic shared C is retained under
`rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c`.
It matches the op4 manifest's original C identity, despite that storage name.

| Identity | SHA256 |
| --- | --- |
| Original Linux ELF, partition and recovery scene | 275c9d872111a37c28e7466b7fbd7f263a545918315b8a98284d456950d22118 |
| Shared original C | b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca |
| Original operations.S | 40bce22639d00865881e06337270ed76fd37e01c7891296471934accbf7afbcf |
| Original operations.h | 886bbcff73cda9d52dd3ab7d152aa319d900959bffaf02de0345d9292a5e5cd4 |
| Prepared SoC ELF | 4e495abc1ec6b553554c5ddee992db88234c969adcba2f92b90ed6c78ea245ab |
| Prepared Spike ELF | 48a6cf76563eb0bbaf771858532237bd0a2c49d7edd3abf8021f1df1d8607e96 |

`source_diffs/` exposes only the established Linux wrapper adaptation and
post-oracle prefix stop/explicit PREFIX marker. All seed0 RNG/source/index
generation, original filtered op0..3 loops, masks, original C checks, guards
and returned-vstart checks remain. Defines are SEW16,RESTART_PERMUTATIONS1,
PERMUTE_OP_MASK16. No invented warmup or skipped selected predecessor.
The complete original Linux ELF rebuild is not claimed; the archived original
source identity and every actual helper encoding are separately verified.

## Merge Oracle And Actual Assembly

For every body element `[vstart,VL)`, v0=1 selects `indices[i]` from v16;
v0=0 selects `input[i]` from v8. Neither branch is gather indexing, an OOR
rule, nor masked-off preservation. Prestart/tail remain0x005b. a1 is ordinary
indices, not indices16. Both index arrays, source and all128 predicate bytes
retain the original source initialization. a6/t3 remain scalar0 and the
original unused `mv t3,a6` is retained.

All13 actual instruction words match archive/SoC/Spike. Original target
PC0x10684, SoC PC0x80000798, Spike PC0x800007e4; opcode5c880c57.
Raw checks include all source/old-destination vector registers and mask before
each target, actual VL/vtype/vstart, all512 result elements after target,
all512 address/value store pairs, original scalar LHU output/guard reads and
returned-vstart0. Setup values checked per call:2178.

| Actual Reference Evidence | Count |
| --- | ---: |
| Original calls / each of13 helper instructions | 98 / 98 |
| Selector-zero / selector-one body results | 2722 / 2669 |
| Full512-element scalar results / guard reads | 50176 / 196 |
| Returned-vstart0 / three vset returns per helper | 98 / 294 |
| Firmware retired through successful HTIF store | 2020160 |
| Original capacity helper calls / unused helpers executed | 1 / 0 |
| Post-HTIF exact self-parking instructions / bootstrap records | 4835 / 5 |
| Entire raw retired record count | 2025000 |
| Spike process wall time / rc | 3.426291472s / 0 |
| Raw commit bytes | 130671353 |

The full raw vector/data trace is `reference/commits.log`, SHA
200cae142a2c252b21fea3f15b0a15727943e0367de06a98dbe138a2769f0452.
`window_audit.json` separately checks the entire file, not only through HTIF:
only original `0xa001` self-jumps at0x8000007e are allowed after successful
HTIF. These4835 parking instructions are retained, not counted as oracle
work or silently discarded. All helper windows are contiguous and every
unused helper internal PC is forbidden. No raw line was modified.

## Profile, Budget And Negative Gates

Actual command is in `reference/command.json`: accepted restartgold Spike
SHA c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2,
`--isa=rv64gcv_zvl1024b -m2`, no Zfh/Zvfh required for integer SEW16.
Compiler flags are rv64gcv/lp64d and existing non-ZCC GCC. SoC and Spike ELFs
use their respective existing runtimes; both are pinned, not interchangeable.

Before the single reference, actual compiled-loop review established the
4,309,396 instruction upper allowance in STATIC_BUDGET.md/cost_table.json,
below5M steps. Limits were120s/5M/768MiB per file and never changed. Reference
execution cost is distinct from the later offline checks; only one Spike
process was invoked. Existing reference helpers/outputs remained unchanged.

Host original-C oracle: **1 positive +9 negatives PASS**. Negatives cover
selector-one, selector-zero (legacy injection name `inactive`), prestart,
tail, both guards, returned-vstart, erroneous gather-style mask-off behavior
and reversed vector source selection. The original C consumes independent
Python fixtures; the positive checks every original initialization/control.

Offline audit: **5 corrupted raw fixtures rejected** (wrong halfword, target
encoding, returned-vstart, missing initialized bytes, missing oracle).
Full-file window audit: **3 additional negatives rejected** (unused internal
integer PC, unused gather target, duplicate op4 interior outside its window).
These are Host/offline checks, not extra references or DUT evidence.

Measured2020160 reference retirements imply approximately3014s using the
same-shape M6 gather's670.20 retired/s proxy, or3617s with20% margin.
At the older273/s proxy this is7399.85s, or8879.82s with20% margin, narrowly
below9000s. Neither is measured VCS performance for merge; resource conditions
and vector work differ. No DUT timeout, launch or acceptance is authorized.

All artifact and dependency hashes are in READY.json/baseline_pins.json.
The completed local audits are producer evidence pending independent review,
not a claim that Aquinas or another reviewer has already accepted them.
