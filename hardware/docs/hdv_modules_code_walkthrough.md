# HDV Prototype RTL Code Walkthrough

本文档逐语段说明 `hardware/src/hdv` 下新增的 Hybrid Decoupled Vector (HDV) 原型 RTL。当前这些模块是独立前端原型，没有接入现有 Ara 顶层；`hdv_top` 只负责把新模块串联起来，并把后续连接标量流水线、向量流水线、取指存储器和任务控制器所需的接口暴露出来。

## 文件总览

| 文件 | 模块 | 作用 |
|---|---|---|
| `hdv_pkg.sv` | `hdv_pkg` | HDV CSR 地址、指令类别、任务状态类型定义 |
| `hdv_task_interface_unit.sv` | `hdv_task_interface_unit` | Task Interface Unit (TIU)，提供任务 CSR 接口 |
| `hdv_task_schedule_unit.sv` | `hdv_task_schedule_unit` | Task Schedule Unit (TSU)，用 FIFO 管理任务提交顺序 |
| `hdv_instruction_prefetch_unit.sv` | `hdv_instruction_prefetch_unit` | Instruction Prefetch Unit (IPU)，双 64B buffer 取指 |
| `hdv_vliw_pack_unit.sv` | `hdv_vliw_pack_unit` | VLIW Pack Unit，按 hint header 和依赖边界切 execute packet |
| `hdv_hybrid_execution_unit.sv` | `hdv_hybrid_execution_unit` | Hybrid Execution Unit 前端分派，把标量/向量指令分流 |
| `hdv_top.sv` | `hdv_top` | 独立顶层 wrapper，连接上述模块并暴露外部接口 |

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
input  logic         csr_valid_i,
input  logic         csr_write_i,
input  logic [11:0]  csr_addr_i,
input  logic [XLEN-1:0] csr_wdata_i,
output logic         csr_ready_o,
output logic [XLEN-1:0] csr_rdata_o,
output logic         csr_error_o,
```

这是一个最小 CSR-like 接口：

- `csr_valid_i`: 表示本周期有 CSR 访问。
- `csr_write_i`: 1 表示写，0 表示读。
- `csr_addr_i`: 访问地址。
- `csr_wdata_i`: 写数据。
- `csr_ready_o`: 当前实现恒为 1，表示 TIU 不会反压 CSR 访问。
- `csr_rdata_o`: 读返回数据。
- `csr_error_o`: 访问非 HDV CSR 地址时置位。

### 任务输出端口

```systemverilog
output logic  task_valid_o,
input  logic  task_ready_i,
output addr_t task_entry_o,
output addr_t task_desc_o,
```

该接口连接 TSU。TIU 在软件写 `VTASK_START` 后置 `task_valid_o`，并把当前 `VTASK_ADDR` 和 `VTASK_PADDR` 输出为任务入口和任务描述符地址。TSU 通过 `task_ready_i` 接收任务。

### 状态回传端口

```systemverilog
input  logic task_busy_i,
input  logic task_done_i,
input  logic task_error_i,
output logic task_status_clear_o
```

这些信号连接任务调度或任务控制层：

- `task_busy_i`: 外部告诉 TIU 当前 HDV 仍忙。
- `task_done_i`: 任务完成事件，TIU 锁存 DONE。
- `task_error_i`: 任务错误事件，TIU 锁存 ERROR。
- `task_status_clear_o`: 软件写 `VTASK_STATUS` 的 DONE/ERROR 位时产生，用于清除 TSU 状态。

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
assign csr_ready_o = 1'b1;
assign csr_error_o = csr_valid_i
                   & (csr_addr_i != HDV_CSR_VTASK_ADDR)
                   & ...
```

TIU 当前不做等待，所有 CSR 访问单周期响应。`csr_error_o` 只在 `csr_valid_i` 有效且地址不属于四个 HDV CSR 时置位。

### START 检测

```systemverilog
assign start_pulse = csr_valid_i & csr_write_i
                   & (csr_addr_i == HDV_CSR_VTASK_START)
                   & csr_wdata_i[0];
```

软件向 `VTASK_START` 写 bit0=1 即触发一次任务提交。这里没有真正保存 START 寄存器，而是将写操作解释为 pulse。

### CSR 读多路选择

`p_read_mux` 根据 `csr_addr_i` 返回不同 CSR 数据：

