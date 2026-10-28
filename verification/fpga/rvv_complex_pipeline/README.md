# RVV Complex Pipeline Workload

`rvv_complex_pipeline.c` is a deterministic, self-checking end-to-end RVV
program intended for a later board run. It is deliberately one ELF so that
long dependency chains and state changes occur without a reset between phases.

## Coverage

- Eight passes over 1,025 32-bit elements, using runtime `vl` chunking and an
  e32,m4 arithmetic chain: add, multiply, xor, unsigned compare, mask-select,
  subtract, unsigned minimum, store, and reduction.
- Each chunk narrows the computed 32-bit result with `vnsrl.wi`, stores and
  reloads the 16-bit values, then performs an aliased add and checks all lanes.
- A 257-element interleaved structure is loaded with `vlseg2e32`, transformed
  across dependent operations, written with `vsseg2e32`, and checked field by
  field.
- Six e16 floating-point vector comparisons generate packed masks for 257
  finite, positive half-precision values. Scalar checks validate every mask
  bit and confirm `fflags` remains clear.
- Non-power-of-two lengths force tail handling; the scalar oracle checks every
  active output and each vector reduction independently.

The test does not inject faults, alter memory mappings, reset the board, or
modify RTL. It should first be built into the existing `rv64uv-p-rvv_complex_pipeline`
ELF, then run against the same frozen bitstream and a QEMU/reference image. A
board run is intentionally not started in this preparation step.

## Build and run status

Source is registered in `apps/riscv-tests/isa/rv64uv/Makefrag`. Build command
from `apps/riscv-tests/isa`:

```sh
make rv64uv-p-rvv_complex_pipeline
```

The default `make` invocation in this host resolved `clang` to x86_64 and could
not cross-compile. A manual build with the installed Buildroot RISC-V GCC
succeeded, but that sysroot only provides LP64D stubs, so its ELF ABI must not
be assumed to match the board's existing test package. The ELF was written to
`/tmp/rvv_complex_pipeline.elf`; it was not executed. Before a board run,
rebuild using the campaign's established target compiler/ABI and verify it
against the paired QEMU image. Preserve the ELF hash, serial transcript, phase
markers, exit status, board image identity, and matching QEMU result.
