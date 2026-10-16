# Masked slide restart deadlock

## Confirmed defect

The FPGA MASKU and SLDU disagree on the mask stream start/count when a masked
slide has a nonzero architectural vstart spanning a complete aggregate word.
This is a reproduced RTL liveness defect, not a software timeout inference.
No design RTL was edited for this investigation.

For four lanes, each mask beat covers `W = 32 / element_bytes` elements.
MASKU initializes read/commit counts to `vl - floor(vstart/W)*W` for
VFU_SlideUnit (masku.sv, request initialization). For slide-up it additionally
trims stride-aligned words and overwrites mask_pnt with the stride position.
SLDU instead starts at the slide stride (up) or destination zero (down), not
at architectural vstart. It needs a mask beat for each destination aggregate,
including aggregates before vstart. Its SLIDE_RUN gate requires mask_valid.

Once MASKU finishes its shorter stream, SLDU cannot decrement its remaining
issue/commit counts. Valid source operands and available result queue space
do not resolve the wait. No further mask producer exists for this instruction.

## Discriminating simulation

`mask_slide_restart_tb.sv` connects the actual FPGA MASKU and SLDU, supplying
valid source operands, all-one mask operands and a lane writeback sink with
one-cycle delayed final grants. No CPU, Linux, DDR or Ethernet is needed.
Each point runs 100 observation cycles after the request. This is a liveness
test, not a numerical or full-SoC correctness test. LMUL is fixed to m1; the
matching board e32/mf2 trigger has the same VL/vstart mask-beat mismatch.

| Operation | SEW | VL | vstart | Mask beats | Done | Remaining issue/commit bytes |
|---|---:|---:|---:|---:|---:|---:|
| slide1up | 32 | 16 | 0 | 2 | 1 | 0/0 |
| slide1up | 32 | 16 | 8 | 1 | 0 | 32/32 |
| slide1up | 64 | 8 | 0 | 2 | 1 | 0/0 |
| slide1up | 64 | 8 | 4 | 1 | 0 | 32/32 |
| slidedown, offset 0 | 16 | 32 | 0 | 2 | 1 | 0/0 |
| slidedown, offset 0 | 16 | 32 | 16 | 1 | 0 | 32/32 |

All stalled rows also assert: MASKU read count zero, mask queue empty, SLDU
mask_valid zero, every source lane valid, result queue not full. Thus the
missing mask, rather than a source dependency or writeback backpressure, is
the immediate blocking condition in this simulation.

Run from the repo with VCS configured:

```sh
bash hardware/fpga/ara_dsa_vcu118/linux/diagnostics/run_mask_slide_restart.sh /tmp/mask-slide-new
```

The runner requires a new output directory and records source hashes. The
success marker means the expected defect AND passing controls were observed;
it does not mean the RTL has been fixed. A future fix must update the failing
expectations and add architectural data checks, not keep expecting a stall.

## Evidence and provenance

Evidence base: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.

- `mask_slide_rtl_cause02`: current FPGA-source run, six expectations satisfied.
- `mask_slide_archived_cause01`: same six outcomes using archived MASKU/SLDU.
- `mask_slide_archived_sources01`: modules copied from Windows
  `D:\fpga_runs\ara_dual_reset_locality_20261005_01\package\rtl\ara\hardware\src`.
  This package is referenced by the bitstream build's `inputs.json`.
- The archived module hashes match that package's `SHA256SUMS`:
  MASKU `9d41dc028967ed5b639072073b2ab07db87254419c30d0eae6b7a558b79f926f`;
  SLDU `e23f11037461a2648e1b783d01ecba32f2f1569ac3e0f2258248a95b0149d687`.
- Other dependencies use the current FPGA tree and are individually hashed
  in each simulation directory. This is not a full archived-SoC simulation
  or a routed-netlist equivalence proof.
- `mask_slide_rtl_cause01` is a rejected initial testbench run: final grant
  incorrectly coincided with normal grant, so controls failed. Do not cite it
  as completed validation. The corrected runs above delay final grant.

Board corroboration: `rvv_fp_move_stall32mf2_symptoms01/symptoms.json` records
the same `vfslide1up.vf v24,v8,ft0,v0.t` stall for the original, instrumented
and single-trial programs; the latter two record VL16/vstart8. The following
`csrr vstart` cannot finish while vector work remains outstanding. The board
snapshots establish frozen retirement and instruction PCs, not internal mask
queue values. The cycle-level explanation comes from the joint RTL test.
Corresponding e64 VL8/vstart4 and e16 zero-offset slide triggers also exist.

## Repair requirements

Choose a consistent producer/consumer stream origin for slide restart. If
SLDU continues traversing the whole destination prefix, MASKU must provide
matching masks and SLDU must explicitly preserve architectural prestart bytes.
If SLDU skips the prefix instead, source addresses, intra-word slide offset,
mask position, issue counts, result byte accounting and commit counts must all
use the same start. Merely increasing a timeout or changing only read_cnt is
not a correctness fix. For slide-up, avoid subtracting both aligned vstart and
aligned stride independently; their covered intervals can overlap.

Required checks after a proposed repair: vstart on both sides of an aggregate
boundary, scalar slide-up/down, offset zero/nonzero, masked-off elements,
prestart/tail preservation, partial final aggregates and queued instructions.

## Scope limits

This explains the reproduced masked-slide restart liveness mechanism. It does
not close extension, fixed-point, multiply-accumulate, compare, mask-operation
or memory-fault stalls merely because they also freeze retirement. Those need
their own request/dependency/completion-path analysis. The old broad reduction
campaign's automatic recovery monitor was stopped at recovery275; no new
batch reduction releases were queued.
