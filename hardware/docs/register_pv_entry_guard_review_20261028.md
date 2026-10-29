# Register-PV entry guard and vectorized libc

## Finding

The promoted runtime promised to reject a nonzero actual `vstart` before work.
An explicit CSR boundary test contradicted that promise. The C runtime clears
its report with `memset` before calling `register_runtime_select`. The linked
toolchain implementation of `memset` contains RVV instructions, including
`vsetivli`, which clear `vstart`. The selector therefore observes zero instead
of the entry value and can accept the request.

This is a software defensive-entry issue, not an RTL arithmetic failure.
Ordinary RISC-V C callers are expected to supply zero `vstart`; the test
deliberately violates that ABI precondition to verify the stronger explicit
rejection contract. The valid-entry performance pairs remain evidence for
their measured binaries, not evidence for arbitrary CSR entry states.

## Evidence

`verification/out/register-shared-entry-guards-20261028-02` preserves the failed
test and ELF. Its GNU disassembly shows:

- `quant_register_execute` calls `memset` at 0x14ab6, before calling
  `register_runtime_select` at 0x14b42.
- `memset` executes `vsetivli zero,2,e64,m1,ta,ma` at 0x33176.
- The caller writes FCSR and vstart immediately before the runtime call;
  there is no intervening vector instruction in the test caller.

The earlier `register-shared-entry-guards-20261028-01` failed to compile due to
a nested test-fixture main macro. It is not a hardware or runtime failure and
is not counted as an executed test.

## Candidate correction

`verification/akv/quantized_kv/register_pv/runtime_entry_guard_candidate.c`
wraps the existing implementation. It reads VLEN, FRM and vstart before any
library call. Unsupported inputs return fallback; report clearing uses volatile
byte writes to prevent compiler conversion into vectorized memset. Output and
workspace remain untouched, no quantization or QBS command occurs, and CSR
values are preserved. Valid entries delegate to the unchanged implementation.

The promoted source is sealed by a live Qwen3 model test, so the correction is
currently an independent successor, not an in-place edit of that input.

`verification/out/register-early-entry-guards-20261028-01` passed:

| Actual VLEN | Rejected cases | Checked dimensions |
| ---: | ---: | --- |
| 1024 | 28 | Both K formats; FRM 0..4; vstart 0,1,31, excluding valid RNE/zero |
| 256 | 30 | Both K formats; every FRM/vstart combination rejected |

Each case checks untouched output/workspace, zero callback/command counts,
capability rejection and unchanged FCSR/vstart. Compiler contract is
`-fno-fast-math -ffp-contract=fast`; QEMU is used only for functionality.
Candidate ELF SHA256:
`2ee2efa9a8321054a7bb3efd4f82934c68c32159431baa5f570bc2d661c498b6`.

The normal 288-case matrix also passed separately as
`register-early-entry-runtime-20261028-01`, checking exact outputs, flags,
panel counts and terminal failure without retry. The VLEN=256 no-effects
rejection passed in that campaign too. Its ELF SHA256 is
`5cb28ec52c1d9ff4aeb65b0e018faad5ff85ee495f6d224ebeecb1b2dbb577db`.
The wrapper adds entry checks on the valid path; no claim of zero cycle cost
is made without a new RTL measurement. Promotion must wait until the live
model consumer releases the existing shared source.
