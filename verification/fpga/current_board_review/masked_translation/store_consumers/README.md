# Real VSTU Public-Port Tests

Independent bounded consumer tests. Only production VSTU and its real common
cells are instantiated. AddrGen descriptors, lane operands, MASKU words and AXI
B responses are public-port models. No force, internal injection, hierarchy
scoreboard, full SoC, Sv39, AW generator, or production edit is involved.

## Source Review and Oracle (Before Execution)

Reviewed VSTU SHA256:
`139b27c0784c867b7a6032665c1634bb4b843ec2d9be5c4a3c6cb6d8fd2919f2`.
Source references are `hardware/src/vlsu/vstu.sv` in the integration tree:

- Lines 90-156: real per-lane fall-through FIFOs and owned mask spill. Inputs
  advance only on public ready/valid. Mask words are held/consumed per vector
  data word, not per element descriptor.
- Lines 370-497: skip advances byte geometry while suppressing WVALID and B
  metadata. Real WLAST records one B obligation. Data uses `old_eew_vs1`, while
  predicate bytes use current `vtype.vsew`; these layouts must not be conflated.
- Lines 530-570: B is attributed to oldest outstanding WLAST metadata, first
  B error wins, and ordinary done requires issue complete and zero pending B.
- Lines 551-620: ordered exception marker blocks normal retirement, waits for
  outstanding B, then consumes the marker, discards buffered operands/owned
  mask, and emits one completion. Do not also assert early-illegal sideband
  for an ordered descriptor after a prefix.
- Lines 626-713: new acceptance resets B error metadata and byte geometry;
  public idle also requires operand/mask buffers empty and running VID released.

The falsifiable failure hypotheses are: skip accidentally produces a W/B
obligation; fault marker/done passes outstanding B; B error VA/element refers to
the marker instead of first failed prefix burst; or cleanup contaminates the
next store. The decisive evidence is timestamped descriptor handshakes,
W data/strb/last, B handshakes, abort/error outputs, done VID and public idle.

Oracle is built from configured architectural byte patterns and active element
sets, not DUT outputs or private counters. Independent bit-reversal lane layout
formula prepares old-EEW data and current-EEW mask inputs; expected AXI data is
linear byte order. Compare every asserted byte, the entire strb, WLAST, exact
W/descriptor/B counts, first-error VA/vstart, and one done/complete per owner.
An AXI response is generated only for a previously accepted real WLAST. Skips
receive no fabricated B. No done or terminal-marker acceptance is allowed
before all expected prefix B handshakes. Unstrobed W data is intentionally not
architecturally constrained.

Six reset-isolated scenarios, each followed by a masked store without reset or
flush (different VID/data, old EEW64, vstart2):

1. All skip, e16 VL20/vstart3, two mask/data windows, old EEW8; WREADY held low.
2. Sparse prefix, e16 VL20, active elements1/4 before fault7; both B delayed
   until at least 12 cycles after the marker is offered, then spaced apart.
3. Same prefix, both B return errors; earliest burst's VA/element must win.
4. Normal sparse masked e16 VL20/vstart3 across two words with W backpressure.
5. Normal unmasked e16 VL32, one 64-byte/two-W-beat burst, one delayed B.
6. First-element exception at active vstart1, zero W/B, owned mask available
   before marker (element0 is inactive and is not a valid fault oracle).

Descriptors use aligned per-element size1/len0 (skip addr0) except the explicit
unmasked size5/len1 burst. Masked descriptors are offered only after the matching
public buffered owner/window is visible, matching the candidate AddrGen's
mask-window prerequisite. Lane inputs stop after the fault's current word;
arbitrary speculative future operands/cancellation are not modeled. Successor
admission occurs after previous done and running-ID release, not concurrently
with exception cleanup. This does not validate a sequencer barrier or younger
queued-store exception behavior (`commit_cnt == 1` remains an upstream contract).

## Run

`python3 verification/fpga/current_board_review/masked_translation/store_consumers/run.py --out verification/fpga/current_board_review/masked_translation/store_consumers/current01`

The runner freezes all compilation inputs and their hashes in a new output
directory. One VCS compilation and one bounded simulation run the six cases;
FAIL logs are retained unchanged. See REPORT.md for measured results when ready.
