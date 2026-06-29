# CVA6 与 HDV 标量后端详细对比

本文档对比两个对象：

- 原始 CVA6：`hardware/deps/cva6/core/` 下的完整 CVA6 core。
- 当前 HDV 标量后端：`hardware/src/scala_backend/hdv_scalar_backend.sv`。

结论先写清楚：当前 `hdv_scalar_backend` 不是“精简后的完整 CVA6 core”，而是一个 **HDV 专用、轻量多发射、复用 CVA6 若干执行部件的标量后端**。它当前配置为 `ScalarIssueWidth=3`、`SimpleAluIssueWidth=2`：每周期最多发射两条 simple ALU 指令和一条 complex 指令。它已经可以承担 HDV 中的标量切片执行、分支 redirect、向量操作数服务、vset granted-vl 回写等职责，但距离完整 RV64IMC + F/D + Zicsr 用户态标量通路还有明显缺口。

---

## 1. 顶层职责对比

| 项目 | 原始 CVA6 | 当前 HDV 标量后端 |
|---|---|---|
| 取指 PC 管理 | 有完整 frontend、PC gen、分支预测、I-cache 接口、异常重定向。 | 没有取指。PC、fetch packet、HINT、EP 起点由 HDV 的 IPU/VLIWPU 管。 |
| 指令队列 | 有 frontend instruction queue、re-align、compressed 处理、issue 输入队列。 | 没有全局指令队列。HEU 已经把一个 EP 内的 scalar slots 直接送入后端。 |
| 发射机制 | CVA6 pipeline 内部 issue/read-operands/scoreboard/commit。 | 一个 EP 的 scalar slots 锁存后，尝试 3 发射：2 simple ALU lane + 1 complex lane；hazard/order barrier 时保守拆开。 |
| 乱序/保序 | CVA6 使用 scoreboard 和 commit 机制保证架构状态提交。 | 没有 scoreboard/commit stage；靠“EP 间保序”和后端顺序状态机保证。 |
| 向量关系 | 原 CVA6 可通过 `acc_dispatcher`/CV-X-IF 连接 Ara。 | 不走原 `acc_dispatcher`。向量指令由 HDV VLIWPU/HEU/vector dispatch 直接送 Ara。 |
| 寄存器堆 | CVA6 有整数/浮点寄存器文件，与 pipeline、bypass、commit 集成。 | 内部自建 `xrf_q[32]` 和 `frf_q[32]` 数组；没有 CVA6 原寄存器堆端口化实现。 |
| CSR | 完整 CSR regfile、特权态、异常、计数器、浮点状态等。 | 只有小型 CSR stub，支持少量用户态/向量相关 CSR。 |
| LSU | 完整 load/store unit、store buffer、cache/MMU/PMP/异常路径。 | 轻量 AXI 单笔访问状态机，单 outstanding，不支持 MMU/PMP/cache 语义。 |
| 异常/中断 | 完整 trap/interrupt/debug/privileged 控制。 | 异常基本压缩成 `scalar_error_o`，没有真实 trap 入口、`mcause`/`mepc` 等状态流。 |

---

## 2. 当前后端实际复用的 CVA6 部件

当前后端不是复制整个 CVA6 pipeline，而是实例化或复用以下 CVA6 部件和包定义。

| CVA6 资源 | 当前用法 | 说明 |
|---|---|---|
| `ariane_pkg::*` | 直接 import | 使用 `fu_t`、`fu_op`、`REG_ADDR_SIZE`、操作枚举、辅助函数如 `is_rs1_fpr`、`is_rd_fpr`、`extract_transfer_size`。 |
| `riscv_pkg` | 通过 `riscv::...` 使用 | 使用 CSR 编号、CSR 操作编码、特权级常量、IRQ 常量。 |
| `compressed_decoder` | 直接实例化 | 把 16-bit 压缩指令展开成 32-bit 指令，并产生 illegal compressed / macro / zcmt 标志。 |
| `decoder` | 直接实例化 | 用 CVA6 原译码器生成类似 scoreboard entry 的译码结果：`fu`、`op`、`rs1`、`rs2`、`rd`、`result/imm`、异常标志等。 |
| `alu` | 直接实例化 | 执行 ALU 类指令，也提供 branch compare 结果。 |
| `branch_unit` | 直接实例化 | 根据 `fu_data`、PC、branch compare 结果计算 taken 与 target。分支预测输入固定为 0。 |
| `mult` | 直接实例化 | 处理 MULT 类指令。该模块内部覆盖乘法/除法相关路径，当前后端按 CVA6 decoder 的 `fu == MULT` 统一交给它。 |
| `fpu_wrap` | 直接实例化 | 处理 scalar FPU 指令，使用当前 CSR stub 中的 `frm`。 |
| CVA6 config | 参数 `CVA6Cfg` | 后端使用 `cva6_config_pkg::cva6_cfg` 作为默认配置，决定 XLEN、VLEN、FLen、FpPresent 等类型宽度。 |

