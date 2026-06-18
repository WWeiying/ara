# HDV Prototype RTL Code Walkthrough

本文档逐语段说明 `hardware/src/hdv` 下新增的 Hybrid Decoupled Vector (HDV) 原型 RTL。当前这些模块仍是 HDV 前端原型，但 `hdv_top` 已经实例化 Ara 作为向量后端 shell，并参考原始 `ara_system` 将 Ara memory port 与预留的标量 memory master 汇成统一 system AXI 出口。

> **近期信号重命名** (2026-06):
> 本文档中的信号名以 RTL 实际代码为准。以下批量重命名已应用到所有 RTL 和 TB 文件：
> - `*_accepted_*` → `*_ep_done_*` (scalar 真正执行完成) 或 `*_ep_acknowledged_*` (向量 operand 安全/EP 前端推进)
> - `*_pending_*` (HEU 内部) → `*_slice_outstanding_*`
> - `*_store_pending_*` → `*_store_inflight_*`
> - `AutoExpectedEpAccepts` → `AutoExpectedEpAcknowledges`
> - `vq_insn_q/rs1_q/rs2_q` → `vq_q` (`vq_entry_t` 结构化 command window)
> - `real_wait_drained_*` → `real_ep_operands_captured_*`
> - `real_wait_vset_seen_*` → `real_ep_vset_wb_done_*`
>
> 文档正文中的示例代码片段可能仍使用旧名。请以 `hardware/src/` 下实际 RTL 代码为准。

## 文件总览

| 文件 | 模块 | 作用 |
|---|---|---|
| `hdv_pkg.sv` | `hdv_pkg` | HDV CSR 地址、指令类别、任务状态类型定义 |
| `hdv_task_interface_unit.sv` | `hdv_task_interface_unit` | Task Interface Unit (TIU)，提供任务 CSR 接口 |
| `hdv_task_schedule_unit.sv` | `hdv_task_schedule_unit` | Task Schedule Unit (TSU)，用 FIFO 管理任务提交顺序 |
| `hdv_instruction_prefetch_unit.sv` | `hdv_instruction_prefetch_unit` | Instruction Prefetch Unit (IPU)，双 64B buffer 取指 |
| `hdv_vliw_pack_unit.sv` | `hdv_vliw_pack_unit` | VLIW Pack Unit，按 hint header 和依赖边界切 execute packet |
| `hdv_hybrid_execution_unit.sv` | `hdv_hybrid_execution_unit` | Hybrid Execution Unit 前端分派，把标量/向量指令分流 |
| `hdv_vec_dispatch_unit.sv` | `hdv_vec_dispatch_unit` | HEU 向量 EP 到 Ara 单指令 accelerator request 的适配器 |
| `cva6_hdv_scalar_backend.sv` | `cva6_hdv_scalar_backend` | HDV 专用真实标量后端，复用 CVA6 部件执行 scalar slice |
| `hdv_mock_host_core.sv` | `hdv_mock_host_core` | 仿真用主核/标量后端模型，负责写 task CSR、模拟分支、计数 EP accepted |
| `hdv_top.sv` | `hdv_top` | 顶层 wrapper，连接 HDV 前端、Ara shell 和统一 AXI memory port |

## `hdv_pkg.sv`

### 包声明

`package hdv_pkg;` 定义 HDV 原型中多个模块共享的常量和类型。所有使用指令类别或任务 CSR 地址的模块都通过 `import hdv_pkg::*;` 引入这些定义，避免每个模块重复写本地常量。

### CSR 地址定义

```systemverilog
localparam logic [11:0] HDV_CSR_VTASK_ADDR   = 12'h7c0;
localparam logic [11:0] HDV_CSR_VTASK_PADDR  = 12'h7c1;
localparam logic [11:0] HDV_CSR_VTASK_START  = 12'h7c2;
localparam logic [11:0] HDV_CSR_VTASK_STATUS = 12'h7c3;
```

这四个地址对应论文中的任务控制 CSR：

- `VTASK_ADDR`: 任务入口地址。
- `VTASK_PADDR`: 任务描述符地址。
- `VTASK_START`: 写 1 触发任务提交。
- `VTASK_STATUS`: 任务状态寄存器，包含 busy/done/error。

当前地址宽度为 12 bit，匹配 RISC-V CSR 编码宽度，也方便后续接入真实 CSR decode。

### 指令分类类型

```systemverilog
typedef enum logic [1:0] {
  HDV_INST_SCALAR = 2'b00,
  HDV_INST_VECTOR = 2'b01,
  HDV_INST_SYSTEM = 2'b10,
  HDV_INST_BRANCH = 2'b11
} hdv_inst_class_e;
```

`hdv_inst_class_e` 是 VLIWPU 到 HEU 的指令类别接口。当前主要用于区分：

- `HDV_INST_VECTOR`: 派发到向量流水线。
- 其它类别：派发到标量流水线。

`SYSTEM` 和 `BRANCH` 暂时仍从 HEU 标量侧输出，后续可以在标量流水线或专门控制模块中处理 CSR、异常、跳转和 flush。

### 任务状态类型

```systemverilog
typedef struct packed {
  logic busy;
  logic done;
  logic error;
} hdv_task_status_t;
```

该结构体描述任务状态位。当前代码中没有直接使用这个类型作为端口，而是保留为后续把状态总线结构化时使用。

## `hdv_task_interface_unit.sv`

### 模块参数和类型

```systemverilog
parameter int unsigned XLEN = 64,
parameter type addr_t = logic [XLEN-1:0]
```

`XLEN` 决定 CSR 数据宽度和地址宽度，默认 64 bit。`addr_t` 用参数化类型表示任务入口地址和任务描述符地址，便于后续适配 32 bit 或 64 bit 系统。

### CSR 端口

```systemverilog
input  logic         host_tiu_csr_valid_i,
input  logic         host_tiu_csr_write_i,
input  logic [11:0]  host_tiu_csr_addr_i,
input  logic [XLEN-1:0] host_tiu_csr_wdata_i,
output logic         tiu_host_csr_ready_o,
output logic [XLEN-1:0] tiu_host_csr_rdata_o,
output logic         tiu_host_csr_error_o,
```

这是一个最小 CSR-like 接口：

- `host_tiu_csr_valid_i`: 表示本周期有 CSR 访问。
- `host_tiu_csr_write_i`: 1 表示写，0 表示读。
- `host_tiu_csr_addr_i`: 访问地址。
- `host_tiu_csr_wdata_i`: 写数据。
- `tiu_host_csr_ready_o`: 当前实现恒为 1，表示 TIU 不会反压 CSR 访问。
- `tiu_host_csr_rdata_o`: 读返回数据。
- `tiu_host_csr_error_o`: 访问非 HDV CSR 地址时置位。

### 任务输出端口

```systemverilog
output logic  tiu_tsu_task_valid_o,
input  logic  tsu_tiu_task_ready_i,
output addr_t tiu_tsu_task_entry_o,
output addr_t tiu_tsu_task_desc_o,
```

该接口连接 TSU。TIU 在软件写 `VTASK_START` 后置 `tiu_tsu_task_valid_o`，并把当前 `VTASK_ADDR` 和 `VTASK_PADDR` 输出为任务入口和任务描述符地址。TSU 通过 `tsu_tiu_task_ready_i` 接收任务。

### 状态回传端口

```systemverilog
input  logic top_tiu_task_busy_i,
input  logic tsu_tiu_task_done_i,
input  logic tsu_tiu_task_error_i,
output logic tiu_tsu_status_clear_o
```

这些信号连接任务调度或任务控制层：

- `top_tiu_task_busy_i`: 外部告诉 TIU 当前 HDV 仍忙。
- `tsu_tiu_task_done_i`: 任务完成事件，TIU 锁存 DONE。
- `tsu_tiu_task_error_i`: 任务错误事件，TIU 锁存 ERROR。
- `tiu_tsu_status_clear_o`: 软件写 `VTASK_STATUS` 的 DONE/ERROR 位时产生，用于清除 TSU 状态。

### 内部寄存器

```systemverilog
addr_t vtask_addr_d,  vtask_addr_q;
addr_t vtask_paddr_d, vtask_paddr_q;
logic  task_valid_d,  task_valid_q;
logic  done_d,        done_q;
logic  error_d,       error_q;
logic  start_pulse;
```

这些寄存器分为三类：

- `vtask_addr_q/vtask_paddr_q`: 保存软件写入的任务地址。
- `task_valid_q`: 保存“有一个任务等待 TSU 接收”的状态。
- `done_q/error_q`: 保存软件可读的任务完成/错误状态。

代码使用 `_d/_q` 风格，组合逻辑计算下一状态，时序逻辑在时钟沿更新，符合常见 RTL 写法。

### CSR ready 和 error

```systemverilog
assign tiu_host_csr_ready_o = 1'b1;
assign tiu_host_csr_error_o = host_tiu_csr_valid_i
                   & (host_tiu_csr_addr_i != HDV_CSR_VTASK_ADDR)
                   & ...
```

TIU 当前不做等待，所有 CSR 访问单周期响应。`tiu_host_csr_error_o` 只在 `host_tiu_csr_valid_i` 有效且地址不属于四个 HDV CSR 时置位。

### START 检测

```systemverilog
assign start_pulse = host_tiu_csr_valid_i & host_tiu_csr_write_i
                   & (host_tiu_csr_addr_i == HDV_CSR_VTASK_START)
                   & host_tiu_csr_wdata_i[0];
```

软件向 `VTASK_START` 写 bit0=1 即触发一次任务提交。这里没有真正保存 START 寄存器，而是将写操作解释为 pulse。

### CSR 读多路选择

`p_read_mux` 根据 `host_tiu_csr_addr_i` 返回不同 CSR 数据：

- 读 `VTASK_ADDR`: 返回 `vtask_addr_q`。
- 读 `VTASK_PADDR`: 返回 `vtask_paddr_q`。
- 读 `VTASK_START`: bit0 返回 `task_valid_q`，表示是否有任务等待提交。
- 读 `VTASK_STATUS`: bit0 为 `top_tiu_task_busy_i | task_valid_q`，bit1 为 DONE，bit2 为 ERROR。

BUSY 由外部 busy 和 TIU 内部 pending task 共同决定，避免任务还没被 TSU 接收时软件读到 idle。

### CSR 写和状态更新

`p_next` 首先保持当前状态，然后处理 CSR 写：

- 写 `VTASK_ADDR`: 更新任务入口地址。
- 写 `VTASK_PADDR`: 更新任务描述符地址。
- 写 `VTASK_STATUS`: bit1/bit2 采用 write-one-clear 语义，清除 DONE/ERROR。

随后处理任务握手：

```systemverilog
if (task_valid_q && tsu_tiu_task_ready_i) begin
  task_valid_d = 1'b0;
end
```

如果 TSU 已经接收任务，则清除 pending valid。

再处理 `start_pulse`：

- 如果当前没有 pending task，或者同周期 TSU 正好 ready 接收旧 task，则允许提交新 task。
- 如果已有 pending task 且 TSU 不 ready，则置 `error_d`，表示重复 start。

最后处理硬件完成/错误事件：

```systemverilog
if (tsu_tiu_task_done_i)  done_d  = 1'b1;
if (tsu_tiu_task_error_i) error_d = 1'b1;
```

这两段放在组合逻辑末尾，因此如果软件 clear 和硬件 done/error 同周期发生，硬件事件优先，不会丢失完成或错误。

### 时序寄存器

`p_regs` 在复位时清零所有寄存器，正常周期加载 `_d`。这里 reset 只作用于少量控制寄存器，合理。

## `hdv_task_schedule_unit.sv`

### 模块定位

TSU 负责接收 TIU 提交的任务，并按顺序把任务发给 IPU。它是任务级 FIFO 调度器，不关心指令内容。

### 参数

```systemverilog
parameter int unsigned QueueDepth = 4
```

`QueueDepth` 是任务 FIFO 深度，默认 4。任务项由入口地址和描述符地址组成。

### 输入输出接口

TSU 有两组 ready/valid：

- `task_in_*`: 来自 TIU。
- `task_out_*`: 发往 IPU。

还有任务完成状态：

