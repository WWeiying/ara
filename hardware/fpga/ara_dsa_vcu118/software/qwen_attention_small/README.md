# Small real-Qwen attention FPGA package

This package uses the real Qwen2.5-1.5B llama.cpp capture
`operator/decode/attention_core`: one decode token, `dim=128`, 12 query heads,
2 KV heads, and a physical KV capacity of 256. The five input/golden blobs are
about 269 KiB; the ELF includes the measured attention workspace and is about
1.91 MiB, so it is suitable for the existing COM6/115200 UART path.

The three ELFs use exactly the same input and golden output:

- `rvv.elf`: standard RVV attention;
- `akv.elf`: version-1 native AKV attention;
- `akv_v2.elf`: token-axis AKV-v2 attention.

They are bare-metal operator measurements, not a complete Linux boot and not a
full-model throughput claim. They provide a small, reproducible FPGA data
point before moving to multi-layer model execution.

## Windows

Use the already programmed normal-speed bitstream and COM6 at 115200. Reset
the CPU in Vivado VIO before each ELF. From
`D:\project\ara\hardware\fpga\ara_dsa_vcu118`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\software\run_qwen_attention_small.ps1 -Mode rvv -Port COM6
powershell -NoProfile -ExecutionPolicy Bypass -File .\software\run_qwen_attention_small.ps1 -Mode akv -Port COM6
powershell -NoProfile -ExecutionPolicy Bypass -File .\software\run_qwen_attention_small.ps1 -Mode akv_v2 -Port COM6
powershell -NoProfile -ExecutionPolicy Bypass -File .\software\compare_qwen_attention_small.ps1
```

Each run leaves `raw.log`, `result.csv`, `result.json`, and `elf.sha256` in
`D:\qwen_attention_runs`. The comparison contains cycles, seconds at 50 MHz,
relative cycles, speedup, and mismatch count. A valid run must print
`LLAMA_OPERATOR ... PASS cycles=... mismatches=0`.

This package does not fake a single combined model run: the existing QBS linear
ELF and these AKV attention ELFs are measured separately with the same
bitstream. That isolates each accelerator path and is the correct first
diagnostic point. A later small multi-layer replay can compose these measured
operators after the three FPGA results are confirmed.
