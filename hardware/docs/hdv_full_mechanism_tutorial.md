# HDV Mechanism Tutorial

本文档面向阅读和调试当前 `hardware/src/hdv` RTL。目标不是逐字翻译代码，而是把每个模块的关键逻辑块、状态机、寄存器、握手和边界条件解释清楚，使你能够沿着一条 HDV task 从主核提交到 Ara 接收向量指令的全过程定位问题。

当前代码中的 HDV 原型可以理解为：

```text
host/mock scalar core
  -> TIU task CSR
  -> TSU task queue
  -> IPU instruction fetch
  -> VLIWPU fetch-packet to execute-packet packing
  -> HEU scalar/vector split
  -> scalar backend mock or future scalar pipeline
  -> vector dispatch adapter
  -> Ara vector backend
```

几个语义先统一：

- `task done` 表示整个 HDV task 结束，由 task controller 或 mock host 告诉 TSU/TIU。
- `ep_accepted` 表示一个 execute packet 的标量/向量切片已经被对应后端接收，不表示指令真正执行完成。
- `vec_heu_accepted_o` 表示当前 EP 中所有向量指令已经被 Ara accelerator request 接口接收，不表示 Ara lane/VLSU 已退休这些指令。
- `ready/valid` 一律遵循同周期 `valid & ready` 才发生传输。

## 1. 全局数据流

### 1.1 任务提交路径

主核或 mock host 通过四个 HDV CSR 配置 task：

```text
VTASK_ADDR   -> task entry PC
VTASK_PADDR  -> task descriptor pointer
VTASK_STATUS -> clear done/error
VTASK_START  -> write bit0=1 to submit
```

TIU 把 CSR 写入转成 `tiu_tsu_task_valid_o`。TSU 接收后放入 FIFO。IPU 空闲时从 TSU 取出一个 task，从 entry PC 开始取 128-bit fetch packet。VLIWPU 根据 fetch packet 顶部 hint header 的 p-bit 和依赖断点切成 execute packet。HEU 再把 EP 内指令按类别分到 scalar 和 vector 两个后端。

### 1.2 指令 fetch packet 格式

当前 VLIWPU 假设一个 128-bit fetch packet 结构如下：

```text
[127:96]  32-bit HDV_HINT header
[ 95: 0]  six 16-bit instruction slots
```

如果某个 slot 是 32-bit RISC-V 指令，它占用连续两个 16-bit slot。VLIWPU 用低 2 bit `11` 判断 32-bit 指令起始 halfword，并把下一 slot 标成 continuation。

### 1.3 execute packet 语义

execute packet 是 VLIWPU 给 HEU 的一次发射包。包内有：

- `slot_valid`: 哪些 slot 属于本 EP。
- `slot`: 原始 16-bit halfword。
- `slot_is_32b`: 哪些 slot 是 32-bit 指令起点。
- `class`: 每个 slot 的 SCALAR/VECTOR/SYSTEM/BRANCH 分类。
- `pc`: fetch packet 基地址；HEU 用 `pc + slot_index * 2` 算每条指令 PC。

HEU 当前一次只允许一个 EP outstanding。只有这个 EP 的 scalar/vector 切片都被后端 accepted 后，才向 VLIWPU 释放 ready 接收下一个 EP。

## 2. `hdv_pkg.sv`

### 2.1 CSR 常量

`hdv_pkg` 定义四个任务 CSR 地址：

```systemverilog
HDV_CSR_VTASK_ADDR   = 12'h7c0
HDV_CSR_VTASK_PADDR  = 12'h7c1
HDV_CSR_VTASK_START  = 12'h7c2
HDV_CSR_VTASK_STATUS = 12'h7c3
```

这些地址只描述 HDV 控制面，不负责真实 RISC-V CSR 权限或异常。`ctrl_registers` 或 mock host 可以把访问转到 TIU。

### 2.2 指令分类枚举

`hdv_inst_class_e` 有四类：

- `HDV_INST_SCALAR`: 普通标量整数/浮点/未知指令。
- `HDV_INST_VECTOR`: RVV 算术、vector load、vector store。
- `HDV_INST_SYSTEM`: CSR/system 类，当前走 scalar 侧。
- `HDV_INST_BRANCH`: branch/jal/jalr，当前走 scalar 侧并由 mock 分支逻辑或未来真实标量流水线产生 redirect。

分类发生在 VLIWPU，消费分类的是 HEU。

### 2.3 task status 结构体

`hdv_task_status_t` 当前没有作为端口直接使用，只是为将来结构化状态总线预留。当前 RTL 用分散的 `busy/done/error` 单 bit。

## 3. `hdv_task_interface_unit.sv`：TIU

TIU 是 HDV 的任务 CSR 前端。它把 host CSR 写入转换成 task valid，并保存软件可见状态。

### 3.1 输入输出边界

CSR 输入：

- `host_tiu_csr_valid_i`: 有 CSR 访问。
- `host_tiu_csr_write_i`: 1 为写，0 为读。
- `host_tiu_csr_addr_i`: 12-bit CSR 地址。
- `host_tiu_csr_wdata_i`: 写数据。

CSR 输出：

- `tiu_host_csr_ready_o`: 当前固定为 1，说明 TIU 不反压 CSR。
- `tiu_host_csr_rdata_o`: 读返回值。
- `tiu_host_csr_error_o`: 地址不是四个 HDV CSR 时置 1。

TSU 任务输出：

