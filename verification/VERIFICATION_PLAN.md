# Ara DSA 验证计划与签核流程

## 1. 目标与边界

本分支把验证从“能运行若干测试”提升为**需求驱动、证据闭环、可复现签核**的流程，覆盖两条主线：

1. 标准 RVV 1.0、CVA6/CVXIF、Ara 向量后端及存储系统的架构正确性；
2. QBS/AKV 等专用路径与普通 RVV fallback 的功能、异常、顺序和软件契约。

最终目标不是只证明某些 kernel 通过，而是能够回答：

- 哪一条架构需求被哪些测试覆盖；
- 每个结果是否来自当前 RTL、当前工具和唯一 seed；
- 失败发生在 Spike、RTL、提交顺序、向量状态、内存签名还是环境；
- Linux 启动、进程切换、虚拟内存和真实运行时是否通过了独立的系统级门禁。

`verification/verification_plan.json` 是机器可读计划，`verify.py plan` 会检查它引用的 suite 是否仍存在，`verify.py audit` 会对一次完成的运行执行签核审计。

## 2. 验证方法的层次

工业级处理器验证通常不是单一 UVM 测试，而是多个互补层次：UVM/事务级随机、ISA architectural tests、参考模型差分、SVA/formal、覆盖率闭环、软件和操作系统集成。UVM 主要解决可复用的 sequence、driver、monitor、scoreboard 和 coverage collector；它本身不能替代参考模型、异常验证或 Linux 回归。

本项目采用相同的职责分解。当前 Python runner、SystemVerilog monitor 和 Spike differential checker 分别承担回归控制、硬件观察和架构参考比较；后续可将模块级接口 agent 替换为 UVM agent，而不改变测试计划和签核证据格式。

### L0：源代码与环境预检

签核前固定以下内容：

- RTL Git revision、工作树状态和 Bender.lock；
- riscv-dv、Spike、RISC-V GCC/LLVM、VCS 版本及绝对路径；
- Ara 配置：VLEN、lane 数、L2、QBS、AKV、SRAM model；
- test inventory、suite、seed、timeout、simulator command；
- 源文件快照和工具锁定文件的 SHA-256。

脏依赖、缺失工具、测试清单减少、覆盖报告缺失时，不能进入 PASS。

### L1：模块/子系统验证

模块级测试直接驱动接口并检查协议和状态转移，不依赖完整 CVA6：

| 子系统 | 必须检查的内容 |
|---|---|
| QBS decoder/profile | opcode、profile、shape、stride、非法编码、fallback |
| QBS read/compute/commit | descriptor、AXI burst、RRESP/RLAST、MMU/PMA fault、原子提交 |
| AKV context/view | view/lifetime、KV refill、tail、fault、flush、fallback |
| VLSU/SLDU/MASKU | handshake、跨页、mask、segment、restart、result routing |
| lane/MFPU/reduction | packed beat、EEW、vstart、mask/tail、重叠寄存器组 |
| CVA6/CVXIF boundary | request/response 顺序、异常、flush、pending 记账、唯一完成 |

这些测试必须带协议断言或 `$fatal` 检查。AXI、MMU、结果端口和 commit 的 owner 不能出现双重驱动、丢失响应、重复完成或未归属写回。

### L2：定向架构差分

定向 RVV 测试覆盖规格中有明确边界的操作：SEW/LMUL、尾和 mask policy、非零 `vstart`、重叠寄存器组、segment/indexed/mask memory、reduction、异常和恢复。

每个测试至少保存：

1. ELF、反汇编和生成命令；
2. Spike commit log；
3. RTL RVFI/CVXIF/backend trace；
4. 逐条 PC/encoding、标量写回、标量内存访问比较；
5. 向量状态签名或逐条向量写回比较；
6. 首个不一致位置及其前后指令。

只看到 `Core Test SUCCESS` 不代表差分通过；没有参考结果或没有 trace 的 PASS 不能作为架构签核证据。

### L3：约束随机与覆盖闭环

riscv-dv 负责产生可复现的 RVV 1.0 指令流。每个 seed 都必须经过：生成、编译、Spike、RTL、trace validation、标量比较、向量比较和 coverage merge。

覆盖不以 seed 数代替。至少闭合以下维度：

- 指令族和精确 mnemonic；
- SEW=`e8/e16/e32/e64`；LMUL=`mf8...m8`；
- `ta/tu`、`ma/mu`；
- unit-stride、strided、indexed、segment、mask、whole-register、fault-first；
- `vstart=0`、合法非零 `vstart`、必须非法的非零 `vstart`；
- widening/narrowing/mixed-EEW 和合法重叠；
- scalar/vector 混合控制、异常、flush、长延迟和 backpressure。