注意：当前实现虽然复用了 `decoder`，但没有复用 CVA6 的 `scoreboard_entry_t` 原始类型定义，而是在本模块内部重新定义了兼容的 localparam type。这是为了让 `decoder/alu/branch/fpu` 能独立工作，而不把完整 CVA6 pipeline 带进来。

---

## 3. 当前没有复用的 CVA6 主要模块

| CVA6 模块/机制 | 当前是否有等价实现 | 当前状态 |
|---|---:|---|
| `cva6.sv` 顶层 core | 否 | HDV 后端不是完整 core，只是 HEU 后面的执行后端。 |
| `frontend/frontend.sv` | 否 | 取指由 HDV IPU 负责。 |
| `instr_realign.sv` | 否 | HDV VLIWPU 已处理 slot 与 16/32-bit 拼接。 |
| `frontend/instr_queue.sv` | 否 | 无全局指令队列；EP 直接锁存。 |
| branch predictor: BHT/BTB/RAS | 否 | 当前分支在标量后端真实解析后 redirect，没有预测。 |
| `id_stage.sv` | 否 | 没有 CVA6 ID stage；译码在后端内部组合完成。 |
| `issue_stage.sv` / `issue_read_operands.sv` | 否 | 没有复用 CVA6 issue/read operand stage；HDV 后端内部自写轻量 3 发射选择和 hazard 检查。 |
| `scoreboard.sv` | 否 | 没有 scoreboard。依赖关系由 VLIWPU p-bit/EP 边界和后端保序承担。 |
| `ex_stage.sv` | 部分 | 没有复用完整 ex_stage，只单独实例化 ALU/branch/mult/FPU。 |
| `commit_stage.sv` | 否 | 没有 commit/retire stage；执行完成直接写内部 XRF/FRF。 |
| `csr_regfile.sv` | 否 | 用小型 CSR stub 代替。 |
| `load_store_unit.sv` | 否 | 用自写轻量 AXI LSU 代替。 |
| `load_unit.sv` / `store_unit.sv` / `store_buffer.sv` | 否 | 不支持 store buffer、load-store hazard、store forwarding。 |
| cache subsystem | 否 | 标量访存直接走 AXI 请求，不走 CVA6 D-cache/HPDcache。 |
| MMU/PTW/TLB | 否 | 不支持虚拟地址翻译。 |
| PMP/PMA | 否 | 不支持完整权限检查。 |
| `amo_buffer.sv` / AMO ALU | 否 | AMO/LR/SC 没有真实实现。 |
| debug/RVFI/tracer | 否 | 没有 debug mode、RVFI、完整 trace。 |
| CLIC/interrupt controller | 否 | 中断输入固定无效。 |
| CV-X-IF issue/commit driver | 否 | 向量由 HDV vector dispatch 直接发 Ara，不走 CVA6 CV-X-IF 管线。 |

---

## 4. 流水线与执行模型对比

### 4.1 原始 CVA6

原始 CVA6 是完整 in-order core，主要阶段可概括为：

```text
frontend / fetch
  -> instruction queue / realign / compressed handling
  -> decode
  -> issue / scoreboard / operand read
  -> execute units
  -> writeback / commit
  -> exception / CSR / redirect control
```

CVA6 的正确性依赖：

- issue 阶段和 scoreboard 做结构相关、RAW/WAW 等依赖控制。
- execute 与 commit 分离，异常和中断在架构提交点精确处理。
- load/store 通过 LSU、cache/MMU/PMP、store buffer 等机制维护内存语义。

### 4.2 当前 HDV 标量后端

当前后端状态机是：

```text
IDLE
  -> EXECUTE
  -> WAIT_MULT / WAIT_FPU / LSU_AR / LSU_R / LSU_AW / LSU_W / LSU_B
  -> DONE
  -> REDIRECT
```

其工作方式：