- 读 `VTASK_ADDR`: 返回 `vtask_addr_q`。
- 读 `VTASK_PADDR`: 返回 `vtask_paddr_q`。
- 读 `VTASK_START`: bit0 返回 `task_valid_q`，表示是否有任务等待提交。
- 读 `VTASK_STATUS`: bit0 为 `task_busy_i | task_valid_q`，bit1 为 DONE，bit2 为 ERROR。

BUSY 由外部 busy 和 TIU 内部 pending task 共同决定，避免任务还没被 TSU 接收时软件读到 idle。

### CSR 写和状态更新

`p_next` 首先保持当前状态，然后处理 CSR 写：

- 写 `VTASK_ADDR`: 更新任务入口地址。
- 写 `VTASK_PADDR`: 更新任务描述符地址。
- 写 `VTASK_STATUS`: bit1/bit2 采用 write-one-clear 语义，清除 DONE/ERROR。

随后处理任务握手：

```systemverilog
if (task_valid_q && task_ready_i) begin
  task_valid_d = 1'b0;
end
```

如果 TSU 已经接收任务，则清除 pending valid。

再处理 `start_pulse`：

- 如果当前没有 pending task，或者同周期 TSU 正好 ready 接收旧 task，则允许提交新 task。
- 如果已有 pending task 且 TSU 不 ready，则置 `error_d`，表示重复 start。

最后处理硬件完成/错误事件：

```systemverilog
if (task_done_i)  done_d  = 1'b1;
if (task_error_i) error_d = 1'b1;
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

- `task_done_i`: 外部任务控制器确认整个 task 完成。
- `task_error_i`: 整个 task 出错。
- `busy_o/done_o/error_o`: 给 TIU 和顶层使用。

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
assign task_in_ready_o = !fifo_full;
assign fifo_push = task_in_valid_i & task_in_ready_o;
```

只要 FIFO 未满，TSU 可以接受 TIU 的任务。入队握手成功时 push。

### 出队逻辑

```systemverilog
assign task_out_valid_o = !fifo_empty & !active_q;
assign fifo_pop = task_out_valid_o & task_out_ready_i;
```

TSU 一次只允许一个 active task。只有当前没有 active task 且 FIFO 非空时，才向 IPU 发出下一个任务。

### busy/done/error

```systemverilog
assign busy_o  = active_q | !fifo_empty;
assign done_o  = done_q;
assign error_o = error_q;
```

`busy_o` 表示已有 active task 或还有排队任务。`done_o/error_o` 是粘滞状态，由任务完成/错误事件置位，由 `status_clear_i` 或 `flush_i` 清除。

### 状态机逻辑

TSU 没有显式 enum 状态，只用 `active_q` 表示是否有任务正在执行：

- `fifo_pop`: 进入 active，清除旧 done/error。
- `active_q && task_error_i`: 当前任务失败，退出 active，置 error。
- `active_q && task_done_i`: 当前任务完成，退出 active，置 done。
- `status_clear_i`: 只清除 done/error，不影响 active task。
- `flush_i`: 清除 active/done/error。

### 时序寄存器

`active_q/done_q/error_q` 复位清零，正常周期更新。FIFO 自身由 `fifo_v3` 管理。

## `hdv_instruction_prefetch_unit.sv`

### 模块定位

