# HDV Prototype RTL Code Walkthrough

本文档逐语段说明 `hardware/src/hdv` 下新增的 Hybrid Decoupled Vector (HDV) 原型 RTL。当前这些模块仍是 HDV 前端原型，但 `hdv_top` 已经实例化 Ara 作为向量后端 shell，并参考原始 `ara_system` 将 Ara memory port 与预留的标量 memory master 汇成统一 system AXI 出口。

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

IPU 当前只允许一个 outstanding request，用 `req_pending_q` 表示。

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
input logic top_ipu_task_complete_i,
```

- `redirect_valid_i`: 后端发现分支/跳转，需要从新 PC 重新取指。
- `loop_lock_i`: 当前 buffer 锁定为循环体，读完最后一个 packet 后回到 buffer 起点而不重新取指。
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
                          (state_q == SERVE & !bg_fill_done_q)) & !req_pending_q;
assign ipu_mem_rsp_ready_o = ((state_q == FILL) | (state_q == SERVE)) & req_pending_q;
```

FILL 状态：只等待第一个 packet 返回。返回后进入 SERVE。
SERVE 状态：只要 `bg_fill_done_q=0` 就持续发请求，与输出并行进行。初始阶段这些请求继续填当前 active buffer；当前 active buffer 填满后，请求转为填另一个背景 buffer。`req_pending_q` 确保同一时刻最多一条 outstanding request。

### 地址生成

```systemverilog
assign ipu_mem_req_addr_o = fetch_base_q + addr_t'(fill_idx_q * PacketBytes);
```

`fetch_base_q` 指向正在填充的 buffer 的起始地址；切换时通过 `fetch_base_d += BufferBytes` 提前推进，指向下一个待填充块。

### FILL 状态（首包等待）

FILL 状态在第一个 response 返回后立即切换到 SERVE：

- `active_buf_d = fill_buf_q`: 当前填充 buffer 立即成为执行 buffer。
- `buffer_*_valid_d[0] = 1`: 第一个 packet 标记为有效。
- `exec_base_d = fetch_base_q`: 执行 base 锁定为当前 buffer 的起始地址。
- `fill_idx_d += 1`: 后续请求继续填当前 active buffer。

若 `PacketsPerBuffer==1`，第一个 response 同时也是 `fill_done`，此时 `fill_buf_d = !fill_buf_q`，`fetch_base_d += BufferBytes`，直接开始背景预取。

### SERVE 状态（输出 + 背景预取）

**active/background 填充**（`accept_rsp` 时）：

- `fill_idx < LastPacketIdx`：递增 `fill_idx_d`。
- `fill_idx == LastPacketIdx` 且 `fill_buf_q == active_buf_q`：early-serve 阶段的 active buffer 填完，`fill_buf` 切到另一个 buffer，`fetch_base` 推进到下一块，开始背景预取。
- `fill_idx == LastPacketIdx` 且 `fill_buf_q != active_buf_q`：背景填充完成，置 `bg_fill_done_d = 1`，等待 active buffer 消费完后切换。

**输出控制**：

```systemverilog
assign active_packet_valid = active_buf_q ? buffer_b_valid_q[exec_idx_q]
                                          : buffer_a_valid_q[exec_idx_q];
assign bg_stall = (exec_idx_q == LastPacketIdx) & !bg_fill_done_q & !loop_lock_i
                & (fill_buf_q != active_buf_q);
assign ipu_vliwpu_packet_valid_o = (state_q == SERVE) & active_packet_valid & !bg_stall;
```

普通 packet 只有在对应 valid bit 已置位后才会输出；如果 VLIWPU 消费速度追上取指速度，`active_packet_valid=0` 会自然暂停。到达 buffer 最后一个 packet 时，若下一个背景 buffer 尚未完成且不在 loop lock 模式，则 `bg_stall=1` 暂停输出，等 `bg_fill_done_q` 置 1 后再切换。

**buffer 切换**（`take_packet & exec_idx==LastPacketIdx & !loop_lock_i`）：

