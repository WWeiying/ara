# Archived Gather Stalls and Parent Histories: Preparation Plan

Date: 2026-10-11. Status: **PLAN ONLY; no DUT authorization, source edits,
builds, reference executions, RTL edits, or campaign polling performed.**
This new note is outside all sealed preparation and result directories.

## Acceptance Boundary

`remainder75_01/TERMINAL83.md` records accepted8 + remaining75 = exactly83
authentic selected source singles on M4. That result does not execute the
original Linux ELFs, their preceding calls, or the full parent histories.
The eleven archived `gather_operand_stream` stalls are different source keys:
four e8m4 children, three e8m8 children, four e16m8 children. None of these
three shapes is in the accepted83. Parent/partition aliases and older reports
must remain identity links, not additional unique tests or superseded failures.

Path abbreviations used below:

- `C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`
- `P=C/rvv_permute_partitions01`
- `O=C/rvv_permute_restart01`
- `R(N)=C/rvv_recovery08_N/terminal_scene`
- `H=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/gather_original_review`

Every short case name below has prefix `rvv_permute_restart_`.

## Authentic Eleven

For every row, canonical ELF is `P/release/binaries/<name>`; identical frozen
scene ELF is `R(N)/<name>`. Both were read and SHA-verified against the row.
Original assembly/header are `P/<name>/operations.S` and `operations.h`, not
newly generated instructions. Each child selects exactly one opcode through
`PERMUTE_OP_MASK=1U<<op`, retaining 2688 actual calls (3*8*7*4*4).

`last_pc` and `head_pc` below are the **debug snapshot's reported PCs**, not
an invented last tuple or proof that the last_pc instruction is still in flight.
Every head is last_pc+4, `00802573` (`csrr a0,vstart`). Opcode mapping:
1=`308e4c57` vrgather.vx v24,v8,t3,v0.t;
2=`30803c57` vrgather.vi v24,v8,0,v0.t;
3=`308fbc57` vrgather.vi v24,v8,31,v0.t;
20=`38880c57` vrgatherei16.vv v24,v8,v16,v0.t.

| Child | Recovery N | last_pc / head_pc | Original ELF SHA256 |
|---|---:|---|---|
| e8_m4_ops1 | 154 | 0x105dc / 0x105e0 | `8f5fd128fdc39014de31bd72f9e997f76d07382ee6268d7e6da83a59b7ddfcd8` |
| e8_m4_ops2 | 155 | 0x10600 / 0x10604 | `498805cf438a11729e74f0ac7b74068fa5e19bbcf56318790b01afc798d18b65` |
| e8_m4_ops3 | 168 | 0x1063e / 0x10642 | `a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b` |
| e8_m4_ops20 | 169 | 0x10980 / 0x10984 | `15469ee7ca24fd7a7dac6e282358872a5d9c3dfc836e5de363661925fac70c18` |
| e8_m8_ops1 | 171 | 0x105dc / 0x105e0 | `7b6623f49a5aee9ae03a3365dc69e898b922ffc61a113c58aae71f96342c83cf` |
| e8_m8_ops2 | 172 | 0x10600 / 0x10604 | `cc5015d9e7838bfc4f0d4f2b0627e6a08930bd4058b12651a4f988a5c9b1d712` |
| e8_m8_ops3 | 173 | 0x1063e / 0x10642 | `ef3a7ff6d6dc48a7e5f20adbb7954490c08c7cbbdcd03afe9bbd4859dee7580c` |
| e16_m8_ops1 | 175 | 0x105ee / 0x105f2 | `25c6f4e22b01d0d1457c18e289cca6fe7cd3e85113175a3c9e5c82e3d56c3d2a` |
| e16_m8_ops2 | 176 | 0x1060e / 0x10612 | `13a9b694ade91e25687108b4bf93b50ecc2d80c3a2a6fd532b269dac3b4aafcf` |
| e16_m8_ops3 | 177 | 0x1064a / 0x1064e | `16a715c87479c206545de7e5e9173fcd5ac93a48fe71a6c9dcfd7466993bd853` |
| e16_m8_ops20 | 178 | 0x10994 / 0x10998 | `21a28efe2ef7b79f9511c9b793bf0235bbc81944b27f1196179642f2a5a8c888` |

