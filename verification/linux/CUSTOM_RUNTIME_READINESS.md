# Linux QBS/AKV Custom Runtime 就绪度

核查日期：2026-09-22。第 1 至 8 节保留运行前的源码/工件核查范围；
第 9 节补充随后完成的 Linux 用户态 QBS 小计算实测，不混淆两者的证据。

## 1. 结论与范围

- **找到可运行的 QBS arch-v3 QEMU，但没有在已核查实现中找到 AKV 指令模拟器。**
  当前可以选择 system-mode QEMU，在 guest Linux 内执行标量、RVV 和 QBS 原生指令。
  不能据此声称同一个模拟器能执行原生 QBS+AKV，也不能把 AKV 软件执行器称作 AKV custom 支持。
- 默认路径有版本陷阱：原仓库的 QBS QEMU 是 arch-v1；llama 平台另有 arch-v2；
  可用 arch-v3 在 `ara_dsa_qbs_adaptive`。这些二进制都显示 QEMU 10.2.0，
  仅看 `--version` 无法选择正确的扩展 ABI。
- `verification/out/linux-userspace-20260922/qemu-checked-vlen1024/stage_result.json`
  是已有通用 Linux/RVV smoke 的证据；QBS/AKV query 都 SIGILL，
  `CUSTOM_COMPUTE=NOT_VALIDATED`。本次没有将它升级为 custom compute PASS。
- 当前 ABI 生成物一致，但仍有 QEMU/RTL 边界行为差异；隐藏上下文的 OS 所有权也未解决。
  **完整 Linux llama.cpp 原生 QBS+AKV、跨进程隔离、RTL/板卡 Linux 均未就绪。**
- 本任务只新增本报告及 `verification/out/custom-runtime-readiness-20260922/` 构建产物。
  外部工具、平台软链接、llama 源码和 capture 仅只读核查；没有修改它们。
  没有运行模型、QEMU guest、RTL 仿真、综合或板卡程序。
  SoC 的实际 OS/MMU 配置和内核使能由主线程核查，本报告不重复签核。

下文路径缩写均精确定义如下；相对路径默认相对于 `R`：

```text
R = /home/wangwy/openproject/ara_dsa_verification
A = /home/wangwy/openproject/ara_dsa
D = /home/wangwy/openproject/ara_dsa_qbs_adaptive
L = /home/wangwy/llama/llama.cpp
P = /home/wangwy/llama/platforms/cva6-qemu
S = /home/wangwy/openproject/cva6/cva6-sdk
C = /home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m
O = R/verification/out/custom-runtime-readiness-20260922
```

## 2. 修订与实际 QEMU 清单

`R` 的 HEAD 为 `1b5ada7067af7f8944edebdc37fa69b40951e80b`，worktree 已有其他任务修改，
包括 dispatcher；本报告检查工作文件，不把 HEAD 当作所有文件的精确快照。
`D` 的 HEAD 为 `361637bb3af90cd19f88aba3b465b9668268bddf`；其已构建 QEMU 是
release tarball 加补丁，并非该 Git revision 本身。`L` 的 HEAD 为
`8ed9403e37f1ceb43c6279cdefef01354eac6fd3`，`akv.cpp` 另有未提交修改。

检查了仓库脚本/文档引用的构建目录、SDK、llama 平台、其 CMake 引用的 `D` 和历史 `/tmp` 路径，
没有进行全机器无限范围搜索。下表七个二进制均存在，且本次 `--version` 返回 10.2.0、exit 0；
扩展版本据各自配套 `target/riscv/Xaraqbs.decode`、`qbs_abi.h`、helper 和配置辨认，
**本次没有重新执行 guest 能力查询或指令契约测试**。

| ID | 二进制精确路径 | 配套源码/扩展 | Linux-user / system-mode |
| --- | --- | --- | --- |
| Q0 | `S/buildroot/output/host/bin/qemu-system-riscv64` | `S/buildroot/output/build/host-qemu-10.2.0`；无 QBS/AKV | 未构建 / `riscv64-softmmu` |
| Q1 | `A/verification/qbs/qemu/build/qemu-10.2.0-build/qemu-system-riscv64` | 同级 `qemu-10.2.0`；QBS arch=1, desc=1, M<=4 | 未构建 / `riscv64-softmmu` |
| Q2 | `P/build/qemu-10.2.0-build/qemu-system-riscv64` | `P/build/qemu-10.2.0`；QBS arch=2, desc=2, M<=4，有 activation context | 未构建 / `riscv64-softmmu` |
| Q3 | `D/verification/qbs/qemu/build/qemu-10.2.0-build/qemu-system-riscv64` | 同级 `qemu-10.2.0`；QBS arch=3, desc=2, M<=8，当前首选候选 | 未构建 / `riscv64-softmmu` |
| Q4 | `P/build/qemu-qbs-10.2.0-build/qemu-system-riscv64` | `P/build/qemu-qbs-10.2.0-src`；旧 QBS arch=1, desc=1, M<=4 | 未构建 / `riscv64-softmmu` |
| Q5 | `P/build/qemu-repro-test/qemu-10.2.0-build/qemu-system-riscv64` | 同根 `qemu-10.2.0`；旧 QBS arch=1, desc=1, M<=4 | 未构建 / `riscv64-softmmu` |
| Q6 | `P/build/qemu-repro-test-v2/qemu-10.2.0-build/qemu-system-riscv64` | 同根 `qemu-10.2.0`；旧 QBS arch=1, desc=1, M<=4；目录的 v2 不是 ABI v2 | 未构建 / `riscv64-softmmu` |