此时 `bg_fill_done_q` 必为 1（被 `bg_stall` 保护）：

- `active_buf_d = fill_buf_q`: 切换到已预取完成的 buffer。
- `exec_base_d = fetch_base_q`: 执行 base 更新为新 buffer 的起始地址。
- `fill_buf_d = !fill_buf_q`、`fetch_base_d += BufferBytes`: 推进，准备下一次背景预取。
- `fill_idx_d = 0`、`bg_fill_done_d = 0`: 开始新一轮预取。

**loop lock**（`take_packet & exec_idx==LastPacketIdx & loop_lock_i`）：

`exec_idx_d = 0` 重头回放当前 buffer，不做 buffer 切换。即使 `bg_fill_done_q=1`，也不消耗预取结果，等 `loop_lock_i` 变 0 时正常切换。

### redirect 和 task complete

`top_ipu_task_complete_i` 优先级最高，使 IPU 回到 IDLE 并清计数。顶层当前把 `host_hdv_task_complete_i | host_hdv_task_error_i` 接到 IPU 的 `top_ipu_task_complete_i`，并把 `flush_i | host_hdv_task_error_i` 接到 IPU 的 `flush_i`，因此 task 出错时会终止取指，避免 TSU 已退出 active 但旧指令继续派出。

`redirect_valid_i` 次之。若 redirect 目标 16B 对齐、落在当前 active buffer 内、且目标 packet 已 valid，IPU 只更新 `exec_idx_d`，直接从 active buffer 内回放目标 packet；若目标不在 active buffer，IPU 清 buffer valid bit，回到 FILL 并从 `redirect_pc_i` 重新取第一包。未对齐 redirect 在仿真中由 `$fatal` 报错。

## `hdv_vliw_pack_unit.sv`

### 模块定位

VLIWPU 接收 IPU 输出的 128-bit packet，解析上 32-bit hint header 和下方 16-bit slots，生成 execute packet。它的输出仍是 slot 级接口，后续由 HEU 把 slot 规范化成一条条 16/32 bit 指令。

### packet 格式假设

当前默认：

- `FetchPacketWidth=128`
- 上 32 bit 是 hint header。
- 下 96 bit 是 6 个 16-bit slot。

`NumSlots=6`、`SlotWidth=16` 与上述格式一致。

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
- `vliwpu_heu_execute_pc_o`: fetch packet 的 slot 0 绝对地址（即 `packet_pc_q`）。HEU 在此基础上加 `i*2` 得到 slot i 的精确 PC。

### packet holding

```systemverilog
packet_hold_valid_q
packet_q
packet_pc_q
head_slot_q
```

VLIWPU 接收一个 packet 后保存在 `packet_q`，然后可能分多次输出 execute packet。`head_slot_q` 指示当前 execute packet 从哪个 slot 开始。

### header 解析

```systemverilog
assign header = packet_q[FetchPacketWidth-1 -: 32];
assign p_bits = header[20 +: NumSlots-1];
```

header 是 32-bit RISC-V HINT 指令。按论文定义，p-bit 编码在 HINT 的 immediate field；当前 RTL 使用 I-type immediate 低位，即 `header[20 +: NumSlots-1]`。当 `p_bits[i]=0` 时，当前 slot 后停止继续打包。当 `p_bits[i]=1` 且无依赖/资源边界时，可以继续把后续 slot 放入同一 execute packet。

在 `apps/vsaxpy_hdv` 中，当前默认 header 写成：

```asm
.macro HDV_HINT pbits=0x1f
  addi x0, x0, \pbits
.endm
```

这条指令是 RISC-V HINT，因为目的寄存器和源寄存器都是 `x0`，对标量架构状态没有副作用。HDV 将其 immediate 低 5 位解释为 packet 内部的 p-bit：