1. `scalar_valid_i && scalar_ready_o` 时锁存一个 EP 中的 scalar slots。
2. 对有效 scalar slot 做 `compressed_decoder + decoder` 组合译码。
3. 每周期选择最多两条 simple ALU 指令进入 simple lane。
4. 同周期最多选择一条 complex 指令进入 complex lane，覆盖 branch、CSR、FPU、MULT、LOAD/STORE 以及不能走 simple lane 的指令。
5. simple batch 内检查读写 mask、重复 rd、order barrier、vset RAW；complex lane 检查是否读取 simple batch 同周期写出的寄存器。
6. 完成的指令直接写 `xrf_d/frf_d`，清掉对应 slot valid。
7. 所有 scalar slots 清空后进入 `DONE`，输出 `scalar_ep_done_o`。
8. 若 branch taken，则 `DONE` 后进入 `REDIRECT`，输出 `redirect_valid_o/redirect_pc_o`。

### 4.3 这个模型的优点

- 控制简单，面积小，时序相对容易。
- 不需要完整 CVA6 frontend/issue/commit/CSR/LSU 体系。
- 与 HDV 当前 EP 保序模型匹配：一个 EP 的 scalar slice 完成后，HEU 才认为该 scalar 部分完成。
- EP 内标量指令如果由 VLIWPU/软件保证无依赖，当前 2 simple ALU + 1 complex lane 可以利用常见并行；遇到本地 hazard 时再保守拆开。

### 4.4 这个模型的限制

- 只利用了最常见的 simple ALU/complex 组合；还不是完整 VLIW functional-unit 绑定模型。
- 没有 bypass/scoreboard，不能安全支持跨 EP 提前发射后还保留任意标量 RAW 正确性；当前依赖 HEU/EP 保序。
- 没有精确异常提交点；unsupported/exception 最终只是 `scalar_error_o`。
- load/store 是阻塞式单 outstanding，容易成为性能瓶颈。

---

## 5. 寄存器堆对比

### 5.1 原始 CVA6

CVA6 的寄存器文件与 issue/read-operands、forwarding、scoreboard、commit 绑定：

- XRF/FRF 读写端口由 pipeline 统一调度。
- 写回来自 ALU、LSU、FPU、CSR 等功能单元。
- scoreboard/commit 管理指令结果何时成为架构状态。
- FPU 状态、CSR 状态与异常提交共同维护。

### 5.2 当前 HDV 标量后端

当前后端内部直接定义：

```systemverilog
logic [XLEN-1:0] xrf_d [32];
logic [XLEN-1:0] xrf_q [32];
logic [XLEN-1:0] frf_d [32];
logic [XLEN-1:0] frf_q [32];
```

支持的写源：

- 标量 ALU/branch link/MULT/FPU/LOAD 写回。
- 向量后端 `vsetvli/vsetivli/vsetvl` 返回的 granted VL 写回 `rd`。

支持的读源：

- 标量后端当前执行 slot 的 `rs1/rs2/rs3`。
- 向量后端请求 `rs1/rs2/frs1`，用于 Ara `acc_req.rs1/rs2`。

当前规则：

- `x0` 在每拍末尾强制为 0。
- `vec_operand_req_ready_o` 恒为 1。
- 向量读 XRF/FRF 是组合读；在最新 vector dispatch 中已经加了一拍寄存，避免向量请求直接穿过标量后端到 Ara。

当前缺口：

- 没有多读写端口冲突建模。
- 没有物理寄存器、rename、bypass，这对当前 in-order 顺序后端不是必须。
- FRF 状态没有和完整 FCSR/fflags 精确绑定。
- 没有 ABI 初始化/任务上下文装载接口；复位后 XRF/FRF 全 0，后续需要靠程序自身标量指令或外部机制建立参数。

---

## 6. 指令集支持对比

### 6.1 总体结论

当前后端 **不是完整 RV64IMC + F/D + Zicsr**。

更准确地说：

- RV64I/RV64W：大部分通过 CVA6 decoder + ALU/branch/LSU 路径可执行。
- M：通过 `mult` 路径接入，但需要用具体 benchmark 继续验证 DIV/REM 等长延迟路径。
- C：接入 `compressed_decoder`，标准压缩指令基础路径可走；但 Zcmt/macro 相关输入被简化，不能视为完整压缩扩展生态。
- F/D：接入 `fpu_wrap` 和 FP load/store 的基本路径，但 FCSR/fflags 副作用不完整。
- Zicsr：只有少量 CSR stub，不是完整 Zicsr/用户态 CSR 行为。

### 6.2 RV64I 整数 ALU