- `tiu_tsu_task_valid_o`: TIU 持有一个待提交任务。
- `tsu_tiu_task_ready_i`: TSU FIFO 未满时为 1。
- `tiu_tsu_task_entry_o`: task entry PC。
- `tiu_tsu_task_desc_o`: task descriptor pointer。

状态输入：

- `top_tiu_task_busy_i`: 顶层综合的 HDV busy。
- `tsu_tiu_task_done_i`: TSU 报告 task done。
- `tsu_tiu_task_error_i`: TSU 报告 task error。
- `tiu_tsu_status_clear_o`: host 写 STATUS bit1/bit2 清状态时给 TSU。

### 3.2 CSR error

`tiu_host_csr_error_o` 是组合逻辑。它在有 CSR 访问且地址不属于四个 HDV CSR 时置位。因为 `tiu_host_csr_ready_o=1`，错误也在访问同周期返回。

### 3.3 task valid 和 task 地址寄存器

TIU 内部寄存：

- `vtask_addr_q`: 最近写入的 task entry。
- `vtask_paddr_q`: 最近写入的 task descriptor pointer。
- `task_valid_q`: 有一个 task 等待 TSU 接收。
- `done_q/error_q`: 软件读 STATUS 看到的 sticky 状态。

`tiu_tsu_task_valid_o = task_valid_q`。只要 TSU 尚未 ready 接收，valid 会保持。

### 3.4 START pulse

`start_pulse` 在 host 写 `VTASK_START` 且 bit0=1 时产生。这个寄存器不是保存型 START，而是 write-pulse 语义。这样软件每次写 1 就提交一次。

### 3.5 CSR read mux

读 `VTASK_ADDR` 返回 `vtask_addr_q`。读 `VTASK_PADDR` 返回 `vtask_paddr_q`。读 `VTASK_START` 的 bit0 返回 `task_valid_q`，表示是否还有 task 没被 TSU 接收。读 `VTASK_STATUS` 时：

- bit0 = `top_tiu_task_busy_i | task_valid_q`
- bit1 = `done_q`
- bit2 = `error_q`

`task_valid_q` 参与 busy 是为了避免 task 刚提交但还没被 TSU pop 时软件读到 idle。

### 3.6 `p_next` 状态优先级

`p_next` 先默认保持所有 `_q` 值，再分阶段更新。

第一段处理 TSU 回来的 done/error。当前代码注释写的是这些输入“最低优先级”，实际效果是：后面 CSR write 清 STATUS 可以覆盖它们。因此 host 可以清除 sticky done/error。

第二段处理 `task_valid_q && tsu_tiu_task_ready_i`。当 TSU 接收 task，TIU 清除 pending valid。

第三段处理 `start_pulse`。如果没有 pending task，或 TSU 同周期 ready 接收旧 task，则允许新 task 进入 `task_valid_d=1`，并清除旧 done/error。若已有 pending task 且 TSU 不 ready，则置 `error_d=1`，表示重复提交。

第四段处理 CSR write：

- 写 `VTASK_ADDR`: 更新 `vtask_addr_d`。
- 写 `VTASK_PADDR`: 更新 `vtask_paddr_d`。
- 写 `VTASK_STATUS`: bit1 清 done，bit2 清 error，同时 `tiu_tsu_status_clear_o` 通知 TSU 清它的 sticky 状态。

### 3.7 `p_regs`

复位清零所有寄存器。正常周期 `_q <= _d`。TIU 没有显式 FSM，行为由这些寄存器组合出来。

## 4. `hdv_task_schedule_unit.sv`：TSU

TSU 是任务队列。它把 TIU 提交的 task 按顺序排队，一次只向 IPU 派发一个 active task。

### 4.1 FIFO 数据结构

`task_t` 只有两个字段：

- `entry`: task entry PC。
- `desc`: task descriptor pointer。

`fifo_v3` 使用 `FALL_THROUGH=1`，所以 FIFO 非空时 `fifo_out` 可以直接被下游看到。

### 4.2 入队握手

```systemverilog
fifo_push = tiu_tsu_task_valid_i & tsu_tiu_task_ready_o
tsu_tiu_task_ready_o = !fifo_full
```

只要 FIFO 未满，TSU 就接受 TIU task。push 成功时 `{entry, desc}` 被写入 FIFO。

### 4.3 出队握手

```systemverilog
tsu_ipu_task_valid_o = !fifo_empty & !active_q
fifo_pop = tsu_ipu_task_valid_o & ipu_tsu_task_ready_i
```

TSU 保证同一时刻只有一个 active task。只要 `active_q=1`，即使 FIFO 还有后续 task，也不会向 IPU 输出下一个。

### 4.4 busy/done/error

- `tsu_top_busy_o = active_q | !fifo_empty`。
- `tsu_top_done_o = done_q`。
- `tsu_top_error_o = error_q`。

`done_q/error_q` 是 sticky 状态，host 写 STATUS 清除时通过 `tiu_tsu_status_clear_i` 清掉。

### 4.5 `p_next`

`fifo_pop` 表示一个 task 被 IPU 接收，TSU 置 `active_d=1`，同时清旧 done/error。

`tiu_tsu_status_clear_i` 清 sticky done/error，但不影响 active task。

若 active task 期间 `top_tsu_task_error_i=1`，TSU 清 active、置 error。

若 active task 期间 `top_tsu_task_done_i=1`，TSU 清 active、置 done。

`flush_i` 最高优先级清 active/done/error。FIFO 自己也收到 flush，因此队列内容会清掉。

## 5. `hdv_instruction_prefetch_unit.sv`：IPU

