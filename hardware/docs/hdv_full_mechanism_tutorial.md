# HDV Mechanism Tutorial

本文档面向阅读和调试当前 `hardware/src/hdv` RTL。目标不是逐字翻译代码，而是把每个模块的关键逻辑块、状态机、寄存器、握手和边界条件解释清楚，使你能够沿着一条 HDV task 从主核提交到 Ara 接收向量指令的全过程定位问题。

当前代码中的 HDV 原型可以理解为：

```text
host / mock task driver
  -> TIU task CSR
  -> TSU task queue
  -> IPU instruction fetch
  -> VLIWPU fetch-packet to execute-packet packing
  -> HEU scalar/vector split
  -> hdv_scalar_backend or mock scalar path
  -> vector dispatch adapter
  -> Ara vector backend
```

几个语义先统一：

- `task done` 表示整个 HDV task 结束，由 task controller 或 mock host 告诉 TSU/TIU。
- `scalar_ep_done` 表示 scalar slice 已在标量后端执行并写回完成。
- `vec_ep_acknowledged_o` 表示 vector slice 已经达到前端可推进的安全点：本 EP 的向量 request 已捕获标量操作数，且 `vset rd!=x0` 的 granted VL 已写回。它不表示普通向量指令已经执行完成。
- `heu_top_ep_acknowledged_o` 表示一个 execute packet 的 scalar/vector slice 都已达到上述安全点，HDV 前端可以推进下一 EP；它不表示 Ara 内部向量退休。
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
[31:0]    32-bit HDV_HINT header
[127:32]  six 16-bit instruction slots
```

如果某个 slot 是 32-bit RISC-V 指令，它占用连续两个 16-bit slot。VLIWPU 用低 2 bit `11` 判断 32-bit 指令起始 halfword，并把下一 slot 标成 continuation。

当前 HDV header 使用显式 RISC-V hint 指令 `lui x0, imm20`。`imm20` 中低位字段给 VLIWPU 使用：

```text
imm20[12:0]  pbits
imm20[13]    packet256
imm20[14]    cross
imm20[15]    loop_start
imm20[16]    loop_end
imm20[18:17] prefetch_mode (00=off, 01=1X, 10=2X, 11=4X)
```

普通 128-bit packet 中 header 后面通常放 3 条 32-bit 业务指令。`packet256=1` 时，VLIWPU 会等下一个 128-bit beat 到来，把两个 beat 组成一个 256-bit logical packet 后再打包；总线宽度仍是 128 bit。

### 1.3 execute packet 语义

execute packet 是 VLIWPU 给 HEU 的一次发射包。包内有：

- `slot_valid`: 哪些 slot 属于本 EP。
- `slot`: 原始 16-bit halfword。
- `slot_is_32b`: 哪些 slot 是 32-bit 指令起点。
- `class`: 每个 slot 的 SCALAR/VECTOR/SYSTEM/BRANCH 分类。
- `pc`: EP 基地址；跨 fetch packet 打包时，VLIWPU 还会给每个 slot 单独携带真实 PC，HEU 使用 per-slot PC。

HEU 当前保留一个 current EP 和一个 skid buffer EP。只有 skid buffer 满了才反压 VLIWPU；current EP 的 scalar/vector 切片都完成 `done/acknowledged` 后，HEU 再推进 buffered EP。当前 `hdv_top` 实例化时打开 `EnableBufferedVectorEarlyIssue=1'b1`，因此在安全条件满足时，skid buffer 中下一 EP 的 vector slice 可以提前进入 vector dispatch。提前发射只覆盖 vector slice，不提前发 scalar slice，也不跨越未处理的控制流。

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
- `HDV_INST_BRANCH`: branch/jal/jalr，当前走 scalar 侧；真实标量模式下由 `hdv_scalar_backend` 产生 redirect，关闭真实标量后端时由 mock 分支逻辑产生 redirect。

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

IPU 是取指前端。它从 task entry 开始取 128-bit fetch packet，写入两个 ping-pong buffer，并尽早把有效 packet 送给 VLIWPU。`hdv_instruction_prefetch_unit.sv` 的独立默认值仍是 `BufferBytes=64`，但当前 `hdv_top` 实例化覆盖为 `BufferBytes=512`，即每个 buffer 32 个 128-bit packet；两个 buffer 可保护最多 1024B 的 locked loop body。

### 5.1 参数与派生常量

- `FetchPacketWidth=128`，所以一个 packet 16B。
- `BufferBytes` 由实例决定；当前顶层为 512B，所以一个 buffer 有 32 个 packet。
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

发请求条件简化看是：

```systemverilog
(state == FILL) ||
(state == SERVE && !bg_fill_done_q && (!loop_blocks_bg_fetch || bg_stall))
```

同时要求 `!fill_req_done_q`、没有 task complete/redirect/flush。是否还能继续接收 request 由下游 `mem_ipu_req_ready_i` 控制；在当前 `hdv_top` 中，这个 ready 来自取指 AXI bridge 的 outstanding counter，顶层参数 `ImemOutstandingDepth=4` 限制最多 4 个取指 AXI AR 在途。

`loop_blocks_bg_fetch` 现在由显式 `loop_lock_i`、自动 lock/build/locked 状态和 protected buffer 共同决定。含义是：如果 loop body 已经被保护，就不要继续取无用背景指令，避免读到 kernel 后面的数据区并和 Ara load/store 抢带宽；但 `bg_stall` 认为这是继续执行 loop 所需的 demand fill 时会放行。

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

IPU 支持显式 loop lock 和自动 loop lock，两者共享 protected-buffer 机制。

第一种是外部显式 `loop_lock_i`。当 `loop_lock_i=1` 且输出到 active buffer 最后一个 packet 时，IPU 保留原来的强制 replay 语义：不切到 background buffer，而是 `exec_idx_d=0`，从 active buffer 开头重放。这个模式要求外部控制器已经知道循环还会 taken。

第二种是硬件自动 lock。`hdv_top` 不再在 dispatch 阶段重解码分支，而是使用 `hdv_scalar_backend` 的精确 `branch_resolved_valid/taken/backward/target` 事件。taken backward redirect 命中 active buffer 或 protected fill buffer 时，IPU 原地/跨 buffer replay；not-taken backward branch 通过 `loop_exit_i` 释放 lock。

`loop_start` / `loop_end` header 会让 IPU 进入 `loop_build_q` / `loop_locked_q`，并设置 `loop_protect_q`，保护 active/fill buffer 中的 loop body。收到带 `loop_end` 的 fetch response 后，IPU 还会停止继续填充该 buffer，避免 512B 大 buffer 在 loop body 之后继续投机取指并抢占数据访存带宽。

这样最后一次 not-taken 不会因为 IPU 盲目 replay 而死循环。若 exit 时 fall-through 仍在当前 buffer 内，IPU 会重新打开被 `loop_end` cap 住的 fill；若需要切到 background buffer，则恢复背景取指，等 background buffer 填完后再切换到顺序后继。

### 5.10 flush 和 task complete

`top_ipu_task_complete_i` 让 IPU 回到 IDLE 并清 valid bit。`flush_i` 也回 IDLE，且优先级最高。

在 `hdv_top` 中，IPU 的 `flush_i` 是 `task_flush`，不直接包含 redirect。这样 redirect 分支可以走 IPU 自己的 redirect path，而不是被 flush path 覆盖。

## 6. `hdv_vliw_pack_unit.sv`：VLIWPU

VLIWPU 把 128-bit fetch packet 切成一个或多个 execute packet。它是 HDV 中最接近 VLIW packing 机制的模块。

### 6.1 packet hold

VLIWPU 内部有当前 packet 寄存器和一个很小的跨包 tail carry 缓冲。当没有持有 packet 时，`vliwpu_ipu_packet_ready_o=1`，可以从 IPU 接收一个 fetch packet。若当前 packet 的最后一个 EP 同周期被 HEU 接收，VLIWPU 也会拉高 ready 接收下一 packet，避免 packet 边界多出一拍空泡。

一旦接收 packet，VLIWPU 持有它，直到这个 packet 内所有 slot 都被发成 EP。

如果当前 EP 到达 fetch packet 末尾、不是 SYSTEM/BRANCH、且 `MaxIssueSlots` 还有空间，VLIWPU 不立即把这个尾部 EP 发给 HEU，而是把尾部 slot 暂存到 carry 缓冲。下一 fetch packet 到来后，VLIWPU 把 carry tail 和下一包开头 slot 压缩成同一个 EP 输出。这个机制允许例如 `sub` 位于第一个 fetch packet 尾部时，和第二个 fetch packet 开头的 `vle/slli` 合到同一个 EP。

### 6.2 header 和 p-bit

`header = packet_q[31:0]`。当前约定 header 是 `lui x0, imm20` 形式的 RISC-V HINT。VLIWPU 不完整执行这条指令，只检查 opcode/rd 是否匹配 LUI-x0 hint，然后解析 `imm20`：

```systemverilog
incoming_header_is_lui_hint = (incoming_header[6:0] == 7'b0110111) &&
                              (incoming_header[11:7] == 5'd0);
header_imm20 = header[31:12];
p_bits       = header_is_lui_hint ? header_imm20[0 +: Packet256Slots-1] : '0;
```

`p_bits[i]` 表示 slot i 后面是否请求继续与下一条指令打包。p-bit 是“请求并行”的 hint，不是强制并行；系统/分支、依赖断点、32-bit 边界和最大 issue 数都可以终止打包。

`imm20` 其余控制位：

