# VCU118 独立 Vivado 工程包

这是当前 Ara DSA 的 FPGA 移植工程源码快照，不是已经上板验证通过的 bitstream。
包中包含 CVA6、四 Lane RVV、QBS、AKV、Cheshire SoC、外设依赖、板级顶层、约束及 Vivado Tcl。
不需要访问原 Linux 工作区，不需要 Git、Bender、软链接、TSMC SRAM 库。

## 1. Windows 上先做什么

1. 从 GitHub 检出 `ara_dsa` 分支。工程位于 `hardware/fpga/ara_dsa_vcu118/`，不需要 ZIP 或 submodule 初始化。
2. 安装 Vivado 和 **Virtex UltraScale+** 器件支持，确认许可证可以综合 `xcvu9p-flga2104-2L-e`。
3. 推荐使用较新的完整 Vivado，例如 2024.2；本机没有 Vivado，因此尚未在该版本上实际执行本包。
4. 打开 Vivado，在底部 Tcl Console 执行：

```tcl
cd D:/project/ara_dsa/hardware/fpga/ara_dsa_vcu118
source scripts/create_project.tcl
```

该步骤只创建工程、生成 DDR4/Clock Wizard/VIO IP，不启动综合。
生成的工程是 `build/ara_dsa_vcu118/ara_dsa_vcu118.xpr`。
后续可直接打开 XPR；不要反复创建覆盖已有工程。

如果旧脚本在创建 IP 时报告 `Vivado 12-3445`，原因是将多个 IP 传给了
`create_ip_run`。新版脚本改为逐个创建 IP 综合任务，不改变 IP 参数。
该错误会中断 `create_project.tcl`，后面的 XDC 添加等步骤还没有执行，
所以不能直接对残留的半成品工程执行 Run Synthesis。

恢复时先关闭 Vivado 中的工程，将现有 `build/` 文件夹改名备份，
更新 `scripts/create_ip.tcl` 后重新执行上面的创建命令。
也可以在 Git 检出的新路径中，关闭旧工程后重新创建。
不要直接重新 source `create_ip.tcl`，否则会重复创建已存在的 IP。

```tcl
source scripts/synth.tcl
# 检查 reports/synth 后，再执行：
source scripts/impl.tcl
```

也可以使用 GUI 的 Run Synthesis / Run Implementation。
综合脚本会先完成三个 IP 的 OOC 综合，再综合处理器顶层。
实现脚本在 setup 或 hold 未收敛时停止，不把失败时序当成可用结果。
成功后生成 `output/ara_dsa_vcu118.bit` 和 `.ltx`。

### 已完成 IP 综合，但 Dispatcher 报 illegal cast

若 Vivado 2020.1 在 `ara_dispatcher.sv` 原第 1610、1961、2210 行报告
`Synth 8-2105`，新版导出包已将这三处窄化类型转换改成等价的低位切片。
高位非零检查仍保留，不能简单去掉它，否则大 AVL 或 slide offset 会被错误截断。
此项修正仅更新 FPGA 副本，不修改主工程 RTL 或 IP 参数。

按第 7 节同步新版包到原目录，保留已有 `build/`，打开原 XPR 后执行：

```tcl
cd D:/project/ara_dsa/hardware/fpga/ara_dsa_vcu118
reset_runs synth_1
source scripts/synth.tcl
```

