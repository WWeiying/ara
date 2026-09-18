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

`vendor/` 随包携带纯 Python 的 pyserial/pyelftools wheel，脚本可直接导入，不必在线 pip 安装。
加载器先逐块写入并读回校验，再执行入口，并显示 30 秒串口输出。
预期出现 `SMOKE PASS: small RAM, RVV integer, QBS/AKV capabilities`；这是预期标志，不是已经上板跑出的记录。
程序结束后停在 WFI，重新加载前通过 VIO 复位一次，等 DDR 再次 ready。

同一个加载器也支持多个 DDR 裸镜像。Linux 首次启动的设备树、内核和 initramfs 流程见上级 `linux/README.md`；大镜像应使用 `--no-readback`，并可提高 `--chunk-size`。

## 注意

- 整个硬件包尚未上板，UART 驱动、DDR 校准、实际波特率仍需在板上确认。
- 默认 Boot ROM 来自锁定的 Cheshire RTL，Boot ROM 源码和 UART 协议源码在 `reference/`。
- UART 没有带宽优势，只用于首个小程序。不要用 115200 串口传输 GB 级模型。
- DDR 里的 `.elf` 和 FPGA 的 `.bit` 是两种不同文件，不能把 ELF 导入 Vivado 当成 HDL。
- 要重编译，运行 `build_smoke.py --gcc <RV64 GCC> --objdump <RV64 objdump>`。Windows 创建 Vivado 工程不需要这个编译器。
- 完整模型接入需另做 Linux/设备树/rootfs 和权重存储，并验证加速器上下文与操作系统的使用约束。
