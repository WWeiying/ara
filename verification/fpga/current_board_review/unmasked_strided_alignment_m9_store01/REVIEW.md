# M9 STORE Local Acceptance

Accepted: successor01 four STORE cases, actual simulator0/no fatal/no timeout,
1004 cycle rows; aligned M8 control actual0,251 rows byte-identical. Exact current
AddrGen3736b64136ebbf5629dadb0037457279f9bb91307356c468c9677d321c8c51c5,
all other sources/dependencies frozen M8. Sole RTL difference verified, pre/post
input pins unchanged. No production or frozen/background image modification.

| Case | Observed interface/completion sequence |
|---|---|
|Aligned stride8 VL2|AW9,10; W10,11; B12,13; done/response14; full16B memory oracle|
|Late stride4 VL2|AW B at9 only; fault ack11; WREADY held low until40; real8B W40; delayed B50; ordered marker consumed50; done/response51|
|start1/rawB-4/stride4|One AW B10/W11/B13; source element1's8B, no element0 write; done14|
|start1/rawB/stride4|Initial fault ack8/done9/response9; zero AW/W/B; no memory side effects|

Both faults are exactly once cause6/tval=B+4/vstart1. Late fault has one ordered
descriptor and no early_illegal; initial fault has one early_illegal and no
descriptor. Thirty cycles of genuine good-descriptor W backpressure and39 cycles
of fault-to-done store-pending protection were observed. Complete/done cannot
precede B: combinational store_complete and marker pop occur on B50; registered
vinsn_done is51. No artificial requirement delays an otherwise protected early
CVX response; this implementation actually responds with done in these cases.
Global idle is required only after retirement. Full64-byte modeled memory/guard
contents, exact AW len0/size3, W data/strobes/last, source operand handshakes, B
ownership, FIFO marker and empty terminal buffers are checked.

`measurement01` remains ERROR: its TB evaluated a stale accumulated done count
before counting the same-cycle done/response51; all architectural context was
correct. It also omitted two CSV format separators. `successor01` changes only
that same-cycle acceptance predicate and the two separators, plus the runner's
directory reference. No RTL, stimulus, watchdog, WREADY/B schedule or oracle was
changed. The original partial run is not claimed PASS or overwritten.

Accepted command: `python3 successor01/run.py`, worker PID2152803, actual exit0
(chunk a173fa). Candidate compile0/29.340s, simulator0/10.642s; M8 normal
compile0/28.938s, simulator0/10.644s.250 cycles per case,60s independent host bound.

- [Result](successor01/measurement01/result.json)
- [Candidate CSV](successor01/measurement01/candidate/cycles.csv), SHA256
  `65ca33d45ecd6e30118c0f0830278125221d49b07d82c3e7dd35eeccfb6c15fc`
- [M8 normal CSV](successor01/measurement01/m8_normal/cycles.csv), SHA256
  `0c7ee51ea7eef4d91d1e33fcf9b8d1661c08681e728122c21739f1693a4591f2`
- [Input pins](successor01/measurement01/input_pins.json)

Scope: actual AddrGen FIFO/VSTU/sequencer/MASKU, NrLanes4/AXI128, EEW64,
translation disabled; lane operand source and AXI sink are explicit port models.
No counter force or invented W beat. Does not prove CPU/MMU, real lane-queue
cleanup, translated behavior or whole-SoC trap/restart; those remain separate.