- `imm20[13]`：`packet256`，当前 logical packet 需要再接收下一条 128-bit fetch beat。
- `imm20[14]`：`cross`，packet 尾部 EP 可以跨到下一个 logical packet 开头。
- `imm20[15]`：`loop_start` metadata。
- `imm20[16]`：`loop_end` metadata。

`packet256` 不改变外部总线宽度。IPU 仍每次给 128 bit；VLIWPU 用 `pending_256_q/pending_first_beat_q` 暂存第一 beat，第二 beat 到来后组成 `{second_beat, first_beat}` 的 256-bit `packet_q`。没有 `packet256` 时，`packet_q` 高 128 bit 补 0。

### 6.3 slot 提取

`slots[i] = packet_q[32 + i*16 +: 16]`。slot0 是 header 后面的第一个 16-bit slot。对普通 128-bit packet，有 6 个有效 slot；对 256-bit logical packet，有 14 个有效 slot。

`raw_slot_is_32b[i] = slots[i][1:0] == 2'b11`。RISC-V 32-bit 指令低两位为 `11`，所以一个 32-bit 指令从 slot i 开始，占 slot i 和 slot i+1。

### 6.4 continuation 标记

`p_slot_marks` 用 `skip_next` 扫描当前 logical packet 的有效 slot。

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

- 到 packet 最后一个 slot，且不能或不需要跨包 carry。
- 达到 `MaxIssueSlots`。
- 对应 p-bit 为 0。
- `ctrl_vliwpu_dep_break_i` 对应 bit 为 1。
- 当前指令是 SYSTEM。
- 当前指令是 BRANCH。

因此 p-bit=1 只允许继续；真正是否能继续还要看这些硬边界。

### 6.7 跨 fetch packet carry

跨包 carry 只处理被 header `cross=1` 明确授权的 logical packet 尾部非控制流 EP：

- `tail_cross_candidate=1` 时，当前尾部 EP 不直接发给 HEU。
- VLIWPU 把当前尾部 slot、slot class、32-bit 起点标记和尾部第一条指令 PC 存入 carry 寄存器。
- 下一 fetch packet 到来后，VLIWPU 从 slot0 开始继续扫描，把能放入的开头指令压缩到 carry tail 后面。
- 跨包 EP 会同时输出 `vliwpu_heu_execute_slot_pc_o[i]`，每个压缩后的 slot 都带真实 PC。fetch packet 之间有 4B hint header 间隙，不能再假设 `base + slot_index*2` 就是真实地址。HEU 用 per-slot PC 组装标量/向量指令 PC，避免 `bnez` 这类 PC-relative 指令算错目标。
- 如果 tail 中有 SYSTEM/BRANCH，或 issue slot 已满，就不会跨包。
- 如果 tail 之前的同一个 fetch packet 已经出现 SYSTEM/BRANCH，也不会跨包；这避免最后一轮 `ret` 后的 `nop` 占位指令被错误 carry 到下一包。

这个机制减少小循环中“packet 尾部单独成 EP”的开销，但不改变控制流边界：branch、jal、jalr、ret 仍然强制结束 EP。

### 6.8 execute valid/ready

`vliwpu_heu_execute_valid_o = normal_execute_valid | cross_execute_valid`。普通 EP 来自当前 packet；跨包 EP 来自 carry tail 加当前 packet 开头。

`execute_accept = valid & heu_ready`。HEU 接收后，VLIWPU 更新 `head_slot_q`。

### 6.9 head slot 更新

如果本 EP 包含 packet 最后一个 slot，说明整个 fetch packet 消费完，VLIWPU 清 `packet_hold_valid_q` 并让 IPU 送下一包。

如果本 EP 是跨包 EP，VLIWPU 根据本次从新 packet 开头消耗到哪个 slot 来更新 `head_slot_q`。如果新 packet 开头也被完全消耗，则清空 `packet_hold_valid_q`；否则下一次从剩余 slot 继续打包。

否则，VLIWPU 扫描 `issue_mask` 中最后一个置 1 的 slot，把 `head_slot_q` 设置为它的下一个 slot。下一周期从那里继续打包同一个 fetch packet 的剩余指令。

### 6.10 flush

`flush_i` 清 `packet_hold_valid_q`、`head_slot_q` 和 carry 缓冲。在 `hdv_top` 中，VLIWPU 的 flush 包含 task error/complete 和 redirect，因此 redirect 后不会继续使用旧 packet 或旧跨包 tail。

## 7. `hdv_hybrid_execution_unit.sv`：HEU

HEU 是 EP 分发器。它接收 VLIWPU 的 EP，把 EP 内 scalar 和 vector 指令切片分别送到后端。

### 7.1 输入 EP

HEU 输入包括：

- `vliwpu_heu_execute_valid_i`
- `vliwpu_heu_execute_slot_valid_i`
- `vliwpu_heu_execute_slot_i`
- `vliwpu_heu_execute_slot_is_32b_i`
- `vliwpu_heu_execute_slot_pc_i`
- `vliwpu_heu_execute_class_i`
- `vliwpu_heu_execute_pc_i`

HEU 不重新决定 EP 边界，只消费 VLIWPU 已经生成的 issue mask 和 class。

### 7.2 `p_split`

`p_split` 扫描每个 slot，跳过 32-bit 指令的 continuation slot。

对于一个真实指令起点：

- 使用 VLIWPU 给出的 per-slot PC：`vliwpu_heu_execute_slot_pc_i[i]`。
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

`heu_vliwpu_execute_ready_o = !buffer_valid_q`。

HEU 当前允许一个正在等待后端 `done/acknowledged` 的 current EP，再加一个 skid buffer EP。只要 skid buffer 为空，VLIWPU 就可以继续交下一个 EP。这样后端有一两拍延迟时，不会立刻反压到 VLIWPU。

### 7.5 buffered vector 提前发射开关

当前 `hdv_top` 以 `.EnableBufferedVectorEarlyIssue(1'b1)` 实例化 HEU，因此 buffered vector 提前发射是打开的。基础路径仍然是：

- skid buffer 可以提前接收下一 EP。
- skid buffer 的 scalar slice 必须等 promote 为 current 后再发送。
- skid buffer 的 vector slice 在安全条件满足时可以提前发给 vector dispatch。

提前发射的目标是让 Ara 前端尽量不断供给：如果 current EP 还在等 scalar slice done 或 vset 写回，而 buffered EP 中有与 current EP 标量结果无关的 vector 指令，就可以先让 vector dispatch 捕获它需要的 scalar operand 并排队到 Ara。

安全边界是：

- 只看 skid buffer 中的下一 EP，不越过更多 EP。
- HEU 为每个 vector slice 分配 `heu_vector_ep_id_o`；vector dispatch acknowledged 时返回 `vec_ep_acknowledged_id_o`。
- 不跨越 current EP 中尚未 resolved 的 scalar control-flow，包括 branch/jal/jalr/ret 和常见 RVC branch/jump。
- 不提前发送 scalar slice。
- 不改变 vector 指令进入 Ara 的程序顺序。
- vector dispatch 必须已经能保存正确的 scalar operand snapshot，否则后续 scalar EP 可能改写寄存器。
- buffered vector 的 GPR/FRF 读集合不能依赖 current scalar 写集合。
- current EP 如果含 `vset rd!=x0`，buffered vector 不能读取同一个 `rd` 作为标量 AVL/operand；如果 buffered vector 自己也含会写 rd 的 vset，则不能与 current vset 写同一 rd。

相关状态仍在 RTL 中保留，用于参数打开时区分 current/buffered vector slice：`buffer_vector_sent_q`、`buffer_vector_slice_outstanding_q`、`vector_dispatch_from_buffer_q`、`current_vector_id_q`、`buffer_vector_id_q`、`vector_dispatch_id_q` 和 `current_has_branch_q`。

依赖集合由 HEU 内部保守解码：

- `scalar_gpr_write_mask`：当前 scalar slice 可能写的 XRF rd。
- `scalar_fpr_write_mask`：当前 scalar FPU/FP load 等可能写的 FRF rd。
- `vector_gpr_read_mask`：buffered vector 可能读取的 `rs1/rs2`，包括 indexed/strided memory 的 scalar stride/base。
- `vector_fpr_read_mask`：buffered vector 可能读取的 `frs1`，例如 OPFVF。
- `vector_write_mask`：`vset rd!=x0` 对 XRF 的写回。

只有这些 mask 不冲突，且 vector dispatch ready，`buffer_vector_issue_fire` 才会发生。

### 7.6 后端 valid 清除

如果 `scalar_dispatch_valid_q && scalar_heu_ready_i`，标量 dispatch valid 清零。向量同理。

这里的 ready 只表示后端接收了这份 dispatch 数据，不表示 EP slice 已经完成。完整前端推进还要等 `scalar_ep_done_i` 或 `vector_ep_acknowledged_i`。

### 7.7 accept packet

`accept_packet = vliwpu_heu_execute_valid_i & heu_vliwpu_execute_ready_o`。

同周期 HEU：

- 置 `outstanding_d=1`。
- 清旧 error。
- 根据 `has_scalar/has_vector` 置 dispatch valid。
- 保存 dispatch 指令、PC 和 valid mask。

### 7.8 pending 和 EP acknowledged

如果 EP 含 scalar，`scalar_pending_d=1`。如果 EP 含 vector，`vector_pending_d=1`。

后端报告“本 EP 切片已达到前端可推进点”时拉：

- `scalar_ep_done_i`
- `vector_ep_acknowledged_i`

HEU 清对应 pending。这里的 vector acknowledged 不是“执行完成/退休”，而是“向量派发已捕获本 EP 所需标量操作数，HEU 可以从依赖控制角度推进到下一个 EP”；scalar done 则表示 scalar slice 已执行并写回。

