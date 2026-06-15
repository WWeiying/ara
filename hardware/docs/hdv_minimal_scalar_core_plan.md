# HDV 最小标量核实现方案

> 目标：用从 CVA6 拆出来的现成模块，搭一个**最小标量指令子集**的标量执行核，
> 替换当前的 `hdv_mock_host_core` 标量伪执行 + `hdv_vec_dispatch_unit` 的 vtrace 喂数机制，
> 让绝大多数向量 kernel（saxpy / sdot / sgemm 等 OpenBLAS kernel）能真实跑通整条流水线。

---

## 1. 论文依据

论文 *Boosting Vector Instruction Throughput in RISC-V via a Hybrid Decoupled Architecture*
第 II.E 节对 Hybrid Execution Unit (HEU) 的描述：

- HEU 是**双流水线**结构，标量流水线是"streamlined five-stage, dual-issue, in-order design,
  equipped with two ALUs, a multiplier, an LSU, a branch predictor"。
- 标量与向量流水线**共享 Unified Register File（XRF 整数 / FRF 浮点 / CSRF）**，
  这是标量↔向量数据交换的枢纽（Fig.1 中央的 Unified Register File）。
- 关键授权句："This full-featured vector pipeline is used for experimental validation,
  and **a much simpler implementation is permitted in the future**."

→ 论文明确允许标量侧做简化实现。本方案据此把"五级双发射"降级为
**单发射、按 EP 切片顺序执行的最小标量核**，但保留共享寄存器堆这一核心语义。

---

## 2. 现状分析（要被替换的东西）

当前向量链路能跑通，靠的是两个"作弊"机制：

| 机制 | 文件 | 作用 | 问题 |
|---|---|---|---|
| Mock 标量伪执行 | `hdv_mock_host_core.sv` | 收到 `heu_scalar_*` 后按固定延迟拉 `scalar_heu_accepted`；用 `is_mock_bnez` 识别 bnez、按 `MockLoopIterations=32` 模拟 taken/not-taken 并产生 `redirect` | 不真正算地址/计数，rd 永远不写回 |
| vtrace 喂标量上下文 | `hdv_vec_dispatch_unit.sv` | 从 `vsaxpy.vtrace` 文件按序读 `{insn, rs1, rs2}`，把 rs1/rs2 灌进 `acc_req` | 标量操作数来自离线 trace，不是真实寄存器堆计算结果 |

**替换目标**：用一个真实标量核同时承担这两件事——
真实执行标量 ALU/load/store/branch，并把寄存器堆里的 rs1/rs2/frs1 实时提供给向量派发。

---

## 3. 指令分类现状（已在 VLIWPU 完成）

`hdv_vliw_pack_unit.sv` 的 `p_classify` 已经把每个 slot 分成四类
（`hdv_pkg::hdv_inst_class_e`）：

| 类别 | 判据（opcode） | 去向 |
|---|---|---|
| `HDV_INST_VECTOR` | `0x57`(OP-V，**含 vset\***)、向量 load/store(FP-format) | 向量派发 → Ara |
| `HDV_INST_SYSTEM` | `0x73`(CSR/ECALL) | 标量核 |
| `HDV_INST_BRANCH` | `0x63`(branch) / `0x6F`(JAL) / `0x67`(JALR) | 标量核（产生 redirect）|
| `HDV_INST_SCALAR` | 其余（整数 ALU、标量 load/store、FP scalar）| 标量核 |

HEU 的 split 逻辑（`hdv_hybrid_execution_unit.sv:102`）：
`class==VECTOR` 走 `heu_vector_*`，**其余三类都走 `heu_scalar_*`**。

> 关键点：**vset\* 走向量路径（Ara 内部 dispatcher 算 vl/vtype）**，
> 但它的 `rd`（granted vl）需要写回标量寄存器堆——见 §5.3。

---

## 4. 最小标量指令子集

按 OpenBLAS kernel（saxpy / sdot / sgemm）的实际需求倒推：

### 4.1 必须支持（Phase 1）

| 组 | 指令 | kernel 用途 |
|---|---|---|
| 整数 ALU-imm | `ADDI SLTI SLTIU XORI ORI ANDI SLLI SRLI SRAI` `LUI AUIPC` | 指针偏移、立即数 |
| 整数 ALU-reg | `ADD SUB SLL SLT SLTU XOR SRL SRA OR AND` | 地址/计数计算 |
| RV64 W 变体 | `ADDIW SLLIW SRLIW SRAIW ADDW SUBW SLLW SRLW SRAW` | 32 位索引 |
| 分支 | `BEQ BNE BLT BGE BLTU BGEU` | 循环回跳 |
| 跳转 | `JAL JALR` | 函数 ret、跳转 |
| 标量 load/store | `LB LH LW LD LBU LHU LWU` `SB SH SW SD` | 加载标量/地址 |

