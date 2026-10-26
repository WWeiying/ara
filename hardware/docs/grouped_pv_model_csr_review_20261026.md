# Model-Level CSR Check Review

## Observed Failure

`verification/out/grouped-pv-model-20261026-01` remains FAIL. The first baseline
prefill, before enabling grouped-PV, returned FCSR=9 and VCSR=3 after the test
initialized FCSR=8 and VCSR=5. The test stopped at `decode_csr_preservation`.
This run does not prove model OFF/ON equivalence, nor a grouped-PV failure.

Raw log SHA256:
`68b8fc8d22534a1a9643bdc6ed97124d40b9326314162039d243d07252516ffb`.
Model ELF SHA256:
`5a8cd2850f304acd1757369e02fb5c0ff113eb372f582f9577021effa42e16c8`.

## Source And Binary Evidence

The current llama.cpp `ggml/src/ggml-cpu/arch/riscv/quants.c`, function
`quantize_row_q8_K`, uses `vnclip` intrinsics with explicit RNE fixed-point
rounding at lines 182-183. The actual model ELF contains:

```text
quantize_row_q8_K:
  0x292c3a  csrwi vxrm,1
  ...
  0x292c82  vnclip.wi v8,v8,0
  0x292c8a  vnclip.wi v8,v8,0
  ...
  0x292d5e  ret
```

There is no VXRM restoration before return. VCSR=5 means VXRM=2 and VXSAT=1;
setting VXRM=1 while preserving the sticky saturation bit yields VCSR=3.
The zero-block branch bypasses this instruction. A minimal nonzero/zero-block
diagnostic is being prepared to discriminate this cause without another full
model run. Static evidence explains the observed value but is not yet that
diagnostic's measured result.

## Contract Boundary

The [RISC-V psABI](https://riscv-non-isa.github.io/riscv-elf-psabi-doc/)
does not require preservation of VXRM or VXSAT across calls. Therefore a test
must not assume that the entire ordinary llama.cpp execution preserves VCSR
merely because the narrower QBS/AKV helper contract does.

Do not add save/restore instructions throughout llama.cpp to satisfy this
unsupported model-wide assumption. Do not relax the local QBS/AKV helper
tests: they promise stronger behavior and must continue to prove it.

After the small diagnostic confirms the cause, prepare a successor model
test, retaining the original failure. The successor should record actual CSR
values and require exact paired baseline/candidate values, retained rounding
mode and sticky floating-point flags, complete logits and token equality,
and identical projection work. It must not demand VCSR equal its entry value
across the whole model call. Any paired CSR mismatch remains a failure to
investigate, not a reason to normalize results or ignore flags.