当：

- `scalar_pending_d=0`
- `vector_pending_d=0`
- `scalar_dispatch_valid_d=0`
- `vector_dispatch_valid_d=0`

时，HEU 认为 EP 已达到前端推进条件，清 `outstanding_d` 并产生一拍 `heu_top_ep_acknowledged_o`。若当前 vector valid 属于 buffered EP 的提前发射，HEU 会等它被 vector dispatch ready 接收后再 promote buffer，避免清掉仍在握手中的 buffered vector 状态。

### 7.9 error

`backend_heu_error_i` 在 EP outstanding 或接收 packet 同周期有效时锁存到 `error_q`。如果 error 存在，HEU 不产生 acknowledged 脉冲，而是通过 `heu_top_ep_error_o` 暴露给上层。

### 7.10 flush

HEU 当前使用 `heu_flush = task_flush | task_complete_request`。也就是说，task flush 和 task complete 会清 outstanding、slice outstanding、dispatch valid、ep acknowledged 和 error；普通 branch redirect 不再直接 flush HEU。

这个区分很重要：branch EP 可能在同一拍由 scalar backend 完成并产生 redirect。如果 redirect 同拍清 HEU，会把这个 EP 的 acknowledged 脉冲也清掉，导致 testbench/host 看到的 EP 计数少于真实后端事件数。redirect 仍会清 VLIWPU 和 vector dispatch 的旧顺序路径状态，但不会抹掉 HEU 当前 EP 的后端事件。

## 8. `hdv_vec_dispatch_unit.sv`：HEU 到 Ara

这个模块把 HEU 的多 slot vector EP 转换成 Ara CV-X-IF 风格的单条 accelerator request。

### 8.1 当前语义

`vec_ep_acknowledged_o` 是给 HEU 的 vector EP acknowledged 脉冲。vtrace 模式下，普通 vector EP 在进入本模块内部 buffer 后即可 acknowledged，后续由本模块继续把其中的 vector 指令顺序送给 Ara。真实标量模式下，acknowledged 要等本 EP 的 vector request 都已经捕获 scalar operand；request 可以已经被 Ara 接收，也可以在 resolved command window 中等待 Ara ready。

例外是 `vsetvli/vsetivli/vsetvl` 且 `rd!=x0` 的 EP。Ara response 会返回新的 VL/rd 值，后续 scalar EP 可能读取这个寄存器。因此这类 EP 会等到对应 vset response 写回到 scalar backend 后，才向 HEU 拉 `vec_ep_acknowledged_o`。

所有其他 Ara response 只用于 exception、vset 写回和 task drain 的 busy 判断，不再阻塞后续 EP 供给。向量指令之间的数据依赖由 Ara 后端自己处理，HDV 不在 vector dispatch 里等待向量指令退休。

这样做的目的是让 HDV 前端尽可能不断供给 Ara，避免因为把 `resp_valid/load_complete/store_complete` 当作 EP done 而过度保守。

### 8.2 向量标量操作数来源

Ara vector 指令仍需要 `rs1/rs2/frs1` 等标量操作数。当前有两种来源：

- `UseCva6HdvScalar=1`：`hdv_vec_dispatch_unit` 通过 operand service 向 `hdv_scalar_backend` 读取真实 XRF/FRF。这是当前真实标量后端路径。
- `UseCva6HdvScalar=0`：`hdv_vec_dispatch_unit` 使用 vtrace 文件提供离线标量上下文，作为 bring-up/debug 模式。

vtrace entry 格式是：

```text
{insn[31:0], rs1[63:0], rs2[63:0]}
```

`VTraceDepth` 默认为 `N_VINSN`，`VTraceFile` 默认为 `apps/ideal_dispatcher/vtrace/vsaxpy.vtrace`。只有 `UseVTraceScalar=1` 时 initial block 才会 `$readmemh` 读入。

### 8.3 状态和内部 buffer

`insn_valid_q` 和 `insn_q` 是当前正在发给 Ara 的 EP 缓冲。另有一组 `pending_*` skid buffer，可在当前 EP 还未完全发完时提前接收下一个 vector EP。

状态：

- `IDLE`: 等 HEU vector dispatch。
- `DISPATCH`: 找最低有效 slot，驱动 Ara request。
- `DONE`: 当前缓冲 EP 的 vector slot 都已送入 Ara request 接口，切到 pending EP 或回到 `IDLE`。
- `WAIT`: 当前保留但实际只直接转 DONE。

### 8.4 slot priority encoder

`slot_found/slot_idx` 每周期从低到高找第一个 `insn_valid_q[i]=1` 的 slot。另有一组 input priority encoder 用于 `IDLE && heu_vec_valid_i` 的首条指令旁路。这样 vector EP 内指令按 slot 顺序发给 Ara，同时新 EP 到达时如果 Ara ready，可以同周期发出第一条 request。

### 8.5 request 生成

当内部缓冲有有效 slot，或 `IDLE` 同周期收到新的 vector EP 且其中有有效 slot 时，模块驱动：

- `acc_req.req_valid=1`
- `acc_req.insn = selected_insn`
- `acc_req.frm = RNE`
- `acc_req.rs1/rs2 = operand service 捕获值`，或 vtrace 模式下的 vtrace 当前项。

如果在 vtrace 模式下 vtrace 耗尽或当前 vtrace 指令与 EP 指令不匹配，则 `req_valid=0` 并报错，避免把错误标量值发给 Ara。真实标量模式下，`req_valid` 会等 operand service 捕获到当前向量指令的标量操作数后再拉高。

真实标量模式下，`vec_ep_acknowledged_o` 不能在 EP 入队时立即返回。原因是尚未处理的向量指令可能还没有读取 rs1/rs2/frs1，如果 HEU 提前推进后续标量 EP，标量寄存器可能被更新，旧向量指令会读到新值。因此真实标量模式等本 EP 的所有 vector slot 都被 dispatch FSM 消费，也就是 request 已经直接发给 Ara 或带 operand snapshot 进入 resolved command window 后，才向 HEU acknowledged；`vset rd!=0` 还要额外等 granted VL 写回。

`resp_meta_*` 是 Ara response 元数据 FIFO。每发出一条 vector request，就记录这条指令是否有 scalar-visible writeback、是否写 FPR、是否为 vset、是否为 vector store、`rd` 和 `ep_id`。Ara response 返回时弹出对应元数据，从而判断是否需要产生 `vec_scalar_wb_valid_o`，并给等待 vset 写回的 EP 产生 acknowledged。`vec_store_inflight_o` 由 response metadata 中的 store 项给 scalar backend 做保守内存定序。

真实标量模式下还有一个两项 `real_wait_*` acknowledged wait table。每个被 HEU 接收的 vector EP 会记录 `{ep_id, has_vset, operands_captured, vset_wb_done}`：

- `operands_captured` 表示该 EP 的所有 vector slot 都已经被 dispatch FSM 消费，标量操作数已经被读取并保存；request 可能已经到 Ara，也可能暂存在 resolved command window。
- `vset_wb_done` 表示该 EP 中 scalar 可见的 `vset rd!=x0` response 已经回来并写回标量后端。
- `real_ep_safe = operands_captured && (!has_vset || vset_wb_done)` 时，vector dispatch 才返回 `vec_ep_acknowledged_o` 和对应 `vec_ep_acknowledged_id_o`。
- wait table 用 `ep_id` 标记等待项。当前 HEU buffered vector 提前发射已在 `hdv_top` 中打开，因此它用于真实标量模式下区分 current/buffered 两类可能排队的 vector EP，避免把 acknowledged 归错 EP。
- `vec_ep_acknowledged_o` 在真实标量模式下由 registered wait-table 状态组合产生。这避免了把 acknowledged 再打一拍后造成的额外空泡。
- `vec_ep_ready_o` 允许同周期弹出一个 safe wait entry 并接收新的 vector EP，减少两项 wait table 满时的空泡。

向 Ara 发送 request 前，还有一个参数化 resolved command window。当前顶层默认 `VectorCmdWindowDepth=8`，并传给 `hdv_vec_dispatch_unit.CmdWindowDepth`。它不是大规模重排序窗口，只是一个小型顺序 FIFO：

- `vq_count_q` 表示 window 中已有多少条 resolved request。
- `vq_insn_q[0] / vq_rs1_q[0] / vq_rs2_q[0]` 是队头，优先驱动 `acc_req_o`。
- window 为空且 Ara ready 时，FSM request 可以 bypass 直接送 Ara。
- Ara backpressure 时，FSM 仍可把已经解析并抓好 operand 的 request 追加进 window，直到 `CmdWindowDepth` 项满。
- `accept_insn` 表示 FSM 这条 vector 指令已被 Ara 接收或被放入 command window，因此 dispatch FSM 可以继续处理 EP 内下一条 vector slot。

### 8.6 accept 指令

当前 `accept_insn = (vq_bypass & ara_acc) | vq_push`。

这表示 vector dispatch FSM 当前选中的一条向量指令已经被消费：

- window 为空且 Ara ready 时，request bypass 直接被 Ara 接收。
- Ara backpressure 时，request 带着已捕获的 `rs1/rs2` 被放入 command window。

FSM 消费一条指令后：

- 清 `insn_valid_d[slot_idx]`。
- vtrace index 加 1。
- 如果还有有效 slot，继续留在 DISPATCH。
- 如果没有有效 slot，进入 DONE。

如果这条指令来自 `IDLE` 同周期输入旁路，则清的是 `input_slot_idx` 对应的 valid bit，再把剩余 slot 写入内部缓冲。因此只要 operand service 和 command window 有空间，新 EP 的第一条 vector 指令不需要等到下一拍，EP 内后续指令也可以连续每周期消费；Ara 是否当拍 ready 由 resolved command window 解耦。