### 4.2 强烈建议（Phase 2，sgemm 需要）

| 组 | 指令 | 用途 |
|---|---|---|
| M 扩展（乘）| `MUL`（可选 `MULH/MULHU`）| gemm 的 `stride*index` |
| FP scalar 传值 | `FLW FLD FSW FSD` `FMV.X.W FMV.W.X` | 把标量 α 装入 FRF 供 `vfmacc.vf` 的 frs1 |

### 4.3 可延后 / 暂不做

- `DIV/REM`（serdiv）——内层 kernel 极少用，先不拉。
- FP 标量算术 `FADD.S/FMUL.S`——sdot 末尾归约可先用向量 `vfredsum`+`vfmv.f.s` 绕过。
- 完整 CSR / 特权指令 / 异常 / RVC 压缩——最小核先不实现（VLIWPU 已能处理 16/32 位 slot 拼接，压缩解码可后补）。

> 子集判据：**能算地址、能数循环、能回跳、能把标量操作数送进向量单元**——
> 这四件事覆盖了绝大多数规则数据并行 kernel 的标量需求。

---

## 5. 架构设计

新增一个模块 **`hdv_scalar_core`**（暂称 SPU, Scalar Pipeline Unit），
插在 HEU 的 `heu_scalar_*` 接口上，替换 mock。

```
                         ┌─────────────────────────────────────────┐
                         │              hdv_top                      │
   VLIWPU ── EP ──► HEU ─┤                                           │
                         │  heu_scalar_*  ┌──────────────────┐       │
                         │ ─────────────► │  hdv_scalar_core │       │
                         │ scalar_accepted│  (新增, SPU)      │       │
                         │ ◄───────────── │  ┌────────────┐  │       │
                         │  redirect/lock │  │ Unified RF │◄─┼──┐    │
                         │ ◄───────────── │  │ XRF / FRF  │  │  │ vl写回
                         │                │  └─────┬──────┘  │  │    │
                         │  heu_vector_*  │        │ rs1/rs2 │  │    │
                         │ ─────────────► ┌────────▼─────────┐│  │    │
                         │ vector_accepted│ hdv_vec_dispatch ││  │    │
                         │ ◄───────────── │ (读 RF 替代vtrace)│┼──┘    │
                         │                └────────┬─────────┘│       │
                         │                    acc_req ▼        │       │
                         │                       ┌─────┐       │       │
                         │                       │ Ara │       │       │
                         │                       └─────┘       │       │
                         └─────────────────────────────────────────┘
```

### 5.1 模块内部划分（复用 CVA6）

```
hdv_scalar_core
├── 取指/译码     : 自写最小 decoder（产出 riscv::fu_op + operand_a/b/imm）
├── 寄存器堆      : ariane_regfile（XRF）+ 可选 FRF
├── 整数 ALU      : alu.sv          (CVA6 原样)
├── 分支单元      : branch_unit.sv  (CVA6 原样，去掉分支预测输入)
├── 乘法器        : multiplier.sv   (CVA6，仅 MUL，Phase 2)
├── 标量 LSU      : 自写轻量 AXI master（不拉 CVA6 LSU）
└── EP 切片状态机 : 顺序处理一个 EP 内的 ≤6 条标量 slot
```

### 5.2 统一寄存器堆（方案核心）

- SPU 拥有 **XRF（x0–x31, 64-bit）**，可选 **FRF（f0–f31）**。
- 读端口供给：① 自身 ALU/branch/LSU 的 rs1/rs2；② **向量派发的 rs1/rs2/frs1**。
- 写端口：① 自身 ALU/load 结果写回；② **Ara 回来的 vset rd（granted vl）写回**。
- 端口数（最小单发射）：**3 读 + 2 写**即可
  （2 读给 ALU，1 读给向量派发；1 写给标量结果，1 写给 vset 回写）。
  直接用 `ariane_regfile.sv` 参数化端口数。

### 5.3 与向量派发的协同（替换 vtrace）

改造 `hdv_vec_dispatch_unit.sv`：