For all eleven, both snapshots have identical retired counts, identical PCs,
zero DDR read/write outstanding and zero DDR errors. Cycles grow by
559824418..598691642 (about11.20..11.97 seconds at the recorded50MHz).
These are genuine archived **no-retirement observations**, not the old source
single's empty-loop timeout. The absolute retired counter includes Linux,
boot and any earlier commands; it is not this program's instruction count.
It cannot be used as a Spike budget or to locate a call ordinal.

The eleven reports have no `RVV_PERMUTE_TRIAL` identifying the unreturned
call. Source prints that marker only for op0/seed0/scalar-index0/mode0.
Numeric DETAIL lines are post-call oracle messages, not pre-call markers;
printing stops after the first20 errors, so their last line is not the stall
tuple. e8m4/e16m8 last numeric lines show vl256/vstart128; e8m8 shows
vl3/vstart1. Neither fact licenses calling vl512/vstart256 the eleven's
actual failing tuple. No vector/GPR tuple snapshot is present in the inspected
terminal report schema (core PCs/counters, DDR counters, zero mailbox only).

Important original process history: recovery168 ran e8m4_ops8 -> ops9 ->
ops10 -> ops11, each passed2688 cases, then e8m4_ops3 stalled. The preceding
PASS text belongs to those four entries, **not ops3**. The other ten terminal
reports list the stalled program as their first result. Recovery metadata says
unchanged-bitstream restart; its `previous_report` links are administrative
history, not proof that a previous stalled process was an in-core predecessor.
Linux/context effects are not reproduced simply by concatenating C functions.

## Source and Parent Recovery

Authentic partition C is already retained at
`C/rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c`:
SHA256 `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca`.
It is the complete unfiltered oracle, not that reduced single's scenario.c.
The current main-tree `permutation_oracle.c`, `permutation.py`, and `build.py`
were checked against the partition manifest and match its three source hashes.
Do not use changing main-tree paths as future sealed inputs; copy authentic
bytes into a new successor only after preparation review.

Original full-parent C is recoverable exactly, without inventing an oracle:
remove only these two partition additions from the retained original.c:

```c
#ifndef PERMUTE_OP_MASK
#define PERMUTE_OP_MASK ((1U << OP_COUNT) - 1U)
#endif
```

```c
            if(!(PERMUTE_OP_MASK & (1U << op)))continue;
```

This read-only, in-memory reconstruction gives
`3e47911abdcff59fbda1986b04d7ba757728605d8719d0cc5347a1c037666884`,
exactly `O/manifest.json`'s original source hash. It is not yet a prepared file
or rebuilt original ELF. Original parent assembly/header exist at `O/<name>/`.
Their bytes equal the corresponding child files for the three shapes:

| Shape | capacity at VLEN1024 | Original parent ELF SHA256 | operations.S SHA256 |
|---|---:|---|---|
| e8_m4 | 512 | `ffcf7785c8bf6dcb553456b60df4240bd106855df4189193b3b635a20b3cb2d5` | `118a8c9572532a2b332749165cff3cea9323a49722641dcf64b14fd501ccd774` |
| e8_m8 | 1024 | `8de6bc735648afacd704f3cdcc00c2a1bc86ca8183f6fee5146077610d75e1a3` | `6210a2d96c74a3d15b331b1aeff3d2a1eef01fc64d7becafbc53a042b3460824` |
| e16_m8 | 512 | `6440459edce6c313d1dbb3bcb0043cd372e10430a85dff4958b76703956634e1` | `40bce22639d00865881e06337270ed76fd37e01c7891296471934accbf7afbcf` |

Parent canonical ELF `O/overlay/opt/ara-tests/<name>` and alias
`C/rvv_additions36/binaries/<name>` were hash-checked for **all22 parents**.
Their exact22 identities remain in O/manifest.json; no new identities are
created by aliases. Nineteen accepted83-associated parents have56448 calls
each; the three additional parents above have56448,53760,56448 respectively.
All22 full histories total1239168 calls. e8m8 has20 ops, not21: ei16 would
require reserved index EMUL16 and is authentically excluded. Do not add an
e8m8_ops20 test to make a symmetric shape grid.

`P/parent_mapping.json` preserves parent-to-child identity, but explicitly
does not make partitions original execution or acceptance. Archived original
gap audit still labels19 partition-eligible parents stalled; three unsplit fractional
parents are absent from that gap list, which alone is not a new M4 PASS.
Keep the existing `H/lineage83.json` links for the19 numeric parents separate
from the new3 shape parents and eleven children.

## Required Original Semantics

