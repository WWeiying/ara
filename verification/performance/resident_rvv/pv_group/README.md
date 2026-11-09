# Resident PV group barrier prototype

`akv_resident_pv_group.sv` is standalone synthesizable control logic, parameterized
by `NrLanes >= 1` (directed gate uses four). It owns no arithmetic, operand
transport, instruction identity, VRF addressing or architectural retirement.
No production RTL is changed. SoC integration and FPGA acceptance remain pending.

## Interface contract

- `start_valid_i && start_ready_o` latches the active mask. The parent must own
  and atomically launch **all selected lane controllers on this same edge**,
  including an abort-at-start transaction. No selected lane may still belong
  to a previous instruction. Unselected lanes are never launched or cancelled.
  This module does not distribute commands or solve partial command acceptance.
- An empty mask is accepted as one rejected transaction: no lane handshake,
  no authorization, one held error terminal. A high abort while idle without a
  start never reaches a lane. Abort concurrent with nonempty start cancels the
  newly launched active lanes beginning in the following cycle.
- Each selected lane must hold its first successful `result_valid` and payload
  until accepted. For the existing `pv_unit/akv_resident_pv_lane.sv`, reaching
  `Commit` implies successful computation and drained accepted FPU work. Merely
  seeing an earlier FPU return or a transport acknowledgment is insufficient.
- The barrier waits for simultaneous result-valid from every active lane.
  Before authorization, external result-valid and lane result-ready are zero.
  A preauthorization abort or active lane done wins over barrier release and
  broadcasts cancel to **all** selected lanes, including already-completed lanes.
  Unexpected successful done before any result also fails closed as a protocol
  error. Valid-qualified inactive lane errors are ignored.
- Authorization is registered before any external result-valid can appear.
  It remains irrevocable through the terminal handshake, even when every
  external ready is low and no write has yet been accepted. `abort_rejected_o`
  explicitly reports abort while authorized; it never propagates to a lane or
  suppresses a result. Do not connect parent abort directly to PV lanes.
- **`result_ready_i` means irrevocable acceptance into a reserved architectural
  write path, NOT VRF final-grant.** After exposure, that path must preserve
  valid/data and eventually accept every beat. The coordinator passes each
  lane's data, slot and byte enable independently; no cross-lane ready reduction
  or duplicate replay is permitted. Invalid outputs have zero payload/BE.
- Lane done handshakes are consumed independently, once per active lane, in
  barrier, commit and cancel states. The parent must not reuse an early-finished
  lane until group release. Cancellation waits for **every** active lane's done;
  those lane dones must guarantee all accepted arithmetic returns are drained.
  No timeout fabricates a drained completion.
- Successful lane flags are OR-reduced. Error/cancel terminals expose zero
  flags; flags from inactive, errored or already-consumed lanes are ignored.
  Terminal valid/error/flags are held until ready, exactly once per start.
- An active lane `done_error` after authorization is **illegal**, not a normal
  recoverable error after partial architectural writes. A simulation assertion
  terminates the gate; synthesizable `fatal_error_o` latches until reset. In
  hardware remaining lanes may drain but no group terminal or new start is
  allowed after this fault. The parent must escalate it as a fatal protocol
  failure, never fall back/replay this transaction. The existing lane controller
  cannot generate such an error after a successful barrier if abort is wired
  only through this coordinator. Reset is global recovery, not rollback.

## Native parent obligations (not implemented)

The group terminal means lane result transfers and lane drains are complete,
**not** that final VRF write acknowledgments have returned. The parent must
track those acknowledgments independently and gate its architectural terminal,
flags publication, release and retirement on all final write acknowledgments.
It may hold group `done_ready_i` low until that point. Merely tying group terminal
directly to CPU completion is incorrect. Keep the original CPU request identity
and reservation alive until architectural retirement; do not reacquire/reuse
the group early.

Private transport acceptance is distinct from native LDU acknowledgment:
`replay_accepted_q`/`final_seen` integration must not double-count a private
delivery as a native write grant, load completion or VID retirement. No native
engine behavior or `pv_transport` implementation is claimed tested here.

The remaining obligations in `../pv_vmfpu/SOC_INTEGRATION.md` still apply:
registered issue-path and operand-request drain, ownership, source/destination
geometry, legal decode/FP state, final-write accounting, context exclusion,
capability/ABI/runtime fallback and exactly-once architectural retirement.
This prototype supplies only the group commit/cancel portion of that contract.

## Bounded host VCS gate

From the repository root (choose a fresh output name):

```sh
python3 -B -m unittest discover -s verification/performance/resident_rvv/pv_group -p test_run.py
python3 -B verification/performance/resident_rvv/pv_group/run.py \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_group_agent_01
```

The runner uses host `vcs` from PATH, no container, synthesis, Verilator or URG.
Compile is bounded to 120 seconds by default (maximum 180); each of two runs to
20 seconds (maximum 30), with a five-second kill grace. The testbench has a
500-cycle/10-us watchdog. No long-running queue or polling loop is used.

All source files, this README, the runner/parser tests and read-only reference
lane/integration documents are copied and SHA-256 pinned before compilation.
VCS compiles only the copied group RTL and protocol testbench. Sources and the
simulator image are verified before/after execution; existing output directories
are rejected. Commands, raw logs, exit status, source/image inventories and a
hash-bound final `report.json` remain in isolated signoff-integration output.

Ten positive directed cases cover staggered barrier arrivals, registered
authorization, abort after exposure but before any grant, stable stalled
payload, independent grants, multiple beats, subset/inactive noise, independent
and simultaneous done pulses, held duplicate done, flag reduction, slow cancel
drain, abort/error at the authorization edge, empty mask, idle/start abort,
early-success protocol rejection, terminal backpressure and reuse. A separate
negative run requires the specific post-authorization-error assertion after
one architectural beat has been accepted; an arbitrary failure is not a PASS.

Scope is **direct handshake protocol only**, not actual lane-controller
instantiation, arithmetic correctness, real model execution, transport/VRF
integration, final-grant tracking, synthesis/timing, formal liveness or SoC
acceptance. Behavior of the synthesized fatal latch is statically reviewed;
the assertion intentionally stops the negative simulation before recovery.