1. **去掉 vtrace**（`UseVTraceScalar=0` 或整段移除）。
2. 在 DISPATCH 状态，用当前向量指令的 `rs1/rs2` 字段去**读共享寄存器堆**：
   - `acc_req.rs1 = XRF[insn[19:15]]`（.vx/load/store 的 base / .vf 走 FRF）
   - `acc_req.rs2 = XRF[insn[24:20]]`（如 strided load 的 stride）
3. **vset rd 写回**：vset\* 经向量路径进 Ara，Ara 在 `acc_resp` 里带回 granted vl
   和目标 `rd`。dispatch 单元把 `{rd, result}` 转给 SPU 的寄存器堆写端口。
   → 这样下一个 EP 的标量 `sub a2,a2,t0`（t0=vl）才能拿到正确的 vl。

> 时序保证见 §5.6——EP 串行 + HEU 等齐 accepted，使得"上一个 EP 的写"
> 一定先于"下一个 EP 的读"，**无需 scoreboard**。

### 5.4 分支与 redirect（替换 mock 分支模拟）

- SPU 用 `branch_unit.sv` 真实解析 `BEQ/BNE/.../JAL/JALR`：
  - 比较结果来自 `alu.sv` 的 `alu_branch_res_o`。
  - taken 时输出 `branch_result_o`（目标 PC）→ 驱动 `ctrl_hdv_redirect_valid_i/pc_i`。
- `loop_lock`：保留现有 IPU 回放机制接口。可由 SPU 检测"后向分支 + 命中 active buffer"
  时拉 `loop_lock`，或先沿用一个简单策略（循环体 ≤128B 即 lock）。
- **redirect 延后一拍**这一既有时序约定（避免同拍 flush 抹掉 branch EP 的 ep_accepted）
  在 SPU 里照搬 mock 的 `branch_redirect_wait` 寄存。

### 5.5 标量 LSU 与 AXI（复用已预留的 mux 从口）

**关键便利**：`hdv_top.sv` 的 `axi_mux` 已是 `NoSlvPorts=3`
（Ara / **预留标量** / imem），当前标量口 `assign scalar_axi_req='0`。

→ 最小标量 LSU 直接驱动这个**已存在的 `scalar_axi_req/resp` 从口**：
- **不需要改 mux 宽度**，AXI ID 位宽（`AxiCoreIdWidth + log2(3)`）保持不变。
- LSU 实现成最简单的"单笔 outstanding"AXI master：
  地址来自 `XRF[rs1]+imm`，发 AR/AW，等 R/B，回写 XRF。
- 不拉 CVA6 的 `load_store_unit.sv`（带 MMU/PTW/store-buffer，太重）。

### 5.6 依赖与同步（为什么最小核不需要 scoreboard）

两个事实保证正确性：

1. **EP 内无标量→向量 RAW**：VLIWPU 只把**无数据依赖**的指令打进同一个 EP
   （p-bit + 依赖检查）。所以同一 EP 里标量算的值不会被同 EP 的向量指令用。
2. **EP 间串行**：HEU 必须等齐 `scalar_heu_accepted_i & vector_heu_accepted_i` 才推进到下一个 EP。
   当前接口名使用 accepted，表示后端已经安全接收本 EP 切片；未来真实标量核可以选择在本 EP 切片写回完成后再拉 accepted，以保持最小实现的保序语义。
   （`hdv_hybrid_execution_unit.sv` 现有逻辑）。
   → 上个 EP 的所有写回（含 vset vl 回写）在下个 EP 取数前已落定。

因此最小核只要做到：**SPU 在 EP 切片内的所有标量写回完成后才拉 `scalar_heu_accepted_i`**，
整条链路就自然保序，省掉 scoreboard。（未来要做"标量与向量真并行/跨EP重叠"
时再引入 paper 提到的 scoreboard。）

---

## 6. CVA6 模块复用清单

| CVA6 文件 | 处理方式 | 说明 |
|---|---|---|
| `alu.sv` | **原样复用** | 输入 `fu_data_t`，输出 `result_o`+`alu_branch_res_o`，覆盖全部 RV64I ALU+W 变体+比较 |
| `branch_unit.sv` | **复用，裁剪** | 去掉 `branch_predict_i`（喂常量），保留 target 计算与 taken 解析 |
| `multiplier.sv` | **复用**（Phase 2）| 仅接 MUL/MULH；`mult.sv` 里另含 serdiv，先不接 |
| `ariane_regfile.sv` | **复用，调端口** | 整数 XRF；参数化 3 读/2 写 |
| `ariane_pkg` / `riscv` pkg | **依赖复用** | `fu_op` 枚举、`fu_data_t` 定义——使 alu/branch 接口对齐 |
| `decoder.sv` | **不直接用** | 太耦合（产 `scoreboard_entry_t`）。自写最小 decoder，仅生成 `fu_op`+operands |
| `load_store_unit.sv` / `load_unit.sv` / `store_unit.sv` | **不用** | 带 MMU/PTW/store-buffer。自写轻量 AXI LSU 走预留 mux 口 |
| `csr_regfile.sv` | **不用** | 写极简 CSR stub（或暂不实现）|
| `compressed_decoder.sv` | **暂不用** | RVC 后补 |
| `scoreboard.sv` | **不用** | 见 §5.6，最小核靠 EP 串行保序 |