IPU 接收 TSU 派发的 task，从 `task_entry_i` 开始按 128-bit fetch packet 取指，写入两个 64B buffer，然后向 VLIWPU 输出 packet。

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
input  logic  task_valid_i,
output logic  task_ready_o,
input  addr_t task_entry_i,
input  addr_t task_desc_i,
```

IPU 在 `IDLE` 状态 ready。接收 task 后锁存入口地址和描述符地址。`task_desc_i` 当前只锁存并通过 `task_desc_o` 输出，给后续任务控制器或访存模块使用。

### instruction memory 接口

```systemverilog
output logic mem_req_valid_o,
input  logic mem_req_ready_i,
output addr_t mem_req_addr_o,
input  logic mem_rsp_valid_i,
output logic mem_rsp_ready_o,
input  logic [FetchPacketWidth-1:0] mem_rsp_data_i,
```

请求和响应都采用 ready/valid：

- `mem_req_valid_o && mem_req_ready_i`: 发出一个取指请求。
- `mem_rsp_valid_i && mem_rsp_ready_o`: 接收一个 128-bit packet。

IPU 当前只允许一个 outstanding request，用 `req_pending_q` 表示。

### packet 输出接口

```systemverilog
output logic packet_valid_o,
input  logic packet_ready_i,
output logic [FetchPacketWidth-1:0] packet_o,
output addr_t packet_pc_o,
```

`packet_o` 来自当前 active buffer，`packet_pc_o` 是对应 packet 的 PC。VLIWPU 通过 `packet_ready_i` 接收。

### 控制接口

```systemverilog
input logic redirect_valid_i,
input addr_t redirect_pc_i,
input logic loop_lock_i,
input logic task_complete_i,
```

- `redirect_valid_i`: 后端发现分支/跳转，需要从新 PC 重新取指。
- `loop_lock_i`: 当前 buffer 锁定为循环体，读完最后一个 packet 后回到 buffer 起点而不重新取指。
- `task_complete_i`: 整个任务完成，IPU 回到 idle。

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
- `FILL`: 向 instruction memory 请求并填充一个 64B buffer。
- `SERVE`: 从 active buffer 向 VLIWPU 输出 packet。

### 双 buffer 寄存器

```systemverilog
buffer_t buffer_a_q;
buffer_t buffer_b_q;
logic active_buf_q;
logic fill_buf_q;
```

`active_buf_q` 指示当前输出 packet 来自哪个 buffer。`fill_buf_q` 指示当前填充哪个 buffer。二者通过状态切换交替。

buffer 数据本身不走复位，只在 `accept_rsp` 时写入对应 entry。这种写法减少 reset 扇出，也避免组合逻辑每周期复制整个 64B buffer。

### 请求/响应控制

```systemverilog
assign mem_req_valid_o = (state_q == FILL) & !req_pending_q;
assign mem_rsp_ready_o = (state_q == FILL) & req_pending_q;
```

IPU 在 FILL 状态且没有 pending request 时发请求；请求被接受后置 `req_pending_q`；响应被接受后清 `req_pending_q` 并写 buffer。

### 地址生成

```systemverilog
assign mem_req_addr_o = fetch_base_q + addr_t'(fill_idx_q * PacketBytes);
```

`fetch_base_q` 是当前 buffer 的起始 PC，`fill_idx_q` 是 buffer 内 packet 编号。默认每次取 16B。

### FILL 状态

FILL 状态做两件事：

1. 如果请求握手成功，置 `req_pending_d`。
2. 如果响应握手成功，写 buffer；如果填满 buffer，则切换到 SERVE，否则 `fill_idx_d++`。

填满 buffer 后：

- `active_buf_d = fill_buf_q`: 刚填好的 buffer 成为执行 buffer。
- `fill_buf_d = !fill_buf_q`: 下一次填另一个 buffer。
- `fetch_base_d += BufferBytes`: 下一块顺序取指地址。

### SERVE 状态

SERVE 状态在 `packet_valid_o && packet_ready_i` 时前进：

- 如果还没到最后一个 packet，`exec_idx_d++`。
- 如果到最后一个 packet：
  - `loop_lock_i=1`: `exec_idx_d=0`，重复当前 buffer。
  - `loop_lock_i=0`: 进入 FILL，准备取下一块。

### redirect 和 task complete

`task_complete_i` 优先级最高，使 IPU 回到 IDLE 并清计数。`redirect_valid_i` 次之，使 IPU 从 `redirect_pc_i` 开始重新 FILL。这里会丢弃当前 buffer 内容，符合 redirect 语义。

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

- `packet_valid_i/packet_ready_o`: 从 IPU 接收 packet。
- `packet_i`: 128-bit packet。
- `packet_pc_i`: packet 起始 PC。
- `dep_break_i`: 外部依赖检测输入，表示某两个 slot 之间不能继续并行打包。

输出：

- `execute_valid_o/execute_ready_i`: 发给 HEU 的 execute packet。
- `execute_slot_valid_o`: 哪些 slot 属于当前 execute packet。
- `execute_slot_o`: 16-bit slot 原始内容。
- `execute_slot_is_32b_o`: 哪些 slot 是 32-bit 指令的低半部分。
- `execute_class_o`: 每个 slot 的指令类别。
- `execute_pc_o`: 当前 execute packet 起始 PC。

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
```

