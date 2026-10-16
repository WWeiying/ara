# Result queue review, 2026-09-28

## Scope and evidence standard

One functional RTL/mapped-netlist discrepancy is confirmed in VALU. Similar
source constructs in other units are review targets, not proven bugs. Passing
RTL simulation does not clear a synthesis-equivalence risk. No additional
functional RTL is changed by this review, and the running Windows build's
sealed inputs remain untouched.

The main-tree VMFPU, VLDU, SLDU and MASKU source hashes match the corresponding
files in `D:/fpga_runs/ara_valu_fix_20260928/package`. This establishes source
identity for those files, not equivalence of the complete simulation and FPGA.

## Static findings

| Unit | Payload production | Consumption | Required discriminator |
| --- | --- | --- | --- |
| VALU | Temporary payload, constant-index entry assignments after fix | Constant-index whole-entry clear | Held payload stability; simultaneous enqueue/dequeue; tail byte enables; completion once per ID |
| VMFPU | Dynamic field writes, including partial narrowing data and byte enables (`vmfpu.sv:1963`) | Whole-entry dynamic clear (`:2570`) | Mapped VMUL/VFADD writes must stay stable without grants while another slot fills |
| VLDU | Dynamic queue/lane/byte updates (`vldu.sv:416`) | Per-lane whole-entry clear (`:537`) | Mapped AXI load with staggered lane grants; only accepted lane may clear; final grant must precede completion |
| SLDU | Dynamic per-byte writes (`sldu.sv:751`), additional reduction paths | Per-lane whole-entry clear (`:1088`) | Mapped slides across lane/word boundaries with independent lane backpressure |
| MASKU | Whole-entry construction (`masku.sv:1426`) plus field updates (`:1479`) | Per-lane and whole-row clear (`:1640`, `:1661`) | Mapped mask/compress with independent lane grants and partial final packet |

VALU's new payload merge occurs before read-side clear and completion checks.
Thus normal clear priority and the completion check's view of next-state IDs
are retained. The final reduction accumulator clear remains last. Non-debug
logic does not read a partially constructed `result_queue_d` before the merge.

The other units' valid flags, lane grants, queue counters and reduction paths
differ. Blindly applying the VALU rewrite could introduce errors, especially
where the current-cycle queue value is used for reduction decisions.

## Validation gaps identified in the original diagnostic

The ten-case VALU probe used full-length e8/m8 scalar moves with all-one data.
It did not cover short tails or transitions from nonzero to zero payloads.
Its completion counter also lacked explicit duplicate-ID rejection. This was
a test-coverage gap, not evidence that earlier passing runs were incorrect.

The strengthened probe tracks accepted/completed IDs, rejects extra writes
and duplicate/early completion, checks active byte data and tail enables, and
retains pending-request stability checks. `check_valu_matrix.py` runs 48 cases:
VL 1/7/8/9/255/256, request gaps 0/7, backpressure off/on, and all-one versus
per-instruction A5/00/5A/FF data. The original ten-case sweep is also retained.

Still not covered by this mapped probe: masked operations, nonzero vstart,
arithmetic operands, saturation, narrowing, reductions, reset mid-flight,
all four independently synthesized lanes, and full-design integration.
Representative SoC RTL tests cover some of these, but are not a substitute
for mapped tests.

## Acceptance boundary

Completed in this review:

* Strengthened original ten-case sweep: fixed RTL 10/10, fixed netlist 10/10.
* Extended matrix: fixed RTL 48/48 and fixed synthesized netlist 48/48.
  Evidence: `/tmp/ara_discard_bare_20260928/review_{rtl,netlist}_matrix_01`.
* Negative control: original standalone synthesized netlist still fails the
  first case with zero data/byte enables at 265 ns. Evidence:
  `/tmp/ara_discard_bare_20260928/review_baseline_01/gap0_pressure0.log`.
* Additional SoC RTL tests: 8/8 passed (`vmul`, `vfadd`, `vfredusum`,
  `vslide_mask_edges`, `vle_vse_hazards`, `vmand`, `vcompress_edges`, `vmseq`).
  Evidence: `verification/out/valu_queue_review_20260928_01/summary.csv`.

No second hardware defect was reproduced in these tests. The other four
units have not received equivalent mapped-netlist tests, so they remain open
review items rather than either confirmed failures or cleared risks.

Before declaring the Linux issue fixed, require full-design netlist review,
routed timing/DRC/CDC review, original eight-ecall board reproducer, V-enabled
Linux boot, shell interaction, and checked user vector/context-switch tests.
Do not equate a boot banner or a successful bitstream build with OS validation.