这些源码的 `target/riscv` 未找到 AKV 实现；Q1-Q6 的 custom decoder 只有 `qbinfo/qbexec`。
Q3 的 `qbs_abi.h` 和 `qbs_ref.c` 与 R 当前文件 SHA-256 相同，见第 8 节。

不可用/不能混淆的入口：

- `R/verification/qbs/qemu/build/` 当前不存在。脚本默认路径不等于已有可执行工具。
- `hardware/docs/qbs_akv_portability_work.md:142` 和
  `verification/akv/run_portability_stage2.py:19` 引用的
  `/tmp/qbs-current-qemu-20260907/qemu-10.2.0-build/qemu-system-riscv64`
  **当前不存在**；目录只剩部分空子目录，不能复用其历史 PASS 作为当前可运行证明。
- `P/src -> L`，`P/sdk -> S`，`P/tools -> S/buildroot/output/host`。
  因而 `P/tools/bin/qemu-system-riscv64` 是通用 Q0，不是 Q3。
- 当前 PATH 未找到 `qemu-riscv64` 或 `qemu-system-riscv64`，须用完整路径。
  已查构建没有 `qemu-riscv64`；不能以 system-mode 中的 Linux userspace 执行，
  推论已支持 host 上直接运行 ELF 的 linux-user 模式。
- `verification/qbs/qemu/build_qemu_xaraqbs.sh:57` 明确只配
  `--target-list=riscv64-softmmu --disable-linux-user`。补丁 helper 无条件调用
  `riscv_cpu_do_transaction_failed()` 等 system MMU 接口，而 QEMU `cpu.h` 将该声明
  放在 `!CONFIG_USER_ONLY` 中；linux-user 不是只改 target-list 就已验证的交付物。
  本次不改模拟器源码、不尝试移植 linux-user。

当前补丁基于 QEMU release **10.2.0**，构建脚本固定上游 tarball SHA-256 为
`9e30ad1b8b9f7b4463001582d1ab297f39cfccea5d08540c0ca6d6672785883a`。
本次未重新下载或重建 QEMU；补丁及二进制哈希比版本字符串更能区分这些实现。

## 3. Firmware、Linux App 与 llama 调用路径

### 启动与用户态 ABI

已有 Q0 smoke 的组合是 `-machine virt -smp 1 -m 512M`，CPU：
`rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true`；固件
`S/install64_qemu/fw_dynamic.bin`，内核
`R/hardware/fpga/ara_dsa_vcu118/linux/artifacts/Image`，initramfs
`R/verification/out/linux-userspace-20260922/payload-checked/initramfs.cpio`。
已有日志记录 OpenSBI 1.7、Linux 6.19.6，exit 0。命令、输入哈希和耗时在原 `stage_result.json`。
Q3 候选使用相同 virt 启动接口，另加 `xaraqbs=true`；该属性默认 false，且要求 Zve32f。
这是可用于下一步测试的配置，不是已经重新测过的组合。

OpenSBI 提供 guest 启动/SBI 环境，**不会代替缺失的 AKV decoder**。
不要将 VCU118 的 `fw_jump.elf`/嵌入式板卡 DTB 当作 QEMU virt 固件。
custom 调用是 U-mode 直接发 `0x5b` 指令，不是 SBI ecall、Linux syscall 或已存在的 ioctl 驱动 ABI。

Linux 新 payload 应是 RV64 little-endian、LP64D、16 字节调用栈对齐的普通 Linux ELF。
本次工具为 `S/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-gcc`，GCC **14.3.0**。
共享 native kernel 编译 ISA 为 `rv64gcv_zfh_zvfh`；custom 用 `.word` 编码，
ELF 的标准 ISA attribute 本身不宣告 custom 可用，也不能代替 trap-safe capability probe。
query 前先执行普通 `vsetvli` 使 Linux 建立向量状态，计算入口还需合法 FP/vector 状态和 `vstart=0`。
新 Linux harness 使用 libc、普通虚拟指针、对齐分配，不碰 M-mode CSR、固定物理地址或 SoC MMIO 计数器。

已有真实数据 app 并不是可直接 exec 的 Linux payload：

- `apps/llama_qwen25_small_qbs_akv/main.c` 依次 include QBS benchmark 与
  `apps/llama_q4km_operator/main.c`；它是两个捕获算子的顺序 replay，
  **不是 QBS 输出直接作为 AKV 输入的端到端依赖链，也不是完整模型**。