header 的 p-bit 当前直接用 `header[i]`。当 `header[i]=0` 时，当前 slot 后停止继续打包。当 `header[i]=1` 且无依赖/资源边界时，可以继续把后续 slot 放入同一 execute packet。

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

对 32-bit 指令的 continuation slot，`execute_class_o` 复制低半 slot 的类别，保证 HEU 后续能一致处理。

### execute packet 形成

`p_issue_mask` 从 `head_slot_q` 开始扫描 slot：

- 先把当前 slot 放入 `issue_mask`。
- 如果当前 slot 是 32-bit 起点，同时放入下一个 slot，并停止本次打包，保证 32-bit 指令不被拆开。
- 如果 header p-bit 为 0、`dep_break_i[i]` 为 1、当前是 system/branch，则停止继续打包。
- 如果达到 `MaxIssueSlotsCount`，也停止继续打包。

当前实现偏保守：32-bit 指令单独形成一个 execute packet。这有利于保证标量流水线拿到完整指令，后续可再优化为允许多个独立 32-bit 指令同包并发。

### packet_ready 逻辑

```systemverilog
assign packet_ready_o = !packet_hold_valid_q || (execute_accept && last_slot_in_packet);
```

只有 VLIWPU 没有保存 packet，或者当前 packet 最后一个 slot 已被 HEU 接收，才允许 IPU 送入下一 packet。

### head_slot 更新

当 HEU 接收当前 execute packet 后：

- 如果本次包含 packet 最后一个 slot，则清空 `packet_hold_valid_q`。
- 否则扫描 `issue_mask`，把 `head_slot_d` 更新到本次最后一个 valid slot 的下一个 slot。

## `hdv_hybrid_execution_unit.sv`

### 模块定位

HEU 当前不是完整执行单元，而是前端 dispatch block。它接收 VLIWPU 的 execute packet，按 `execute_class_i` 分成标量和向量两条输出流。

### 输入 execute packet

输入仍是 slot 级：

- `execute_slot_valid_i`: 哪些 slot 属于当前 execute packet。
- `execute_slot_i`: 16-bit slot 内容。
- `execute_slot_is_32b_i`: 哪些 slot 是 32-bit 指令低半部分。
- `execute_class_i`: slot 对应类别。
- `execute_pc_i`: execute packet 起始 PC。

### 标量/向量输出接口

HEU 输出已经不是 slot，而是一条条规范化指令：