- `tsu_tiu_task_done_i`: 外部任务控制器确认整个 task 完成。
- `tsu_tiu_task_error_i`: 整个 task 出错。
- `tsu_top_busy_o/tsu_top_done_o/tsu_top_error_o`: 给 TIU 和顶层使用。

### FIFO 数据结构

```systemverilog
typedef struct packed {
  addr_t entry;
  addr_t desc;
} task_t;
```

一个 task FIFO entry 包含：

- `entry`: 任务指令入口 PC。
- `desc`: 任务描述符地址。

### `fifo_v3` 实例

TSU 调用 `common_cells` 中的 `fifo_v3`：

```systemverilog
fifo_v3 #(
  .FALL_THROUGH (1'b1),
  .DEPTH        (QueueDepth),
  .dtype        (task_t)
) i_task_queue (...)
```

`FALL_THROUGH=1` 允许 FIFO 空时新写入的数据快速从输出侧可见，降低任务启动延迟。`dtype` 直接使用结构体，代码可读性较好。

### 入队逻辑

```systemverilog
assign tsu_tiu_task_ready_o = !fifo_full;
assign fifo_push = tiu_tsu_task_valid_i & tsu_tiu_task_ready_o;
```

只要 FIFO 未满，TSU 可以接受 TIU 的任务。入队握手成功时 push。

### 出队逻辑

```systemverilog
assign tsu_ipu_task_valid_o = !fifo_empty & !active_q;
assign fifo_pop = tsu_ipu_task_valid_o & ipu_tsu_task_ready_i;
```

TSU 一次只允许一个 active task。只有当前没有 active task 且 FIFO 非空时，才向 IPU 发出下一个任务。

### busy/done/error

```systemverilog
assign tsu_top_busy_o  = active_q | !fifo_empty;
assign tsu_top_done_o  = done_q;
assign tsu_top_error_o = error_q;
```

`tsu_top_busy_o` 表示已有 active task 或还有排队任务。`tsu_top_done_o/tsu_top_error_o` 是粘滞状态，由任务完成/错误事件置位，由 `tiu_tsu_status_clear_i` 或 `flush_i` 清除。

### 状态机逻辑

TSU 没有显式 enum 状态，只用 `active_q` 表示是否有任务正在执行：

- `fifo_pop`: 进入 active，清除旧 done/error。
- `active_q && tsu_tiu_task_error_i`: 当前任务失败，退出 active，置 error。
- `active_q && tsu_tiu_task_done_i`: 当前任务完成，退出 active，置 done。
- `tiu_tsu_status_clear_i`: 只清除 done/error，不影响 active task。
- `flush_i`: 清除 active/done/error。

### 时序寄存器

`active_q/done_q/error_q` 复位清零，正常周期更新。FIFO 自身由 `fifo_v3` 管理。

## `hdv_instruction_prefetch_unit.sv`

### 模块定位

IPU 接收 TSU 派发的 task，从 `tsu_ipu_task_entry_i` 开始按 128-bit fetch packet 取指，写入两个 64B buffer，然后向 VLIWPU 输出 packet。第一个 128-bit packet 返回后即可开始输出，不再等待整个 64B buffer 填满。

当前 IPU 是原型：它实现双 buffer、取指请求/响应握手、redirect 和 loop lock 接口，但没有解析任务描述符，也没有完整的 loop 自动识别。

### 参数和局部常量

```systemverilog
FetchPacketWidth = 128
BufferBytes      = 64
PacketBytes      = FetchPacketWidth / 8
PacketsPerBuffer = BufferBytes / PacketBytes
```

默认 128-bit packet 等于 16B，64B buffer 可容纳 4 个 packet。`LastPacketIdx` 是 buffer 内最后一个 packet 下标。

### task 接口

```systemverilog
input  logic  tsu_ipu_task_valid_i,
output logic  ipu_tsu_task_ready_o,
input  addr_t tsu_ipu_task_entry_i,
input  addr_t tsu_ipu_task_desc_i,
```

IPU 在 `IDLE` 状态 ready。接收 task 后锁存入口地址和描述符地址。`tsu_ipu_task_desc_i` 当前只锁存并通过 `ipu_top_task_desc_o` 输出，给后续任务控制器或访存模块使用。

### instruction memory 接口

```systemverilog
output logic ipu_mem_req_valid_o,
input  logic mem_ipu_req_ready_i,
output addr_t ipu_mem_req_addr_o,
input  logic mem_ipu_rsp_valid_i,
output logic ipu_mem_rsp_ready_o,
input  logic [FetchPacketWidth-1:0] mem_ipu_rsp_data_i,
```

请求和响应都采用 ready/valid：

- `ipu_mem_req_valid_o && mem_ipu_req_ready_i`: 发出一个取指请求。
- `mem_ipu_rsp_valid_i && ipu_mem_rsp_ready_o`: 接收一个 128-bit packet。

IPU 允许多个 in-order outstanding request。它用 `fill_req_idx_q` 记录下一条 request 的 packet index，用 `fill_rsp_idx_q` 记录下一条 response 写回的 packet index。下游可通过 `mem_ipu_req_ready_i` 限制 outstanding 深度。

### packet 输出接口

```systemverilog
output logic ipu_vliwpu_packet_valid_o,
input  logic vliwpu_ipu_packet_ready_i,
output logic [FetchPacketWidth-1:0] ipu_vliwpu_packet_o,
output addr_t ipu_vliwpu_packet_pc_o,
```

`ipu_vliwpu_packet_o` 来自当前 active buffer，`ipu_vliwpu_packet_pc_o` 是对应 packet 的 PC。VLIWPU 通过 `vliwpu_ipu_packet_ready_i` 接收。

### 控制接口

```systemverilog
input logic redirect_valid_i,
input addr_t redirect_pc_i,
input logic loop_lock_i,
input logic loop_exit_i,
input logic top_ipu_task_complete_i,
```

- `redirect_valid_i`: 后端发现分支/跳转，需要从新 PC 重新取指。
- `loop_lock_i`: 外部显式 loop buffer 锁定控制；该信号表示外部已经知道循环还会 taken，因此保留强制 replay 语义。
- `loop_exit_i`: 自动 loop lock 的退出事件；后向 branch 已被标量后端接收且没有 taken redirect。
- `top_ipu_task_complete_i`: 整个任务完成，IPU 回到 idle。

### 状态机

```systemverilog
typedef enum logic [1:0] {
  IDLE,
  FILL,
  SERVE
} state_e;
```

三个状态含义：

- `IDLE`: 等待 TSU task。
- `FILL`: 等待任务或 redirect 后的第一个 packet 返回。
- `SERVE`: 从 `active_buf` 向 VLIWPU 输出已有效的 packet。初始阶段 `fill_buf==active_buf`，边输出边继续填当前 buffer；当前 buffer 填完后，`fill_buf` 切到另一个 buffer 做背景预取。

### 双 buffer 寄存器

```systemverilog
buffer_t buffer_a_q;
buffer_t buffer_b_q;
logic active_buf_q;   // 当前输出 packet 来自哪个 buffer
logic fill_buf_q;     // 当前背景填充哪个 buffer
logic bg_fill_done_q; // 背景填充已完成标志
logic [PacketsPerBuffer-1:0] buffer_a_valid_q;
logic [PacketsPerBuffer-1:0] buffer_b_valid_q;
```

`active_buf_q` 和 `fill_buf_q` 交替，通过 buffer 切换实现乒乓。`buffer_*_valid_q` 标记每个 128-bit packet 是否已经由 memory response 写回，避免 early-serve 读到未填完的 entry。`bg_fill_done_q` 在背景填充完成时置 1，在 buffer 切换时清 0。

buffer 数据本身不走复位，只在 `accept_rsp` 时写入对应 entry。

### 请求/响应控制

```systemverilog
assign ipu_mem_req_valid_o = ((state_q == FILL) |
                          (state_q == SERVE & !bg_fill_done_q & !loop_blocks_bg_fetch)) &
                         !fill_req_done_q;
assign ipu_mem_rsp_ready_o = ((state_q == FILL) | (state_q == SERVE));
```

FILL 状态：只等待第一个 packet 返回。返回后进入 SERVE。
SERVE 状态：只要 `bg_fill_done_q=0` 且没有被 loop lock 抑制背景预取，就持续发请求，与输出并行进行。初始阶段这些请求继续填当前 active buffer；当前 active buffer 填满后，请求转为填另一个背景 buffer。`fill_req_done_q` 只表示当前 fill buffer 的 request 已全部发出，不表示 response 已全部返回；response 完成由 `fill_rsp_idx_q` 到达 `LastPacketIdx` 判断。task complete、redirect、flush 同周期会抑制新的 request，避免旧 PC 再进入取指 AXI bridge。

### 地址生成

```systemverilog
assign ipu_mem_req_addr_o = fetch_base_q + addr_t'(fill_req_idx_q * PacketBytes);
```

`fetch_base_q` 指向正在填充的 buffer 的起始地址；切换时通过 `fetch_base_d += BufferBytes` 提前推进，指向下一个待填充块。request 侧用 `fill_req_idx_q` 生成地址，response 侧用 `fill_rsp_idx_q` 写回对应 buffer entry。

### FILL 状态（首包等待）

FILL 状态在第一个 response 返回后立即切换到 SERVE：

- `active_buf_d = fill_buf_q`: 当前填充 buffer 立即成为执行 buffer。
- `buffer_*_valid_d[0] = 1`: 第一个 packet 标记为有效。
- `exec_base_d = fetch_base_q`: 执行 base 锁定为当前 buffer 的起始地址。
- request 侧继续用 `fill_req_idx_q` 发后续 packet 请求，response 侧继续用 `fill_rsp_idx_q` 标记后续 packet valid。

若 `PacketsPerBuffer==1`，第一个 response 同时也是 `fill_done`，此时 `fill_buf_d = !fill_buf_q`，`fetch_base_d += BufferBytes`，直接开始背景预取。

### SERVE 状态（输出 + 背景预取）

**active/background 填充**（`accept_rsp` 时）：

- `fill_rsp_idx_q < LastPacketIdx`：递增 `fill_rsp_idx_d`。
- `fill_rsp_idx_q == LastPacketIdx` 且 `fill_buf_q == active_buf_q`：early-serve 阶段的 active buffer 填完，`fill_buf` 切到另一个 buffer，`fetch_base` 推进到下一块，开始背景预取。
- `fill_rsp_idx_q == LastPacketIdx` 且 `fill_buf_q != active_buf_q`：背景填充完成，置 `bg_fill_done_d = 1`，等待 active buffer 消费完后切换。

**输出控制**：

```systemverilog
assign active_packet_valid = active_buf_q ? buffer_b_valid_q[exec_idx_q]
                                          : buffer_a_valid_q[exec_idx_q];
assign effective_loop_fetch_lock = loop_lock_i | auto_loop_lock_q;
assign bg_stall = (exec_idx_q == LastPacketIdx) & !bg_fill_done_q & !effective_loop_fetch_lock
                & (fill_buf_q != active_buf_q);
assign ipu_vliwpu_packet_valid_o = (state_q == SERVE) & active_packet_valid
                                 & !bg_stall & !loop_wait_q;
```

普通 packet 只有在对应 valid bit 已置位后才会输出；如果 VLIWPU 消费速度追上取指速度，`active_packet_valid=0` 会自然暂停。到达 buffer 最后一个 packet 时，若下一个背景 buffer 尚未完成且不在 loop lock 模式，则 `bg_stall=1` 暂停输出，等 `bg_fill_done_q` 置 1 后再切换。进入 `loop_wait_q`（后向 branch 保持）后也会屏蔽输出，防止刚发出的 branch packet 被重复发送。

**后向 branch 检测（loop lock 生效的关键）**：

```systemverilog
// 扫描正在输出的 packet 的 4 个 32-bit 字，找后向 branch
always_comb begin
  served_packet = active_buf_q ? buffer_b_q[exec_idx_q] : buffer_a_q[exec_idx_q];
  served_pkt_has_bwd_branch = 1'b0;
  for (w = 0; w < FetchPacketWidth/32; w++)
    if (served_packet[w*32 +: 7] == 7'b1100011 &&  // BRANCH opcode
        served_packet[w*32 + 31] == 1'b1)           // imm[12]=1 → 后向
      served_pkt_has_bwd_branch = 1'b1;
end
```

