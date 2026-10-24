# Legacy AKV Write Repacker

Experimental prerequisite for unified AKV storage; not connected to the
production source graph. This module is not itself a shared SRAM implementation
and does not establish area savings or complete-operator performance.

## Producer And Consumer Contract

The input is a **payload handshake**, not a valid that can remain asserted while
backpressured. Each fragment contains 2..16 bytes, an even count, compacted into
the low bytes with a contiguous low-bit strobe. Invalid bytes may be arbitrary.
Logical offsets are contiguous within a row; tag and row length stay constant
until completion. A row begins at zero and has 128, 192 or 256 bytes. The 192B
case is an adapter capability, not permission to enable legacy D96 commands.

The output is one aligned 16-byte word with an implicit all-ones byte enable;
the destination must accept each valid word without backpressure. Integrating
with SRAM requires maintaining existing exclusion against conflicting replay
reads. The caller derives stream/token from the opaque tag and must preserve
the complete mapping. No tag bits are repurposed inside this adapter.

## Datapath

Stage0 captures payload and identity. The next stage appends the compact bytes
after a pending suffix of at most 14B, masks invalid bytes, and emits the low
16B when available. There are at most 30B in the join, so one output per cycle
is sufficient. Any remainder stays private until the next fragment. Physical
beat, burst and page boundaries do not reset this suffix.

Output tag, offset and last flag are registered independently of younger
fragments. Nine-bit logical byte positions can represent the terminal value
256. The final fragment always completes a 16-byte word because each accepted
row length is divisible by 16. The final fragment is captured at edge E0,
registered output appears after E1, and SRAM consumes it at E2. Intermediate
nonaligned write timing differs from the old two-bank writer; only the final
write latency is checked here, not full engine latency equivalence.

## Fault And Context Lifetime

`abort_i` masks an unconsumed output on that same SRAM edge and clears stage0,
pending bytes and active-row tracking. Writes already consumed at earlier edges
cannot be undone. The containing engine must invalidate failed context according
to its existing rules and ensure no next command observes partial data.
Abort does not erase SRAM and must not discard resident Q during a failed KV
REFILL. `busy_o` deliberately includes a partially assembled row until either
completion or abort; waiting for busy to clear before issuing abort deadlocks.

## Bounded VCS Gate

```sh
python3 -B verification/akv/storage_adapter/run_unit.py \
  --output verification/out/akv-legacy-repacker-unit-NEW
```

The runner requires a fresh directory, pins inputs and tool identity, bounds
compile to 300s and simulation to 60s, and rejects VCS Fatal/Error output even
if the simulator exits zero. No SoC build, synthesis or alternative simulator
is invoked.

The fixture checks byte/tag/offset/last against an independent deterministic
payload oracle. It covers all eight even physical beat alignments for all
three row lengths, fragment gaps, each possible nonzero pending occupancy,
abort with a registered output plus younger fragment, recovery under a new
tag, and two different rows with no inter-row idle cycle. All completed rows
require exactly two edges from final-fragment capture to output consumption.
The total is 34 complete rows, eight aborts, 424 writes and 6784 checked bytes.
The alignment sweep covers fragments produced by a 4KiB page boundary because
4KiB is a multiple of 16B, but does not simulate MMU/page-fault transactions.

Run01 completed the original byte checks but its Python result checker used
an incorrect workload total; its FAIL record is retained. Run02 used the
correct total for 32 rows. Run03 adds the reviewed no-idle and latency gates.
Only a receipt whose source pins match current files is current evidence.
