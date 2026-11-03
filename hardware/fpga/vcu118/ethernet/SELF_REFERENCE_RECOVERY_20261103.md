# Current-netlist routing recovery

## Evidence and limits

The current RTL delivery remains `ed39f750589ea5c04d38b35c186316b97ced613b`.
This recovery changes implementation control only, not RTL, SDK, clock periods,
CDC exceptions, board state, or flash. It is not hardware acceptance.

The preserved routed input is:

`D:/fpga_runs/ara_qbs_akv_selective_20261102_07/impl/ara_dsa_vcu118_routed.dcp`

Its setup WNS/TNS are -0.056/-5.348 ns with 205 failing endpoints, all in
`mmcm_clkout0_1`. Hold WHS is +0.004 ns. The endpoint inventory has 127 FIFO,
66 Ethernet fabric, 11 Ethernet shared-DDR, and one MIG-calibration endpoint;
162 are CE pins and 43 are D pins. A CE-only repair cannot cover this failure.

Two concrete implementation mechanisms have been established:

1. `reuse_before.rpt` reports 29.83% cell reuse, 27.41% net reuse, and Low
   reuse mode. At `place_design`, `impl_existing.log` emits
   `Vivado_Tcl 4-251`: default place/route is used and only placement from the
   incremental reference is retained. At the end, `4-1062` reports incremental
   flow disabled. Therefore, the selected DDR roots did NOT preserve the old
   timing-closed routing throughout the run. Neither changing the incremental
   directive alone nor claiming that an old reference was loaded fixes this.
2. The subsequent `ara_complete_routed_repair_20261103_01` AggressiveExplore
   log shows five attempted nets on the worst path and zero accepted setup
   optimizations. WNS/TNS did not improve. Repeating this command unchanged
   does not constitute a repair of the complete failing endpoint set.

The old baseline itself had zero reported worst setup margin. For a measured
same-startpoint/same-endpoint example, FIFO W `gen_slice[6].select_q_reg[6]`
to spill `a_data_q_reg[data][348]/D` changed from +0.022 to -0.037 ns.
Clock skew stayed -0.403 ns and logic depth stayed three LUTs. Data delay
increased from 2.882 to 2.941 ns; one intermediate LUT moved. Route delay
actually decreased by 0.015 ns while cell delay increased by 0.074 ns.
This is not evidence for blaming increased RTL logic depth or a changed clock.
The relative contributions of pin mapping, slew, and load require more than
this timing report; do not label all 205 paths with that one example's cause.

The independent read-only comparison is stored in
`D:/fpga_runs/ara_c1_root_compare_20261103_01`. It compares all 205 endpoints
against the old routed baseline and exports path/cell/net records. Missing
endpoint matches must remain explicit, not be treated as passing paths.

## Corrected continuation

`repair_self_reference.tcl` opens the current routed input and uses that SAME
checkpoint as its incremental reference with `TimingClosure`. It requires a
High-reuse report, the expected directive, and at least 99% matched/reused
cells and nets before invoking `route_design -directive Explore -tns_cleanup`.
It never imports an old functional netlist or reruns synthesis/placement.
This addresses the observed loss of routing reuse and allows the router to
work on the remaining setup paths instead of repeating the ineffective
post-route optimization. It does not guarantee final timing closure.

Validation commands:

```sh
tclsh hardware/fpga/vcu118/tests/test_self_reference.tcl
```

The native `test_self_reference_vivado.tcl` must also pass on Vivado 2020.1
in a fresh output directory before the large design is launched. This test
validates commands and reuse semantics, not full-design timing.

Use a fresh frozen release bundle and the existing `run_release.ps1` supervisor.
Pin the routed input, endpoint inventory, driver/dependencies and native test
evidence. Retain the original failed checkpoints. Check route integrity and
clock/synchronizer inventories, save the result, then run strict timing,
DRC, CDC, and bus-skew gates. Bitgen remains conditional on all required gates.
There is no automatic retry loop and no automatic board programming.