### 8.7 response 和 error

`resp_ready` 永远为 1，模块总是愿意接收 Ara response。当前只把 `resp_valid && exception.valid` 作为错误上报，不用 response 表示 EP complete。

### 8.8 flush

flush 清 state、当前 EP buffer 和 vtrace index。注意现在 flush 会把 vtrace 从 0 开始，这适合当前整任务重启式仿真；如果未来支持复杂 redirect 后继续 vtrace，需要 vtrace PC/index 映射。

## 9. `hdv_mock_host_core.sv`

mock host 当前主要模拟主核/任务控制器：写 CSR 启动 task，观察 EP acknowledged/task done/task busy/error，并打印 PASS/FAIL。关闭真实标量后端时，它也可以接管 scalar dispatch，作为临时标量后端和 mock branch 逻辑。真实标量后端打开时，任务通常由 `ret` 或 `ebreak` 触发 scalar backend task complete；expected EP 主要用于 testbench 的一致性检查和兜底结束。

### 9.1 参数

- `AutoStart`: 是否复位后自动启动。
- `AutoStartDelay`: 等多少周期后启动。
- `AutoTaskEntry`: 写入 VTASK_ADDR 的 entry。
- `AutoTaskDesc`: 写入 VTASK_PADDR 的 descriptor。
- `AutoExpectedEpAcknowledges`: 期望收到多少个 EP acknowledged。
- `EnableMockBranch`: 是否模拟 bnez redirect。
- `MockLoopIterations`: mock 循环次数。
- `TaskWatchdogCycles`: 整 task 超时。
- `PacketWatchdogCycles`: EP acknowledged 长时间不来时超时。

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

- `mock_hdv_scalar_ep_done_o=1`
- 下一拍 pending 清零

这里 ep done 代表 mock 标量后端处理完这个 EP 标量切片。它不是完整真实标量流水线。

### 9.5 vector backend mock

当前顶层向量已经内部接 Ara，所以 `ara_tb` 把 mock vector 输入绑 0。mock host 里仍保留 vector ready/acknowledged 逻辑，用于旧连接或未来测试。

### 9.6 mock branch

`is_mock_bnez` 识别 opcode branch、funct3=BNE、rs2=x0 的 `bnez` 形式。

`branch_target` 按 B-type immediate 从指令中拼出 signed offset，再加当前 PC。

如果 `EnableMockBranch && scalar_fire`，mock host 扫描 scalar EP 中的指令。遇到 bnez：

- 如果 `loop_iters_remaining_q > 1`，认为 taken。
- 计算 redirect PC。
- 递减 loop counter。
- 设置 `branch_redirect_wait_d=branch_taken`。

redirect 不在 scalar_fire 同周期发出，而是等 `mock_hdv_scalar_ep_done_o` 后再发。这样可以避免同周期 redirect flush 把 branch EP 自己的 done/acknowledged 事件冲掉。

### 9.7 loop lock 输出

`mock_hdv_loop_lock_o = EnableMockBranch && RUN && loop_iters_remaining_q > 1`。

这是旧的 mock 辅助信号，当前 `ara_tb` 不再把它接入 DUT，而是把外部 `hdv_loop_lock_i` 固定为 0，让 `hdv_top` 和 IPU 的自动 loop lock 逻辑接管。真实标量模式下，taken redirect 由 `hdv_scalar_backend` 的 branch 路径产生；关闭真实标量后端时，mock host 仍可模拟 taken redirect。

### 9.8 EP acknowledged 计数

`hdv_mock_ep_acknowledged_i` 每来一拍：

- `acknowledged_eps_q++`
- 清 packet watchdog

如果加一后达到 `expected_ep_acknowledges_q`，进入 `COMPLETE_TASK`。此外，RUN 状态下如果看到 `hdv_mock_task_done_i` 或 `hdv_mock_task_busy_i` 已经拉低，也会进入状态读取流程；这覆盖真实标量后端执行 `ret`/`ebreak` 后由 HDV 自己结束任务的路径。

### 9.9 task complete

`COMPLETE_TASK` 拉 `mock_hdv_task_complete_o=1` 一拍，作为外部 task complete 请求。TSU 收到后置 task done。mock host 随后 `WAIT_TASK_STATUS` 等 HDV status 更新，再 `READ_STATUS` 确认没有 error，最后 FINISH。若真实标量后端已通过 `ret` 让 HDV done，mock host 可以跳过主动 complete，只读取状态。

### 9.10 watchdog

`task_watchdog_q` 在整个 task active 期间计数。超时直接 FAIL。

`packet_watchdog_q` 只在 RUN 状态计数。如果很久没有 EP acknowledged，说明前端或后端卡住，也 FAIL。

## 10. `hdv_top.sv`

`hdv_top` 把所有 HDV frontend 模块、Ara、AXI mux 和外部 mock/scalar 接口接起来。

### 10.1 对外接口分组

host CSR：

- `host_hdv_csr_*` 输入给 TIU。
- `hdv_host_csr_*` 从 TIU 返回。

控制：

- `ctrl_hdv_redirect_valid_i/pc_i` 给 IPU，并作为 dispatch flush 清 VLIWPU/HEU/vector dispatch。
- `ctrl_hdv_loop_lock_i` 给 IPU，作为外部显式 lock；硬件自动 lock 由 `hdv_top` 的后向 branch 检测和 IPU 的 active-buffer redirect hit 共同产生。
- `ctrl_hdv_dep_break_i` 给 VLIWPU。

task 状态：

- `host_hdv_task_complete_i/error_i` 从 mock host 或未来 task controller 来。
- `hdv_host_task_busy_o/done_o/error_o` 给外部观察。

scalar dispatch：

- `hdv_scalar_valid_o`
- `scalar_hdv_ready_i`
- `hdv_scalar_insn_*`
- `scalar_hdv_ep_done_i`

vector dispatch 不再作为 top 外部端口，它在 top 内部进入 `hdv_vec_dispatch_unit` 和 Ara。

EP 状态：

- `hdv_host_ep_busy_o`
- `hdv_host_ep_acknowledged_o`
- `hdv_host_ep_error_o`

### 10.2 task busy

`task_busy = tsu_top_busy | ipu_top_busy | heu_top_busy | vec_dispatch_busy`。

它表示 HDV 中还有任务排队、正在取指、HEU 还有 EP outstanding，或 vector dispatch/Ara adapter 中仍有已接管但未清空的 vector request。

### 10.3 flush 分层

`task_complete_request = host_hdv_task_complete_i | scalar_backend_task_complete`。

`task_done_to_tsu = (task_complete_request | host_task_complete_seen_q) & !vec_dispatch_busy`。如果 scalar backend 已经看到 `ret`，但 vector dispatch 还有 request/response metadata 没清空，top 会先锁存 complete seen，等 vector dispatch drain 后再通知 TSU done。

`task_flush = flush_i | task_error_to_tsu | tsu_top_error`。

`dispatch_flush = task_flush | task_complete_request | hdv_ctrl_redirect_valid`。

`heu_flush = task_flush | task_complete_request`。

IPU 使用 `task_flush`，这样 redirect 不会被当成普通 flush，而是走 IPU 的 redirect path。

IPU 接收 redirect 请求并重定向取指。VLIWPU 和 vector dispatch 使用 `dispatch_flush`，因为 redirect 后旧 packet、旧 carry、旧 vector request window 都必须丢弃；task complete 时也要停止继续分发 fallthrough padding 指令。

HEU 使用 `heu_flush`，不把 branch redirect 作为 flush 输入。这样 branch EP 被 scalar backend 完成并产生 redirect 的同拍，HEU 仍能正确输出 `heu_top_ep_acknowledged_o`，不会因为 redirect 清状态而漏计 EP acknowledged。

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

`imem_outstanding_q` 统计已经发出但尚未收到最后一个 R beat 的取指 read。AR handshake 递增，R handshake 且 `last` 递减，二者同周期则保持不变。AXI R 通道在 outstanding 非零时持续 ready；如果 IPU 因 flush/task complete 已不再接收 response，bridge 会 drain 并丢弃旧 response，避免 AXI fabric 被旧预取卡住。当前默认深度为 `ImemOutstandingDepth=4`，和旧 64B buffer 的 4 个 packet 行为相同；当前 IPU buffer 本身已由顶层放大到 512B。

### 10.5 Ara invalidation packing

Ara 原本通过 CV-X-IF response 带 cache invalidation 信息。这里 `axi_inval_filter` 仍实例化，`pack_ara_invalidation` 把 filter 产生的 inval 信号注入 `ara_acc_resp_pack`。

当前 `acc_cons_en` 来自 `acc_req.acc_req.acc_cons_en`，通常为 0，所以 invalidation filter 结构连着但基本禁用。这样未来接回 CVA6 cache coherence 路径时不需要大改结构。

### 10.6 vector dispatch 和 Ara

HEU vector 输出连到 `i_vec_dispatch_unit`。该模块再驱动 Ara `acc_req_i`。Ara 的 `acc_resp_o` 经 invalidation packing 后回到 vector dispatch。

向量 acknowledged 路径是：

```text
Ara req_ready
  -> hdv_vec_dispatch_unit 清 slot / 推进 response metadata
  -> vec_ep_acknowledged_o（vtrace 模式普通 EP 入队即产生；真实标量模式等 request drain，vset rd!=0 还等 response 写回）
  -> HEU vector_ep_acknowledged_i
  -> HEU ep_acknowledged
```

### 10.7 AXI mux