Retain seed order0..2; xorshift13/7/17 with initial
`0xe736815b449aec21 ^ seed`; whole-capacity input/indices/indices16 setup.
Retain scalar values0,1,cap-1,cap,cap+1,UINT64_MAX,2^63,2^63-1;
VL order0,1,2,3,cap/2,cap-1,cap; four masks (all, odd, i%7==2, none);
four starts (1,vl/2,vl-if-representable-else-cap-1,cap-1). Retain tu/mu,
the complete original thirteen-instruction routines including all three fullcap
loads, mask load, vstart write/read, target and fullcap store, and all headers.
Capacity and vlenb must be checked, not hard-coded to a different board width.

Every completed call must check returned vstart==0, **all cap output words**,
both91-valued guards and cumulative cases/errors. Below-start, inactive,
masked-off and tail elements must remain91. Gather index must be tested
against cap; OOR results must be0, with full-XLEN vx scalar semantics.
Preserve oracle errors/statistics and the original continue-after-numeric-error
behavior within a program: early-aborting on an old prestart DETAIL would
delete the later archived stall history. The independent runner may failstop
between programs. Final acceptance still requires full expected call count,
errors0, authentic PASS marker, exit0 and no failure/exception marker.

A source port replaces Linux ecall I/O/exit only using existing integration
runtime/GCC. It is not Linux ELF replay or OS/predecessor acceptance. Prefix
completion must have an explicitly separate PREFIX result; never emit an
unqualified original2688/56448 PASS for a shorter execution.

## Discriminating Prefixes, Not Arbitrary Reductions

Order is seed -> op -> scalar-index -> length-index -> mode -> trial. One
op/seed has896 calls. Use one-based executed-call ordinals; retaining the
natural prefix means running **every earlier executed call and oracle** from
program entry, without reset, checkpoint restore, oracle thinning, or loop
narrowing away actual predecessors. Removing excluded-op empty iterations
in a partition may reduce scalar-only overhead, but must be separately
diffed and labeled a source port, not original cycle-identical execution.

Archived companion op0 and full-parent reports provide exact localization
boundaries: R153/R44 (e8m4), R170/R77 (e8m8), R174/R78 (e16m8) end with
`RVV_PERMUTE_TRIAL vl=512 vstart=256`; op0 condition fixes seed0,scalar0,
mode0,trial1. Thus e8m4/e16m8 have length-index6, ordinal98; e8m8 has
length-index4, ordinal66. These companion vv records are classified under
packed-mask restart, **not among the eleven gather_operand_stream records**.

Recommended next preparation scope, gated before any future DUT launch:

1. Prepare three faithful parent-start op0 prefixes ending at those exact
   archived boundaries (98,66,98 calls). Their PASS would cover actual
   parent prefixes, not full parents. Retain original op0 UART/drain behavior
   or explicitly account for runtime port differences.
2. Prepare eleven partition-start prefixes through the same shape-specific
   boundary (98 calls for e8m4/e16m8,66 for e8m8). These are evidence-based
   **localization candidates**, not claimed exact eleven-stall reproductions.
   Keep a before/after tuple record in non-vector memory and use commit trace
   to bind each call and return; no per-call UART, extra vector operation,
   fence, or queue drain. Any instrumentation timing difference is disclosed.
3. First discriminant: e16m8_ops1 boundary single vs its natural98-call
   partition prefix vs a true994-call parent prefix (896 preceding op0 calls
   plus98 op1 calls). A boundary single uses the authentic same seed/scalar/
   mask/start and complete original setup/oracle, but does not substitute for
   the preceding98/994-call histories. If parent blocks in op0, report that
   earlier blocker instead of silently jumping to op1.
4. For e8m4_ops3, preserve the optional **separate process-history control**
   ops8 -> ops9 -> ops10 -> ops11 -> ops3. Each predecessor has2688 calls;
   do not reduce it to one move. A bare-metal concatenation can only test
   operation-sequence dependence, not claim Linux process/context replay.
   Prefer deferring this expensive control until standalone prefix evidence
   actually distinguishes a predecessor-dependent failure.

Parent prefix ordinals to the same boundary are994,1890,2786,18018 for
e8m4/e16m8 op1,2,3,20; e8m8 op1,2,3 are962,1858,2754. Do not select only
gather predecessors for op20: original ops4..19, their masks, scalar/VL/start
sweeps and full oracles must execute first. For the existing numerical83
tuple, parent ordinals are33,929,1825,2721,17953 for ops0,1,2,3,20.
A parent-start op20 prefix also reaches earlier selected gather points; reuse
that trace instead of counting nested prefixes as independent closure.