IPU 是取指前端。它从 task entry 开始取 128-bit fetch packet，写入两个 64B ping-pong buffer，并尽早把有效 packet 送给 VLIWPU。

### 5.1 参数与派生常量

- `FetchPacketWidth=128`，所以一个 packet 16B。
- `BufferBytes=64`，所以一个 buffer 有 4 个 packet。
- `PacketIdxWidth` 是 buffer 内 packet index 位宽。
- `LastPacketIdx=PacketsPerBuffer-1`。

### 5.2 三个状态

`IDLE`: 等待 TSU 给 task。

`FILL`: task 或 redirect 后等待第一个 packet 返回。当前设计不再等满 64B，而是第一个 packet 到就可进入 SERVE。

`SERVE`: 输出 active buffer 中已经 valid 的 packet，同时继续填充 active buffer 或 background buffer。

### 5.3 双 buffer 角色

IPU 有 `buffer_a_q` 和 `buffer_b_q` 两个 64B buffer。两个选择位定义角色：

- `active_buf_q`: VLIWPU 当前读取哪个 buffer。
- `fill_buf_q`: memory response 当前写入哪个 buffer。

初始 early-serve 阶段 `active_buf_q == fill_buf_q`。这表示同一个 buffer 一边被填，一边把已经 valid 的 packet 送出去。等 active buffer 填满后，`fill_buf_q` 切到另一个 buffer，开始真正背景预取。

### 5.4 valid bit

`buffer_a_valid_q` 和 `buffer_b_valid_q` 逐 packet 记录是否已经收到 memory response。输出 packet 时必须检查 `active_packet_valid`，所以 VLIWPU 不会读到还没填好的 entry。

### 5.5 memory request/response

IPU 的 request 侧和 response 侧使用两个独立指针：

- `fill_req_idx_q`: 下一条要发出的 fetch request 在当前 fill buffer 内的 packet index。
- `fill_rsp_idx_q`: 下一条按序返回的 response 应写入当前 fill buffer 的 packet index。
- `fill_req_done_q`: 当前 fill buffer 的所有 request 已经发完。

这样 IPU 可以连续发出多个 in-order fetch request，不必等上一条 response 回来才发下一条。

发请求条件：

```systemverilog
(state == FILL) ||
(state == SERVE && !bg_fill_done_q && !loop_blocks_bg_fetch)
```

同时要求 `!fill_req_done_q`。是否还能继续接收 request 由下游 `mem_ipu_req_ready_i` 控制；在当前 `hdv_top` 中，这个 ready 来自取指 AXI bridge 的 outstanding counter。

`loop_blocks_bg_fetch = loop_lock_i & (fill_buf_q != active_buf_q)`。含义是：如果正在 loop lock 且背景 buffer 与 active buffer 不同，就不要继续取无用背景指令，避免浪费带宽；但已经发出的请求仍然允许 response 回来。

### 5.6 地址生成

`ipu_mem_req_addr_o = fetch_base_q + fill_req_idx_q * PacketBytes`。

`fetch_base_q` 指向当前 fill buffer 的起始地址。request 侧用 `fill_req_idx_q` 生成地址；response 侧用 `fill_rsp_idx_q` 写回 buffer valid bit 和 packet 数据。这个拆分是支持多 outstanding fetch 的关键。

### 5.7 输出 packet

`ipu_vliwpu_packet_valid_o = state_q == SERVE && active_packet_valid && !bg_stall`。

`bg_stall` 只在 active buffer 最后一个 packet 处生效：如果下一个 background buffer 尚未填完且不在 loop lock，则不能切 buffer，所以暂停输出。普通中间 packet 只依赖自身 valid bit。

`take_packet = ipu_vliwpu_packet_valid_o & vliwpu_ipu_packet_ready_i`。只有 take 之后 `exec_idx_q` 才前进。

### 5.8 redirect

redirect 优先级高于普通状态机逻辑，低于 task complete，最终又会被 flush 覆盖。

IPU 要求 redirect PC 16B 对齐，也就是 fetch packet/EP entry 对齐。`p_redirect_alignment_check` 在仿真中用 `$fatal` 检查未对齐 redirect。

如果 redirect 目标落在当前 active buffer 且目标 packet 已 valid，IPU 不重新取指，只把 `exec_idx_d` 改到目标 packet。这是 loop 跳转的快速路径。

如果 redirect 对齐但不在 active buffer，IPU 清 valid bit，回到 FILL，从 redirect PC 重新取第一包。

如果 redirect 不对齐，状态不变，仿真 fatal 会暴露问题。

### 5.9 loop lock

当 `loop_lock_i=1` 且输出到 active buffer 最后一个 packet 时，IPU 不切到 background buffer，而是 `exec_idx_d=0`，从 active buffer 开头重放。这个机制依赖循环体已经完整处在 active buffer 内。

如果 loop lock 时背景 buffer 已经填好，它也不会被消费；等 loop lock 解除后，正常切换。

### 5.10 flush 和 task complete

`top_ipu_task_complete_i` 让 IPU 回到 IDLE 并清 valid bit。`flush_i` 也回 IDLE，且优先级最高。

在 `hdv_top` 中，IPU 的 `flush_i` 是 `task_flush`，不直接包含 redirect。这样 redirect 分支可以走 IPU 自己的 redirect path，而不是被 flush path 覆盖。

## 6. `hdv_vliw_pack_unit.sv`：VLIWPU

VLIWPU 把 128-bit fetch packet 切成一个或多个 execute packet。它是 HDV 中最接近 VLIW packing 机制的模块。