HDV task body 是非压缩的（32-bit 对齐），一个 128-bit fetch packet 正好 4 条 32-bit 指令。
关键修复点：**当输出的 packet 里含后向 branch 时，IPU 不能投机性地切换/丢弃 active buffer**。
否则——典型循环（如 vsaxpy）的 `bnez` 恰好落在 buffer 最后一个 packet——
切换会让 `exec_base` 提前推进，几个周期后到来的 redirect（目标=循环头）落在 `exec_base` 之前，
`redirect_in_active` 判否 → 退回 FILL → **每次迭代都重新取指**（这正是 loop lock “没奏效”的根因）。

**输出时的三条分支**（`take_packet`）：

1. **后向 branch 保持**（`served_pkt_has_bwd_branch & !replay_loop_lock`）：
   置 `loop_wait_d=1`，停在该 packet，**不切换、不前进**。等 taken redirect（in-active 回放）
   或 not-taken `loop_exit`（落到下一 buffer）来决定走向。这样循环体始终驻留，taken 迭代不再取指。
2. **直线最后一个 packet**（`exec_idx==LastPacketIdx`，无后向 branch）：正常切换到已预取完成的背景 buffer
   （`active_buf_d=fill_buf_q`、`exec_base_d=fetch_base_q`、推进 `fill_buf`/`fetch_base`、清预取索引）。
3. **显式 loop lock**（`replay_loop_lock=loop_lock_i`）：外部已知循环 taken，`exec_idx_d=0` 立即回放，
   不切换 buffer。该路径需要外部控制器保证 taken；TB 当前未驱动（`hdv_loop_lock=0`），靠自动机制即可。

**自动 loop lock**：

当 taken redirect 的目标 16B 对齐、命中 active buffer、目标 packet 已 valid、且为后向跳转时，
IPU 置 `auto_loop_lock_q`，使 `loop_blocks_bg_fetch=1` 停止背景取指，循环体常驻。
若命中 active buffer 的 redirect 不是后向，则清 `auto_loop_lock_q`。

**从 branch 保持中退出**（`loop_wait_q`）：

- taken：`redirect_valid_i` 命中 active buffer → 高优先级 redirect 块把 `exec_idx_d` 改到目标、
  清 `loop_wait_q`/`loop_exit_seen`、置 `auto_loop_lock_q`，从 active buffer 内回放，**不取指**。
- not-taken：用 **寄存后的** `loop_exit_seen_q`（不是组合 `loop_exit_i`）判退出。原因：taken 迭代里
  `loop_exit_i` 可能在（被刻意延后一拍的）redirect 之前瞬时拉高一拍；只有等到下一拍仍未被
  redirect 清掉，才确认是真正的 not-taken，从而避免 taken 迭代被误切换 buffer。确认后若
  在最后一个 packet 且背景 buffer 就绪则切换，否则 `exec_idx+1` 落到同 buffer 内的后续 packet。

> 已知限制：当前 in-active 回放只覆盖**单 buffer（≤64B）循环**。论文提到的“≤128B 跨双 buffer 锁定”
> 需要同时保住两个 buffer，属后续工作；vsaxpy 等紧循环为单 buffer，已覆盖。

### redirect 和 task complete

`top_ipu_task_complete_i` 优先级最高，使 IPU 回到 IDLE 并清计数。顶层当前把 `host_hdv_task_complete_i | host_hdv_task_error_i` 接到 IPU 的 `top_ipu_task_complete_i`，并把 `flush_i | host_hdv_task_error_i` 接到 IPU 的 `flush_i`，因此 task 出错时会终止取指，避免 TSU 已退出 active 但旧指令继续派出。

`redirect_valid_i` 次之。若 redirect 目标 16B 对齐、落在当前 active buffer 内、且目标 packet 已 valid，IPU 只更新 `exec_idx_d`，直接从 active buffer 内回放目标 packet；若目标不在 active buffer，IPU 清 buffer valid bit，回到 FILL 并从 `redirect_pc_i` 重新取第一包。未对齐 redirect 在仿真中由 `$fatal` 报错。

## `hdv_vliw_pack_unit.sv`

### 模块定位

VLIWPU 接收 IPU 输出的 128-bit fetch beat，解析第一个 32-bit word 中的 hint header 和后续 16-bit slots，生成 execute packet。它的输出仍是 slot 级接口，后续由 HEU 把 slot 规范化成一条条 16/32 bit 指令。

### packet 格式假设

当前默认：

- `FetchPacketWidth=128`
- 低地址第一个 32 bit 是 hint header，即 RTL 中的 `packet_q[31:0]`。
- header 后面有 6 个 16-bit payload slot，即 `packet_q[32 + i*16 +: 16]`。
- 如果 header 置 `packet256=1`，VLIWPU 会再等待下一条 128-bit beat，把两个 beat 合成一个 256-bit logical packet；外部总线仍是 128 bit。

当前 RTL/顶层使用 `NumSlots=8`、`SlotWidth=16`。普通 128-bit packet 只有 6 个有效 payload slot；256-bit logical packet 有 14 个有效 payload slot，但单个 EP 输出仍受 `NumSlots=8` 限制。

### 输入输出接口

输入：

- `ipu_vliwpu_packet_valid_i/vliwpu_ipu_packet_ready_o`: 从 IPU 接收 packet。
- `ipu_vliwpu_packet_i`: 128-bit packet。
- `ipu_vliwpu_packet_pc_i`: packet 起始 PC。
- `ctrl_vliwpu_dep_break_i`: 外部依赖检测输入，表示某两个 slot 之间不能继续并行打包。

输出：

- `vliwpu_heu_execute_valid_o/heu_vliwpu_execute_ready_i`: 发给 HEU 的 execute packet。
- `vliwpu_heu_execute_slot_valid_o`: 哪些 slot 属于当前 execute packet。
- `vliwpu_heu_execute_slot_o`: 16-bit slot 原始内容。
- `vliwpu_heu_execute_slot_is_32b_o`: 哪些 slot 是 32-bit 指令的低半部分。
- `vliwpu_heu_execute_class_o`: 每个 slot 的指令类别。
- `vliwpu_heu_execute_slot_pc_o`: 每个输出 slot 的真实 PC。普通 EP 时等于 `packet_pc_q + i*2`；跨包 EP 时，carry tail 和新 packet 开头 slot 各自保留原始 PC。
- `vliwpu_heu_execute_pc_o`: EP 参考 PC，普通 EP 时是 fetch packet 的 slot 0 绝对地址，跨包 EP 时是 carry tail 第一条指令 PC。精确指令 PC 以后优先看 `slot_pc_o`。

### packet holding

```systemverilog
packet_hold_valid_q
packet_q
packet_pc_q
head_slot_q
carry_valid_q
carry_slot_valid_q
carry_slot_q
carry_pc_q
```

VLIWPU 接收一个 packet 后保存在 `packet_q`，然后可能分多次输出 execute packet。`head_slot_q` 指示当前 execute packet 从哪个 slot 开始。

当 packet 尾部还有一个非控制流 EP、该 EP 没有用满 `MaxIssueSlots`、并且本 packet 在 tail 之前没有出现 SYSTEM/BRANCH 时，VLIWPU 会把尾部 slot 暂存进 carry 缓冲，等待下一 fetch packet。下一包到来后，carry tail 和下一包开头 slot 被压缩成一个跨包 EP 输出。跨包压缩不会丢 PC：每个输出 slot 通过 `vliwpu_heu_execute_slot_pc_o` 携带真实地址。

当前跨包 carry 必须由 header 显式允许：`header_cross_next=1` 时，packet 尾部才允许和下一 packet 开头组成跨包 EP。没有这个 bit 时，即使尾部看起来可以合并，也按 packet 边界结束。

### header 解析

```systemverilog
assign header             = packet_q[31:0];
assign header_is_lui_hint = (header[6:0] == 7'b0110111) && (header[11:7] == 5'd0);
assign header_imm20       = header[31:12];
assign p_bits             = header_is_lui_hint ? header_imm20[0 +: Packet256Slots-1] : '0;
assign header_packet_256  = header_is_lui_hint & header_imm20[13];
assign header_cross_next  = header_is_lui_hint & header_imm20[14];
assign header_loop_start  = header_is_lui_hint & header_imm20[15];
assign header_loop_end    = header_is_lui_hint & header_imm20[16];
```

header 是 32-bit RISC-V HINT 指令。当前约定使用 `lui x0, imm20`：`rd=x0` 使它对 RISC-V architectural state 无副作用，HDV 额外解释 `imm20` 中的控制位。当 `p_bits[i]=0` 时，当前 slot 后停止继续打包。当 `p_bits[i]=1` 且无依赖/资源边界时，可以继续把后续 slot 放入同一 execute packet。

在 `apps/vsaxpy_hdv` 中，当前默认 header 写成：

```asm
.macro HDV_HINT pbits=0, packet256=0, cross=0, loop_start=0, loop_end=0
  lui x0, (((\loop_end) << 16) | ((\loop_start) << 15) | ((\cross) << 14) | ((\packet256) << 13) | (\pbits))
.endm
```

这条指令是 RISC-V HINT，因为目的寄存器是 `x0`，对标量架构状态没有副作用。HDV 将 `imm20` 解释为：

| bit | RTL 位 | 含义 |
| --- | --- | --- |
| `imm20[12:0]` | `header[12 +: 13]` | `p_bits`，描述相邻 halfword slot 是否允许继续进同一 EP |
| `imm20[13]` | `header[25]` | `packet256`，当前 logical packet 还要合并下一条 128-bit beat |
| `imm20[14]` | `header[26]` | `cross`，允许 packet 尾部跨到下一 packet 开头 |
| `imm20[15]` | `header[27]` | `loop_start`，显式 loop 起点标记，供 loop lock/调试使用 |
| `imm20[16]` | `header[28]` | `loop_end`，显式 loop 末端标记，供 loop lock/调试使用 |

对于普通 128-bit packet，header 后面通常放 3 条 32-bit 业务指令。32-bit 指令占两个 halfword slot，因此最常用的 p-bit 是：

| bit | 含义 |
| --- | --- |
| `pbits[1]` | 第一条 32-bit 指令后继续合并第二条 |
| `pbits[3]` | 第二条 32-bit 指令后继续合并第三条 |
| `pbits[5]` | 第三条 32-bit 指令后继续合并跨包 carry 或 256-bit packet 中的下一条 |

控制并行性的规则是：`1` 表示“允许继续向后并入当前 execute packet”，`0` 表示“当前 slot 后结束这个 execute packet”。例如：

```asm
HDV_HINT 0x00, 0, 0, 0, 0  // 每条业务指令之间都形成边界
HDV_HINT 0x02, 0, 0, 0, 0  // 第一、第二条 32-bit 指令可以同 EP
HDV_HINT 0x0a, 0, 0, 0, 0  // 三条 32-bit 指令可连成一个 EP
HDV_HINT 0x02, 0, 1, 1, 0  // 第一包：前两条同 EP，尾部允许跨到下一包，标记 loop_start
```

p-bit 只是软件给出的并行请求，不是无条件并行承诺。`hdv_vliw_pack_unit` 还会根据真实硬件约束提前切断 execute packet，切断条件包括：

- **`p_bits[i]=0`**（或 `ctrl_vliwpu_dep_break_i[i]=1`）：当前 slot 后立即结束当前 execute packet，下一个 slot 开启新 execute packet。
- **SYSTEM/BRANCH 边界**：当前 slot 是 SYSTEM 或 BRANCH 类指令，执行完该指令后强制结束 execute packet（硬件行为，不依赖 p-bit 值）。
- **32-bit 指令内部**：continuation slot 必须与起点 slot 同包（p_bits[i] 被硬件视为强制=1），不受外部 p-bit 控制。
- **packet 末尾**：到达 fetch packet 最后一个 slot 时，普通情况下结束；如果 header 显式置 `cross=1`，且尾部 EP 不是 SYSTEM/BRANCH、没有用满 issue 宽度，则可以进入跨包 carry，和下一 fetch packet 开头继续组成同一个 EP。

