# 初次上板程序

`smoke.elf` 是为本包编译的 bare-metal 程序，不是 Linux，也不是模型测试。
程序入口位于 DDR `0x80000000`，测试小范围存储读写、67 个元素的普通 RVV 加法及 QBS/AKV 能力返回值。
它不验证 QBS/AKV 的数值计算，不覆盖整个 DDR 容量，不输出 FPGA 性能结论。
`smoke.dump` 为反汇编，`smoke.map` 为链接映射，`include/` 是本次 RTL 对应的 ABI 头文件。

## Windows UART 加载

Vivado 下载 bitstream 后，VIO 启动模式保持 `00`，观察 `probe_in0=1110`。
安装板载 USB-UART 的驱动，在设备管理器确认 COM 号。关闭占用该串口的终端。
Cheshire 原有 Boot ROM 的被动模式支持 UART 的 WRITE / READ / EXEC 协议，因此这一步不需要外接 CPU JTAG。

安装 Python 3.9 或更新版本，然后在工程根目录执行：

```powershell
py software/uart_load.py --port COM5
```

The loader keeps 115200 as its default for compatibility with the existing
bitstream. After rebuilding and programming the fast-boot bitstream, use the
CP2105 Enhanced COM port and select the matching rate explicitly:

```powershell
py software/uart_load.py --port COM7 --baud 1562500 --console-baud 115200 `
  --no-readback --chunk-size 65536
```

The 1562500 setting is only valid after the Boot ROM has been regenerated with
the updated `reference/params.h` and the resulting RTL has gone through
synthesis, implementation, and bitstream generation. The CP2105 Standard COM
port is kept for 115200; the Enhanced COM port is the high-speed channel.
`--console-baud 115200` switches the host back after `EXEC`, matching the
Linux device tree and the smoke program's console setup.

`vendor/` 随包携带纯 Python 的 pyserial/pyelftools wheel，脚本可直接导入，不必在线 pip 安装。
加载器先逐块写入并读回校验，再执行入口，并显示 30 秒串口输出。
预期出现 `SMOKE PASS: small RAM, RVV integer, QBS/AKV capabilities`；这是预期标志，不是已经上板跑出的记录。
程序结束后停在 WFI，重新加载前通过 VIO 复位一次，等 DDR 再次 ready。

Linux 交互启动可在加载命令末尾增加 `--interactive`。该模式在 `EXEC`
之后保持串口打开，把主机键盘输入转发到目标，并把目标输出显示到当前
终端。Linux 设备树控制台仍为 115200；高速 Boot ROM 只用于加载阶段：

```powershell
py software/uart_load.py --port COM7 --baud 1562500 --console-baud 115200 --interactive
```

按 `Ctrl-C` 只断开主机串口桥，不会复位 FPGA 中正在运行的 Linux。

同一个加载器也支持多个 DDR 裸镜像。Linux 首次启动的设备树、内核和 initramfs 流程见上级 `linux/README.md`；大镜像应使用 `--no-readback`，并可提高 `--chunk-size`。

## 注意

- 整个硬件包尚未上板，UART 驱动、DDR 校准、实际波特率仍需在板上确认。
- 默认 Boot ROM 来自锁定的 Cheshire RTL，Boot ROM 源码和 UART 协议源码在 `reference/`。
- UART 仅用于加载和验证，不是持久化存储。旧 bitstream 使用 115200；新的
  高速 bitstream 使用 1562500，并且主机必须选择 CP2105 Enhanced COM 口。
  即使提高到 1562500，1.28 GB 模型仍需要约 2.3 小时，不能替代 Flash、PCIe
  或 Ethernet 高速加载。
- DDR 里的 `.elf` 和 FPGA 的 `.bit` 是两种不同文件，不能把 ELF 导入 Vivado 当成 HDL。
- 要重编译，运行 `build_smoke.py --gcc <RV64 GCC> --objdump <RV64 objdump>`。Windows 创建 Vivado 工程不需要这个编译器。
- 完整模型接入需另做 Linux/设备树/rootfs 和权重存储，并验证加速器上下文与操作系统的使用约束。

## Small real-Qwen attention measurement

`qwen_attention_small/` is a separate bare-metal package for the first
attention end-to-end measurement. It uses the real llama.cpp Qwen2.5-1.5B
decode capture and provides RVV, AKV-v1, and AKV-v2 ELFs. It does not replace
the Linux artifacts or the QBS linear package. Run it with
`run_qwen_attention_small.ps1`; each mode writes the raw UART log plus CSV,
JSON, and an ELF hash, and `compare_qwen_attention_small.ps1` produces the
three-mode cycle comparison.

`qwen_small_combined/` contains the next small end-to-end replay. Its single
`qbs_akv.elf` runs one real Qwen Q4_K projection through QBS and one real
`attention_core` decode through AKV-v2, checks both golden outputs, and emits
QBS cycles, attention cycles, and their UART-excluded total. Run
`run_qwen_small_combined.ps1`; it saves `raw.log`, `result.csv`,
`result.json`, and the ELF hash under `D:\qwen_small_combined_runs`.

## Four-mode small matrix

The matrix runner combines the same real-Qwen projection and attention records
into four comparable rows: `rvv`, `qbs`, `akv` (AKV-v2 attention), and
`qbs_akv`. It runs five ELF cases because the first three rows reuse the
projection or attention records; all cycle measurements are compute intervals
and exclude UART printing.

Use the normal bitstream and COM6/115200. Add `-WaitForReset` when the CPU
must be reset in Vivado VIO before each case:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\software\run_qwen_small_matrix.ps1 -Port COM6 -WaitForReset
```

With the bitstream open in Vivado Hardware Manager, the reset can be pulsed
from the Vivado Tcl Console instead of clicking VIO manually:

```tcl
source D:/project/ara/hardware/fpga/ara_dsa_vcu118/software/reset_vio_cpu.tcl
```

Run that command at each `-WaitForReset` prompt, then press Enter in the
PowerShell window. The helper changes only `probe_out0` (CPU reset); it leaves
the boot-mode probes unchanged.

The final `matrix.csv`, `matrix.json`, and `manifest.json` are written under
`D:\qwen_small_matrix_runs\matrix_<timestamp>`. Each row includes projection
and attention cycles, total cycles, 50 MHz seconds, speedup against RVV,
logical read bytes, native dispatch, mismatch counts, and pass status.
