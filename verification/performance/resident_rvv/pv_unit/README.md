# Resident PV lane prototype

This is an isolated implementation experiment, not enabled production RTL or
an accepted ISA. It borrows the existing FP16 SIMD FMA through ready/valid ports;
there is no multiplier in the controller. The testbench instantiates the frozen
baseline FPNew FP16 slice as that borrowed arithmetic resource. No synthesis.

## Contract for the first component gate

- `akv_resident_pv_lane`: clock/reset, one exclusive command at a time.
- `cmd_valid_i/cmd_ready_o`, `cmd_elements_i[5:0]` (1..32 FP16 elements on
  this lane), `cmd_two_heads_i`, `cmd_tokens_i[6:0]` (1..64), `cmd_rm_i[2:0]`
  (0..4). Invalid configuration terminates with error, without seed/input/FPU
  or architectural result transfers. Completion is held until acknowledged.
- `seed_valid_i/seed_ready_o/seed_data_i[63:0]`: already-rescaled FP16
  accumulator words, all head 0 words then all head 1 words, low elements first.
  Scaling/conversion remains outside this unit and must be included in the
  eventual complete-call comparison and accumulated flags.
- `stream_valid_i/stream_ready_o/stream_is_value_i/stream_data_i[63:0]`:
  coefficient packet (`is_value=0`, head 0 in bits 15:0 and head 1 in 31:16),
  then ceil(elements/4) V words (`is_value=1`), repeated in token order.
  The producer holds kind/data while stalled. Two ingress entries are allowed.
  An unexpected packet kind terminates with error after draining accepted FMA
  operations, without committing any architectural destination.
- `fpu_valid_o/fpu_ready_i`, `fpu_operands_o[2:0][63:0]`: indices 0,1,2 are
  broadcast probability, V word, accumulator; FP16 fused multiply-add, no
  negation; `fpu_tag_o[3:0]` is `{head, word_index[2:0]}`;
  `fpu_mask_o[3:0]` masks inactive tail elements; `fpu_rm_o[2:0]` is captured
  command rounding. Each slot has at most one outstanding arithmetic update.
- `fpu_result_valid_i/fpu_result_ready_o`, `fpu_result_i[63:0]`,
  `fpu_result_tag_i[3:0]`, `fpu_result_flags_i[4:0]`: every accepted input
  returns exactly once with its tag. Return order may vary. Inactive tail
  elements do not update local sums or contribute flags (the FPU masks flags).
- `result_valid_o/result_ready_i`, `result_data_o[63:0]`,
  `result_slot_o[3:0]`, `result_be_o[7:0]`: final commits only after all
  arithmetic has returned, in head/word order. Ready means the final write
  acknowledgment, not only request buffering.
- `done_valid_o/done_ready_i`, `done_error_o`, `done_flags_o[4:0]`, `busy_o`.
  All FMA flags are sticky until completion acknowledgment. The parent must
  combine prior preparation flags and publish them before releasing ownership.
  Flag/error outputs are zero outside completion, preventing inactive-owner
  flags from entering a shared OR path.
- `abort_i`: peer/parent failure before commit authorization cancels seed/input
  acceptance and new FMA issue, drains accepted arithmetic, then completes with
  error and no result writes. Reset still resets the FPU; abort does not flush
  it. Abort after the first acknowledged commit is a parent protocol violation;
  a lane waiting to commit with no acknowledged writes can still abort. A global
  parent must wait until every lane is ready to commit successfully and gate
  **external write valid**, not just each lane's final acknowledgment. On a
  peer error it aborts the other uncommitted lanes instead of starving them.

Reset also resets/flushed the borrowed FPU. This component cannot independently
cancel a live FPU and must not receive results from a previous owner. The parent
must drain native issue/processing/commit/results, reserve all registers and
context ownership, and route private payload/result beats explicitly. Those
SoC ownership and fault contracts remain a separate integration gate.

Storage is 16 x 64-bit local sums (128 B/lane), two 65-bit ingress entries,
32 coefficient bits and control/pending bits. Four lanes require 512 B of sums,
not four copies of the entire coefficient table. No payload memory needs reset.
Central coefficient collection and existing resident-bank transport are not
implemented here and cannot be assumed free or fully pipelined.

The component mask contract is packed low halfwords, not arbitrary architectural
VL. Native Ara EW16 words order dimensions as `16*w + {l,l+8,l+4,l+12}`. Fully
populated D64/D96/D128 words can retain this permutation consistently for seeds,
V and results. Partial architectural words require explicit mask translation;
two local consecutive dimensions would use native mask `0101`, not `0011`.
Do not advertise arbitrary-D SoC support from packed component tail tests.

## Test requirements

Use the ordered Spike SoftFloat reference, not host floating-point or the same
RTL twice. Cover head counts 1/2, local elements 1/2/3/4/8/16/24/31/32, token
counts 1/2/9/64, rounding 0..4, backpressure on ingress/FPU/results, short-slot
dependency recurrences, special IEEE operands, flags, invalid commands, packet
errors, reset with work in flight, and back-to-back ownership. Pin arithmetic
sources from the accepted SoC source manifest rather than live dependencies.
Component cycles are not end-to-end performance or SoC acceptance.