### 6.1 packet hold

VLIWPU 内部只有一个 `packet_hold_valid_q`。当没有持有 packet 时，`vliwpu_ipu_packet_ready_o=1`，可以从 IPU 接收一个 fetch packet。若当前 packet 的最后一个 EP 同周期被 HEU 接收，VLIWPU 也会拉高 ready 接收下一 packet，避免 packet 边界多出一拍空泡。

一旦接收 packet，VLIWPU 持有它，直到这个 packet 内所有 slot 都被发成 EP。

### 6.2 header 和 p-bit

`header = packet_q[127:96]`。当前约定 header 是 `addi x0, x0, imm` 形式的 RISC-V HINT。VLIWPU 不完整解码这条指令，只取 immediate 低位中的 p-bit：

```systemverilog
p_bits = header[20 +: NumSlots-1]
```

`p_bits[i]` 表示 slot i 后面是否请求继续与下一条指令打包。p-bit 是“请求并行”的 hint，不是强制并行；系统/分支、依赖断点、32-bit 边界和最大 issue 数都可以终止打包。

### 6.3 slot 提取

`slots[i] = packet_q[i*16 +: 16]`。slot0 是 packet 低 16 bit。header 在高 32 bit。

`raw_slot_is_32b[i] = slots[i][1:0] == 2'b11`。RISC-V 32-bit 指令低两位为 `11`，所以一个 32-bit 指令从 slot i 开始，占 slot i 和 slot i+1。

### 6.4 continuation 标记

`p_slot_marks` 用 `skip_next` 扫描六个 slot。

如果 slot i 是 32-bit 指令起点且不是最后一个 slot，则：

- `slot_is_32b[i]=1`
- 下一轮把 slot i+1 标成 `slot_is_continuation=1`

continuation slot 不会作为新指令起点发给 HEU，但会被强制放进同一个 issue mask 中，保证 32-bit 指令完整。

### 6.5 指令分类

VLIWPU 在 `p_classify` 中按 opcode 粗分类。

Vector 类：

- opcode `0x57`，RVV arithmetic，包括 `vsetvli/vsetivli/vsetvl` 这类 OP-V 指令。
- opcode `0x07` LOAD-FP，但排除 scalar FLW/FLD 的 funct3。
- opcode `0x27` STORE-FP，但排除 scalar FSW/FSD 的 funct3。

System 类：

- opcode `0x73`
- 或部分 compressed system 形态。

Branch 类：

- opcode `0x63` branch
- opcode `0x6f` JAL
- opcode `0x67` JALR

其它默认 scalar。continuation slot 的 class 继承前一个起始 slot。

### 6.6 issue mask 生成

`p_issue_mask` 从 `head_slot_q` 开始扫描 slot，生成当前 EP 的 `issue_mask`。

它跳过 continuation slot，因为 continuation 已经由它的 32-bit 起始指令强制带入。

每遇到一个起始 slot：

1. 标记 `issue_mask[i]=1`。
2. `issue_count++`。
3. 如果是 32-bit 指令，还标记 `issue_mask[i+1]=1` 并再计数。
4. 根据终止条件决定是否停止本 EP。

终止条件包括：

- 到 packet 最后一个 slot。
- 达到 `MaxIssueSlots`。
- 对应 p-bit 为 0。
- `ctrl_vliwpu_dep_break_i` 对应 bit 为 1。
- 当前指令是 SYSTEM。
- 当前指令是 BRANCH。

因此 p-bit=1 只允许继续；真正是否能继续还要看这些硬边界。

### 6.7 execute valid/ready

`vliwpu_heu_execute_valid_o = packet_hold_valid_q`。只要 VLIWPU 持有 packet，就持续向 HEU 提供当前 EP。

`execute_accept = valid & heu_ready`。HEU 接收后，VLIWPU 更新 `head_slot_q`。

### 6.8 head slot 更新

如果本 EP 包含 packet 最后一个 slot，说明整个 fetch packet 消费完，VLIWPU 清 `packet_hold_valid_q` 并让 IPU 送下一包。

否则，VLIWPU 扫描 `issue_mask` 中最后一个置 1 的 slot，把 `head_slot_q` 设置为它的下一个 slot。下一周期从那里继续打包同一个 fetch packet 的剩余指令。

### 6.9 flush

`flush_i` 清 `packet_hold_valid_q` 和 `head_slot_q`。在 `hdv_top` 中，VLIWPU 的 flush 包含 task error/complete 和 redirect，因此 redirect 后不会继续使用旧 packet。

## 7. `hdv_hybrid_execution_unit.sv`：HEU

HEU 是 EP 分发器。它接收 VLIWPU 的 EP，把 EP 内 scalar 和 vector 指令切片分别送到后端。

### 7.1 输入 EP

HEU 输入包括：

- `vliwpu_heu_execute_valid_i`
- `vliwpu_heu_execute_slot_valid_i`
- `vliwpu_heu_execute_slot_i`
- `vliwpu_heu_execute_slot_is_32b_i`
- `vliwpu_heu_execute_class_i`
- `vliwpu_heu_execute_pc_i`

HEU 不重新决定 EP 边界，只消费 VLIWPU 已经生成的 issue mask 和 class。

### 7.2 `p_split`

`p_split` 扫描每个 slot，跳过 32-bit 指令的 continuation slot。

对于一个真实指令起点：