---

## 7. 实施路线图

**Phase 0 — 接口预备**
- 在 `hdv_top.sv` 暴露/接好 SPU 与 dispatch 之间的寄存器堆读写端口。
- `hdv_vec_dispatch_unit` 增加 `rf_raddr/rf_rdata`（读）与 `rf_waddr/rf_wdata/rf_we`（vset 回写）端口；`UseVTraceScalar` 设为可关。

**Phase 1 — 整数最小核（跑通 saxpy 的标量侧）**
- 新建 `hdv_scalar_core.sv`：自写 decoder + `ariane_regfile` + `alu` + `branch_unit` + EP 切片 FSM。
- 标量 LSU（AXI）接到预留 `scalar_axi` 从口。
- 向量派发改读 XRF 取 rs1（base 地址）；vset vl 回写 XRF。
- 在 `ara_tb` 用宏切换：SPU vs mock（保留 mock 作回归对照）。

**Phase 2 — FP 传值 + 乘法（saxpy 的 α、sgemm 的索引）**
- 加 FRF + `FLW/FMV.W.X`，把 α 送 `vfmacc.vf` 的 frs1。
- 接 `multiplier.sv` 支持 `MUL`。

**Phase 3 — 收尾**
- sdot 末段归约（`vfredsum`+`vfmv.f.s` 回 FRF，必要时补 `FADD.S`）。
- 退役 vtrace；mock 仅保留为 CI 冒烟测试。
- （可选）RVC 压缩解码、CSR、scoreboard 并行化。

---

## 8. 验证策略

1. **vtrace 当金标准**：SPU 跑出来的 `acc_req.rs1/rs2` 序列，与现有
   `vsaxpy.vtrace` 逐拍比对（可在 dispatch 单元里保留一个"对照模式"断言）。
2. **mock 作回归底座**：宏 `USE_REAL_SCALAR` 切 SPU/mock，确保 EP 计数、
   FINISH 状态、`ep_accepted` 个数三者在两种模式下一致。
3. **kernel 分级**：saxpy（Phase1）→ sdot（Phase3）→ sgemm（Phase2 乘法）逐个点亮。
4. **内存内容校验**：SPU 上线后 load/store 真实访存，需在 TB 预置输入向量、
   仿真后比对输出向量（不再是纯握手）。

---

## 9. 风险与权衡

| 风险 | 说明 | 缓解 |
|---|---|---|
| 真实访存引入延迟 | load EP 不再 1 拍，`PacketWatchdogCycles` 可能误触发 | 调大 watchdog；LSU 单笔 outstanding 简化时序 |
| vset rd 回写时序 | granted vl 必须在下个 EP 标量取数前落定 | 未来真实执行需让 vector accepted 覆盖 vset rd 回写；当前原型的 `vec_heu_accepted_o` 只表示 Ara 接收，不保证 rd 写回 |
| 向量操作数取 XRF vs FRF | `.vx` 取 XRF、`.vf` 取 FRF，需按 funct3 区分 | decoder 给 dispatch 一个 `use_frf` 标志位 |
| EP 内多向量 slot 取数顺序 | 多个向量 slot 各需自己的 rs1 | dispatch 已是 lowest-index 串行，逐条读 RF 即可 |
| 自写 decoder 覆盖面 | 漏译某条指令→执行错误 | 子集封闭、有限；用 vtrace 对照兜底 |

---

## 10. 一句话总结

复用 CVA6 的 **`alu` + `branch_unit` + `ariane_regfile`（+Phase2 `multiplier`）**，
自写**最小 decoder 和轻量 AXI LSU**，组成单发射顺序标量核 `hdv_scalar_core`；
以**共享寄存器堆**为枢纽，向量派发从 RF 实时取 rs1/rs2 取代 vtrace、
Ara 把 vset 的 vl 写回 RF；靠 **EP 串行 + HEU 等齐 accepted** 天然保序而免去 scoreboard；
标量访存复用 axi_mux **已预留的标量从口**，零 ID 位宽改动。
这样即可在不破坏现有解耦流水线的前提下，让绝大多数向量 kernel 真实跑通。