| bit | RTL 位 | 含义 |
| --- | --- | --- |
| `pbits[0]` | `header[20]` | slot0 可以继续和 slot1 放入同一 execute packet |
| `pbits[1]` | `header[21]` | slot1 可以继续和 slot2 放入同一 execute packet |
| `pbits[2]` | `header[22]` | slot2 可以继续和 slot3 放入同一 execute packet |
| `pbits[3]` | `header[23]` | slot3 可以继续和 slot4 放入同一 execute packet |
| `pbits[4]` | `header[24]` | slot4 可以继续和 slot5 放入同一 execute packet |

控制并行性的规则是：`1` 表示“允许继续向后并入当前 execute packet”，`0` 表示“当前 slot 后结束这个 execute packet”。例如：

```asm
HDV_HINT        // 默认等价于 HDV_HINT 0x1f，所有 p-bit 都请求继续
HDV_HINT 0x00   // 每个 slot 都单独形成边界
HDV_HINT 0x01   // slot0||slot1，然后停止
HDV_HINT 0x03   // slot0||slot1||slot2，然后停止
HDV_HINT 0x07   // slot0||slot1||slot2||slot3，然后停止
```

p-bit 只是软件给出的并行请求，不是无条件并行承诺。`hdv_vliw_pack_unit` 还会根据真实硬件约束提前切断 execute packet，切断条件包括：

- **`p_bits[i]=0`**（或 `ctrl_vliwpu_dep_break_i[i]=1`）：当前 slot 后立即结束当前 execute packet，下一个 slot 开启新 execute packet。
- **SYSTEM/BRANCH 边界**：当前 slot 是 SYSTEM 或 BRANCH 类指令，执行完该指令后强制结束 execute packet（硬件行为，不依赖 p-bit 值）。
- **32-bit 指令内部**：continuation slot 必须与起点 slot 同包（p_bits[i] 被硬件视为强制=1），不受外部 p-bit 控制。
- **packet 末尾**：到达 fetch packet 最后一个 slot（`i+1 == NumSlots-1` 或 `i == NumSlots-1`）时自然结束。

`MaxIssueSlots=NumSlots`（即 6），等效于"不超过一个 fetch packet 的 slot 总数"，不引入额外截断。因此一个 fetch packet 可以产生 1 个到多个 execute packet，由 p-bit 与上述边界共同决定。

### slot 提取

```systemverilog
assign slots[i] = packet_q[i*SlotWidth +: SlotWidth];
```

slot 从 packet 低位开始编号。slot0 是 packet 的最低 16 bit，slot5 是下方 96 bit 中最高的 16 bit。

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

这样，一个 fetch packet 可以拆分成多个 execute packet（由 p-bits 和边界条件决定），也可以在所有 p-bits=1、无 SYSTEM/BRANCH 的情况下整包形成一个 execute packet。

以 vsaxpy（`HDV_HINT 0x1f`，所有 p-bit=1）的 4 个 fetch packet 为例：

| fetch packet | 指令内容 | execute packet 划分 | 原因 |
|---|---|---|---|
| packet 0 | vsetvli + vle32.v + sub | EP1: slots 0-1（vsetvli）<br>EP2: slots 2-5（vle32.v + sub） | vsetvli 是 SYSTEM 指令，硬件强制在 slot 1 后结束 EP |
| packet 1 | vle32.v + slli + vfmacc.vf | EP1: slots 0-5（3 条指令全部并入） | 无 SYSTEM/BRANCH，所有 p-bits=1，整包形成 1 个 EP |
| packet 2 | add + vse32.v + add | EP1: slots 0-5（3 条指令全部并入） | 无 SYSTEM/BRANCH，所有 p-bits=1，整包形成 1 个 EP |
| packet 3 | bnez + ret + nop | EP1: slots 0-1（bnez）<br>EP2: slots 2-3（ret）<br>EP3: slots 4-5（nop） | bnez/ret 均为 BRANCH，每条之后强制结束 EP |

合计：2+1+1+3 = **7 个 execute packet**。

### packet_ready 逻辑

```systemverilog
assign vliwpu_ipu_packet_ready_o = !packet_hold_valid_q;
```

