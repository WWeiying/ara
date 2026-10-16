# Additional queue validation, 2026-09-28

## Scope and hypothesis

Test the hypothesis that writing another dynamically selected queue entry can
corrupt a blocked entry after Vivado 2020.1 synthesis, as reproduced in VALU.
Discriminators are pending request/data/BE/address/ID stability, independent
lane grants, ordered payload comparison, pointer reuse and exactly-once
completion after all writes. No production RTL is modified by these probes.

These are complete source-module instances with restricted external inputs,
not rewritten queue kernels. Synthesis is standalone out-of-context for
xcvu9p-flga2104-2L-e; simulation uses VCS V-2023.12-SP1. Constants in wrappers
allow optimization of unused paths. This is **not** full-design formal
equivalence, routed simulation, timing validation or hardware acceptance.

## Cases

* VLDU: four lanes, VLEN=1024, 128-bit AXI R input, LMUL=4, unmasked VLE,
  vstart=0, aligned address. Four element widths, four byte lengths per width
  (one element, 32 bytes plus one element, 128 and 512 bytes), grants immediate
  or staggered across lanes: 32 cases. Each active byte is independently
  predicted using lane striping and intra-lane bit reversal, without calling
  the DUT's shuffle function. Byte enables, write addresses and completion
  are checked as well as blocked payload stability.
* SLDU: the same 32-case output matrix, unmasked zero-offset VSLIDEDOWN,
  LMUL=4. Input data is pre-shuffled into four lane words. Operand readiness
  must agree across lanes for this restricted stream. The second word is
  delayed past the first operand spill to exercise a held result. This does
  not cover nonzero offsets, reductions, masks or slide1 scalar insertion.
* ID queue: ID_WIDTH=2, CAPACITY=4, 32-bit data, both FULL_BW=0 and 1,
  CUT_OUP_POP_INP_GNT=0. Three deterministic random seeds, each with 4096
  traffic cycles plus directed initial fill/reuse and final drain. Independent
  per-ID software queues check grants, full/empty, presence, data and ordering.
  The exists port is tied off; other capacities and parameter sets are open.

## Results and evidence

* ID queue RTL and mapped: all three seeds pass in both modes. Per-model
  enqueue and dequeue totals are identical. FULL_BW simultaneous pop/push:
  293 / 300 / 296; full-queue reuse: 263 / 258 / 253 (774 total).
  `/tmp/ara_id_queue_rtl_20260928_01`
  `/tmp/ara_id_queue_mapped_20260928_01`
  Netlist: `/tmp/ara_id_queue_mapped_20260928.v`.
* VLDU final LMUL=4 RTL and mapped: 32/32 each, identical case summaries.
  `/tmp/ara_vldu_queue_rtl_20260928_final`
  `/tmp/ara_vldu_queue_mapped_20260928_final`.
  Netlist: `/tmp/ara_vldu_mapped_20260928_final.v`.
  The preceding LMUL=1 wrapper's RTL and mapped runs also passed 32/32,
  but its 512-byte tests exceeded architectural LMUL=1 VLMAX. Those are
  internal queue stress only, not legal instruction acceptance evidence.
* SLDU RTL and final LMUL=4 mapped: 32/32 each, identical case summaries.
  `/tmp/ara_sldu_queue_rtl_20260928_03`
  `/tmp/ara_sldu_queue_mapped_20260928_01`.
  Netlist: `/tmp/ara_sldu_mapped_20260928.v`.
* Old VALU mapped negative control still reports zero result data/BE at 265 ns.
  `/tmp/ara_queue_audit_valu_negative_20260928.log`.
  VCS returned zero despite the fatal message in this old binary; acceptance
  must require the explicit PASS marker, not process exit alone.

Windows synthesis inputs and logs are isolated under:

* `D:/fpga_runs/ara_id_queue_probe_20260928`
* `D:/fpga_runs/ara_lane_queue_probes_20260928`

Source SHA256 at test preparation:

* VLDU: `2661d1d5bd22ad95825c38be679622d7bae987deae743e12d1fadfe7c3b0af0d`
* SLDU: `e44dad39287adfc77d27b37e602a3f2468cc28a57aa23e75a796a98fed75c3b3`
* ID queue: `103c09c4ef9861f8274ceed40436ed89884eb993067b0bb587b9fcf19bdc69fb`

Ara main-tree VLDU/SLDU hashes equal the corresponding FPGA-package copies.
The original integrated build and board image are not changed by this work.
Source archives and synthesis/test logs are preserved under
`verification/out/queue_mapped_review_20260928`.

All three final RTL/mapped case-summary sets match exactly. No additional
VALU-like corruption was reproduced in this restricted batch. The candidates
listed below remain open, and full-design mapped instances are not certified.

Final netlist SHA256:

* VLDU: `d7dcfd1c0ad5c0765a403ae462701659f290f3dde03b55e1d3e83bd74f86dcd5`
* SLDU: `779893573ff7c3598c4f8315058c48233e7d088be26487c70d1629c509c7b327`
* ID queue: `019427b0a02ee1080dd90dad6413d5fda6ea4b419d30ef093accf448df14cff7`

Harness bring-up issues were corrected before accepting results: the initial
byte oracle omitted Ara's intra-lane bit reversal; exported packed-array ports
needed escaped-name bindings; and the first short SLDU case prefetched its
second operand before any result was pending. Delaying that operand exercises
the intended overlap. None of these harness failures was classified as a new
production RTL defect. LMUL=4 was subsequently set explicitly to keep the
512-byte vector cases within VLMAX.

## Reproduction

From the repository root, with VCS available and fresh output directories:

```sh
D=hardware/fpga/ara_dsa_vcu118/linux/diagnostics
bash "$D/run_vldu_queue.sh" /tmp/new_vldu_rtl
PROBE=sldu bash "$D/run_vldu_queue.sh" /tmp/new_sldu_rtl
bash "$D/run_id_queue_probe.sh" /tmp/new_id_rtl
NETLIST=/absolute/path/vldu.v bash "$D/run_vldu_queue.sh" /tmp/new_vldu_mapped
PROBE=sldu NETLIST=/absolute/path/sldu.v bash "$D/run_vldu_queue.sh" /tmp/new_sldu_mapped
NETLIST=/absolute/path/id_queue.v bash "$D/run_id_queue_probe.sh" /tmp/new_id_mapped
```

Vivado scripts take a source-tree root and a fresh output path:
`synth_vldu_queue.tcl ROOT OUT vldu|sldu`,
`synth_id_queue_probe.tcl ROOT OUT`.

## Still open

VMFPU, both MASKU queues, CVA6 scoreboard/store_buffer/lsu_bypass and QBS burst
metadata have not received new mapped tests in this batch. VLDU exceptions,
masks, vstart, multiple instruction IDs and reset mid-flight are also open.
Passing restricted wrappers does not certify the corresponding instances in
the full FPGA netlist. Do not mass-rewrite similar syntax or declare all
global candidates cleared from these results.
