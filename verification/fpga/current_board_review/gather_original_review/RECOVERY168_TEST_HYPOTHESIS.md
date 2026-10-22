# Recovery168 Returned Numerical Error: Discriminating Test

This concerns the returned numerical-error tuple, not the unknown later
stalled instruction. Original child: `rvv_permute_restart_e8_m4_ops3`.
Recovered tuple: seed0/scalar0/VL256/mask0/vstart128, VI31, cap512 under
VLEN1024. Original complete UART details report prestart elements0..3 as
expected91/actual177. Call66 is a source/configuration mapping, not a measured
stopped-call identity.

## Current Static Explanation And Prediction

`hardware/src/masku/masku.sv` uses the scalar index for VRGATHER.vx/vi when
`use_scalar_op` is set. VI31 therefore requests source element31; it does not
read an element index from the vector index stream. The selected source byte
is177. The current gather write-enable condition uses
`(vinsn_issue.vl - issue_cnt_q) >= vinsn_issue.vstart`, independently of the
word-local output slot. At instruction acceptance, issue_cnt is initialized
to VL, so prefix traversal starts at absolute destination element0.

Prediction for the recovered tuple: full destination bytes0..127 remain91,
bytes128..255 are177, and bytes256..511 remain91. Both guards remain91 and
returned vstart is0. Existing repairs may already satisfy this prediction;
this static argument is not current-DUT acceptance or proof of the original
board root cause.

The M5 EI16 source-origin repair addresses a different path: vector index
scan coordinates. Its accepted EI16 test cannot substitute for this scalar
VI31 numerical tuple. No new RTL change is justified before measured evidence.

## Test Scope

Execute the original first66 calls, including65 predecessor calls, unchanged
13-instruction m4 helper, seed0 RNG, input/index arrays, physical128-byte
predicate initialization and full-capacity scalar oracle. Check33792 result
elements,132 guards and66 returned-vstart values. Keep source identity separate
from runtime TESTCASE identity. Preserve actual simulator numeric exit before
post-check exceptions; simulator exit0 alone does not establish correctness.

## Signals If The Full Oracle Fails

Capture a bounded window around the first failing target, not an entire run.
Match request valid/ready and instruction ID to op, VL, vstart, scalar index,
and destination. Then follow:

- `issue_cnt_q`, `out_valid_cnt_q`: absolute destination versus word-local slot;
- `be_vrgat_seq_d`, shuffled result byte enables, accepted result/VRF writes:
  whether prestart writes are actually suppressed;
- `vrgat_req_idx_q`, `vrgat_idx_oor_q`, source request/grant and returned data:
  whether element31 supplies177 and whether an out-of-range path is selected;
- predicate valid/ready and mask bit, index/request FIFO push/pop, result queue
  full/accept, processing/commit counts: stream and completion alignment.

Prestart writes with nonzero accepted byte enables support a destination-gating
defect. Correct byte enables but wrong scalar oracle values require investigation
of write address, initialization, cache observation and instruction history.
Wrong active payload with correct enables instead points to scalar decoding,
source selection or data alignment. A missing helper return requires accepted
request/completion evidence; the old PC-only stall snapshots cannot supply it.

If the complete66-call oracle passes, accept only that source-derived numerical
prefix on its actual image. Do not close the unknown stalled tuple, original
Linux process history, full2688-call child or all11 historical Gather stalls.