- 计算该指令 PC：`packet_pc + i * 2`。
- 如果是 32-bit 指令，把 `{slot[i+1], slot[i]}` 拼成 32-bit 指令。
- 如果是 16-bit 指令，把高 16 bit 补 0。
- 如果 class 是 VECTOR，置 `has_vector=1` 和 `vector_insn_valid_in[i]=1`。
- 否则置 `has_scalar=1` 和 `scalar_insn_valid_in[i]=1`。

这意味着 SYSTEM 和 BRANCH 当前都进入 scalar 后端。

### 7.3 dispatch 寄存器

HEU 把 EP 内容寄存在：

- `dispatch_insn_q`
- `dispatch_insn_is_32b_q`
- `dispatch_insn_pc_q`
- `dispatch_pc_q`
- `scalar_insn_valid_q`
- `vector_insn_valid_q`

这样 `heu_scalar_valid_o` 和 `heu_vector_valid_o` 是寄存器输出，不依赖后端 ready 的组合反馈。

### 7.4 ready 规则

`heu_vliwpu_execute_ready_o = !outstanding_q`。

HEU 当前一次只允许一个 EP outstanding。只要还没收到 scalar/vector 后端 accepted，就不接收下一个 EP。

### 7.5 后端 valid 清除

如果 `scalar_dispatch_valid_q && scalar_heu_ready_i`，标量 dispatch valid 清零。向量同理。

这里的 ready 只表示后端接收了这份 dispatch 数据，不表示 EP 被完整 accepted。完整 accepted 还要等 `scalar_heu_accepted_i` 或 `vector_heu_accepted_i`。

### 7.6 accept packet

`accept_packet = vliwpu_heu_execute_valid_i & heu_vliwpu_execute_ready_o`。

同周期 HEU：

- 置 `outstanding_d=1`。
- 清旧 error。
- 根据 `has_scalar/has_vector` 置 dispatch valid。
- 保存 dispatch 指令、PC 和 valid mask。

### 7.7 pending 和 EP accepted

如果 EP 含 scalar，`scalar_pending_d=1`。如果 EP 含 vector，`vector_pending_d=1`。

后端报告“已接收本 EP 切片”时拉：

- `scalar_heu_accepted_i`
- `vector_heu_accepted_i`

HEU 清对应 pending。

当：

- `scalar_pending_d=0`
- `vector_pending_d=0`
- `scalar_dispatch_valid_d=0`
- `vector_dispatch_valid_d=0`

时，HEU 认为 EP 已经被相关后端接收，清 `outstanding_d` 并产生一拍 `heu_top_ep_accepted_o`。

### 7.8 error

`backend_heu_error_i` 在 EP outstanding 或接收 packet 同周期有效时锁存到 `error_q`。如果 error 存在，HEU 不产生 accepted 脉冲，而是通过 `heu_top_ep_error_o` 暴露给上层。

### 7.9 flush

flush 清 outstanding、pending、dispatch valid、ep_accepted 和 error。redirect 会通过 `dispatch_flush` 清 HEU。

## 8. `hdv_vec_dispatch_unit.sv`：HEU 到 Ara

这个模块把 HEU 的多 slot vector EP 转换成 Ara CV-X-IF 风格的单条 accelerator request。

### 8.1 当前语义

`vec_heu_accepted_o` 表示 EP 内所有 vector 指令已被 Ara 接收。它不等待 Ara 真正执行完，也不等待 load/store 返回数据或写回完成。

这样做的目的是让 HDV 前端尽可能不断供给 Ara，避免因为把 `resp_valid/load_complete/store_complete` 当作 EP done 而过度保守。

### 8.2 vtrace 标量环境

Ara vector 指令仍需要 `rs1/rs2` 等标量操作数。当前 mock 环境用 vtrace 文件提供：

```text
{insn[31:0], rs1[63:0], rs2[63:0]}
```

`VTraceDepth` 默认为 `N_VINSN`，`VTraceFile` 默认为 `apps/ideal_dispatcher/vtrace/vsaxpy.vtrace`。模块 initial block 用 `$readmemh` 读入。

### 8.3 状态和内部 buffer

`insn_valid_q` 和 `insn_q` 是当前 EP 的内部缓冲。

状态：

- `IDLE`: 等 HEU vector dispatch。
- `DISPATCH`: 找最低有效 slot，驱动 Ara request。
- `DONE`: 当前 EP 内所有 vector 指令都被 Ara accepted，向 HEU 拉一拍 accepted。
- `WAIT`: 当前保留但实际只直接转 DONE。

### 8.4 slot priority encoder

`slot_found/slot_idx` 每周期从低到高找第一个 `insn_valid_q[i]=1` 的 slot。另有一组 input priority encoder 用于 `IDLE && heu_vec_valid_i` 的首条指令旁路。这样 vector EP 内指令按 slot 顺序发给 Ara，同时新 EP 到达时如果 Ara ready，可以同周期发出第一条 request。

### 8.5 request 生成

当内部缓冲有有效 slot，或 `IDLE` 同周期收到新的 vector EP 且其中有有效 slot 时，模块驱动：

- `acc_req.req_valid=1`
- `acc_req.insn = selected_insn`
- `acc_req.frm = RNE`
- `acc_req.rs1/rs2 = vtrace 当前项`

如果 vtrace 耗尽或当前 vtrace 指令与 EP 指令不匹配，则 `req_valid=0` 并报错，避免把错误标量值发给 Ara。`selected_insn` 可能来自内部缓冲，也可能来自新 EP 输入旁路。

### 8.6 accept 指令

`accept_insn = acc_resp.req_ready & acc_req.req_valid`。

