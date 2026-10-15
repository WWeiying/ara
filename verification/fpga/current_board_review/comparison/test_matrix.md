# Comparison regression inventory

## Final consumer status

**24/24 real-MASKU unit cases PASS:** `consumer_after05/status.json` 23/23,
plus `consumer_after06/status.json` 1/1. Both use parent MASKU SHA256
`1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d`.
No consumer cases remain running or uncompleted. Coverage includes e16/e32/e64
NV active/masked-off/prefix/tail qualification, unmasked and integer controls,
multiple slices/mask words, operand/output stalls, and the legal e8/m8 VL769
four-word staggered-lane full/pop/refill test. NV payloads are contract port
stimuli; these units do not claim to validate the VMFPU classifier itself.

Before failures remain intact. The decoder-only EW8/output-SEW test bug and
the independent real full-queue address overwrite are separately documented
below. All software/provenance/ELF inputs pinned by parent final03 are unchanged.
Parent owns the running final03 full-SoC build/replay; its result is not claimed
here. The software matrix's existing four Spike programs remain 4/4 PASS
(303 directed points including the isolated-prefix derivative).

## Independent software probes

`prepare_matrix.py` builds new `prepared_matrix`, `spike_matrix`, `soc_matrix`.
Original five ELFs and pinned prepared inputs are unchanged.
`reference_matrix01/reference.json`: 4/4 Spike programs PASS, explicit ISA
`rv64gcv_zvfh_zvl1024b`, including nonzero-vstart capability probe.

| Program | Cases | Provenance and coverage |
| --- | ---: | --- |
| prefix_quiet_tail | 1 | Original prestart derivative: ONLY v8[15] 0x7c55 -> 0x7e55; v16[5] remains sNaN, VL8/start6; archived assembly unchanged; reconstructed fixture oracle and separate integer audit both adjusted |
| matrix_e16 | 102 | New directed oracle and assembly; m8; EQ/NE/LT/LE, finite control, sNaN/qNaN in either source, active/all-off/tail/pure-prefix/later-slice-active/later-slice-masked-off; two additional 256-mask-bit boundary cases |
| matrix_e32 | 100 | Same base matrix, without >256-element cases |
| matrix_e64 | 100 | Same base matrix, without >256-element cases |

The new matrix uses positive finite 1.0/2.0 plus exact NaN bit patterns.
Independent integer rules: EQ/NE signal only sNaN; LT/LE signal any NaN.
Only active elements contribute NV. Finite EQ/LT use integer equality/order
over those positive encodings; NaN result rules are explicit. Later-slice
cases initialize sticky NX and require it to remain set. Every case checks
actual v8/v16/v0 readback, old-vd preservation in prefix/masked body, allowed
mask-tail alternatives, guard bytes, postinstruction vstart and fflags.
No scalar fixture filtering, hints, FP scalar oracle, or exception weakening.

`prefix_before01`: retained final01 VCS image measured FAIL, expected flags=0,
actual=16, vstart=0, data_errors=0, setup_errors=0, oracle_disagreements=0.
Input log confirms v8[15]=0x7e55 and sole sNaN v16[5]=0x7c55. This isolates
prefix suppression failure; it does not depend on the original tail sNaN.
Target PC=0x80000996, opcode=0x60881c57 (`vmfeq.vv v24,v8,v16,v0.t`);
neighboring instructions clear flags at 0x8000098e, write vstart at 0x80000992,
read vstart at 0x8000099a and read flags at 0x8000099e. Console, commit trace,
decoded ELF and sealed-image manifest identities are retained.

## Real consumer port unit

`consumer_tb.sv` instantiates actual MASKU and actual masku_operands at four
lanes, VLEN1024. `run_consumer.py` snapshots and hashes exact sources.
The producer interface is modeled: result bit0 and NV bit2 are external port
stimuli, not forced internal nodes and not captured new-producer outputs.
The first two cases use measured lane1/FP16-slot2 NV location (element5);
other bits are independently generated contract tests.

