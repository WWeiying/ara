# CVA6_HDV 简化标量后端设计

> 目标：在 `hardware/deps/cva6_hdv/` 副本中，基于 CVA6 现有模块构建一个尽量简化的
> HDV 标量后端。HDV 仍由 IPU/VLIWPU/HEU 负责取指、HINT/p-bit、EP 打包和
> 标量/向量分派；CVA6_HDV 只接收 HEU 的标量切片，执行标量指令、维护共享 XRF/FRF、
> 产生分支 redirect，并给 HDV 向量后端提供真实标量操作数。

---

## 1. 总体结论

当前 HDV 已经有自己的向量路径：

```text
IPU -> VLIWPU -> HEU -> vector slice -> HDV vector backend -> Ara
```

因此 CVA6_HDV 不负责向 Ara 派发向量指令，也不接管 HDV 向量后端。CVA6_HDV 的职责收敛为：

- 执行 `HEU` 分出来的 scalar/system/branch 指令。
- 维护 XRF/FRF，替代 vtrace 提供向量指令的 `rs1/rs2/frs1`。
- 接收向量后端的 vset granted-vl 写回。
- 执行真实 branch/jump，向 HDV IPU 发 redirect。
- 执行标量 load/store，接 `hdv_top` 里预留的 scalar AXI slot。

这版方案不是“魔改完整 CVA6 整核”，而是“从 CVA6 副本中复用必要模块，搭一个 HDV 专用的顺序标量后端”。这样比接入完整 CVA6 pipeline 简单，也比完全自写 decoder/regfile/ALU 稳。

---

## 2. 不修改原始 CVA6

原始目录保持不动：

```text
hardware/deps/cva6/
```

新建副本：

```text
hardware/deps/cva6_hdv/
```

所有 HDV 定制只在 `cva6_hdv` 中完成。这样可以保留 upstream CVA6 作为对照，也方便后续清理、回退或重新同步。

建议新增目录：

```text
hardware/deps/cva6_hdv/hdv/
  cva6_hdv_scalar_backend.sv
  cva6_hdv_scalar_decode.sv
  cva6_hdv_scalar_rf.sv
  cva6_hdv_scalar_lsu.sv
  cva6_hdv_csr_stub.sv
  cva6_hdv_operand_service.sv
  README.md
```

---

## 3. 与 HDV 的边界

### 3.1 保留现有 HDV 分派

现有 HDV 链路保持：

```text
VLIWPU -> HEU -> scalar slice -> CVA6_HDV scalar backend
             -> vector slice -> HDV vector backend -> Ara
```

不把 vector slice 重新喂回 CVA6。这样可以保留当前 VLIWPU/HEU 的架构意义，也避免 CVA6 内部 PC、fetch、commit 与 HDV IPU/VLIWPU 发生双重控制。

### 3.2 VLIWPU 的依赖职责

VLIWPU/p-bit/dep-break 控制的是 EP 粗粒度并行关系：

- 哪些 slot 可以同一个 EP 发给 HEU。
- 哪些 slot 需要切到下一个 EP。
- branch target 必须是 fetch packet/EP 起点。

这能简化标量后端：CVA6_HDV 可以按 EP 内 slot 顺序执行，不需要做复杂双发射和跨 EP 乱序。  
但 VLIWPU 不能替代所有流水线 hazard，因此 CVA6_HDV 内部仍需保证：

- 本 slice 内标量指令按序执行。
- 标量写回完成后才拉 `scalar_accepted_o`。
- load/store 完成后才认为相关指令完成。
- branch resolved 后才确认 redirect 或 not-taken。

---

## 4. 顶层接口

建议 `cva6_hdv_scalar_backend.sv` 接口如下：

