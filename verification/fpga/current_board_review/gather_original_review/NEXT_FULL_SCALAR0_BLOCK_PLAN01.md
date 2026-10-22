# Natural First112: Full Seed0 / Scalar-Slot0 Block

Read-only planning, 2026-10-11. Only this new document is written. No reference,
host test, DUT, build, service/process query, active-campaign inspection, RTL
change, sealed-input change, or timeout increase. Arithmetic below is planning,
not a newly executed reference or measured first112 result.

## Decision

**Yes: natural first112 is exactly the complete seed0/scalar-slot0 block of a
single selected original child: 7 VLs x 4 masks x 4 restart trials.** It retains
all111 predecessors and closes the stated within-block gaps. It is not the
full2688 child, a Linux replay, a recovered historical stopped tuple, or a
proof about later scalar slots/seeds/process history.

Prioritize a future e8/m8 VI0 first112 preparation over blanket repetition of
all accepted prefixes. Its new upper-half destination and predicate traversal
is meaningful, but admission under the unchanged5M reference limit is tight.
Do not call it ready before an independently authorized bounded reference
actually completes its entire oracle. This note authorizes no execution.

**Budget correction:** the supplied approximately2.621M reference is the
current **VI31** record (2,621,149), not VI0. Current VI0 is2,881,705. Use the
correct per-op record; transferring the smaller count to VI0 hides the narrow
instruction-budget margin.

## Source, Legal Membership, And Order

Paths:

- `W=/home/wangwy/openproject/ara_dsa_signoff_integration`
- `G=W/verification/fpga/current_board_review/gather_original_review`
- `C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`
- `P=C/rvv_permute_partitions01`
- Original C: `C/rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c`.

The actual C, manifest, relevant operations headers and prior immutable
reference/acceptance records were read. All11 original ELF hashes below were
freshly recomputed and match the manifest. Each child has configurations2688,
one selected operation, pass marker RVV_PERMUTE_PASS, archived timeout600s.
That timeout is historical metadata, not the proposed current9000s bound.

At VLEN1024, NrLanes4, ELEN64:

| Shape | Capacity | Legal original operations | Data/source and destination groups | op20 index group |
| --- | ---: | --- | --- | --- |
| e8/m4 | 512 | 1 VX, 2 VI0, 3 VI31, 20 EI16 | v8..11 / v24..27 | EEW16, EMUL8, v16..23 |
| e8/m8 | 1024 | 1 VX, 2 VI0, 3 VI31 | v8..15 / v24..31 | op20 absent: EMUL16 is reserved, not a missing test |
| e16/m8 | 512 | 1 VX, 2 VI0, 3 VI31, 20 EI16 | v8..15 / v24..31 | EEW16, EMUL8, v16..23 |

There are11 legal shape/op combinations, not12. This is a membership inventory,
not a request to run all11. Targets remain masked (`v0.t`), including all-on
mode; none supplies vm=1 coverage. Helpers retain their unused index load and
`mv t3,a6` for VI. Scalar-slot0 means argument0: op3 still selects source31;
op20 still uses vector indices, not scalar index0.

Original loop nesting at C:60-64 is seed, op, scalar-slot, length, mask, trial.
The selected-op filter remains inside these loops. Each preceding excluded op
has896 empty iterations; before ops1/2/3/20 the counts are896/1792/2688/17920.
Preserve them in source, rather than introduce predecessor helpers or new
warmups. Compiler elimination is not architectural execution of these skips.
The first112 contain no calls from scalar-slot1 or another op/seed.

For a chosen op, one-based ordinal is `1 + 16*l + 4*mode + trial`:

| Calls | Length slot | e8/m8 VL | e8/m4 or e16/m8 VL |
| --- | ---: | ---: | ---: |
| 1..16 | 0 | 0 | 0 |
| 17..32 | 1 | 1 | 1 |
| 33..48 | 2 | 2 | 2 |
| 49..64 | 3 | 3 | 3 |
| 65..80 | 4 | 512 | 256 |
| 81..96 | 5 | 1023 | 511 |
| 97..112 | 6 | 1024 | 512 |