| 指令类别 | CVA6 | 当前 HDV 后端 |
|---|---|---|
| `LUI/AUIPC` | 完整支持 | 通过 decoder + ALU 路径支持。 |
| `ADDI/SLTI/SLTIU/XORI/ORI/ANDI` | 完整支持 | 通过 ALU 路径支持。 |
| `SLLI/SRLI/SRAI` | 完整支持 | 通过 ALU 路径支持。 |
| `ADD/SUB/SLL/SLT/SLTU/XOR/SRL/SRA/OR/AND` | 完整支持 | 通过 ALU 路径支持。 |
| RV64 `*W` 算术 | 完整支持 | 通过 ALU 路径支持，依赖 CVA6 ALU 对 op 的处理。 |

风险点：

- 当前 `unsupported` 只看 CVA6 decoder 异常和 FU 分类，不逐条白名单检查 ALU op。因此 decoder 若把某些非目标扩展译成 ALU op，后端可能会尝试执行。需要后续用 ISA 白名单进一步收敛。

### 6.3 分支与跳转

| 指令类别 | CVA6 | 当前 HDV 后端 |
|---|---|---|
| `BEQ/BNE/BLT/BGE/BLTU/BGEU` | 完整支持，含预测/异常/commit 控制。 | branch_unit 真实计算 taken/target。taken 后输出 HDV redirect。 |
| `JAL/JALR` | 完整支持，含 link 写回和异常。 | branch_unit 计算 target，非 branch op 会写 link register。 |
| 分支预测 | 有 BHT/BTB/RAS | 无预测，解析后 redirect。 |
| mispredict 处理 | 完整 pipeline flush | HDV redirect/flush 机制处理。 |
| 非对齐 target 异常 | 完整异常路径 | branch_unit 可给 exception，但当前只转成 `unsupported/error_seen` 类错误，没有真实 trap。 |

当前 branch target 设计约束仍建议保持：

- branch target 必须是 fetch packet / HDV_HINT 后 EP 起点。
- 最好 16B 对齐。

这是为了避免 IPU redirect 到 EP 中间后 VLIWPU 无法正确恢复 packet/slot 边界。

### 6.4 Load/Store

| 指令类别 | CVA6 | 当前 HDV 后端 |
|---|---|---|
| `LB/LH/LW/LD/LBU/LHU/LWU` | 完整 LSU/cache/MMU/PMP/异常支持。 | 单笔 AXI AR/R，按 size/offset 取数并符号扩展。 |
| `SB/SH/SW/SD` | 完整 store buffer/cache 语义。 | 单笔 AXI AW -> W -> B。 |
| `FLW/FLD` | 完整 FP load。 | 通过 LSU 路径写 FRF。`FLW` 使用 NaN-boxing 形式写入。 |
| `FSW/FSD` | 完整 FP store。 | 从 FRF 取 store operand，经 AXI 写出。 |
| misaligned access | 按配置和异常机制处理。 | 直接视为 unsupported/error，不拆分访问。 |
| cache/MMU/PMP | 有 | 无。 |
| 多 outstanding | CVA6 cache/LSU 可复杂处理。 | 无，完全阻塞式单 outstanding。 |
| AMO/LR/SC | 有专用 AMO/cache 支持。 | 没有。见 6.8。 |

重要实现细节：

- 当前 store 通道按 `LSU_AW -> LSU_W -> LSU_B` 顺序发，不同于高性能实现中 AW/W 同时发；功能简单但性能较低。
- 当前 AXI `aw.atop = '0`，所以即使 decoder 把 AMO 归到 STORE，也不会产生原子事务。

### 6.5 M 扩展

| 指令类别 | CVA6 | 当前 HDV 后端 |
|---|---|---|
| `MUL/MULH/MULHSU/MULHU/MULW` | 完整支持 | 通过 `mult` 接入，结果写 XRF。 |
| `DIV/DIVU/REM/REMU` 及 W 变体 | 完整支持，依赖 mult/serdiv 配置。 | 按 `fu == MULT` 交给 `mult`，但尚未针对 DIV/REM 做单独覆盖验证。 |

当前风险：

- 需要检查 `CVA6Cfg` 下 `mult` 是否启用了除法路径，以及 `mult_valid_i`/`mult_ready_o` 协议是否覆盖所有 M op。
- 文档层面不能宣称 M 扩展已经完整验证。

### 6.6 F/D 浮点