只有 VLIWPU 没有保存 packet，才允许 IPU 送入下一 packet。这里没有在“当前 packet 最后一组 execute 被 HEU 接收”的同一周期拉高 ready，因为 IPU 的 `ipu_vliwpu_packet_i` 在该周期仍是当前 packet；如果同周期 handshake，会把刚处理完的 packet 再装入 VLIWPU。当前写法多留一个周期空隙，但 ready/valid 语义更清晰。

### head_slot 更新

当 HEU 接收当前 execute packet 后：

- 如果本次包含 packet 最后一个 slot，则清空 `packet_hold_valid_q`。
- 否则扫描 `issue_mask`，把 `head_slot_d` 更新到本次最后一个 valid slot 的下一个 slot。

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
assign heu_vliwpu_execute_ready_o = !outstanding_q;
```

HEU 当前一次只处理一个 execute packet。只要有 packet outstanding，就不接收下一个 execute packet。

`heu_scalar_valid_o` 和 `heu_vector_valid_o` 分别由寄存器输出。后端 ready 后对应 dispatch valid 清零。

### pending 和 EP accepted

`scalar_pending_q`、`vector_pending_q` 表示已经向对应后端发出 dispatch，但该后端还没有报告“已接收本 EP 切片”。它们由 `scalar_heu_accepted_i/vector_heu_accepted_i` 清除。

当一个 execute packet 的 scalar/vector pending 都清零，且两个 dispatch valid 都已经被 ready 接收后：

```systemverilog
if (!scalar_pending_d && !vector_pending_d &&
    !scalar_dispatch_valid_d && !vector_dispatch_valid_d) begin
  outstanding_d = 1'b0;
  ep_accepted_d = !error_d;
end
```

`heu_top_ep_accepted_o` 表示一个 execute packet 已经被相关后端接收，不表示整个 task 完成，也不表示 Ara 内部向量指令已经退休。accepted 条件同时检查 dispatch valid，可以避免后端 accepted 信号异常提前时，HEU 接收下一包并覆盖尚未被 ready 握手的输出寄存器。

### 错误处理

`backend_heu_error_i` 在当前 packet outstanding 或接收 packet 同周期有效时，置 `error_q`。`heu_top_ep_error_o` 是 packet 级错误状态，由上层任务控制器决定是否转为 task error。

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
- `ctrl_hdv_loop_lock_i`: loop buffer 锁定控制。
- `ctrl_hdv_dep_break_i`: 依赖检测边界，输入 VLIWPU。

当前依赖检测没有在 VLIWPU 内部完整实现，而是由外部传入 `ctrl_vliwpu_dep_break_i`。

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

标量流水线应在 `hdv_scalar_valid_o` 有效且 `scalar_hdv_ready_i` 握手后接收一组并行标量指令 entry。每个 valid entry 都是一条完整指令。`scalar_hdv_accepted_i` 表示标量后端已经安全接收/处理本 EP 的标量切片，当前 mock host 用固定 latency 产生它。

### vector pipeline 接口

顶层不再导出 `hdv_vector_*` 外部端口。HEU 向量侧在 `hdv_top` 内部连接到 `hdv_vec_dispatch_unit`，再由该模块驱动 Ara accelerator request。向量侧的 `vector_heu_accepted_i` 来自 `vec_heu_accepted_o`，语义是当前 EP 内所有向量指令已被 Ara request 接口接收。

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

第三段是预留标量 AXI slot：

```text
scalar_axi_req  = '0
scalar_axi_resp <- axi_mux
```

当前 RTL 还没有真实标量 LSU，也没有实例化标量侧 data-width converter。保留 `scalar_axi_req/scalar_axi_resp` 是为了维持三路 `axi_mux` 拓扑：Ara vector memory path、未来 scalar memory path、HDV IPU 取指 path。现在 `scalar_axi_req` 绑 0，因此不会从这一路产生事务。以后如果接入的真实标量后端仍是 64-bit 窄 AXI，可以在这个 slot 前补 `axi_dw_converter`，再进入当前 mux。

第四段是 `axi_mux`：

```text
{ara_axi_req_inval, scalar_axi_req, hdv_imem_axi_req} -> axi_mux -> axi_req_o
{ara_axi_resp_inval, scalar_axi_resp, hdv_imem_axi_resp} <- axi_mux <- axi_resp_i
```

`axi_mux` 当前有三个 slave-side master 入口：

- `ara_axi_req_inval/ara_axi_resp_inval`: Ara vector memory path。
- `scalar_axi_req/scalar_axi_resp`: 预留给未来真实标量 LSU 的宽 AXI path，当前 `scalar_axi_req` 绑 0，不产生事务。
- `hdv_imem_axi_req/hdv_imem_axi_resp`: HDV IPU 取指 path。IPU 仍看到简单 ready/valid packet-fetch 接口，`hdv_top` 在内部把它转换成单拍 AXI read。

顶层最终只导出一组 system AXI：

- `axi_req_o`
- `axi_resp_i`

这与 `ara_system` 的顶层接口方向一致。当前标量 AXI 只是预留 slot，外部只看到统一的 system AXI port。

### ara_soc 例化方式

`ara_soc.sv` 的普通非 gate-sim 路径中，原来 `i_system` 直接例化 `ara_system`。现在 `i_system` 改为例化 `hdv_top`：

- `hdv_top.i_ara` 是当前 Ara 向量侧。
- `hdv_top.i_vec_dispatch_unit` 把 HEU 的 vector EP 转成 Ara accelerator request。
- 标量侧仍从 `hdv_top` 端口导出给 `ara_tb` 中的 `hdv_mock_host_core`，真实标量后端尚未接入。
- `hdv_top.axi_req_o/axi_resp_i` 连接回 SoC 原来的 `system_axi_req/system_axi_resp`。

这样系统主访存路径变为：

```text
hdv_top.i_ara vector AXI -> inval_filter -+
                                           +-> hdv_top system AXI -> ara_soc xbar