- `apps/common/runtime.h` 含 `mstatus`、硬件计数 MMIO；原 app 还依赖裸机启动、链接和 printf。
  `verification/fpga/reports/qbs-akv-readelf.txt` 显示板卡
  `hardware/fpga/ara_dsa_vcu118/software/qwen_small_combined/qbs_akv.elf`
  入口为 `0x80000000`，没有 Linux 运行时契约。ELF 标头的 `UNIX - System V` 不证明可在 Linux exec。
- 不应通过给原 app 定义 `SPIKE` 来伪装 Linux 移植；共享 AKV native 代码在 `SPIKE` 下被禁用。
  应新建独立 Linux harness，直接链接未改动的 `software/qbs`、`software/akv` helpers。
  不使用 app wrapper 定义的 `AKV_BENCH_HW_COUNTERS` 或 `HW_CNT_PHASE`。

### llama 的原生和软件路径

`L/ggml/src/ggml-cpu/CMakeLists.txt:451` 起将 R/D 形式的共享 runtime 源文件直接加入
GGML；`arch/riscv/qbs.cpp` 原生执行调用 `qbs_native_execute_command()`，
`arch/riscv/akv.cpp:677` 起在软件 callback 和 `akv_attention_execute_v2_native()` 之间选路。

`hardware/scripts/akv/run-qemu-combined-model-check.sh` 只转发给
`run-qemu-model-check.sh`。其 guest init
`hardware/scripts/akv/akv-token-init.c:494` 明确设置 `GGML_RISCV_AKV_EMULATE=1`。
因此日志中的 `QBS_AKV_V2` / `GGML_RISCV_AKV_EXEC` 不证明执行过 AKV opcode。
`akv.cpp` 的软件 executor 直接做 dot/softmax/PV；其 F16 Value 累加舍入和独立 F32 oracle
也不相同，不能把任一 oracle 宣称为 native bit-exact 或硬件时序模型。

实际存在的 `L/build-rv64-cva6-qbs-arch3-current/bin/llama-simple` 和
`L/build-rv64-cva6-akv-static/bin/llama-simple` 均为静态 Linux RISC-V ELF。
两者 `CMakeCache.txt` 都启用 QBS、AKV、RVV、Zfh、Zvfh，但 runtime 路径指向
`D/software/qbs`、`D/software/akv`，**不是 R 的本次构建**。
`L/ggml/src/ggml-cpu/arch/riscv/akv.cpp` 有未提交的 mask/sink/软件累加路径修改；
不能用单个 Git HEAD 保证现有 ELF 与当前源文件一致。本次仅记录文件哈希，未运行它们。

原生启用需要受控能力探测；`qbs_native_info()` / `akv_native_info()` 本身不捕获 SIGILL。
`GGML_RISCV_*_EMULATE=1` 是软件模式，不是发现处理器支持的机制。
`software/qbs/src/qbs_runtime.c:135` 严格要求 arch=3、desc=2、匹配的数值/容量契约，
不能因只使用 M1 就令当前 runtime 接受 arch-v1/v2。
保留正常 RVV fallback；一旦 native 执行已经部分修改输出或状态，不应透明重算来掩盖故障。

## 4. 当前指令与布局契约

权威配置是 `config/qbs_abi.json`、`config/akv_abi.json`；生成
`apps/common/*_abi.h`、`software/*/include/*/*_abi.h` 与 `hardware/include/{qbs,akv}_pkg.sv`。
本次两个生成器的 `--check` 均通过，两个 C header 副本逐字节哈希相同。
dispatcher 核查点：`hardware/src/ara_dispatcher.sv:4816` 起。

| 指令 | funct3 / funct7 | 寄存器与效果 |
| --- | --- | --- |
| `qbinfo` | 1 / 0 | rs1=query index, rs2=x0, rd=整数结果；`a0` 版本 `0x0005155b` |
| `qbexec` | 0 / M-1 | funct7[6:3]=0；rs1=descriptor VA，rs2=activation VA，rd=向量组；M1/v8 为 `0x00b5045b`，M8/v8 为 `0x0eb5045b` |
| AKV FULL/REFILL | 2 / 0 或 1 | rd=x0；FULL rs1=descriptor，rs2=tile_start；REFILL rs1=x0，rs2=tile_start |
| AKV row load | 3 / D code | rs1=selector，rs2=x0，rd=向量组；D64/128/96 code 分别 0/1/2 |
| `akvinfo` | 4 / 0 | rs1=index，rs2=x0，rd=整数；`0x0005455b` |
| AKV release | 5 / 0 | rd/rs1/rs2 均 x0；`0x0000505b` |
| AKV-v2 FULL/REFILL | 6 / 0 或 1 | FULL `0x00b5605b`；共享 helper 的 REFILL `0x02a0605b` |
| AKV-v2 K column/panel4 | 7 / 0 或 1 | rs1=column selector，rs2=x0，rd=向量；单列 v8 `0x0005745b`，panel4 v8 `0x0205745b` |

全部使用 custom-2 opcode **0x5b**，不是互不相关的 opcode 空间。
Q3 只覆盖表的前两行；不能用 `xaraqbs=true` 打开 AKV 的 funct3=2..7。