| 指令类别 | CVA6 | 当前 HDV 后端 |
|---|---|---|
| FP ALU/FMA/convert/compare/classify | 完整 FPU pipeline + CSR/fflags 处理。 | 接入 `fpu_wrap`，结果写 XRF 或 FRF。 |
| `frm` | 来自完整 CSR regfile。 | 来自内部 `csr_frm_q`。 |
| `fflags` | 异常标志精确累积到 CSR。 | `CSR_FFLAGS` 读恒为 0，FPU exception 只置 `error_seen`，不累积 flags。 |
| `fcsr` | 完整 FRM+FFLAGS。 | 只保存 `frm`，低 5-bit flags 恒为 0。 |
| NaN boxing | CVA6/FPU 完整处理。 | `FLW` load 做了高位全 1 的 NaN-boxing；其他路径依赖 FPU 输出和当前宽度转换，未完整审计。 |
| FP exceptions/trap | 完整异常/CSR 语义。 | 只转为 `scalar_error_o`。 |

结论：当前 F/D 是“有执行路径”，不是“完整浮点架构状态实现”。

### 6.7 C 压缩扩展

| 项目 | CVA6 | 当前 HDV 后端 |
|---|---|---|
| 标准 RVC 解压 | 有 `compressed_decoder` | 已接入。 |
| 16/32-bit 指令边界 | frontend/realign 负责 | HDV VLIWPU/HEU 已提供 `scalar_insn_is_32b_i` 和拼好的 32-bit 指令。 |
| illegal compressed | 完整异常 | decoder exception 最终转成 error，不是真实 trap。 |
| macro/Zcmt | CVA6 有相关 decoder 支撑 | 当前 `is_last_macro_instr_i=0`、`is_double_rd_macro_instr_i=0`、`jump_address_i='0`，不完整。 |

结论：普通 RVC 可以作为“基本支持”，但不要声明 Zcmt/macro 完整支持。

### 6.8 A 扩展 / AMO

| 项目 | CVA6 | 当前 HDV 后端 |
|---|---|---|
| LR/SC | 有 | 无真实实现。 |
| AMO add/swap/and/or/xor/min/max | 有 | 无真实实现。 |
| AXI atomic / cache atomic | 有对应 cache/AMO 路径 | `aw.atop='0`，不会发 atomic。 |

这是一个明确缺口。

即使 CVA6 decoder 会把 AMO 译成 `fu == STORE`，当前轻量 LSU 也只会把它当普通 store 类事务处理，语义不正确。因此如果目标 benchmark 或 runtime 有 AMO/LR/SC，当前后端不能支持。

如果目标仍是“RV64IMC + F/D + Zicsr”，A 扩展不在名字里，可以暂不做；但若目标是通用 Linux/glibc 或多核同步代码，A 必须补。

### 6.9 Zicsr / CSR

当前 CSR stub 支持 CSR 指令编码：

- `CSRRW`
- `CSRRS`
- `CSRRC`
- `CSRRWI`
- `CSRRSI`
- `CSRRCI`

但只对少量 CSR 返回/写入有意义：

| CSR | 当前行为 |
|---|---|
| `cycle` | 返回内部 `cycle_q`。 |
| `time` | 返回内部 `cycle_q`，不是真实 time CSR。 |
| `instret` | 返回内部 `cycle_q`，不是 retired instruction 计数。 |
| `frm` | 保存/返回 `csr_frm_q`。 |
| `fflags` | 读恒为 0，不累积 FPU flags。 |
| `fcsr` | 返回 `{frm, 5'b0}`，写只影响 `frm` 部分。 |
| `vl` | 返回 `csr_vl_q`。 |
| `vtype` | 返回 `csr_vtype_q`。 |
| `vlenb` | 返回参数 `VectorVlenBytes`。 |

缺失 CSR/机制：

- `mstatus/sstatus/ustatus` 等状态寄存器。
- `mepc/mcause/mtval/mtvec` 等 trap CSR。
- `misa`、`mhartid`、`satp`、counter enable 等常见 CSR。
- CSR 权限检查、只读 CSR 写异常、特权级检查。
- `fflags` sticky bits 和 FPU exception flags。
- `vstart/vxrm/vxsat/vcsr` 等向量 CSR。
- `cycle/time/instret` 的准确语义。

结论：当前 Zicsr 是“指令格式可译码，少量 CSR 可读写”，不是完整 Zicsr。

### 6.10 System / Fence / Trap 指令

| 指令 | CVA6 | 当前 HDV 后端 |
|---|---|---|
| `ECALL` | 进入 trap | 不支持真实 trap。 |
| `EBREAK` | 进入 debug/trap | 当前把 `32'h00100073` 特判为不写回、不报 unsupported；但没有 debug/trap 语义。 |
| `MRET/SRET/DRET` | 完整特权返回 | 不支持。 |
| `FENCE` | 按内存顺序语义处理 | 不支持真实语义。 |
| `FENCE.I` | 指令 cache 同步 | 不支持真实语义。 |
| `SFENCE.VMA/HFENCE.*` | MMU/TLB 相关 | 不支持。 |