---
---

# 补充（v2）：基于真实 kernel 的稳健子集 + 魔改 CVA6 路线

> 背景更新：用户后续打算**直接魔改 CVA6**（而非只拆零件自搭核），让它充当 HDV 的标量流水线。
> 本补充：① 扫描仓库内**真实 RVV kernel** 的标量指令用量，定一个稳健子集；
> ② 给出"魔改 CVA6"的具体接入方案。

---

## A. 真实 RVV kernel 标量指令扫描

数据来源：`apps/` 下各 kernel 的内联汇编 / 反汇编（这些就是 HDV 当作 task 跑的循环体本身）。

### A.1 各 kernel 标量指令实测

| kernel | 标量指令（去掉 v* 向量指令）| 备注 |
|---|---|---|
| `vsaxpy` | `sub slli add bnez ret` + `rdcycle` | 真二进制里是 **RVC**：`959a`=c.add、`f165`=c.bnez、`8082`=c.ret |
| `vsscal` | `sub slli add bnez ret` + `rdcycle` | 同上 |
| `vsdot` | `sub slli add bnez ret` + `rdcycle` | 末尾 `vfmv.f.s`（向量→FP标量）|
| `vsgemv` | `li mv addi fsw bnez ret` + `rdcycle` | `fsw` 存归约结果；`li` 建常量 |
| `vsger` | `slli mv flw fmul.s add sub addi bnez ret` + `rdcycle` | **标量 `fmul.s`**（alpha*x[i]）+ `flw` |
| `vsgemm` | `addi mv flw li bnez` + `rdcycle`（×3 大块）| 大量 `addi` 做多指针偏移；`flw` 取 A 的标量 |

### A.2 关键发现

1. **RVC（压缩指令）是刚需**：真二进制的循环体大量用 `c.add/c.bnez/c.ret/c.mv/c.li/c.sd/c.ld/c.addi`。
   VLIWPU 已能拼 16/32 位 slot，但**标量核必须能解压 RVC**，否则跑不了实际编译产物。
2. **手写 kernel 刻意用 `slli`+`add` 规避 `mul`**（×4 步长 = 左移 2）。
   但**编译器产物 / 任意步长**会生成 `mul` → 为稳健性仍需纳入 `MUL`。
3. **标量 FP 真实出现**：`vsger` 用 `fmul.s ft1, fa0, ft0`，多个 kernel 用 `flw/fsw`。
   → FP 标量不止"传值"，还有少量算术。最小集需含 `FLW/FSW/FMUL.S/FADD.S/FMV.*`。
4. **`rdcycle`（CSR 读）出现在每个 kernel 开头**：是 `csrrs zero, cycle, zero`（写 zero，丢弃）。
   → 只需把 CSR 读**stub 成返回 0 或一个自增计数**即可，不必实现完整 CSR。
5. **分支只见 `bnez`**，但 C 编译循环会出 `beq/bne/blt/bge/bltu/bgeu` 全套 → 全纳入。
6. **没出现 `div/rem`**：内层 kernel 不用除法 → 可暂不实现（serdiv 延后）。

---

## B. 推荐的稳健指令子集 ≈ **RV64IM + C + 最小 F/D 标量 + Zicsr-stub**

比 v1 §4 更稳健，覆盖"手写 + 编译器产物"两类 kernel：

| 扩展 | 纳入指令 | 理由 |
|---|---|---|
| **RV64I** | 全部：`LUI AUIPC` / `ADDI..ANDI` / `ADD..AND` / W 变体 / `JAL JALR` / `BEQ..BGEU` / `LB..SD` | 地址/计数/分支/访存基础 |
| **M（乘）** | `MUL MULW`（`MULH/MULHU/MULHSU` 可选；`DIV/REM` 延后）| 任意步长索引 |
| **C（压缩）** | 标准 RVC 解码（`c.add/addi/mv/li/lw/ld/sw/sd/beqz/bnez/jr/jalr/...`）| **真二进制刚需** |
| **F/D 标量** | `FLW FLD FSW FSD` `FMV.X.W FMV.W.X FMV.X.D FMV.D.X` `FMUL.S FADD.S`（D 版可选）| 标量 α、归约、`.vf` 广播源 |
| **Zicsr（stub）** | `CSRRS/CSRRW` 仅对 `cycle/time/instret/vl/vtype/vlenb` 做最小响应 | `rdcycle` 等 |

