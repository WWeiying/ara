# QBS Phase-0 reference environment

This directory is the executable specification for the first QBS-Ara ABI.
It is intentionally independent of the RTL implementation.

- `qbs_ref.c`: descriptor validation, Q3_K/Q4_K/Q5_K/Q6_K x Q8_K and
  Q4_0/Q8_0 x Q8_0 execution, layout conversion, numerical-contract ordering,
  trace events, and atomic result commit. R4 output-row groups are padded to
  four rows; the descriptor retains the logical N and commit ignores padding.
- `qbs_ref_test.c`: constructed-vector tests for instruction/descriptor ABI,
  profile decoding, quantization, layout equivalence, M/N tails, and failure
  behavior.
- `qbs_real_test.c`: tiled execution over the six captured Qwen2.5 workloads.
  It requires bit-identical outputs across supported layouts and compares the
  numerical-contract output with the captured llama.cpp golden result.
- `run_real_cases.sh`: fixed real-data regression manifest.
- `qbs_command_vectors.c` and `qbs_engine_tb.sv`: end-to-end command tests for
  every implemented profile, including R4 `N=7/9` multi-block tails and four
  validation/MMU/AXI/PMA fault classes.

Run the fast constructed tests with:

```sh
make -C verification/qbs check
```

Run the six real-data cases with:

```sh
make -C verification/qbs real-check
```