Checks cover exact registered per-slice flag-valid/NV, missing operand stalls,
held VRF grants, e16/e32/e64 prefix/tail/unmasked behavior, multiple result
slices, 256-bit packed-mask boundary, two queued output words, and integer
VMSEQ with NV poison. The unselected functional-unit stream is valid and
poisoned. Comparison data writes and old-vd merge are checked independently
of internal MASKU counters. All stimuli use ports.

`consumer_after01` is a compile-only failure in parent-owned RTL declaration
ordering: the new block precedes vinsn_issue_valid/result_queue_active_mask_seq.
No expectation changed and no RTL was edited by the test owner.
Subsequent results must be separate, not overwrite this attempt.

`consumer_after02` compiles after the parent's declaration-only move. First
three tests PASS. Multiword active accepts all 18 slices; per-edge flag-valid
and NV checks pass, including NV at cycle45/base256 and zero at cycle46/base272.
It then fails the independent result-write footprint check.

`consumer_after03` changes only testbench WRITE logging. It reproduces the
same failure with actual granted ports: cycle91 all lanes addr98/BEff;
cycle92 all lanes addr97/BEff. Correct addresses for vd24, four lanes,
VLEN1024 are 96 then97. Thus the missing first word is not inferred only from
the scoreboard. Output grants were zero until cycle90, allowing two entries
to queue. The default MASKU queue assignment writes metadata at the write
pointer even when full; pointer wrap plus iteration2 overwrites the first
entry address. That assignment also exists in final01's frozen source.
This is separate from the added per-element NV contract. No oracle was
relaxed, no production RTL edited, and the failing tests remain FAIL.

`consumer_queue_probe01` reuses the identical consumer03 binary, no build:
quiet payload plus stalled grants still writes98/97. Removing stalls restores
addresses96/97, but then exposes a separate bench output-decoding error:
MASKU shuffles packed mask output with `vtype.vsew` (masku.sv result/background
shuffle loops), whereas the initial scoreboard decoded it as EW8. Operand
predicate/old-vd EW8 layouts remain correct. `consumer_after04` changes only
that output coordinate conversion and adds read-only queue q/d logs; golden
element values, NV rules, write-footprint requirements, and RTL are unchanged.
The unchanged RTL SHA256 pair for consumer03/04 is masku
`26da8c32bfc0e4d35f51e970dc3cd2086e375eff59c46e649d84a2f79cf0aaf9`,
masku_operands
`c907488c75b5051a917e61c5ac08bca15859f2f0506fd61dae07dd576569456f`.

`consumer_after04` focused results: unstalled multiword PASS (18 slices,
18 flag pulses, one NV). Stalled multiword FAIL. At cycle47 cnt=2/full=1,
wp=rp=0, iteration=2, accept=0, req=f, grant=0, final=0, entry0 addr q96/d98.
At cycle48 q=98 with no handshake. First actual grant at cycle91 writes98.
This establishes queued descriptor overwrite independently of completion.
The before04 hardware and testbench snapshots are now read-only, with SHA
identities in pins.json; they are retained while parent edits live RTL.

The unstalled probe's original element11 data failure was in ACTIVE body
(VL273, predicate=1), not tail. Correcting output-layout decoding fixes it;
no tail policy or element golden was relaxed. Parent then gated the default
descriptor loop with !result_queue_full. `consumer_after05` tests that new
snapshot with the SAME corrected consumer_tb used by before04.

After-guard evidence in `consumer_after05/multiword_active.log`: cycle47 is
cnt2/full1/wp0/rp0/iteration2 with accept0/grant0 and entry0 q96/d96. Actual
grants write96 then97. That test PASS includes all18 registered flag pulses,
one NV, complete data and footprint checks. The full suite is recorded in
consumer_after05/status.json; no baseline record is overwritten.