Inside each row, four calls each cover all-on, odd elements, i%7==2, all-off,
in that order. Starts are exactly1, floor(VL/2),
`VL <= 1023 ? VL : cap-1`, cap-1. Keep duplicates. Thus VL1024 starts are
1/512/1023/1023, **not**1/512/1024/1023. At cap512/VL512 they are1/256/512/511.
Architectural no-op targets still execute and retain complete checking;112
target retirements does not mean112 backend gathers issue.

First66 ends at length4/mode0/trial1. Calls67..68 finish that all-on mode;
69..80 add the three missing masks. First98 ends at length6/mode0/trial1.
Calls99..100 finish that mode and101..112 add the three remaining masks.
The first112 endpoint is `[0,op,0,6,3,3]`, with start=cap-1 and all-off.

## Oracle And Scope Accounting

Do not extract only calls67..112 or99..112 into a fresh execution. Keep original
seed RNG, both index arrays, all128 predicate initialization bytes, old-vd91,
both guards91, helper order, all13 helper instructions, CSR setup/readback and
every predecessor's full oracle. Stop only after call112's guards/error update.
The original C combines the two guard comparisons with `||`; a strict
successful trace must nevertheless prove both guard values, and every failure
remains fatal. No narrowed active-only or final-call-only checking.

| Scope per child | Calls / returned-vstart-zero checks | Fullcap result comparisons | Guard values | Helper instruction retirements |
| --- | ---: | ---: | ---: | ---: |
| first112, cap1024 | 112 | 114688 | 224 | 1456 (112 at each of13 PCs) |
| first112, cap512 | 112 | 57344 | 224 | 1456 |
| additional coverage versus66, cap1024 | 46 | 47104 | 92 | 598 |
| additional coverage versus98, cap512 | 14 | 7168 | 28 | 182 |

The extra-coverage rows are accounting only, not standalone run plans. Preserve
the independent setup/vector-store checks and all336 helper vset checks, plus
normal exit, firsterror veto and exact PREFIX marker. Guard plus result scalar
loads total114912 or57568 on a successful full112 path. Original CSR oracle is
returned vstart0; do not invent unrelated original fflags/vxsat requirements.

Full child:3*8*112=2688 calls, so112 is1/24, not a complete seed (which has896
calls). The remaining2576 calls include all seven other scalar slots and two
other seeds. Even VI/ei16's unused scalar slots must not be collapsed: they
carry different preceding histories. Full child comparisons are2752512 at
cap1024 or1376256 at cap512, plus5376 guards. A hypothetical all11 first112
inventory is1232 calls/802816 comparisons/2464 guards, still11 prefixes, not11
closed Linux children. Whole Linux C-to-ELF byte-equivalence remains unproven;
ports bind actual original ELF plus helper bytes and source-derived oracle.

## Actual New Hardware Paths

1. **e8/m8 beyond66 is substantial.** MASKU scans from0; lane_sequencer:1223
   sets packed MaskM length to ceil(VL/256). VL512 needs2 aggregate words;
   VL1023/1024 need4, newly crossing the512/768 predicate boundaries in the
   target stream. VL1023 has a partial last output beat and uneven lane extent;
   VL1024 has a full final beat. Exact start1023 reaches a final-element case;
   mode1 enables index1023, modes2/3 disable it. This distinguishes final BE
   preservation from stream/final-grant completion, including an all-off last
   element. All128 predicate bytes and fullcap stores were already setup in66;
   the new coverage is target consumption, not first allocation of those bytes.
2. **Full destination span, not a new source allocation.** e8/m8 targets with
   VL1023/1024 extend writes/scanning into v28..31; first66 real target writes
   were limited below512. Fullcap setup loads/stores and dispatcher full-vs2
   normalization already covered the whole group. Scalar0/31 still reads the
   same low source element, not every source register merely because VL grew.
   Sparse/all-off masks test BE and completion while gather request sequencing
   still proceeds; mask-off does not remove all source requests.
3. **Scalar operations do not add OOR tokens.** VX slot0, VI0 and VI31 select
   in-range0/31 for both capacities, regardless of VL. masku:1383-1405 therefore
   uses ordinary data requests/last token, not final no_data. A full112 scalar
   block must not be advertised as OOR overflow coverage. Later VX scalar=cap,
   cap+1 or high-bit values remain outside this prefix.