`axi_mux` 有 3 个 slave port：

1. Ara AXI。
2. scalar AXI，连接 `hdv_scalar_backend` 的 load/store 端口。
3. HDV instruction fetch AXI。

scalar slot 现在连接 `hdv_scalar_backend`，用于真实标量 load/store。保留 3 个 slave port 仍然是为了不改变 system AXI ID 宽度和拓扑。

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

这里的 N 来自 `acknowledged_eps_q + 1`，表示 mock host 已观察到第 N 个 EP acknowledged。日志字符串仍沿用 `ep_backend_accept` 名称。

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
11. scalar 侧由 `hdv_scalar_backend` 执行并产生 `scalar_ep_done_o`；如果关闭真实标量后端，则由 mock host 产生 `scalar_hdv_ep_done_i`。branch EP 可能产生 redirect 和 loop lock。
12. vector 侧由 `hdv_vec_dispatch_unit` 接收 EP，并逐条发给 Ara。vtrace 模式下普通 vector EP 入队即向 HEU acknowledged；真实标量模式下等本 EP 的向量 request 都捕获了标量操作数后 acknowledged；`vset rd!=0` 还要等 Ara response 写回。
13. HEU 等 scalar/vector 切片都 done/acknowledged，产生 `ep_acknowledged`。
14. scalar backend 执行 fallthrough `ret` 后产生 task complete；如果 expected EP 先达到，mock host 也可发出兜底 complete。
15. top 等 vector dispatch drain 后通知 TSU/TIU done，mock host 读 STATUS，并用 expected EP 数做 PASS/FAIL 检查。

## 13. 调试时建议看的信号

### 13.1 task 层

- `i_hdv_mock_host_core.state_q`
- `i_hdv_mock_host_core.acknowledged_eps_q`
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
- `scalar_ep_done_i/vector_ep_acknowledged_i`
- `ep_acknowledged_q`
- `heu_top_ep_error_o`

### 13.5 vector dispatch/Ara 层

- `i_vec_dispatch_unit.state_q`
- `insn_valid_q`
- `slot_idx`
- `acc_req_o.acc_req.req_valid`
- `acc_resp_i.acc_resp.req_ready`
- `acc_req_o.acc_req.insn`
- `vtrace_idx_q`
- `vec_ep_acknowledged_o`
- Ara dispatcher/sequencer/VLSU 信号，例如 `req_ready`、`resp_valid`、`load_complete/store_complete`，用于看真实执行是否卡住。

## 14. 当前机制边界

当前 HDV 原型已经能表达结构流程：

- host/task CSR
- task queue
- IPU early serve、双 buffer、redirect、loop lock（**已改为由 scalar backend 的精确 branch_resolved 事件驱动**，不再依赖 dispatch 阶段 opcode 重解码）
- hint p-bit based VLIW packing
- HEU scalar/vector split、**buffered vector early issue 受 memory-ordering 约束保护**
- vector dispatch 到 Ara（**command window 已结构化为 `vq_entry_t`，携带 ep_id / cmd_class / side-effect flags**）
- mock scalar branch redirect
- **EP acknowledged 计数和 task done（信号已重命名：`accepted`→`acknowledged`/`done`，区分"前端推进"和"执行完成"）**
- **ebreak 可作为显式 task-end marker（与 ret 解耦，参数 `TreatEbreakAsTaskExit`）**
- **FENCE 已正确归类为 SYSTEM（EP 硬边界），在 scalar backend 中作为 NOP 处理**
- **Sequencer hazard bypass：HDV 的 ep_id（p-bit 保证）驱动 Ara sequencer 跳过同 EP 内的 RAW/WAW/WAR 检查（`vid_ep_id_q` per-vid 跟踪），减少 false hazard stall → 减少 Ara backpressure**
- **VLSU Next-VL prefetch：Ara VLSU 借鉴 ideal_execution 分支的解耦访存前端 + 预取机制。addrgen 自动检测 unit-stride load 并提前发射下一 VL 区间的预取 AR（AXI ID=PREFETCH）；预取返回数据存入 vldu 预取 buffer，命中时跳过 demand AXI beat。幅度由 VLIWPU header `imm20[18:17]` 控制（off/1X/2X/4X，匹配内核迭代步长 S/B；用法详见 porting guide §3.5）→ 累计 -35% cycles**
- **预取已泛化支持 LMUL 1/2/4/8（不再只 m1）。预取 buffer = vldu `PrefetchQueueDepth=64`×256bit = 2KB（行为级 `tc_sram`，宏 `TS1N28...64X256`）。addrgen 用基于 vldu buffer 占用的**信用流控**（`prefetch_inflight_beats` + issue 门控 `占用×2+在途+burst ≤128`），对任意 LMUL/流数 K(1-4) 都不溢出、不死锁。配套修复了 5 个原 m1-烤死点：vldu beat 计数器位宽 5→9bit（m4=32/m8=64 beats 完成判据）、hit 完成 `==4`→`4×LMUL`、buffer 32→64、信用流控、addrgen 页跨越配对 `len!=7`→ROB 段标志。**
- **HDV→Ara hints 贯通：`trans_id[3:0]` = {cmd_class, is_last_in_ep, ep_id} 经 acc_req → ara_req → sequencer；`hdv_ara_loop_active_o` 经 hdv_top → ara → VLSU 预留接口**

仍然是临时或待完善的部分：

- 真实标量后端已经接入 `hdv_scalar_backend`，支持当前 HDV 路径需要的寄存器、ALU/branch/LSU、operand service、vector-to-scalar 写回和 vset inflight interlock；但它还不是完整 CVA6 core，也还没有完整异常/commit/scoreboard。
- `hdv_vec_dispatch_unit` 在真实标量模式下通过 operand service 读取 `hdv_scalar_backend` 的 XRF/FRF；vtrace 只作为 bring-up/debug 模式。
- `ep_acknowledged` 不等于真实执行退休。如果要验证数据正确性，仍需观察 Ara 内部完成信号和内存结果。
- VLIWPU 的依赖断点 `ctrl_vliwpu_dep_break_i` 现在由外部提供，尚未自动分析 RAW/WAW/WAR。
- redirect 目标被要求 16B fetch packet/EP entry 对齐，不支持跳进 EP 中间。
- IPU 已有自动 loop lock/双 buffer 取指支撑逻辑，但仍需要结合更多 kernel 验证 taken/not-taken、redirect、loop exit 和 buffer 命中边界。
- **memory-ordering 保护当前为保守策略：current EP 含任何标量访存/FENCE/SYSTEM/AMO 时阻塞 buffered vector early issue。后续可通过 noalias 或更精细地址分析放宽。**
- **outstanding EP 数量硬编码为 2（HEU current + buffer），参数化为 `MaxOutstandingVecEPs`。扩展到 >2 EP 需同步加宽 EP ID 位宽。**

### 累计性能（vsaxpy_hdv，4 lanes，VLEN=1024）

| 阶段 | cycles | Δ | 关键技术 |
|---|---|---|---|
| 基线 | 1284 | — | — |
| + CmdWindowDepth 8 | 1284 | 0 | 消除 HDV 侧反压 |
| + operand pre-fetch (HDV) | 1283 | -1 | dispatch 4× 加速 |
| + sequencer hazard bypass (HDV ep_id) | 1066 | **-17%** | `vid_ep_id_q` 同 EP 免检 |
| + ideal VLSU 架构 | 829 | -22% | 解耦访存前端 |
| + prefetch 动态控制 (VLIWPU header) | **769** | **-7.2%** | `imm20[18:17]`→addrgen，95%命中率 |
| **累计** | | **-40%** | |

### 最终性能计数器（769 cycles）

当前 `hardware/sim/run.vcs.log` 中的性能输出分为四组：HDV vector dispatch、IPU fetch supply、Ara sequencer、VLSU addrgen。逐 EP 的高频明细不直接刷控制台，而是写入 `hdv_ep_trace_<TESTCASE>.log`，避免 `run.vcs.log` 被每个 EP 的 slot 信息淹没。

**IPU / Fetch supply** (`[IPU-PERF]`)：

| 指标 | 含义 |
|---|---|
| `serve_cycles` | IPU 处于 SERVE 状态的周期数。反映取指侧实际服务任务的时间窗口 |
| `packets` | VLIWPU 从 IPU 接收的 fetch packet 数 |
| `bypass_hits` | SRAM 同步读后一拍数据通过 `sram_bypass_hit` 直接供给当前 packet 的次数，避免再等 `served_packet_q` |
| `demand_reads` | 当前 packet cache miss 后发起的 SRAM demand read 次数。越低说明 read-ahead / loop-start cache 越有效 |
| `avg_cycles_per_pkt` | `serve_cycles / packets`，粗略衡量取指供给平均间隔。它包含下游 backpressure，不等价于纯 IPU miss penalty |
| `ready_cyc` | VLIWPU ready 且 IPU 在 SERVE 的周期数 |
| `ready_stall` | VLIWPU ready 但 IPU 没有 valid packet 的周期数。非 0 时说明取指侧确实饿住后级 |
| `stall_due_to_sram` | `ready_stall` 中与 demand SRAM read 同拍的次数，用来评估 SRAM 一拍读延迟造成的实际损失 |

**VLSU / Addrgen** (`[PERF-ADDRGEN]`)：

