# Resident PV Cluster Protocol Gate

Experimental synthesizable parent of four **unmodified** `pv_unit` lane
controllers, the `pv_group` barrier, and the `pv_transport` private fanout.
No production bus, FPU array, native LDU, or prior source/document changes.

## Contract

- One command at a time, one common shape, selected subset of four lanes.
  All selected controllers and the group launch atomically, even abort+start.
  The group retains the active mask through final-ack drain and terminal acceptance.
- Each lane independently accepts its seeds in controller slot order, head 0
  then head 1, with slot = head*8 + word. A shape has 1..32 elements,
  1..64 tokens, one or two heads, and ceil(elements/4) words per head.
- Private stream contains one coefficient packet then that many value packets
  per token. Heads share value packets. Token/word counters bound ingress without
  multiplication; trailing offers remain unaccepted, including while seeds wait.
  Fanout retains per-lane pending delivery and is cancelled on private failure.
- Group cancellation reaches every selected controller and drains outstanding
  FPU returns before an error terminal. External abort never reaches controllers
  after authorization, even before the first write acceptance.
- `result_valid_o & result_ready_i` advances a lane. `final_ack_i[l]` is a
  separate pulse per finally completed accepted word. Five-bit per-lane debt
  counters represent 0..16: eight words per head times at most two heads.
  Simultaneous acceptance+ack is legal, including zero prior debt. Accounting
  continues after lane done; group completion is held until every debt is zero.
- Excess ack pulses assert `ack_rejected_o` and do not alter debt; they are
  deliberately non-fatal. Overflow is sticky-fatal; the existing group fatal
  likewise prevents terminal retirement. Terminal flags/error are zero outside
  `done_valid_o`, and stable while valid is backpressured.
- This ack port is **NOT native LDU final completion in production**. It has no
  VID/epoch/word identity and cannot distinguish stale/duplicate acknowledgments
  while another debt is live. The parent production adapter must carry/check
  identity and establish actual final completion, not mere queue acceptance.
  Reset requires the environment to flush outstanding FPU and ack traffic too.
  Upstream older-VID drain integration remains separate, with no fixed latency
  assumption or claim that this wrapper establishes that drain.

## Run

```sh
PYTHONDONTWRITEBYTECODE=1 python3 verification/performance/resident_rvv/pv_cluster/run.py \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_cluster_agent_UNIQUE
```

New output only; existing failures are never overwritten. All source inputs,
testbench/responder, runner and this contract are frozen read-only under signoff
output. Source and image hashes are checked before/after execution. Host VCS
only: compile <=120s, each of four runs <=20s, bounded 12000 cycles per case.
No synthesis, Verilator, URG, SoC, FPGA or performance acceptance.

The test uses the actual controllers and a small tagged delayed return responder.
**XOR operand/result signatures are protocol-only, NOT numerical verification.**
Earlier VMFPU tests provide separate arithmetic evidence; this gate does not
repeat or extend that claim. Independent ledgers check seed/packet delivery,
request tags/masks/operands, pending returns, accepted writes, final acks and flags.
Ten directed cases cover heads, element tails, token lengths 1/2/3/9/64,
asymmetric seed/FPU/stream/write timing, 16-word debt, abort at launch, cancellation
with live returns, malformed packet kind, abort after valid, resets during compute
and final drain, and reuse without reset. Three checker self-tests inject observed
duplicate write slots, incorrect flags, and premature completion; each must fail
at its exact checker. These are checker sensitivity tests, not RTL mutation proof.