> 一句话：**RV64IMC + 一撮 FD 标量 + CSR stub**。
> 这正好是"能编译大多数 RVV kernel 标量胶水"的最小封闭集。

---

## C. 魔改 CVA6 接入方案（推荐路线）

### C.1 两条路线对比

| | 路线①：拆零件自搭（v1 §5–6）| 路线②：**魔改 CVA6 整核**（本补充）|
|---|---|---|
| 做法 | 抽 `alu/branch_unit/regfile` 自己连 | 拿整个 CVA6，砍掉不需要的，换掉前端喂指令口 |
| 译码 | 自写最小 decoder | **直接用 CVA6 的 `decoder`+`compressed_decoder`**（RVC 免费） |
| 共享寄存器堆 | 要自己把 RF 暴露给向量派发 | **CVA6 的 `acc_dispatcher` 原生就读 RF 操作数发给 Ara** |
| vset vl 回写 | 要自己接回写口 | **`acc_dispatcher` 原生接收 Ara 回的 rd 写回 RF** |
| 与论文 Fig.1 吻合度 | 中 | **高**：Fig.1 的 HEU 本就是"标量五级流水 + dispatcher + Ara + 统一RF" |
| 工作量 | 中（写得多）| 中（砍 + 改接口，但复用度最高）|

**推荐路线②**：CVA6 的 id/issue/ex/commit + acc_dispatcher 几乎就是论文画的 HEU 后端，
把"取指前端"换成 HDV 的 IPU/VLIWPU/HEU 即可，RVC 解码、操作数读取、vset 回写、
标量↔向量 scoreboard **全部白嫖**。

### C.2 注入点（已确认）

CVA6 的 `id_stage` 入口吃 `fetch_entry_t`（`cva6.sv:83`）：

```systemverilog
fetch_entry_t = struct packed {
  logic [VLEN-1:0] address;       // PC
  logic [31:0]     instruction;   // 指令字（RVC 也放这，compressed_decoder 解）
  branchpredict_sbe_t branch_predict;  // 喂"not-taken"即可
  exception_t      ex;            // 喂 0
};
// 握手：fetch_entry_valid_i / fetch_entry_ready_o
```

→ **魔改桥接器**把 HEU 的 `heu_scalar_insn_o[i]` + `heu_scalar_insn_pc_o[i]`
逐条打包成 `fetch_entry_t` 灌进 `id_stage.fetch_entry_i`，旁路掉整个 `frontend`。

> 注意：向量指令也可一并灌进去——CVA6 译码识别为 OP-V 后由 `acc_dispatcher` 读操作数
> 发给 Ara。这样 `hdv_vec_dispatch_unit` 的职责被 CVA6 原生 acc_dispatcher 接管，
> rs1/rs2 取数与 vset 回写都不用我们再写。

### C.3 砍 / 留 / 改 清单

| CVA6 组件 | 处理 | 说明 |
|---|---|---|
| `frontend/`（PC gen、I$、BHT/BTB、instr_queue）| **砍** | HDV 的 IPU/VLIWPU 已做取指+对齐+打包 |
| `cva6_mmu/`、`pmp/`、PTW | **砍** | 物理地址直跑，无虚拟内存 |
| cache_subsystem（D$/I$）| **砍/换** | 标量访存走轻量 AXI（复用预留 `scalar_axi` 从口）|
| CLIC、debug、RVFI、CVXIF | **砍** | 原型不需要 |
| `csr_regfile` | **裁成 stub** | 只留 `cycle/vl/vtype/vlenb/frm` 等少数；其余 ECALL/异常路径砍 |
| `decoder` + `compressed_decoder` | **留** | RVC 解码白嫖（对应 A.2 发现1）|
| `issue_stage`（scoreboard、operand read）| **留** | 解决标量↔向量定序与操作数读取 |
| `ex_stage`（alu/branch/mult/lsu）| **留**，LSU 换轻量 AXI | mult 给 §B 的 MUL；serdiv 可砍 |
| `commit_stage` | **留**，裁简 | 退休/写回；异常处理裁简 |
| `acc_dispatcher` | **留（核心复用）** | 即"向量 dispatcher"：读操作数→发 Ara→收 vl 回写 |

### C.4 与现有 HDV 信号的对接

