# Unmasked Strided Alignment: Bounded Joint Measurement

## Finding

P1 reproduced in frozen M8 real AddrGen/VLDU/sequencer, NrLanes=4,
VLEN=1024, AXI=128: VLSE64 VL2, vstart0, vm1, e64m1, vd24,
base=0x80010000, stride4 issues two len0/size3 reads but consumes only
8+4 bytes. No alignment exception is reported. VLDU remains at
issue_bytes=16, commit_bytes=16, vrf_count=12 without writeback or done.
This is a measured incomplete-instruction path, not successful bad-data retirement.

Sources: frozen M8 `hardware/src/vlsu/addrgen.sv:948` excludes vm1 from
the later per-element alignment check; `:1065` strided requests use len0;
`hardware/src/vlsu/vldu.sv:363` and `:389` calculate available AXI bytes;
`:445` requires a full aggregate word or all remaining instruction bytes
before queuing a VRF result. Twelve bytes satisfy neither condition here.

## Exact Cycle Evidence

Both cases were executed once, separated by reset, in one simulator invocation.
The source transaction is held through the sequencer acknowledgment. AddrGen's
real descriptor FIFO connects directly to VLDU. Each accepted AR receives exactly
one OKAY RLAST beat; no internal force, fabricated extra beat, or counter override.
VRF requests pass through real stream_register buffers into an always-ready bank
model. MASKU is real but inactive for vm1; lane request readiness is modeled.

| Event | stride8 control | stride4 diagnostic |
|---|---|---|
| PE request visible/accepted | cycle7 | cycle7 |
| AR + descriptor pushes | cycles9,10: B,B+8 | cycles9,10: B,B+4 |
| AR len/size | 0/3 twice | 0/3 twice |
| AddrGen ack / sequencer response | cycle10 / no exception | cycle10 / no exception |
| RLAST + descriptor pop | cycles11,12 | cycles11,12 |
| Valid bytes consumed | 8+8 | 8+4 |
| Result request / final grant | cycles13/14 | none |
| load_complete / vinsn_done | cycles14/15 | none |
| Global idle | cycle16 onward | zero through cycle255 |
| Final issue/commit/VRF byte count | 0/0/0 | 16/16/12 |

Control checks all 128 destination bytes: 16 expected data bytes plus untouched
112-byte tail, exact enables, address and owner. Offline reconstruction separately
checks actual result data/enables/grants. Diagnostic has zero VRF writes; from
cycle13 through255 both transaction streams are empty and the three counters are
stable. The CSV uses pre-edge sampling, so cycle12's count8 becomes count12 on
cycle13. These are 250 observation cycles after request presentation, not a host
timeout. AXI remaining responses and modeled writeback pressure are ruled out.

## Preserved Harness Errors

`measurement01` is a compile-only ERROR: the initial probe named `queue_push`
instead of the actual `axi_addrgen_queue_push`. It never ran a simulator.
`successor01` changes only that probe spelling (and its runner's ancestor path).
Compilation returned0 in29.995s. The sole simulator invocation, PID2129151,
returned numeric0 in10.642s; its worker was PID2127939.

The sole executed batch retains ERROR. After both complete observation windows,
the TB wrongly requires `addr_idle` for the intentionally stuck diagnostic and
calls $fatal. AddrGen `idle_o` at1327 includes `!(|vinsn_running_q)`, not merely
an empty descriptor FIFO/idle AXI FSM. Thus this requirement contradicts the
expected unfinished instruction. All six handshakes are reported complete in
the fatal message. Numeric simulator0 does NOT override that fatal, and no
successful original batch or diagnostic marker is claimed.

No rerun was made. `audit_closed.py` validates the already closed CSV, reconstructs
the full control writes and diagnostic counters, requires the exact sole fatal,
and checks pins before/after. It returned actual0 (command execution chunk
`4e8f0f`) and records:
`CLOSED_CYCLE_EVIDENCE_ACCEPTED_P1_REPRODUCED_NOT_ARCH_PASS`.
Original ERROR metadata, logs, and all sources remain unchanged.

## Identity And Artifacts

- RTL root: `/home/wangwy/fpga_runs/current_board_memory_candidate08/frozen/sources`.
- AddrGen SHA256: `1cc40e2669e310ae25e23f5c9ee1f7ee493dc1ac990d70d8b8122f47e93742b2`.
- VLDU SHA256: `92f9ebbeb136cd3ff11ae1a8ea92ce31b3aac077ae0667f79d82e919a3603401`.
- All local RTL/dependencies copied byte-for-byte from that root; request/response
  types extracted from its actual ara.sv. M8 image.json/config also pinned.
- [Closed audit result](closed_audit01/result.json): SHA256
  `5725c6d9a56d488268cac6402d0e82ec8911e6059cafd019f4be0b0858da0349`.
- [Cycle CSV](successor01/measurement01/cycles.csv): 502 rows, SHA256
  `6edb1777a39c6b81af06e62f2e49a7823c4e73726e9abc9496f4c684ddc93f1b`.
- [Original batch ERROR](successor01/measurement01/result.json): SHA256
  `99115cf768583b7c2f0915771033f6c90b945620cf8684e09875245c6e2bd80d`.
- [Run log](successor01/measurement01/run.log),
  [numeric child outcome](successor01/measurement01/process_exit.json),
  [83 checked pins](closed_audit01/pins.json).

## Scope

This proves the two specified local LOAD cases only. Translation is disabled to
isolate the descriptor/packing boundary; no CPU/MMU/lane execution or full SoC
was simulated. It does not measure stores, vstart>0, VM-enabled faults, repair
correctness, or any archived Linux root. The existing source analysis explains
why MMU does not supply the missing EEW alignment check, but that is not an MMU
measurement here. No production RTL or existing background image/task was changed
or polled. A later SoC test remains separate work.

## Deferred Effective-Start Control

The parent proposed this after the sole baseline run had finished, so it was not
added or executed: VL2/vstart1, scalarbase=B-4, stride4, e64, vm1. The only actual
access is aligned B. Correct behavior is one 8-byte access writing only element1,
preserving prestart element0 and tail. The old initial raw-base check predicts
an erroneous load-address-misaligned exception (cause4, tval=B-4). This remains
a static prediction and a focused future repair acceptance case, not measured
evidence. Do not rerun the completed baseline merely to append this control.