```systemverilog
output logic [NumSlots-1:0]       scalar_insn_valid_o,
output logic [NumSlots-1:0][31:0] scalar_insn_o,
output logic [NumSlots-1:0]       scalar_insn_is_32b_o,
output addr_t [NumSlots-1:0]      scalar_insn_pc_o,
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
   - 32-bit 指令: 拼 `{execute_slot_i[i+1], execute_slot_i[i]}`。
   - 16-bit 指令: 拼 `{16'b0, execute_slot_i[i]}`。
5. 根据 `execute_class_i[i]` 决定置 scalar valid 还是 vector valid。
6. 计算每条指令自己的 PC: `execute_pc_i + i * 2`。

### 输出寄存器

HEU 使用寄存器保存 dispatch packet：

- `dispatch_insn_q`
- `dispatch_insn_is_32b_q`
- `dispatch_insn_pc_q`
- `scalar_insn_valid_q`
- `vector_insn_valid_q`

这样 `scalar_valid_o` 和 `vector_valid_o` 不组合依赖下游 `ready`，避免 ready/valid 组合环。

### ready/valid 语义

```systemverilog
assign execute_ready_o = !outstanding_q;
```

HEU 当前一次只处理一个 execute packet。只要有 packet outstanding，就不接收下一个 execute packet。

`scalar_valid_o` 和 `vector_valid_o` 分别由寄存器输出。后端 ready 后对应 dispatch valid 清零。

### pending 和完成

`scalar_pending_q`、`vector_pending_q` 表示已经派发给对应后端但尚未完成。它们由 `scalar_done_i/vector_done_i` 清除。

当一个 execute packet 的 scalar/vector pending 都清零后：

```systemverilog
outstanding_d = 1'b0;
done_d = !error_d;
```

`execute_done_o` 表示一个 execute packet 完成，不表示整个 task 完成。

### 错误处理

`backend_error_i` 在当前 packet outstanding 或接收 packet 同周期有效时，置 `error_q`。`execute_error_o` 是 packet 级错误状态，由上层任务控制器决定是否转为 task error。

## `hdv_top.sv`

### 模块定位

`hdv_top` 是独立集成顶层，只连接新增模块，不接入现有 Ara RTL。它负责形成以下链路：

```text
CSR/TIU -> TSU -> IPU -> VLIWPU -> HEU -> scalar/vector pipeline ports
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

后续可以通过顶层参数统一配置 HDV 前端。

### CSR 接口

顶层将 CSR 端口直接连接到 TIU：

- `csr_valid_i`
- `csr_write_i`
- `csr_addr_i`
- `csr_wdata_i`
- `csr_ready_o`
- `csr_rdata_o`
- `csr_error_o`

### 取指存储器接口

顶层将 IPU 的 memory 接口导出：

- `imem_req_valid_o`
- `imem_req_ready_i`
- `imem_req_addr_o`
- `imem_rsp_valid_i`
- `imem_rsp_ready_o`
- `imem_rsp_data_i`

后续可接 I-cache、AXI read adapter 或测试 memory model。

### 控制接口

顶层暴露：

- `redirect_valid_i/redirect_pc_i`: 后端跳转或异常重定向。
- `loop_lock_i`: loop buffer 锁定控制。
- `dep_break_i`: 依赖检测边界，输入 VLIWPU。

当前依赖检测没有在 VLIWPU 内部完整实现，而是由外部传入 `dep_break_i`。

### task 完成接口

```systemverilog
input logic task_complete_i;
input logic task_error_i;
```

这两个信号是 task 级，不是 execute packet 级。顶层明确要求未来 task controller 只在整个任务结束时断言它们。

### active task descriptor

`active_task_desc_o` 来自 IPU 锁存的 task descriptor。后续 scalar/vector pipeline 或 task controller 可用它读取参数、数据地址、长度等任务元信息。

### scalar pipeline 接口

顶层导出 HEU 标量侧接口：

- `scalar_valid_o/scalar_ready_i`
- `scalar_insn_valid_o`
- `scalar_insn_o`
- `scalar_insn_is_32b_o`
- `scalar_insn_pc_o`
- `scalar_done_i`

标量流水线应在 `scalar_valid_o` 有效且 `scalar_ready_i` 握手后接收一组并行标量指令 entry。每个 valid entry 都是一条完整指令。

### vector pipeline 接口

顶层导出 HEU 向量侧接口：

- `vector_valid_o/vector_ready_i`
- `vector_insn_valid_o`
- `vector_insn_o`
- `vector_insn_is_32b_o`
- `vector_insn_pc_o`
- `vector_done_i`

向量流水线同样看到的是完整指令，而不是 16-bit slot。

### execute packet 状态

```systemverilog
execute_busy_o
execute_done_o
execute_error_o
```

这些信号来自 HEU，只表示 execute packet 级状态。顶层没有把 `execute_error_o` 自动并入 `task_error_i`，避免把单条 execute packet 的错误误当成整个 task 的错误。是否转成 task error 由外部 task controller 决定。

### 内部连接

顶层内部信号按模块边界命名：

- `tiu_*`: TIU 到 TSU。
- `tsu_*`: TSU 到 IPU。
- `packet_*`: IPU 到 VLIWPU。
- `execute_*`: VLIWPU 到 HEU。
- `heu_*`: HEU 状态。

这种命名使接口方向和数据流清晰，后续接入 Ara 顶层时也更容易定位边界。

## 当前实现边界

当前 HDV 原型已经完成：

- task CSR 接口。
- task FIFO 调度。
- 双 buffer instruction prefetch。
- packet 到 execute packet 的保守 VLIW 分包。
- 标量/向量指令分流。
- 压缩/非压缩指令规范化输出。
- 顶层 wrapper 连接。

尚未完成：

- 真正接入 Ara vector pipeline。
- 真正接入 scalar pipeline。
- 完整 RISC-V decode。
- 精确异常、commit、flush 和分支预测。
- 任务描述符解析。
- 自动 loop pattern 检测。
- 完整 scalar-vector 依赖 scoreboard。

因此当前代码适合作为 HDV 前端结构原型和后续集成边界，不应直接视为完整处理器执行子系统。