---

## 7. HDV 特有机制：CVA6 没有，当前后端新增了什么

当前后端有一些不是 CVA6 原 core 的功能，而是为了接 HDV 架构新增的。

### 7.1 EP scalar slice 接口

输入不是 CVA6 frontend 的指令流，而是 HEU 分好的 scalar slots：

```systemverilog
scalar_valid_i
scalar_ready_o
scalar_insn_valid_i[NumSlots]
scalar_insn_i[NumSlots][31:0]
scalar_insn_is_32b_i[NumSlots]
scalar_insn_pc_i[NumSlots]
scalar_ep_done_o
scalar_error_o
```

这意味着：

- 后端一次接收一个 EP 的 scalar 子集。
- EP 内 slot 可能不连续。
- 执行完成的粒度是 scalar slice，而不是单条指令 commit。

### 7.2 向量操作数服务

为了替代 vtrace，当前后端提供：

```systemverilog
vec_operand_req_valid_i
vec_operand_req_ready_o
vec_rs1_addr_i
vec_rs2_addr_i
vec_frs1_addr_i
vec_rs1_data_o
vec_rs2_data_o
vec_frs1_data_o
```

用途：

- 向量 load/store 需要 base address，读 `rs1`。
- strided/indexed 类向量指令可能需要 `rs2`。
- `.vx` 向量指令需要整数 scalar operand。
- `.vf` 向量指令需要浮点 scalar operand，即 `frs1`。

这套接口是 HDV 标量/向量共享寄存器堆的最小实现，不存在于原始 CVA6 core。

### 7.3 vector-to-scalar 写回

向量后端执行 `vsetvli/vsetivli/vsetvl` 后，Ara 返回 granted VL；执行 `vmv.x.s`、`vfmv.f.s` 等 scalar-visible vector 指令后，也需要把结果写回标量寄存器。当前标量后端通过：

```systemverilog
vec_wb_valid_i
vec_wb_rd_i
vec_wb_data_i
vec_wb_is_fpr_i
vec_wb_is_vset_i
```

完成：

- 若 `rd != x0` 且 `vec_wb_is_fpr_i=0`，写回 XRF[rd]。
- 若 `rd != f0` 且 `vec_wb_is_fpr_i=1`，写回 FRF[rd]。
- 若 `vec_wb_is_vset_i=1`，同时更新内部 `csr_vl_q`。

缺口：

- 当前只更新 `vl`，没有完整更新 `vtype`。
- `vstart/vxrm/vxsat/vcsr` 不在这条写回链中。

### 7.4 HDV redirect

当前后端 branch taken 后不直接改自己的 PC，而是输出：

```systemverilog
redirect_valid_o
redirect_pc_o
```

由 HDV top/IPU 接管重取指。这个 redirect 目标必须满足 HDV 对 EP 起点/fetch packet 对齐的约束。

---

## 8. 依赖与并行性对比

### 8.1 原始 CVA6

CVA6 的依赖处理来自：

- scoreboard 追踪未完成目的寄存器。
- issue stage 决定何时可以发射。
- forwarding/bypass 减少 RAW stall。
- commit 保证架构状态有序。
- LSU/store buffer 处理内存依赖。

### 8.2 当前 HDV 标量后端

当前后端没有这些复杂机制，依赖关系由三层共同承担：

1. VLIWPU/p-bit：决定哪些指令可以进同一个 EP。
2. HEU：维护 EP 边界上的 dispatch、scalar done 和 vector acknowledged。
3. 标量后端：一个 EP 内做轻量多发射选择和局部 hazard 检查，并在完成后才拉 `scalar_ep_done_o`。

当前可保证：

- EP 内 simple ALU/complex lane 只在本地 hazard 检查允许时同周期执行；否则保守拆成后续周期。
- 标量后端完成所有写回后才 done。
- 下一 EP 如果依赖上一 EP 的标量结果，在 HEU 保序模型下能读到。

当前不能保证：

- 若未来允许不同 EP 提前进入标量后端并并行执行，则必须增加 scoreboard 或至少增加跨 EP register pending tracking。
- 当前 EP 内并行只覆盖轻量 lane；若未来扩到更宽，仍必须增加更完整的端口仲裁和结构冲突检查。
- memory ordering 目前只靠单 outstanding LSU，简单但低性能；没有复杂 load/store dependency。

---

## 9. 当前冗余与缺失逻辑

### 9.1 看起来冗余但暂时合理的逻辑