**QBS：** arch=3，numerical=1 固定 RNE、非动态 frm；descriptor=2，16 字节且地址须 16 字节对齐。
`qbs_descriptor_t` 是带 `aligned(16)` 的 `uint64_t header, weight_base` 结构；
普通类型对象已有该对齐，外部 blob/指针强转仍须核对实际地址。
header `[3:0]` version、`[7:4]` weight profile、`[11:8]` activation profile、
`[15:12]` weight layout、`[19:16]` activation layout、`[24:20]` N-1、
`[32:25]` K_blocks-1、`[34:33]` activation access、`[38:35]` context ID、
`[46:39]` generation；`[63:47]` 保留为零。

Q2_K/Q3_K/Q4_K/Q5_K/Q6_K 配 Q8_K；Q4_0/Q5_0/Q8_0/IQ4_NL 配 Q8_0。
K-quant 每块 256 元素，Q4_K 为 144 字节，Q8_K 为 292 字节；
非 K 的这些 profile 每块 32 元素，Q8_0 为 34 字节。不能统一以 256 计算所有 profile 的 K_blocks。
weight 对齐 2 字节，DIRECT/FILL activation 对齐 4 字节。

weight layout 1=ROW_MAJOR，2=R4_BLOCK_MAJOR；R4 是
`[row_group][k_block][row_in_group][完整量化 block]`，N 向上补齐到 4 行。
它不是 app 的 RVV x32 字段重排格式，也不是 GGML 任意重排 weight。
activation layout 1=ROW_MAJOR，2=M4_INTERLEAVED（仅 M=4），3=M8_INTERLEAVED（必须 M=5..8）。
M8 始终存八行，未使用行清零，不能把 M 行 row-major 直接改标签。
M<=4 时 N<=min(32,VLEN/32)；M>=5 时 N<=16；总结果<=128，K_blocks<=256。
向量组寄存器数为 1/2/4/8，按组对齐；M3 不覆盖第四个寄存器；
M1..4 输出尾清零，M5..8 仅更新 active N、保留其他元素。

activation context 只有一个，限 M1/Q8_K/ROW_MAJOR/K_blocks<=16，generation 为 8 位。
DIRECT 不使用缓存；FILL 成功后发布快照；REUSE 不重新读 activation；
RELEASE **仍执行计算，成功提交后失效**，不是独立 OS flush。
QEMU 整条 helper 完成后更新向量结果及 fflags；RTL 是 drain、blocking command、terminal response 的合同，
不能用 QEMU wall time 推导其队列或执行周期。

**AKV：** 基础 arch=1、descriptor=1；v2 是 query index=2/3 的 token-axis profile，
不是把 descriptor.version 改成 2。descriptor 为 64 字节/64 字节对齐：
offset 0..3 为 version/format/q_rows/flags，4/6 为 u16 head_dim/kv_length，
8/12/16 为 u32 Q/K/V stride，20 为 reserved，24/32/40 为 u64 Q/K/V base，48/56 保留。
输入 F16；capture 的 F32 query 须按既有 helper/adapter 转为 F16，不能直接作为 Q payload。

v1 tile=8、D64/128；v2 tile=64、q_rows=1..8、D64/96/128，payload base/stride 须 32 字节对齐。
D96 用 D128 物理槽并保持 D-axis tail；D256 是两段 D128 合同，不是直接 D256 row-load 编码，
现有 GGML production selector 仍不接纳 D256。
row selector 是 `stream | index<<2`，stream Q/K/V=0/1/2，v1 index 3 位、v2 6 位；
column selector 的 bit7 为 segment，低 7 位 dimension。
panel4 要求列和 vd 四对齐、query capability bit40；不能用四列命令替代任意不对齐单列。
当前 dispatcher 的 AKV 实现条件是 `AkvEnable && NrLanes==4 && VLEN==1024`，v2 还须 `AkvV2Enable`。
这只是 custom 实现的静态约束，不是本报告对实际 SoC 参数的确认。

AKV 原生命令提供 Q/K/V 填充和 row/column 访问，**注意力乘加、softmax、输出仍是普通 RVV**。
“真实 AKV custom 工作”至少须观察 FULL + column/row load + release 与正确输出，不能只计 query。

## 5. 已发现的不兼容及验证边界

