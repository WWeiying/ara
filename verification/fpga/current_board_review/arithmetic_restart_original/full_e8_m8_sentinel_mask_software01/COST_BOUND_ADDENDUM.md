# Linked Cost Bound Clarification

This supplements, without changing, SOFTWARE_READY.json (SHA d2d24d346f016b474b351ae26d96cd26a10afb72e95d04d2805b5c49cc736327) and LINKED_COST.json (SHA f1f7cd9b30666f772a229e7df5f02d9b75506b7fc6a8beabc84ca791a52a1200).

The complete conditional success CFG upper is2586331 SoC /2584640 Spike, not a measured firmware count. The audit child exited0 in132.53022720012814s. Both compilations were once with unchanged optimization flags.

## Constant and Memory Accounting

Actual linked comparator LUI is visited52335 times, followed each time by ADDI/SLLI/ADD:209340 materialization instructions, not one materialization per call. All branch/join/constant setup is included in1686072 comparator instructions,160773 below the independently audited old451*4095=1846845. No new per-word sticky comparator was used; original tail SUB/SNEZ remains.

Comparator loads:528255 actual-output +105480 fullword gold +4095 gold-tail LHU +69615 ID LHU =707445. Literal-pool and stack loads in the comparator are both0 in this particular linked lowering. This is not an assumed source property. Whole main contributes60249 scalar loads and584467 stores on its success path; these totals count every actual load/store opcode visit including any literal loads, not merely dictionary reads. IO/helper memory outside main/comparator is in its own instruction terms.

## Startup and Print Allowances

The BSS loop is independently charged4*ceil(BSSbytes/8)+1. Actual startup has only the BSS loop; its remaining instructions are straight-line setup/call/return and park. Both main wrappers are one tail jump to arithmetic_main. Both success replay_exit bodies are finite straight-line paths ending at their park instruction (SoC includes MMIO exit; Spike includes the tohost store). Therefore the additional20000 startup/return instructions is a conservative allowance for those small remaining paths, not an unexplained firmware measurement or an allowance to iterate a new loop. Arithmetic_main, all helper13-instruction bodies and comparator returns are separately counted. Each direct replay_write and number/nested writer call receives the explicit bounded-length whole-function upper in LINKED_COST. Trap/failure paths and indefinite park iteration are not claimed bounded by this success cost.

## Exact Geometry and Scope

a/b are each1024 bytes, with no extra1024-byte e16 BSS shadow. Original helper ABI out+1/CAP1024, physical8/vtype3,128SD+SH2B fresh output and128LD+LHU2B reads are exact. All1026 bytes including front/rear byte guards remain checked. The entire128B predicate is meaningful. Original source histories4095, RNG, helpers, dictionary and fallback/error totals remain unchanged. Fullstream vector correctness is not proven by this static success-path analysis.

The source-review phrase '128 initializer byte writes' means128 complete8B copies plus the separate2B tail, not128 total output bytes.

No new reference, Spike ISA execution, VCS, RTL or budget extension is authorized or performed. Runtime remains uncertain; no <3h completion guarantee is made.
