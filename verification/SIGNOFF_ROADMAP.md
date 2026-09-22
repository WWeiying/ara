# Ara DSA 工业化验证路线与签收门禁

本文定义 `ara_dsa_verification` 的最终验证闭环。目标不是让某一批随机程序通过，而是证明三件事同时成立：

1. 普通 RVV 1.0 架构语义保持正确；
2. QBS/AKV 等专用快速路径在满足契约时正确工作，契约不满足时可靠回退到标准 RVV；
3. CVA6、内存系统、Linux 运行时和 VCU118 板卡上的真实软件可以长期稳定运行。

## 1. UVM 在整套流程中的位置

工业验证通常使用 UVM 建立可复用的 SystemVerilog 验证组件，包括 transaction、driver、monitor、agent、reference model、scoreboard、coverage collector 和 virtual sequence。UVM 解决的是**如何组织可复用的激励和观测**，并不自动提供 RVV 架构真值，也不能代替 Spike 差分、软件自检、形式属性或 Linux 系统测试。

本项目采用分层组合：

| 层 | 本项目的实现 | UVM 的作用 | 通过标准 |
|---|---|---|---|
| RTL 接口级 | VCS testbench、CVA6/CVXIF 请求、commit/vector monitor | 可将请求和完成信号包装成 transaction agent | 握手、顺序、ID、异常行为无违规 |
| 架构差分级 | Spike commit log、vector state/checkpoint、内存签名 | scoreboard 可消费 transaction，但真值仍来自 Spike/参考模型 | 每条可观察标量/向量架构状态一致 |
| 子系统级 | QBS/AKV/VLSU/VRF/lane contract test 和 SVA | virtual sequence 组合边界场景 | 资源仲裁、回退、完成和错误路径正确 |
| 随机级 | riscv-dv RVV1 profile、固定 seed、语义 coverage | UVM sequence 可替代或扩展激励生成 | 覆盖目标达到，失败可重放并定位首错 |
| 系统级 | QEMU、VCS SoC、VCU118 Linux | UVM 只负责启动前后接口观测 | Linux 启动、用户态、上下文切换和长稳态通过 |

因此，本仓库当前的 Python 编排器 + VCS 监视器 + Spike 差分不是 UVM 的替代品，而是已经能够执行的架构差分主线。后续若将 CVXIF/向量后端接口稳定为公开 transaction，加入 UVM agent 可以提升激励复用和回归管理；在此之前，不能把“存在 UVM 类文件”当作验证完成，也不能用 UVM 通过掩盖架构差分缺失。

## 2. 分阶段验证节点

每个节点必须产出机器可读结果。只有状态为 `PASS` 且具有 commit、工具、配置、命令和输入哈希的结果，才允许进入下一节点。`FAIL` 必须保留首错日志和可重放命令；`TIMEOUT` 不得被改写为通过。

### G0：规格、版本与环境冻结

**目的：** 防止“代码、依赖或工具变了但结果仍被当作同一版本”。

执行内容：

- 固定 RTL commit、配置文件、VLEN、lane 数、编译宏和 simulator 命令；
- 用 `Bender.lock` 和 `toolchain.lock.json` 锁定依赖和工具；
- 使用 `verification/setup_worktree.sh`，依赖以 clean detached checkout 快照进入验证 worktree；
- 保存 Git commit、worktree 状态、VCS/Spike/Bender 版本、ELF/网表/bitstream SHA-256；
- 生成测试库存、需求到 suite 的映射和本轮 seed 清单。

门禁：`verify.py doctor` 无 ERROR，禁止 dirty dependency，`verify.py plan` 为 `VALID`。

### G1：静态检查与可编译性

**目的：** 在运行昂贵仿真以前消除结构性错误。

执行内容：

- Verilog/SystemVerilog 语法、参数展开、顶层 elaboration；
- lint、未驱动/多驱动、宽度截断、signed/unsigned、锁存器和时序 always 块检查；
- SVA 编译和基础断言 smoke；
- Bender source manifest 与顶层 filelist 固定；
- 必要时使用 Verilator 做快速结构检查，但 Verilator 结果不作为 VCS 功能签收。

