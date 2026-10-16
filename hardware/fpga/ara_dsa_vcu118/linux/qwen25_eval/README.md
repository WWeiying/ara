# Qwen2.5 FPGA evaluation image

This is a separate Linux payload. It does not replace or rewrite
`linux/artifacts/`, the original interactive image, or any FPGA bitstream.

The payload contains a statically linked llama.cpp `llama-simple` compiled
with both QBS and AKV support, a reliable UART model receiver, deterministic
prompt files, and the `qwen-eval` mode wrapper. QBS and AKV are runtime
selected by environment variables inside the wrapper:

| Mode | `GGML_RISCV_QBS` | `GGML_RISCV_AKV` |
|---|---:|---:|
| `rvv` | off | off |
| `qbs` | on | off |
| `akv` | off | on |
| `qbs-akv` | on | on |

The model is deliberately uploaded after Linux reaches the shell. Putting a
1.12 GB GGUF inside initramfs would make the kernel temporarily hold both the
cpio archive and the unpacked model, which is unsafe on the board's 2 GB DDR.
The receiver writes one 64 KiB frame at a time to `/model` and checks every
frame with CRC32.

## Build on the Linux development host

```bash
cd hardware/fpga/ara_dsa_vcu118
QWEN_MODEL=/home/wangwy/llama/models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  bash linux/build_qwen25_eval.sh
```

The local working output is in `linux/qwen25_eval/out/`. The script also copies
the boot payload into the separate package directory
`linux/qwen25_eval/artifacts/`, which is the directory to use on the Windows
board PC. The default llama.cpp build is in a separate directory,
`build-rv64-ara-dsa-qwen25-eval`, and is statically linked. The 1.12 GB GGUF
model is intentionally not stored in Git; transfer it separately with
`software/model_push.py`.

## Boot and upload the model

Program the existing working bitstream as before. On the Windows board PC,
load the new Linux payload with the old 115200-bitstream settings:

```powershell
py hardware/fpga/ara_dsa_vcu118/software/uart_load.py --port COM6 --elf hardware/fpga/ara_dsa_vcu118/linux/qwen25_eval/artifacts/fw_jump.elf --load 0x80200000:hardware/fpga/ara_dsa_vcu118/linux/qwen25_eval/artifacts/Image --load 0x80100000:hardware/fpga/ara_dsa_vcu118/linux/qwen25_eval/artifacts/ara_vcu118.dtb --load 0x88000000:hardware/fpga/ara_dsa_vcu118/linux/qwen25_eval/artifacts/initramfs.cpio --no-readback --chunk-size 4096 --interactive
```

After the shell is visible, press `Ctrl-C` to disconnect the loader without
resetting Linux. Then run a second PowerShell command from the repository
root. The model file remains on the Linux side until power is removed:

```powershell
py hardware/fpga/ara_dsa_vcu118/software/model_push.py --port COM6 --model D:\models\qwen2.5-1.5b-instruct-q4_k_m.gguf
```

Verify the target hash against `artifacts/MODEL_MANIFEST.txt`:

```text
sha256sum /model/qwen2.5-1.5b-instruct-q4_k_m.gguf
```

At 115200 baud, uploading 1.117 GB takes roughly 27 hours. The image and
protocol also work with a validated 1562500-baud boot/UART setup; at that rate
the model transfer is roughly 2 hours. No RTL rebuild is needed for the
runtime mode changes themselves.

## Run the four cases

Start with a short run:

```text
qwen-eval rvv 64 8
qwen-eval qbs 64 8
qwen-eval akv 64 8
qwen-eval qbs-akv 64 8
```

Then use the fixed prompt labels and generation lengths needed for the report,
for example `qwen-eval qbs-akv 128 32`. Each run writes a log under
`/eval/results/` and enables the QBS/AKV coverage and execution summaries.
The llama.cpp performance report contains the actual prompt-token count; the
`64/128/512/2048` labels identify the fixed prompt files and are not silently
claimed to be exact tokenizer lengths.
