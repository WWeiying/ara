# Original Negative-Stride Store Single

**Prepared Host/reference PASS, pending independent review. No DUT launch,
RTL change or new image.** Exactly one reference invocation, no retry or
changed bound. After READY generation all inputs and artifacts are sealed.

Source identity:
`rvv_small_fault_strided_negative_stride_e16_m1_u1_s1_b3_m2_f0_g3` under
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_negative_stride_handoff01/singles/`.
The archived independently failed Linux diagnostic is retained unchanged;
the new real-Sv39 ELF is a source-derived port, not a byte-identical Linux ELF.

See [REFERENCE_REPORT.md](REFERENCE_REPORT.md) for measured events, provenance
and limits, [STATIC_BOUND.md](STATIC_BOUND.md) for pre-execution admission,
and `software01/source_proof.json` for the actual original helper-byte match.
`READY.json` binds source/runtime/compiler/decoder, software, Host, full raw,
numeric process outcomes and final reference checks.

## Actual Preparation

Commands already executed once in this owned directory:

```text
python3 prepare.py build
python3 host_tests.py
python3 prepare.py run
```

These are an execution record, not instructions to repeat a sealed run.
`prepare.py run` requires a fresh reference01 and the exact pinned bound;
it cannot automatically retry. The supervising wrapper waited for its actual
exit0 and saved `reference01/wrapper_wait.json` independently of the child
Spike's `execution.json`. No inference from missing processes is used.

Host independently checked17152 C/Python oracle rows and41 negative controls.
The once-only golden exited0 in12.753125s with858371 firmware instructions,
103533239 raw bytes, no timeout. Whole observer/wrapper wait exited0 in35.752826s.
All17275 scalar comparisons,64 original results/two guards, four8KiB phases,
2048-word lower-page refill, original helper order and actual MRET context pass.

## Store-Specific Contract

This is not the load checker with a renamed case. The target is09c55c27;
source v24 remains input across the fault. The completed store is127 atP+6,
then its original poison is36. Retry writes166 atP-18 with vstart5 and the
same target PC/original a0=P+22/t3=-8. Inactive elements never appear in either
target's actual reference memory-access list. The unused load helper's entire
PC range is rejected. Full memory, input, offsets, mask, guards and CSR checks
remain mandatory.

A scalar prefix observation precedes snapshot fences/page repair. This checks
architectural store visibility, not a simulated AXI B response: **Spike has
no AXI bus**. A future M6 execution must retain this observable ordering and
its own bus/completion contract; this reference cannot prove arbitrary delayed-B
behavior. No original Linux signal-frame, full96-parent or hardware acceptance
is claimed. Independent source/reference review and separate DUT admission
are still required.