随机回归必须保存 profile、seed、生成源码 hash、ELF hash、Spike 命令和 RTL 命令。失败重放只使用原始 ELF 和原始命令，不重新随机生成“相似”用例。

### L4：SoC 与 Linux 集成

Linux 需要独立于 bare-metal/RVV 差分的系统级签核，至少分三层：

| 层级 | 环境 | 通过条件 |
|---|---|---|
| Linux-QEMU | 与目标 ISA/设备树一致的 QEMU/OpenSBI/Linux/rootfs | OpenSBI、内核、init、shell、RVV 程序均到达预定 marker |
| Linux-RTL | CVA6+Ara RTL 或门级仿真，使用同一 kernel/DTB/rootfs | 启动、页表、异常、UART、定时器、用户态 RVV 和 QBS/AKV smoke 全通过 |
| Linux-FPGA | VCU118 bitstream、DDR、UART、设备树 | 可重复启动，运行自检、RVV fallback、QBS/AKV contract，日志带版本和 hash |

当前仓库已经有 VCU118 Linux payload 生成脚本，但它不能自动证明 RTL Linux 已通过。只有产生带 `boot_id`、kernel/rootfs/DTB hash、console marker 和退出状态的完整日志，L4 才能标记 PASS。

Linux 回归还必须覆盖：进程/线程切换后的 vector CSR、信号或异常返回、页表切换、用户态非法指令、QBS/AKV disabled fallback、内存 fault、reset/flush 和长时间循环。QBS/AKV 不得依赖 bare-metal 固定物理地址或未声明的特权状态。

### L5：形式与断言

仿真发现功能错误，形式方法适合证明局部不变量。应为以下性质建立 bind/assertion 集合：

- request/response 不重复、不丢失、不越过 flush；
- backend `vid` 只分配给一个未完成请求；
- 每个 owner 独占 MMU/AXI/result path；
- store byte-enable 不写入非活动元素；
- 非法 `vstart` 操作产生异常且不提交目的状态；
- QBS/AKV fault 后不提交部分结果；
- fallback 与普通 RVV 使用同一架构完成规则。

形式证明不能替代端到端数值比较；端到端测试也不能证明所有 backpressure/flush 状态组合。

## 3. 签核门禁

一次结果只有同时满足以下条件才可标记为签核通过：

1. 运行状态为 `COMPLETE`，没有 `FAIL`、`TIMEOUT`、`ERROR`、`NOT_RUN`；
2. 每个 case 有可重放 command metadata 和唯一 artifact directory；
3. 需要差分的 case 有有效 trace、Spike/RTL 比较结果和首错信息；
4. RVV case 有向量状态证据，不能只比较标量前缀；
5. 随机 profile 有实际 `stimulus_coverage.json`，覆盖维度满足计划；
6. 运行前后源快照一致，或差异被明确记录并拒绝作为签核；
7. Linux/QBS/AKV 的通过条件与普通 RVV 分开统计，不能用一个 suite 的 PASS 替代另一条主线。

执行：

```bash
cd /home/wangwy/openproject/ara_dsa_verification
PYTHONPATH=verification python3 verification/verify.py plan
PYTHONPATH=verification python3 verification/verify.py doctor
PYTHONPATH=verification python3 -m unittest discover -s verification/tests
PYTHONPATH=verification python3 verification/verify.py audit \
  --run verification/out/<completed-run> \
  --require-trace --require-vector --require-coverage
```

`verification_audit.json` 是签核输出，不允许用手工修改 summary.json 的方式通过。

## 4. 当前状态与后续实施顺序

本分支当前已具备：锁定依赖、VCS 隔离运行目录、确定性 random seed、Spike/RTL commit 比较、向量签名/写回比较、CVXIF/backend trace validation、测试汇总和失败重放。新加入的机器可读 plan 与 audit 将这些能力统一到需求和签核门禁下。

仍不能把当前状态称为“Linux 已签核”：现有 VCU118 Linux 脚本证明的是 FPGA bring-up 资产可生成，不等于当前 RTL 仿真已经完成 Linux boot。后续必须按 L1 → L2 → L3 顺序补齐：先稳定 QEMU/ISA 组合，再建立 RTL Linux boot smoke，最后在 VCU118 实测，并将日志纳入同一 provenance 格式。

推荐执行顺序：

1. `plan`、`doctor`、单元测试和模块级 QBS/AKV contract；
2. smoke + directed RVV + vector checkpoint；
3. 失败回归和 10-seed profile；
4. 50-seed/nightly coverage closure；
5. QEMU Linux boot marker；
6. RTL Linux boot、用户态 RVV/QBS/AKV smoke；
7. FPGA Linux bring-up；
8. 只有全部门禁通过后才做性能、功耗和物理实现结论。
