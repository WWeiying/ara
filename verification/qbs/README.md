# QBS reference and contract-verification environment

This directory contains the executable specification and focused RTL contract
checks for QBS architecture version 3 and descriptor version 2.

- `qbs_ref.c`: descriptor validation, all nine implemented weight profiles,
  Q8_K/Q8_0 activation execution, layout conversion, numerical-contract
  ordering, trace events, and atomic result commit. R4 output-row groups are
  padded to four rows; the descriptor retains logical N and commit ignores
  padding.
- `qbs_ref_test.c`: constructed-vector tests for instruction/descriptor ABI,
  fixed-RNE behavior under a conflicting host rounding mode, profile decoding,
  quantization, layout equivalence, M/N tails, and failure behavior.
- `qbs_real_test.c`: tiled execution over the six captured Qwen2.5 workloads.
  It requires bit-identical outputs across supported layouts and compares the
  numerical-contract output with the captured llama.cpp golden result.
- `run_real_cases.sh`: fixed real-data regression manifest.
- `qbs_command_vectors.c` and `qbs_engine_tb.sv`: end-to-end command tests for
  every implemented profile and M1--M8 narrow/wide command geometry, including
  R4 `N=7/9` multi-block tails and four validation/MMU/AXI/PMA fault classes.
- `compare_adaptive_model_logs.py`: matched-log checker for the production
  GGML M4/M8 paths. It reconstructs ABI-derived weight-plus-activation payload
  bytes and rejects mismatched graph-node counts, M counters, command counts,
  or dot work. It does not treat those logical bytes as measured AXI traffic or
  cycle speedup.
- `qbs_activation_context_tb.sv`: focused DIRECT-independent context storage,
  metadata lookup, stale-generation rejection, incomplete-FILL protection,
  abort, replay backpressure, and RELEASE test. It deliberately writes Q8_K
  blocks with 12-, 8-, and 4-byte first chunks to exercise non-row-aligned
  compact storage.
- `qbs_context_sram_macro_model.sv`: behavioral model for the exact
  `64x256` TSMC macro interface used by the synthesis branch.
- `check_activation_context_evidence.py`: strict two-tile top-level log
  validator. It checks checksum equality, access modes, fault flags, AXI range
  roles and payload bytes, context counters, and cycle deltas together.

Run the fast constructed tests with:

```sh
make -C verification/qbs check
```

The profile-level VCS suite contains the original 432 cases plus 16 Q8_0
signed-extreme cases (physical M1--M4, row counts 1--4). Both operands are
`-128`: eight products total `+131072`, which requires a signed 19-bit dot
result. Alternating `-128/127` inputs alone do not exercise this overflow.
The suite checks decoded operands, integer groups/results, first and repeated
FP updates, fflags, and dot activity counters. Its PASS lines also report
first/repeated block latency for before/after comparisons.

From the repository root, use a separate build directory:

```sh
build_dir=$(mktemp -d)
make -C verification/qbs rtl-profile-check RTL_BUILD="$build_dir" RTL_RUN_TIMEOUT=180

# Optional: trace the first extreme case, without changing the DUT.
"$build_dir/simv" -no_save -l "$build_dir/trace.log" \
  +QBS_VECTOR_FILE="$PWD/verification/qbs/qbs_rtl_vectors.txt" \
  +QBS_DOT_TRACE_CASE=432
```

`QBS_DOT_TRACE` samples stream-zero operands at a rising edge and reports the
registered dot result after that edge, together with a signed 32-bit testbench
sum. The trace is disabled unless a case ID is supplied. Test success requires
the final PASS marker and no `Error:`/`Fatal:` lines, not just process exit zero.
The measured failure, fix, and unchanged command-cycle comparisons are recorded
in [the signed-extreme regression report](results/int8_extreme_20260908.md).

Run the six real-data cases with:

```sh
make -C verification/qbs real-check
```

After building the patched QEMU model, run the short ISA-contract regression
with `QBS_QEMU=/path/to/qemu-system-riscv64 make -C verification/qbs
qemu-contract-check`. It drives `frm=RUP` through an RNE/RUP-discriminating
input and checks that QBS still returns the fixed-RNE result. It also requires
load-access faults, before device reads, when the descriptor, activation, or
weight range points at the QEMU `virt` UART MMIO region. Legal payloads that
cross a 4-KiB page must succeed; payloads whose tail crosses from RAM into an
unmapped region must fault without changing the destination vector group.

Run the generic and SRAM-mapped activation-context checks with:

```sh
make -C verification/qbs rtl-context-check
make -C verification/qbs rtl-context-macro-check
make -C verification/qbs rtl-engine-check
```

The engine test executes FILL/REUSE/RELEASE through the normal range builder,
read engine, compute engines, and atomic commit path. Mismatched context ID,
generation, profile, layout, M, or K must fault before any payload access.

After the real Qwen2.5 two-tile top-level runs have populated
`hardware/qbs_activation_context_evidence`, validate the evidence with:

```sh
make -C verification/qbs activation-context-evidence-check
```

The expected pair is `decode_attn_q` DIRECT/DIRECT versus FILL/REUSE. A
passing result proves that the second command has no activation AXI range and
that both executions produce the same bit-level checksum; it does not infer
absence of reads from a single aggregate counter.
