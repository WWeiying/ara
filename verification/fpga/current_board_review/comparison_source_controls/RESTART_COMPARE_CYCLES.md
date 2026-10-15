# Candidate04 Restart-Compare Cycle Review

Read-only analysis of existing candidate03/candidate04 artifacts. No RTL edits,
new simulation, or FSDB. Membership/pin/marker acceptance remains Tesla's
separate audit. This report examines only `singles__restart_compare`, the one
nonidentical CSV in the reported19+16 batch.

## Measured Difference

| Measurement | Candidate03 | Candidate04 | Delta |
| --- | --- | --- | --- |
| CSV event rows, excluding header | 18,975 | 18,975 | 0 |
| First recorded cycle | 82 | 82 | 0 |
| Final recorded cycle | 30,318 | 30,319 | +1 |
| First-to-last recorded span | 30,236 | 30,237 | +1, +0.003307% |
| Target arch_start / CVX request | 27,632 | 27,632 | 0 |
| Target uop_alloc | 27,633 | 27,633 | 0 |
| Target scalar retire event | 27,634 | 27,634 | 0 |
| Target backend uop_done | 27,644 | 27,645 | +1 |
| Allocation-to-done interval | 11 | 12 | +1, +9.09% |
| Request-to-done interval | 12 | 13 | +1, +8.33% |
| Console simulation finish time | 30,334.5 ns | 30,335.5 ns | +1 ns |

The first differing event is zero-based CSV row17601 (file line17603 including
header): `uop_done`, arch order11, VID0 (the `port` column for this event),
transaction6, opcode `608e4c57`. Its PC field is zero by monitor design; the
corresponding retirement identifies actual PC `0x800005a0`, instruction
`vmseq.vx v24,v8,t3,v0.t`.

Every non-cycle field in every row is identical. The initial17,601 events are
fully identical; all remaining1,374 events have exactly cycle+1, with no later
growth or recovery. The following `csrr a0,vstart` CVX response moves from27645
to27646 and returns zero in both runs. This is a real single-cycle completion
delay propagated through the rest of execution, not changed scalar control
flow, extra instructions, changed observed result data, or wall-clock noise.

Cycle semantics: frozen `hardware/tb/ara_commit_monitor.sv:117,144` resets and
increments a dedicated clock counter; lines165-174 emit `uop_done` on
`backend_done_i[id]`. It is not scalar retirement or a per-lane VRF grant.
`hardware/tb/ara_tb.sv:748` sets ClockPeriod=1ns. The console finish-time delta
independently agrees with one clock. `[hw-cycles]: 0` is not usable for this
program; final trace cycle and explicit trace span above state the measurement
boundary rather than claiming an instrumented main-only cycle count.

## Source-Origin Attribution

Both consoles identify e64, VL8, vstart4. The source assembly loads v8/v16,
predicate v0 and old destination v24, writes vstart, sets scalar t3=-3, then
executes the target. Mode0 supplies an all-one predicate. This is a scalar
integer comparison: AluB/vs2=v8 is requested, not vector AluA.

Comparing the two frozen `hardware/src` trees finds only
`lane/lane_sequencer.sv` changed. Its relevant difference at lines1008-1012
extends source-origin zero from carry to all integer comparisons. FP request
changes in the same diff do not execute in this program.

For four lanes, localStart=4/4=1 and lane VL=8/4=2. EEW64 gives one element per
lane word. Frozen `operand_requester.sv:416-425` keeps request length=2 because
scale_vl=0, while its first address changes from `vaddr(v8)+1` to `vaddr(v8)`.
Thus the old sequence reads lane words1,2 and the repaired sequence reads0,1.
The old full-VL consumer wrongly labels the advanced source stream as starting
at element0. The repaired source stream matches VALU consumption and MASKU
compression. The byte count does **not** grow in this case; do not explain the
extra cycle as an added prefix beat or a new conversion operation.

Static bank implication: `ara_pkg.sv:1010-1018` specifies8 banks and four
64-bit words per register per lane at VLEN1024. The first AluB address changes
33(bank1) ->32(bank0). Old-vd MaskB starts at96(bank0), and predicate MaskM at
0(bank0). `operand_requester.sv:376,1016-1096` selects banks from low address
bits and arbitrates requests per bank. Changed source/old-vd/predicate bank
competition is therefore a concrete explanation compatible with the +1-cycle
backend delay. However, these commit CSVs contain no requester grant waveform:
which exact request lost arbitration is **not measured here**. The attribution
to the source-origin patch is strong (only relevant production change, identical
prefix, first divergence at target completion); the internal arbitration
sequence remains a static inference, not a newly captured cycle proof.

## Reporting Boundary

Recommended summary: **16 functional controls PASS; 15 commit CSVs identical;
restart_compare completes one cycle later.** For the reviewed program, terminal
cycle grows30318->30319 (about0.00330%); its target backend allocation-to-done
interval grows11->12. Do not claim16/16 cycle non-regression or extrapolate this
single workload's cost to other restart comparisons. Full functional acceptance
and nineteen-original membership are outside this narrow cycle review.

## Evidence Paths

Before CSV:
`../fp_moves/candidate03_controls16_01/replay/tests/singles__restart_compare/commit_trace.csv`

After CSV:
`../comparison_alias_original/candidate04_01/singles/replay/tests/restart_compare/commit_trace.csv`

- Before CSV SHA256: `edc9f40019589517b3120b747c2d68500701ff0e5514d3b41bd66791f76f6f6f`.
- After CSV SHA256: `c806a935496dd7d247238c6e092ad0f03ae3d9fa62f946eb4914e7ab59548a25`.
- Both adjacent `console.log` files contain VL8/vstart4 and simulator finish time.
- Frozen source roots:
  `/home/wangwy/fpga_runs/current_board_memory_candidate03/frozen/sources` and
  `/home/wangwy/fpga_runs/current_board_memory_candidate04/frozen/sources`.
- Software setup:
  `../integration/prepared/restart_compare/original/scenario.S` and
  `../integration/prepared/restart_compare/case.c`.
- Batch outcome: `../comparison_alias_original/candidate04_01/complete.json`.