- `heu_scalar_*` →（桥接器→`fetch_entry_t`）→ `id_stage`；标量 EP 切片处理完拉 `scalar_heu_accepted_i`。
- 向量：二选一
  - **C.4a 收敛式（推荐）**：向量指令也进 CVA6，`acc_dispatcher.acc_req_o` 直接驱动 Ara，
    现有 `hdv_vec_dispatch_unit` 退役（vtrace 一并删）。
  - **C.4b 并存式**：保留 `hdv_vec_dispatch_unit`，但其 rs1/rs2 改从 CVA6 的 RF 读
    （需把 RF 读口引出，较丑）。→ 不推荐。
- 分支 redirect：用 CVA6 `commit_stage`/`branch_unit` 解析出的跳转，转成
  `ctrl_hdv_redirect_valid_i/pc_i`，替换 mock 的 `is_mock_bnez` 假分支。
- `loop_lock`：沿用 IPU 回放接口，由桥接器在检测后向分支命中 active buffer 时拉起。

### C.5 魔改路线的特有风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| CVA6 配置裁剪牵连广 | `config_pkg` 一处开关牵动多模块 | 用现成精简 config（如 `cv32a60x`/`cv64a6` 系列）做基线再删 |
| 前端旁路的握手语义 | `id_stage` 期望 frontend 的 valid/ready + 异常/预测字段 | 桥接器喂 not-taken 预测、0 异常；按 NrIssuePorts 对齐位宽 |
| 双发射 vs 单发射 | CVA6 可能配双发射，HEU 一个 EP 多 slot | 先配**单发射**，EP 内 slot 串行灌入，简化定序 |
| commit/PC 连续性 | CVA6 内部假设 PC 单调；HDV 由 IPU 控 PC | redirect 只取 CVA6 算的 target，PC 流仍由 IPU 主导；二者一致性需对齐 |
| 仿真层次引用 | 旧 CVA6/gatesim 路径可能有 `i_ariane.*` 探针；当前 HDV 非 gatesim 路径没有 `i_ariane` | 魔改后层次名变化，相应更新探针 |

### C.6 推荐落地顺序（在 v1 路线图基础上调整）

1. **先用现成精简 CVA6 config** 跑通"前端旁路 + id_stage 注入"单条标量指令。
2. 接 `acc_dispatcher` → Ara，跑通 vsetvli + 一条 vle32（验证 vl 回写 RF）。
3. 点亮 `vsaxpy`（RVC + sub/slli/add/bnez/ret）→ `vsscal` → `vsdot`。
4. 加 `flw/fsw/fmul.s` 点亮 `vsger`；加 `mul` 点亮通用 gemm。
5. 退役 `hdv_vec_dispatch_unit` + vtrace + mock 标量；mock 仅留 CI 冒烟。

> 参考资料：仓库内已有 CVA6 中文学习笔记
> `/home/wangwy/openproject/cva6/cva6_learning_notes/`（02 前端、03 ID 译码、11 Package 配置体系），
> 魔改时按这些笔记定位裁剪点最快。

---
---

# 补充（v3）：全仓库 RVV kernel 扫描 + 子集选择再定论

> 本节把 `apps/` 下**所有** RVV kernel 都过了一遍（不止 vs*），重新审视子集选择。
> 结论有变化：**子集该多大，取决于"HDV 要跑哪类 kernel"**，而魔改 CVA6 路线让这个问题基本消失。

## D. 全仓库 kernel 分类（共 32 个）

按"标量代码从哪来"分两类：

| 类别 | 含义 | kernel |
|---|---|---|
| **HAND-ASM**（标量也手写在 asm 里）| 整个循环体含标量都是内联汇编，子集可控 | `vsaxpy vsscal vsdot vsgemv vsger vsgemm vvaddint32 vmc dtype-matmul fconv2d iconv2d` |
| **compiler-scalar**（只有向量是 asm，标量是 C）| 标量胶水由编译器生成 = **任意 RV64GC** | `dotproduct fmatmul fmatmul-loop imatmul gemv fdotproduct fconv3d dtype-conv3d conjugate_gradient spmv jacobi2d softmax exp log cos fft dropout pathfinder roi_align lavamd vfredsum` |

**关键事实**：21/32 个 kernel 是 compiler-scalar——它们的标量部分（指针运算、循环控制、
索引计算、稀疏间接寻址）由 GCC/Clang 生成，**无法预测、就是完整 RV64IMC+FD**。
只有 11 个 HAND-ASM kernel 的标量子集是封闭可控的。

## E. 全 HAND-ASM kernel 标量指令直方图（实测）