Ara 接收一条指令后：

- 清 `insn_valid_d[slot_idx]`。
- vtrace index 加 1。
- 如果还有有效 slot，继续留在 DISPATCH。
- 如果没有有效 slot，进入 DONE。

如果这条指令来自 `IDLE` 同周期输入旁路，则清的是 `input_slot_idx` 对应的 valid bit，再把剩余 slot 写入内部缓冲。因此只要 Ara `req_ready` 连续为 1，新 EP 的第一条 vector 指令不需要等到下一拍，EP 内后续指令也可以连续每周期发送。

### 8.7 response 和 error

`resp_ready` 永远为 1，模块总是愿意接收 Ara response。当前只把 `resp_valid && exception.valid` 作为错误上报，不用 response 表示 EP complete。

### 8.8 flush

flush 清 state、当前 EP buffer 和 vtrace index。注意现在 flush 会把 vtrace 从 0 开始，这适合当前整任务重启式仿真；如果未来支持复杂 redirect 后继续 vtrace，需要 vtrace PC/index 映射。

## 9. `hdv_mock_host_core.sv`

mock host 模拟主核和临时标量后端。它做四件事：写 CSR 启动 task、接收 scalar dispatch、模拟分支 redirect、按 EP accepted 计数决定 task complete。

### 9.1 参数

- `AutoStart`: 是否复位后自动启动。
- `AutoStartDelay`: 等多少周期后启动。
- `AutoTaskEntry`: 写入 VTASK_ADDR 的 entry。
- `AutoTaskDesc`: 写入 VTASK_PADDR 的 descriptor。
- `AutoExpectedEpAccepts`: 期望收到多少个 EP accepted。
- `EnableMockBranch`: 是否模拟 bnez redirect。
- `MockLoopIterations`: mock 循环次数。
- `TaskWatchdogCycles`: 整 task 超时。
- `PacketWatchdogCycles`: EP accepted 长时间不来时超时。

### 9.2 CSR 状态机

状态顺序：

```text
IDLE
WRITE_TASK_ADDR
WRITE_TASK_DESC
CLEAR_STATUS
WRITE_START
RUN
COMPLETE_TASK
WAIT_TASK_STATUS
READ_STATUS
FINISH or FAIL
```

每个 CSR 状态都通过 `p_csr_drive` 组合输出地址、写使能和数据。`csr_fire = valid & ready` 后进入下一状态。

### 9.3 AutoStart

`auto_start_armed_q` 复位后等于 `AutoStart`。如果打开 AutoStart，`auto_start_count_q` 计到 `AutoStartDelay` 后产生 `auto_start_pulse`，进入写 CSR 流程。

### 9.4 scalar backend mock

`mock_hdv_scalar_ready_o = RUN && !scalar_pending_q`。

收到 scalar dispatch 后：

- `scalar_pending_d=1`
- `scalar_count_d=ScalarLatency-1`

倒计数到 0 后：

- `mock_hdv_scalar_accepted_o=1`
- 下一拍 pending 清零

这里 accepted 代表 mock 标量后端接收/处理完这个 EP 标量切片。它不是完整真实标量流水线。

### 9.5 vector backend mock

当前顶层向量已经内部接 Ara，所以 `ara_tb` 把 mock vector 输入绑 0。mock host 里仍保留 vector ready/accepted 逻辑，用于旧连接或未来测试。

### 9.6 mock branch

`is_mock_bnez` 识别 opcode branch、funct3=BNE、rs2=x0 的 `bnez` 形式。

`branch_target` 按 B-type immediate 从指令中拼出 signed offset，再加当前 PC。

如果 `EnableMockBranch && scalar_fire`，mock host 扫描 scalar EP 中的指令。遇到 bnez：

- 如果 `loop_iters_remaining_q > 1`，认为 taken。
- 计算 redirect PC。
- 递减 loop counter。
- 设置 `branch_redirect_wait_d=branch_taken`。

redirect 不在 scalar_fire 同周期发出，而是等 `mock_hdv_scalar_accepted_o` 后再发。这样可以避免同周期 redirect flush 把 branch EP 自己的 accepted 事件冲掉。

### 9.7 loop lock 输出

`mock_hdv_loop_lock_o = EnableMockBranch && RUN && loop_iters_remaining_q > 1`。

这只是临时策略：循环未结束时一直拉 loop lock，让 IPU 尽量重放 active buffer，减少不必要取指。未来真实标量流水线应根据后向分支和 loop body 范围更精确地产生。

### 9.8 EP accepted 计数

`hdv_mock_ep_accepted_i` 每来一拍：

- `accepted_packets_q++`
- 清 packet watchdog

如果加一后达到 `expected_ep_accepts_q`，进入 `COMPLETE_TASK`。

### 9.9 task complete

`COMPLETE_TASK` 拉 `mock_hdv_task_complete_o=1` 一拍。TSU 收到后置 task done。mock host 随后 `WAIT_TASK_STATUS` 等 HDV status 更新，再 `READ_STATUS` 确认没有 error，最后 FINISH。

### 9.10 watchdog

`task_watchdog_q` 在整个 task active 期间计数。超时直接 FAIL。

`packet_watchdog_q` 只在 RUN 状态计数。如果很久没有 EP accepted，说明前端或后端卡住，也 FAIL。

## 10. `hdv_top.sv`

`hdv_top` 把所有 HDV frontend 模块、Ara、AXI mux 和外部 mock/scalar 接口接起来。

### 10.1 对外接口分组

