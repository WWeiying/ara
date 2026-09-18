# 从当前 RTL 到 VCU118 的接入说明

## 数据通路

```text
                      VCU118 250 MHz
                            |
                  Clock Wizard: 50 MHz
                            |
              +-------------+--------------+
              |                            |
        CVA6 + L1 I/D cache          4-Lane RVV
              |                  VLEN=1024, QBS, AKV
              |        accelerator/MMU/response |
              + <----------------------------> +
              |                         128-bit AXI
              |                    L1 invalidation filter
              |                    128-to-64 conversion
              +------------+---------------+
                           |
                    Cheshire AXI fabric
                      /           \
        ROM/CLINT/PLIC/UART/...     LLC / SPM
                                      |
                            AXI width/ID conversion
                                      |
                              dual-clock AXI FIFO
                                      |
                            DDR4 IP, 512-bit AXI
                                      |
                              64-bit DDR4 pins
```

新建的是板级封装，不是把现有仿真 `ara_soc` 原封不动当作 FPGA 顶层。
现有的 CVA6/RVV 核心和 QBS/AKV 运算机制保留，SoC 使用具有 Ara 接入的 Cheshire 版本。
该版本的 accelerator request/response、MMU 和 L1 invalidation 接口与当前代码对接。

## 接入时做了哪些适配

| 位置 | 本包处理 | 原因 |
|---|---|---|
| 板级顶层 | 固定 1 CVA6、4 Lane、VLEN=1024，关闭无外接引脚的 USB/VGA/SerialLink/I2C 和本阶段不用的 DMA | 不把悬空板级接口带到综合顶层；LLM 数据通路不依赖这些外设 |
| CVA6 配置 | `XF16=1`；`FpgaEn=0`，维持通用实现 | 当前 CVA6 的 `FpgaEn=1` 会选中故意报错的 FPGA RAM 占位模块；不能将其当作真实 RAM 使用 |
| 片上 RAM | 选择 `tc_sram_xilinx.sv`，Vivado 实例化真实 XPM | 没有使用 TSMC 宏，也没有用空壳模块假装存储器 |
| CVA6 cache RAM wrapper | 补齐下层 SRAM 的 reset 和 user 端口连接 | 通用仿真 RAM 对复位依赖较小，XPM 输出复位不能悬空 |
| 标量核 CLIC | 未启用的 CLIC 输入显式接零 | 防止无意的悬空输入，不新增 CLIC 功能 |
| UART/GPIO | UART CTS/DSR/DCD 置于允许通信状态，未用 GPIO 接零 | 默认 Boot ROM 开启 UART 自动流控，CTS 不能悬空 |
| `axi_inval_filter` | 仅编译本项目实现，不重复编译依赖中的同名模块 | 保持现有 cache invalidation 逻辑，并消除重复定义 |
| Dispatcher 的 VL 比较 | 三处 AVL/slide 比较改用显式低位切片，保留高位非零检查 | 避开 Vivado 2020.1 对这些 `vlen_t'(...)` 表达式的 `Synth 8-2105` 报错，不改变 unsigned 截断、比较和溢出处理 |
| AKV 字节统计 | 可综合路径的三处动态 `$countones` 改为固定上限的逐位计数；读 strobe 计数共用一个组合结果 | 避开 Vivado 2020.1 的 `Synth 8-280`；只统计已知的 1，保留计数寄存器更新条件，不改数据通路或流水级 |
| AKV 一处表达式 | 导出副本中 `!&descriptor_byte_valid_q` 写成 `!(&descriptor_byte_valid_q)` | 显式表达 reduction-AND 后取反，消除解析歧义；不改变预期逻辑 |
| DDR wrapper | 回移上游 VCU118 支持，补齐 DDR ready 和时钟域复位 | 上游 Ara-enabled 分支没有 VCU118 板级支持 |
| 时钟门控 | 使用 tech_cells_generic 的 Xilinx 映射，节能用 clock gating 在 FPGA 上旁路 | 不能照搬 ASIC 的门控时钟实现，FPGA 功耗也不能直接当 ASIC 功耗 |

这些修改仅发生于工程包里的导出副本；原工作区的 `hardware/src`、`hardware/include` 和 CVA6 依赖没有被修改。
精确改动在 `provenance/integration.patch`；原有 CVA6 工作区修复另存于 `cva6_local.patch`。

## 复位与 CDC

物理 reset、VIO reset 或 PLL 未锁定时，DDR 控制器复位。
DDR `init_calib_complete` 为真且 UI reset 撤销后，允许释放系统复位。
SoC 和 DDR UI 两侧的 `rstgen` 使用共同的异步复位条件，各自同步释放。
因此不在两个 AXI FIFO 时钟域之间引入“一个还运行、另一个已单独清空”的正常复位流程。

CDC 约束不把 SoC 与 DDR 两个时钟整体切成 false path。
它对异步 FIFO 的 data 和 Gray pointer 设置 3 ns datapath 上限，并关闭对应 hold 检查。
实现阶段会检查 CDC 端点和 DDR UI 时钟是否存在，若未匹配则报错。
这仍需要在 Vivado `report_cdc` 中结合实际布局审查，静态 Tcl 测试无法验证物理 CDC。

## 启动与模型边界

只将 VIO boot mode `00` 作为当前推荐启动方式，通过板载 UART 的原有被动加载协议运行程序。
`linux/` 目录现在提供了基于同一 bitstream 的 OpenSBI/Linux 首次 handoff 产物和加载脚本；
该路径仍需在实际板上完成一次启动验证，不能把静态生成成功当成 Linux 已经在板上运行。
不要直接选择其他 boot mode：本顶层没有 SD/I2C 启动接线，QSPI 也没有验证 Flash 型号对应的软件驱动。

2 GiB DDR 是一个通道的容量，不是片上 SRAM 容量。LLC/SPM 默认物理容量为 128 KiB。
`0x10000000` 是 SPM cached alias，`0x14000000` 是 uncached alias；不要在模型程序中使用仿真 testbench 的地址假设。
模型性能会受到 FPGA 主频、DDR/LLC、软件系统的共同影响，不能由原先仿真周期直接宣称已经获得板级 token/s。