| 项目 | 源码/工件证据 | 影响与处置 |
| --- | --- | --- |
| 旧 QBS arch/descriptor | Q1/Q4/Q5/Q6 是 1/1；Q2 是 2/2；R 为 3/2 | 当前 runtime 拒绝；不要手改 descriptor.version 或 capability 校验掩盖不匹配 |
| M 字段宽度 | 旧 `Xaraqbs.decode` 的 `%m 25:2`，Q3/R 为 `25:3` | M5..8 在旧 QEMU 非法；R 的 M8_INTERLEAVED、窄 N/tail 合同也不能由旧 M4 模型验证 |
| AKV 缺失 | Q0-Q6 无 AKV helper/decoder；组合 init 设置 EMULATE | AKV query/fill/load 不能原生执行；添加 query 返回值仍不是计算支持 |
| REUSE/RELEASE 的 rs2 对齐 | `ara_dispatcher.sv:4924` 对所有 qbexec 预检 rs2[1:0]；`qbs_ref.c:389` 和 descriptor decoder 仅 DIRECT/FILL 检查；Q3 helper 走后者 | 即使 REUSE 不读取 rs2，传入未对齐占位地址也可能 QEMU 接受、RTL 拒绝；先用保留的合法对齐 activation 指针。此差异是静态发现，未做新 DUT 测试 |
| 地址检查优先级 | dispatcher 在 descriptor 读取前预检 activation 对齐；Q3 helper 在读完 descriptor 后才调 validator | “descriptor 无法访问且 activation 未对齐”可能得到不同异常优先级；单独的成功计算 smoke 不能闭合此边界 |
| query 与 vstart | `ara_dispatcher.sv:5850` 起成功的非 SYSTEM 指令清 vstart；Q3 `trans_qbinfo` / `helper_qbs_info` 不写 vstart | 非零 vstart 下 query 的架构副作用不同；正常 smoke 先设为 0，不把 query 宣称为状态不变。须独立契约测试裁定 |
| RAM/MMIO/PMA | Q3 `qbs_helper.c:41` 全范围 RAM probe，`208` 起先检查 payload 再复制 | 是保守功能模型，不等同 Ara PMA、AXI、页故障重启或硬件取数时序；QEMU 成功不证明 RTL/板卡权限与原子提交 |
| 布局误接 | QBS R4 vs x32；AKV F32 Q vs F16 Q、物理 KV=256 vs active KV=16 | 沿用真实 metadata 和共享 pack/conversion helper，不凭相同字节数或 tensor 名直接转型 |
| 软件版本误配 | 既有 llama CMake 指向 D，akv.cpp 工作文件非干净 HEAD | 后续产物必须记录 runtime 路径、源码哈希、ISA 和 ELF 哈希；本次只构建 R 的共享库 |

以上不包含主线程的 OS/MMU 配置结论，也不宣称静态差异已经获得周期级 root-cause 证据。
如需诊断 RTL，遵守 AGENTS：先针对具体差异列假设、异常/提交信号和期望，再安排一次有界、可区分的测试。

## 6. 本次隔离构建结果

没有为了编译而修改任何 runtime、原 app、llama 或硬件文件。
`python3 scripts/gen_qbs_abi.py --check`、`python3 scripts/gen_akv_abi.py --check` 均 exit 0。
两套共享库均交叉编译成功；没有启用 tests/examples，没有执行 RISC-V 产物。
构建配方如下，输出均在 O，不会覆盖外部 build 或 install：

```bash
cd /home/wangwy/openproject/ara_dsa_verification
OUT=verification/out/custom-runtime-readiness-20260922
CC=/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-gcc
CFLAGS='-march=rv64gcv_zfh_zvfh -mabi=lp64d -fno-fast-math -ffp-contract=off'
cmake -S software/qbs -B "$OUT/qbs-linux" \
  -DCMAKE_SYSTEM_NAME=Linux -DCMAKE_SYSTEM_PROCESSOR=riscv64 \
  -DCMAKE_C_COMPILER="$CC" -DCMAKE_C_FLAGS="$CFLAGS" \
  -DCMAKE_BUILD_TYPE=Release -DQBS_BUILD_TESTS=OFF -DQBS_BUILD_EXAMPLES=OFF
cmake --build "$OUT/qbs-linux" -j2
cmake -S software/akv -B "$OUT/akv-linux" \
  -DCMAKE_SYSTEM_NAME=Linux -DCMAKE_SYSTEM_PROCESSOR=riscv64 \
  -DCMAKE_C_COMPILER="$CC" -DCMAKE_ASM_COMPILER="$CC" \
  -DCMAKE_C_FLAGS="$CFLAGS" \
  '-DCMAKE_ASM_FLAGS=-march=rv64gcv_zfh_zvfh -mabi=lp64d' \
  -DCMAKE_BUILD_TYPE=Release -DAKV_BUILD_NATIVE_KERNEL=ON -DAKV_BUILD_TESTS=OFF
cmake --build "$OUT/akv-linux" -j2
```

输出 `O/qbs-linux/libqbs_runtime.a` 和 `O/akv-linux/libakv_runtime.a`。
`readelf -hA` 核对 native QBS C object 及 AKV-v2 assembly object 为 ELF64 little-endian、
RISC-V REL、RVC/double-float ABI，ISA 包含 V1.0/Zfh/Zvfh。
`objdump -d` 还确认 archive 内有 QBS query/M1/M8 及 AKV query/FULL/REFILL/column/release
的实际机器码，没有落入禁用 native 的 stub；静态反汇编不能证明这些指令已经执行。
这是 **archive 编译成功**，还不是完整 Linux smoke ELF 的链接、运行或 OS 隔离证明。
生成的 CMakeCache、flags.make、link.txt 保留详细编译参数；哈希见下节。

## 7. 一个最小真实数据 Linux Compute Smoke 方案

### 输入与复用边界

新增独立 `custom_real_smoke` Linux ELF，不改原 app，不加载 GGUF、不跑 tokenizer/模型图生成。
同一 ELF 的两段 leaf replay 复用既有 Qwen 捕获；测试报告明确它们不是数据依赖链。
所有裁剪/复制/打包只写新的 `R/verification/out/<独立run-id>/`，不在原 app 目录运行会写
`generated/` 的 generator，不覆盖现有 cpio。原 capture 多处有 hardlink，不原地重排。

