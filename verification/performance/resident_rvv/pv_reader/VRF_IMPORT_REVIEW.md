# Reuse the existing operand queue before adding coefficient storage

This is a source-path design review, not an implemented instruction ABI. The
accepted reader gate supplies coefficient pairs externally. The earlier
`pv_cluster_fp/SOURCE_IMPORT_REVIEW.md` considers a seeds-first, interleaved
layout with a 32-byte rolling coefficient buffer. The inspected RTL suggests
the queue head can provide that hold function instead. Validate this alternative
before fixing the ABI or adding another data array.

## Actual existing path

- `lane_sequencer.sv` already requests old-destination QBS seeds through `StA`
  when a VQBEXEC operation has its explicit source enabled.
- `operand_queues_stage.sv:i_operand_queue_st_mask_a` has two data entries per
  lane. Its output is `stu_operand_o`, with an independently controlled ready.
- `operand_queue.sv:obuf_control` advances the data and command FIFOs only on
  output acceptance. With `OpQueueConversionNone`, a held output does not change
  its conversion selector or element counter. New operands may fill the spare
  credit but cannot replace the held head. Reset/LSU flush is an exception.
- `vlsu.sv:i_seed_stream_router` demonstrates an exclusive seed owner versus
  the normal store consumer. It is not already an AKV owner: a new user must
  be mutually exclusive with both QBS and stores, including registered offers.

## Candidate bounded import

For the four-lane VLEN1024 prototype, place two fixed-stride FP16 seed vectors
first (256 halfwords), followed by 64 interleaved FP16 coefficient pairs
(128 halfwords). Reserve an aligned eight-register source group, but consume
only six registers: 24 words per lane. Each seed head retains a 128-element
stride, even for D64/D96 and one-head calls. This layout is still provisional;
software preparation cost must be included in complete-call timing.

1. Consume the first 16 words per lane independently. Forward only active seed
   words to that lane's accumulator controller; drain inactive stride/head words
   without presenting them as arithmetic operands. Per-lane counters prevent a
   fast lane from changing another lane's seed position.
2. When all lanes reach the coefficient part, require all four queue heads valid.
   Their 256 aggregate bits contain eight token pairs. Undo the fixed EW16 lane
   permutation with wiring and select one 32-bit pair at a time.
3. Hold all four queue heads while the reader consumes those eight pairs. Pop
   them together only on acceptance of the final pair in that group. A partial
   final group pops after its last active token; unused pairs do not participate
   in floating-point arithmetic and cannot contribute exception flags.
4. For a fixed six-register import, drain the remaining unused coefficient words
   after T tokens. Do not leave them queued for the next native store or QBS
   instruction. A shorter source-VL alternative would require a corresponding
   dispatcher/requester/maintenance audit and is not silently assumed here.
5. On precommit cancellation, stop seed/coefficient publication but drain the
   entire remaining owned source request. Do not release the source owner merely
   because the private reader or FPU is empty. A global reset must flush all
   participating queues together; an LSU-only flush needs explicit handling.

No new 256-byte whole-tile coefficient array is needed under this contract. Even
the proposed 32-byte rolling buffer may be unnecessary because existing queues
hold the words. There are still counters, a pair selector, ownership state and
control wiring. This is a storage organization argument, not a measured area or
timing result.

## Deadlock and correctness obligations

The source requester must be able to read StA while the shared FPU is reserved;
FPU ownership cannot wait for StA to empty before allowing the operation that
consumes StA. Conversely, older native operand requests must drain before the
new source request is admitted. Separate these two phases explicitly.

Holding StA must not block AKV V-row reads or the independent final write path.
Keep source register hazards until their reads finish, reserve destination
hazards until final write acknowledgment, and reject source/destination aliases
in this first implementation. Do not reuse same-EP suppression or bypass normal
scoreboarding to make this path run.

Tests must cover unequal lane availability, stalled coefficient acceptance,
T1/T9/T64, D64/D96/D128, one/two heads, inactive seed words, cancellation in every
import phase, and a following ordinary store/QBS request. Use the real operand
queue in this gate: a mock ready/valid source alone cannot prove no stale words
remain in that queue. Then combine it with the actual context/FPU numerical gate.

The resident endpoint is still tied off in the production wrapper. A successful
transport or arithmetic test does not complete the dispatcher, source-geometry,
CSR, exception, VID or retirement obligations listed in
`pv_vmfpu/SOC_INTEGRATION.md`.