| 指标 | 含义 |
|---|---|
| `demand_ar` | 向量 load 指令发出的 AXI 读请求（demand AR）总数 |
| `pf_ar` | prefetch 机制发出的 AXI 读请求（prefetch AR）总数。`pf_hit / pf_ar` = 命中率 |
| `pf_hit` | demand load 的首地址命中 prefetch buffer 的次数。命中时跳过首 beat 的 AXI 等待 |
| `loads` | addrgen 接收到的向量 load 指令总数 |
| `pf_en_cyc` | `prefetch_en=1` 的周期数，反映预取活跃时间占比 |
| `demand_aw` | 向量 store 指令发出的 AXI 写请求总数 |
| `demand_B` | demand AXI 读请求的总字节数。`demand_B / demand_ar` = 平均 burst 大小 |
| `pf_B` | prefetch AXI 读请求的总字节数。`pf_B / demand_B` = 预取放大比 |

**Sequencer** (`[PERF-SEQ]`)：

| 指标 | 含义 |
|---|---|
| `issue` | sequencer 成功发射到 PE 的向量指令总数 |
| `blocked` | sequencer 有指令待发射但被阻塞的周期数（hazard/队列满/lane 不同步） |
| `raw` | RAW hazard 检测次数——新指令的源寄存器正在被前序指令写 |
| `war` | WAR hazard 检测次数——新指令的目标寄存器正在被前序指令读 |
| `waw` | WAW hazard 检测次数——新指令与未完成的前序指令写同一目标寄存器 |
| `waw_block` | 仅因 WAW（无 RAW 同时存在）导致发射阻塞的周期数。`waw_block / waw` = 纯 WAW 占比 |
| `ep_bypass` | 因 HDV ep_id 同 EP 免检而跳过的 hazard 检查次数。减少 false hazard stall |
| `full` | `vinsn_running_full=1` 的周期数——所有 8 个 vid 槽位都被占用，无法接收新指令 |

**HDV Dispatch** (`[HDV-PERF]`)：

| 指标 | 含义 |
|---|---|
| `dispatch_slots` | vec_dispatch FSM 消费的向量指令 slot 总数。`= vq_push + vq_bypass` |
| `vq_push` | 进入 command window 的请求数（Ara 反压时暂存） |
| `vq_bypass` | 绕过 command window 直发 Ara 的请求数（Ara 空闲时） |
| `vq_pop` | Ara 从 command window 取走的请求数。`vq_push ≈ vq_pop`（稳态） |
| `vq_full_stall` | FSM 有请求但 command window 满的阻塞周期数。0 = window 足够深 |
| `ara_backpressure` | command window 有数据但 Ara `req_ready=0` 的周期数。越大说明 Ara 是瓶颈 |
| `fsm_could_bypass` | FSM 有请求且 window 为空的周期数——理论上可 bypass。`vq_bypass / fsm_could_bypass` = bypass 成功率 |
| `ep_acknowledged` | 向量 EP 完成 operand 捕获的次数（≠ 向量指令执行完成） |
| `ep_vset_acknowledged` | 其中因等待 vset 写回而延迟确认的 EP 数 |
| `operand_wait_cycles` | FSM 等待标量 operand 捕获的周期数 |
| `resp_meta_full_stall` | 响应元数据 FIFO 满导致的阻塞周期数。0 = RespMetaDepth 足够 |
| `real_wait_full_stall` | EP 跟踪表满导致的阻塞周期数（>2 个 outstanding EP）。0 = MaxOutstandingVecEPs 足够 |
| `vq_max_occupancy` | command window 的峰值占用深度。`vq_max / CmdWindowDepth` = 利用率 |
| `resp_meta_max` | 响应元数据 FIFO 的峰值占用深度 |
| `dispatch_total_cycles` | FSM 在 DISPATCH 状态的周期总数。`dispatch_slots / dispatch_total_cycles` = 每周期吞吐 |

## 15. 阅读代码的推荐顺序

1. 先读 `hdv_pkg.sv`，记住 CSR 和 class（**FENCE 现已归类为 HDV_INST_SYSTEM**）。
2. 再读 `hdv_top.sv` 的 wire 和实例化，建立全局连接图（**loop control 已简化，`is_branch32/btype_target` 已删除**）。
3. 读 TIU/TSU，理解 task 生命周期。
4. 读 IPU，重点看 `state_q`、valid bit、redirect 和 loop lock。
5. 读 VLIWPU，重点看 p-bit、32-bit continuation、issue mask（**FENCE 归类变更**）。
6. 读 HEU，重点看 dispatch valid、**`scalar_slice_outstanding/vector_slice_outstanding`**、**`ep_acknowledged`**、**`current_has_branch/current_has_scalar_mem_order`**。
7. 读 vector dispatch，重点看 **`vq_entry_t` 结构化 command window**、`vec_ep_acknowledged_o`、Ara request、**仿真性能计数器 (`ifdef FOR_VERIFY`)**。
8. 最后读 mock host 和 TB，理解当前仿真为什么能跑起来，以及哪些地方只是临时模型。
9. **读 scalar backend 时留意 FENCE NOP 处理和 `TreatEbreakAsTaskExit` 参数**。
10. 性能调试时先读 `run.vcs.log` 的 `[HDV-CSR]`/`[HDV-PERF]`/`[IPU-PERF]`/`[PERF-SEQ]`/`[PERF-ADDRGEN]`，再用 `hdv_ep_trace_<TESTCASE>.log` 对照具体 EP。

## 16. 指令发射与依赖处理（合并自 hdv_instruction_issue_dependency_logic.md）

# HDV 指令发射与依赖处理逻辑总结

本文总结当前 HDV 原型中从取指包到 execute packet，再到标量/向量后端的指令发射、依赖处理和保序机制。重点是说明“哪些并行由软件/编译器提示，哪些由硬件强制切断，哪些依赖交给后端处理”。

## 1. 总体路径

当前 HDV 指令流大致是：

```text
host / task CSR
  -> TIU / TSU
  -> IPU instruction prefetch
  -> VLIWPU fetch packet decode / EP packing
  -> HEU scalar/vector split
  -> hdv_scalar_backend
  -> hdv_vec_dispatch_unit
  -> Ara
```

其中：

- IPU 只负责按 task entry 取 128-bit fetch packet，不理解指令依赖。
- VLIWPU 根据 hint p-bit、指令分类和硬边界形成 EP。
- HEU 不重新判断 EP 边界，只把 EP 拆成 scalar slice 和 vector slice。
- 标量后端执行标量 slice，并维护 XRF/FRF/CSR stub、branch redirect、标量 load/store。
- 向量后端适配器把 vector slice 串行送到 Ara，Ara 内部处理向量指令间的数据依赖。

## 2. Fetch Packet 和 Hint

当前外部取指 beat 宽度是 128 bit，也就是 16B。软件生成的 HDV 代码按 packet 组织，每个 packet 头部通常是一条 RISC-V HINT 指令，用来携带 p-bit 和 packet 控制位。

典型布局：

```text
packet base:
  word 0:      HDV_HINT imm
  slot 0..N:   real instructions after header
```

HINT 本身不是要被标量/向量后端执行的有效业务指令，而是给 VLIWPU 使用的打包提示。当前约定是用 `lui x0, imm20` 形式携带控制位：

```text
imm20[12:0] = p_bits
imm20[13]   = packet256
imm20[14]   = cross_next
imm20[15]   = loop_start
imm20[16]   = loop_end
```

`packet256=1` 时，VLIWPU 会把当前 128-bit beat 和下一 128-bit beat 合成一个 256-bit logical packet；总线宽度不变。`cross_next=1` 时，packet 尾部 EP 才允许显式跨到下一 packet 开头。

p-bit 的语义是“软件认为相邻指令可以继续打入同一个 EP”。它不是硬件无条件相信的并行保证。VLIWPU 仍会根据硬件规则切断 EP。

## 3. VLIWPU 的 EP 打包规则

VLIWPU 从 IPU 接收 fetch packet 后，按 slot 扫描指令，并形成一个或多个 execute packet。

### 3.1 指令分类

VLIWPU 会粗分类每条指令：

- `HDV_INST_SCALAR`: 普通标量整数、浮点、CSR/system 等。
- `HDV_INST_VECTOR`: RVV 指令，包括 vector load/store、vector arithmetic、`vsetvli/vsetivli/vsetvl`。
- `HDV_INST_BRANCH`: branch、jal、jalr 等控制流指令。
- system/unknown 当前通常走 scalar 侧或作为硬边界处理。

HEU 后面根据这个 class 把指令分到标量或向量后端。

### 3.2 p-bit 只是继续条件

VLIWPU 从当前 head slot 开始扫描：

1. 当前 slot 是有效指令起点。
2. 把它加入当前 EP。
3. 看 p-bit 是否允许继续。
4. 再看硬件边界是否必须切断。

p-bit 为 0 时，一定切断。p-bit 为 1 时，只表示“允许继续”，但还要满足其他条件。

### 3.3 强制切断条件

当前 EP 会在这些情况下切断：

- 到达 fetch packet 末尾，且不能进行跨包 carry。
- 达到 `MaxIssueSlots`。
- p-bit 不允许继续。
- 外部依赖断点 `ctrl_vliwpu_dep_break_i` 指示必须切断。
- 遇到 branch/jal/jalr/ret 等控制流边界。
- 遇到 system 类硬边界。
- 32-bit 指令 continuation slot 不能被当作新指令起点。

因此 EP 的含义是：“VLIWPU 认为可以一起发射、且没有触碰硬件边界的一组 slot”。

### 3.4 跨 Fetch Packet Carry

当前 VLIWPU 支持一种有限的跨包 EP：

- 如果 header 显式置 `cross_next=1`，且一个 fetch packet 尾部剩余 slot 可以和下一个 packet 开头指令合并，并且不是控制流/system 边界，则 VLIWPU 可以把尾部 slot carry 到下一包。
- 下一包到来后，VLIWPU 把 carry tail 和下一包开头 slot 合成一个 EP。
- 跨包 EP 必须带 per-slot PC，因为 fetch packet 之间有 HINT/header 间隙，不能再用 `packet_pc + slot_index * 2` 推导所有指令 PC。