If a localization prefix completes, the eleven's exact tuple remains open.
Next endpoint must come from recovered per-call evidence or the authentic
complete2688-call child, not random masks/indices or a guessed trial. If a
prefix blocks, compare observed last before/after tuple and request/response
trace with the archive; only then propose one bounded, focused signal capture.
Full-parent closure requires each full unbroken source history, or separately
authorized original Linux ELF replay. Restarting each seed/op chunk loses
predecessor state and is not full-parent closure.

## Retirement and Runtime Admission

Existing measured sources: `H/TIMEOUT_TRIAGE.md`, sealed
`H/remainder75_01/reference75/reference.json`, and
`H/remainder75_01/vcs_candidate04_01/complete.json`. The latter75 runs have
11275..36030 terminal cycles,23.17..54.03 seconds, and approximately484..912
simulated cycles/second (273..528 scalar retired instructions/second across
these whole runs). Spike single firmware retirement is11416..26135, not DUT
cycles. Representative cap256 singles:

| Source single | DUT retire | DUT cycles | elapsed seconds |
|---|---:|---:|---:|
| e8_m2_ops1 | 16116 | 28327 | 36.88 |
| e16_m4_ops1 | 17943 | 31086 | 40.43 |
| e32_m8_ops1 | 20503 | 35375 | 46.42 |

None measures a cap512/1024 large-VL prefix. Repeating whole-single cost is
also not an actual prefix count: it repeats boot/RNG but misses large-VL
gather latency. An explicitly coarse workload illustration is nevertheless
useful for admission:98*(512/256)*28327 =5552092 cycles;66*(1024/256)*28327
=7478328 cycles, corresponding to about1.7..3.2 and2.3..4.3 hours at the
observed rate. Retired illustrations using16116 are3158736 and4254624.
These are **not measured counts, guaranteed bounds, or an authorized timeout**.
They show why this plan cannot inherit300seconds and call a timeout a stall.
Large-VL serial gather may make these illustrations optimistic; common setup
reuse may make them pessimistic.

Known exact work bounds are more defensible: a98-call/cap512 prefix requires
50176 scalar output checks+196 guards;66-call/cap1024 requires67584+132.
The e16m8 op1 parent994-call prefix requires508928 checks+1988 guards;
op20 parent18018-call prefix requires9225216+36036. Each full child requires
2688*cap output checks; full parents56448*cap (53760*cap for e8m8).
Even empty-loop overhead alone was measured at336883/740576 retired scalar
instructions after the old e16/e8 single oracle, with continued PC retirement.
That old300s event is not evidence that these archive PCs make progress.

Before a DUT plan can be marked ready, bounded **preparation-only** work must:

- First recover/seal C, original asm/header, compile flags, parent/child ELF
  aliases and exact endpoint inventory; keep all83 accepted inputs untouched.
- Host-check the complete prefix tuple stream, RNG digest and cap-wide oracle
  values against the original loops, including cases/errors and guard counts.
- Build only existing host/Spike/SoC source ports in a new directory, after
  review. Run bounded Spike on the three initial prefixes, then the eleven;
  initial preparation limits: jobs2,120seconds per reference,5million firmware
  retirements per localization prefix, no automatic retry or limit increase.
  A hit is a preparation budget stop, not RTL failure; retain logs and report.
- Record actual Spike retirement through exit plus per-call target/return
  counts. Full retirement logging must have a byte cap, since millions of
  rows can themselves dominate runtime/disk. Reference limits above are a
  proposed work bound, not a claim that every prefix fits them.
- Do not extrapolate the994/18018-call parent or10752-call process predecessor
  control into a long VCS batch. Review actual prefix retirement and measured
  existing trace throughput first; if it cannot fit a reviewed bounded probe,
  defer it explicitly. No higher DUT timeout or new image is approved here.

## Frozen M4 Reuse and Hypothesis Gates

Reuse only `/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image`:
image.json SHA256 `e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`;
snapshot SHA256 `b8dcc5d0efc55af13b1e194866135ac2d7370bbcc75276e37d402c5235ea545d`;
simv SHA256 `2caf02a142d9f28fa2bf390ab5225465e4a5281b6877a04eda976cfe80f27502`.
Existing integration/run.py image settings:4 lanes,VLEN1024,qbs1,akv1,
akv_v2=1,L2=2MiB,asserts enabled,no FSDB/code coverage. No rebuild or RTL edit.
Original Linux ELFs need Linux/syscall context and cannot be treated as
bare-metal binaries just by pointing this image at them.

