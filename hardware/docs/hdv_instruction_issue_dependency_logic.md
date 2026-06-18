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
  -> cva6_hdv_scalar_backend
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
- 同一 EP 内多条 scalar 指令当前在 `cva6_hdv_scalar_backend` 内最多 3 发射：两个 simple ALU lane 加一个 complex lane。不能并行的标量指令仍会在后端内部等待。
- 不同 EP 之间当前靠 HEU pending/accepted、buffer EP 和 buffered vector early issue 的安全检查协调。

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
scalar_heu_accepted_i
vector_heu_accepted_i
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

HEU 产生一拍 `heu_top_ep_accepted_o`，表示这个 EP 从 HDV 依赖角度已经被后端安全接管。

注意：`ep_accepted` 不是“所有指令执行退休”。它只是 HDV 前端允许推进到下一个 EP 的同步点。

### 5.3 HEU Skid Buffer

当前 HEU 允许：

- 一个 current EP 正在等待后端 accepted。
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

当前真实标量后端是 `cva6_hdv_scalar_backend`。它不是完整 CVA6 core，而是复用 CVA6 decoder/ALU/branch/mult/FPU 部件的 HDV 专用标量后端。

### 6.1 EP 内标量执行

标量后端接收一个 scalar slice 后：

1. 锁存该 EP 的 scalar slots。
2. 解压 RVC，使用 CVA6 decoder 分类。
3. 尝试每周期发射最多 3 条标量指令。
4. 两条 simple ALU lane 处理 LUI/AUIPC/OP-IMM/OP-IMM-32/OP/OP-32 这类简单整数指令。
5. 一条 complex lane 处理 branch/jal/jalr/CSR/MULT/FPU/LSU/复杂或有序指令。
6. 写回 XRF/FRF/CSR stub，所有 scalar slots 处理完后拉 `scalar_accepted_o`。

后端会做本周期 simple batch 内的读写 mask、重复 rd、order barrier、vset RAW、complex 读 simple 写等检查。能并行的标量指令同周期发射；不能并行的留到后续周期，保证功能正确。

### 6.2 标量寄存器依赖

当前没有完整 scoreboard，也没有乱序 commit。依赖正确性主要来自：

- VLIWPU/软件 p-bit/dep-break 尽量不把有依赖的标量指令打进同一个 EP。
- 标量后端仍有 EP 内基本 hazard 检查，避免明显 RAW/WAW/order 问题在多发射 lane 中出错。
- 不同 EP 之间由 HEU 等 `scalar_accepted` 和 `vector_accepted` 保序；在 buffered vector early issue 下，HEU 只提前满足依赖 mask 的 vector slice。
- 标量后端在 scalar slice 所有写回完成后才 accepted。

因此，如果 EP 间有 RAW 依赖，例如：

```text
EP1: vsetvli t0, a0, ...
EP2: sub a0, a0, t0
```

则 EP2 的标量读取应发生在 EP1 的相关写回被 accepted 规则保护之后。

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

- vtrace 模式：operand 来自 vtrace 文件，普通 vector EP 入队后即可 accepted。
- 真实标量模式：operand 来自 `cva6_hdv_scalar_backend` 的 XRF/FRF operand service。

真实标量模式下，vector dispatch 不能在 EP 入队时立即 accepted。原因是：

- 如果 vector request 还没读取 scalar operand；
- HEU 又提前推进后续 scalar EP；
- 后续 scalar EP 可能更新 a0/a1/a2/fa0 等寄存器；
- 则旧 vector 指令可能读到新值。

因此当前真实标量模式的规则是：

- 普通 vector EP 要等本 EP 所有 vector slot 都已经被 vector dispatch FSM 消费，也就是 request 已经直接发给 Ara 或带着 scalar operand snapshot 进入 resolved command window 后，才向 HEU accepted。
- 含 `vset rd!=x0` 的 EP 还要等 Ara response，把 granted VL 写回标量后端。

这个规则保证正确性。当前 command window 默认深度为 4，能解耦短期 Ara backpressure；但 vector dispatch 仍需要先逐条选择 slot、读取 operand、写入 request buffer，这部分延迟仍在 EP accepted 路径上。

### 7.4 vset 的特殊依赖

`vsetvli/vsetivli/vsetvl` 当前被分类为 vector 指令，送入 Ara。

特殊点：