| 逻辑 | 为什么存在 | 是否建议删除 |
|---|---|---|
| 本地定义 `scoreboard_entry_t` 等类型 | 为了实例化 CVA6 `decoder/branch_unit/fpu_wrap`，避免拉完整 CVA6 pipeline。 | 不建议删。 |
| `HDV_INTERRUPTS` 常量 | CVA6 decoder 接口需要 interrupts 类型，即使当前中断固定无效。 | 不建议删，除非重写 decoder wrapper。 |
| `branch_resolved_*` 输出 | 调试和 loop/redirect 机制可用。 | 保留。 |
| `redirect_pending_q` 后发 redirect | 避免同周期 DONE/redirect/flush 互相覆盖。 | 保留。 |
| `unused_vec_operand_req_valid` | 当前读口 ready 恒 1，valid 没参与门控，用来消 warning。 | 后续可改为真实请求握手后删除。 |

### 9.2 明确缺失的逻辑

| 缺失项 | 影响 | 优先级 |
|---|---|---|
| 完整 CSR regfile | 无法跑依赖 `mstatus/misa/mhartid/satp` 等 CSR 的通用 runtime。 | 高，如果目标是全 benchmark + 编译器生成胶水。 |
| FFLAGS/FCSR 完整副作用 | 浮点异常标志不正确。 | 中到高，取决于 benchmark 是否检查 flags。 |
| AMO/LR/SC | 不支持 A 扩展，pthread/同步/runtime 可能失败。 | 中；若目标 RV64IMAFDC/Ara benchmark 裸机可先低。 |
| `FENCE/FENCE.I` | cache/内存顺序语义缺失。 | 中。 |
| misaligned load/store 拆分 | 编译器若产生非对齐访问会失败。 | 中。 |
| 完整 trap/exception | unsupported/illegal/load fault 无法进入软件处理。 | 高，如果要跑通用程序。 |
| 标量 EP 内并行执行 | 性能损失，不是功能 bug。 | 中。 |
| 多 outstanding LSU | 性能损失。 | 低到中。 |
| vtype/vstart/vxrm/vxsat/vcsr 维护 | 部分向量 CSR 行为不完整。 | 中。 |
| 任务入口 ABI/context 初始化 | 当前寄存器复位全 0，缺少主核传参机制。 | 高，如果不用程序自身初始化参数。 |

---

## 10. 当前实现能覆盖什么

当前实现适合覆盖：

- 手写/可控的 HDV kernel。
- EP 边界经过 VLIWPU 控制、不会出现复杂跨 EP 乱序依赖。
- 标量主要用于地址递增、循环计数、分支跳转、简单整数运算。
- 向量指令需要从真实 XRF/FRF 获取 `rs1/rs2/frs1`。
- `vset*` 需要把 granted VL 写回标量 XRF。
- 物理地址直通的简单裸机环境。

当前不适合覆盖：

- 完整 OS/特权环境。
- 依赖异常/trap/debug 的程序。
- 依赖完整 CSR 权限和状态的 runtime。
- 依赖 AMO/LR/SC 的同步代码。
- 对 FPU exception flags 有严格要求的测试。
- 随机 RISC-V ISA compliance 全量测试。

---

## 11. 与“全 Ara benchmark”目标的差距

若目标是全 Ara benchmark，而不是只跑当前 `vsaxpy_hdv`，建议按如下顺序补齐。

### 11.1 第一优先级：功能必需

1. 建立任务 ABI/context 初始化机制  
   需要明确 host 如何把 `a0/a1/a2/...`、浮点标量参数、栈指针等写入 XRF/FRF。否则很多 benchmark 的入口参数无法建立。

2. 扩展 CSR stub 到 benchmark 常用集合  
   至少考虑 `misa/mvendorid/marchid/mimpid/mhartid`、`mstatus` 的 FS/VS 位、counter CSR、`vstart/vxrm/vxsat/vcsr`。

3. 完善 FCSR/FFLAGS  
   `fpu_wrap` 给出的 exception flags 需要累积进 `fflags`，`fcsr` 读写要同时覆盖 `frm` 和 `fflags`。

4. 明确 unsupported 指令策略  
   对于当前不支持的 system/AMO/privileged 指令，应该决定是当作 NOP、报 task error，还是进入软件 trap。不能静默误执行。
   **当前状态**：FENCE/FENCE.I 已作为 NOP 处理（单核 in-order 系统中无架构副作用），`ebreak` 可作为显式 HDV task-end marker（通过 `TreatEbreakAsTaskExit=1` 参数控制，默认启用）。

### 11.2 第二优先级：兼容性

