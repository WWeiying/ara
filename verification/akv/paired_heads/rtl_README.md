# Paired-head RTL numeric gate (build only)

This gate does not execute a simulator. It links the frozen experimental leaves
and canonical generic F16 QK/PV assembly into the same GNU baremetal ELF. No
canonical source, existing helper, or simulator image is modified.

## Scope

Accepted Qwen KV128 capture, physical Q=[128,1,12,1], K/V=[128,256,2,1].
The three shapes are **derived dimension/head subsets, not new model captures**:

| D | tokens | query stride | KV head | real Q heads |
|---|---|---|---|---|
| 64 | 1 | 320 | 0 | 0,1 |
| 96 | 63 | 256 | 1 | 6,7 |
| 128 | 64 | 320 | 1 | 6,7 |

All contexts contain tokens0..63 and exactly two real Q rows. Each mode uses
FULL once, QK then PV on that same context, RELEASE once. Capabilities are read
using actual akv_device_query, and bounded geometry is validated before FULL.
There is no reference capability injection, fallback after partial issue, or
concurrent context owner in this single-threaded baremetal program.

QK query conversion is Python struct `<e` RNE from genuine F32 Q. Independent
host C fmaf uses original capture physical indexing and dimension0..D-1 order.
All 512 score bytes per run, including tails, are compared on chip; mode1 also
compares baseline bytes. Host exceptions map explicitly to RISC-V flags.

PV is **canonical regression only, not an independent FP16 oracle**. Accumulator
row0/1 starts with real V token0/1, first D channels. Coefficients alternate
0.5/1.0 (opposite phase per head); old scales are 0.5/1.0. These are declared
control inputs, not softmax outputs or a full-Attention comparison. The two
modes compare all 1024 accumulator bytes and FCSR; baseline and paired both
check inactive gaps. Score rows remain 256B and accumulator rows 512B.

Each phase starts with RNE FCSR=8 (sticky DZ), VCSR=5. No live vector values
cross a C call. The snapshot retains `vmv.x.s ...,v12; fence rw,rw; frcsr; csrr
...,vcsr`: **v12 is not an operand dependency on the paired result**. This
accepted image's `hardware/src/ara_sequencer.sv:619` VMVXS issue gate waits for
all older running instructions and mask work. The builder pins that RTL via
the accepted image source manifest and verifies retained snapshot instructions.

Compact UART: 26 success records, per-stage FNV32 summaries, CSR/counts/check
results, plus first byte mismatch only on failure. Hashes do not replace exact
on-chip comparisons. Each stage checks 34,112 input bytes, 1,152 guard bytes,
the untouched dummy output and descriptor; PV also checks unchanged QK scores.
Real vector/backend/AXI-write traces and AKV_PERF remain mandatory.

Static work: 1,044 commands = 576 column singles +72 panels +384 V rows +6 FULL
+6 RELEASE; 864 logical columns, 786 read ranges, 2,304 Q bytes, 147,456 KV bytes,
150,144 read-payload bytes, 196,416 replay bytes. No speedup claim. Compact UART
reduces output volume, but wall time is unmeasured; use a 10,800-second safety
budget, not a shorter timeout chosen to truncate slow passing cases.

## Build and host tests

From the signoff worktree:

```sh
python3 -B -m unittest discover -s verification/akv/paired_heads -p rtl_test.py -v
python3 -B verification/akv/paired_heads/rtl_build.py \
  --output verification/out/akv-paired-heads-rtl-gate-build-20261023-01
```

The build checks original accepted capture hashes, the accepted QBACC image
receipt chain (not its historical failed parent status), actual image components
and source hashes. It pins canonical and experimental sources, all transitive
C/assembly headers, tools, host libm, oracle binary, generated data and ELF.
Start/post hashes must match. `build.json` stays BUILT_NOT_EXECUTED.

## Later execution, only after authorization

Use a new output directory and a directly owning bounded systemd worker. Do not
reuse the old QK panel4 worker: its workload checker expects different counts.
Before and after execution require all build/artifact pins and accepted image
components unchanged, and run the existing source-inventory checker:

```sh
PYTHONPATH=verification python3 -B -m ara_verify.vcs_source_manifest \
  --output verification/out/qbacc-soc-20261023-02/build/sim/vcs_source_manifest.json --check
```

Reviewed simulator argv (absolute ELF/log/trace paths; fresh working directory):

```text
<qbacc-soc-20261023-02/build/sim/simv> -no_save -l <run.vcs.log>
 +PRELOAD=<akv_paired_heads_rtl.elf> +TESTCASE=akv_paired_heads_rtl
 +NO_FSDB +NO_INSTR_TRACE +AKV_PERF +AKV_SUMMARY
 +VECTOR_TRACE=<vector_trace.csv>
 +ARA_CONTRACT_TRACE_LIMIT=2000000 +ARA_UVM_TRACE_LIMIT=2000000
```

After simulator exit0 and before acceptance, require both checks:

```sh
python3 -B verification/akv/paired_heads/rtl_check.py --build <BUILD> --log <LOG>
PYTHONPATH=verification python3 -B -m ara_verify.uvm_dut \
  --require-events --require-backend --require-axi --require-axi-write \
  --vector-trace <TRACE> --log <LOG> --simv <SIMV> --elf <ELF> --output <UVM_JSON>
```

The compact checker returns NUMERIC_AND_WORK_CHECKED, deliberately not final
run acceptance: UVM PASS with empty issues, matching ELF/log/trace/image hashes,
and post-run source/image/artifact pin equality are independently required.
On timeout/signal terminate and reap the simulator process group; preserve the
first failure and do not automatically retry. No VCS/QEMU execution is part of
the build or host tests.