Read-only M4 masku.sv inspection establishes the discriminating path:
index FIFO push -> in-range source request (or final OOR no-data token) ->
broadcast request accepted by all four lanes -> data/index/mask result gate
-> result queue/commit and completion. Per-lane valid remains asserted until
acceptance; idx FIFO, request FIFO and result queue are distinct obligations.
No archive snapshot observes these internal states. Mask starvation versus
request/data accounting therefore remains a hypothesis, not a proven cause.

If later authorized focused observation becomes necessary, use existing
image-accessible probes first: `vinsn_issue.{id,op,vl,vstart,vm}`,
`masku_operand_{alu,vd,m}_{valid,ready}`, `vrgat_cnt_q`,
`vrgat_{idx,req}_fifo_{push,pop,empty,full}`, `vrgat_req_valid_mask_q`,
per-lane `masku_vrgat_req_{valid_o,ready_i}`, `vrgat_idx_oor_q`,
`result_queue_cnt_q/full`, `issue_cnt_q/processing_cnt_q/commit_cnt_q`,
and completion. Count each actual handshake, not asserted valid cycles.
Request FIFO pops only after all lanes accept that head; OOR indices do not
all require data responses. A stable missing mask operand with otherwise
available inputs distinguishes starvation; a stranded index/request/data
obligation after mask supply advances distinguishes token accounting.
No FSDB build or extra instrumentation is authorized by this note.

## Evidence Pins

The read-only verification checked11 scene/canonical ELF identities,
11 report hashes and all22 parent canonical/alias ELF hashes. Preserve these
paths and hashes in a future preparation manifest, not just a family label.

| C-relative file | SHA256 |
|---|---|
| stall_family_triage02/triage.json | `eb87f0ed9c07b3978e91e35ff5bcc0824388beb312510ba942ef061c0f63043f` |
| rvv_permute_restart01/manifest.json | `deaab469c465ca2eff67b774049d9c46bee0a6786705e4c8289f7dd6fcf89f46` |
| rvv_permute_partitions01/manifest.json | `6e6c083670aaf312e9eeb252e576ec88cd5fe3a94b415c3f619c2bb9e7c43e58` |
| rvv_permute_partitions01/parent_mapping.json | `46b142c59ce1bf63e122355bba5ca03f86b8a0e63dc5237826f3afa68062c1d9` |
| rvv_permute_partitions01/reference_1024.json | `b08243b7d357c8da59b36bcd8643031592d54b188fc98187cf3e19adfaf39188` |

Archived QEMU1024 child reference exit0/PASS is useful source-oracle evidence,
not Spike retirement evidence or M4 acceptance. Individual terminal report
SHA256 values (all paths `R(N)/report.json`):

```text
154 88a97ccf1a0ce9ca8644d06321a992930418f3f59b23c2c48eaa28d1a61dbe03
155 ad8fb5a60fa778ecc50da6ba117ea51b4a7b953b4515fa73eb6dddfec6d113c9
168 0908961a67b3b26f032efdd264869205f0b1930b46eb72eac5aaf714ff4266a1
169 148a45a63a6c1129c4fb661d0080481056267b8d4c4d36221676989e1dd003e8
171 65aa957c80a1ad93200756af1d1cf98661cf4325980171ef1a0fc459f6fab72e
172 419c4dc30fa11412c89eb16f2ba229b8e6a16ebe4390b4a6e5dee1c686531417
173 1ca4e0f534d0fb804f94ba8e127a32945eb45a6de4b2bd8ab8d6ac40848ba50d
175 f23cbb21bb4a134d61ed4a4b4e2737fe9b1f1e04daa1b23656c219d8064eaa55
176 f6a807d2460cc3237df1e033a6a90796a51b76f03c1c9197984c0f9c4d7a698f
177 15a4bd6236a76e9ef8b3eec69fdf018ffb85ab3989114fad066851c0635f1bbf
178 586f53d281016fc62cf5c5dbb0cb58c035585bf1d7553ccd63c7069a7b4ba965
```

Remaining acceptance gaps: exact eleven unreturned tuples;14 initial source
prefix ports/reference retirement budgets; source parent-start discriminants;
the recovery168 process-history distinction; full22 uninterrupted histories;
and original Linux ELF/OS acceptance if required. This note closes none of
those gaps by assertion. Recommended next action is review of this bounded
preparation scope, not a DUT launch.