host CSR：

- `host_hdv_csr_*` 输入给 TIU。
- `hdv_host_csr_*` 从 TIU 返回。

控制：

- `ctrl_hdv_redirect_valid_i/pc_i` 给 IPU，并作为 dispatch flush 清 VLIWPU/HEU/vector dispatch。
- `ctrl_hdv_loop_lock_i` 给 IPU。
- `ctrl_hdv_dep_break_i` 给 VLIWPU。

task 状态：

- `host_hdv_task_complete_i/error_i` 从 mock host 或未来 task controller 来。
- `hdv_host_task_busy_o/done_o/error_o` 给外部观察。

scalar dispatch：

- `hdv_scalar_valid_o`
- `scalar_hdv_ready_i`
- `hdv_scalar_insn_*`
- `scalar_hdv_accepted_i`

vector dispatch 不再作为 top 外部端口，它在 top 内部进入 `hdv_vec_dispatch_unit` 和 Ara。

EP 状态：

- `hdv_host_ep_busy_o`
- `hdv_host_ep_accepted_o`
- `hdv_host_ep_error_o`

### 10.2 task busy

`task_busy = tsu_top_busy | ipu_top_busy | heu_top_busy`。

它表示 HDV frontend 中还有任务排队、正在取指，或 HEU 还有 EP outstanding。

### 10.3 flush 分层

`task_flush = flush_i | host_hdv_task_error_i`。

`dispatch_flush = task_flush | ctrl_hdv_redirect_valid_i`。

IPU 使用 `task_flush`，这样 redirect 不会被当成普通 flush，而是走 IPU 的 redirect path。

VLIWPU、HEU、vector dispatch 使用 `dispatch_flush`，因为 redirect 后旧 packet/旧 EP 必须丢弃。

### 10.4 instruction fetch AXI bridge

IPU 看到的是简化 ready/valid：

```text
ipu_mem_req_valid/ready/addr
mem_ipu_rsp_valid/ready/data
```

`hdv_top` 把它转换成单 beat AXI read：

- ar_valid = IPU req valid 且 outstanding counter 未满。
- ar.addr = `ipu_mem_req_addr`。
- ar.len = 0，单 beat。
- ar.size = log2(16B)，对应 128-bit fetch packet。
- r_ready = outstanding counter 非零且 IPU ready 接收 response。

`imem_outstanding_q` 统计已经发出但尚未收到最后一个 R beat 的取指 read。AR handshake 递增，R handshake 且 `last` 递减，二者同周期则保持不变。AXI R 通道在 outstanding 非零时持续 ready；如果 IPU 因 flush/task complete 已不再接收 response，bridge 会 drain 并丢弃旧 response，避免 AXI fabric 被旧预取卡住。当前默认深度等于一个 IPU buffer 内的 packet 数，即 64B buffer / 16B packet = 4。

### 10.5 Ara invalidation packing

Ara 原本通过 CV-X-IF response 带 cache invalidation 信息。这里 `axi_inval_filter` 仍实例化，`pack_ara_invalidation` 把 filter 产生的 inval 信号注入 `ara_acc_resp_pack`。

当前 `acc_cons_en` 来自 `acc_req.acc_req.acc_cons_en`，通常为 0，所以 invalidation filter 结构连着但基本禁用。这样未来接回 CVA6 cache coherence 路径时不需要大改结构。

### 10.6 vector dispatch 和 Ara

HEU vector 输出连到 `i_vec_dispatch_unit`。该模块再驱动 Ara `acc_req_i`。Ara 的 `acc_resp_o` 经 invalidation packing 后回到 vector dispatch。

向量 accepted 路径是：

```text
Ara req_ready
  -> hdv_vec_dispatch_unit 清 slot
  -> vec_heu_accepted_o
  -> HEU vector_heu_accepted_i
  -> HEU ep_accepted
```

### 10.7 AXI mux

`axi_mux` 有 3 个 slave port：

1. Ara AXI。
2. scalar AXI，当前绑 0，未来接真实 scalar backend。
3. HDV instruction fetch AXI。

保留 scalar slot 是为了不改变 system AXI ID 宽度和拓扑。

### 10.8 模块实例化顺序

实例化顺序基本对应数据流：

1. vector dispatch/Ara/memory mux 先放在 top 中间，因为类型和接口复杂。
2. TIU 接 host CSR。
3. TSU 接 TIU task。
4. IPU 接 TSU task。
5. VLIWPU 接 IPU packet。
6. HEU 接 VLIWPU EP，并分到 scalar/vector。

## 11. `ara_soc.sv` 和 testbench 中的 HDV 集成

### 11.1 `ara_soc.sv`

`ara_soc` 暴露 HDV host/task/scalar/EP 端口给 testbench。同时它还保留软件 `ctrl_registers` 产生的 HDV CSR。

CSR 选择逻辑是：

```text
if host CSR valid:
  use host CSR
else:
  use ctrl_registers CSR
```

也就是说 TB/mock host 直连优先级更高。

注意当前 `ara_soc` 实例化 `hdv_top` 时，HDV instruction fetch 的外部简化 imem 端口未连接，因为 top 内部已经把 IPU fetch 接入 system AXI mux。真正取指走统一 AXI。

### 11.2 `ara_testharness.sv`

testharness 只是把 `ara_soc` 的 HDV 端口继续暴露给 `ara_tb`，没有额外 HDV 逻辑。

### 11.3 `ara_tb.sv`