门禁：所有目标配置至少完成一次编译；warning 必须分类，不能把未解释的 warning 计入 PASS。

### G2：模块和子系统契约

**目的：** 先隔离局部逻辑，再进入整核差分。

优先顺序：

1. QBS descriptor/profile/decode/read/compute/commit、SRAM adapter；
2. AKV descriptor/context/view/lifetime、读写和回退路径；
3. VLSU AddrGen、lookup、demand/prefetch 仲裁和返回匹配；
4. vector sequencer、VID 生命周期、lane/VMFPU/MASKU/VRF；
5. CVXIF 请求、ready/valid、异常、flush、reset 和 backpressure。

每个子系统需要：参考模型或等价黄金结果、边界输入、负向输入、断言、至少一个随机化场景、波形/事务日志和综合可编译 smoke。QBS/AKV 的专用契约必须明确“不适用时走 fallback”，不能只测试快速路径。

门禁：接口握手无断言失败；队列无溢出/重复提交/丢失完成；同一输入在 reference 和 RTL 中数值、长度、异常状态一致。

### G3：ISA 1.0 定向差分

**目的：** 保证普通 RVV 不是为了快速路径而被破坏。

覆盖四个 SEW、七个 LMUL、tail/mask policy、vstart、mask、widen/narrow、reduction、segment/indexed/strided/whole-register memory、异常恢复和 vset 状态。每条生成的向量指令至少记录：

- Spike 提交记录；
- RTL 标量提交和 vector backend alloc/write/done 记录；
- `vl/vtype/vstart/vcsr/fcsr` 及向量寄存器状态；
- vector store 后目标内存字节签名；
- 首个不一致的 PC、指令、VID、lane、地址和状态快照。

门禁：定向 suite 全部 `PASS`；需要 vector evidence 的 suite 不接受只比较 `tohost` 的弱证据。

### G4：约束随机与覆盖闭环

**目的：** 从“有随机测试”升级为“随机测试证明覆盖了哪些风险”。

固定 seed 可重放；随机 profile 按 arithmetic、load/store、FP、vtype churn、restart、mixed control 和 integer stress 分组。coverage 至少分解到：

- 指令 opcode/operand form；
- SEW/LMUL/VL/vstart；
- tail/mask policy；
- memory mode、segment 数、对齐/跨 burst；
- 源/目的寄存器重叠类别；
- 异常、flush、backpressure、queue full/empty；
- QBS/AKV 命中、回退、descriptor 非法和资源不足。

覆盖闭环不是简单增加 seed。每个未覆盖 bin 必须归类为“尚未激励、约束排除、硬件不支持、不可观测或规格允许不覆盖”，并由验证计划负责人签字。失败保留最小化 seed 和原始 seed 两份回归。

### G5：QEMU/软件集成

**目的：** 验证编译器、运行时和 ABI 使用方式，不把 QEMU 结果冒充 RTL 结果。

顺序为：

1. 标准 RVV fallback 的 llama.cpp/GGML microkernel；
2. QBS/AKV 指令 ABI、descriptor、profile/layout/shape/lifetime 合同；
3. 多量化格式和 shape 的 reference 数值检查；
4. Qwen2.5/Qwen3 代表性模型的 token generation 和较短 prompt；
5. 未命中快速路径的算子必须自动回退并保持结果正确。

门禁：QEMU 只证明软件契约和 ISA 扩展模拟正确；必须同时保存模型、量化格式、shape、上下文长度、seed、输出 token 和数值误差。

### G6：VCS SoC/Linux

**目的：** 在 FPGA 以前验证完整特权级、MMU、缓存、DDR、异常和用户态。

分三层推进：