`MaxIssueSlots=NumSlots`（当前为 8），等效于每个 EP 最多 8 个 16-bit slot，即最多 4 条完整 32-bit 业务指令。跨包 EP 仍受这个宽度限制：例如 carry tail 已占 2 个 slot，则最多还能从下一 fetch packet 开头并入 6 个 slot。

### slot 提取

```systemverilog
assign slots[i] = packet_q[32 + i*SlotWidth +: SlotWidth];
```

slot 从 header 之后开始编号。slot0 是 header 后面的第一个 16 bit；普通 128-bit packet 有 slot0..slot5；256-bit logical packet 有 slot0..slot13。

### 32-bit 指令标记

`raw_slot_is_32b[i] = (slots[i][1:0] == 2'b11)` 用 RISC-V 指令低两位判断该 halfword 是否可能是 32-bit 指令起点。

`p_slot_marks` 做进一步处理：

- 如果某 slot 被判为 32-bit 起点，则 `slot_is_32b[i]=1`。
- 下一个 slot 标成 `slot_is_continuation`。
- continuation slot 不会再被当成新的 32-bit 指令起点。

这避免了 32-bit 指令高半部分被误判为另一条 32-bit 指令。

### 指令分类

`p_classify` 根据 slot 内容做保守分类：

- opcode `1010111`: `HDV_INST_VECTOR`
- opcode `1110011` 或部分 compressed system 模式: `HDV_INST_SYSTEM`
- branch/jal/jalr opcode: `HDV_INST_BRANCH`
- 默认: `HDV_INST_SCALAR`

对 32-bit 指令的 continuation slot，`vliwpu_heu_execute_class_o` 复制低半 slot 的类别，保证 HEU 后续能一致处理。

### execute packet 形成

`p_issue_mask` 从 `head_slot_q` 开始扫描 slot，**跳过 continuation slot**（continuation slot 已由其 32-bit 起点 slot 强制包入，不能双重计数）：

- 将当前 slot 放入 `issue_mask`，`issue_count++`。
- 若当前 slot 是 32-bit 起点：
  1. 强制把下一个 slot（continuation）也放入 `issue_mask`，`issue_count++`。
  2. 检查是否继续打包下一条指令：使用 `p_bits[i+1]`（即 continuation 和后续指令之间的 p-bit）——若为 0、有 `ctrl_vliwpu_dep_break_i[i+1]` 或**当前 32-bit 指令本身**是 SYSTEM/BRANCH（`class_system_mask[i]` / `class_branch_mask[i]`，用起点 slot 的类别，因为 continuation slot 的原始 bits 不含有效 opcode），则停止；若 `issue_count >= MaxIssueSlotsCount` 或已到最后 slot，也停止；否则继续扫描下一条指令（`i+2`）。
- 若当前 slot 是 16-bit 普通指令：依据 `p_bits[i]`、`ctrl_vliwpu_dep_break_i[i]`、system/branch 判断是否停止。

这样，一个 fetch packet 可以拆分成多个 execute packet（由 p-bits 和边界条件决定），也可以在所有 p-bits=1、无 SYSTEM/BRANCH 的情况下整包形成一个 execute packet。若最后一个 EP 符合跨包条件且 header `cross=1`，packet 末尾不会立即发出，而是先进入 carry。

以当前 `vsaxpy_hdv` 为例，第一包使用 `HDV_HINT 0x02` 切开 `vsetvli+vle32` 和依赖 `t0` 的 `sub`；后续包默认 `HDV_HINT 0x1f`。跨包 carry 后，taken iteration 的主要 EP 形态为：

| 阶段 | 来源 | execute packet 划分 | 原因 |
|---|---|---|---|
| EP1 | packet 0 | vsetvli + vle32.v | `HDV_HINT 0x02` 允许这两条同包，随后切开 `sub` |
| EP2 | packet 0 tail + packet 1 | sub + vle32.v + slli + vfmacc.vf | packet 0 尾部 `sub` 进入 carry，和 packet 1 合成最多 4 条 32-bit 指令的 EP |
| EP3 | packet 2 | add a1 + vse32.v + add a2 | packet 2 内三条业务指令同 EP |
| EP4 | packet 3 | bnez | branch 是控制流边界，单独成 EP |

taken iteration 合计 **4 个 execute packet**。最后一轮 branch not-taken 后，fallthrough 的 `ret` 作为最终 scalar EP 结束任务，padding `nop` 不应被计入任务语义。因此 1024 elements、VL=32 时 expected EP 数为 `32*4 + 1 = 129`。

### packet_ready 逻辑

```systemverilog
assign packet_hold_can_accept =
    !packet_hold_valid_q ||
    tail_cross_candidate ||
    (execute_accept &&
     ((normal_execute_valid && issue_packet_drained) ||
      (cross_execute_valid  && cross_next_drained)));
```

VLIWPU 没有保存 packet 时可以接收新 packet；如果当前 packet 的最后一个 EP 正在被 HEU 接收并 drain，也可以同周期向 IPU 拉 ready。若当前尾部 EP 符合显式跨包条件，`tail_cross_candidate` 会提前向 IPU 拉 ready，让下一 packet 尽快进入 VLIWPU。跨包 EP 被 HEU 接收且下一包被消耗完时，`cross_next_drained` 清掉 held packet。

### head_slot 更新

当 HEU 接收当前 execute packet 后：

- 如果本次包含 packet 最后一个 slot，则清空 `packet_hold_valid_q`。
- 否则扫描 `issue_mask`，把 `head_slot_d` 更新到本次最后一个 valid slot 的下一个 slot。
- 如果本次是跨包 EP，则根据从新 packet 开头消耗到的位置更新 `head_slot_q`；如果新 packet 已被跨包 EP 全部吃完，就清空 `packet_hold_valid_q`。

## `hdv_hybrid_execution_unit.sv`

### 模块定位

HEU 当前不是完整执行单元，而是前端 dispatch block。它接收 VLIWPU 的 execute packet，按 `vliwpu_heu_execute_class_i` 分成标量和向量两条输出流。

### 输入 execute packet

输入仍是 slot 级：

- `vliwpu_heu_execute_slot_valid_i`: 哪些 slot 属于当前 execute packet。
- `vliwpu_heu_execute_slot_i`: 16-bit slot 内容。
- `vliwpu_heu_execute_slot_is_32b_i`: 哪些 slot 是 32-bit 指令低半部分。
- `vliwpu_heu_execute_class_i`: slot 对应类别。
- `vliwpu_heu_execute_pc_i`: execute packet 起始 PC。

### 标量/向量输出接口

HEU 输出已经不是 slot，而是一条条规范化指令：

```systemverilog
output logic [NumSlots-1:0]       heu_scalar_insn_valid_o,
output logic [NumSlots-1:0][31:0] heu_scalar_insn_o,
output logic [NumSlots-1:0]       heu_scalar_insn_is_32b_o,
output addr_t [NumSlots-1:0]      heu_scalar_insn_pc_o,
```

向量侧同样有 `vector_insn_*`。每个 entry 表示一条完整指令：

- 压缩指令: `{16'b0, halfword}`，`is_32b=0`。
- 32-bit 指令: `{upper_half, lower_half}`，`is_32b=1`。
- 32-bit 指令高半 slot 不单独 valid。

这保证标量流水线不会收到半条指令。

### 指令规范化

`p_split` 是 HEU 的核心组合逻辑：

1. 清空 `scalar_insn_valid_in`、`vector_insn_valid_in`、`dispatch_insn_in`。
2. 遍历每个 slot。
3. 判断当前 slot 是否是 32-bit 指令 continuation，如果是则跳过。
4. 如果当前 slot 是有效起点：
   - 32-bit 指令: 拼 `{vliwpu_heu_execute_slot_i[i+1], vliwpu_heu_execute_slot_i[i]}`。
   - 16-bit 指令: 拼 `{16'b0, vliwpu_heu_execute_slot_i[i]}`。
5. 根据 `vliwpu_heu_execute_class_i[i]` 决定置 scalar valid 还是 vector valid。
6. 计算每条指令自己的 PC: `vliwpu_heu_execute_pc_i + i * 2`。

### 输出寄存器

HEU 使用寄存器保存 dispatch packet：

- `dispatch_insn_q`
- `dispatch_insn_is_32b_q`
- `dispatch_insn_pc_q`
- `scalar_insn_valid_q`
- `vector_insn_valid_q`

这样 `heu_scalar_valid_o` 和 `heu_vector_valid_o` 不组合依赖下游 `ready`，避免 ready/valid 组合环。

### ready/valid 语义

```systemverilog
assign heu_vliwpu_execute_ready_o = !buffer_valid_q;
```

HEU 当前保留一个 current execute packet 和一个 skid buffer execute packet。只要 skid buffer 为空，就可以继续从 VLIWPU 接收下一个 EP；如果 current EP 还没被后端 accepted，新来的 EP 会进入 buffer。

### buffered vector 提前发射开关

当前 `hdv_top` 实例化 HEU 时设置 `.EnableBufferedVectorEarlyIssue(1'b1)`。因此 HEU 不只把 buffer EP 当作单纯 skid buffer：当安全条件满足时，下一 EP 的 vector slice 可以在该 EP promote 为 current 之前提前送入 `hdv_vec_dispatch_unit`。scalar slice 仍然按 EP 顺序发射。

这个优化的目标是让 Ara 前端更连续地获得 vector request。它不是无条件跨 EP 乱发；HEU 会检查 current EP 的控制流和依赖摘要，避免把可能依赖当前 scalar/vset 结果的 buffered vector 提前送出。

相关状态仍保留：

- `vector_dispatch_insn_*`: 独立的 vector 输出寄存器。scalar 输出仍用 `dispatch_insn_*`。
- `buffer_vector_sent_q`: buffered EP 的 vector 切片是否已经被 `vec_heu_ready_o` 接收。
- `buffer_vector_pending_q`: buffered vector 切片已经送出，但还没收到同 id 的 `vector_heu_accepted_i`。
- `vector_dispatch_from_buffer_q`: 当前 vector valid 属于 buffered EP 还是 current EP，用来在 ready 握手时正确标记 `buffer_vector_sent_q`。
- `current_vector_id_q` / `buffer_vector_id_q`: current/buffered vector slice 的 EP id。
- `vector_dispatch_id_q`: 当前送给 vector dispatch 的 EP id。
- `current_has_branch_q`: current EP 内是否有尚未 resolved 的 scalar control-flow 指令。

如果打开 `EnableBufferedVectorEarlyIssue`，提前发射条件是：

```systemverilog
EnableBufferedVectorEarlyIssue &&
buffer_valid_q &&
buffer_has_vector_q &&
!buffer_vector_sent_q &&
!vector_dispatch_valid_q &&
!current_has_branch_q &&
no_scalar_gpr_conflict &&
no_scalar_fpr_conflict &&
no_vector_config_conflict
```

也就是说：

- 只提前发 skid buffer 中的下一 EP，不越过更远的 EP。
- `heu_vector_ep_id_o` 给每个 vector slice 分配 1-bit EP id；`vec_heu_accepted_id_o` 返回同一个 id。因此 current vector pending 和 buffered vector pending 可以同时存在，HEU 按 id 清对应 pending。
- 不跨越 current EP 中尚未处理的 branch/jal/jalr/ret/c.branch/c.j/c.jr。
- 不改变 scalar 发射顺序。
- 不改变 vector 指令进入 Ara 的程序顺序。
- current scalar 写 GPR/FPR 与 buffered vector 读 GPR/FPR 冲突时，不提前发。
- current vector 写向量寄存器、`vset` 配置更新与 buffered vector 冲突时，不提前发。
- buffered vector 若已提前 accepted，等该 EP promote 为 current 时不会重复发；若还没 accepted，则 promote 后继续等待这次提前发射对应的 accepted。

`heu_scalar_valid_o` 和 `heu_vector_valid_o` 分别由寄存器输出。后端 ready 后对应 dispatch valid 清零。

### pending 和 EP accepted

