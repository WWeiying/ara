# Bounded Probe Plan (Not Launched)

Correlate by original target PC/opcode, round, restart attempt, PE ID and accepted
handshakes. PC alone is insufficient because the same instruction retries.
Capture the first failing attempt and its preceding capture/normalization and
partial writes; do not dump every SoC hierarchy scope.

## Three Falsifiable Hypotheses

1. **The first index view is already wrong.** Before any destination write,
   compare all capture words (deshuffled using their actual saved EEW) with
   `((i*13+7)%32)*4096`. Check source normalization, capture completion, selected
   replay words and the first accepted index address. A correct first capture
   and pre-write address stream falsifies this version of the hypothesis.
   Resident ov1 separates initial overlap/layout from exception retry.
2. **Partial writes plus retry damage the remaining index view.** The initial
   stream is correct, but after a fault and actual destination write grants,
   the retry capture/replay or its EEW decoding disagrees for an active index
   `i >= vstart`. Correlate every v4-v7 metadata update and snapshot epoch with
   the first wrong word. Architectural writes to already-consumed low source
   bytes are allowed; do not require the entire overlapped source to remain
   byte-identical. Correct active offsets on every retry falsify this hypothesis.
   Fault ov0 retains translation/retry while removing register overlap.
3. **Indices remain correct but translation/completion is wrong.** Compare
   base+decoded offset, actual MMU request/response, PTE repair and SFENCE,
   AddrGen exception tval/vstart, and VLDU final prefix write grant/done before
   the trap response. Correct source data alone does not prove this path.
   Failure of fault ov0 strengthens a common memory-path hypothesis, but does
   not prove all indexed historical failures share one cause.

## Exact RTL Anchors and Signals

- `hardware/src/ara_dispatcher.sv:5404`: `indexed_load_groups_overlap`,
  `indexed_load_index_overlap`, `reshuffle_req_d`, `eew_q/valid` for v4-v7.
- `ara_dispatcher.sv:5776`: capture selection `source_snapshot_vs/lmul/eew/vl`,
  `state_q`, maintenance request/accept/completion. Retain full VL32 capture.
- `ara_dispatcher.sv:5557`: `source_snapshot_valid_q`, saved EEW,
  `ara_req.source_snapshot_replay_vs2`, `ara_req.old_eew_vs2`, `ara_req.vstart`,
  VL/LMUL/EMUL/index EEW and request valid/ready.
- `ara_dispatcher.sv:5920`: published replay clears dispatcher snapshot-valid.
  This alone is **not** evidence of fault corruption or of lane storage erasure.
  Measure the lifetime of the accepted request and lane buffer, then any later
  recapture from the architecturally partially updated VRF.
- `hardware/src/lane/lane.sv:452`: lane snapshot buffer/write enable/read index,
  source capture valid/ready, VRF operand, replay response valid/data.
- `hardware/src/lane/lane_sequencer.sv:675`: SlideAddrGenA request `vs/eew/vtype`,
  `scale_vl`, aligned `vstart/vl`, replay tag, enqueue/dequeue and operand ready.
  With NrLanes4 and index EEW64 the aggregate word is four indices; retry origin
  is floor(vstart/4), then AddrGen selects vstart%4. Use actual old EEW for
  physical-layout decoding rather than assuming index EEW equals stored EEW.
- `hardware/src/vlsu/addrgen.sv:291`: input operands/valid/ready,
  deshuffled/reduced word; `:324` initial lane/element counters;
  `:430` accepted `idx_vaddr`, `idx_final_vaddr_d/q`, valid/ready;
  `:1172` MMU request; `:1251` exception vstart/tval and descriptor ordering.
- Actual VLDU VRF write request/grant/address/data/BE and PE done[id], plus
  `ara_sequencer` matching load-completion barrier and exception response.
  A predicted write or queue occupancy is not proof of architectural completion.

## Software Correlation

The adapter records `[mepc,mtval,vstart,vl,vtype,fcsr,vcsr]` for every actual fault.
The checker requires unchanged target PC on retry and only 50 index-load
prologues per fault program, not 1650. Record PTE write and `io_repair_sfence`,
then `io_retry_mret`, then the same original load PC. Check each of the 50 full
results and original guards at `io_checkpoint`; retain exact firmware success,
absence of fail/trap markers and successful exit as separate acceptance gates.

The deliberately chosen 32-fault schedule is only an adapter discriminator.
Historical Linux minor-fault batching and exact failing restart remain unknown.
No RTL cause or fix is asserted before current DUT measurements agree with this
request/capture/write/exception/retry chain.