```systemverilog
module cva6_hdv_scalar_backend #(
  parameter int unsigned XLEN = 64,
  parameter int unsigned NumSlots = 6,
  parameter type addr_t = logic [XLEN-1:0],
  parameter type axi_req_t = logic,
  parameter type axi_resp_t = logic
) (
  input  logic                         clk_i,
  input  logic                         rst_ni,
  input  logic                         flush_i,

  input  logic                         scalar_valid_i,
  output logic                         scalar_ready_o,
  input  logic [NumSlots-1:0]          scalar_insn_valid_i,
  input  logic [NumSlots-1:0][31:0]    scalar_insn_i,
  input  logic [NumSlots-1:0]          scalar_insn_is_32b_i,
  input  addr_t [NumSlots-1:0]         scalar_insn_pc_i,
  output logic                         scalar_accepted_o,
  output logic                         scalar_error_o,

  output logic                         redirect_valid_o,
  output addr_t                        redirect_pc_o,
  output logic                         branch_resolved_valid_o,
  output logic                         branch_taken_o,
  output addr_t                        branch_pc_o,
  output addr_t                        branch_target_o,

  input  logic                         vec_operand_req_valid_i,
  output logic                         vec_operand_req_ready_o,
  input  logic [4:0]                   vec_rs1_addr_i,
  input  logic [4:0]                   vec_rs2_addr_i,
  input  logic [4:0]                   vec_frs1_addr_i,
  output logic [XLEN-1:0]              vec_rs1_data_o,
  output logic [XLEN-1:0]              vec_rs2_data_o,
  output logic [XLEN-1:0]              vec_frs1_data_o,

  input  logic                         vec_vset_wb_valid_i,
  input  logic [4:0]                   vec_vset_wb_rd_i,
  input  logic [XLEN-1:0]              vec_vset_wb_data_i,

  output axi_req_t                     scalar_axi_req_o,
  input  axi_resp_t                    scalar_axi_resp_i
);
```

### 4.1 accepted 语义

`scalar_accepted_o` 表示当前 scalar slice 已经真正处理完：

- 所有标量 ALU/branch/CSR 指令完成。
- 所有标量 load/store 完成。
- 需要写 XRF/FRF 的结果已经写回。
- branch/jump 已经产生 redirect 或明确 not-taken。

它不是“后端收到了指令”的意思，而是“这个 scalar slice 对后续 EP 来说已经安全完成”。

### 4.2 向量操作数服务

HDV 向量后端发每条向量指令前，从 CVA6_HDV 读：

- `rs1`: base address、AVL、`.vx` 标量源等。
- `rs2`: stride、index、部分向量配置源。
- `frs1`: `.vf` 浮点标量源。

第一版可以做成组合读或一拍读；若后续 RF 端口冲突，可以加一个小仲裁：

```text
标量后端内部读 RF 优先
向量 operand request 等待一拍
```

由于 HEU 当前一个 EP outstanding，且 EP accepted 后才进入下一 EP，这个低速读口通常足够。

### 4.3 vset 写回

`vsetvli/vsetivli/vsetvl` 仍走 HDV 向量后端到 Ara。Ara 返回 granted vl 后，向量后端必须通过 `vec_vset_wb_*` 写回 CVA6_HDV XRF。

关键约束：

- 如果 vset 指令写 `rd != x0`，vector slice accepted 必须等 vset 写回完成。
- 下一 EP 中使用该 rd 的标量指令才能读到正确 vl。

---

## 5. CVA6 模块复用与裁剪

### 5.1 复用

| CVA6 模块 | 用法 |
|---|---|
| `compressed_decoder.sv` | 复用 RVC 解压，避免真实二进制中的 `c.add/c.bnez/c.ret` 无法执行。 |
| `decoder.sv` 或其 decode 表 | 优先复用译码定义；若直接接原 decoder 太重，可抽取 opcode/funct 到 `cva6_hdv_scalar_decode.sv`。 |
| `alu.sv` | 复用 RV64I/W ALU、比较、移位。 |
| `branch_unit.sv` 或 branch immediate 逻辑 | 复用 target 计算和 taken 判断，或在简化 decode 中重写同等逻辑。 |
| `multiplier.sv` | 可选复用，至少支持 `MUL/MULW`。 |
| `ariane_regfile.sv` | 作为 XRF；FRF 可复用 CVA6 FP regfile 或先做简单 32x64 regfile。 |
| `ariane_pkg` / `riscv` package | 复用指令枚举、立即数格式、CSR 编码等定义。 |

### 5.2 不复用

| CVA6 模块 | 原因 |
|---|---|
| frontend / PC gen / I-cache / branch predictor | HDV IPU/VLIWPU 已负责取指和 PC。 |
| instruction queue | HDV HEU 已按 EP 给出 slot；后端只需锁存 scalar slice。 |
| issue_stage / scoreboard | 极简后端按序执行一个 scalar slice，不做 CVA6 多发射。 |
| commit_stage | 极简后端完成一条写一条；slice 完成后拉 accepted。 |
| cache/MMU/PTW/PMP | 初期物理地址直通，标量 LSU 走预留 AXI。 |
| debug/RVFI/interrupt/CLIC | 原型不需要。 |
| 完整 csr_regfile | 用 `cva6_hdv_csr_stub.sv` 替代。 |

