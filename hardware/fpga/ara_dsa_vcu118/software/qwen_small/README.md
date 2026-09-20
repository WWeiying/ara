# Small Real-Qwen FPGA Benchmark

This package is the first end-to-end measurement point. It uses real
Qwen2.5 layer-0 Q4_K data captured from llama.cpp, but limits the operator to
32 output rows and one decode input (`K=1536`, `M=1`). The same activation,
weight, and golden output are used by the RVV and QBS ELF files.

The package deliberately measures one real llama.cpp-compatible linear layer,
not a synthetic matrix and not the full model. It is small enough to load over
the existing VCU118 COM6/115200 path, while still exercising quantization,
Q4_K weight access, the matmul kernel, correctness checking, and cycle timing.

## QEMU functional check

On the Linux development host, run the existing QBS contract regression first:

```bash
verification/qbs/qemu/run_qbs_contract_test.sh
```

For a small real llama.cpp model check, use the 101 MiB SmolLM2 Q4_K_M model;
this validates the QEMU/llama.cpp dispatch path and is separate from FPGA
timing:

```bash
QBS_MODEL_FILE=/home/wangwy/llama/models/SmolLM2-135M-Instruct-Q4_K_M.gguf \
QBS_MODEL_NAME=smollm2-135m-q4_k_m.gguf \
QBS_EXPECTED_PROFILES=Q4_K \
QBS_EXPECTED_EXECUTION=both \
QBS_TOKEN_COUNT=2 \
QBS_QWEN_WORK_DIR=$PWD/verification/qbs/qemu/build/smollm2-small \
verification/qbs/qemu/run_qwen_native_check.sh
```

QEMU is a functional model, not an FPGA cycle model. The FPGA result below is
the performance measurement.

## Windows FPGA run

Use the already verified normal-speed bitstream and COM6 at 115200. Do not
rebuild or reprogram the bitstream for this package. After programming the
FPGA, run one mode at a time. Reset the CPU through Vivado VIO before each
run, then execute one copyable command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\software\run_qwen_small.ps1 -Mode rvv -Port COM6
```

Reset the CPU again and run QBS:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\software\run_qwen_small.ps1 -Mode qbs -Port COM6
```

Each run creates `raw.log`, `result.csv`, `result.json`, and `elf.sha256`
under `D:\qwen_small_runs\<mode>_<timestamp>`. The CSV fields include result,
cycle count, cycles per output, quantize/pack/matmul cycles, logical bytes,
checksum, mismatch count, and error bounds. A valid run must report
`result=PASS` and `mismatches=0`.

The cycle counter is the FPGA CPU cycle counter. With the current 50 MHz
SoC clock, convert cycles to seconds as `cycles / 50000000`. Compare RVV and
QBS using the same bitstream, reset procedure, and UART command.

This first package does not claim AKV coverage. It establishes a reproducible
real-Qwen RVV-versus-QBS baseline; AKV should be added as a second small case
after this data path is confirmed.