**QBS 段：** 依据 `apps/llama_qwen25_shape_decode_n32_qbs/case.json`：
`C/decode/operators/blk_0_attn_q_weight/{weight_q4_K,activation_f32,output_f32}.bin`。
保留 K=1536、M=1；裁前 32 个 weight/output 行。
输入 activation 6144 字节；Q4_K weight 从 1327104 字节裁为 **27648** 字节；golden 128 字节。
量化后 activation 为 6 个 Q8_K block，即 **1752** 字节，输出 32 个 F32。

复用 `apps/llama_q4km_micro/micro_kernels.c` 的 `q4km_quantize_row_q8_K()` 和
`q4km_vec_dot_q4_K_q8_K()`，即现有 `repack_kernels.c`/benchmark 包含的公共实现，
不 include 带 main/裸机运行时的 benchmark。
R4 重排调用 `software/qbs/src/qbs_runtime.c` 的 `qbs_repack_weight_r4()`，
指令执行调用 `qbs_native_execute_command()`，与 GGML 同源。
用 `qbs_device_query()` 校验实际设备、profile/shape，再构造显式对齐 descriptor；
首个 smoke 只用 DIRECT，禁用 activation context 生命周期优化。

**AKV 段：** 依据 `C/replay/cases/operator/decode/attention_core/case.json`，真实 blob 在
`C/decode/block/{attn_q_input-0,attn_k_input-0,attn_v_input-0,attn_mask_input-0,kqv_out-0}.bin`。
Q metadata `[128,1,12,1]` F32，K/V `[128,256,2,1]` F16，mask `[256,1,1,1]` F16。
本次只读检查 mask：前 **16** 个 `0x0000`，余下 **240** 个 `0xfc00`；所以
query_tokens=1、physical_KV=256、active_KV=16 是三个不同维度。

仅选 KV head0 对应 Q head0..5，保持 D128/GQA6，scale=0.08838834764831843。
Q F32=3072 字节，转换后 F16=1536；K/V 各取前 16 行、各 4096 字节；mask=32 字节；
golden 前六头=3072 字节。base 64 字节对齐、Q/K/V row stride=256，output stride=512。
Q 转换沿用现有 F32->F16 RNE 路径，不合成随机 payload，不把 K/V 转置成软件 tile 格式。
调用 `akv_attention_plan_create_v2()` 和 `akv_attention_execute_v2_native()`；
共享的 `software/akv/src/akv_v2_native_riscv.c`、`akv_v2_attention_rvv.S` 同时用于 app/GGML。
此输入仅有一块 v2 tile，足以测 FULL、K column、V row、release，**不覆盖 REFILL**。

### 执行与判定

1. 新 harness 用 Linux libc 分配/读取输入，先核对 metadata、输入哈希和裁剪尺寸；
   标量检查、普通 RVV load/store 与真实 QBS RVV baseline 必须先通过。
   复用 `verification/linux/userspace/custom_caps.c` 的子进程 trap-safe 探测模式，
   把 RAW capability 解码为版本/profile 检查；query 子进程不算计算证据。
2. 在一个专用 guest、单 hart、单线程、没有其他 custom 调用者的条件下，Q3 执行 QBS DIRECT。
   实际执行返回后检查 output 哨兵被替换、前后 guard 未改变，逐项对照
   `verification/qbs/qbs_ref.c` 使用同一量化输入的结果及捕获 golden。
   QBS golden 门限沿用 app `atol=0.002, rtol=0.002`，非有限值直接失败；
   精确契约参考与捕获 golden 的数值门限是两个不同检查，不互相替代。
   记录 native 调用路径及成功返回；QEMU 阶段保留一次 `helper_qbs_exec` 命中的受限动态证据
   或等价 custom 执行 trace，不能把反汇编或仅翻译的 `in_asm` 日志当作执行次数。
3. AKV 必须实际执行共享 native kernel 并比较六头全部输出；沿用 capture
   `atol=0.004, rtol=0.002`，检查 guard、有限值和 release 后行为。
   独立 F32 oracle 只能辅助定位，不要求与 native F16 累加/exp 逐位相同。
   **在当前 Q0-Q6 上此段预期 UNAVAILABLE，不能报告组合 PASS。**
   需将来补齐且审查过 AKV ISA 模型，或由主线程提供符合 OS 合同的硬件环境，才运行此段。
4. 同一 harness 的控制模式明确禁用 custom：只执行普通 RVV baseline；
   另以 Q3 `xaraqbs=false` 检查 query/SIGILL 和 fallback 分类。
   `--require-qbs` / `--require-akv` 模式中缺失能力必须返回非零/明确未通过，不能用 oracle 顶替。
   marker 应分别包含 `QBS_NATIVE_COMPUTE`、`AKV_NATIVE_COMPUTE`、`RVV_FALLBACK`，
   不以 `query_ok` 或泛化的 `EXEC` 计数作为成功依据。
