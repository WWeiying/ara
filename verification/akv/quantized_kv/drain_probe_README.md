# Dead Vector-Tail Read In Test Snapshot

The original all-head multioutput inquiry finished its program but its worker
correctly rejected the raw log on assertion failure. Preserve the original FAIL:
`verification/out/akv-quantkv-batch-qk-20261024-01`.

## Cause And Discriminating Evidence

The snapshot helper used `vmv.x.s %0,v12` only to create an execution dependency;
its scalar result was ignored in C. The unchanged production quantizer operates
with VL=32 and LMUL=8. V12 is outside the written active prefix, so its contents
are not initialized by these operations. In the batch ELF the compiler chose
A4 for the ignored scalar result (`0x800005d0`). The next variadic `printf`
does not overwrite A4 as an argument, but its prologue saves all argument
registers. Saving the unknown value triggers all eight byte assertions in
`wt_cache_subsystem.sv:a_invalid_write_data`. This is not proof of a QBS result
or cache correctness defect, and ignoring those assertions would be incorrect.

A short two-ELF VCS experiment keeps the original image, Query data and
production quantizer fixed:

| Probe | Snapshot | Cache invalid-write assertions | Query byte hash |
|---|---|---:|---|
| Original allocation reproduced | Read V12 into A4 | 8 | `da9453d5` |
| Defined scalar behavior | Read V8 into X0 | 0 | `da9453d5` |

Evidence: `verification/out/akv-quantkv-drain-probe-20261024-01/result.json`,
including both ELF, disassembly and raw simulation log hashes. These probes
are a helper-cause discriminator, not whole-batch acceptance or a proof that
the sequence drains every possible unrelated vector instruction.

## Successor And Required Closure

`build_batch_defined_drain.py` preserves the old source and evidence. It derives
a new source by replacing exactly one snapshot function: the dead scalar output
is removed, `vmv.x.s zero,v8` is retained alongside `fence`, and the CSR output
operand indices are adjusted. All original numerical, geometry, host-replay,
guard, protocol and assertion checks remain enabled. No RTL, original GGML
primitive, real input bytes or checker condition is changed.

The complete Attention test's analogous helper is corrected before rebuilding
its successor ELFs. Old builds remain immutable historical artifacts; because
their source snapshot is superseded they are not current executable evidence.
New full Attention workers may start only after the new complete multioutput
QK worker earns terminal PASS, not merely because the short probe passes.