| 子阶段 | 内容 | 结果 |
|---|---|---|
| G6.1 | OpenSBI/bootloader/内核启动到 shell 或固定 init marker | boot log marker + payload hash |
| G6.2 | 用户态 RVV fallback、QBS/AKV smoke、非法/回退路径、fork/exec/context switch | 用户程序 PASS + kernel log 无异常 |
| G6.3 | 长时间内存压力、抢占、定时器、中断、文件系统和模型片段 | 固定时长无 hang、无 kernel oops、结果签名一致 |

RTL Linux 不能只看 UART 输出。至少要检查启动阶段、内核版本、DDR 可用性、RVV 用户态执行、快速路径和 fallback 两条路径，并对 Image、DTB、rootfs、应用 ELF 记录哈希。当前仓库中的 `verification/linux/check_boot.py` 是门禁工具；真正的 Linux RTL PASS 需要实际启动日志和用户态 smoke 产物。

### G7：VCU118 板卡 bring-up 与长稳态

**目的：** FPGA 用于扩大时间覆盖和真实软件覆盖，而不是替代仿真中的首错定位。

板卡顺序：

1. bitstream、时钟复位、DDR 校准、UART/JTAG 和版本寄存器；
2. 裸机自检：CSR、timer、interrupt、DDR walking、RVV register/memory signature；
3. OpenSBI、Linux、console、网络/存储或预置 rootfs；
4. 用户态 RVV microkernel、QBS/AKV contract 和 fallback；
5. llama.cpp 代表性 quantization、decode、短 prompt，再到长 prompt/prefill；
6. 多小时稳定性、重复启动、上下文切换、内存压力、温度/频率记录。

每轮板卡测试记录：bitstream SHA、Vivado/Vitis 版本、XDC 时钟、板卡序列号、DDR 校准状态、软件镜像哈希、启动日志、程序输出、周期/计数器、错误计数和环境温度。板卡 PASS 必须能由同一 bitstream 和软件镜像重现，不能只记录“运行过”。

### G8：最终签收

最终签收分为四个独立结论：

- **ISA correctness**：普通 RVV 1.0 定向、随机、差分和内存签名全部通过；
- **special-path correctness**：QBS/AKV 合同、非法/资源不足、回退和上下文切换全部通过；
- **system readiness**：VCS Linux 与 VCU118 Linux 通过启动、用户态和长稳态门禁；
- **performance evidence**：在同一模型、shape、频率、内存配置下，对比 RVV fallback 与 QBS+AKV，并保留计数器和原始日志。

任何一个结论缺少对应证据，只能标记 `INCOMPLETE`，不能用平均性能或少量 kernel PASS 覆盖。

## 3. 建议的执行顺序

当前最稳妥的执行顺序是：

```text
G0 doctor/plan
  -> G1 compile/lint/assertion smoke
  -> G2 QBS/AKV/VLSU/lane subsystem
  -> G3 directed RVV differential
  -> G4 fixed-seed random coverage closure
  -> G5 QEMU software contract
  -> G6 VCS SoC/Linux
  -> G7 VCU118 Linux and long-run model
  -> G8 signoff archive
```

前四级可以在当前 worktree 中持续执行；G5 需要稳定的 QEMU 扩展和模型输入；G6 需要可启动的 SoC Linux payload；G7 需要完成 VCU118 bitstream、时钟、DDR 和板卡软件链路。当前不应把 G6/G7 缺失的硬件条件用模拟日志填补。

## 4. 统一结果目录

每次运行建议使用独立目录：

```text
verification/out/<run-id>/
  run.json                  # commit、工具、配置、命令、状态
  summary.json/csv          # 每个 testcase 的 verdict
  campaign_summary.json     # 全局完整性和组件状态
  stimulus_coverage.json    # 随机语义覆盖
  tests/<case>/             # 命令、日志、trace、差分和最小化结果
  linux/                    # boot log、payload hash、用户态结果
  fpga/                     # bitstream/software/environment manifest
```

`verification/verify.py audit` 只在 run metadata、结果状态、重放命令和需要的 trace/vector/coverage 证据均齐全时给出 `PASS`。这条规则用于阻止“旧日志混入新结果”和“被 watchdog 截断却被当作通过”的问题。