hdv_top scalar AXI slot (reserved, zero) --+
hdv_top IPU imem AXI ---------------------+
```

HDV task CSR 在 `ara_soc` 中有两条来源：软件 `ctrl_registers` 产生的 CSR 访问，以及 testbench/mock host 直连的 host CSR 访问。host CSR 有效时优先送入 `hdv_top`。HDV scalar dispatch 仍在 `ara_tb` 中由 `hdv_mock_host_core` 接收；vector dispatch 已在 `hdv_top` 内部通过 `hdv_vec_dispatch_unit` 转成 Ara accelerator request。

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
- Ara/vector、预留 scalar slot、HDV IPU 取指到统一 system AXI port 的 mux。

尚未完成：

- 真正接入 scalar pipeline。
- 让 Ara 指令退休/写回结果反向约束 EP accepted；当前 `vec_heu_accepted_o` 只表示 Ara request 接口已经接收。
- 完整 RISC-V decode。
- 精确异常、commit、flush 和分支预测。
- 任务描述符解析。
- 自动 loop pattern 检测。
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
| `accepted_packets_q` | [31:0] | MOCK 内部 | 已被后端接收的 execute packet 数 | 最终达到 7 |
| `expected_ep_accepts_q` | [31:0] | MOCK 内部 | 期望 EP 数 | 7 |
| `csr_valid_o` | 1 | MOCK → TIU | 正在写 HDV CSR | 各阶段依次脉冲 |
| `csr_write_o` | 1 | MOCK → TIU | CSR 写使能 | 写时为 1 |
| `csr_addr_o` | [11:0] | MOCK → TIU | 写入哪个 CSR | 见下方 |
| `csr_wdata_o` | [63:0] | MOCK → TIU | 写入数据 | 见下方 |
| `hdv_mock_ep_accepted_i` | 1 | HEU → MOCK | HEU 发来的 execute packet accepted 脉冲 | 共 7 次脉冲 |
| `task_complete_o` | 1 | MOCK → IPU | 通知 IPU 任务结束 | EP 计数达到 7 后 1 cycle 脉冲 |

**state_q 状态枚举**：

| 值 | 状态名 | 动作 |
|---|---|---|
| 0 | IDLE | 等待 AutoStartDelay |
| 1 | WRITE_TASK_ADDR | 写 VTASK_ADDR = 0x80001000 |
| 2 | WRITE_TASK_DESC | 写 VTASK_PADDR = 0x80001000 |
| 3 | CLEAR_STATUS | 写 VTASK_STATUS 清除旧状态 |
| 4 | WRITE_START | 写 VTASK_START = 1，触发任务 |
| 5 | RUN | 等待并计数 ep_accepted 脉冲 |
| 6 | COMPLETE_TASK | 发 task_complete_o = 1（1 cycle） |
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
| `tsu_tiu_task_done_i` | 1 | TSU → TIU | 来自 TSU 的 task done | mock host 在 EP accepted 计数达标后触发 task complete，TSU 再置 done |

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
| `fill_idx_q` | [1:0] | IPU 内部 | 正在填充第几个 128-bit packet（0-3） | 0→1→2→3 顺序推进 |
| `exec_idx_q` | [1:0] | IPU 内部 | 正在输出第几个 128-bit packet | 每次 VLIWPU 接收后递增 |
| `active_buf_q` | 1 | IPU 内部 | 当前 serve 的 buffer（0=A, 1=B） | 初始 0 |
| `buffer_a_valid_q/buffer_b_valid_q` | [3:0] | IPU 内部 | 每个 128-bit packet 是否已写回 | 首包返回后即可出现 bit0=1 |
| `bg_fill_done_q` | 1 | IPU 内部 | 背景预取完成 | exec_idx=3 前应为 1 |
| `bg_stall` | 1 | IPU 内部 | 等待下一个背景 buffer，暂停输出 | 正常应短暂或不出现 |
| `ipu_vliwpu_packet_valid_o` | 1 | IPU → VLIWPU | 向 VLIWPU 输出有效 packet | SERVE 状态且当前 packet valid 且 !bg_stall |
| `vliwpu_ipu_packet_ready_i` | 1 | VLIWPU → IPU | VLIWPU 接受 packet | 握手 |
| `ipu_vliwpu_packet_o` | [127:0] | IPU → VLIWPU | 128-bit fetch packet 内容 | 高 32 bit = hint header |
| `ipu_vliwpu_packet_pc_o` | [63:0] | IPU → VLIWPU | fetch packet 起始 PC | 0x80001000, +16, +32, +48 |
| `axi_ar_valid_o` | 1 | IPU → SRAM/AXI | AXI 读地址请求 | FILL 阶段依次发出 |
| `axi_ar_addr_o` | [63:0] | IPU → SRAM/AXI | AXI 读地址 | 0x80001000, +16, +32, +48 |
| `axi_r_valid_i` | 1 | SRAM/AXI → IPU | AXI 读数据返回 | |
| `axi_r_data_i` | [127:0] | SRAM/AXI → IPU | 返回的 128-bit 数据 | 即 SRAM 中的 VLIW 指令 |
| `top_ipu_task_complete_i` | 1 | MOCK → IPU | 来自 mock host，任务结束 | MOCK.mock_hdv_task_complete_o |

**关键波形特征**：`state_q` 应从 IDLE→FILL（axi_ar 握手）→SERVE（packet_valid 拉高）。

---

### 阶段 4：VLIWPU — VLIW 打包

**路径**：`VLIWPU.*`

| 信号 | 位宽 | 方向（源 → 目的） | 含义 | 期望值/事件 |
|---|---|---|---|---|
| `packet_hold_valid_q` | 1 | VLIWPU 内部 | 持有一个 fetch packet | 接收后为 1，最后一个 EP 出去后清 0 |
| `packet_q` | [127:0] | VLIWPU 内部 | 锁存的 fetch packet | 高 32 bit 是 hint header |
| `header` | [31:0] | VLIWPU 内部 | hint header（addi x0,x0,pbits） | 低 12 bit 含 p-bits |
| `p_bits` | [4:0] | VLIWPU 内部 | 并行控制位 | vsaxpy 全为 5'b11111 |
| `slots[0..5]` | [15:0] each | VLIWPU 内部 | 6 个 16-bit 指令槽 | slot i = packet_q[i*16+:16] |
| `slot_is_32b` | [5:0] | VLIWPU 内部 | 哪些 slot 是 32-bit 指令起点 | vsaxpy: 6'b010101 |
| `slot_is_continuation` | [5:0] | VLIWPU 内部 | 哪些 slot 是 32-bit 续半 | vsaxpy: 6'b101010 |
| `class_system_mask` | [5:0] | VLIWPU 内部 | SYSTEM 指令标记 | packet0 slot0: bit0=1 |
| `class_branch_mask` | [5:0] | VLIWPU 内部 | BRANCH 指令标记 | packet3 slot0,2: bit0,2=1 |
| `head_slot_q` | [2:0] | VLIWPU 内部 | 当前 EP 从哪个 slot 开始 | 0→2→0→0→0→2→4 |
| `issue_mask` | [5:0] | VLIWPU 内部 | 当前 EP 包含哪些 slot | EP1: 6'b000011, EP2: 6'b111100, EP3/4: 6'b111111, ... |
| `issue_count` | [3:0] | VLIWPU 内部 | 当前 EP 包含的 slot 数 | EP1:2, EP2:4, EP3/4:6, EP5/6/7:2 |
| `stop_pack` | 1 | VLIWPU 内部 | EP 边界已确定 | 每个 EP 确定后组合逻辑为 1 |
| `last_slot_in_packet` | 1 | VLIWPU 内部 | 本 EP 是该 fetch packet 的最后 | 清空 packet_hold_valid_q |
| `vliwpu_heu_execute_valid_o` | 1 | VLIWPU → HEU | EP 有效发往 HEU | = packet_hold_valid_q |
| `heu_vliwpu_execute_ready_i` | 1 | HEU → VLIWPU | HEU 接收 EP | = !HEU.outstanding_q |
| `vliwpu_heu_execute_slot_valid_o` | [5:0] | VLIWPU → HEU | EP slot 掩码 | 同 issue_mask |
| `vliwpu_heu_execute_class_o[i]` | [1:0] each | VLIWPU → HEU | slot i 指令类别 | 0=SCALAR,1=VECTOR,2=SYSTEM,3=BRANCH |

**7 个 EP 的 issue_mask 速查（vsaxpy）**：

| EP | fetch packet | head_slot | issue_mask（[5:0]，bit0=slot0） | 指令 |
|---|---|---|---|---|
| EP1 | packet 0 | 0 | 6'b000011 | vsetvli（SYSTEM 截断） |
| EP2 | packet 0 | 2 | 6'b111100 | vle32.v + sub |
| EP3 | packet 1 | 0 | 6'b111111 | vle32.v + slli + vfmacc |
| EP4 | packet 2 | 0 | 6'b111111 | add + vse32.v + add |
| EP5 | packet 3 | 0 | 6'b000011 | bnez（BRANCH 截断） |
| EP6 | packet 3 | 2 | 6'b001100 | ret（BRANCH 截断） |
| EP7 | packet 3 | 4 | 6'b110000 | nop |

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
| `vector_heu_accepted_i` | 1 | 向量后端 → HEU | 向量后端接收本 EP 切片 | `hdv_vec_dispatch_unit` 发完当前 EP 内向量指令后脉冲 |
| `ep_accepted_q` | 1 | HEU 内部 | ep_accepted 脉冲（**1 cycle**） | 每个 EP 被后端接收后出现，次周期自动清 0 |
| `heu_top_ep_accepted_o` | 1 | HEU → MOCK | = ep_accepted_q，连到 MOCK.hdv_mock_ep_accepted_i | 共 7 次脉冲 |
| `heu_vliwpu_execute_ready_o` | 1 | HEU → VLIWPU | = !outstanding_q | HEU 空闲时为 1 |

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