`scalar_pending_q`、`vector_pending_q` 表示已经向对应后端发出 dispatch，但该后端还没有报告“已接收本 EP 切片”。它们由 `scalar_heu_accepted_i/vector_heu_accepted_i` 清除。

当一个 execute packet 的 scalar/vector pending 都清零，且本 EP 对应的 dispatch valid 都已经被 ready 接收后：

```systemverilog
if (!scalar_pending_d && !vector_pending_d &&
    !scalar_dispatch_valid_d && !vector_dispatch_valid_d) begin
  outstanding_d = 1'b0;
  ep_accepted_d = !error_d;
end
```

`heu_top_ep_accepted_o` 表示一个 execute packet 已经被相关后端接收，不表示整个 task 完成，也不表示 Ara 内部向量指令已经退休。accepted 条件同时检查 dispatch valid，可以避免后端 accepted 信号异常提前时，HEU 接收下一包并覆盖尚未被 ready 握手的输出寄存器。默认配置下 buffered EP 要等 promote 为 current 后才发射；如果打开 buffered vector 提前发射，HEU 还会等相关 vector ready/accepted 状态归属清楚后再 promote，避免清掉仍在握手中的 buffered vector 状态。

### 错误处理

`backend_heu_error_i` 在当前 packet outstanding 或接收 packet 同周期有效时，置 `error_q`。`heu_top_ep_error_o` 是 packet 级错误状态，由上层任务控制器决定是否转为 task error。

## `hdv_vec_dispatch_unit.sv`

### 模块定位

`hdv_vec_dispatch_unit` 是 HEU 向量侧到 Ara 的适配器。HEU 输出的是一个 execute packet，里面最多有 `NumSlots` 个 slot，其中若干 slot 是向量指令；Ara 的 accelerator request 接口一次只能接收一条向量指令。因此这个模块负责把“一个 EP 内的多条向量指令”缓存下来，并按 slot 顺序拆成多次 Ara request。

数据流是：

```text
HEU vector dispatch
  -> hdv_vec_dispatch_unit
  -> Ara acc_req_i
  <- Ara acc_resp_o
  -> vec_heu_accepted_o
  -> HEU vector_heu_accepted_i
```

也就是说，它不是向量执行单元本身，而是 HDV 和 Ara 前端协议之间的桥。

### HEU 侧接口

```systemverilog
input  logic                heu_vec_valid_i,
output logic                vec_heu_ready_o,
input  logic [NumSlots-1:0] heu_vec_insn_valid_i,
input  logic [NumSlots-1:0][31:0] heu_vec_insn_i,
input  logic                heu_vec_ep_id_i,
output logic                vec_heu_accepted_o,
output logic                vec_heu_accepted_id_o,
output logic                vec_heu_error_o,
```

- `heu_vec_valid_i` 表示 HEU 当前有一个 vector EP 要交给向量后端。
- `vec_heu_ready_o` 在 pending skid buffer 为空时为 1，表示可以接收新的 vector EP。
- `heu_vec_insn_valid_i[i]` 表示 EP 的 slot `i` 是有效向量指令。
- `heu_vec_insn_i[i]` 是 HEU 已经规范化好的 32-bit 向量指令。
- `heu_vec_ep_id_i` 是 HEU 分配给这个 vector slice 的 1-bit id，用来区分 current EP 和提前发射的 buffered EP。
- `vec_heu_accepted_o` 是给 HEU 的一拍脉冲，表示这个 vector EP 切片已经被本模块安全接管。vtrace 模式下普通 EP 入队即可 accepted；真实标量模式下，要等本 EP 的 vector request 都已经被 dispatch FSM 消费，并且 scalar operand 已经被捕获到 Ara request 或 command window。带 `vset rd!=x0` 的 EP 还要等对应 Ara response 写回 scalar backend 后 accepted。
- `vec_heu_accepted_id_o` 和 accepted 脉冲同拍有效，返回被 accepted 的 vector EP id。HEU 用它分别清 current vector pending 或 buffered vector pending。
- `vec_heu_error_o` 表示 vtrace 缺失、vtrace 指令不匹配或 Ara response 报 exception。

关键点：`vec_heu_accepted_o` 不表示 Ara 已经真正执行完，也不表示 load/store 已经完成，更不表示向量写回已经退休。向量指令之间的数据依赖由 Ara 后端自己处理，HDV 不因为普通 vector response 等待退休。HDV 只对 scalar 可见事件做额外处理：vset granted VL、`vmv.x.s`/`vfmv.f.s` 一类 vector-to-scalar 写回，以及 vector store pending 对标量内存操作的保守定序。

### Ara 侧接口

```systemverilog
output cva6_to_acc_t acc_req_o,
input  acc_to_cva6_t acc_resp_i
```

`acc_req_o` 复用 Ara 原本接 CVA6 accelerator dispatcher 的请求类型。当前 `hdv_top` 中不再让 CVA6/ideal dispatcher 驱动 Ara，而是由这个模块直接驱动 Ara：

```systemverilog
acc_req_o.acc_req.req_valid
acc_req_o.acc_req.insn
acc_req_o.acc_req.rs1
acc_req_o.acc_req.rs2
acc_req_o.acc_req.frm
```

Ara 用 `acc_resp_i.acc_resp.req_ready` 反压。只有 `req_valid && req_ready` 同时为 1 时，本条向量指令才算被 Ara 接收。

### 内部状态机

状态定义：

```systemverilog
typedef enum logic [1:0] {
  IDLE,
  DISPATCH,
  WAIT,
  DONE
} state_e;
```

当前实际主要用三个状态：

- `IDLE`: 等待 HEU 送入一个 vector EP。
- `DISPATCH`: 找当前最低编号的有效 slot，驱动 Ara request。
- `DONE`: 当前缓冲 EP 的有效 slot 都已经送入 Ara request 接口，随后切到 pending EP 或回到 `IDLE`。

`WAIT` 目前是保留状态，代码里只会直接转 `DONE`，没有承担真实等待 Ara 退休的功能。

### EP 缓冲

模块内部有当前 EP 缓冲和一个 pending skid buffer。当前 EP 缓冲是：

```systemverilog
logic [NumSlots-1:0]       insn_valid_q;
logic [NumSlots-1:0][31:0] insn_q;
```

当 `IDLE && heu_vec_valid_i` 时：

- `insn_valid_q <= heu_vec_insn_valid_i`
- `insn_q <= heu_vec_insn_i`
- 如果 Ara 同周期 `req_ready=1`，最低编号的第一条 vector 指令可以不等进入 `DISPATCH`，直接从输入 EP 旁路发给 Ara，并清掉对应 valid bit。
- 若剩余还有 vector slot 有效，进入 `DISPATCH`
- 若没有有效 vector slot，直接进入 `DONE`

这样本模块可以保存 EP 后继续给 Ara 发指令，同时 HEU 不必为普通 vector EP 等待这些指令全部发完。若当前 EP 还在发，且 pending buffer 为空，新 EP 可以先进入 pending buffer，减少对 HEU/VLIWPU 的反压。

### slot 选择

模块有两个简单 priority encoder：一个找内部缓冲 `insn_valid_q` 的最低编号有效 slot，另一个找新输入 `heu_vec_insn_valid_i` 的最低编号有效 slot。后者只在 `IDLE && heu_vec_valid_i` 时用于首条指令旁路。

```systemverilog
for (int unsigned i = 0; i < NumSlots; i++) begin
  if (insn_valid_q[i] && !slot_found) begin
    slot_found = 1'b1;
    slot_idx   = SlotIdxW'(i);
  end
end
```

所以 EP 内向量指令是按 slot 从小到大发给 Ara 的。对于 `vsetvli + vle32` 这类同 EP 组合，如果两个都是 vector slot，slot 0 会先发，slot 1 后发。Ara 后端内部负责处理向量指令间的数据依赖；HDV 只保证 request 发射顺序，以及 scalar-visible vector response 与标量后端之间的顺序。

### 标量操作数来源

`hdv_vec_dispatch_unit` 有两种标量操作数来源：

- 真实标量模式：`UseVTraceScalar=0`，通过 `vec_scalar_operand_req_valid_o` 和 `vec_scalar_rs*_addr_o` 向 `cva6_hdv_scalar_backend` 的 operand service 读取 XRF/FRF。
- vtrace 模式：`UseVTraceScalar=1`，从 vtrace 文件按序读取离线 `{insn, rs1, rs2}`。

vtrace entry 格式是：

```text
{insn[31:0], rs1[63:0], rs2[63:0]}
```

vtrace 模式下，每次 Ara 接收一条向量指令时，模块消耗一条 vtrace entry：

```systemverilog
if (accept_insn && UseVTraceScalar) begin
  vtrace_idx_d = vtrace_idx_q + 1'b1;
end
```

同时它会检查：

- vtrace 是否耗尽。
- vtrace 中的 `insn` 是否等于当前要发给 Ara 的 `selected_insn`。`selected_insn` 可能来自内部缓冲，也可能来自 IDLE 同周期输入旁路。

如果不匹配，`vec_heu_error_o` 会拉高，并打印错误。这是为了防止 HDV 分包顺序和 vtrace 标量值错位。

真实标量模式下，模块必须先捕获当前向量指令的 rs1/rs2/frs1，再把 request 送往 Ara 或放入内部 resolved-request buffer。这里的关键不是 Ara 是否已经完成执行，而是旧 vector 指令需要的标量操作数是否已经被快照保存。否则后续 scalar EP 可能先更新 a1/a2/a0/fa0 等寄存器，导致旧向量指令读到新值。

### resolved command window

当前代码在 FSM request 和 Ara `req_ready` 之间放了一个参数化小型 command window。顶层默认 `VectorCmdWindowDepth=4`，实例化时传给本模块 `CmdWindowDepth`。它保存的是“已经选中 slot、已经拿到 scalar operand”的单条 vector request：

```systemverilog
vq_count_q
vq_insn_q[CmdWindowDepth]
vq_rs1_q[CmdWindowDepth]
vq_rs2_q[CmdWindowDepth]
```

`vq_*[0]` 是队头，优先驱动 Ara。window 为空且 Ara ready 时，FSM request 可以 bypass 直接被 Ara 接收；Ara backpressure 时，FSM 仍可以继续把后续已解析 request 追加进 window，减少因为 Ara 暂时不 ready 导致的前端空泡。默认深度只有 4，是为了吸收短期 `req_ready` 气泡，而不是在 HDV 侧复制 Ara 内部调度窗口。

因此当前代码里的 `accept_insn` 语义是“dispatch FSM 的当前 vector slot 已经被消费”：

- 如果 window 为空且 Ara ready，request bypass 直接发送。
- 如果 Ara 不 ready，request 被保存到 command window。
- 两种情况都说明这条指令的 scalar operand 已经被安全捕获，FSM 可以清 slot 并继续处理下一条。

### accepted 的产生

dispatch FSM 消费单条向量指令的条件是：

```systemverilog
accept_insn = (vq_bypass & ara_acc) | vq_push;
```

每消费一条，当前 slot 的 valid bit 清零：

```systemverilog
insn_valid_d[slot_idx] = 1'b0;
```

vtrace 模式下，普通 vector EP 在 `enqueue_ep && !input_ep_has_vset_wb` 时直接产生 `vec_heu_accepted_o`，表示本模块已经接管该 EP。因为操作数来自离线 trace，后续标量寄存器变化不会影响这些向量 request。

真实标量模式下，普通 vector EP 等所有 slot 都被 dispatch FSM 消费后才产生 `vec_heu_accepted_o`。这些 slot 可能已经被 Ara 接收，也可能在 command window 中等待 Ara ready；无论哪种情况，每条向量指令的标量操作数都已经从真实标量后端读出并保存。

如果 EP 中存在 `vsetvli/vsetivli/vsetvl` 且 `rd!=x0`，模块先递增 `vset_accept_wait_q`，暂不 accepted。每条发给 Ara 的 vector request 会在 `resp_meta_*` FIFO 中记录 `{wb_valid, is_fpr, is_vset, is_store, rd, ep_id}`；Ara response 返回时弹出 FIFO。如果弹出的元数据表示 scalar-visible writeback，则产生 `vec_scalar_wb_valid_o`，并用 `vec_scalar_wb_is_fpr_o` 区分写 XRF 还是 FRF，用 `vec_scalar_wb_is_vset_o` 区分是否为 vset granted VL。若是 `vset rd!=0`，还会对等待中的 vset EP 产生 `vec_heu_accepted_o`。