### 5.3 设计取舍

这个版本比完整 CVA6_HDV 更简单，但也承担一个边界：

- 它能稳定覆盖 HDV hand-asm kernel 和当前 vsaxpy 类任务。
- 对 compiler 自动生成的大型 RV64GC 标量胶水，可能仍需补指令。

但由于复用了 CVA6 的 RVC/ALU/branch/regfile 基础模块，补指令成本比完全自写低。

---

## 6. 内部状态机

### 6.1 slice 锁存

当 `scalar_valid_i & scalar_ready_o`：

- 锁存 `scalar_insn_valid_i`
- 锁存 `scalar_insn_i`
- 锁存 `scalar_insn_is_32b_i`
- 锁存 `scalar_insn_pc_i`
- 找到最低有效 slot，进入 EXECUTE

### 6.2 顺序执行

状态建议：

```text
IDLE
  -> DECODE
  -> EXEC_ALU / EXEC_BRANCH / EXEC_LSU / EXEC_CSR / EXEC_FP
  -> WRITEBACK
  -> NEXT_SLOT
  -> DONE
```

每次只处理一个有效 scalar slot。完成后清该 slot valid，再找下一个。所有 slot 清空后：

- 拉 `scalar_accepted_o` 一拍。
- 回到 IDLE。

### 6.3 分支

branch/jump 在 EXEC_BRANCH 中计算：

- not-taken：只产生 `branch_resolved_valid_o`，不产生 redirect。
- taken：产生 `redirect_valid_o` 和 `redirect_pc_o`。

为匹配当前 HDV flush 语义，redirect 可以延后一拍发出，避免同周期 flush 抹掉本 scalar slice 的 accepted。

建议同时输出明确事件：

```text
branch_resolved_valid_o
branch_taken_o
branch_pc_o
branch_target_o
```

这样 HDV 的 loop lock/loop exit 不必继续靠“一拍内没有 redirect”推断。

---

## 7. 指令子集

### 7.1 第一阶段必须有

| 类别 | 指令 |
|---|---|
| RV64I ALU | `LUI AUIPC ADDI SLTI SLTIU XORI ORI ANDI SLLI SRLI SRAI ADD SUB SLL SLT SLTU XOR SRL SRA OR AND` |
| RV64 W | `ADDIW SLLIW SRLIW SRAIW ADDW SUBW SLLW SRLW SRAW` |
| branch/jump | `BEQ BNE BLT BGE BLTU BGEU JAL JALR` |
| load/store | `LB LH LW LD LBU LHU LWU SB SH SW SD` |
| RVC | `c.add c.addi c.mv c.li c.lw c.ld c.sw c.sd c.beqz c.bnez c.j c.jr c.jalr c.ret c.nop` |
| CSR stub | `rdcycle`/`cycle` 至少不能非法 |

### 7.2 第二阶段

| 类别 | 指令 |
|---|---|
| M | `MUL MULW`，之后再补 `MULH/MULHU/MULHSU` |
| FP load/store | `FLW FLD FSW FSD` |
| FP move | `FMV.X.W FMV.W.X FMV.X.D FMV.D.X` |
| FP arithmetic | 至少 `FMUL.S FADD.S` |
| fence | 作为 LSU outstanding drain |

### 7.3 可延后

- `DIV/REM`
- 完整特权 CSR
- exception/interrupt/debug
- cache/MMU/PMP

---

## 8. 标量 LSU

第一版 LSU 不接 CVA6 D-cache/MMU，只做轻量 AXI master：

- 单 outstanding。
- 物理地址直通。
- load 支持 B/H/W/D，带 signed/unsigned extend。
- store 支持 B/H/W/D byte strobe。
- `fence` 等 outstanding 清空后完成。

接入点是 `hdv_top` 当前预留的 scalar AXI slot：

```text
Ara | scalar reserved | HDV imem
```

这样不需要改 AXI mux 端口数和 system ID 宽度。

---

## 9. CSR Stub

最小 CSR 行为：

| CSR | 行为 |
|---|---|
| `cycle/time/instret` | 返回自增计数或 0；`rdcycle` 不报错。 |
| `frm` | 返回默认 rounding mode，通常 RNE。 |
| `vl/vtype/vlenb` | 可由向量后端同步维护；至少要能被读取。 |
| 其他 CSR | 初期返回 0 或置 `scalar_error_o`，由测试决定。 |