跨包 carry 的目的只是减少 packet 边界产生的单指令 EP，不改变控制流规则。branch/jal/jalr/ret 仍然强制结束 EP。

## 4. EP 的语义

EP 是 HDV 的基本发射与依赖边界。一个 EP 可以同时包含标量指令和向量指令。

当前设计中，EP 有两个层次的含义：

- 对前端：VLIWPU 一次交给 HEU 的发射包。
- 对依赖：不同 EP 之间默认保序；同 EP 内由 VLIWPU/p-bit/外部 dep-break 保证没有需要 HDV 处理的数据依赖。

更具体地：

- 同一 EP 内的 scalar 和 vector slice 可以并行进入后端。
- 同一 EP 内多条 vector 指令按 slot 顺序送入 Ara，向量寄存器/流水依赖交给 Ara。
- 同一 EP 内多条 scalar 指令当前在 `hdv_scalar_backend` 内最多 3 发射：两个 simple ALU lane 加一个 complex lane。不能并行的标量指令仍会在后端内部等待。
- 不同 EP 之间当前靠 HEU slice outstanding / done / acknowledged、buffer EP 和 buffered vector early issue 的安全检查协调。

## 5. HEU 的发射和保序

HEU 接收 VLIWPU 的 EP，不重新做依赖分析，只做拆分和握手管理。

### 5.1 Scalar/Vector Split

HEU 对 EP 内每个有效指令起点：

- 按 `slot_is_32b` 拼成 32-bit 指令。
- 使用 VLIWPU 提供的 per-slot PC。
- 根据 class 放到 scalar valid mask 或 vector valid mask。

HEU 输出两条 dispatch 流：

```text
heu_scalar_valid_o / scalar_heu_ready_i
heu_vector_valid_o / vector_heu_ready_i
```

ready/valid 握手只表示后端接收了 dispatch 数据，不表示该 EP slice 已经执行完成或依赖已经解除。

### 5.2 Pending 和 Accepted

HEU 为当前 EP 维护：

- `scalar_pending_q`
- `vector_pending_q`

如果 EP 含 scalar，则 scalar pending 置位；如果 EP 含 vector，则 vector pending 置位。

对应后端拉：

```text
scalar_ep_done_i
vector_ep_acknowledged_i
```

后，HEU 清对应 pending。

当当前 EP 满足：

```text
scalar pending 已清
vector pending 已清
scalar dispatch valid 已被 ready 接收
vector dispatch valid 已被 ready 接收
没有 packet 级错误
```

HEU 产生一拍 `heu_top_ep_acknowledged_o`，表示这个 EP 从 HDV 依赖角度已经被后端安全接管。

注意：`ep_acknowledged` 不是“所有指令执行退休”。它只是 HDV 前端允许推进到下一个 EP 的同步点。

### 5.3 HEU Skid Buffer

当前 HEU 允许：

- 一个 current EP 正在等待后端 done/acknowledged。
- 一个 buffer EP 暂存在 HEU 内。

只要 buffer 为空，VLIWPU 就可以继续把下一个 EP 交给 HEU。这样 scalar/vector 后端有少量延迟时，不会立刻反压到 IPU/VLIWPU。

### 5.4 Buffered Vector Early Issue 的当前状态

代码中保留了 `EnableBufferedVectorEarlyIssue` 参数，`hdv_top` 当前显式打开：

```systemverilog
.EnableBufferedVectorEarlyIssue(1'b1)
```

打开后，buffered EP 的 vector slice 在满足安全条件时可以早于该 EP promote 为 current 进入 vector dispatch。HEU 仍不提前发 scalar slice，也不跨越 current EP 中尚未 resolved 的控制流。

提前发射必须满足：

- buffer EP 有 vector slice，且该 slice 尚未发送。
- vector dispatch 当前输出寄存器空闲。
- current EP 没有未处理的 branch/jal/jalr/ret。
- current scalar 写 GPR/FPR 与 buffered vector 读 GPR/FPR 没有冲突。
- current vector/vset 对 buffered vector 没有配置或向量寄存器冲突。

因此这个优化只放松“不同 EP 必须完全串行”的限制，不放松控制流和标量 operand snapshot 的正确性要求。

后续如果继续加速，主要空间在 vector dispatch 内部的 operand snapshot / resolved-request buffer 深度、批量化能力，以及 HEU 对更多无关 EP 的窗口化识别。

## 6. 标量后端的依赖处理

当前真实标量后端是 `hdv_scalar_backend`。它不是完整 CVA6 core，而是复用 CVA6 decoder/ALU/branch/mult/FPU 部件的 HDV 专用标量后端。

### 6.1 EP 内标量执行

标量后端接收一个 scalar slice 后：

1. 锁存该 EP 的 scalar slots。
2. 解压 RVC，使用 CVA6 decoder 分类。
3. 尝试每周期发射最多 3 条标量指令。
4. 两条 simple ALU lane 处理 LUI/AUIPC/OP-IMM/OP-IMM-32/OP/OP-32 这类简单整数指令。
5. 一条 complex lane 处理 branch/jal/jalr/CSR/MULT/FPU/LSU/复杂或有序指令。
6. 写回 XRF/FRF/CSR stub，所有 scalar slots 处理完后拉 `scalar_ep_done_o`。

后端会做本周期 simple batch 内的读写 mask、重复 rd、order barrier、vset RAW、complex 读 simple 写等检查。能并行的标量指令同周期发射；不能并行的留到后续周期，保证功能正确。

### 6.2 标量寄存器依赖

当前没有完整 scoreboard，也没有乱序 commit。依赖正确性主要来自：

- VLIWPU/软件 p-bit/dep-break 尽量不把有依赖的标量指令打进同一个 EP。
- 标量后端仍有 EP 内基本 hazard 检查，避免明显 RAW/WAW/order 问题在多发射 lane 中出错。
- 不同 EP 之间由 HEU 等 `scalar_ep_done` 和 `vector_ep_acknowledged` 保序；在 buffered vector early issue 下，HEU 只提前满足依赖 mask 的 vector slice。
- 标量后端在 scalar slice 所有写回完成后才 done。

因此，如果 EP 间有 RAW 依赖，例如：

```text
EP1: vsetvli t0, a0, ...
EP2: sub a0, a0, t0
```

则 EP2 的标量读取应发生在 EP1 的相关写回被 acknowledged 规则保护之后。

### 6.3 分支和 Redirect

branch/jal/jalr/ret 走 scalar 后端。

标量后端负责：

- 解析 branch 条件。
- 计算 target。
- taken 时产生 `redirect_valid_o/redirect_pc_o`。
- 同时给顶层 loop lock/exit 逻辑提供 branch resolved 信息。

顶层将 redirect 送回 IPU，并 flush VLIWPU/HEU/vector dispatch。当前约定 redirect target 应是 fetch packet/HDV_HINT 后的 EP 起点，最好 16B 对齐；不支持跳入 EP 中间。

branch 是强控制边界：

- VLIWPU 不应把 branch 后面的顺序路径指令打进同一个 EP。
- redirect 后旧 fetch packet、旧 carry、旧 EP 都必须丢弃。

## 7. 向量后端的依赖处理

向量路径由 `hdv_vec_dispatch_unit` 驱动 Ara。

### 7.1 Vector EP 到 Ara Request

HEU 给 vector dispatch 的是一个 vector slice，里面可能有多个 vector slots。Ara accelerator request 一次只能接收一条指令，所以 vector dispatch 做串行化：

1. 缓存 EP 内 vector slots。
2. 每周期选择最低 index 的有效 vector slot。
3. 读取该指令需要的 scalar operand。
4. `acc_req.req_valid` 拉高。
5. Ara `req_ready` 后清该 slot。
6. 继续下一条。

所以同一 EP 内 vector 指令发给 Ara 的顺序是 slot index 从低到高。

### 7.2 向量指令之间的依赖

HDV 不在前端实现向量寄存器 scoreboard。

当前假设是：

- Ara 后端本身处理 RVV 指令之间的寄存器、流水、load/store 顺序和结构冲突。
- HDV 只保证送入 Ara 的 program order。
- HDV 不等待普通 vector response 表示 EP 完成。

例如：

```text
vle32.v v0, (a1)
vfmacc.vf v3, fa0, v0
vse32.v v3, (a2)
```

这些 vector 指令之间的向量数据依赖由 Ara 负责。HDV 的职责是按顺序把 request 送进去。

### 7.3 Vector 指令的 Scalar Operand 依赖

Vector 指令仍可能需要标量寄存器值：

- vector load/store base: `rs1`
- vector-scalar arithmetic: `rs1` 或 `frs1`
- `vsetvli`: AVL、vtype immediate 等

当前有两种模式：

- vtrace 模式：operand 来自 vtrace 文件，普通 vector EP 入队后即可 acknowledged。
- 真实标量模式：operand 来自 `hdv_scalar_backend` 的 XRF/FRF operand service。

真实标量模式下，vector dispatch 不能在 EP 入队时立即 acknowledged。原因是：

- 如果 vector request 还没读取 scalar operand；
- HEU 又提前推进后续 scalar EP；
- 后续 scalar EP 可能更新 a0/a1/a2/fa0 等寄存器；
- 则旧 vector 指令可能读到新值。

因此当前真实标量模式的规则是：