5. 新 rootfs 复用已修复 `/lib64 -> lib` 的 userspace builder 打包逻辑，只加新 ELF 和少量数据。
   通过 `verification/linux/run_stage.py --stage qemu` 保存命令、console、退出码与工件哈希；
   采用第 3 节 virt/firmware/kernel 组合，初始预算可沿用 180 秒短 smoke 上限。
   超时即保留证据分析，不循环改超时或参数试跑。

这里给出的是**待实现/待运行方案**。现有 `run_userspace_qemu.py` 的 marker 和
`CUSTOM_COMPUTE=NOT_VALIDATED` 没有被本报告改造成 compute 签核入口。
QEMU 的 native 表示真实发出 custom opcode、由模拟器执行，始终不是 RTL 测量。

### OS 隔离的后续门槛

上述专用 guest 只是单调用者计算环境，不是多任务安全部署。
QBS `CPUArchState.qbs_activation_context` 是 per-hart，AKV RTL Q/K/V context 也不在 VRF 内；
普通 Linux vector save/restore 不保存这些状态。GGML 的 process-local mutex、CPU affinity
都不能排除另一个进程或信号处理器使用同一 hart 的 custom 上下文。

OS 合同须明确上下文所有权、切换/迁移时的失效重建或保存恢复、未授权指令访问和故障清理。
仅加一个 ioctl mutex 而仍允许任意 U-mode 发指令，也不构成隔离；QBS RELEASE 不能充当独立 flush。
合同确定后，再安排双进程 A/B 不同真实 payload、强制切换、signal/fault return、fork/exec/迁移、
stale generation、AKV release 后访问的独立测试；不能以本报告的单进程 smoke 代替。
QEMU 源码还未将新增 QBS context 纳入 `target/riscv/machine.c` 的 VMState，
也不能假定 savevm/migration 能透明保存它。

## 8. 精确指纹

以下为本次读取/构建得到的 SHA-256。运行前须重新核对，尤其是可被其他任务复用的外部 build。

```text
Q0 db380f3173b3383bf0d8a92108974060ac0d5004e54f92fc87f9b52d1e077c54
Q1 50df16d5af4ffce971c8657fa525ef18ef6e0dcf3b944358f6a7e8002859ba55
Q2 9d169e77ca41001943053bf5ce8b893dd900dc9b17612286667afa6e04d436ef
Q3 5c586c418708712e5ad1bf377ff9c2f89b3114e2e1178e0aa25b7f053b156068
Q4 92139aed5db14ac43d95c3825e8697e3fcd3f56244ad020820f38b970b2b18c9
Q5 f1ee7e843ec1e872aa110a9b207fbe9016fb7a2cb1d74fd1359f51fadd69de50
Q6 5669718197971409a164ba87e0c39200146598e52bd5ae5746947e91baf55894

R/verification/qbs/qemu/qemu-10.2.0-xaraqbs.patch
69cf7f3b7d57ea02ca0c71ca15da81d04400516d42f808592db1810aa0bf4f53
R/apps/common/qbs_abi.h = R/software/qbs/include/qbs/qbs_abi.h = Q3源码/target/riscv/qbs_abi.h
86fb8f1b48ad1ba23d0af07307285f323282ead735354f002db8f5b1d0707015
R/verification/qbs/qbs_ref.c = Q3源码/target/riscv/qbs_ref.c
b694b0e2be20b1bada5388cbf4d23d43c401d67cef827024a5be4966f7fa08fe
Q3源码/target/riscv/qbs_helper.c
5ed80e3807f078b75be6c89dc2825af8268fbe04d581fe4623d450b2fcc2c2fd
R/apps/common/akv_abi.h = R/software/akv/include/akv/akv_abi.h
59ae7775780d7a4cf41fa2ae4d445133dda27a11b467cfe25a0db86d353c7e1f
R/hardware/src/ara_dispatcher.sv
59afd489ac2775f5119a70f080c1a53ef6774599f3dd1f8ee0c18577d8080d96
R/hardware/src/vlsu/qbs/qbs_descriptor_decoder.sv
54e1496ca93bb7ccc3949038a0329c9e9d7843de5b9ebdcba7be63b011a4569b

L/ggml/src/ggml-cpu/arch/riscv/qbs.cpp
1dd783c8e1278b95f3006486cc8859874479967da63392956769337b3dac21e7
L/ggml/src/ggml-cpu/arch/riscv/akv.cpp (含未提交修改)
495dfe1e88a03974d64ed17780e4597f13bcd5ec13411810a435aeedfda53c61
L/build-rv64-cva6-qbs-arch3-current/bin/llama-simple
863d0204cfe52aa56e3405968b4b8c024ba4eb1759c985d43c5c9ac4554215a4
L/build-rv64-cva6-akv-static/bin/llama-simple
2f487dc9fe88a57345cffd61dc2774dd9e87da80f927be886c52df46634d16a0
O/qbs-linux/libqbs_runtime.a
792d66eae21b48d869ccbc6bfe95956d440a32842eeafc55ae8b5516fab8483d
O/akv-linux/libakv_runtime.a
ebe4d199a740e0f7ed403f8d0bdb439190dfbb63339baa53c3aadc0f2bcaa754
```