真实标量模式下，accepted 不再由一个单独的 `real_ep_wait_valid` 状态保存，而是由两项 `real_wait_*` table 保存：

```systemverilog
real_wait_valid_q[i]
real_wait_id_q[i]
real_wait_has_vset_q[i]
real_wait_drained_q[i]
real_wait_vset_seen_q[i]
```

每个新接收的 vector EP 占一项 table。该 EP 的所有 vector slot 都被 dispatch FSM 消费后，置 `drained`；如果这个 EP 需要 `vset rd!=0` 写回，则等 response 元数据匹配该 `ep_id` 后置 `vset_seen`。当 `drained && (!has_vset || vset_seen)` 成立，模块产生 `vec_heu_accepted_o`，并在 `vec_heu_accepted_id_o` 返回该项的 `ep_id`。

这个 table 是真实标量模式 accepted 的关键配套逻辑：vector dispatch 可能因为 request drain 或 `vset` response 写回而延迟 accepted，因此需要用 `ep_id` 标记等待项。当前 HEU buffered vector 提前发射已打开，wait table 用于区分 current/buffered 两类 vector slice，避免把 accepted 归错 EP。`vec_heu_accepted_o` 在真实标量模式下由 registered wait-table 状态组合产生，避免额外打一拍；`vec_heu_ready_o` 还会把本周期 ready 可弹出的 table entry 视为空位，从而支持同周期 accepted 一个旧 EP 并接收一个新 EP。

## `hdv_top.sv`

### 模块定位

`hdv_top` 是 HDV 原型的集成顶层。它负责形成以下前端链路：

```text
CSR/TIU -> TSU -> IPU -> VLIWPU -> HEU -> scalar/vector pipeline ports
```

同时，顶层实例化 Ara 作为当前向量后端 shell，并参考 `ara_system.sv` 组织 memory bus：

```text
Ara AXI -> axi_inval_filter ----------------+
                                             +-> axi_mux -> system axi_req_o/axi_resp_i
scalar AXI reserved slot, tied off now ------+
HDV imem AXI adapter ------------------------+
```

### 顶层参数

顶层透传各子模块关键参数：

- `XLEN`
- `QueueDepth`
- `FetchPacketWidth`
- `BufferBytes`
- `NumSlots`
- `SlotWidth`
- `MaxIssueSlots`
- `addr_t`

同时透传 Ara 和 AXI 相关参数，包括 `NrLanes`、`VLEN`、`CVA6Cfg`、`AxiAddrWidth`、`AxiIdWidth`、`AxiNarrowDataWidth`、`AxiDataWidth`、标量窄 AXI channel/req/resp 类型、Ara 宽 AXI channel/req/resp 类型，以及 system AXI channel/req/resp 类型。`AxiAddrWidth` 和 `AxiIdWidth` 的默认值采用 `ara_system` 的 64 和 6，避免本地 invalidation 地址线出现 0 宽度。

### CSR 接口

顶层将 host 侧 CSR 端口直接连接到 TIU：

- `host_hdv_csr_valid_i`
- `host_hdv_csr_write_i`
- `host_hdv_csr_addr_i`
- `host_hdv_csr_wdata_i`
- `hdv_host_csr_ready_o`
- `hdv_host_csr_rdata_o`
- `hdv_host_csr_error_o`

### 取指存储器接口

顶层将 IPU 的 memory 接口导出：

- `hdv_imem_req_valid_o`
- `imem_hdv_req_ready_i`
- `hdv_imem_req_addr_o`
- `imem_hdv_rsp_valid_i`
- `hdv_imem_rsp_ready_o`
- `imem_hdv_rsp_data_i`

后续可接 I-cache、AXI read adapter 或测试 memory model。

### 控制接口

顶层暴露：

- `ctrl_hdv_redirect_valid_i/ctrl_hdv_redirect_pc_i`: 后端跳转或异常重定向。
- `ctrl_hdv_loop_lock_i`: 外部显式 loop buffer 锁定控制；自动 loop lock 不依赖该输入。
- `ctrl_hdv_dep_break_i`: 依赖检测边界，输入 VLIWPU。

当前依赖检测没有在 VLIWPU 内部完整实现，而是由外部传入 `ctrl_vliwpu_dep_break_i`。

### 自动 loop 检测

`hdv_top` 会扫描发往 scalar backend 的 EP。如果某个 32-bit scalar 指令是 B-type branch，且 B-type immediate 计算出的 target 小于该指令 PC，则认为这是后向 branch。

检测分三步：

- `scalar_dispatch_fire = hdv_scalar_valid_o & scalar_hdv_ready_i` 时，若 EP 内含后向 branch，置起 `loop_branch_inflight_q`。
- `scalar_hdv_accepted_i` 表示该 scalar EP 已被后端接收，顶层转而置起 `loop_branch_exit_pending_q`。
- 下一拍如果没有 `ctrl_hdv_redirect_valid_i`，说明该后向 branch not-taken，顶层向 IPU 发送 `auto_loop_exit`；如果有 redirect，则认为 taken，exit pending 被取消。

这个设计要求 taken redirect 在 branch accepted 后一拍内出现。当前 mock host 正是这种时序：
`mock_hdv_scalar_accepted_o` 在 T+1 拉高（组合），`branch_redirect_valid_q`（registered）在 T+2 拉高，
即 **redirect 比 accepted 晚一拍**。顶层 `loop_branch_exit_pending_q` 也在 T+2 拉高，与 redirect 对齐，
因此 taken 迭代里 `auto_loop_exit = exit_pending_q & !redirect = 0`，理论上不产生瞬时脉冲。

> **消费侧的健壮性约定（IPU）**：IPU 不直接用组合 `loop_exit_i` 触发 buffer 切换，而是用
> **寄存后的 `loop_exit_seen_q`**（晚一拍）。这样即使 SoC 布线让 redirect 与 accepted 之间出现
> 一拍偏斜、导致 `auto_loop_exit` 在 redirect 前瞬时拉高一拍，IPU 也会等到下一拍——届时高优先级的
> redirect 已经清掉 `loop_exit_seen` 并原地回放，从而不会在 taken 迭代误切换 buffer。未来接真实
> 标量后端时，仍应保证 branch accepted 与 redirect/not-taken 事件有明确配对关系（偏斜 ≤1 拍）。

### task 完成接口

```systemverilog
input logic host_hdv_task_complete_i;
input logic host_hdv_task_error_i;
```

这两个信号是 task 级，不是 execute packet 级。顶层明确要求未来 task controller 只在整个任务结束时断言它们。

### active task descriptor

`hdv_host_active_task_desc_o` 来自 IPU 锁存的 task descriptor。后续 scalar/vector pipeline 或 task controller 可用它读取参数、数据地址、长度等任务元信息。

### scalar pipeline 接口

顶层导出 HEU 标量侧接口：

- `hdv_scalar_valid_o/scalar_hdv_ready_i`
- `hdv_scalar_insn_valid_o`
- `hdv_scalar_insn_o`
- `hdv_scalar_insn_is_32b_o`
- `hdv_scalar_insn_pc_o`
- `scalar_hdv_accepted_i`

真实模式下，`hdv_top` 内部的 `cva6_hdv_scalar_backend` 消费 HEU scalar dispatch；这些外部 `hdv_scalar_*` 信号仍然导出，主要用于 testbench/调试观察。关闭真实标量后端时，外部 mock host 通过 `scalar_hdv_ready_i/scalar_hdv_accepted_i` 接管。

标量流水线应在 `hdv_scalar_valid_o` 有效且 `scalar_hdv_ready_i` 握手后接收一组并行标量指令 entry。每个 valid entry 都是一条完整指令。`scalar_hdv_accepted_i` 表示标量后端已经安全接收/处理本 EP 的标量切片；真实后端是在 scalar slots 执行和写回完成后产生 accepted，mock host 则用固定 latency 产生它。

### vector pipeline 接口

顶层不再导出 `hdv_vector_*` 外部端口。HEU 向量侧在 `hdv_top` 内部连接到 `hdv_vec_dispatch_unit`，再由该模块驱动 Ara accelerator request。向量侧的 `vector_heu_accepted_i` 来自 `vec_heu_accepted_o`，语义是 vector EP 切片已被向量派发模块安全接管；vtrace 模式下普通 EP 入队即 accepted，真实标量模式下等本 EP 的 vector request 都 drain 并捕获 operand 后 accepted，`vset rd!=0` EP 还要等 response 写回后 accepted。

### scalar/Ara accelerator 接口

当前 `hdv_top` 内部实例化 Ara，实例名为 `i_ara`。Ara 的 accelerator request 由 `hdv_vec_dispatch_unit` 驱动，不再来自 CVA6/ideal dispatcher。Ara 实例的原始 `acc_resp_o` 先进入内部 `ara_acc_resp`，随后顶层把 `axi_inval_filter` 产生的 dcache invalidation 信息打包进 `ara_acc_resp_pack`，再送回 `hdv_vec_dispatch_unit`。这个写法保留了 `ara_system` 中 `pack_inval` 的结构：

- `inval_valid` 写入 `ara_acc_resp_pack.acc_resp.inval_valid`。
- `inval_addr` 写入 `ara_acc_resp_pack.acc_resp.inval_addr`。
- `inval_ready` 来自内部 `acc_req.acc_req.inval_ready`。
- `acc_cons_en` 来自内部 `acc_req.acc_req.acc_cons_en`。

这样 Ara 发起会影响 scalar dcache 一致性的写事务时，invalidation 信息不会绕过 accelerator response 通道。当前 `acc_cons_en` 通常为 0，filter 多数时间等价于结构占位，后续接真实 CVA6/cache coherence 时可复用。

### memory bus 系统

`hdv_top` 不再把 Ara 的 AXI port 直接导出为 `ara_axi_req_o/ara_axi_resp_i`。内部 memory 连接分四段。

第一段是 Ara 原生 AXI：

```text
ara_axi_req / ara_axi_resp
```

这组信号只在 `hdv_top` 内部连接 Ara 实例和 invalidation filter。

第二段是 `axi_inval_filter`：

```text
ara_axi_req -> axi_inval_filter -> ara_axi_req_inval
ara_axi_resp <- axi_inval_filter <- ara_axi_resp_inval
```

filter 的参数和 `ara_system` 保持同一风格：`MaxTxns=4`，`AddrWidth=AxiAddrWidth`，`L1LineWidth=CVA6Cfg.DCACHE_LINE_WIDTH/8`。它根据 `acc_cons_en` 决定是否启用 invalidation 追踪，并通过 `inval_valid/inval_addr/inval_ready` 与 accelerator response path 协调。

第三段是标量 AXI slot：

```text
scalar_axi_req/scalar_axi_resp <-> cva6_hdv_scalar_backend
```

当前 RTL 已经把 `cva6_hdv_scalar_backend` 的 load/store AXI 接入这个 slot。保留三路 `axi_mux` 拓扑的目的仍然是保持 Ara vector memory path、scalar memory path、HDV IPU 取指 path 共用一组 system AXI port，并保持 ID 宽度稳定。若后续标量 LSU 宽度与 system AXI 宽度不一致，可以在这个 slot 前补 `axi_dw_converter`。

第四段是 `axi_mux`：

```text
{ara_axi_req_inval, scalar_axi_req, hdv_imem_axi_req} -> axi_mux -> axi_req_o
{ara_axi_resp_inval, scalar_axi_resp, hdv_imem_axi_resp} <- axi_mux <- axi_resp_i
```

`axi_mux` 当前有三个 slave-side master 入口：

- `ara_axi_req_inval/ara_axi_resp_inval`: Ara vector memory path。
- `scalar_axi_req/scalar_axi_resp`: `cva6_hdv_scalar_backend` 的标量 load/store path。
- `hdv_imem_axi_req/hdv_imem_axi_resp`: HDV IPU 取指 path。IPU 仍看到简单 ready/valid packet-fetch 接口，`hdv_top` 在内部把它转换成单拍 AXI read。