`ara_tb` 实例化 `hdv_mock_host_core`，把 mock host CSR 端口接到 testharness。scalar dispatch 也接到 mock host。vector dispatch 已经由 `hdv_top` 内部接 Ara，所以 TB 中 `hdv_vector_*` 不再存在。

TB 打印：

```text
[HDV] ... ep_backend_accept accepted_so_far=N
```

这里的 N 来自 `accepted_packets_q + 1`，表示 mock host 已观察到第 N 个 EP accepted。

## 12. 一次 `vsaxpy_hdv` 任务的典型执行

1. mock host 等 AutoStartDelay。
2. mock host 写 VTASK_ADDR、VTASK_PADDR。
3. mock host 写 STATUS 清旧 done/error。
4. mock host 写 START。
5. TIU 置 task_valid。
6. TSU FIFO push，然后在 IPU ready 时 pop。
7. IPU 从 task entry 发第一个 16B read。
8. 第一个 fetch packet 返回后，IPU 进入 SERVE，开始给 VLIWPU。
9. VLIWPU 读取 hint p-bit，把 packet 内 slot 切成一个或多个 EP。
10. HEU 接收 EP，分 scalar/vector。
11. scalar 侧由 mock host accepted；branch EP 可能产生 redirect 和 loop lock。
12. vector 侧由 `hdv_vec_dispatch_unit` 逐条发给 Ara，Ara `req_ready` 后 accepted。
13. HEU 等 scalar/vector 都 accepted，产生 `ep_accepted`。
14. mock host 计数 EP accepted；达到期望数后拉 task complete。
15. TSU/TIU 置 task done，mock host 读 STATUS，仿真 PASS。

## 13. 调试时建议看的信号

### 13.1 task 层

- `i_hdv_mock_host_core.state_q`
- `i_hdv_mock_host_core.accepted_packets_q`
- `i_task_interface_unit.task_valid_q`
- `i_task_schedule_unit.active_q`
- `hdv_host_task_busy_o/done_o/error_o`

### 13.2 IPU 层

- `i_instruction_prefetch_unit.state_q`
- `fetch_base_q/exec_base_q`
- `fill_req_idx_q/fill_rsp_idx_q/exec_idx_q`
- `active_buf_q/fill_buf_q`
- `buffer_a_valid_q/buffer_b_valid_q`
- `ipu_mem_req_valid_o`
- `mem_ipu_req_ready_i`
- `mem_ipu_rsp_valid_i`
- `ipu_vliwpu_packet_valid_o`
- `redirect_valid_i`
- `loop_lock_i`

### 13.3 VLIWPU 层

- `packet_hold_valid_q`
- `header`
- `p_bits`
- `head_slot_q`
- `slot_is_32b`
- `slot_is_continuation`
- `issue_mask`
- `slot_class`
- `vliwpu_heu_execute_valid_o`
- `heu_vliwpu_execute_ready_i`

### 13.4 HEU 层

- `accept_packet`
- `has_scalar/has_vector`
- `scalar_dispatch_valid_q/vector_dispatch_valid_q`
- `scalar_pending_q/vector_pending_q`
- `scalar_heu_accepted_i/vector_heu_accepted_i`
- `ep_accepted_q`
- `heu_top_ep_error_o`

### 13.5 vector dispatch/Ara 层

- `i_vec_dispatch_unit.state_q`
- `insn_valid_q`
- `slot_idx`
- `acc_req_o.acc_req.req_valid`
- `acc_resp_i.acc_resp.req_ready`
- `acc_req_o.acc_req.insn`
- `vtrace_idx_q`
- `vec_heu_accepted_o`
- Ara dispatcher/sequencer/VLSU 信号，例如 `req_ready`、`resp_valid`、`load_complete/store_complete`，用于看真实执行是否卡住。

## 14. 当前机制边界

当前 HDV 原型已经能表达结构流程：

- host/task CSR
- task queue
- IPU early serve、双 buffer、redirect、loop lock
- hint p-bit based VLIW packing
- HEU scalar/vector split
- vector dispatch 到 Ara
- mock scalar branch redirect
- EP accepted 计数和 task done

仍然是临时或待完善的部分：

- scalar 后端仍是 mock，不是真实寄存器读写/ALU/branch/LSU。
- `hdv_vec_dispatch_unit` 通过 vtrace 提供 rs1/rs2，未来真实标量后端需要替换这部分。
- `ep_accepted` 不等于真实执行退休。如果要验证数据正确性，仍需观察 Ara 内部完成信号和内存结果。
- VLIWPU 的依赖断点 `ctrl_vliwpu_dep_break_i` 现在由外部提供，尚未自动分析 RAW/WAW/WAR。
- redirect 目标被要求 16B fetch packet/EP entry 对齐，不支持跳进 EP 中间。
- loop lock 由 mock host 简单驱动，未来要由真实分支/loop detector 精确控制。

## 15. 阅读代码的推荐顺序

1. 先读 `hdv_pkg.sv`，记住 CSR 和 class。
2. 再读 `hdv_top.sv` 的 wire 和实例化，建立全局连接图。
3. 读 TIU/TSU，理解 task 生命周期。
4. 读 IPU，重点看 `state_q`、valid bit、redirect 和 loop lock。
5. 读 VLIWPU，重点看 p-bit、32-bit continuation、issue mask。
6. 读 HEU，重点看 dispatch valid、pending、ep_accepted。
7. 读 vector dispatch，重点看 Ara request 和 vtrace。
8. 最后读 mock host 和 TB，理解当前仿真为什么能跑起来，以及哪些地方只是临时模型。