- 普通 vector EP 要等本 EP 所有 vector slot 都已经被 vector dispatch FSM 消费，也就是 request 已经直接发给 Ara 或带着 scalar operand snapshot 进入 resolved command window 后，才向 HEU acknowledged。
- 含 `vset rd!=x0` 的 EP 还要等 Ara response，把 granted VL 写回标量后端。

这个规则保证正确性。当前 `hdv_top` 默认 `VectorCmdWindowDepth=8`，并传给 `hdv_vec_dispatch_unit.CmdWindowDepth`；该窗口能解耦短期 Ara backpressure。但 vector dispatch 仍需要先逐条选择 slot、读取 operand、写入 request buffer，这部分延迟仍在 EP acknowledged 路径上。

### 7.4 vset 的特殊依赖

`vsetvli/vsetivli/vsetvl` 当前被分类为 vector 指令，送入 Ara。

特殊点：

- `vset` 会改变 VL/VTYPE。
- 如果 `rd != x0`，Ara response 会返回 granted VL，需要写回标量寄存器 `rd`。
- 后续标量指令可能读取这个 `rd`，例如 `sub a0,a0,t0`。

因此含 `vset rd!=x0` 的 vector EP 不能只等 request 被 Ara 接收，还必须等 response 回来并写回 scalar backend 后才能 acknowledged。

当前 vector dispatch 使用 response metadata 记录：

```text
{wb_valid, is_fpr, is_vset, is_store, rd, ep_id}
```

response 回来后根据 metadata 判断是否产生 `vec_scalar_wb_valid_o`。其中 `is_vset` 用于 granted VL 写回和 vset acknowledged 等待；`is_fpr` 告诉 scalar backend 写 FRF 还是 XRF；`is_store` 参与 `vec_store_inflight_o`，用于标量后端保守处理 vector store 与后续标量 memory op 的顺序。

## 8. 标量与向量之间的跨 EP 依赖

当前 HDV 的主要正确性模型是 EP 间保序。

对于不同 EP：

- 如果 EP1 的标量写回被 EP2 使用，必须等 EP1 scalar done 后才能推进 EP2。
- 如果 EP1 的 `vset rd` 写回被 EP2 使用，必须等 EP1 vector acknowledged 后才能推进 EP2。
- 如果 EP2 的 vector 指令需要读取 EP1 scalar 写出的地址/标量值，也依赖 EP acknowledged 顺序保护。

因此当前设计简单但保守：

```text
EP N scalar/vector slice 都 done/acknowledged
  -> HEU 才认为 EP N 完成
  -> EP N+1 才成为 current EP
```

这避免了完整 scoreboard，但也限制了跨 EP 重叠。

## 9. 同 EP 内标量/向量并行关系

同 EP 内可以同时包含 scalar 和 vector 指令。设计意图是：这些指令之间没有 HDV 必须处理的数据依赖。

例如可以同 EP：

```text
vle32.v v3, (a2)
slli t1, t0, 2
```

前提是：

- `vle32.v` 使用的 `a2` 是旧值；
- `slli` 写的 `t1` 不被同 EP 内 vector 指令读取；
- 或者这些依赖已经由软件和 p-bit/dep-break 确认不存在。

当前真实实现中：

- HEU 会同时向 scalar 后端和 vector dispatch 发 valid。
- 标量后端尝试最多 3 发射：2 条 simple ALU + 1 条 complex lane；遇到同周期 hazard/order barrier 时保守拆开。
- vector dispatch 顺序送 vector slots。
- HEU 要等两个 slice 都 done/acknowledged 后才推进 EP。

所以同 EP 的 scalar/vector 可以并行启动，但 EP 完成仍受较慢一侧限制。

## 10. 分支、Loop Lock 和取指依赖

### 10.1 Branch 边界

Branch 是 EP 硬边界。VLIWPU 不应把 branch 后面的 fall-through 指令和 branch 打进同一个 EP。

Branch 执行后：

- not taken：顺序继续。
- taken：标量后端产生 redirect。
- redirect flush IPU/VLIWPU/HEU/vector dispatch 的旧状态。

### 10.2 Redirect 对 IPU 的影响

IPU 收到 redirect 后，从 redirect target 重新取 fetch packet。当前设计要求 target 是 packet/EP 起点，通常 16B 对齐。

这样可以避免支持“跳进 EP 中间”的复杂逻辑：

- VLIWPU 从 slot0 或明确入口开始重新打包。
- carry buffer 被清空。
- HEU/vector dispatch 中旧指令被 flush。

### 10.3 Loop Lock

当前有自动 loop lock/双 buffer 取指机制，用于减少小循环反复取指。

基本思想：

- IPU 双 buffer 预取顺序 packet。
- 后向 branch taken 且 target 命中 active buffer 时，可以进入 auto loop lock。
- loop lock 期间从 active buffer replay，减少重复 SRAM/AXI 取指。
- 最后一轮 not taken 时，通过 branch resolved/loop exit 信息退出 lock，继续顺序后继。

Loop lock 只优化取指，不改变 EP 依赖语义。

## 11. 当前性能瓶颈和已知限制

### 11.1 当前正确性依赖于 EP 保序

HDV 当前没有完整跨 EP scoreboard。因此不要随意提前发射跨 EP 标量指令，也不要让后续 scalar EP 在前序 vector EP 尚未捕获 operand/vset 写回前修改寄存器。

### 11.2 Scalar EP 内并行能力仍有限

当前 `hdv_scalar_backend` 已经不是单发射：它有 2 条 simple ALU lane 和 1 条 complex lane，适合覆盖 Ara benchmark 中常见的“两个指针/计数 ALU 更新 + 一个 branch/LSU/FPU/MUL”的组合。

但它仍不是完整 superscalar core：

- simple lane 只覆盖简单整数 ALU 类。
- branch/CSR/MULT/FPU/LSU 等仍集中在 complex lane。
- 同周期 hazard 检查是轻量级的，不是完整 scoreboard。
- 如果一个 EP 内有 3 条以上简单标量指令，或多条都需要 complex lane，仍会拆成多周期。

可优化方向：

- 增加 simple ALU lane 或写端口前，先用 dump/EP 统计确认实际收益。
- 给常见地址更新路径做更明确的 lane 绑定。
- LSU/branch/CSR 仍需单独仲裁。

### 11.3 Vector Accepted 仍受 Operand 捕获约束

真实标量模式下，vector acknowledged 必须等 request 消耗 scalar operand。当前已有参数化 resolved command window，默认深度为 8，能够在 Ara `req_ready=0` 时保存已经抓好 operand 的 request，降低 Ara backpressure 对前端的影响。

但 acknowledged 仍需要等 EP 内每条 vector slot 被 dispatch FSM 处理过，因此剩余优化方向是：

- 扩大或重构 vector dispatch 内的 operand snapshot / request FIFO。
- 更早、更批量地读取并保存每条 vector 指令所需的 rs1/rs2/frs1。
- 一旦 operand snapshot 完成，就可以向 HEU acknowledged。
- 后续 Ara request 使用 snapshot，而不是实时读标量寄存器。

这样才能让后续 scalar EP 提前更新寄存器，同时旧 vector request 仍使用旧 operand。

### 11.4 Buffered Vector Early Issue 当前已打开

当前 `hdv_top` 打开了 HEU 的 buffered vector early issue。它允许下一 EP 的 vector slice 在满足依赖检查时提前进入 vector dispatch，从而减少 Ara 前端空泡。

当前必须满足：

- vector dispatch 能保存每条 vector 指令的 operand snapshot。
- acknowledged-id/tag 不会错配 current/buffered EP。
- 不跨越未解析 control-flow (`current_has_branch_q`)。
- **不跨越 memory-ordering 边界 (`current_has_scalar_mem_order_q`)：current EP 含标量访存/FENCE/SYSTEM/AMO 时，buffered vector early issue 被阻塞。**
- 不破坏 Ara request program order。
- current scalar 写寄存器、current vector/vset 配置与 buffered vector 不冲突。

## 12. 当前可依赖的核心规则

调试和写 HDV 程序时，可以按以下规则理解当前系统：

1. HINT p-bit 控制”能否继续打包”，但不能越过硬件边界（**FENCE 已归类为 SYSTEM，是 EP 硬边界**）。
2. EP 是当前 HDV 的主要依赖边界。
3. 同 EP 内指令应由软件/编译器保证无需要 HDV 处理的数据依赖。
4. 不同 EP 之间默认保序，但 HEU 可以在安全检查通过时提前发送 buffered EP 的 vector slice。
5. 标量后端在 scalar slice 执行和写回完成后 `scalar_ep_done_o`，EP 内最多 2 simple ALU + 1 complex lane。
6. 向量后端按 slot 顺序送 Ara，向量内部依赖交给 Ara。
7. 真实标量模式下，`vec_ep_acknowledged_o` 承担”scalar operand 已被安全读取”的含义（**不代表向量执行完成**）。
8. `vset rd!=x0` 必须等 response 写回标量后端后 acknowledged。
9. **Loop control 完全由 scalar backend 的 `branch_resolved_valid` 精确事件驱动，`hdv_top` 不再做 dispatch 阶段 branch opcode 重解码。**
10. **Memory-ordering：current EP 含标量 load/store/FENCE/AMO/CSR 时，buffered EP 的 vector slice 不能 early issue（保守策略）。后续可通过 noalias 或地址分析放宽。**
11. **Task-end：支持 `ret` (兼容) 和 `ebreak` (推荐) 两种 task completion 机制，通过 `TreatRetAsTaskExit` / `TreatEbreakAsTaskExit` 参数控制。**
9. Branch 是强边界，taken redirect 会 flush 后续旧状态。
10. Loop lock 只减少取指，不改变指令依赖和 EP 保序。
