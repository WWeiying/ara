# M9 Joint Alignment Acceptance

**Accepted for this local LOAD scope:** seven candidate cases complete with exact
data/enables, precise exceptions, one completion each, and global idle. Four normal
controls have zero observed cycle differences from their appropriate M8 sources.
This is not STORE, VM-enabled, SoC, or archived Linux acceptance.

## Identity And Execution

- Only candidate AddrGen comes from current production, SHA256
  `3736b64136ebbf5629dadb0037457279f9bb91307356c468c9677d321c8c51c5`.
- All other RTL/dependencies come byte-for-byte from
  `/home/wangwy/fpga_runs/current_board_memory_candidate08/frozen/sources`.
  Baseline AddrGen is `1cc40e2669e310ae25e23f5c9ee1f7ee493dc1ac990d70d8b8122f47e93742b2`.
- Exact frozen candidate/baseline file sets differ only at `hardware/src/vlsu/addrgen.sv`.
  Original input hashes and both frozen source sets were verified after execution.
- Real sequencer, AddrGen descriptor FIFO, VLDU, inactive MASKU, and stream_register
  writeback buffers. NrLanes4, VLEN1024, AXI128, translation disabled. No force or
  synthetic internal counters. Ready lane/bank and backing-memory models are explicit.
- One compile/run per source version, no retries: candidate compile0/29.285s,
  run0/10.693s, PID2139248; new M8 normal-controls compile0/29.135s,
  run0/10.642s, PID2140189. Worker PID2137982 returned actual0 (chunk `0b75e2`).
- Every case has a fixed250-cycle window after request presentation; 60s host
  startup/batch bound is separate. No fatal, timeout, or extension occurred.

## Exact Cases

All use e64m1, VL2, vm1, vd24; B=0x80010000. Each verifies all128 destination
bytes, including untouched prestart/tail, exact VRF owner/address/enables and
one acknowledgment, response, load_complete, vinsn_done and empty final queues.

| ID | Operation / base / stride / start | Actual outcome |
|---|---|---|
|0|VLSE / B / 8 / 0|AR9,10; R/pop11,12; 16B final grant14; done15; idle16|
|1|VLSE / B / 4 / 0|Only AR B at9, R/pop11; 8B prefix final grant15; exception-marker pop16; done/response17; idle18|
|2|VLSE / B-4 / 4 / 1|Only AR B at9; R/pop11; only element1's8B final grant13; done14; idle15; no exception|
|3|VLSE / B / 4 / 1|No AR/R/descriptor/write; early alignment acknowledgment8; done/response12; idle13|
|4|VLE / B / 8 / 0|One len0,size4 AR9; R/pop11;16B final grant13;done14;idle15|
|5|VLSE / B / 0 / 0|Two AR B at9,10; R/pop11,12;16B final grant14;done15;idle16|
|6|VLSE / B+8 / -8 / 0|AR B+8,B at9,10; R/pop11,12;16B final grant14;done15;idle16|

Case1: the ordered local fault acknowledgment at11 has cause4/tval=B+4/vstart1;
there is exactly one exception descriptor, no duplicate early_illegal_load, and
no AR for B+4. The sequencer exposes the same precise exception only at17, after
the actual prefix write. Cases1 and3 both report vstart1, not a delayed zero.
Case3's same-cycle early acknowledgment8 has cause4/tval=B+4/vstart1 and exactly
one early_illegal_load; no ordered marker is fabricated for it.

The AXI responder returns exactly one OKAY RLAST per accepted len0 AR, with the
addressed 128-bit backing-memory word. Case1 demonstrates actual prefix writeback,
not an exception acknowledgment substituted for completion. Both effective-start
controls preserve element0 and tail; case3 preserves the entire destination.

## Cycle Comparison And Evidence

- Case0's251-row complete `cycles.csv` slice is byte-identical to the original
  M8 measurement. Original ERROR metadata and closed-audit evidence are untouched;
  that old diagnostic was not rerun or relabeled PASS.
- Cases4/5/6 are new, separately identified M8 controls, not claimed as old
  two-case coverage. Their753-row complete `cycles.csv` AND `context.csv` are
  byte-identical between M8 and candidate. No added response/execution cycles.
- Candidate CSV has1757 rows, plus1757 correlated context rows. New baseline
  has753 rows per CSV. Context includes exception cause/tval/vstart at both
  AddrGen acknowledgment and sequencer response, descriptor marker/element,
  issue-valid, commit-count, exception FSM and running-owner state.
- [Result](measurement01/result.json), SHA256
  `e2af226c3b560e06782bd1bd1c482bd5e841970d123488be99a876a42b6eb5e6`.
- [Candidate cycles](measurement01/candidate/cycles.csv), SHA256
  `accb9536879cc1d30dce3a5e0ac261f951416d29604ea062d75144059f5ace8e`.
- [Candidate context](measurement01/candidate/context.csv), SHA256
  `21d9503179da770350d7c6da26159fdd25f1f78861bc92c9339edbd042d93985`.
- [Input pins](measurement01/input_pins.json),
  [candidate child exit](measurement01/candidate/run_exit.json),
  [M8 normal child exit](measurement01/m8_normals/run_exit.json).

No production RTL, frozen image, sealed predecessor or background task was changed.
No full SoC build/run was performed. VM/MMU arbitration, STORE AW/W/B behavior,
other EEWs/strides and trap/retry software remain outside this acceptance.