不需要重新创建工程，也不需要 reset 已成功的 `ddr4_synth_1` 等 IP 任务。
`reset_runs` 的作用是重置指定的失败任务，见
[AMD UG835](https://docs.amd.com/r/2024.1-English/ug835-vivado-tcl-commands/reset_runs)。
本机没有 Vivado；表达式等价性检查不代表 Vivado 顶层综合已经通过。

### AKV 动态 countones 报错

若遇到 `Synth 8-280 expression must be constant: first argument to $countones`，
新版导出副本已将 AKV 字节统计改成固定上限的逐位计数，包括 replay byte enable
和两处 read strobe 计数。主工程 RTL、计算功能和 IP 配置未改动。
更新后在当前工程目录重置 `synth_1` 并重新执行 `scripts/synth.tcl`，无需重建 XPR。

若同时出现 `Memdata 28-203/28-83`，需保留并检查 DDR4 IP 的完整日志。
不能只凭 `ddr4_synth_1 finished` 就认定校准程序的 BRAM 初始化成功；
在明确原因前，不把生成 bitstream 或上板启动视为已验收。

连接 VCU118 的 FPGA JTAG USB 后：

```tcl
source scripts/program.tcl
```

这里只下载到 FPGA，不擦写板上 Flash。多块板卡连接时要求手动选择。
若仍在旧 `D:/fpga/ara_dsa_vcu118` 中工作，以上 `cd` 改为实际路径；
从 Git 检出目录向旧工程同步的方法见第 7 节，工程名保持不变。

### 已有工程：自动检查并复用 IP

已有 `build/ara_dsa_vcu118/ara_dsa_vcu118.xpr` 且三个 IP 已完成综合时，
不需要新 worktree，也不要重新创建工程或删除 `build/`。以后从 PowerShell 使用：

```powershell
cd D:/project/ara/hardware/fpga/ara_dsa_vcu118
powershell -NoProfile -File scripts/run.ps1
# 综合成功并检查报告后，布局布线使用同一个入口：
powershell -NoProfile -File scripts/run.ps1 -Stage impl
```

若本机策略禁止运行本地脚本，可在上述命令中加入 `-ExecutionPolicy RemoteSigned`，
只对这次 PowerShell 进程生效，不修改系统级执行策略。

默认 Vivado 路径为 `D:/Xilinx/Vivado/2020.1/bin/vivado.bat`，可以用
`-Vivado C:/Xilinx/Vivado/2020.1/bin/vivado.bat` 指定其他安装位置。
结果默认放在工程所在盘的 `fpga_runs/ara_<时间>_<唯一标识>/` 下，
也可用 `-RunRoot D:/fpga/ara_runs` 指定有写权限和足够空间的位置。
所有诊断日志、综合/实现 DCP 都保留，报告在原工程包的 `reports/<新 run 名>/`。

此入口的边界和保护如下：

- 始终打开原 XPR，新增顶层 run，不重置/删除旧 run，不重新生成或升级 IP。
- 检查 `clkwiz`、`vio`、`ddr4` 的完成状态、过期/锁定状态及非空 DCP；不满足条件直接停止。
- 使用独占文件句柄阻止同一工程重复启动；句柄随进程退出释放，不要手动删除 `build/managed/run.lock`。
- 保守拒绝机器上已有的 `vivado.exe`，包括 GUI 和旧 worker，即便它可能属于另一个工程。
  先保存并关闭 GUI，确认残留进程归属后再处理；脚本只列出 PID，不会自动杀进程。
- 每次使用全新的结果目录，不读旧 `synth_1/runme.log` 判断当前进度。
  监视新目录的 `exception.log`、错误标记和崩溃日志，避免已明确启动失败却无限等待。
  没有因为运行时间长或 CPU 低就中止任务的超时策略；无错误记录的挂起仍需人工诊断。
- 成功后记录输入文件指纹。`-Stage impl` 只使用记录的成功综合，源码变化或综合过期时拒绝实现。
  原有自定义 Tcl hook 必须先审查，避免 hook 写回旧目录或修改共享 IP。
- 实现只运行到布线并生成报告，setup/hold 失败则返回错误，**不自动生成或下载 bitstream**。
  布局布线前和布线后检查 `LUTLP-1` 组合环；存在环路则停止，不添加环路豁免。
  审查 DRC、CDC 和未约束路径后再处理 bitstream；原 `output/` 的旧文件不是本次结果。

运行期间保持终端打开，不要通过 GUI/其他脚本同时操作该工程，也不要更新源码。
这是同一份源码的独立运行目录，不是冻结的源码快照。
此入口不代替首次工程/IP 初始化，不修复损坏的 IP，也不能保证排除所有系统权限或安全软件问题。
不混用写死 `synth_1`/`impl_1` 的旧 `scripts/synth.tcl`、`scripts/impl.tcl` 启动后续阶段。

控制流程已用 Tcl/PowerShell 测试替身验证，并非 Windows Vivado 实测。
独立 run 的 `launch_runs -dir` 语义见
[AMD UG835](https://docs.amd.com/r/2020.2-English/ug835-vivado-tcl-commands/launch_runs)。

### 只检查已有综合：不重新综合或生成 IP

已有 `build/managed/latest_synth.json` 时，更新工程包、关闭 Vivado GUI，
在 PowerShell 中执行：

```powershell
cd D:/project/ara/hardware/fpga/ara_dsa_vcu118
powershell -NoProfile -File scripts/run.ps1 -Stage inspect
```

入口仍使用原 XPR 和已完成的综合 DCP，不创建或启动任何 run，不重建三个 IP。
新报告写入 `reports/inspect_<唯一标识>/`，原综合报告和 `latest_synth.json` 不覆盖。
报告包含 `loop_cells.rpt`（环路 LUT 的 INIT、引脚及驱动连接）、`loops.rpt`、
`setup_paths.rpt`、`ignored_exceptions.rpt` 和原有资源、时序、CDC、DRC 报告。
`inspection.json` 同时记录旧综合输入指纹和当前输入指纹，提交报告时一并保留。

此模式允许源码已更新，但分析的是**旧综合网表加当前约束**，不验证新的 RTL，
也不使旧综合重新满足 `-Stage impl` 的输入一致性检查。
检查完成后提交该目录的文本报告即可，不需要上传 DCP、XPR 或 IP 目录。
`reports/` 仍默认忽略；确认本次报告后，可显式加入：

```powershell
git add -f -- 'reports/inspect_*/*.rpt' 'reports/inspect_*/inspection.json'
git diff --cached --stat
```

脚本会自动将原 XPR 中的 `constraints/cdc.xdc` 设置为 `FILE_TYPE TCL`，
以支持 Vivado 2020.1 的 Tcl 控制流，并在 IP 时钟约束之后加载。
五个 AXI CDC FIFO 分别约束数据接收寄存器和双向 Gray 指针第一级同步器，
保持 3 ns `set_max_delay -datapath_only` 上限，不使用整个跨域模块的批量 `-through`。
查不到预期端点或时钟时明确停止；不要用全局 false path 掩盖这些错误。
已有 XPR 应通过上述脚本迁移属性，单击 GUI Run 不会自动执行该迁移。
同步工具即使提示工程配置改变，本次更新也不需要重新创建工程或 IP。
文件类型设置依据 [AMD UG903](https://docs.amd.com/r/2023.1-English/ug903-vivado-using-constraints/About-XDC-Constraints)。

这些修复已经通过离线控制流程测试，但仍需用本机 Vivado 检查实际端点匹配和约束效果。
现有报告的问题清单见 `docs/FPGA_ISSUES.md`。

## 2. 固定配置

| 项目 | 本包配置 |
|---|---|
| FPGA | VCU118，`xcvu9p-flga2104-2L-e` |
| 板卡文件 | AMD VCU118 2.4，已随包提供 |
| 标量核 | 一个 CVA6，MMU、调试、浮点、RVV accelerator 接口 |
| 向量核 | 4 Lane，VLEN=1024 |
| 快速路径 | QBS、AKV、AKV-v2 开启，保留普通 RVV |
| 输入时钟 | 250 MHz 差分时钟 |
| SoC 时钟 | 50 MHz 起步目标，不是已测最高频率 |
| 外部存储 | 一个 64-bit DDR4 通道，2 GiB，`0x80000000..0xffffffff` |
| 片上存储 | Xilinx XPM，保持原端口和读延迟，实际 BRAM/URAM/LUTRAM 分配由综合决定 |
| UART | 板载 USB-UART，用于控制台；启动监控程序默认 115200、8N1 |
| 调试控制 | VIO 控制复位与启动模式，观察时钟和 DDR 就绪 |

DDR 的 512-bit AXI 接口经位宽转换和异步 FIFO 接入 SoC，不能把仿真的 16 MiB L2 数组当作模型 DRAM。
时钟频率不是只改 Tcl 一个数字即可：还要同步 RTC 分频、UART 软件及相关约束。本包先固定 50 MHz。

## 3. 硬件连接与启动边界

板载 FPGA JTAG USB 用来下载 bitstream 和访问 VIO。
本包 CPU 调试 TAP 沿用 Cheshire 的 J53 引脚，不会自动接到板载 FPGA JTAG 链：

| CPU JTAG | FPGA pin | J53 |
|---|---|---|
| TMS | N28 | 1 |
| TDI | M30 | 3 |
| TDO | N30 | 5 |
| TCK | P30 | 7 |

这些约束是 **LVCMOS12**。先核对实际板卡 revision 和电压，不能直接接 3.3 V/5 V 调试器。
没有 CPU JTAG 转接器不影响用 Vivado 下载 FPGA；UART 启动工具的使用见 `software/`。

VIO 的 `probe_out0` 为复位，`probe_out1` 为两位启动模式，`probe_out2=1` 选择 VIO 启动模式。
默认启动模式 `00`。`probe_in0[3:0]` 依次为 SoC reset 已释放、DDR fabric 就绪、PLL locked、reset 请求。
正常稳态应为二进制 `1110`。复位会清除 CPU、CDC 及 DDR 控制器状态，不是保留运行任务的软复位。
系统等待 DDR 初始化完成后才释放处理器复位，避免过早访问尚未就绪的存储器。

## 4. 包内文件

| 目录/文件 | 内容 |
|---|---|
| `rtl/ara`、`rtl/cva6` | 本次导出的实际源码，包括当前本地修复 |
| `rtl/cheshire`、其余 `rtl/*` | 固定版本 SoC 与开源 IP 依赖 |
| `rtl/board` | VCU118 顶层与 DDR 接入 |
| `board_files` | AMD 板卡定义，不依赖 Windows 已安装板卡库 |
| `scripts` | 创建、综合、实现、下载入口 |
| `constraints` | 引脚、时钟、UART/JTAG、DDR CDC 约束 |
| `software` | 板级启动辅助与 smoke test，见该目录说明 |
| `provenance` | 本地 CVA6 补丁、FPGA 集成补丁 |
| `manifest.json`、`SHA256SUMS` | 源码版本、编译顺序、定义和文件校验值 |
| `.gitignore`、`.gitattributes` | 排除本机产物、保留 Windows 检出的快照字节 |
| `licenses` | 随源码分发的许可证 |

## 5. 当前完成度与后续顺序

本包的验收范围是“离线、无软链接的 FPGA 工程输入”，并进行源码/接口静态检查。
2026-09-14 的 Windows Vivado 2020.1 报告证明旧快照 `synth_67f8334f3965` 综合完成，
但同时存在组合环、失效的 CDC 约束和时序违例；不是可上板的验收结果。
本次约束及脚本更新尚未经过 Vivado 实测，布局布线收敛、DDR 上板校准、Linux 启动
或端到端模型运行也**尚未证明**。
具体静态检查记录见 `docs/VALIDATION.md`，不要把静态 elaboration 当成 FPGA 功能验证。

建议逐步验证：

1. Vivado 生成 IP，综合无缺失模块、无非预期 black box。
2. 检查时序、未约束路径、DRC、CDC，不降低 DRC 严重级别来强行生成 bitstream。
3. 下载并检查 VIO 的 PLL/DDR 状态，再验证 UART、DDR 读写、普通 RVV。
4. 验证 QBS/AKV 能力指令及实际计算结果，与已有 Spike/VCS reference 对比。
5. 准备符合 **本 SoC 地址表和中断布局** 的 OpenSBI、Linux、设备树和 rootfs，再接入 llama.cpp。

已有 QEMU `virt` 镜像不能直接当作这块板的 Linux 镜像。
工程没有附带 Vivado 软件、许可证或几 GB 的模型权重，这些不是 RTL 工程依赖。
完整模型还需要文件存储/搬运方案、GGUF 权重、KV cache 和运行内存规划。
初期使用单推理进程；不要假设当前隐藏加速上下文支持操作系统任意任务间的透明抢占保存。

## 6. 来源

- [Cheshire FPGA 平台](https://pulp-platform.github.io/cheshire/tg/xilinx/)
- [Cheshire Ara 集成](https://github.com/pulp-platform/cheshire/tree/mp/ara-pulpv2-os-rebase)
- [AMD VCU118 board files](https://github.com/Xilinx/XilinxBoardStore/tree/2022.2/boards/Xilinx/vcu118/2.4)
- [AMD Vivado IP Tcl 流程](https://docs.amd.com/r/2021.2-English/ug896-vivado-ip/Using-IP-Tcl-Commands-In-Design-Flows)

精确 commit 和集成差异以本包 `manifest.json` 与 `provenance/` 为准。

## 7. 后续源码更新

首次可以只检出 FPGA 工程，避免下载无关工作目录：

```powershell
git clone --branch ara_dsa --single-branch --sparse https://github.com/WWeiying/ara.git D:/project/ara_dsa
git -C D:/project/ara_dsa sparse-checkout set hardware/fpga/ara_dsa_vcu118
py D:/project/ara_dsa/hardware/fpga/ara_dsa_vcu118/scripts/verify_package.py
```

以后更新：

```powershell
git -C D:/project/ara_dsa status --short
git -C D:/project/ara_dsa pull --ff-only
py D:/project/ara_dsa/hardware/fpga/ara_dsa_vcu118/scripts/verify_package.py
```

本机 `build/`、`reports/`、`output/`、日志和备份都已排除，不随 Git 传输。
不要使用 `git clean -fdx`，它会删除这些被忽略的本地产物。
若修改过版本管理中的源码或约束，先整理/提交本地修改，不能用强制 reset 覆盖。
快照的 `.gitattributes` 禁止自动换行转换；校验失败时应检查工作区修改，不要重写校验表掩盖差异。

如果继续使用之前独立的 `D:/fpga/ara_dsa_vcu118` 工程，先更新 Git 检出目录，
再从其中预览向旧工程同步：

```powershell
py D:/project/ara_dsa/hardware/fpga/ara_dsa_vcu118/scripts/sync.py D:/fpga/ara_dsa_vcu118 --from-package D:/project/ara_dsa/hardware/fpga/ara_dsa_vcu118
```

确认后添加 `--apply`。此兼容模式需要 Python 3.9+，无需 Linux、Bender 或交叉编译器。
脚本只更新导出清单管理的文件，不改旧工程的 `build/`、`reports/`、`output/`，并在
`.fpga_sync_backups/` 保存旧文件。`LOCAL` 表示仅本地修改，保留；`CONFLICT` 表示两端内容冲突，整体停止。
不要重写 `SHA256SUMS` 来掩盖本地修改，否则会破坏三方比较的基线。

同步前停止该工程的 Vivado 运行并关闭正在编辑的文件。
若提示源码清单或工程配置变化，需要手动刷新 XPR，或归档旧 `build/` 后重新创建工程。
只修改已有 RTL 正文时，可以保留 XPR，但仍需重新综合、实现。
同步不会重新生成 bitstream 或测试结果；旧验证日志不代表同步后的版本已经通过。