1. AMO/LR/SC  
   如果 benchmark runtime 或编译器库使用原子操作，需要真实支持，至少支持 LR/SC 或常见 AMO add/swap。

2. misaligned load/store  
   如果 ABI 或编译器可能产生非对齐访问，需要拆成两笔 AXI 或产生可处理异常。

3. 更完整 RVC/Zcmt  
   标准 RVC 基础已有，但 macro/Zcmt 相关输入目前简化。

4. `FENCE/FENCE.I`  
   裸机单核可先当 NOP，但需要文档化；如果有 self-modifying code 或 cache coherence 需求则必须补。

### 11.3 第三优先级：性能

1. EP 内 scalar slots 并行执行  
   由于 VLIWPU 可保证同 EP 内无依赖，可以增加两个 ALU lane、一个 branch/LSU lane 的简单多发射。

2. LSU AW/W 同拍发射  
   当前 store 先 AW 后 W，功能简单但延迟高。

3. 多 outstanding load/store  
   对标量访存密集的 benchmark 有帮助，但会引入内存依赖和返回乱序问题。

4. 更强的 HEU/后端 credit  
   让不同 EP 的向量指令持续灌入 Ara，同时标量后端维护必要的 register pending 或 EP token。

---

## 12. 文件级清单

### 12.1 当前 HDV 标量后端相关文件

| 文件 | 作用 |
|---|---|
| `hardware/src/scala_backend/hdv_scalar_backend.sv` | 当前标量后端主体。 |
| `hardware/src/hdv/hdv_top.sv` | 实例化标量后端，连接 HEU、vector dispatch、AXI、task done/error。 |
| `hardware/src/hdv/hdv_hybrid_execution_unit.sv` | EP 分 scalar/vector slices，并维护当前 EP 与一项 skid buffer。 |
| `hardware/src/hdv/hdv_vec_dispatch_unit.sv` | 向量后端请求真实标量操作数，向 Ara 发向量指令，并把 vset granted VL 写回标量后端。 |
| `Bender.yml` | 把 `hdv_scalar_backend.sv` 纳入编译。 |

### 12.2 原始 CVA6 对照文件

| 文件 | 对照意义 |
|---|---|
| `hardware/deps/cva6/core/cva6.sv` | 完整 core 顶层。 |
| `hardware/deps/cva6/core/frontend/frontend.sv` | 原始取指/预测入口。 |
| `hardware/deps/cva6/core/decoder.sv` | 当前后端复用的译码器。 |
| `hardware/deps/cva6/core/compressed_decoder.sv` | 当前后端复用的压缩指令解码器。 |
| `hardware/deps/cva6/core/alu.sv` | 当前后端复用的 ALU。 |
| `hardware/deps/cva6/core/branch_unit.sv` | 当前后端复用的 branch target/taken 逻辑。 |
| `hardware/deps/cva6/core/mult.sv` | 当前后端复用的 MULT 路径。 |
| `hardware/deps/cva6/core/fpu_wrap.sv` | 当前后端复用的 FPU wrapper。 |
| `hardware/deps/cva6/core/load_store_unit.sv` | 当前没有复用；可对照完整 LSU 行为。 |
| `hardware/deps/cva6/core/csr_regfile.sv` | 当前没有复用；后续补 CSR 应重点参考。 |
| `hardware/deps/cva6/core/scoreboard.sv` | 当前没有复用；后续跨 EP 提前发射/并行标量执行时可参考。 |
| `hardware/deps/cva6/core/commit_stage.sv` | 当前没有复用；后续若要精确异常，需要参考。 |

---

## 13. 最终判断

当前 `hdv_scalar_backend` 的设计选择是合理的原型路线：

- 它避免把完整 CVA6 core 和 HDV IPU/VLIWPU/HEU 重复连接。
- 它复用了 CVA6 最容易出错的译码、ALU、branch、mult、FPU 部件。
- 它用很小的状态机接上了 HDV 所需的 scalar slice、redirect、向量操作数服务和 vset 写回。

但它还不是完整标量核：

- 指令集覆盖还不是完整 RV64IMC + F/D + Zicsr。
- CSR、异常、FPU flags、AMO、fence、misaligned、trap 等机制缺失或只是 stub。
- EP 内标量并行性没有利用。
- 内存系统是单笔 AXI，和 CVA6 完整 LSU/cache/MMU/PMP 相差很大。

因此后续文档和代码中应把它称为：

```text
CVA6-style HDV scalar backend
```

而不是：

```text
minimal CVA6 core
```

除非后续把 CSR/异常/LSU/scoreboard/commit 等关键机制继续补齐。
