# Empty segment reservation repair

## Evidence and status

The completed memory-gap campaign contains 473 PASS and 12 TIMEOUT results
(445 inherited PASS, 28 new PASS). All 12 timeouts are NF=5/6/7 indexed
segment tests at EEW=8/16/32/64. Timeout VDBs are excluded from the verified
DVE report in `out/vcs-memory-gap-20260928-01/dve/summary_waived.csv`.
Top-level waived coverage is line 75.69%, condition 77.89%, branch 75.69%,
FSM 45.89%, toggle 59.53%. These numbers describe the pre-repair image only.

## Root cause

Read-only UCLI probes used the original image and original failing ELF:

- `out/memory-gap-fence-probe-20260928-01/probe.log`
- `out/memory-gap-completion-probe-20260928-01/probe.log`
- Probe sources: `probes/memory_gap_fence.tcl` and
  `probes/memory_gap_completion.tcl`.

In the NF5/EEW8 indexed test, the empty segment is acknowledged at probe
time 17702 ns. At 17703 ns, `pending_seg_mem_op_q` becomes one despite no
segment being issued. It remains set after the dispatcher leaves WAIT_IDLE.
The next segment consequently bypasses its normal pre-segment drain.
Older ordinary loads are still completing when the segment sequencer begins
filtering micro-operation completion pulses. Two older completions are lost.
At 22000 and 23000 ns, Ara, VLDU, VSTU and address generation are idle, but
CVA6 still has two pending dispatched loads. The subsequent fence cannot
complete. This is a completion-accounting deadlock, not a runtime-budget issue.

## Repair

Within the existing successful no-op override in `ara_dispatcher.sv`, a memory
instruction with nonzero `nf` clears the pending segment reservation and
combinational segment flag. Only a proposed WAIT_IDLE transition is canceled.
Active whole-register accesses remain excluded by `ignore_zero_vl_check`;
restarted whole-register no-ops need no reservation either. Exceptions
remain excluded by the original exception guard. The repair also covers empty
active intervals with `vstart >= vl`, not just VL=0.

An active nonempty segment is not canceled: the no-op test uses architectural
CSR bounds, not the sequencer's per-element micro-operation bounds. Normal
segment drain, request and completion paths remain unchanged. No counter,
timeout, memory ordering rule or checker is relaxed.

## Validation gate

The RTL repair is applied; functional and performance validation is pending.
Build a separate coverage-enabled VCS image, run the original failing
NF5/EEW8 indexed ELF first, then the memory matrix and adjacent regressions.
Use up to eight workers and halt new dispatch on a new failure. Collect only
checked PASS VDBs from that image. Do not merge the old 473-case report into
the repaired-image report as though the RTL were identical.