- `vset` 会改变 VL/VTYPE。
- 如果 `rd != x0`，Ara response 会返回 granted VL，需要写回标量寄存器 `rd`。
- 后续标量指令可能读取这个 `rd`，例如 `sub a0,a0,t0`。

因此含 `vset rd!=x0` 的 vector EP 不能只等 request 被 Ara 接收，还必须等 response 回来并写回 scalar backend 后才能 accepted。

当前 vector dispatch 使用 response metadata 记录：

```text
{wb_valid, is_fpr, is_vset, is_store, rd, ep_id}
```

response 回来后根据 metadata 判断是否产生 `vec_scalar_wb_valid_o`。其中 `is_vset` 用于 granted VL 写回和 vset accepted 等待；`is_fpr` 告诉 scalar backend 写 FRF 还是 XRF；`is_store` 参与 `vec_scalar_store_pending_o`，用于标量后端保守处理 vector store 与后续标量 memory op 的顺序。

## 8. 标量与向量之间的跨 EP 依赖

当前 HDV 的主要正确性模型是 EP 间保序。

对于不同 EP：

- 如果 EP1 的标量写回被 EP2 使用，必须等 EP1 scalar accepted 后才能推进 EP2。
- 如果 EP1 的 `vset rd` 写回被 EP2 使用，必须等 EP1 vector accepted 后才能推进 EP2。
- 如果 EP2 的 vector 指令需要读取 EP1 scalar 写出的地址/标量值，也依赖 EP accepted 顺序保护。

因此当前设计简单但保守：

```text
EP N scalar/vector slice 都 accepted
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
- HEU 要等两个 slice 都 accepted 后才推进 EP。

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

当前 `cva6_hdv_scalar_backend` 已经不是单发射：它有 2 条 simple ALU lane 和 1 条 complex lane，适合覆盖 Ara benchmark 中常见的“两个指针/计数 ALU 更新 + 一个 branch/LSU/FPU/MUL”的组合。

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

真实标量模式下，vector accepted 必须等 request 消耗 scalar operand。当前已有参数化 resolved command window，默认深度为 4，能够在 Ara `req_ready=0` 时保存已经抓好 operand 的 request，降低 Ara backpressure 对前端的影响。

但 accepted 仍需要等 EP 内每条 vector slot 被 dispatch FSM 处理过，因此剩余优化方向是：

- 扩大或重构 vector dispatch 内的 operand snapshot / request FIFO。
- 更早、更批量地读取并保存每条 vector 指令所需的 rs1/rs2/frs1。
- 一旦 operand snapshot 完成，就可以向 HEU accepted。
- 后续 Ara request 使用 snapshot，而不是实时读标量寄存器。

这样才能让后续 scalar EP 提前更新寄存器，同时旧 vector request 仍使用旧 operand。

### 11.4 Buffered Vector Early Issue 当前已打开

当前 `hdv_top` 打开了 HEU 的 buffered vector early issue。它允许下一 EP 的 vector slice 在满足依赖检查时提前进入 vector dispatch，从而减少 Ara 前端空泡。

当前必须满足：

- vector dispatch 能保存每条 vector 指令的 operand snapshot。
- accepted-id/tag 不会错配 current/buffered EP。
- 不跨越未解析 control-flow。
- 不破坏 Ara request program order。
- current scalar 写寄存器、current vector/vset 配置与 buffered vector 不冲突。

## 12. 当前可依赖的核心规则

调试和写 HDV 程序时，可以按以下规则理解当前系统：

1. HINT p-bit 控制“能否继续打包”，但不能越过硬件边界。
2. EP 是当前 HDV 的主要依赖边界。
3. 同 EP 内指令应由软件/编译器保证无需要 HDV 处理的数据依赖。
4. 不同 EP 之间默认保序，但 HEU 可以在安全检查通过时提前发送 buffered EP 的 vector slice。
5. 标量后端在 scalar slice 执行和写回完成后 accepted，EP 内最多 2 simple ALU + 1 complex lane。
6. 向量后端按 slot 顺序送 Ara，向量内部依赖交给 Ara。
7. 真实标量模式下，vector accepted 还承担“scalar operand 已被安全读取”的含义。
8. `vset rd!=x0` 必须等 response 写回标量后端后 accepted。
9. Branch 是强边界，taken redirect 会 flush 后续旧状态。
10. Loop lock 只减少取指，不改变指令依赖和 EP 保序。
