# Candidate Load Fault Predicate Drain

One joint compile of real sequencer, AddrGen, MASKU and VLDU. The only RTL
override relative to frozen M6 is the current parent-owned VLDU; all other
RTL remains M6-identical. Snapshot every compiled input before compiling,
then recheck source pins after the fixed seven-case run. Do not modify the
baseline measurement or startup diagnostic, production RTL, or M6 image.

Cases execute VL8, VL9, then VL1/4/5/12/16. All are legal e64m4, start0,
stride0, vm0, all-one predicate, first-element cause13. The packed-mask
source, MMU timing and real owner/window wiring remain baseline-identical.
VL8 is the prior completing control. This matrix does NOT test a nonfaulting
AXI-data transfer, wrong-owner injection, prefix VRF writes, early-illegal,
STORE, nonzero start, CPU CSR or the archived Linux source sequence.

Each case requires one actual acceptance, MMU response, ordered descriptor,
load-done, MASKU-done and real sequencer exception response. Require exactly
ceil(VL/4) MASKU output handshakes AND VLDU local pops, with sequential window
offsets and matching real owner on every pop. Done cannot precede that full
drain. Require global idle, no running VID, zero MASKU commit, both spill
slots empty, no pending result, and all final-grant bits set. Observe 100
clock cycles; final invariants hold for cycles80..100. Marker means this
bounded local fault-path matrix PASS, not full architectural acceptance.

Compile bound90s; each host startup/run bound60s; unchanged RTL watchdog2000ns
(200 clocks). Stop on the first failure; no automatic retry. The diagnostic
already established about11s startup overhead, separate from RTL cycles.

Command from repository root:
`python3 -B verification/fpga/current_board_review/masked_translation/multiword_fault_liveness01/successor01/run.py`

Output is exclusive `successor01/measurement01/`. No service or SoC build.