顶层最终只导出一组 system AXI：

- `axi_req_o`
- `axi_resp_i`

这与 `ara_system` 的顶层接口方向一致。外部只看到统一的 system AXI port。

### ara_soc 例化方式

`ara_soc.sv` 的普通非 gate-sim 路径中，原来 `i_system` 直接例化 `ara_system`。现在 `i_system` 改为例化 `hdv_top`：

- `hdv_top.i_ara` 是当前 Ara 向量侧。
- `hdv_top.i_vec_dispatch_unit` 把 HEU 的 vector EP 转成 Ara accelerator request。
- 标量侧默认由 `hdv_top` 内部的 `cva6_hdv_scalar_backend` 接收；外部 `hdv_scalar_*` 端口仍导出给 `ara_tb` 观察或在关闭真实标量后端时交给 `hdv_mock_host_core` 接管。
- `hdv_top.axi_req_o/axi_resp_i` 连接回 SoC 原来的 `system_axi_req/system_axi_resp`。

这样系统主访存路径变为：

```text
hdv_top.i_ara vector AXI -> inval_filter -+
                                           +-> hdv_top system AXI -> ara_soc xbar
hdv_top scalar AXI ------------------------+
hdv_top IPU imem AXI ---------------------+
```

HDV task CSR 在 `ara_soc` 中有两条来源：软件 `ctrl_registers` 产生的 CSR 访问，以及 testbench/mock host 直连的 host CSR 访问。host CSR 有效时优先送入 `hdv_top`。真实标量模式下，HDV scalar dispatch 在 `hdv_top` 内部由 `cva6_hdv_scalar_backend` 接收；`ara_tb` 中的 scalar 信号仍可观察。vector dispatch 在 `hdv_top` 内部通过 `hdv_vec_dispatch_unit` 转成 Ara accelerator request。

### execute packet 状态

```systemverilog
hdv_host_ep_busy_o
hdv_host_ep_accepted_o
hdv_host_ep_error_o
```

这些信号来自 HEU，只表示 execute packet 级“后端接收/错误”状态。顶层没有把 `hdv_host_ep_error_o` 自动并入 `host_hdv_task_error_i`，避免把单条 execute packet 的错误误当成整个 task 的错误。是否转成 task error 由外部 task controller 决定。

### 内部连接

顶层内部跨模块连线按“源模块_目的模块_信号名”命名。模块自己的端口仍保留 `_i/_o` 后缀；只有 `hdv_top` 内部 wire/reg 使用源/目的前缀，便于从波形上一眼看出连线方向。

| 信号前缀 | 源 → 目的 | 说明 |
|---|---|---|
| `tiu_tsu_*` | TIU → TSU | task valid、entry、desc 和 status clear |
| `tsu_tiu_*` | TSU → TIU | task ready 回压 |
| `tsu_ipu_*` | TSU → IPU | task valid、entry、desc |
| `ipu_tsu_*` | IPU → TSU | task ready 回压 |
| `ipu_mem_*` | IPU → top 内部取指 AXI adapter | 取指请求与 response ready |
| `mem_ipu_*` | top 内部取指 AXI adapter → IPU | 取指请求 ready 与 response data/valid |
| `ipu_vliwpu_*` | IPU → VLIWPU | fetch packet、packet PC、packet valid |
| `vliwpu_ipu_*` | VLIWPU → IPU | packet ready 回压 |
| `vliwpu_heu_*` | VLIWPU → HEU | execute packet 及 slot/class/PC |
| `heu_vliwpu_*` | HEU → VLIWPU | execute ready 回压 |
| `tsu_top_*` | TSU → hdv_top status | task busy/done/error |
| `ipu_top_*` | IPU → hdv_top status | IPU busy 与 active task descriptor |
| `heu_top_*` | HEU → hdv_top status | execute busy/done/error |

这种命名把 ready/valid 的正向数据和反向回压分开，后续替换 mock 标量后端或增强 HDV-to-Ara adapter 时也更容易定位边界。

## 当前实现边界

当前 HDV 原型已经完成：

- task CSR 接口。
- task FIFO 调度。
- 双 buffer instruction prefetch。
- packet 到 execute packet 的保守 VLIW 分包。
- 标量/向量指令分流。
- 压缩/非压缩指令规范化输出。
- 顶层 wrapper 连接。
- Ara shell 实例化。
- Ara memory invalidation filter。
- `hdv_vec_dispatch_unit` 把 HEU vector EP 转成 Ara accelerator request。
- Ara/vector、CVA6_HDV scalar backend、HDV IPU 取指到统一 system AXI port 的 mux。

尚未完成：

- 把 `cva6_hdv_scalar_backend` 扩展成覆盖全 Ara benchmark 的完整 RV64IMC + F/D + Zicsr 用户态标量通路。
- 让普通 Ara 指令退休/写回结果反向约束 EP accepted；当前只有 scalar 可见的 `vset rd!=0` response 会延迟 vector EP accepted。
- 精确异常、commit、flush 和分支预测。
- 任务描述符解析。
- 自动 loop pattern 检测仍需更多 kernel 验证。
- 完整 scalar-vector 依赖 scoreboard。

因此当前代码适合作为 HDV 前端结构原型和后续集成边界，不应直接视为完整处理器执行子系统。

---

## 仿真信号监测指南（Verdi / waveform）

本节列出在 Verdi 或任意波形工具中验证 HDV 流水线各阶段正确性时，**应添加到 wave 的信号**及其含义。

### 层次路径前缀

