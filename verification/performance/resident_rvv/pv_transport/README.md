# Private resident payload transport gate

This synthesizable prototype delivers each accepted context word exactly once to
each selected lane. It is not attached to the production LDU or advertised as an
instruction. It changes neither an AXI width nor the arithmetic resources.

Two entries decouple SRAM replay from per-lane private FIFO readiness. Each entry
contains four 64-bit payloads, one packet-kind bit and four pending bits. The data
storage is 512 bits (64 bytes), without data reset. After a lane accepts, its valid
is removed until the next entry. The entry retires only after every selected lane
accepts. No combinational downstream-ready path reaches source ready; two entries
allow sustained one-packet-per-cycle delivery with all consumers ready.

`cancel_i` suppresses both input and output handshakes in that cycle and discards
undelivered private entries. It does not cancel FPU work already accepted by a
lane. The parent must separately abort/drain controllers, and must never assert
cancel once architectural commit has been authorized. Empty active masks are an
illegal producer contract, checked by assertion rather than silently accepted.

## Evidence

Run from the repository root with host VCS:

```sh
python3 verification/performance/resident_rvv/pv_transport/run.py \
  /absolute/new/output/directory
```

Accepted run: `ara_dsa_signoff_integration/verification/out/resident_payload_20261108_03`.
The scoreboard checks packet identity, lane identity, kind, order, stalled-data
stability and conservation independently for every lane. Sources hold their offer
while backpressured. Tests enumerate nonempty masks and readiness patterns, then
cancel partially delivered packets and reuse the storage.

| Counter | Result |
| --- | ---: |
| Accepted input packets | 742 |
| Required per-lane deliveries | 1780 |
| Completed deliveries | 1732 |
| Cancelled deliveries | 48 |
| Partial-lane acceptance cycles | 253 |
| Source backpressure cycles | 323 |
| Concurrent input/output cycles | 444 |

The initial 100 continuously offered packets are accepted in 100 cycles with all
lanes ready. This is a transport-only property, not measured Attention speedup.
The run stores frozen inputs, hashes, compile command, raw logs and final receipt.
Run 01 failed due to a missing default simulation timescale; the runner now sets
it explicitly. Run 02 passed the earlier freely offered-source test; run 03 adds
the stricter held-offer source protocol. Original reports are preserved.

## Parent integration and reuse

`akv_engine.sv` already has `replay_accepted_q` and `replay_final_seen_q`. Do not
stack this new pending mask on top of those as a second architectural load. For
resident mode, source replay acceptance is the private queue handshake; native
LDU grants and native final grants must remain untouched. The current native
engine advances only after both replay masks complete. Private execution must
instead release each SRAM word after its private consumers have accepted it,
with final architectural PV writes handled separately by the commit coordinator.

Whether this two-entry buffer is needed in the final topology depends on the
registered context SRAM output and lane-controller FIFO timing. Existing storage
should be reused where it supplies the same hold/credit guarantee. This gate does
not justify adding duplicate buffering, nor prove a modified context engine.
Coefficient unshuffle, source import, native issue drain, all-lane commit and
SoC exception/response integration remain separate obligations.