---

## 10. 对当前 HDV 的修改点

后续实现时需要改这些入口，但不要现在直接动原 CVA6：

| 文件 | 动作 |
|---|---|
| `hardware/src/hdv/hdv_top.sv` | 增加 `USE_CVA6_HDV_SCALAR` 路径，把 `hdv_scalar_*` 接到 `cva6_hdv_scalar_backend`。 |
| `hardware/src/hdv/hdv_vec_dispatch_unit.sv` | 去掉 vtrace 操作数模式，改为向 CVA6_HDV operand service 请求 rs1/rs2/frs1。 |
| `hardware/tb/ara_tb.sv` | 增加 mock scalar 与 CVA6_HDV scalar 的切换开关。 |
| `hardware/Makefile` / filelist | 增加 `hardware/deps/cva6_hdv/hdv/*.sv` 和必要 CVA6 复用模块。 |

---

## 11. 落地顺序

### Phase 0：副本与 filelist

- 复制 `hardware/deps/cva6` 到 `hardware/deps/cva6_hdv`。
- 新增 `hardware/deps/cva6_hdv/hdv/`。
- 新增 HDV 专用 filelist，先只编译复用模块和新建后端。

### Phase 1：整数标量 slice

- 实现 `cva6_hdv_scalar_backend` 的 IDLE/DECODE/EXEC_ALU/WRITEBACK/DONE。
- 复用或抽取 CVA6 compressed decoder。
- 跑通 `addi/add/sub/slli/bnez/jalr/ret` 这一类 vsaxpy 控制流。

### Phase 2：真实 branch redirect

- branch taken 输出 `redirect_valid_o/redirect_pc_o`。
- branch resolved 输出明确 taken/not-taken 事件。
- HDV loop lock 改用明确 branch resolved 事件。

### Phase 3：operand service 替代 vtrace

- `hdv_vec_dispatch_unit` 发向量指令前请求 rs1/rs2/frs1。
- `.vx/.vf/load/store/vset` 使用真实 RF 值。
- 保留 vtrace 对照模式作为 debug 断言，但不再作为功能来源。

### Phase 4：vset 写回

- 向量后端收到 granted vl 后写回 CVA6_HDV XRF。
- vector accepted 等待 vset 写回完成。
- 验证下一个 EP 的 `sub a?, a?, vl_rd` 能读到正确值。

### Phase 5：LSU/FP/MUL

- 接 scalar AXI LSU。
- 加 FLW/FSW/FLD/FSD、FMV、MUL/MULW。
- 逐步扩展到 `vsscal/vsdot/vsgemv/vsger`。

---

## 12. 最小成功标准

按顺序判断是否成功：

1. `cva6_hdv` 副本能独立参与编译。
2. scalar slice 中一条 `addi` 能写回 XRF。
3. `bnez` 能基于真实 XRF 产生 redirect。
4. `hdv_vec_dispatch_unit` 不再用 vtrace 功能值，而是从 CVA6_HDV RF 取 `rs1/rs2`。
5. `vsetvli` 的 granted vl 能写回 XRF。
6. `vsaxpy_hdv` 的地址、AVL、loop counter 都来自真实标量执行结果。

---

## 13. 主要风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| VLIWPU 依赖信息不足 | 如果 p-bit 把存在 RAW 的 scalar/vector 放进同一 EP，极简后端不会自动修。 | 先保证打包工具保守；必要时增强 VLIWPU dep-break。 |
| vector accepted 过早 | vset request accepted 不代表 vl 已写回。 | vset 写回完成后再 accepted。 |
| RVC 接入细节 | 16-bit 指令高半字清零、PC 是 halfword PC。 | 第一阶段专门测 `c.bnez/c.ret/c.add`。 |
| CSR stub 太弱 | `rdcycle/frm/vl/vtype` 缺失会导致 kernel 失败。 | CSR stub 第一阶段就做。 |
| 自建 LSU 语义不全 | 子字 sign extend、store strobe 容易错。 | LSU 单元测试覆盖 B/H/W/D load/store。 |

这版方案的核心取舍是：**保留 HDV 的标量/向量分派，不接管向量路径；从 CVA6 复用基础执行部件，但不搬完整 CVA6 pipeline**。这样标量后端尽可能简单，同时仍能逐步替换 mock 和 vtrace。
