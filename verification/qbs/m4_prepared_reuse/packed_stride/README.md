# Packed Row Stride Reproducer

This is a bounded software-functional reproducer, not a production repair or a
hardware/performance test. It does not run VCS, Verilator, or URG, change a
library, or override any linked production object. The active
`m4-packed-qkv-vcs-20261027-01` source pins must remain unchanged.

## Hypothesis

In the installed source, `ggml/src/ggml-cpu/repack.cpp` accepts F32 input in
`extra_buffer_type::supports_op` without requiring contiguous rows.
`forward_mul_mat` selects each four-row group's starting address using `nb11`,
but passes only that address and `ne10` to `ggml_quantize_mat_t`. The enabled
`ggml_riscv_q8_K_m4::quantize` helper addresses internal rows as `x + row*k`.
In contrast, the remainder-row loop advances each row by `nb11`.

Prediction: equal contiguous controls, unequal padded rows 1-3, and equal row 0
and M7 remainder rows 4-6. This prediction is not used to relax acceptance:
every output bit must match for a test PASS. An unexpected pattern is retained.

## Matrix And Checks

- Q4_K and Q6_K weights in the actual `CPU_REPACK` backend buffer, K256, N8.
- M4 and M7, each with padding of 0, 1, and 16 floats: 12 scheduled graphs,
  24 real matmuls, 528 paired F32 output values.
- Identical logical activation values from the first 1792 floats of the
  previously verified Qwen2.5-1.5B Q4_K_M prefill `blk_0_attn_q_weight` capture.
  This is a linear prefix reshaped to K256, not the original model shape.
  Weights are deterministic finite values quantized by GGML's reference
  Q4_K/Q6_K quantizers, then repacked through the normal tensor-set API.
- M4 cache OFF, preparation ON (existing four-row helper), wide-M OFF,
  activation/cross-op context OFF, one CPU thread, QBS emulation OFF.
- A real single-CPU GGML scheduler runs each paired graph. Its evaluation
  callback checks before and after each matmul that the source tensor and data
  pointers still identify the original view, and logs actual `nb0`/`nb1` and
  contiguity. Only VIEW and MUL_MAT operations are accepted. There is no
  manually called preparation or matmul kernel in the driver.
- Require successful complete graph calls and both completion callbacks,
  finite overwritten outputs, bit-exact paired values, and byte-exact full
  backing allocations (including all row padding and both guard regions).
  Also check the complete repacked-weight allocation, original float and
  quantized weight arrays, and activation prefix. All output pairs include
  decimal values and exact bits; each failing shape retains its first mismatch.
- The Python checker independently reconciles values, first mismatches,
  scheduling observations, existing-helper traces, and native QBS activity.
  A discrepancy makes both the guest and runner exit nonzero, with suite FAIL.
  The fixed matrix continues to completion to characterize both weight types
  and tail shapes; there are no retries or production changes.

## Execution And Evidence

From `/home/wangwy/openproject/ara_dsa_signoff_integration`:

```sh
python3 -B verification/qbs/m4_prepared_reuse/packed_stride/run.py
```

The runner refuses an existing output directory. It checks all 901 SHA256
entries of `verification/out/m4-prepared-installed-build-20261027-01/manifest.json`
before reuse, requires the passing normal build, and links only its four normal
libraries plus `test.o`. It reuses checked firmware, kernel, init, capture, and
custom-instruction QEMU assets from the verified graph recipe. The compiler
recipe follows `run_installed.py` / `runtime_graph.cpp`; the manifest also pins
this reproducer and its actual execution inputs before and after the run.

Output is exclusively `verification/out/m4-packed-stride-repro-20261027-01`.
There is exactly one QEMU invocation, with a hard 300-second process timeout.
If launched as a transient systemd service, the service must execute `python3`
directly and retain stdout/stderr, not launch a detached worker and exit.

Evidence includes `preflight.json`, command/exit records, `link.map`, the
executable and initramfs, `manifest.json`, `qemu.log`, `first-mismatch.json`,
`comparison.json`, and `result.json`. `CONFIRMED` is a failing result, never a
PASS. No mismatch means only not reproduced within this bounded matrix, not
universal proof that other shapes or execution modes are correct.
