# Small real-Qwen QBS + AKV replay

`qbs_akv.elf` is one bare-metal replay built from real Qwen2.5-1.5B
llama.cpp captures. It runs a 32-row Q4_K projection through the QBS path,
then one decode `attention_core` (`dim=128`, 12 query heads, 2 KV heads,
physical KV capacity 256) through AKV-v2. Both outputs are checked against
the captured llama.cpp golden tensors.

The UART log contains the individual QBS and attention records plus:

```text
QBS_AKV_COMBINED result=PASS qbs_cycles=... attention_cycles=... total_cycles=...
```

The combined cycle fields are the measured compute intervals from the two
operators. UART printing time is excluded. The package is a small end-to-end
operator replay, not a complete Linux boot or full-model throughput result.

## Windows

Use the existing normal-speed bitstream, COM6, and 115200 baud. Reset the CPU
in Vivado VIO before running the ELF. From
`D:\project\ara\hardware\fpga\ara_dsa_vcu118`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\software\run_qwen_small_combined.ps1 -Port COM6
```

The command writes `raw.log`, `result.csv`, `result.json`, and `elf.sha256`
under `D:\qwen_small_combined_runs`. The parser rejects missing records,
nonzero mismatches, an AKV-v2 fallback, nonzero runtime statuses, or
inconsistent cycle totals. Ordinary Spike does not implement the QBS custom
instruction; use the existing patched QEMU/llama.cpp check for functional
QBS validation and this ELF on the FPGA for QBS cycle data.