真实数据原始文件指纹（不是裁剪后的指纹）：

```text
C/decode/operators/blk_0_attn_q_weight/weight_q4_K.bin
f578b25b8fe8ce69119c2dfd157ed1a98021d699fd6d678a1f8d6aeec4029825
C/decode/operators/blk_0_attn_q_weight/activation_f32.bin
c053e6e62ba859c90be074c06c449fdc21117beb407e1afc864313cee39044f1
C/decode/operators/blk_0_attn_q_weight/output_f32.bin
796b1dd56a51e4ff907b36c8f1f053126789f570920f093660720bb6a14684b3
C/decode/block/attn_q_input-0.bin
497e309560d6f3a107529e530e3994a75d880169abf1a75193fcdbe3dd3a1267
C/decode/block/attn_k_input-0.bin
4658738198a7b962109cca5bd2456ebd14faf1d8de5bf581a3690d7b55e65d65
C/decode/block/attn_v_input-0.bin
1cc1636b8783ebdfdb62fa293cd62e2a55b1380b296586f26dc129a26b3185aa
C/decode/block/attn_mask_input-0.bin
ae9ec3a8e0b1763fc7f4dd05a25603ca3326479dcfb5dfc589fa7f228ea6b48b
C/decode/block/kqv_out-0.bin
91744f0fbce1f37ae746e047c6bb2118b82b69797619622bfe6987a75b9cf1e6
```

capture 的 `model.json` 没有 `llama_commit`；既有
`hardware/fpga/ara_dsa_vcu118/software/qwen_small/qbs_provenance.json` 也记录
`capture_llama_commit=unknown`。不能拿当前 L HEAD 倒填捕获时 revision。
这些数据可用于有明确文件指纹的最小 replay；工业追溯仍需补齐原始模型/capture 生成修订记录。

## 9. 后续 Linux 用户态 QBS 小计算实测

独立目录 `verification/out/linux-qbs-native-20260922/attempt-02/` 已完成三项
有界测试。输入是上述真实 Qwen2.5-1.5B Q4_K `blk.0.attn_q.weight` 的前 32 行，
`M=1,N=32,K=1536`。权重 27648 字节、F32 activation 6144 字节、Q8_K activation
1752 字节，golden 为冻结的 GGML 输出前 32 个 F32。没有运行完整模型。

| 路径 | 动态证据 | 结果 | 主机耗时 |
|---|---|---|---:|
| Q3 原生 opcode，要求 QBS | 23 次 info helper、1 次 exec helper、成功返回、32/32 输出比较 | PASS | 8.64 s |
| 扩展存在，强制 RVV | 0 次 custom helper，RVV 与冻结 golden 一致 | PASS | 8.74 s |
| 扩展关闭 | capability SIGILL；auto 回退成功；要求 QBS 返回 77 | PASS，native 未执行 | 8.99 s |

这里的“原生 opcode”是 guest 执行实际 `qbinfo/qbexec`，由 QEMU helper 模拟，
不是在 guest 偷换为 QBS 软件执行器，更不是实际 RTL 执行。GDB helper-entry 计数
只证明进入 helper；还须结合 guest 返回、输出逐元素比对、输入未改和 8/8 guard
完整才能接受结果。guard 是缓冲区哨兵，不是页保护证明。

native 对冻结 GGML 输出的最大绝对误差为 `9.68575478e-08`；预先固定的容差为
`0.002 + 0.002*abs(golden)`，没有为通过测试修改容差。guest 的 RVV quantizer
输出与独立主机 quantizer 的 1752 字节逐字节相同。输出 oracle 不链接 QEMU 的
`qbs_ref.c`。数值比较、能力/ABI、输入指纹、拒绝路径与捕获完整性分别检查。

首轮日志保留在根目录：harness 把 planner 的 M/K 上限错当成已发出命令的尺寸，
在执行 `qbexec` 前退出。静态核对 `qbs_plan_next` 后修正 checker，并新增对应的
主机回归；没有改 runtime、RTL、QEMU、shape 或 timeout。最终通过结果是
`attempt-02/summary.json`，不能误读根目录的失败 summary。

运行前计划：[qbs_NATIVE_PLAN.md](qbs_NATIVE_PLAN.md)。入口为 `qbs_build.py`、
`qbs_run.py`，支持独立 `--attempt`，已有目录拒绝覆盖；12 项 host 测试检查
plan 语义、哈希、量化、输出 oracle、反例拒绝和证据完整性。详细命令、全部输入
哈希、ELF、反汇编与逐元素输出均保存在上述工件目录。

只使用 DIRECT 单次命令，没有 activation context 的 FILL/REUSE/RELEASE。
`OS_CUSTOM_CONTEXT=NOT_VALIDATED`、`AKV_NATIVE_COMPUTE=UNAVAILABLE` 保持不变。
此结果不涵盖多进程隔离、任务迁移、原生计算中的 fault/signal 恢复、其他格式、
完整 llama.cpp、RTL/FPGA 或硬件性能。GDB 也会改变主机耗时，不据此报告加速比。
