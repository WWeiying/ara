# RVV-13 Original Comparison-Alias Singles

## Current Measured Status

**Candidate04 terminal:19 original singles +16 controls PASS, independently
audited**, not merely inferred from the driver's completion marker. See
[terminal audit](candidate04_audit02/README.md) and
[machine-readable evidence](candidate04_audit02/finding.json).
All35 staged ELFs, full original oracles, zero exits and exact membership were
checked.1859 candidate04 pins,1144 original19 measurement pins and107 source
pins are unchanged.15 control CSVs are byte-identical to candidate03;
restart_compare has the same18975 rows and all noncycle fields, with1374 rows
each delayed1 cycle from target done27644->27645 through final cycle30318->30319.
The service is inactive with exit0; total recorded run time948.84s.

### Preserved Candidate03 Baseline

Candidate03: **2 PASS, 1 FAIL, 16 CANCELLED**, not19 PASS.
All19 runtime-only source ports passed Spike. Original assembly, RNG, selected
tuple and scalar oracle are retained; Linux entry/output/exit wrappers alone
were replaced. These are archived genuine singles, not full4032-case parents.

- PASS: e16/m1 selected, e8/m1.
- FAIL: e8/m2, seed0, op0 `vmseq.vv v8,v8,v16,v0.t`, VL128,
  vstart64, all-on predicate. First wrong active bit84: expected0, actual1.
- Remaining16 cancelled by stop-first-failure. e8/mf2 had started; the other15
  had not. No acceptance is inferred for cancelled cases.
- The explicit failure-marker veto stops at `RVV_MASK_BIT`, before the failed
  program's final error summary. This is a genuine bit counterexample, not a
  completed failing-oracle error count or timeout.

[Independent audit](audit01/finding.json) verifies exact19 membership,
19 reference logs, archived source copies/wrapper boundaries, staged ELF/image
identities, six negative failure-veto tests and1144 unchanged pins.
[Selected result](measurement01/selected.json) and
[remaining batch](measurement01/remaining.json) are unchanged original records.

## Measured Source Coordinate Failure

One authorized rerun of the **same e8/m2 ELF and candidate03 image** reproduced
the same bit84 error in76.69 seconds. No RTL, oracle or software hint changed.
UCLI captured18000--20500ns and flushed before the oracle failure.

Identity:

- ELF SHA256: `7a49da58f5e84da62acd671bd2f3d064ff2b876c99c0e6d54da4857c77ee625d`.
- Image ledger: `e2c32c314ca85042e49517476d36c93d0d1f8a9c8eae75d86602cef1de476cb6`.
- Target PC `0x80000508`, instruction `0x60880457`, VID0.

| Cycle | Actual pre-edge event |
| --- | --- |
| 19203 | Target backend allocation |
| 19205 | All lanes accept AluA(v16)/AluB(v8), EW8, VL32, local vstart16; MaskB instead has start0/VL1/EW64 |
| 19206--19210 | AluA reads addresses66--69; AluB reads34--37. Source starts at word2, global element64 |
| 19209--19212 | Four VALU source acceptances with issue_cnt32/24/16/8, still output ordinals0/32/64/96 |
| 19211 | Third lane0 beat: A=`b621e7332c87fab3`, B=`f750e7642c87fab3`; byte5 is e7/e7, result byte03 (equality bit0=1) |
| 19213 | MASKU accepts third slice at vrf_pnt64; lane0 byte5 becomes output bit84=1 |
| 19216 | Actual final VRF grants; bit84 is lane2 byte2 bit4=1 |
| 19217 | Target done |

Original fixture: a[84]=0xe4, b[84]=0xac, expected0;
a[148]=b[148]=0xe7, equality1. Measured queue inputs and VALU operands match
the original elements64--191 for all4 lanes/all4 beats. Comparison bits are
correct for those received values; MASKU faithfully compacts them to0--127.
The first stream coordinate discrepancy is source64 versus output0. The only
wrong active output in this measured write is84. Final writes occur after all
source acceptances, excluding an early alias write as this case's cause.

Evidence: [finding](failure_capture01/cycle/finding.json),
[raw pre-edge cycles](failure_capture01/cycle/raw_cycles.json),
[run status](failure_capture01/status.json),
[console](failure_capture01/replay/tests/rvv_small_masks_cmp_alias_restart_e8_m2/console.log).
The original FSDB and VCD are retained. Analysis removes only identical duplicate
VCD declarations, with raw/normalized hashes recorded; values are unchanged.
This measured active-bit failure differs from the archived first prestart-bit3
symptom. It does not establish a common cause for all19 historical records.

## Selected Old-Vd Check

[e16/m1 finding](cycle01/finding.json): backend16486, MaskB commands16488,
VRF grants16489, MASKU done16497. All lanes request start0/VL1/EW64.
Full lane address32 is bank0/row4, not address4 or v9. Captured deshuffled
old-vd equals the original RNG's first32 bytes; stored EEW and eew_vd_op areEW16.
The initial analyzer conflated bank row with full address; the corrected finding
checks metadata32, row4 and grant bitmap1 explicitly. No simulation rerun was
needed for that analysis correction.

## Candidate04 Successor

Parent completed freeze/build; this measurement task did not create the
candidate04 image directory or build it. At the recorded startup on2026-10-11,
service `ara-rvv13-candidate04-01` launched actual simv PID12564 and loaded the
same e8/m2 ELF. This is startup evidence only, not a PASS claim; terminal results
belong in [candidate04_01](candidate04_01/), with no long-run polling.
Image ledger SHA256:
`e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.
Sealed driver SHA256:
`ef0833dfccbb7ddfcbb04c2d9a98fa28fb5f8d2f608f7b5840cf04c6367b4037`.

First e8/m2 completed its unchanged full oracle PASS in73.08s.
[Cycle gate](candidate04_01/first/cycle/gate.json) is
`PASS_ORIGIN0_BIT84_ZERO`: same pre-target cycle trace, all4 lanes request
AluA/B start0 at19205 and read64--67/32--35. At19211 lane0 byte5 is
ac/e4, comparison bit0=0; MASKU bit84=0 at19214 and final VRF write bit84=0
at19217. The extra cycle versus the baseline MASKU/write timing is recorded,
not hidden by a functional-only comparison.

Historical intermediate startup: after that gate, remaining18 entered the existing background service atjobs2;
actual workers PID16253/16274 were confirmed once. The16 controls remain
dependent on remaining18 PASS. No whole19/35 acceptance was claimed from that
partial progress; inspection stopped after worker confirmation. The later
terminal audit above now supplies the35-case acceptance.
[replay_candidate04.py](replay_candidate04.py) accepts `--image`,
`--image-sha256` and a fresh owned `--out`. It reuses integration/run.py's
run_programs and the frozen runner. It never builds or edits RTL.

Order: e8/m2 same ELF/same focused capture, then remaining18 original singles,
then10 original smokes and6 original singles. The first stage must pass its full
oracle and the origin0/bit84-zero cycle gate before successors launch. Jobs1
for the capture, jobs2 thereafter,180s per ELF, stop-first-failure, global cap24,
MemAvailable>=32GiB, reserve NF7 two slots.16 control ELF/oracle/provenance
identities were independently checked without launching simulation.

Recorded launch arguments (already launched; do not repeat into this directory):

```sh
python3 verification/fpga/current_board_review/comparison_alias_original/replay_candidate04.py \
  --image /home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image \
  --image-sha256 e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673 \
  --out /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/comparison_alias_original/candidate04_01
```

The independent service has a4200s outer bound, exceeding35 bounded cases at
jobs1/2 plus capture conversion and identity checks. Do not poll the long run.