4. **EI16 differs, but112 does not create its first OOR terminal path.** At
   cap512 the preserved index formula has index[255]=512 (OOR final at VL256),
   index[510]=0 (in-range final at VL511), index[511]=1 (in-range at VL512).
   All these ends were reached by natural98. New99..112 adds full-length
   sparse/all-off/prestart combinations to mixed in-range/OOR sequencing;
   it does not newly cover an OOR last index. No e8/m8 EI16 may be synthesized.
5. **cap512 extension is lower priority.** Existing98 already reached VL511/512,
   two packed mask words and final destination register, and all masks at
   VL256/511. An extra14 calls adds final-VL masks and start511; it is useful
   for a concrete final-BE/completion hypothesis, not a new maskword/fullgroup
   boundary. Do not rerun accepted m4/e16 VX/EI16 merely to reach112. This note
   does not inspect or duplicate the active e16 VI31 campaign. New VI0 source
   preparation may choose112 initially if affordable, without an extra98 run.

The common backend caveats and frontend VI/VX dependency distinction remain
as documented in VI0_VX0_PATH_REVIEW01.md. No liveness claim follows from these
static comparisons, and unknown stalls are not waived.

## Fixed Budget Feasibility

Completed-record anchors, not live observations:

| Existing66 e8/m8 record | Retired | Elapsed | Other |
| --- | ---: | ---: | --- |
| M6 VX DUT audit | 2672460 | 4052.291789s | 3854541 cycles; approximately659.49 retirements/s |
| VI31 Spike reference | 2621149 | 4.227606s | 165411158 commit bytes |
| VI0 Spike reference | 2881705 | 4.781532s | 189056398 commit bytes |

Simple112/66 scaling gives VX approximately4.535M/6877s; VI31 approximately
4.448M reference instructions,7.17s and267.7MiB log; VI0 approximately4.890M,
8.11s and306.0MiB. Pricing reference counts at the measured VX retirement rate
gives approximately6745s for VI31 and7415s for VI0. These are cross-ELF/cross-op
heuristics, **not predicted exact DUT instructions or bounded runtime proofs**.

Reference limits remain5M instructions,120s,768MiB. The current helper enforces
768MiB as RLIMIT_FSIZE **per output file**, not a proven process-RSS ceiling;
it cannot be cited as a memory-use measurement. VI0's linear instruction margin
is only109834 (about2.2% of5M). Later lengths execute more active expected-value
branches and more vector work, whereas most of the first64 calls have tiny VL.
For example existing VI0 target65-to66 costs49988 retirements versus44898 for
target49-to50. These mixed setup/oracle intervals demonstrate nonuniform cost,
not an exact slope for all future mask/start combinations. Compiler decisions
and prefix-exit code also change the total. Thus112 is plausible but VI05M is
the first tight gate; the linear time/file estimates have much more headroom.

DUT remains case9000s, service3h=10800s. The latter reserves1800s beyond the
case deadline for orchestration/teardown/checking, not an extension of simulation
time. VX scaling leaves2123s under9000; VI0's cross-rate estimate leaves1585s.
A20% slowdown takes the latter to8898s, nearly the bound. Higher-VL vector cost,
backpressure, load and CSV checking can defeat either estimate. Actual admission
must use the completed new reference, private ELF/trace oracle and unchanged
pins, never treat a timeout/partial trace as PASS. No larger timeout is proposed.

For cap512, accepted e16 VX98 has1997782 retirements/2980.885962s. Scaling to112
gives2.283M/3407s, substantially easier; this does not price m4 or EI16 exactly.
Their lower incremental hardware value, not merely affordability, determines
whether an extension is justified.

## If112 Does Not Fit

Keep an exact contiguous original prefix, not a selection of easier tuples.
The following are **alternative advance-review boundaries**, not an automatic
ladder of repeated simulations. Select one from completed reference evidence
and a conservative fixed-budget estimate before any DUT admission:

| e8/m8 stop after | Exact completed coverage | Results / guards | VI0 linear reference / VX linear seconds |
| ---: | --- | ---: | ---: |
| 80 | all masks/starts through VL512 | 81920 /160 | 3.493M /4912s |
| 96 | additionally all masks/starts at VL1023 | 98304 /192 | 4.192M /5894s |
| 100 | additionally VL1024 all-on, all4 starts | 102400 /200 | 4.366M /6140s |
| 104 | additionally VL1024 odd mask, all4 starts | 106496 /208 | 4.541M /6385s |
| 108 | additionally VL1024 i%7==2, all4 starts | 110592 /216 | 4.716M /6631s |
| 112 | additionally VL1024 all-off, all4 starts | 114688 /224 | 4.890M /6877s |

Prefer a complete-length boundary96 if112 cannot be admitted; it preserves all95
predecessors and closes VL512 masks plus VL1023, but explicitly leaves VL1024
open. A100/104/108 boundary is valid only with its entire prior history and
oracle, not as detached final4-call tests. If even96 cannot fit,80 is the next
complete-length boundary. These are feasibility estimates, not guarantees.

If112 actually exceeds5M/120s/file bound or predicted9000s, preserve that result
as NOT_COMPLETED_WITHIN_BOUND; do not trim oracle, raise limits or auto-retry.
No partition into fresh boots can claim the same full111-call history for112.
Achieving all112 under an insufficient fixed budget would require a separately
reviewed history-equivalent implementation or complete-state continuation;
neither is supplied/authorized here. Remaining coverage must stay explicitly
open rather than be replaced by easier sampled endpoints.

## Fresh Identity Anchors

Original ELF paths are `P/release/binaries/rvv_permute_restart_<suffix>`:

```text
e8_m4_ops1 8f5fd128fdc39014de31bd72f9e997f76d07382ee6268d7e6da83a59b7ddfcd8
e8_m4_ops2 498805cf438a11729e74f0ac7b74068fa5e19bbcf56318790b01afc798d18b65
e8_m4_ops3 a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b
e8_m4_ops20 15469ee7ca24fd7a7dac6e282358872a5d9c3dfc836e5de363661925fac70c18
e8_m8_ops1 7b6623f49a5aee9ae03a3365dc69e898b922ffc61a113c58aae71f96342c83cf
e8_m8_ops2 cc5015d9e7838bfc4f0d4f2b0627e6a08930bd4058b12651a4f988a5c9b1d712
e8_m8_ops3 ef3a7ff6d6dc48a7e5f20adbb7954490c08c7cbbdcd03afe9bbd4859dee7580c
e16_m8_ops1 25c6f4e22b01d0d1457c18e289cca6fe7cd3e85113175a3c9e5c82e3d56c3d2a
e16_m8_ops2 13a9b694ade91e25687108b4bf93b50ecc2d80c3a2a6fd532b269dac3b4aafcf
e16_m8_ops3 16a715c87479c206545de7e5e9173fcd5ac93a48fe71a6c9dcfd7466993bd853
e16_m8_ops20 21a28efe2ef7b79f9511c9b793bf0235bbc81944b27f1196179642f2a5a8c888
P/manifest.json 6e6c083670aaf312e9eeb252e576ec88cd5fe3a94b415c3f619c2bb9e7c43e58
original.c b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca
```

Existing evidence paths relative to G and freshly recomputed SHA256:

```text
e8_m8_ops1_prefix66_terminal_audit01/audit.json
7840992136756479dd019a95eab8534a05d99ecb07998e83fa6c698f2eb4a6ee
e8_m8_ops2_prefix66_prepare01/reference/reference.json
8377e632ea80fa92cfd4c82d77835ba34b505e8a6d32181ac1b8314d87c710f4
e8_m8_ops3_prefix66_prepare01/reference/reference.json
a2b3e9848042991afcf6ccff518f53897cf1edd2e09438cfa7fa101160d23286
e16_m8_ops1_prefix98_terminal_audit01/audit.json
d22348024e99b1eb881192472128e8149ffe3b63041a7fe57aa25843b1d043f7
```

Current source hashes: dispatcher c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d;
lane_sequencer c11e2a871b91a7aaf940f9e4fb0ef79229a48a2a9b7e2db3fd1108e24dc01dcc;
MASKU 1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d.
M6 image.json at `/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image/image.json`
hash a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0.
These are identity references only, not a newly repeated whole-image pin gate
or validation of a changing workspace. No active e16 VI31 output was queried.