`consumer_after06/integer_fourword_staggered.log` PASS adds legal e8/m8 VL769
integer VMSEQ with NV poison and four output words. Twenty-five result slices,
zero flag pulses, input_stalls218, output_stalls276. Checked coverage reports
full=1/pop=1/refill=1/partial_waits24. Grants arrive on different lane cycles;
each lane writes addresses96,97,98,99 once. Every blocked lane retains
request/address/data/BE until its grant. Queue refills to full at cycle107,
after the first pop, while pending lanes retain descriptors. This unit uses
the same parent MASKU hash `1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d`.

Tail policy note: initial scoreboard failure e11 was active body, not tail.
These consumer tests request old-vd and check MASKU's existing exact inactive
bit merge implementation (active-window AND and old-vd background), which is
stronger than ISA-permitted mask tail alternatives. The bare-metal independent
software oracle continues accepting the original legal tail alternatives.
No ISA tail freedom was removed from software checks or used to hide the
queue-address bug; production output layout was never changed by this owner.

### Input/output layout contract

- Result source operands: `eew_vs2`; each element's physical low byte carries
  comparison bit0 and NV bit2. `masku_operands.sv:228-241` compresses both with
  the same source-byte mapping and vrf pointer; NV defaults zero elsewhere.
- Predicate source: `eew_vmask`; old destination source: `eew_vd_op`.
  The bench sets both to EW8. Their independent deshuffles are in
  `masku_operands.sv:103-113`.
- Stored destination: `vtype.vsew`, including for packed mask results.
  `masku.sv:1017-1020` shuffles the result and `:1035-1043` shuffles the
  background using that encoding. Therefore the external write scoreboard
  uses `seq_byte(lane,b,sew)`, NOT `seq_byte(lane,b,0)`.
- Sequential element goldens remain independent of those physical layouts.
  Correcting the output transport decoder did not change result/NV goldens,
  inactive-window rules, or valid/ready acceptance rules.

## Bounded old-image width sample

The additive `prepared_smoke`/`soc_smoke` programs directly call nine selected
matrix points per width, with the same run()/oracle; no scalar filter loop.
Spike `reference_smoke01`: 27/27 PASS. `smoke_before01` uses final01, not the
new consumer/producer candidate. e64 completes nine points: five pass, four
flags-only failures (EQ sNaN all-off/tail/prefix; LE masked-off qNaN with sticky
NX expects1, gets17). All detail rows have data/setup/vstart errors zero.
The checked runner cancels siblings upon failure. e32 nevertheless printed
its complete nine-point self-check summary before cancellation, with the same
5/4 split; runner status remains CANCELLED, not PASS. e16 has only three
observed flags-only failures; remaining points are UNPROVEN. Raw outcomes and
classification are preserved in `smoke_before01/classified.json`.

Frozen software for parent final03: `soc/programs.json` (original five) and
`soc_matrix/programs.json` (four additive programs). The latter SHA256 is
`fcac4e3f647a7c133c0b92172231cbd54f7b8839b75ba15826fc34c64c603252`;
prepared provenance SHA256 is
`52f0d0e8a943fa3535c41132d087f1cc65b3305819e6e83198df8cf5e90a19c2`.
Both prepared trees and all referenced ELF identities have been rechecked;
they will not be modified for the parent's sealed replay.

## Replay boundary

`replay_after.py --image <sealed-image> --out <fresh-comparison-directory>
--include-matrix` invokes the pinned checked integration runner, one program
at a time, 120-second simulation bound, and stops on failure. It replays the
five unchanged historical ports, pure-prefix derivative, and optionally all
three new width matrices. Final03 was not available at preparation time;
after-image results are not yet claimed.

This is NOT full-original-source comparison coverage. Archived comparison
assembly is available, but the audited reduced C/generator/oracle is marked
`current_reconstruction`; original full C/generator provenance was not located.
Do not label this script a full original board-program replay. Reduction
activity-epoch findings and tests belong to a separate family and owner.