跨 11 个 HAND-ASM kernel 统计到的标量指令（按出现次数）：

```
 117 ld     102 fld    97 flw    88 addi   84 lb    84 lh    84 lwu
  23 mv      23 add    19 bnez   16 nop    15 li    13 slli  13 rdcycle
  11 sub      3 fsw     2 beqz    1 fmul.s  1 fence
```

相比 v2，**新增三类必须纳入的指令**：

1. **子字访存 `lb / lh / lwu`（各 84 次）**：来自 `dtype-matmul` 等**混合精度** kernel——
   读 int8/int16/int32 标量元素再广播给 `.vx/.vf`。→ load/store 必须支持 **B/H/W/D 全宽度 + 有/无符号**。
2. **`nop`（16）/ `fence`（1）**：padding 与访存定序。`fence` 在 HDV 单标量场景可弱化实现。
3. **`rdcycle`（13）**：每个 kernel 开头都有，CSR 读，stub 即可。

依旧**没出现 `mul / div`**：HAND-ASM kernel 全用 `slli+add` 规避——但 compiler-scalar
kernel（imatmul 的 `i*stride`、`s*=2`；spmv 的稀疏索引）必然产生 `mul`。

## F. 子集选择：再定论

这次扫描把决策点彻底厘清——**子集大小由"目标 kernel 范围"决定**：

| 目标范围 | 需要的标量子集 | 适配路线 |
|---|---|---|
| 仅 HAND-ASM 紧循环（vs* 类）| RV64I 子集 + `MUL` + RVC + 子字 load + `{flw fld fsw fsd fmul.s fadd.s fmv.*}` + CSR-stub | 路线①自搭核**可行** |
| **全 Ara 基准（含 compiler-scalar）** | **完整 RV64IMC + F/D 标量 + Zicsr**（≈ RV64GC 去特权）| 路线①成本骤升；**路线②魔改 CVA6 几乎零额外成本** |

### F.1 决定性结论

> **走魔改 CVA6（路线②）时，"指令子集"基本是个伪命题。**
> CVA6 的 `decoder/compressed_decoder/issue/ex` 本来就完整支持 RV64GC，
> **删 ALU 指令反而比保留它们更费劲、更易出错**。
> 所以正确的做法不是"裁 ISA"，而是"**裁系统**"：

- **保留**：完整 RV64IMC + F/D 标量数据通路（白嫖，覆盖全部 32 个 kernel 的标量）。
- **删/stub**：MMU、PMP、cache、特权态/CSR 大部、frontend、CLIC、debug、原子/`fence` 重实现。
- 这样 **HAND-ASM 与 compiler-scalar kernel 一视同仁全跑通**，不必逐 kernel 确认子集。

### F.2 若坚持路线①自搭核（仅为更小面积）

则锁定到这张"封闭最小集"（覆盖全部 HAND-ASM kernel）：

- **整数**：RV64I 全量 + `MUL/MULW`
- **访存**：`LB LH LW LD LBU LHU LWU` / `SB SH SW SD`（**子字必须有**，否则 dtype 类挂）
- **压缩**：RVC 解码（真二进制刚需）
- **FP 标量**：`FLW FLD FSW FSD FMUL.S FADD.S FMV.X.W FMV.W.X`（D 版可选）
- **杂项**：`NOP`、`FENCE`（可弱化）、CSR 读 stub（`rdcycle/vl/vtype/vlenb`）
- **可省**：`DIV/REM`、完整 CSR、特权指令

> 但请注意：**这套子集只保证 HAND-ASM kernel**。一旦要跑 compiler-scalar kernel
> （fmatmul/imatmul/spmv/fft…），自搭核就得不断补指令，最终趋近完整 RV64GC——
> 那还不如直接魔改 CVA6。

## G. 给用户的最终建议

1. **若 HDV 目标就是 Ara 全基准** → **直接魔改 CVA6（路线②），不要纠结子集**：
   保留全 RV64GC 标量通路，把工程量花在"裁系统 + 换前端注入口 + acc_dispatcher 接 Ara"。
2. **若 HDV 只想先点亮 vs* 紧循环做原型** → 路线①自搭核用 **§F.2 封闭最小集**即可，
   面积最小、可控；但要清楚它的天花板是 HAND-ASM kernel。
3. 无论哪条路，**子字 load/store + RVC + 标量 FP（含 fmul.s）+ rdcycle-stub** 都是
   本次全仓库扫描确认的"不可省"项——v1 的纯 RV64I 子集会漏掉 dtype/RVC/FP 三处。