| 简称 | 完整层次路径 |
|---|---|
| `TB` | `ara_tb` |
| `MOCK` | `ara_tb.i_hdv_mock_host_core` |
| `SOC` | `ara_tb.dut.i_ara_soc` |
| `TOP` | `ara_tb.dut.i_ara_soc.i_system` （hdv_top 实例，在 `` `ifndef TARGET_GATESIM `` 块中） |
| `TIU` | `ara_tb.dut.i_ara_soc.i_system.i_task_interface_unit` |
| `TSU` | `ara_tb.dut.i_ara_soc.i_system.i_task_schedule_unit` |
| `IPU` | `ara_tb.dut.i_ara_soc.i_system.i_instruction_prefetch_unit` |
| `VLIWPU` | `ara_tb.dut.i_ara_soc.i_system.i_vliw_pack_unit` |
| `HEU` | `ara_tb.dut.i_ara_soc.i_system.i_hybrid_execution_unit` |

---

### 阶段 0：Mock Host 状态机（最高层观察入口）

**路径**：`MOCK.*`

| 信号 | 位宽 | 方向（源 → 目的） | 含义 | 期望值/事件 |
|---|---|---|---|---|
| `state_q` | [3:0] | MOCK 内部 | 状态机状态 | 见下方状态表 |
| `accepted_packets_q` | [31:0] | MOCK 内部 | 已被后端接收的 execute packet 数 | `vsaxpy_hdv` 当前最终期望 129 |
| `expected_ep_accepts_q` | [31:0] | MOCK 内部 | 期望 EP 数 | `1024/VL=32` 时为 129 |
| `csr_valid_o` | 1 | MOCK → TIU | 正在写 HDV CSR | 各阶段依次脉冲 |
| `csr_write_o` | 1 | MOCK → TIU | CSR 写使能 | 写时为 1 |
| `csr_addr_o` | [11:0] | MOCK → TIU | 写入哪个 CSR | 见下方 |
| `csr_wdata_o` | [63:0] | MOCK → TIU | 写入数据 | 见下方 |
| `hdv_mock_ep_accepted_i` | 1 | HEU → MOCK | HEU 发来的 execute packet accepted 脉冲 | `vsaxpy_hdv` 共 129 次脉冲 |
| `task_complete_o` | 1 | MOCK → HDV top/TSU/IPU | 外部请求任务结束 | expected 达标或 HDV done 后 1 cycle 脉冲 |

**state_q 状态枚举**：

| 值 | 状态名 | 动作 |
|---|---|---|
| 0 | IDLE | 等待 AutoStartDelay |
| 1 | WRITE_TASK_ADDR | 写 VTASK_ADDR = 0x80001000 |
| 2 | WRITE_TASK_DESC | 写 VTASK_PADDR = 0x80001000 |
| 3 | CLEAR_STATUS | 写 VTASK_STATUS 清除旧状态 |
| 4 | WRITE_START | 写 VTASK_START = 1，触发任务 |
| 5 | RUN | 等待并计数 ep_accepted 脉冲；若看到 HDV task done/busy 结束也可进入读状态 |
| 6 | COMPLETE_TASK | 发 task_complete_o = 1（1 cycle），用于 expected 达标的兜底结束 |
| 7 | WAIT_TASK_STATUS | 轮询 tsu_tiu_task_done_i |
| 8 | READ_STATUS | 读 VTASK_STATUS 确认 done=1 |
| 9 | FINISH | **PASS**，仿真结束 |
| 10 | FAIL | 超时或错误，仿真结束 |

**关键 CSR 写序列**：

| state | csr_addr_o | csr_wdata_o |
|---|---|---|
| WRITE_TASK_ADDR | 0x7c0 | 0x80001000（任务代码入口） |
| WRITE_TASK_DESC | 0x7c1 | 0x80001000 |
| CLEAR_STATUS | 0x7c3 | 0x6（清 done/error 位） |
| WRITE_START | 0x7c2 | 0x1（触发） |

---

### 阶段 1：TIU — 任务提交

**路径**：`TIU.*`

| 信号 | 位宽 | 方向（源 → 目的） | 含义 | 期望值/事件 |
|---|---|---|---|---|
| `host_tiu_csr_valid_i` | 1 | MOCK → TIU | 有 CSR 访问 | 与 MOCK.mock_hdv_csr_valid_o 同步 |
| `host_tiu_csr_write_i` | 1 | MOCK → TIU | CSR 写 | |
| `host_tiu_csr_addr_i` | [11:0] | MOCK → TIU | CSR 地址 | 0x7c0/0x7c1/0x7c2/0x7c3 |
| `host_tiu_csr_wdata_i` | [63:0] | MOCK → TIU | 写入值 | |
| `vtask_addr_q` | [63:0] | TIU 内部 | 已锁存的任务入口地址 | 应为 0x80001000 |
| `task_valid_q` | 1 | TIU 内部 | 任务已提交等待 TSU 接收 | 写 VTASK_START 后变 1 |
| `tiu_tsu_task_valid_o` | 1 | TIU → TSU | 发往 TSU | 同上 |
| `tiu_tsu_task_entry_o` | [63:0] | TIU → TSU | 任务入口 PC | 0x80001000 |
| `done_q` | 1 | TIU 内部 | 任务完成标志（粘滞） | TSU done 传来后置 1 |
| `error_q` | 1 | TIU 内部 | 任务错误标志（粘滞） | 应保持 0 |
| `tsu_tiu_task_done_i` | 1 | TSU → TIU | 来自 TSU 的 task done | scalar backend 执行 `ret` 或 mock host task complete 后，TSU 置 done |

---

### 阶段 2：TSU — 任务调度

**路径**：`TSU.*`

| 信号 | 位宽 | 方向（源 → 目的） | 含义 | 期望值/事件 |
|---|---|---|---|---|
| `fifo_push` | 1 | TIU → TSU | 任务入队 | TIU 提交时 1 cycle 脉冲 |
| `fifo_pop` | 1 | TSU 内部 | 任务出队发往 IPU | 随后 1 cycle 脉冲 |
| `active_q` | 1 | TSU 内部 | 当前有 active task | 任务执行期间保持 1 |
| `tsu_ipu_task_valid_o` | 1 | TSU → IPU | 向 IPU 发出任务 | fifo_pop 时有效 |
| `ipu_tsu_task_ready_i` | 1 | IPU → TSU | IPU 接受任务 | 握手成功时为 1 |
| `done_q` | 1 | TSU 内部 | TSU 侧任务完成粘滞 | task controller 报告 task done 后置 1，直到 status_clear |
| `tsu_top_done_o` | 1 | TSU → TIU | 输出给 TIU | 同 done_q |

---

### 阶段 3：IPU — 取指

**路径**：`IPU.*`

| 信号 | 位宽 | 方向（源 → 目的） | 含义 | 期望值/事件 |
|---|---|---|---|---|
| `state_q` | [1:0] | IPU 内部 | 状态：0=IDLE, 1=FILL, 2=SERVE | FILL→SERVE 转换是关键 |
| `fetch_base_q` | [63:0] | IPU 内部 | 当前 fill 的起始地址 | 首次 = 0x80001000 |
| `exec_base_q` | [63:0] | IPU 内部 | 当前 serve 的起始地址 | 首次 = 0x80001000 |
| `fill_req_idx_q` | [1:0] | IPU 内部 | 下一条 request 的 128-bit packet index | 连续发请求时 0→1→2→3 |
| `fill_rsp_idx_q` | [1:0] | IPU 内部 | 下一条 response 写回的 128-bit packet index | response 按序返回时 0→1→2→3 |
| `exec_idx_q` | [1:0] | IPU 内部 | 正在输出第几个 128-bit packet | 每次 VLIWPU 接收后递增 |
| `active_buf_q` | 1 | IPU 内部 | 当前 serve 的 buffer（0=A, 1=B） | 初始 0 |
| `buffer_a_valid_q/buffer_b_valid_q` | [3:0] | IPU 内部 | 每个 128-bit packet 是否已写回 | 首包返回后即可出现 bit0=1 |
| `bg_fill_done_q` | 1 | IPU 内部 | 背景预取完成 | exec_idx=3 前应为 1 |
| `bg_stall` | 1 | IPU 内部 | 等待下一个背景 buffer，暂停输出 | 正常应短暂或不出现 |
| `ipu_vliwpu_packet_valid_o` | 1 | IPU → VLIWPU | 向 VLIWPU 输出有效 packet | SERVE 状态且当前 packet valid 且 !bg_stall |
| `vliwpu_ipu_packet_ready_i` | 1 | VLIWPU → IPU | VLIWPU 接受 packet | 握手 |
| `ipu_vliwpu_packet_o` | [127:0] | IPU → VLIWPU | 128-bit fetch beat 内容 | 低地址第一个 word = hint header，即 RTL `packet[31:0]` |
| `ipu_vliwpu_packet_pc_o` | [63:0] | IPU → VLIWPU | fetch packet 起始 PC | 0x80001000, +16, +32, +48 |
| `axi_ar_valid_o` | 1 | IPU → SRAM/AXI | AXI 读地址请求 | FILL 阶段依次发出 |
| `axi_ar_addr_o` | [63:0] | IPU → SRAM/AXI | AXI 读地址 | 0x80001000, +16, +32, +48 |
| `axi_r_valid_i` | 1 | SRAM/AXI → IPU | AXI 读数据返回 | |
| `axi_r_data_i` | [127:0] | SRAM/AXI → IPU | 返回的 128-bit 数据 | 即 SRAM 中的 VLIW 指令 |
| `top_ipu_task_complete_i` | 1 | HDV top → IPU | 任务结束或错误，终止取指 | `host_hdv_task_complete_i | scalar_backend_task_complete | host_hdv_task_error_i` |

**关键波形特征**：`state_q` 应从 IDLE→FILL（axi_ar 握手）→SERVE（packet_valid 拉高）。

---

### 阶段 4：VLIWPU — VLIW 打包

**路径**：`VLIWPU.*`

| 信号 | 位宽 | 方向（源 → 目的） | 含义 | 期望值/事件 |
|---|---|---|---|---|
| `packet_hold_valid_q` | 1 | VLIWPU 内部 | 持有一个 fetch packet | 接收后为 1，最后一个 EP 出去后清 0 |
| `packet_q` | [255:0] | VLIWPU 内部 | 锁存的 logical packet | 低 32 bit 是 hint header；128-bit packet 高位补 0；256-bit packet 合并两个 beat |
| `carry_valid_q` | 1 | VLIWPU 内部 | 有跨包 tail 等待和下一 packet 合包 | packet 尾部 `sub/vfmacc/add` 可进入 carry |
| `carry_slot_valid_q` | [7:0] | VLIWPU 内部 | carry tail 中哪些压缩 slot 有效 | 典型为 8'b00000011 |
| `carry_pc_q` | [63:0] | VLIWPU 内部 | carry tail 第一条指令 PC | 跨包 EP 的 base PC |
| `vliwpu_heu_execute_slot_pc_o` | [7:0][63:0] | VLIWPU → HEU | 每个输出 slot 的真实 PC | 跨包 EP 中每条指令仍保持原始 PC |
| `header` | [31:0] | VLIWPU 内部 | hint header（`lui x0, imm20`） | `imm20` 含 pbits/packet256/cross/loop flags |
| `p_bits` | [12:0] | VLIWPU 内部 | 并行控制位 | 普通 128-bit 常用 bit1/3/5 |
| `slots[0..13]` | [15:0] each | VLIWPU 内部 | logical packet 的 16-bit 指令槽 | slot i = packet_q[32+i*16+:16] |
| `slot_is_32b` | [13:0] | VLIWPU 内部 | 哪些 slot 是 32-bit 指令起点 | 普通 128-bit 常见 bit0/2/4 |
| `slot_is_continuation` | [13:0] | VLIWPU 内部 | 哪些 slot 是 32-bit 续半 | 普通 128-bit 常见 bit1/3/5 |
| `class_system_mask` | [13:0] | VLIWPU 内部 | SYSTEM 指令标记 | `vset*` 仍按 vector class，CSR/system 按 system |
| `class_branch_mask` | [13:0] | VLIWPU 内部 | BRANCH 指令标记 | branch/jal/jalr/ret 强制 EP 边界 |
| `head_slot_q` | [2:0] | VLIWPU 内部 | 当前 EP 从哪个 slot 开始 | 0→2→0→0→0→2→4 |
| `issue_mask` | [7:0] | VLIWPU 内部 | 当前 EP 包含哪些输出 slot | 最多 8 个 halfword slot |
| `issue_count` | [3:0] | VLIWPU 内部 | 当前 EP 包含的 slot 数 | EP1:2, EP2:4, EP3/4:6, EP5/6/7:2 |
| `stop_pack` | 1 | VLIWPU 内部 | EP 边界已确定 | 每个 EP 确定后组合逻辑为 1 |
| `last_slot_in_packet` | 1 | VLIWPU 内部 | 本 EP 是该 fetch packet 的最后 | 清空 packet_hold_valid_q |
| `tail_cross_candidate` | 1 | VLIWPU 内部 | 当前 packet 尾部 EP 可跨包 | 置 1 时先进入 carry，不立即发 HEU |
| `cross_execute_valid` | 1 | VLIWPU 内部 | 当前输出是跨包 EP | carry tail + 新 packet 开头 |
| `vliwpu_heu_execute_valid_o` | 1 | VLIWPU → HEU | EP 有效发往 HEU | 普通 EP 或跨包 EP |
| `heu_vliwpu_execute_ready_i` | 1 | HEU → VLIWPU | HEU 接收 EP | = !HEU.buffer_valid_q |
| `vliwpu_heu_execute_slot_valid_o` | [7:0] | VLIWPU → HEU | EP slot 掩码 | 普通 EP 同 issue_mask；跨包 EP 为压缩后的 slot0..N |
| `vliwpu_heu_execute_class_o[i]` | [1:0] each | VLIWPU → HEU | slot i 指令类别 | 0=SCALAR,1=VECTOR,2=SYSTEM,3=BRANCH |

**当前 vsaxpy_hdv 的 taken-iteration EP 速查**：

| EP | 来源 | 输出 slot_valid | 指令 |
|---|---|---|---|
| EP1 | packet 0 | 6'b001111 | vsetvli + vle32.v |
| EP2 | packet 0 tail + packet 1 | 8'b11111111 | sub + vle32.v + slli + vfmacc.vf |
| EP3 | packet 2 | 8'b00111111 | add a1 + vse32.v + add a2 |
| EP4 | packet 3 | 8'b00000011 | bnez |

最后一轮 not-taken 后，还会继续看到 fallthrough 的 `ret`，它由标量后端作为 task exit 处理。1024 elements、VL=32 时 expected EP 数为 `32*4+1=129`。

---

### 阶段 5：HEU — 分发执行

**路径**：`HEU.*`

| 信号 | 位宽 | 方向（源 → 目的） | 含义 | 期望值/事件 |
|---|---|---|---|---|
| `accept_packet` | 1 | HEU 内部 | 接收来自 VLIWPU 的 EP | 每个 EP 到来时 1 cycle 脉冲 |
| `outstanding_q` | 1 | HEU 内部 | 有 EP 正在处理中 | accept_packet 后变 1，done 后变 0 |
| `has_scalar` | 1 | HEU 内部 | 本 EP 含标量指令（组合） | EP 含 SCALAR/SYSTEM/BRANCH |
| `has_vector` | 1 | HEU 内部 | 本 EP 含向量指令（组合） | EP 含 VECTOR |
| `scalar_dispatch_valid_q` | 1 | HEU 内部 | 标量 dispatch 等待 ready | accept_packet 后若 has_scalar 则为 1 |
| `vector_dispatch_valid_q` | 1 | HEU 内部 | 向量 dispatch 等待 ready | accept_packet 后若 has_vector 则为 1 |
| `scalar_pending_q` | 1 | HEU 内部 | 标量后端尚未 accepted | scalar_fire 后为 1 |
| `vector_pending_q` | 1 | HEU 内部 | 向量后端尚未 accepted | vector_fire 后为 1 |
| `scalar_heu_ready_i` | 1 | MOCK → HEU | 标量后端（mock）ready | MOCK 在 RUN 状态时为 1 |
| `vector_heu_ready_i` | 1 | VEC_DISPATCH → HEU | 向量后端 ready | `hdv_vec_dispatch_unit` 空闲时为 1 |
| `scalar_heu_accepted_i` | 1 | MOCK → HEU | 标量后端接收本 EP 切片 | ScalarLatency 周期后脉冲 |
| `vector_heu_accepted_i` | 1 | 向量后端 → HEU | 向量后端接收本 EP 切片 | 普通 vector EP 入队后脉冲；`vset rd!=0` 等 response 写回后脉冲 |
| `ep_accepted_q` | 1 | HEU 内部 | ep_accepted 脉冲（**1 cycle**） | 每个 EP 被后端接收后出现，次周期自动清 0 |
| `heu_top_ep_accepted_o` | 1 | HEU → MOCK | = ep_accepted_q，连到 MOCK.hdv_mock_ep_accepted_i | 共 7 次脉冲 |
| `heu_vliwpu_execute_ready_o` | 1 | HEU → VLIWPU | = !buffer_valid_q | HEU skid buffer 未满时为 1 |

---

### 推荐观察顺序（从零开始）

1. **先看 `MOCK.state_q`**：确认状态机从 IDLE 走到 FINISH（值从 0→1→2→3→4→5→6→7→8→9）。这是最高层的通过/失败指示器。

2. **看 `TIU.vtask_addr_q` 和 `TIU.task_valid_q`**：确认 0x80001000 写入并且任务成功提交给 TSU。

3. **看 `IPU.state_q` 和 `IPU.axi_ar_valid_o/addr`**：确认 IPU 开始从 0x80001000 取指（FILL 阶段），然后进入 SERVE 阶段。

4. **看 `IPU.ipu_vliwpu_packet_valid_o` 和 `VLIWPU.packet_hold_valid_q`**：确认 fetch packet 逐个从 IPU 流入 VLIWPU。

5. **看 `VLIWPU.p_bits`、`VLIWPU.issue_mask`、`VLIWPU.stop_pack`**：确认每个 EP 的 slot 划分正确（对照上方 EP 速查表）。

6. **看 `HEU.accept_packet` 和 `HEU.ep_accepted_q`**：确认 HEU 逐包接收，并在标量/向量后端 accepted 后发出 EP accepted 脉冲。

7. **看 `MOCK.hdv_mock_ep_accepted_i` 和 `MOCK.accepted_packets_q`**：确认计数器从 0 走到 7。

8. **最后看 `MOCK.state_q == 9`（FINISH）**：验证通过。
