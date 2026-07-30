# HDV Hardware Design Guide

本文档是当前 `ara_hdv` 分支中 HDV 硬件设计的统一说明。它合并并替代以下旧文档：

- `hdv_full_mechanism_tutorial.md`
- `hdv_modules_code_walkthrough.md`
- `prefetch_config.md`
- `hdv_scalar_backend_comparison.md`
- `hdv_scalar_ep_demand_analysis.md`
- `hdv_scalar_backend_bug_review_and_roadmap.md`

旧文档中仍有价值的机制解释已经吸收并按当前 RTL 重写。本文以当前 `hardware/src/` 为准，重点说明设计思想、模块逻辑、握手语义、正确性边界和可观测计数器。

## 1. 设计目标与全局语义

HDV 的目标不是替代 Ara 的 RVV 后端，也不是把后端做成静态 VLIW 执行器。当前设计把传统标量核逐条驱动 RVV 指令的方式改成 task-level 本地执行：host 提交一个向量 kernel 任务后，HDV 本地前端负责取指、循环 replay、execute packet 形成、标量/向量分流和向量请求适配；Ara 后端仍然负责真实 RVV 指令解码、发射、lane 执行、寄存器相关性、访存顺序和响应。

全局数据流如下：

```text
host/task driver
  -> hdv_task_interface_unit
  -> hdv_task_schedule_unit
  -> hdv_instruction_prefetch_unit
  -> hdv_vliw_pack_unit
  -> hdv_hybrid_execution_unit
       -> hdv_scalar_backend
       -> hdv_vec_dispatch_unit
            -> ara_dispatcher
            -> ara_sequencer
            -> Ara lanes/VLSU
```

几个语义必须先区分清楚：

- `task done`：整个 HDV task 结束。当前顶层会等 scalar task-complete 事件出现，并且 vector dispatch 中还在等待的请求/响应排空后，再把 task done 传给 TSU/TIU。
- `scalar_ep_done`：一个 EP 的 scalar slice 已经在 `hdv_scalar_backend` 中执行完，并且标量寄存器/状态更新完成。
- `vec_ep_acknowledged`：一个 EP 的 vector slice 已到达前端可推进的安全点。真实标量模式下，它表示该 EP 所有 vector request 需要的标量操作数已经被捕获到 request 或 command window；如果该 EP 含 `vset* rd!=x0`，还必须等待 granted VL 写回标量后端。
- `heu_top_ep_acknowledged`：HEU 看到 scalar slice done 且 vector slice acknowledged 后，对整个 EP 产生的前端推进事件。它不表示 Ara 中的普通向量指令已经完成。
- `hdv_meta`：随每条 Ara vector request 进入后端的 HDV 语义，包括 `hdv_valid`、`ep_id`、`prefetch_hint_valid`、`prefetch_disable`、`prefetch_mode`。

HDV 的基本原则是：前端提供 packet/loop/prefetch 语义，后端保留跨 EP 的动态正确性管理。软件 hint 和 EP metadata 会减少不必要的保守等待，但同一个 EP 内被软件声明为可并行的指令必须满足更强的软件约束：不能把真实 RAW/WAR/WAW、标量操作数版本依赖或必须保序的 memory 关系放进同一个 EP 后再依赖后端自动串行化。

### 1.1 一条 EP 在硬件中的生命周期

把 HDV 当成“host 把整个 kernel 交给本地前端执行”还不够细。真正的最小工作单元是 VLIWPU 形成的 execute packet。一次典型 EP 的路径如下：

1. IPU 从本地 instruction buffer 中取出 128-bit fetch packet，并用 ready/valid 送给 VLIWPU。
2. VLIWPU 解析 header，按 p-bit、control boundary、dependency break 和 issue width 形成一个 EP。EP 中的 slot 仍保留原始 PC、32-bit/continuation 信息和 `SCALAR/VECTOR/BRANCH/SYSTEM` 分类。
3. HEU 接收 EP 后，不执行指令本身，只做拆分：vector slot 进入 VDU，其他 slot 进入标量后端。HEU 同时为 vector slice 分配 1-bit `ep_id`。
4. 标量后端按 EP 内 slot 执行 scalar slice。simple ALU 可以 batch 执行，复杂指令走 mult/FPU/LSU/branch 路径。它完成后拉 `scalar_ep_done`。
5. VDU 逐条处理 vector slice，把每条 RVV 指令变成 Ara accelerator request。需要标量操作数的指令先从标量后端 snapshot rs1/rs2/frs1，再进入 command window 或直发 Ara。
6. VDU 不等普通 vector 指令真正执行完才 acknowledge EP。它只等该 EP 的所有 vector request 都已经捕获必要操作数；若含 `vset rd!=x0`，还要等 granted VL 写回标量后端。
7. HEU 同时看到 `scalar_ep_done` 和 `vec_ep_acknowledged` 后，对该 EP 产生 `heu_top_ep_acknowledged`，VLIWPU/IPU 可以继续推进前端流。
8. Ara 后端继续真实执行已经收到的 vector request，包括 sequencer hazard、lane issue、VLSU demand/prefetch 和 response。

因此，HDV 的“前端推进完成”和“Ara 执行完成”不是同一个时间点。这个设计允许前端快速进入下一 EP，同时把真实向量相关性留给 Ara 后端处理。

### 1.2 三条保序边界

当前 RTL 里最重要的正确性边界有三条：

- **标量状态边界**：标量后端只有在 scalar slice 写回 XRF/FRF/CSR stub 后才返回 `scalar_ep_done`。后续需要这些寄存器的 vector operand snapshot 不应读取旧值。
- **vector operand 边界**：VDU acknowledge 的条件是 operand 已被 snapshot 到 request/window，或不需要 scalar operand。acknowledge 不是 vector retirement，但它保证后续标量修改不会影响已经形成的 vector request。
- **访存顺序边界**：Ara 内部仍维护 vector memory 顺序；HDV 标量后端额外用 `vec_store_inflight` 阻止标量访存越过未完成 vector store。VLSU prefetch 只能命中并替代 demand load，不能改变 demand 可见顺序。

### 1.3 EP 内依赖责任边界

EP 是 HDV 利用局部并行性的单位，不是一个小型乱序窗口。硬件会保护以下边界：

- 不跨 unresolved branch/control 继续接收或提前发射后续 EP。
- 不让 buffered vector 读取 current scalar slice 尚未写回的 GPR/FRF。
- 不让后续标量 load/store 越过仍在飞的 vector store。
- 不让后续标量指令在 `vset rd!=x0` 写回前读取旧 granted VL。
- 不让跨 EP 的 Ara vector RAW/WAR/WAW hazard 被 same-EP 规则裁掉。

但同一个 EP 内的软件承诺会被硬件相信：

- 同 EP 内两条 vector 指令若存在真实 RAW/WAR/WAW，必须用 p-bit 或 packet 边界拆成不同 EP。当前 sequencer 看到相同有效 `ep_id` 后，会把该 running instruction 从 RAW/WAR/WAW hazard 候选中裁掉。
- 同 EP 内 scalar 指令写某个 GPR/FRF，而 vector 指令把该寄存器作为 base/stride/scalar operand 读取时，VDU snapshot 到的是它消费该 vector slot 时寄存器文件中的值，不保证自动等待同 EP scalar 写回。若想读取新值，必须拆 EP；若放在同 EP，软件应明确这是读取旧值。
- 同 EP 内 `vset rd!=x0` 写标量寄存器，而 scalar 指令读取该 `rd` 时，也必须拆 EP。RTL 的 `vset` interlock保护的是后续 EP/后续标量执行读取旧值，不把同 EP scalar slice 改造成等待 vector response 的细粒度流水。
- 同 EP 内 scalar memory 与 vector memory 没有通用的逐指令保序语义。需要确定顺序时应拆 EP，或让 HEU 的 branch/memory-order 边界自然阻止重叠。

因此，p-bit/cross/packet256 的语义应理解为“软件证明这些 slot 可以作为一个并行 packet 交给硬件”，而不是“硬件会在同 EP 内重新发现并修复所有真实依赖”。

### 1.4 memory 操作正确性保证

HDV 里有三类 memory master：IPU instruction fetch、`hdv_scalar_backend` 标量 LSU、Ara VLSU。它们最终经过顶层 system AXI mux 进入同一个 memory system，但正确性不依赖 mux 自己猜顺序，而依赖明确的前端互锁和 VLSU 内部顺序规则。

**标量 LSU 自身顺序**：

- 标量 load 在 `LSU_AR` 状态下可以对 EP 内连续 load 连续发 AR，但每个 load 都按发出顺序进入 load queue。
- AXI R 返回按 queue head 写回 XRF/FRF；标量后端只有在连续 load 都发完且 load queue drain 后才离开 `LSU_AR`。
- 标量 store 不做多 outstanding queue，而是按 `LSU_AW -> LSU_W -> LSU_B` 完成一个 store 后再推进，选择更保守的顺序语义。

**vector memory 自身顺序**：

- 向量 load/store 进入 Ara 后，仍由 Ara dispatcher、sequencer、VLSU 和 lane pipeline 处理。HDV metadata 不改变普通 RVV memory 指令的解码、异常、lane 写回和 VLSU 队列规则。
- same-EP hazard bypass 只裁剪 sequencer 的寄存器 hazard 候选，不让请求绕过 VLSU 的 load/store 接收条件、store data path、addrgen ack 或 lane/operand queue ready。
- VLSU 内部仍以 descriptor/queue 维护 load/store 请求和返回数据归属；HDV prefetch 只在 load path 上作为 demand 的可替代数据来源，不创建新的 architecturally visible memory operation。

**scalar 和 vector memory 的相对顺序**：

- HEU 发现 current EP 的 scalar slice 含 load/store/FENCE/AMO/FP memory 或压缩未知指令时，会置 `current_has_scalar_mem_order`。该标记会阻止 buffered EP 的 vector slice early issue，避免后一 EP 的 vector memory 越过当前 EP 的 scalar memory。
- VDU 的 `vec_store_inflight_o` 覆盖两种情况：已经送入 Ara 但 response metadata 尚未返回的 vector store，以及还停在 VDU command window 中尚未送入 Ara 的 vector store。标量后端看到该信号后，不发新的 scalar load/store。
- 因此，后续 scalar memory 不会越过已形成或正在形成的 vector store。这是当前最重要的 vector-store 到 scalar-memory 保守互锁。
- 反过来，若程序需要 scalar memory 完成后再允许 vector memory 访问，应把它们放入不同 EP，并让 HEU 的 scalar memory-order 标记阻止后续 vector early issue；不要把必须保序的 scalar/vector memory 放入同一个 EP 里依赖隐式顺序。

**prefetch 的正确性边界**：

- Prefetch 只来源于带有效 hint 且未显式关闭的 unit-stride load。它不会服务 store，也不会改变 store 可见顺序。
- Demand AR 优先于 prefetch AR。只要当前 demand 能发，prefetch 不会抢占地址通道。
- 当前 prefetch 与 demand 共用 `AXI_ID_DEMAND`，addrgen 在 AR 接受时压入 burst tag，vldu 按 same-id 返回顺序 pop tag。这样返回数据属于 demand 还是 prefetch 由 tag 决定，不靠猜测。
- Demand 命中 prefetch 的条件是 demand 地址匹配 lookup FIFO head。若同地址 prefetch 已经进入 ROB/in-flight/return path，或者处在 page-cross 第一段已可消费但第二段仍需对齐的等待路径，demand 可以短暂等待其变成 lookup hit。单纯还停在 prefetch AR queue 里的同地址请求不会阻塞 demand；如果它太晚，demand 会按普通 AR 发出，后续 stale prefetch 由 stream-break/flush 清理。
- 如果 demand stream 和 lookup head 不一致，addrgen 进入 stream-break recovery：停止新 prefetch，等待 prefetch ROB/in-flight beat 排空，然后 flush lookup FIFO 和 vldu prefetch buffer。错误或过远的 prefetch 最多浪费带宽，不会被错误消费为 demand 数据。
- Demand 等待 in-flight pending prefetch 有 watchdog。若等待过长会 fatal，避免把 prefetch miss/乱序问题伪装成无限等待。

所以，memory 正确性的核心是“demand 可见顺序仍由原 VLSU/标量 LSU 执行，HDV 只允许安全提前形成请求；prefetch 只能在地址精确匹配时替代同一个 demand load，否则必须退回 demand-driven 或 flush”。性能 hint 不能成为正确性条件。

### 1.5 一轮 loop 中各模块如何协同

下面用一个常见流式 loop 解释 HDV 的真实执行语义。假设软件希望每轮做：

```asm
vsetvli t0, a0, e32, m1, ta, ma
vle32.v v0, (a1)
vle32.v v1, (a2)
vfmacc.vf v1, fa0, v0
vse32.v v1, (a2)
slli t1, t0, 2
add  a1, a1, t1
add  a2, a2, t1
sub  a0, a0, t0
bnez a0, loop
```

HDV 不把这段代码变成一个后端乱序窗口。它做的是把代码拆成若干 EP，让每个 EP 在正确性边界内尽快交给两个后端：

1. IPU 提供 fetch packet。若 loop 已经进入 replay，IPU 可以从本地 buffer 重新服务 loop body，不再每轮访问 instruction memory。
2. VLIWPU 看 header、p-bit、packet256/cross 和控制边界，形成一个 EP。例如 `vle32.v v0` 和 `vle32.v v1` 可以在软件确认没有非法依赖时放进同一 EP。
3. HEU 把同一个 EP 拆成 scalar slice 和 vector slice。vector slice 获得一个 `ep_id`；scalar slice 送往 `hdv_scalar_backend`。
4. Scalar backend 执行本 EP 的标量指令，更新 XRF/FRF，处理 branch，并在标量 slice 全部完成后返回 `scalar_ep_done`。
5. VDU 处理 vector slice。对 load/store，它会向 scalar backend 读取 base pointer 并 snapshot；对 OPFVF，它 snapshot `fa0`；对 `vsetvli`，它记录这条指令可能产生 scalar-visible `vl` 写回。
6. VDU 把已经 resolved 的 vector request 放入 command window 或直接送 Ara。此时普通 vector 指令还没有执行完，但它们需要的 scalar operand 已经固定。
7. Ara dispatcher/sequencer/VLSU 按原 RVV 后端规则继续执行这些 request。HDV metadata 只作为 sideband 告诉 sequencer/VLSU 这些 request 属于哪个 EP、有没有 prefetch hint。
8. 当 VDU 已经消费完该 EP 的所有 vector slot，并且必要的 `vset rd!=x0` 写回也完成后，它返回 `vec_ep_acknowledged`。这个事件只表示“前端可以继续推进”，不是 vector retirement。
9. HEU 等到 `scalar_ep_done` 和 `vec_ep_acknowledged` 都满足，才向 VLIWPU/IPU acknowledge 这个 EP。如果 buffer 里已有下一 EP，会把 buffered EP 提升为 current。
10. 如果 current scalar slice 因 load、branch 或复杂指令卡住，而 buffered EP 的 vector slice 与 current 没有标量寄存器/memory-order 冲突，HEU 可以提前把 buffered vector 发给 VDU，让 Ara 不空转。

这个流程的重点是：HDV 的并行来自“前端交付和后端执行解耦”，不是来自随意重排程序语义。标量寄存器版本由 scalar done 与 operand snapshot 保证；vector register 依赖由 EP 语义和 Ara sequencer 边界共同约束；memory 顺序由 HEU memory-order、VDU store inflight、VLSU demand/prefetch 规则共同保证。

### 1.6 正确性速查表

| 场景 | 当前 RTL 如何保证 | 软件/文档应如何理解 |
|---|---|---|
| scalar -> scalar 依赖 | `hdv_scalar_backend` 内 simple batch RAW/WAW 检查、complex lane 顺序和 `complex_simple_raw_stall` | 同一 scalar slice 内不是任意乱序，复杂指令仍保持保守顺序 |
| scalar 写 GPR/FRF，后续 EP vector 读该寄存器 | HEU 只有在 current scalar done 后才整体 acknowledge；buffered vector early issue 会检查 current scalar write mask | 跨 EP 的 scalar-to-vector operand 版本由硬件保护 |
| scalar 写 GPR/FRF，同 EP vector 读该寄存器 | 没有同 EP 自动等待；VDU 在消费 vector slot 时 snapshot 当前寄存器文件值 | 若要读新值必须切 EP；同 EP 只能在软件确认读旧值或无关时使用 |
| `vset rd!=x0` 后 scalar 读 `rd` | VDU 输出 vset inflight，scalar backend 检查 `vec_vset_inflight_rd` | 后续 EP/后续 scalar 读 granted VL 有保护；同 EP 内仍应切开 |
| vector -> vector 跨 EP RAW/WAR/WAW | 不同 `ep_id` 或无 HDV metadata 时，Ara 原 hazard 逻辑生效 | 跨 EP 依赖仍由 Ara 后端保护 |
| vector -> vector 同 EP RAW/WAR/WAW | sequencer same-EP 裁剪 RAW/WAR/WAW 候选 | 同 EP 必须是软件证明可并行；真实需要串行就切 EP |
| current scalar memory -> buffered vector memory | HEU `current_has_scalar_mem_order` 阻止 buffered vector early issue | 需要 scalar memory 先发生时，把后续 vector memory 放到后一 EP |
| vector store -> 后续 scalar load/store | VDU `vec_store_inflight_o` 覆盖 command window 和 response metadata 中的 store，scalar LSU 等待 | 后续 scalar memory 不会越过已经形成的 vector store |
| vector load prefetch 命中 | addrgen 地址匹配 lookup head，demand AR 被同地址 prefetch 数据替代 | prefetch 只优化同一个 demand load，不改变程序可见语义 |
| prefetch 失配/过远 | stream-break drain 后 flush lookup/buffer，或者退回普通 demand AR | prefetch 错了最多损性能，不应产生错误数据 |
| branch/ret/control | VLIWPU 把 BRANCH/SYSTEM 作为硬边界；HEU 不跨 unresolved branch 接收/提前发射 | branch target 应是合法 EP 起点，不要跳入 EP 中间 |

如果要判断一个 kernel hint 是否安全，可以按这张表逐项检查：同 EP 内没有真实 vector 串行依赖；同 EP 内没有必须读新值的 scalar-to-vector 关系；必须保序的 scalar/vector memory 被拆到不同 EP；`vset rd` 的消费者不在同 EP 内；prefetch mode 只影响性能，不参与功能正确性。

## 2. HDV 端到端流水线

这一章把 HDV 当成一条完整流水线来讲，而不是按 RTL 文件孤立讲。画 SEAM-V 总体框图时，可以直接把下面的 stage 画成主数据流，再把 scalar slice、vector slice、metadata、prefetch 画成旁路/协同路径。

HDV 的主线是：

```text
S0 Host task accept
  -> S1 Task schedule
  -> S2 Local instruction supply
  -> S3 EP formation
  -> S4 Hybrid EP split
       -> S5 Scalar slice execution
       -> S6 Vector request resolution
            -> S7 Ara semantic consumption
            -> S8 Vector execution / VLSU prefetch
  -> S9 Drain and task completion
```

更具体地说，HDV 同时有三条相互配合的流：

- **control/task stream**：host 写 CSR，TIU/TSU 建立 active task，task complete/drain 后返回 done/error。
- **instruction/EP stream**：IPU 本地供给 fetch packet，VLIWPU 形成 EP，HEU 决定前端能否推进。
- **execution/request stream**：HEU 把 EP 拆成 scalar slice 和 vector slice；scalar backend 执行标量控制和地址更新；VDU 把 vector slice 解析成 Ara request；Ara/VLSU 执行真实 RVV 工作。

这三条流的核心同步点不是“每条 vector 指令完成”，而是 **EP 的前端安全推进点**。HDV 通过 `scalar_ep_done`、`vec_ep_acknowledged`、`heu_top_ep_acknowledged` 把标量版本、vector operand snapshot 和前端推进绑定起来。

从画框图和讲课角度，可以先记住下面这张总表，再进入每一级的细节：

| Stage | 主要模块 | 本级输入 | 本级产物 | 关键反压/正确性点 |
|---|---|---|---|---|
| S0 Host task accept | TIU | host CSR start/address | pending task、status | pending task 未被 TSU 接收时不能覆盖 |
| S1 Task schedule | TSU | pending task、task done/error | single active task | 同一时间只允许一个 active task 占用 HDV 前端状态 |
| S2 Local instruction supply | IPU | task PC、AXI instruction data、redirect | 128-bit fetch packet、loop replay | VLIWPU not-ready 时 packet 不前进；redirect 只改变取指流 |
| S3 EP formation | VLIWPU | fetch packet、header、p-bit、hint | execute packet、slot class、EP hint | branch/system/width/p-bit/packet 边界决定 EP 切分 |
| S4 Hybrid EP split | HEU | execute packet、scalar/vector ready/ack | scalar slice、vector slice、`ep_id` | current/buffer 两级；early issue 受 branch、scalar write、memory-order 限制 |
| S5 Scalar slice execution | scalar backend | scalar slice、vector wb、VDU operand req | XRF/FRF 更新、branch redirect、operand service | scalar slice done 才允许 EP 前端安全推进 |
| S6 Vector request resolution | VDU | vector slice、scalar operand、Ara ready | Ara request、command window entry、response metadata | operand snapshot 后普通 vector 可 ack；`vset rd` 需等 scalar-visible 写回 |
| S7 Ara semantic consumption | dispatcher/sequencer | Ara request + `hdv_meta` | lane/VLSU issue、hazard decision | same-EP bypass 只裁剪软件承诺可并行的保守 hazard |
| S8 Vector execution/prefetch | Ara lanes/VLSU/addrgen/vldu | issued vector op、prefetch hint | demand AR、prefetch AR、VRF writeback | prefetch 只能在地址精确匹配时替代同一 demand load |
| S9 Drain and completion | top/VDU/scalar/TIU/TSU | scalar task exit、VDU busy、Ara response | task done/error | task done 必须等待 vector dispatch/response 相关状态 drain |

### 2.1 总体框图层级

建议总框图按下面层级画：

```text
Host / CSR driver
  |
  v
+--------------------+      +--------------------+
| TIU                | ---> | TSU                |
| task CSR/status    |      | single active task |
+--------------------+      +--------------------+
                                |
                                v
                         +----------------------+
                         | IPU                  |
                         | local I-fetch        |
                         | loop replay          |
                         +----------------------+
                                |
                         128-bit fetch packet
                                |
                                v
                         +----------------------+
                         | VLIWPU               |
                         | header/p-bit/cross   |
                         | EP formation         |
                         +----------------------+
                                |
                         execute packet + hint
                                |
                                v
                         +----------------------+
                         | HEU                  |
                         | scalar/vector split  |
                         | current/buffer EP    |
                         +----------------------+
                           |                  |
                    scalar slice        vector slice + ep_id
                           |                  |
                           v                  v
              +---------------------+   +----------------------+
              | HDV scalar backend  |   | VDU                  |
              | XRF/FRF/branch/LSU  |   | operand snapshot     |
              | operand service     |   | command window       |
              +---------------------+   +----------------------+
                           ^                  |
                           | scalar operand   | Ara request + hdv_meta
                           | vset/vector wb   v
                           |           +----------------------+
                           |           | Ara dispatcher       |
                           |           | Ara sequencer        |
                           |           | lanes / VLSU         |
                           |           +----------------------+
                           |                  |
                           +------- response / scalar-visible writeback
```

图中应特别标出四类边：

- **EP 边**：VLIWPU 到 HEU，携带 slot valid、PC、32-bit 标记、指令类别和 packet-level prefetch hint。
- **scalar operand 边**：VDU 到 scalar backend，用于读取 vector base/stride/scalar operand。
- **HDV metadata 边**：VDU 到 Ara，随每条 vector request 携带 `ep_id` 和 prefetch hint。
- **ack/drain 边**：scalar backend 与 VDU 回到 HEU/top，用于 EP 推进和 task done。

### 2.2 Stage S0：Host task accept

对应模块：`hdv_task_interface_unit.sv`。

这一段把 host 的 CSR 写入转换成 HDV 内部 task。host 写 `VTASK_ADDR`、`VTASK_PADDR` 和 `VTASK_START`；TIU 保存 task entry、descriptor pointer 和 sticky status。

输入：

- host CSR write/read。
- TSU ready。
- 顶层返回的 task done/error。

输出：

- `tiu_tsu_task_valid`
- task entry PC
- task descriptor pointer
- status busy/done/error

关键逻辑：

1. `VTASK_ADDR` 和 `VTASK_PADDR` 写入寄存器。
2. `VTASK_START.bit0` 产生一次 start pulse。
3. 若当前没有 pending task，start pulse 把 entry/descriptor 打包成 `task_valid_q`。
4. 若 pending task 尚未被 TSU 接收又收到新的 start，则置 error，避免覆盖任务。
5. TSU 接收 task 后，TIU 清 pending valid。

阻塞和边界：

- TIU 本身不反压 CSR，CSR ready 恒为 1。
- 真正的 backpressure 来自 TSU FIFO full；若 TSU 不 ready，TIU 保留 pending task。
- TIU 不解释 kernel 指令，也不参与 EP 形成。

画图时可以把 TIU 画成 **Host CSR front-end + task/status registers**。

### 2.3 Stage S1：Task schedule

对应模块：`hdv_task_schedule_unit.sv`。

TSU 把 TIU 提交的 task 排队，并保证当前 HDV 前端一次只执行一个 active task。当前 RTL 支持 task FIFO，但 HDV 执行路径是 single-active-task 语义。

输入：

- TIU task valid。
- IPU task ready。
- top/task done/error/flush。

输出：

- `tsu_ipu_task_valid`
- active task entry/descriptor
- TIU ready/status

关键逻辑：

1. TIU task 进入 FIFO。
2. 当 FIFO 非空且 `active_q=0` 时，TSU 把队头 task 发给 IPU。
3. IPU 接收后，TSU 置 `active_q=1`。
4. 当前 task done/error 后清 `active_q`，允许下一个 task 出队。

阻塞和边界：

- `active_q` 是 task 所有权标记，防止多个 task 的 IPU buffer、HEU EP、VDU wait table、Ara response 混叠。
- flush 会清 active 状态和 FIFO，表示放弃排队/执行中的 task。

画图时可以把 TSU 画成 **Task FIFO + single active task latch**。

### 2.4 Stage S2：Local instruction supply

对应模块：`hdv_instruction_prefetch_unit.sv`。

IPU 是 HDV 前端供给的第一段。它从 task entry PC 开始取 128-bit fetch packet，写入本地 ping-pong buffer，并向 VLIWPU 按顺序提供 packet。循环稳定后，IPU 可以从本地 buffer replay loop body，减少重复 instruction memory 访问。

输入：

- active task entry。
- instruction-memory AXI response。
- VLIWPU ready。
- scalar backend branch redirect / loop exit。
- task complete/flush。

输出：

- `ipu_vliwpu_packet_valid`
- 128-bit fetch packet
- packet PC
- instruction-memory AR
- `hdv_loop_active`

内部阶段可以理解为：

```text
IDLE
  -> FILL first packet
  -> SERVE active buffer
       -> optional background fill
       -> loop replay on backward redirect
       -> refill or switch buffer on miss/fall-through
```

关键逻辑：

1. **FILL**：task 启动或 redirect miss 后发 instruction-memory AR，等待首个 packet 返回。
2. **SERVE**：只要当前 `exec_idx` 对应 packet valid，就向 VLIWPU 输出。
3. **packet cache/SRAM bypass**：隐藏 SRAM 读延迟，避免每个 packet 都多等一拍。
4. **loop build/lock**：看到 loop_start/loop_end 后记录 loop body 范围。
5. **loop replay**：taken backward branch 若命中本地 buffer，直接把 `exec_idx` 跳回 loop head。
6. **loop exit**：not-taken backward branch 让 IPU 退出 replay，恢复 fall-through。

阻塞和边界：

- VLIWPU 不 ready 时，IPU 保持当前 packet，不跳过。
- redirect PC 必须按 128-bit fetch packet 对齐。
- IPU 只供给指令 packet，不形成 EP，也不理解 vector hazard。
- instruction-memory outstanding 有上限，避免取指淹没数据访存。

画图时可以把 IPU 画成 **Local instruction buffer + loop replay engine**，旁边标出 `redirect` 和 `loop_exit` 控制边。

### 2.5 Stage S3：EP formation

对应模块：`hdv_vliw_pack_unit.sv`。

VLIWPU 把 128-bit 或 256-bit logical packet 扫描成 execute packet。它是 HDV 前端从“指令流”变成“EP 流”的关键模块。

输入：

- IPU fetch packet。
- packet PC。
- header/p-bit/prefetch hint。
- HEU ready。

输出：

- EP slot valid。
- EP slot halfword。
- 32-bit 起点/continuation 标记。
- 每个 slot PC。
- 每个 slot class：scalar/vector/branch/system。
- EP-bundled prefetch hint。

内部阶段可以理解为：

```text
packet latch
  -> header decode
  -> slot classify
  -> issue-mask scan
  -> optional carry merge
  -> EP valid to HEU
  -> head_slot update
```

关键逻辑：

1. **header decode**：识别 `lui x0, imm20`，提取 p-bit、packet256、cross、loop_start/end、prefetch mode/disable。
2. **logical packet build**：普通 packet 是 128-bit；`packet256=1` 时拼接两个 128-bit packet。
3. **slot classify**：按 opcode 粗分类 scalar/vector/branch/system。
4. **32-bit continuation**：32-bit 指令占两个 16-bit slot，业务计数只按起点算一条。
5. **issue-mask scan**：从 `head_slot_q` 开始，按 p-bit、dep_break、control boundary、MaxIssueSlots 决定 EP 宽度。
6. **cross carry**：若 header 允许 cross，packet 尾部 EP 可暂存并与下一 packet 开头合并。
7. **hint alignment**：prefetch hint 随 EP/carry 一起保存，避免跨 packet 时错配。

阻塞和边界：

- HEU 不 ready 时，VLIWPU 保持当前 EP。
- branch/system 是硬边界。
- p-bit 只允许合并，不强制合并；硬件可因资源/边界拆开。
- VLIWPU 不做完整寄存器 scoreboard；同 EP 依赖安全主要由软件 p-bit 承诺和后端边界共同保证。

画图时可以把 VLIWPU 画成 **Header decoder + EP packer**，输入是 fetch packet，输出是 execute packet。

### 2.6 Stage S4：Hybrid EP split and front-end advance

对应模块：`hdv_hybrid_execution_unit.sv`。

HEU 是 HDV 的分水岭。它不执行指令，而是把同一个 EP 拆成 scalar slice 和 vector slice，并维护 current/buffer 两个 EP 上下文。它决定前端什么时候可以接收下一 EP，也决定 buffered vector 是否可以安全提前发给 VDU。

输入：

- VLIWPU EP。
- scalar backend ready/done。
- VDU ready/acknowledge。
- backend error/flush。

输出：

- scalar slice 到 scalar backend。
- vector slice 到 VDU。
- `ep_id`。
- vector prefetch hint。
- `heu_top_ep_acknowledged`。

内部阶段可以理解为：

```text
accept EP
  -> split scalar/vector slots
  -> allocate vector ep_id
  -> send scalar slice
  -> send vector slice
  -> wait scalar_ep_done and vector_ep_acknowledged
  -> acknowledge EP to front-end
```

current/buffer 行为：

1. 若当前没有 outstanding EP，新 EP 进入 current。
2. 若 current 仍未完成但 HEU buffer 空，新 EP 进入 buffer。
3. 若 current 的 scalar slice 卡住，而 buffer 的 vector slice 与 current 没有冲突，则 buffer vector 可 early issue。
4. current 完成后，buffer 被提升为 current。
5. 当前最多两个 outstanding vector EP，因此 `ep_id` 用 1 bit 在 0/1 间切换。

early issue 安全条件：

- 不能跨 unresolved branch。
- 不能让 buffered vector memory 越过 current scalar memory-order op。
- 不能让 buffered vector 读取 current scalar slice 尚未写回的 GPR/FRF。
- 不能让 buffered vector 与 current vector 在保守写读关系上出现不安全重叠。
- vector dispatch 通路必须能接收。

阻塞和边界：

- `heu_vliwpu_execute_ready_o` 受 buffer 和 unresolved branch 控制。
- `heu_top_ep_acknowledged` 要等 scalar slice done 和 vector slice acknowledged。
- EP acknowledge 只表示前端安全推进，不表示 vector 指令 retirement。

画图时可以把 HEU 画成 **EP split + current/buffer scheduler**，这是 SEAM-V “hybrid decoupled” 的核心框。

### 2.7 Stage S5：Scalar slice execution

对应模块：`hdv_scalar_backend.sv`。

标量后端执行 EP 中的 scalar slice，维护本地 XRF/FRF，解析分支，提供 vector operand，并处理少量 scalar-visible vector writeback。它不是完整 CVA6，但具备 HDV kernel 所需的标量执行能力。

输入：

- HEU scalar slice。
- scalar LSU AXI response。
- VDU operand request。
- VDU vector writeback / vset writeback。
- `vec_store_inflight` 和 `vec_vset_inflight`。

输出：

- `scalar_ep_done`。
- branch redirect / loop exit。
- scalar AXI load/store request。
- vector operand rs1/rs2/frs1 data。
- task complete/error。

内部状态机可以画成：

```text
IDLE
  -> EXECUTE
       -> simple batch
       -> WAIT_MULT
       -> WAIT_FPU
       -> LSU_AR / LSU_R
       -> LSU_AW / LSU_W / LSU_B
       -> REDIRECT
  -> DONE
```

关键逻辑：

1. **simple batch**：对简单 ALU/地址更新/循环控制类指令做批处理，减少逐条标量供给瓶颈。
2. **complex lane**：乘法、FPU、复杂指令进入等待状态，完成后写回。
3. **标量 LSU**：load 可连续发 AR 并按 load queue 写回；store 保守按 AW/W/B 完成。
4. **branch**：解析 branch target/taken/backward，把 taken redirect 送回 IPU/top。
5. **operand service**：响应 VDU 对 base/stride/scalar operand 的读取请求。
6. **vset interlock**：若后续 scalar 读正在飞的 `vset rd`，等待 vector writeback。
7. **vector store ordering**：若 VDU 表示 vector store inflight，标量 LSU 不发新 memory op。

阻塞和边界：

- scalar slice 完成前，HEU 不会整体 acknowledge 当前 EP。
- 同 EP 内 scalar 写后 vector 读新值没有自动保证，软件需要切 EP。
- 后续 EP 的 scalar-to-vector 版本由 HEU/VDU 的 acknowledge 和 early-issue mask 保证。

画图时可以把 scalar backend 画成 **Scalar slice executor + operand server + branch/LSU**。

### 2.8 Stage S6：Vector request resolution

对应模块：`hdv_vec_dispatch_unit.sv`。

VDU 把 HEU 的 vector slice 变成 Ara 能接收的 accelerator request。它是“HDV EP 语义”和“真实 Ara 后端”之间的适配层。

输入：

- HEU vector slice。
- `ep_id`。
- EP-bundled prefetch hint。
- scalar backend operand response。
- Ara request ready/response。

输出：

- Ara accelerator request。
- `acc_req_hdv_meta`。
- `vec_ep_acknowledged`。
- scalar operand request。
- vector/scalar-visible writeback。
- `vec_store_inflight` / `vec_scalar_vset_inflight`。

VDU 内部建议在框图中拆成八个小框：

```text
EP intake / pending skid
  -> slot select
  -> scalar operand request
  -> operand snapshot
  -> resolved request generation
  -> command window push/bypass
  -> Ara valid/ready
  -> response metadata / real wait table
```

关键逻辑：

1. **EP intake**：接收一个 vector slice；若 VDU 正忙，可用 pending skid 暂存后续 EP。
2. **slot select**：从 vector slot mask 中选择下一条有效 RVV 指令。
3. **operand detection**：判断该 vector 指令是否需要 scalar rs1/rs2/frs1。
4. **operand snapshot**：从 scalar backend 读取并固定 operand 值，后续 scalar 修改不会影响这条 request。
5. **lookahead/bypass**：当前 slot dispatch 时可提前请求下一 slot operand，减少一拍等待。
6. **request generation**：生成 Ara request，并绑定 `hdv_meta`。
7. **command window**：Ara 不 ready 时，resolved request 进入 window；window 空且 Ara ready 时可 bypass 直发。
8. **response metadata**：记录 request 的 scalar-visible writeback、store/vset 属性和 ep_id。
9. **real wait table**：跟踪最多两个 outstanding vector EP 是否已经达到前端安全 acknowledge 点。

`vec_ep_acknowledged` 的安全条件：

- 该 EP 所有 vector slot 已经被 VDU 消费为 request，或者该 EP 没有 vector slot。
- 需要的 scalar operand 已经 snapshot。
- 如果含 `vset rd!=x0`，对应 granted VL 写回已经可见。

阻塞和边界：

- command window full 会阻塞 request resolution。
- Ara req_ready 低会造成 backpressure，但 VDU 可以用 window 吸收一部分。
- VDU 不等待普通 vector arithmetic/load/store 完成后才 ack EP。
- vector store 对后续 scalar memory 的顺序通过 `vec_store_inflight` 保守保证。

画图时可以把 VDU 画成 **Vector request resolver + command window + EP wait table**。

### 2.9 Stage S7：Ara semantic consumption

对应模块：`ara.sv`、`ara_dispatcher.sv`、`ara_sequencer.sv`。

Ara 后端仍是执行 RVV 指令的主体。HDV 不替换 Ara dispatcher/sequencer/lane/VLSU，而是在 request 中携带 metadata，让后端在安全位置消费 EP 语义。

输入：

- VDU accelerator request。
- `hdv_meta`。
- Ara 内部 lane/VLSU ready。

输出：

- lane/VLSU issued operations。
- response。
- hazard/backpressure 计数。

关键逻辑：

1. `ara_dispatcher` 把 VDU request 解码成 Ara 内部 request，并把 `hdv_meta` 原样绑定到请求。
2. `ara_sequencer` 按原 Ara 规则建立 read/write hazard 候选。
3. 若新 request 与 running request 都有有效 HDV metadata 且 `ep_id` 相同，则 same-EP hazard candidate 可被裁剪。
4. 若不是 same EP，或者任一方没有有效 metadata，原 Ara hazard 规则保持不变。
5. lane/VLSU 的 ready、queue、operand requester、VRF bank 等压力仍按 Ara 原机制处理。

阻塞和边界：

- same-EP bypass 只裁剪保守 RAW/WAR/WAW 候选，不绕过 lane/VLSU 资源限制。
- same-EP bypass 依赖软件保证同 EP 内无真实非法 vector 依赖。
- 跨 EP 依赖仍由 Ara sequencer 正常保护。

画图时可以把 Ara semantic consumption 画成 **Ara dispatcher/sequencer with HDV metadata sideband**，不要画成一个全新的向量后端。

### 2.10 Stage S8：Vector execution and VLSU prefetch

对应模块：Ara lanes、`vlsu.sv`、`addrgen.sv`、`vldu.sv`。

这一段是真正的 vector compute/memory 执行。HDV 对它的新增影响主要是 request-bound prefetch，以及 sequencer 看到 EP metadata 后减少保守 hazard。

输入：

- Ara sequencer issued vector instructions。
- VLSU memory descriptors。
- `hdv_meta.prefetch_hint_valid`
- `hdv_meta.prefetch_disable`
- `hdv_meta.prefetch_mode`
- `hdv_loop_active`

输出：

- AXI demand load/store。
- AXI prefetch AR。
- lane/VRF writeback。
- VDU/Ara response。

prefetch 子流水可以画成：

```text
demand unit-stride load
  -> compute future prefetch address
  -> prefetch AR queue
  -> prefetch ROB / in-flight beats
  -> lookup FIFO + vldu prefetch buffer
  -> later demand lookup hit
  -> demand AR suppressed, data read from prefetch buffer
```

关键逻辑：

1. 只有带有效 hint 且未 disable 的 unit-stride load 才生成 prefetch。
2. `prefetch_mode` 描述同一条 load 下一次出现时的地址距离：1X/2X/4X/8X。
3. Demand AR 优先于 prefetch AR，prefetch 不能抢占可发 demand。
4. 当前 prefetch 与 demand 共用 `AXI_ID_DEMAND`，用 tag FIFO 标记返回 burst 属于 demand 还是 prefetch。
5. prefetch 完成后，addrgen 把地址放入 lookup FIFO，vldu 把数据放入 prefetch buffer。
6. later demand 地址匹配 lookup head 时，demand 不发 AR，直接消费 prefetch buffer。
7. 若 demand 与 lookup head 不一致，addrgen 触发 stream-break drain/flush，错误 prefetch 被丢弃。
8. page-cross prefetch 被拆成两个 segment，并用 second-tag 保持 lookup/data 对齐。

阻塞和边界：

- prefetch credit 同时看 VLD premem buffer、lookup FIFO、ROB 和 inflight beats。
- store-aware pacing 限制 prefetch lead，避免 vector store 被 prefetch 读请求长期饿死。
- strided/gather/scatter 当前不走有效 prefetch 路径。
- prefetch 永远不能成为正确性条件；miss、late、unused 只能影响性能。

画图时可以把 VLSU prefetch 画成 **request-bound prefetch path beside demand load path**，注意它不是独立 ISA 指令。

### 2.11 Stage S9：Response, drain and task completion

对应模块：`hdv_vec_dispatch_unit.sv`、`hdv_scalar_backend.sv`、`hdv_top.sv`、TIU/TSU。

HDV task 不能在 scalar code 看到 exit 后立刻结束，因为 vector request 可能还在 VDU command window、Ara response metadata、VLSU 或 lane 中飞行。当前顶层显式等待 vector dispatch drain。

输入：

- scalar backend task complete request。
- VDU busy。
- Ara response。
- pending stale instruction-memory response。

输出：

- TSU task done/error。
- TIU status done/error。
- host visible status。

关键逻辑：

1. scalar backend 遇到 task exit/ret/ebreak 或 host complete 条件，产生 `task_complete_request`。
2. top 若看到 VDU 仍 busy，就锁存 task complete seen。
3. VDU 继续 drain command window、response metadata、real wait table、vset wait、prefetch/response 相关状态。
4. VDU busy 清零后，top 才把 task done 送给 TSU/TIU。
5. 如果 task complete/flush 前有旧 instruction-memory response 未返回，top 用 stale response 机制接收并丢弃，避免 AXI fabric 被旧 response 堵住。

阻塞和边界：

- task done 是整个 HDV task 的完成，不是单个 EP 或单条 vector 指令完成。
- EP acknowledge 允许前端进入下一 EP，但 task done 必须等 vector side drain。
- error 会沿 TIU/TSU status 传播，供 host 读回。

画图时可以把这段画成 **Drain/commit controller**，连接 scalar exit、VDU busy、TSU/TIU status。

### 2.12 Stage 间反压关系

为了画清楚整体框图，需要把 ready/valid 反压画出来：

| 上游 | 下游 | 反压条件 | 结果 |
|---|---|---|---|
| TIU | TSU | task FIFO full | TIU 保留 pending task，重复 start 报错 |
| TSU | IPU | active task 未完成 | 后续 task 留在 FIFO |
| IPU | VLIWPU | VLIWPU not ready、packet invalid、loop_wait | `exec_idx` 不前进 |
| VLIWPU | HEU | HEU not ready | EP 保持，head_slot 不更新 |
| HEU | scalar backend | scalar backend not ready | scalar dispatch 保持 |
| HEU | VDU | VDU not ready | vector dispatch 保持或 buffer 等待 |
| VDU | Ara | Ara req_ready 低 | request 进入/停留 command window |
| Ara/VLSU | memory | AXI ready 低、VLSU queue full | Ara 后端 backpressure |
| VDU/top | task done | VDU busy | task complete 被锁存，等待 drain |

这张表有助于解释 SEAM-V 为什么不是“无限提前发射”：每一级都有明确的 storage 或 ready 边界。

### 2.13 Flush、redirect 与 replay 关系

HDV 里不要把所有 flush 画成一根全局 reset 线。至少应区分四类控制边：

- **task flush**：终止当前 task，清 TIU/TSU active、IPU、VLIWPU、HEU、VDU 前端状态。
- **branch redirect**：来自 scalar backend 的 taken branch，刷新已基于旧 PC 的前端 packet/EP/vector pending 状态，但 IPU 可尝试本地 loop replay。
- **loop exit**：not-taken backward branch，告诉 IPU 退出 loop locked/replay 状态，恢复 fall-through。
- **prefetch stream break**：只作用在 VLSU prefetch lookup/buffer 路径，等待 ROB/inflight drain 后 flush prefetch buffer，不清整个 HDV 前端。

画图时建议用不同颜色或线型区分：

- task/branch control path
- EP ready/ack path
- scalar operand path
- HDV metadata path
- prefetch side path

### 2.14 教学级讲解顺序

讲 HDV 时可以按下面顺序，而不是按 RTL 文件顺序：

1. 先画 S0-S9 总流水，说明 task、packet、EP、request、response 的粒度不同。
2. 再讲 S2/S3：为什么本地取指和 EP formation 能提高 instruction supply。
3. 再讲 S4：为什么 HEU 需要 current/buffer，以及为什么只能安全提前发 buffered vector。
4. 再讲 S5/S6：scalar slice 和 vector slice 如何通过 operand snapshot 协同。
5. 再讲 S7：Ara sequencer 如何消费 same-EP metadata。
6. 再讲 S8：VLSU prefetch 如何把软件 memory intent 转成 request-bound prefetch。
7. 最后讲 S9：为什么 task done 必须 drain，而 EP ack 不是 vector completion。

如果要把这章变成论文框图，建议主图只放 S0-S9 和五条关键 sideband；细节图再分别放 HEU current/buffer、VDU command window、VLSU prefetch。

## 3. 软件可见格式与硬件解释

HDV kernel 使用一个 RISC-V hint 形式的 header 描述 logical packet。当前 RTL 将 `lui x0, imm20` 识别为 HDV header。VLIWPU 对 header 的解释如下：

| 字段 | 含义 |
|---|---|
| `imm20[12:0]` | p-bits，描述 logical packet 内相邻 16-bit slot 的连接关系 |
| `imm20[13]` | `packet256`，当前 logical packet 由两个连续 128-bit fetch packet 组成 |
| `imm20[14]` | `cross`，允许 logical packet 尾部 EP 跨到下一个 logical packet 开头 |
| `imm20[15]` | `loop_start`，循环体起点标记，供 IPU loop build/lock 使用 |
| `imm20[16]` | `loop_end`，循环体末端标记，供 IPU 停止无界背景填充 |
| `imm20[18:17]` | `prefetch_mode`，在未关闭时表示 1X、2X、4X、8X |
| `imm20[19]` | `prefetch_disable`，显式关闭本 packet 的 prefetch |

`prefetch_hint_valid` 由 header 是否存在决定。它与 `prefetch_disable` 必须分开理解：

- 没有 HDV header：`prefetch_hint_valid=0`，后端认为没有软件访存提示。
- 有 header 且 `prefetch_disable=1`：软件显式关闭 prefetch。
- 有 header 且 `prefetch_disable=0`：`prefetch_mode` 编码 1X、2X、4X 或 8X。

这种编码避免把 `00` 同时解释成“关闭”和“1X”。当前 RTL 中 `00` 是 1X，关闭由独立 bit 表示。

## 4. 顶层集成：`hdv_top.sv`

`hdv_top` 是当前 HDV 原型的系统级 wrapper。它实例化 HDV 前端、真实标量后端、VDU、Ara 后端，并把 Ara 数据 AXI、标量 LSU AXI、HDV instruction-memory AXI 汇入一个 system AXI mux。

关键参数：

| 参数 | 当前默认/用途 |
|---|---|
| `QueueDepth=4` | TSU task FIFO 深度 |
| `FetchPacketWidth=128` | IPU 每次提供 128-bit fetch packet |
| `BufferBytes=512` | IPU 每个 ping-pong buffer 容量，32 个 128-bit packet |
| `ImemOutstandingDepth=4` | HDV instruction-memory read outstanding 上限 |
| `NumSlots=8` | HEU/VLIWPU slot 宽度，单位为 16-bit halfword |
| `MaxIssueSlots=NumSlots` | 单个 EP 最多输出的 slot 数 |
| `VectorCmdWindowDepth=12` | VDU resolved command window 深度 |
| `UseCva6HdvScalar=1` | 当前默认使用真实 `hdv_scalar_backend` |

### 4.1 内部数据连接

TIU 输出 task entry/descriptor 到 TSU，TSU 一次激活一个 task 给 IPU。IPU 输出 fetch packet 到 VLIWPU。VLIWPU 输出 EP slot、PC、指令类别和 EP-bundled prefetch hint 到 HEU。HEU 分别输出 scalar slice 和 vector slice。

Scalar slice 接入 `hdv_scalar_backend`。Vector slice 接入 `hdv_vec_dispatch_unit`，VDU 再驱动 Ara accelerator request，同时输出 `acc_req_hdv_meta_o` 作为 Ara 后端 HDV metadata sideband。

### 4.2 branch redirect 与 flush

真实标量后端解析分支后输出：

- `branch_resolved_valid`
- `branch_taken`
- `branch_target`
- `branch_backward`

`hdv_top` 用 taken branch 生成 `hdv_ctrl_redirect_valid/pc`，送给 IPU。这个 redirect 会 flush VLIWPU、HEU 和 vector dispatch 的前端状态，但不会把同一个 flush 输入 IPU 覆盖掉 IPU 自己的 redirect path。这样 taken backward branch 能让 IPU 在已缓存 loop body 中 replay。

not-taken backward branch 产生 `scalar_loop_exit`，送入 IPU 的 `loop_exit_i`，用于结束 loop-active 状态并恢复顺序取指。

### 4.3 instruction-memory AXI bridge

IPU 内部只发 128-bit instruction fetch request。`hdv_top` 把它转换成 AXI AR，并使用 `imem_outstanding_q` 限制 outstanding 数量。发生 dispatch flush 或 task complete 时，桥接逻辑不会让旧 response 堵住 AXI fabric，而是用 `imem_stale_rsp_q` 记录需要 drain 的旧 response，接收后丢弃。

这个限制很重要。IPU buffer 已经放大到 512B，如果让 instruction fetch 无限制提前填充，会和 Ara 数据访存、标量 LSU 争抢同一个 system AXI 端口，严重时会造成 store-heavy kernel 卡住。

### 4.4 task done drain

`task_complete_request` 可以来自 host 或 scalar backend。若它出现时 VDU 仍 busy，`hdv_top` 会锁存 `host_task_complete_seen_q`，等 `vec_dispatch_busy` 清零后才让 TSU 看到 task done。这保证 task 状态不会在 vector request/response 仍未清空时提前结束。

### 4.5 flush 分层

顶层不是用一个全局 reset 式 flush 简单清所有模块，而是区分几类来源：

- `task_flush`：host 或上层控制请求终止当前 task，清前端、HEU、VDU 和 TSU active 状态。
- `task_complete_request`：标量后端看到 `ret/ebreak` 或 host 显式完成请求。它会停止继续取指，并等待 VDU drain。
- `hdv_ctrl_redirect_valid`：真实 branch taken 或外部 redirect。它 flush VLIWPU/HEU/VDU 中已经基于旧 PC 形成但还没有安全进入后端的前端状态，同时让 IPU 自己按 redirect path 处理本地 buffer replay/refetch。

这三类事件对 IPU 的意义不同。task complete/flush 会让 IPU 回到 idle；branch redirect 则可能命中本地 loop buffer，使 IPU 不必重新发 instruction-memory AR。顶层必须保留这种差异，否则会丢掉 loop replay 的性能收益。

### 4.6 system AXI 汇聚

当前 `hdv_top` 内部有三类 AXI master：

- Ara 数据访问，包括 VLSU demand/store/prefetch。
- `hdv_scalar_backend` 的标量 LSU。
- IPU instruction-memory 读请求。

这些 master 通过 system AXI mux 汇到外部 memory system。顶层对 IPU 加 `ImemOutstandingDepth=4`，对 task complete/redirect 后旧 instruction response 做 stale drain，是为了避免 instruction fetch 在共享端口上造成不可控反压。标量 LSU 与 Ara 数据访问的顺序关系不靠 AXI mux 推断，而靠 VDU/标量后端之间的 `vec_store_inflight` 等显式互锁。

## 5. 共享定义：`hdv_pkg.sv` 与 `ara_pkg.sv`

### 5.1 `hdv_pkg.sv`

`hdv_pkg` 定义 HDV 控制面和前端分类所需的公共类型：

- `HDV_CSR_VTASK_ADDR = 12'h7c0`
- `HDV_CSR_VTASK_PADDR = 12'h7c1`
- `HDV_CSR_VTASK_START = 12'h7c2`
- `HDV_CSR_VTASK_STATUS = 12'h7c3`
- `hdv_inst_class_e = SCALAR/VECTOR/SYSTEM/BRANCH`

`hdv_inst_class_e` 由 VLIWPU 产生，由 HEU 消费。HEU 当前把 `VECTOR` 送入 vector slice，其余类别进入 scalar slice；SYSTEM 和 BRANCH 作为硬边界影响 VLIWPU 打包。

### 5.2 `ara_pkg.sv`

当前 Ara package 中新增或扩展的 HDV 相关字段是：

```systemverilog
typedef struct packed {
  logic       hdv_valid;
  logic       ep_id;
  logic       prefetch_hint_valid;
  logic       prefetch_disable;
  logic [1:0] prefetch_mode;
} hdv_meta_t;
```

`hdv_meta_t` 进入 Ara request，并最终到 sequencer/VLSU。`ara_pkg` 里仍保留 `AXI_ID_PREFETCH` 常量，但当前 VLSU prefetch AR 实际与 demand 共用 `AXI_ID_DEMAND`，通过独立 tag FIFO 区分 R burst 类型。不要再把当前设计描述成“prefetch 使用独立 AXI ID 返回”。

## 6. 任务控制模块

### 6.1 TIU：`hdv_task_interface_unit.sv`

TIU 是 HDV task CSR 前端。它提供一个极简 CSR-like ready/valid 接口，保存 task entry、task descriptor 和 sticky status。

CSR 行为：

- `VTASK_ADDR`：保存 task entry PC。
- `VTASK_PADDR`：保存 task descriptor pointer。
- `VTASK_START`：写 bit0=1 产生一次 start pulse。
- `VTASK_STATUS`：bit0 为 busy，bit1 为 done，bit2 为 error；写 bit1/bit2 清 done/error。

TIU 不反压 CSR，`tiu_host_csr_ready_o` 恒为 1。访问非 HDV CSR 地址时，`tiu_host_csr_error_o` 在同周期置位。

Start pulse 的处理逻辑是：

1. 如果当前没有 pending task，或者同周期 TSU ready 接收旧 task，则允许新 task 进入 `task_valid_q`。
2. 如果已有 pending task 且 TSU 不 ready，又收到新的 start，则置 error，避免覆盖未提交任务。
3. 新 task 提交会清除旧 done/error。

`task_valid_q` 与当前保存的 entry/descriptor 一起送给 TSU。TSU ready 后，TIU 清掉 pending valid。

TIU 的组合逻辑优先级可以按下面理解：

1. 先默认保持寄存器值。
2. 若旧 pending task 被 TSU 接收，则清 `task_valid_q`。
3. 若 `START` 写 bit0=1，则尝试写入新的 pending task。
4. 若状态寄存器写 bit1/bit2，则清 sticky done/error。
5. 若顶层 task done/error 输入到来，则置 TIU sticky done/error。

这种顺序允许“TSU 同周期接走旧 task，host 同周期 start 新 task”成立；但不允许在 TSU 不 ready 时覆盖已有 pending task。

### 6.2 TSU：`hdv_task_schedule_unit.sv`

TSU 是 FIFO-backed task scheduler。它用 `fifo_v3` 保存 host 提交的 task，保证任务按提交顺序进入 IPU。

TSU 的核心状态是：

- FIFO：保存待执行 task。
- `active_q`：表示已有一个 task 被发给 IPU，尚未完成。
- `done_q/error_q`：sticky 状态，供 TIU 读回。

TSU 只在 `!fifo_empty && !active_q` 时向 IPU 输出 task。IPU 接收 task 后，TSU 置 `active_q=1`。只有当前 active task done/error 后，才会继续发下一个 task。这样当前 HDV 路径保持单 task active，避免多个 task 的 IPU/HEU/Ara 状态混叠。

TSU 的 ready/valid 关系是：

```text
fifo_push = tiu_tsu_task_valid & tsu_tiu_task_ready
fifo_pop  = tsu_ipu_task_valid & ipu_tsu_task_ready
tsu_tiu_task_ready = !fifo_full
tsu_ipu_task_valid = !fifo_empty && !active_q
```

`active_q` 是 TSU 与 IPU/后端之间的任务所有权标记。FIFO 中可以排队多个任务，但只有 `active_q=0` 时才允许下一个任务出队给 IPU。done/error 会清 `active_q` 并置 sticky 状态；`flush_i` 会清 active/done/error，并通过 `fifo_v3` flush 清空排队任务。

## 7. 本地指令供给：`hdv_instruction_prefetch_unit.sv`

IPU 从 task entry 开始取 128-bit fetch packet，并向 VLIWPU 提供连续 packet。当前顶层配置下，每个 ping-pong buffer 是 512B，即 32 个 128-bit packet；模块自身默认 `BufferBytes=64` 只是 standalone 默认值，不代表当前系统集成值。

### 7.1 状态机

IPU 有三个主状态：

- `IDLE`：等待 TSU 派发 task。
- `FILL`：task 启动或 redirect 后，等待第一个 packet 返回。
- `SERVE`：向 VLIWPU 输出 active buffer 中的 packet，同时继续填充当前 buffer 或 background buffer。

IPU 不等待整个 buffer 填满后才开始服务。第一个 packet 返回后，只要对应 entry valid 且 packet cache 命中，就可以进入 SERVE，降低 task 启动延迟。

状态推进可简化成：

```text
IDLE  --task_valid--> FILL
FILL  --first response accepted and entry valid--> SERVE
SERVE --task_complete/flush--> IDLE
SERVE --redirect miss local buffers--> FILL
SERVE --redirect hit local buffers--> SERVE with exec_idx changed
```

`ipu_tsu_task_ready_o` 只在 `IDLE` 为 1，所以 IPU 不会在一个 task 尚未结束时接收另一个 task。

### 7.2 packet cache 与 SRAM 读隐藏

IPU 内部使用 SRAM 保存 fetch packet。为了避免每个顺序 packet 都多等一拍 SRAM 读，IPU 有几类小型 cache/bypass：

- `served_packet_q`：保存刚服务过的 packet。
- `prefetch_packet_q`：提前读取下一个 packet。
- `sram_bypass_hit`：上周期 SRAM 读返回正好对应当前 exec index 时直接旁路。
- `loop_start_packet_q`：保存 loop-start packet，backward redirect 回 loop head 时不必重新读 SRAM。

这些结构只用于取指供给，不改变软件语义。

### 7.3 background fill 与带宽约束

在 SERVE 状态，IPU 可以填充 background buffer。但当前设计不会盲目把 512B buffer 后续地址全部填满。若 loop body 已经通过 `loop_start/loop_end` 标记识别，IPU 会在 loop-end packet 已取到后停止继续填充剩余空间。这样避免把 kernel 后的数据区当指令继续读入，抢占 Ara 数据访存带宽。

`hdv_top` 还通过 `ImemOutstandingDepth=4` 限制 instruction fetch outstanding 数量。IPU 本地 buffer 变大后，这个限制是防止共享 AXI 被 instruction fetch 淹没的关键。

### 7.4 loop build、lock 与 replay

IPU 使用以下状态跟踪循环：

- `loop_build_q`：已经看到 loop-start，正在构建 loop body。
- `loop_locked_q`：已经看到 loop-end，loop body 可被保护。
- `auto_loop_lock_q`：taken backward redirect 后进入自动 loop replay。
- `loop_wait_q`：遇到 backward branch packet 后等待分支解析，避免错误顺序前进。
- `loop_exit_seen_q`：记录 not-taken backward branch，指导 loop exit 后恢复顺序取指。

当标量后端解析 taken backward branch，IPU 如果发现 redirect target 在 active/fill buffer 且对应 packet valid，就直接把 `exec_idx` 跳回目标 packet。这是 HDV loop replay 的核心收益：循环体后续迭代不需要重新从 memory fetch。

若 backward branch 最终 not-taken，标量后端产生 `loop_exit_i`。IPU 退出 `auto_loop_lock/loop_locked` 状态，恢复 fall-through 路径。如果 fall-through packet 因 loop-end cap 没有继续填充，IPU 会重新打开必要填充，而不是死在 replay 状态。

### 7.5 redirect 对齐约束

IPU 要求 redirect PC 按 fetch packet 宽度对齐。当前 `FetchPacketWidth=128`，所以 redirect PC 必须 16B 对齐。仿真中若 `redirect_valid_i` 非对齐，会触发 fatal。这一约束要求 HDV kernel 中 loop label 适当 `.balign 16`，否则 branch target 无法作为 fetch packet head replay。

### 7.6 memory request/response 与 buffer 角色

IPU 内部有 active buffer 和 fill buffer 两个角色，物理上对应 A/B ping-pong buffer。active buffer 给 VLIWPU 服务 packet；fill buffer 接收 instruction-memory response。两者可以相同，也可以不同：

- task 启动初期，active/fill 指向同一个 buffer，IPU 边填边服务，首包可用后即可输出。
- 顺序执行时，active buffer 快用完而另一个 buffer 已经 background fill 完成，IPU 可以切换 active/fill 角色。
- loop replay 时，loop body 可能横跨两个 buffer，因此 redirect 命中 active 或 fill 都可能有效。

`fill_req_idx_q` 表示已经发出到内存的 packet index，`fill_rsp_idx_q` 表示已经收到并写入 SRAM/valid bit 的 index。请求发出和响应返回分离后，IPU 用 valid bit 判断某个 packet 是否真的可服务，不能只看地址范围。

### 7.7 packet 输出和反压

`ipu_vliwpu_packet_valid_o` 的核心条件是：

```text
state_q == SERVE
&& active_packet_valid
&& !loop_wait_q
&& !bg_stall
&& !task_complete
```

VLIWPU 不 ready 时，IPU 保持当前 `exec_idx_q`，不会跳过 packet。VLIWPU 接收后，IPU 才根据顺序路径、loop wait、buffer 边界或 redirect 更新 `exec_idx_q`。这样取指端是严格按 packet 顺序推进的；所有“跨 packet”并行只发生在 VLIWPU 的显式 carry 逻辑里。

## 8. EP 形成：`hdv_vliw_pack_unit.sv`

VLIWPU 把 IPU 的 fetch packet 转成 HEU 可消费的 execute packet。它不是通用 decoder，而是一个保守 packet scanner。

VLIWPU 内部没有多级流水线，核心状态是：

- `packet_hold_valid_q`：当前 logical packet 是否已经锁存。
- `packet_q`：当前 128/256-bit logical packet 内容。
- `packet_is_256_q`：当前 logical packet 是否为 packet256。
- `head_slot_q`：下一次扫描从哪个 slot 开始。
- `carry_valid_q`：是否有上一 packet 尾部 EP 等待跨包合并。

理解这个模块时可以把它看成“一个带 head pointer 的 packet scanner”。它每次从 `head_slot_q` 开始向后扫，形成一个 `issue_mask`，成功交给 HEU 后把 `head_slot_q` 推到下一条未处理 slot。

### 8.1 logical packet

普通情况下，一个 128-bit fetch packet 包含：

```text
[31:0]    HDV hint header
[127:32] 6 个 16-bit instruction slot
```

若 `packet256=1`，VLIWPU 暂存第一 beat，等待下一 128-bit beat 到来，然后组成 256-bit logical packet：

```text
{second_beat, first_beat}
```

此时 slot 数从 6 扩大到 14。注意 packet256 扩大的是扫描窗口，不扩大 HEU 单个 EP 的最大 slot 数。

### 8.2 32-bit 指令与 continuation slot

VLIWPU 用指令 halfword 低两位判断 32-bit 指令起点。若一个 slot 是 32-bit 指令起点，下一个 slot 被标记为 continuation。打包时 continuation slot 会随起点一起输出，但 HEU 只在起点位置组装完整 32-bit 指令，避免把同一条 32-bit 指令当作两条业务指令。

### 8.3 指令分类

VLIWPU 用轻量 opcode 判断 slot 类型：

- RVV arithmetic、vector load、vector store 归为 `HDV_INST_VECTOR`。
- FENCE、SYSTEM、非法 compressed/system 类边界归为 `HDV_INST_SYSTEM`。
- branch/jal/jalr 归为 `HDV_INST_BRANCH`。
- 其他默认归为 `HDV_INST_SCALAR`。

SYSTEM 和 BRANCH 都是硬边界：形成 EP 时遇到它们会停止继续 pack，避免控制流或系统语义被跨越。

### 8.4 p-bit 与 issue mask

`p_bits` 描述 logical packet 内相邻 slot 是否允许连接。VLIWPU 从 `head_slot_q` 开始扫描，生成 `issue_mask`。扫描停止条件包括：

- logical packet 已到末尾。
- 已达到 `MaxIssueSlots`。
- 当前边界 p-bit 为 0。
- 外部 `dep_break` 指定该边界切开。
- 当前指令是 SYSTEM 或 BRANCH。

因此 header/p-bit 只是允许合并，硬件仍可因为边界条件拆分 EP。

`issue_mask` 里会同时包含 32-bit 指令的起始 slot 和 continuation slot。后续输出到 HEU 时，continuation slot 用来恢复完整 32-bit 指令，但不会作为单独业务指令参与分类和 slice split。

### 8.5 cross-packet carry

若当前 logical packet 尾部 EP 满足以下条件：

- header `cross=1`。
- 当前 EP 已 drain 到 packet 末尾。
- EP 还有空余 issue slot。
- 当前 EP 和前序已处理部分没有控制流/system 边界。

VLIWPU 不立即把尾部 EP 发给 HEU，而是保存到 carry buffer，并拉取下一个 logical packet。下一 packet 到来后，`cross_execute_valid` 把 carry tail 和下一 packet 开头 slot 组合成一个跨 packet EP。跨包只在 header 显式授权时发生；没有 `cross=1` 时，packet 边界就是 EP 边界。

carry buffer 保存的不只是 slot 数据，还包括：

- 每个 slot 的 `is_32b` 信息。
- 每个 slot 的 PC。
- 每个 slot 的分类。
- 该 EP 起点 PC。
- 跟随这个 tail EP 的 prefetch hint。

所以跨包 EP 在 HEU 看来和普通 EP 一样完整，不需要回头查上一 packet 的 header 或 PC。

### 8.6 prefetch hint 随 EP 对齐

VLIWPU 输出：

- `vliwpu_prefetch_hint_valid_o`
- `vliwpu_prefetch_disable_o`
- `vliwpu_prefetch_mode_o`

跨包 carry 时，这些 hint 会随 carry 一起保存。这样 HEU 和 VDU 看到的是 EP-bundled hint，而不是已经前移到下一 packet 的瞬时 header。这个细节保证 packet256/cross 下 prefetch hint 不错配。

### 8.7 ready/valid 与 head 更新

VLIWPU 接收 IPU packet 的条件是 `vliwpu_ipu_packet_ready_o=1`。它在以下情况下可以接收新 packet：

- 当前没有 held packet。
- 当前 held packet 的普通 EP 已被 HEU 接收，并且 packet 被 drain。
- 当前 held packet 的尾部已进入 carry，模块需要下一 packet 完成跨包 EP。
- 当前 cross EP 被 HEU 接收，并且下一 packet 也被 drain。

VLIWPU 输出 EP 的握手是 `vliwpu_heu_execute_valid_o & heu_vliwpu_execute_ready_i`。只有握手成功后，`head_slot_q` 才移动或清零。若 HEU 反压，VLIWPU 保持 held packet/carry 不变，IPU 也会因为 packet_ready 下降而停住。

### 8.8 正确性不变量

这个模块需要维持几条不变量：

- 任何 32-bit 指令不能被拆成两个 EP。
- SYSTEM/BRANCH 不能被跨越进后续 EP。
- 没有 header 时，p-bit 和 prefetch hint 都按无效/保守处理。
- packet256 只改变 logical packet 长度，不改变 HEU/VDU 每个 EP 最大 slot 数。
- carry 中的 prefetch hint 必须跟随原 tail EP，而不是使用下一 packet header。

## 9. 混合执行：`hdv_hybrid_execution_unit.sv`

HEU 接收 VLIWPU 输出的 EP，把其中的指令按类别分成 scalar slice 和 vector slice，并管理 EP acknowledge。

HEU 是前端保序的核心。它自己不执行 scalar 或 vector 指令，但决定什么时候可以接收下一个 EP、什么时候可以让 buffered vector 提前发给 VDU，以及什么时候告诉上游“当前 EP 已安全交付”。

### 9.1 slice split

HEU 对每个非 continuation slot 组装 32-bit 指令，并根据 VLIWPU 的 class 生成：

- `scalar_insn_valid_in`
- `vector_insn_valid_in`
- 完整 `dispatch_insn_in`
- per-slot PC

非 vector 指令都进入 scalar slice。vector 指令进入 vector slice。

### 9.2 current EP 与 buffered EP

HEU 维护一个 current EP 和一个 buffered EP。当前 EP 正在等待 scalar/vector slice 完成时，如果 VLIWPU 又给出一个 EP，HEU 可以把它放入 buffer。buffer 满时，HEU 才反压 VLIWPU。

当前实现只支持最多两个 vector EP slice 同时活跃：current 和 buffered。因此 HEU 使用 1-bit `ep_id` toggle 区分它们。VDU 的 `MaxOutstandingVecEPs=2` 与这个设计匹配。若未来扩展到更多 outstanding EP，必须同时扩宽 `ep_id` 和 VDU wait table。

HEU 的输入 ready 规则是：

```text
heu_vliwpu_execute_ready = !buffer_valid && !(outstanding && current_has_branch)
```

也就是说，如果 current EP 还没完成但没有 unresolved branch，HEU 允许再收一个 EP 放进 buffer；如果 current EP 含 branch/control，则不再接收后续 EP，防止错误路径上的 packet 进入 buffer。

### 9.3 EP acknowledge

Current EP 完成条件：

- scalar slice 不存在，或 `scalar_ep_done_i` 已返回。
- vector slice 不存在，或 `vector_ep_acknowledged_i` 返回且 id 匹配 current EP。
- 当前 scalar/vector dispatch valid 不再悬挂。

满足后，HEU 产生一拍 `heu_top_ep_acknowledged_o`。如果 buffer 中已有下一个 EP，HEU 将 buffer 提升为 current。

current 提升/清除时，HEU 同步更新：

- current scalar/vector outstanding bit。
- current vector `ep_id`。
- current branch/memory-order 标记。
- current scalar/vector register mask。
- buffer valid 与 buffer vector-sent 状态。

这些状态必须一起切换，否则 VDU 返回的 `vec_ep_acknowledged_id` 可能被错配到已经提升的 EP。

### 9.4 buffered vector early issue

如果 current EP 的 scalar side 卡住，而 buffer 中有 vector slice，HEU 可以提前把 buffered vector slice 发给 VDU。这个优化只提前 vector slice，不提前 scalar slice。

提前发射的安全条件包括：

- current EP 不能有未解析 branch/control。
- current EP 不能有标量 memory-ordering 指令，例如 load/store/FENCE/AMO/FP memory。
- buffered vector 读取的 GPR/FRF 不能依赖 current scalar write mask。
- current vector 若有 `vset rd!=x0` 等 scalar-visible vector write，buffered vector 不能读取或冲突写同一标量寄存器。
- compressed/不易精确分析的标量指令按保守 mask 处理。

因此 early issue 是受限、保守的跨 EP 重叠，不是乱序执行。

其中 memory-ordering 条件是 scalar/vector memory 正确性的第一道门：只要 current scalar slice 可能访问 memory，buffered vector slice 就不能提前进入 VDU。这样后一 EP 的 vector load/store 不会在 current scalar memory 之前形成 Ara request。压缩标量指令因无法在 HEU 精确展开，也按 memory/order 相关处理。

HEU 为 early issue 维护几类 mask：

- `current_scalar_write_mask` / `current_scalar_fpr_write_mask`：current scalar slice 可能写的 GPR/FRF。
- `current_vector_write_mask`：current vector slice 可能通过 `vset rd` 等路径写的标量寄存器。
- `buffer_vector_read_mask` / `buffer_vector_fpr_read_mask`：buffered vector snapshot scalar operand 时会读的 GPR/FRF。
- `buffer_vector_write_mask`：buffered vector 可能写的标量寄存器。

如果 buffered vector 读取 current 还没写完的标量寄存器，或 current/buffer 两个 vector scalar-visible write 互相冲突，就不 early issue。这样做牺牲部分并行机会，但能避免同 EP/跨 EP 的 operand snapshot 读到错误版本。

从 RTL 读这个模块时，建议抓住三组状态：

| 状态/信号 | 教学含义 |
|---|---|
| `outstanding_q` | current EP 是否仍在等待 scalar/vector slice 安全交付 |
| `buffer_valid_q` | 是否已经收下下一 EP，等待 current 完成或尝试 vector early issue |
| `current_vector_id_q` / `buffer_vector_id_q` | current/buffered vector slice 的 1-bit `ep_id` |
| `current_has_branch_q` | current EP 有未解析控制流，禁止继续接收或提前发射 |
| `current_has_scalar_mem_order_q` | current scalar slice 可能访问 memory，禁止 buffered vector memory 越过 |
| `current_scalar_write_mask_q` | current scalar slice 可能写的 GPR，用于挡住 buffered vector operand snapshot |
| `current_scalar_fpr_write_mask_q` | current scalar slice 可能写的 FPR，用于挡住 buffered vector FP operand snapshot |
| `current_vector_write_mask_q` | current vector slice 可能通过 `vset rd` 等路径写 scalar-visible 寄存器 |
| `buffer_vector_read_mask_q` / `buffer_vector_fpr_read_mask_q` | buffered vector snapshot 时会读的 scalar operand |
| `buffer_vector_can_issue` | 以上边界全部满足后，buffered vector 才允许提前送 VDU |

这组逻辑说明 HEU 的职责不是算出所有 RVV 寄存器依赖，而是保护标量状态版本、控制流和 scalar/vector memory-order 边界。真正的 vector register hazard 仍在 Ara sequencer 层处理，或者被 same-EP 软件承诺裁剪。

## 10. 真实标量后端：`hdv_scalar_backend.sv`

`hdv_scalar_backend` 是 HDV 专用标量后端，不是完整 CVA6 core。它复用 CVA6 的 decode/branch/FPU/mult 等部件思想，提供 HDV scalar slice 所需功能：寄存器文件、简单整数指令、多周期复杂指令、分支解析、标量 LSU、向量操作数服务、向量写回接收和 task exit。

当前顶层配置：

- `ScalarIssueWidth=3`
- `SimpleAluIssueWidth=2`
- 每个 EP 内最多同时消耗两条 simple ALU 指令和一条 complex lane 指令。

状态机包括：

| 状态 | 作用 |
|---|---|
| `IDLE` | 等 HEU 送入一个 scalar slice |
| `EXECUTE` | 扫描 EP 内剩余 scalar slot，执行 simple batch 或发起 complex op |
| `WAIT_MULT` | 等待乘法结果 |
| `WAIT_FPU` | 等待 FPU 结果 |
| `LSU_AR` | 对 load 发 AR，并用 load queue 收 R |
| `LSU_AW/LSU_W/LSU_B` | 对 store 依次发 AW/W 并等 B |
| `DONE` | 本 EP scalar slice 完成，输出 `scalar_ep_done_o` |
| `REDIRECT` | taken branch 后输出一拍 redirect |

`scalar_ready_o` 只在 `IDLE` 为 1，HEU 不会在标量后端还没完成上一个 scalar slice 时覆盖它。

### 10.1 寄存器与初始化

标量后端维护本地 XRF/FRF。`hdv_top` 通过参数提供 `InitialRa`、`InitialA0` 到 `InitialA7`、`InitialFa0` 等初始值。HDV kernel 的 task 参数通常通过这些初始寄存器注入。

后端还维护必要 CSR stub，例如 `vl` 状态，用于记录 Ara 返回的 granted VL。

### 10.2 simple batch

Simple batch 识别可在同周期完成的简单整数/地址类指令。它对 EP 内 slot 从低到高扫描，最多选择 `SimpleAluIssueWidth` 条 simple ALU 指令。选择时检查：

- 指令是否有效。
- 是否与同 batch 已选指令存在 RAW/WAW/order barrier。
- 是否读取了尚未写回的 `vset rd`。
- 是否超过 issue width。

被选中的 simple 指令在同周期计算结果并写回 XRF。未选中的指令留给后续周期或 complex lane 处理。

simple batch 的关键点是“只选择确定能无等待完成且不会破坏顺序的指令”。例如普通 `addi/add/sub/slli` 这类整数地址更新通常能进入 batch；若某条 simple 指令读了本 batch 前面刚要写的寄存器，或者与 complex lane 同周期读写冲突，就会被留到下一轮 `EXECUTE`。

可以把 simple batch 理解为“EP 内标量轻量并行提交”。它不是完整乱序执行，因为选择 batch 前会做本 batch 内的 RAW/WAW/order 检查。若一条 simple 指令读取另一条 simple 指令同周期才写的 rd，就不会被放进同一个 batch 里同时执行；若某条指令可能影响顺序，例如 memory、branch、复杂运算，则转到 complex lane 或形成 order barrier。

### 10.3 complex lane

Complex lane 处理不能 simple batch 完成的指令，包括：

- branch/jump。
- mult。
- FPU。
- load/store。
- 其他需要 CVA6 decode/ex unit 辅助的复杂标量指令。

如果 complex lane 当前指令读取 simple batch 同周期要写的寄存器，`complex_simple_raw_stall` 会让 complex lane 等待，避免读旧值。

复杂 lane 按 EP 内最低编号的未处理 slot 推进。它不是另一个乱序 issue queue，因此同一个 scalar slice 内的复杂指令仍保持软件顺序。simple batch 可以先消耗独立 simple slot，但涉及复杂 lane operand 的 RAW 会被 `complex_simple_raw_stall` 拦住。

这意味着 scalar backend 的正确性边界比较保守：复杂指令不在 EP 内乱序穿越；连续 scalar load 可以流水发 AR，但写回仍按 load queue 顺序；store 则一次一个等待 B response。这样做会牺牲一部分标量吞吐，但让 vector operand snapshot 更容易定义：当 scalar slice done 后，相关标量寄存器已经是确定版本。

### 10.4 分支解析与 loop 控制

标量后端执行 branch 后输出精确分支事件。Taken branch 通过 `hdv_top` redirect IPU；not-taken backward branch 产生 loop exit。Backward 判定在标量后端内部完成，顶层不再基于 PC/target 重新推断。

这一点保证 IPU loop replay 只由真实分支结果控制，而不是取指端猜测。

Taken branch 的处理分两步：`EXECUTE` 中解析出 `branch_target` 并锁存 `redirect_pending_q`，EP 进入 `DONE` 后再进入 `REDIRECT` 输出一拍 `redirect_valid_o/redirect_pc_o`。这样 branch redirect 与 scalar slice done 保持清晰边界，HEU/IPU 不会在 scalar 状态还没提交时看到 redirect。

### 10.5 标量 LSU 与 vector store ordering

标量后端有自己的 AXI master，经 `hdv_top` system AXI mux 接入内存。Load 侧使用小型 load queue，当前深度为 4。Store 按 AW/W/B 顺序推进。

如果 VDU 报告 `vec_store_inflight_i=1`，标量 load/store 不会越过未完成 vector store。这是保守的 vector-store 到 scalar-memory ordering 互锁，避免后续标量访存观察到错误顺序。

load queue 的实际逻辑是：在 `LSU_AR` 状态下，对 EP 内连续 load slot 连续发 AR；每个 AR 记录 rd、是否 FPR、byte offset 和扩展类型到 `ldq_*`。AXI same-id 返回保持顺序，R beat 到来时从 queue head 写回 XRF/FRF。状态机只有在没有更多 load 可发且 `ldq_count` drain 后，才离开 `LSU_AR`。这让 GEMM 这类 EP 内多条标量 load 能流水化，而后续依赖这些 load 的 vector operand snapshot 仍然只能在 `scalar_ep_done` 后看到新值。

store 不做类似 queue，而是走 `LSU_AW -> LSU_W -> LSU_B`。这是更保守的选择，因为 store 的可见顺序比 load 更容易影响后续 scalar/vector memory 行为。

### 10.6 vset RAW interlock

`vsetvli/vsetivli/vsetvl` 被分类为 vector 指令，进入 Ara。若 `rd!=x0`，Ara response 会把 granted VL 写回标量后端。为了防止后续标量指令在写回前读取旧 `rd`，VDU 输出：

- `vec_vset_inflight_i`
- `vec_vset_inflight_rd_i`

标量后端在 simple batch 和 complex lane 两处都检查这个 hazard。若当前标量指令读取该 rd，就等待写回。

### 10.7 向量操作数服务

VDU 发 vector request 前需要读取标量 rs1/rs2/frs1。标量后端提供组合式 operand service：

- `vec_operand_req_valid_i`
- `vec_operand_req_ready_o`
- `vec_rs1_addr_i/vec_rs2_addr_i/vec_frs1_addr_i`
- `vec_rs1_data_o/vec_rs2_data_o/vec_frs1_data_o`

当前 `vec_operand_req_ready_o=1`，VDU 可以在需要时读取 XRF/FRF 中的值。VDU 捕获这些值后，即使后续标量 EP 修改寄存器，也不会影响已经形成的 vector request。

### 10.8 向量到标量写回

VDU 接收 Ara response 后，若该 vector 指令产生 scalar-visible writeback，就通过：

- `vec_wb_valid_i`
- `vec_wb_rd_i`
- `vec_wb_data_i`
- `vec_wb_is_fpr_i`
- `vec_wb_is_vset_i`

写回 XRF/FRF。若是 `vset` 写回，同时更新本地 `vl` 相关状态。

vector writeback 与 simple/complex scalar 写回在同一个 `p_next` 里合并到 XRF/FRF。若 `vec_wb_valid_i` 写同一个 rd，它代表 Ara response 的 scalar-visible 结果，后续 scalar 指令读取该 rd 时应看到最新值。`vec_vset_inflight` 则负责防止写回到来前提前读。

### 10.9 task exit 与边界

当前后端支持把 `ret` 或 `ebreak` 解释为 task exit，具体由参数控制。它不是完整 CVA6 commit pipeline，也没有完整异常/CSR/特权级实现。它的设计目标是服务 HDV kernel 的 scalar slice，而不是运行任意用户态程序。

### 10.10 指令覆盖和保守处理

标量后端覆盖 HDV kernel 常见的 RV64I 地址/计数更新、branch/jump、M 扩展、F/D 浮点、标量 load/store、必要 CSR stub。它明确不是完整 Linux 用户态 core：

- 不实现完整特权级、异常委托和 page fault recovery。
- AMO/LR/SC 等不属于当前 HDV kernel 目标路径。
- FENCE/系统类指令更多作为保守边界处理，而不是完整微架构同步机制。
- 压缩指令在 HDV kernel 中通常由 `.option norvc` 避免；硬件遇到不易精确分析的 compressed 标量写 mask 会偏保守。

这种取舍使标量后端面积和复杂度低于完整 CVA6，同时保留 HDV kernel 需要的真实分支、真实寄存器值和真实标量访存。

## 11. 向量请求适配：`hdv_vec_dispatch_unit.sv`

VDU 把 HEU 的多 slot vector slice 变成 Ara 接口的一条条 accelerator request。它是 HDV 前端与 Ara 后端之间最关键的语义桥。

VDU 可以按四层来理解：

1. **EP 接收层**：接收 HEU 的 vector slice，必要时放到 pending skid。
2. **slot FSM 层**：按 slot 从低到高选择下一条 vector 指令，并准备 scalar operand。
3. **resolved command window 层**：保存已经拿到 operand、可以送 Ara 的 request。
4. **response/ack 层**：用 response metadata FIFO、real wait table 和 vset writeback 生成 scalar writeback 与 EP acknowledge。

### 11.1 输入 EP 与 slot 选择

VDU 接收：

- vector slot valid mask。
- 每个 slot 的 32-bit vector 指令。
- `ep_id`。
- EP-bundled prefetch hint。

它按 slot 从低到高选择下一条 vector 指令。IDLE 状态下可以在接收 EP 的同周期选择第一条指令，减少首条 request 延迟。

VDU 状态机包括：

| 状态 | 作用 |
|---|---|
| `IDLE` | 没有正在 dispatch 的 vector slice，可同周期接收 HEU 新 EP |
| `DISPATCH` | 逐 slot 处理当前 vector slice |
| `WAIT` | 当前 slice 已处理完，但还有 pending EP 或等待切换 |
| `DONE` | 结束过渡状态，回到 IDLE |

如果 VDU 不在 `IDLE` 但 HEU 又送来一个 vector EP，只要 `pending_valid_q=0` 且 real wait table 允许，就会进入 pending skid。这样 HEU 的 buffered vector early issue 不会因为 VDU 正在处理前一个 EP 而立即丢失机会。

### 11.2 标量操作数捕获

VDU 判断当前 vector 指令是否需要标量操作数：

- vector load/store base address 使用 rs1。
- strided load/store 使用 rs2 作为 stride。
- OPIVX/OPMVX 使用 integer scalar operand。
- OPFVF 使用 FP scalar operand。
- `vset*` 可能使用 rs1/rs2。

需要 operand 时，VDU 向标量后端请求并 snapshot 数据。这个 snapshot 是真实标量模式下 vector EP acknowledge 的前提。

VDU 还支持 next-slot operand prefetch：当前 slot dispatch 后，如果下一个 slot 也需要标量 operand，VDU 可以提前读取并保存，减少 EP 内连续 vector 指令的 operand 等待。

operand 有三种来源：

- 已经在 `operand_rs1_q/operand_rs2_q` 中保存的当前 slot operand。
- 当前周期从标量后端组合读口 bypass 的 operand。
- `next_operand_*_q` 中预取的下一 slot operand。

IDLE 同周期接收新 EP 时，VDU 不直接组合 bypass 新 EP 的 operand，而是至少经过当前 timing 规则允许的 capture 路径，避免跨 EP 的 scalar write/read 时序被同周期旁路破坏。进入 `DISPATCH` 后，组合读口可以为当前 slot 直接 bypass，减少等待。

### 11.3 resolved command window

VDU 在 FSM request 与 Ara `req_ready` 之间有一个顺序 command window。顶层当前传入深度为 12。每个 entry 是结构化 `vq_entry_t`，包含：

- vector instruction。
- 已捕获的 rs1/rs2。
- 完整 `hdv_meta`。
- command class：arith/load/store/config。
- 是否有 scalar-visible writeback。
- writeback 是否写 FPR。
- 是否为 EP 中最后一条 vector 指令。

这个 window 只保存已经 resolved 的 request，不是 reorder buffer。若 Ara ready，request 可以 bypass window 直发 Ara；若 Ara backpressure，request 进入 window，VDU 可以继续处理后续 slot，只要 window 未满。

window 的出入口规则是：

```text
vq_serving = vq_count != 0
vq_bypass  = !vq_serving && fsm_req_valid
vq_pop     = vq_serving && Ara accepted head
vq_push    = fsm_req_valid && !(bypass and accepted) && (!vq_full || vq_pop)
```

只要 window 非空，VDU 优先服务 head entry，保证送入 Ara 的 request 顺序不被后来的 bypass 打乱。`vq_push` 与 `vq_pop` 可以同周期发生，所以满窗口在同周期 pop 一项时仍可接收新 request。

这个 window 解决的是 Ara backpressure，不是指令重排。进入 window 的 request 已经完成三件事：选中具体 vector slot、捕获必要 scalar operand、绑定 HDV metadata。window 只允许在 Ara 暂时不 ready 时继续吸收后续 resolved request。服务端始终先送 head entry，因此不会因为 bypass 把后一条 vector request 送到前一条之前。

### 11.4 HDV metadata 形成

VDU 为每条 vector request 生成：

```systemverilog
hdv_valid          = 1'b1
ep_id              = selected_ep_id
prefetch_hint_valid= selected_prefetch_hint_valid
prefetch_disable   = selected_prefetch_disable
prefetch_mode      = selected_prefetch_mode
```

这些 metadata 随 command window entry 保存，也随 Ara request sideband 送入后端。VDU 同时把 `trans_id[0]` 设置为 `ep_id`，用于 response routing；`trans_id[1]` 标记 `vset* rd!=x0`，用于精确识别 vset writeback response。

### 11.5 response metadata 与 scalar-visible writeback

每条送往 Ara 的 request 都会在 response metadata FIFO 中记录：

- 是否产生 scalar-visible writeback。
- 是否写 FPR。
- 是否是 `vset`。
- 是否是 vector store。
- `rd`。
- `ep_id`。

Ara response 返回时，VDU 根据 metadata 判断是否写回标量后端、是否释放 vset wait、是否减少 store-inflight 状态。普通 vector arithmetic/load/store 的完成不会阻塞下一 EP 前端推进；Ara 后端自己维护 vector register 依赖和执行完成。

response metadata FIFO 是必须的，因为 Ara response 只回传 `trans_id` 和结果，不携带“这条指令是否是 store、是否写 FPR、rd 是谁”等完整上下文。VDU 在 request 被 Ara 接收时把这些 side-effect 信息入队，response 返回时从队头取出对应信息。由于 request 顺序保持不乱，FIFO 顺序和 response 顺序匹配。

### 11.6 real wait table 与 EP acknowledge

真实标量模式下，VDU 使用两项 wait table 跟踪 current/buffered vector EP：

- `real_wait_valid`
- `real_wait_id`
- `real_wait_has_vset`
- `real_ep_operands_captured`
- `real_ep_vset_wb_done`

当一个 EP 被接收时，VDU 分配一项。该 EP 所有 vector slot 都被 FSM 消费后，置 `operands_captured`。若该 EP 含 `vset rd!=x0`，还要等待对应 response 写回后置 `vset_wb_done`。当：

```text
operands_captured && (!has_vset || vset_wb_done)
```

成立，VDU 对 HEU 输出 `vec_ep_acknowledged_o` 和对应 `vec_ep_acknowledged_id_o`。

real wait table 深度为 2，对应 HEU current+buffer 两个可能 outstanding 的 vector EP。`vec_ep_ready_o` 不仅看 pending skid，还看 table 是否有安全空间：

```text
vec_ep_ready = !pending_valid && real_ep_can_acknowledge
```

其中 `real_ep_can_acknowledge` 要求 table 中不能全是未 safe 的 EP。这样防止 HEU 继续送入第三个 vector EP，超过 1-bit `ep_id` 可区分范围。

wait table 是理解 VDU acknowledge 的关键。每个有效项代表一个已经被 VDU 接收的 vector EP。该 EP 的 vector 指令可以继续在 Ara 中执行，但只要 VDU 已经把所有 vector slot 变成 resolved request，并且该 EP 需要的 `vset rd` 写回也已经处理，就可以通知 HEU “这个 EP 对前端来说安全”。因此 wait table 的 safe 条件不是 vector 指令完成，而是：

```text
所有 vector slot 的 scalar operand 已经 snapshot
&&
如果有 scalar-visible vset 写回，则该写回已到 scalar backend
```

这个定义让 HDV 可以提前推进下一 EP，同时仍避免后续标量代码读到旧的 `vl` 或让后续 scalar 修改污染已经形成的 vector request。

### 11.7 vector store 与 vset 互锁输出

`vec_store_inflight_o` 覆盖两类 store：

- 已送入 Ara、response metadata FIFO 中尚未返回的 vector store。
- 已进入 command window 但尚未送入 Ara 的 vector store。

这样关闭了 store 刚进入 command window、metadata 还没注册时的一拍空窗。

标量后端把这个信号作为 load/store 发射门禁。只要有 vector store 已经在 VDU/Ara 路径中可见，后续 scalar load/store 就停住，直到该 store response 返回并从 metadata FIFO 中释放。这个互锁不要求 VDU 等普通 vector store 完成后才 acknowledge EP；它只在真正可能影响 scalar memory 顺序的地方阻塞 scalar LSU。

`vec_scalar_vset_inflight_o` 从含 `vset rd!=x0` 的 EP 出现开始置位，到对应 vset response 返回后清除。标量后端用它阻止后续标量指令读取旧 granted VL。

### 11.8 VDU 为什么不等普通 vector 完成

VDU 若等待每条 vector arithmetic/load 完成才 acknowledge EP，会把 HDV 前端退化成“标量核逐条等向量完成”，失去 decoupling。当前 acknowledge 选择的是 operand-safety 边界：

- 对不写标量寄存器的 vector 指令，operand snapshot 后即可认为前端安全。
- 对 `vset rd!=x0`，因为会影响后续标量寄存器读，必须等 response 写回。
- 对 store，VDU 不阻塞 EP acknowledge，但通过 `vec_store_inflight_o` 约束后续标量 memory。

这不等于 VDU 证明同 EP 内所有 vector 指令之间都无真实依赖。VDU 只保证 scalar operand 版本已经固定、scalar-visible side effect 有互锁；vector register 之间是否允许被 same-EP hazard bypass 加速，取决于软件 p-bit 对同 EP 的承诺和 Ara sequencer 的 EP-aware 规则。若两条 vector 指令存在必须串行的真实寄存器依赖，就不应放在同一个 EP。

## 12. Ara 后端 HDV 扩展

### 12.1 `ara.sv`

Ara 顶层增加两个 HDV 输入：

- `hdv_loop_active_i`
- `hdv_meta_i`

`hdv_meta_i` 被打入内部 `ara_req_t.hdv_meta`。`hdv_loop_active_i` 进入 VLSU/addrgen，用于 prefetch 状态在 loop-active 下降沿清理。

Ara 顶层不解释 HDV header，也不重新计算 EP。它只把 VDU 已经形成的 `hdv_meta` 与当前 accelerator request 绑定。这样 metadata 的生命周期与指令生命周期一致：VDU 发哪条 RVV 指令，Ara 内部的 dispatcher/sequencer/VLSU 就看到同一条指令的 HDV 语义。

### 12.2 `ara_dispatcher.sv`

Ara dispatcher 接收 VDU 的 accelerator request，同时接收 `hdv_meta_i`。在生成内部 `ara_req` 时，它把 metadata 原样放入 `ara_req.hdv_meta`。这一步保持 HDV 语义与具体 vector instruction 对齐。

dispatcher 的主要职责仍是原 Ara 的 RVV 指令解码、VFU 选择、源/目的寄存器字段解析、`vl/vtype` 相关控制等。HDV 修改只是在 request 结构中加 sideband，不改变 dispatcher 对普通 RVV 语义的解释。也就是说，如果同一条 RVV 指令在非 HDV 模式进入 Ara，后端依赖逻辑仍能按原路径工作。

### 12.3 `ara_sequencer.sv`

Sequencer 对每个 running vector instruction slot 记录：

- `vid_ep_id_q`
- `vid_hdv_valid_q`

新 vector request 到来时，sequencer 先根据原有 read/write list 形成候选 RAW/WAR/WAW hazard。若候选 running instruction 与新 request 都有有效 HDV metadata，并且 `ep_id` 相同，则该候选 vid 不进入对应 hazard mask。RTL 对 RAW、WAR、WAW 三类候选都使用这个 same-EP 裁剪，而不是只裁掉 WAW/WAR。

这个机制是 EP-aware dependency handling，不是全局关闭 scoreboard。资源满、lane desync、队列 ready、特殊指令规则、真实跨 EP hazard 仍然按 Ara 原逻辑处理。特别是某些 slide 类指令仍保留额外阻塞规则。

同 EP hazard bypass 的目标是消除“软件已经承诺同一 EP 内可并行”的保守阻塞。例如同一 EP 内几条 vector 指令可能在寄存器命名上形成 conservative RAW/WAR/WAW 候选，但软件/前端已经用 p-bit 表示这些 slot 属于同一并行 packet。sequencer 看到 same `ep_id` 后，会对这些候选 vid 清 hazard mask；如果不是同 EP，或者任一方没有 `hdv_valid`，原 Ara hazard 仍然生效。

这也给软件/前端一个明确责任：同 EP 内不能包含真实需要 sequencer RAW/WAR/WAW 串行化的 vector register 依赖。需要串行化时，应在 HINT p-bit 上切断，或者利用 branch/system/issue-width 等硬边界让 VLIWPU 形成不同 EP。

这个改动的边界很重要：

- 它不让指令绕过 lane/operand queue 的 ready 条件。
- 它不绕过 VLSU 的 memory ordering。
- 它不把 slide/特殊指令的额外限制全部取消。
- 它依赖 HEU/VDU 保证当前最多两个 outstanding EP，且 `ep_id` 不会在仍有同 ID running instruction 时被第三个 EP 复用。

## 13. VLSU prefetch 设计

VLSU prefetch 是当前 HDV 后端协同中最复杂的部分。它由 `addrgen.sv`、`vldu.sv` 和 `vlsu.sv` 协同完成。

### 13.1 当前 prefetch 启用条件

`addrgen` 根据 `pe_req_d.hdv_meta` 计算 prefetch 状态：

- `prefetch_hint_valid=0`：关闭。
- `prefetch_disable=1`：关闭。
- `prefetch_mode=00`：1X。
- `prefetch_mode=01`：2X。
- `prefetch_mode=10`：4X。
- `prefetch_mode=11`：8X。
- loop-active 下降沿：关闭并清状态。

当前 prefetch 只针对 unit-stride load 的未来同流地址。Strided/gather/scatter 不走这条有效预取路径。

对硬件来说，“有 hint”与“显式关闭”是两个不同事件：

- `prefetch_hint_valid=0`：这条 request 没有软件提供的 prefetch 语义，计数/调试时属于 no-hint。
- `prefetch_hint_valid=1 && prefetch_disable=1`：软件明确判断这类访问不适合预取，例如不规则访问、多流冲突或窗口重叠。
- `prefetch_hint_valid=1 && prefetch_disable=0`：软件认为可按 `prefetch_mode` 预取未来同流地址。

这样区分后，调 kernel 时可以知道是“软件没标注”还是“软件故意关掉”。

### 13.2 地址距离

对一次 demand unit-stride load，addrgen 使用本次逻辑访问长度 `vreq_blen_d` 计算未来地址：

```text
prefetch_addr = demand_addr + (vreq_blen_d << prefetch_mul)
```

其中 `prefetch_mul` 分别为 0/1/2/3，对应 1X/2X/4X/8X。使用逻辑访问长度而不是 AXI 对齐后的覆盖长度，是为了避免 unaligned load 因总线对齐扩张而把预取地址推过真实下一轮 demand 地址。

enable 门是：

```text
AVL >= VL + (VL << prefetch_mul)
```

也就是 1X 至少需要 `2*VL`，2X 需要 `3*VL`，4X 需要 `5*VL`，8X 需要 `9*VL`。AVL 不够时，计数器中体现为 `pf_avl_low`。

这条门禁避免在最后一两轮循环仍发没有未来 demand 对应的 prefetch。它不是根据总字节数判断，而是根据 vector 语义中的 `AVL/VL` 判断“未来是否还有同类 vector 访问”。如果 kernel 的真实指针步长与 `prefetch_mode` 不匹配，即使 AVL 门满足，也可能不命中；这属于软件 hint 与访存模式不匹配，不是正确性错误。

教学上可以把 `prefetch_mode` 理解为“同一条 load 指令下一次出现时，地址比这次前进了几个本次访问长度”。设本次向量 load 覆盖字节数为 `B = VL * EEW`，同一条 `vle` 下一轮 demand 地址与当前 demand 地址的差为 `S`：

| 访问模式 | `S/B` | 合适 mode | 说明 |
|---|---:|---|---|
| 每轮同一条 `vle` 只前进一个向量 | 1 | 1X (`00`) | vsaxpy/vsdot/vvadd 这类最常见 |
| 每轮同一条 `vle` 跨过两个向量的数据 | 2 | 2X (`01`) | 常见于一次循环展开处理两组数据 |
| 每轮同一条 `vle` 跨过四个向量的数据 | 4 | 4X (`10`) | GEMM 某些 B load 展开后可能出现 |
| 每轮同一条 `vle` 跨过八个向量的数据 | 8 | 8X (`11`) | 更激进展开，只有确实匹配时才用 |
| 窗口重叠或 `S/B` 不是 2 的幂 | 不固定 | 关闭或只给稳定流开 | stencil/FIR 这类要逐条 load 判断 |

因此，mode 不等于 LMUL，也不等于 kernel 里有几条 load。它只描述“这一条 request 自己的未来地址距离”。同一个 kernel 中，不同 packet 可以因为 load 流不同而使用不同 hint，或者对不稳定流显式 `prefetch_disable=1`。

### 13.3 demand 优先与 same-id prefetch

Demand AR 始终优先使用 AXI read address 通道。Prefetch AR 只有在本周期没有 demand AR、AXI ready、队列/ROB/lookup 有空间、credit 允许、没有 flush pending 时才能发出。

当前 prefetch AR 使用 `AXI_ID_DEMAND`，与 demand 同 ID。为了区分返回 R burst 属于 demand 还是 prefetch，addrgen 在 AR 接受时维护 tag FIFO，vldu 按 R burst pop tag。这样保留 same-id in-order 返回的简单性，同时避免仅靠 AXI ID 区分。

same-id 设计的好处是 AXI 返回天然按同 ID 顺序，不需要在 vldu 里对 demand/prefetch R beat 做跨 ID reorder。代价是必须维护额外 burst tag，并且 prefetch 不能压住 demand：只要 demand AR 本周期可发，就优先 demand。这样即使 prefetch 失配或被限流，程序也能退回 demand-driven。

### 13.4 credit 与 store-aware pacing

addrgen 使用两个关键常量：

- `PrefetchBufBeats=128`
- `PrefetchLeadBeats=32`

Prefetch 发射前检查：

```text
resident_beats + inflight_beats + this_burst_beats <= PrefetchBufBeats
```

其中 resident 来自 vldu prefetch buffer occupancy。这个 credit 保证 prefetch R beat 返回时一定有 buffer 空间，不会把 demand R channel 反压到死锁。

当 vector store 长时间拿不到内存机会时，`store_stuck` 触发 store-aware pacing。此时 prefetch 不再无限领先，而是把 resident+inflight lead 控制在 `PrefetchLeadBeats` 附近，让单一内存端口给 store 留出机会。store 不饿死时，prefetch 可以更自由地跑。

credit 分两层：

- buffer credit：保证预取返回一定有地方写入 vldu prefetch buffer。
- lookup/ROB credit：保证完成的 prefetch 能登记地址并等待未来 demand 消费。

两层都满足才发 prefetch AR。只看 buffer 空间不够，因为 lookup FIFO 满时数据虽然进了 buffer，却没有可匹配的地址标签；只看 lookup 也不够，因为 R beat 返回时可能反压 data channel。

### 13.5 page-cross split

若 prefetch burst 跨 4KB page，addrgen 会生成第一段，并暂存第二段信息到 `second_prefetch_*`。第二段稍后入 prefetch AR queue。addrgen 同时记录 segment tag，prefetch 完成后 lookup FIFO 和 second-segment FIFO 同步 push/pop，保证跨页命中时 lookup 顺序正确。

page-cross 的难点不是发两个 AR，而是后续 demand hit 的描述符消费。一个逻辑 prefetch 可能对应两个 AXI burst，lookup FIFO 必须知道第二段是否属于同一次逻辑预取。否则 demand 命中第一段后，第二段 lookup 可能变成“孤儿标签”，后续 demand 会误匹配或被错误阻塞。

### 13.6 lookup、hit 与 demand 等待

Prefetch 完成后，addrgen 把 prefetch address 推入 lookup FIFO。后续 demand load 到来时，如果 demand 地址匹配 lookup FIFO head，则认为 prefetch hit：

- demand AR 不再发出。
- ldu addrgen queue entry 标记 `is_prefetch_hit`。
- vldu 从 prefetch buffer 取数据送入 result queue。

如果 demand 地址正好匹配已经进入 ROB/in-flight/return path 的 prefetch，demand 可以短暂等待对应 prefetch 完成。RTL 中有 demand-wait watchdog，若等待过长会 fatal，避免隐藏死锁。

这里要特别区分 **prefetch AR queue** 和 **prefetch ROB/in-flight**。AR queue 只是“准备发出的 prefetch 请求”，它还可能被 credit、lookup FIFO、ROB 空间或 store-aware pacing 卡住。当前 RTL 不会因为 demand 匹配一个仅在 AR queue 中的 prefetch 就阻塞 demand；否则 demand 可能被一个尚未真正进入内存系统的请求反向卡死。这个 queue match 仍会被计数/探针记录，用来诊断 prefetch 太晚，但它不是严格的 demand 等待条件。

因此 demand 到来时有几种情况：

| 情况 | 行为 |
|---|---|
| lookup head 地址等于 demand 地址 | 直接 hit，pop lookup，vldu 走 prefetch buffer |
| lookup FIFO 空，但同地址 prefetch 已进入 ROB/in-flight/return path | demand 等待短时间，等 prefetch 完成变成 hit |
| lookup FIFO 空，但同地址 prefetch 仅在 AR queue 中 | 不等待该 prefetch，demand 正常发 AR；若 prefetch 后续变 stale，由 stream-break/flush 处理 |
| lookup head 是比 demand 未来更远的近地址 | 暂时保留，避免把即将使用的数据错误 flush |
| lookup head 与 demand 明显分叉 | 触发 stream break，drain 后 flush lookup/buffer |
| 没有可用 prefetch | 发普通 demand AR |

这个策略是“优先使用确定匹配的预取；不确定时宁可退回 demand 或 flush”，避免把错误数据送进 VRF。

### 13.7 stream-break recovery

如果 demand stream 与 lookup FIFO head 明显不匹配，说明预取流和真实 demand 流分叉。例如 GEMM 重新回到同一 B 行开头，而 FIFO head 还保存上一段 over-prefetch tail。此时 addrgen：

1. 停止继续发新的 prefetch。
2. 等待 prefetch ROB 和 in-flight beats 排空。
3. 同周期 flush lookup FIFO 和 vldu prefetch buffer。
4. 之后恢复正常 demand-driven 或重新建立 prefetch 流。

这个机制保证错误预取不会永久堵住 FIFO，也不会让旧 prefetch 数据被误认为新 demand 数据。

stream-break 常见于软件访问流重启、矩阵 kernel 回到行首、或 prefetch mode 过大导致 tail 预取超过下一轮 demand。flush 之前必须等 ROB/in-flight beat 排空，是因为 vldu buffer 与 lookup FIFO 只保存“已经完成且可消费”的数据；如果还有 R beat 正在返回，同周期 flush 可能丢失后续 tag/data 对齐。

### 13.8 `vldu.sv` prefetch buffer

vldu 保存 prefetch R data。当前 buffer 是 64 个 256-bit word，使用 SRAM 宏或等价 tc_sram 实现。由于 AXI R beat 是 128-bit，vldu 使用 low-half latch，把两个 128-bit beat 组装成一个 256-bit word 写入 prefetch SRAM。

读出侧维护 head register 和 read pointer。prefetch hit descriptor 到达后，vldu 从 prefetch buffer 中取数据，按原有 lane/VRF byte shuffle 逻辑送入 result queue。hit path 按 AXI descriptor 的实际 len/bytes 消费，支持 unaligned 和 page-cross 分段场景，避免只按“一个 hit 一个描述符”导致 orphan descriptor。

vldu 并不重新判断“这次是不是 hit”。这个判断来自 addrgen descriptor 的 `is_prefetch_hit`。vldu 的职责是：

1. 对 prefetch R beat，按 tag 写入 prefetch buffer。
2. 对 demand R beat，走原 demand load path。
3. 对 hit descriptor，不等 AXI R beat，而是从 prefetch buffer 读出对应数据。
4. 对 `prefetch_buf_flush_i`，在 addrgen 确认无 in-flight 后清空已完成的 buffered prefetch 数据。

也就是说，addrgen 负责地址和时序正确性，vldu 负责数据保存和按 descriptor 消费。

### 13.9 `vlsu.sv` wrapper

`vlsu` 负责把 addrgen 与 vldu 的 prefetch sideband 接起来：

- `prefetch_axi_ar_hit`
- `prefetch_buf_flush`
- `axi_addrgen_prefetch_req`
- `prefetch_buf_occupancy`
- same-id burst tag head/empty/pop
- `stu_store_pending`
- `hdv_loop_active_i`

它本身不决定 prefetch 策略，策略在 addrgen，数据保存与消费在 vldu。

## 14. 仿真与 mock host

`hdv_mock_host_core.sv` 主要服务早期 bring-up 和仿真。它可以自动写 task CSR、模拟 scalar/vector latency、输出 mock branch redirect、统计 EP acknowledge，并提供 watchdog。当前完整路径默认使用真实 `hdv_scalar_backend` 和内部 VDU 到 Ara，不再依赖 mock host 模拟 vector backend 语义。

Mock host 仍有价值：

- 测试 TIU/TSU/IPU/VLIWPU/HEU 基本握手。
- 在不启用真实标量后端时验证 frontend packet 流。
- 提供 watchdog 和可控 mock branch 行为。

但论文或当前设计说明不应把 mock host 当作真实执行路径。

## 15. 性能计数器与调试探针

当前仿真中常用日志包括：

- `[PERF-HEU-EP]`：HEU 接收的 EP 数、EP 宽度、scalar/vector 指令数、混合 EP 数、issue slot 数和 prefetch hint 分布。
- `[PERF-HEU-FE]`：HEU 前端 valid/ready、buffer、branch、current/buffer outstanding 的周期级压力。
- `[PERF-HEU-OVLP]`：buffered vector early issue 的 attempt/grant/block 原因，以及 cross-EP inflight/overlap 周期。
- `[PERF-VDU-CMD]`：VDU 到 Ara 的 command valid/fire/blocked、command window occupancy、window full/empty。
- `[PERF-VDU-OPERAND]`：VDU scalar operand capture/bypass/lookahead、vector EP enqueue、vset visible wait。
- `[IPU-PERF]`：IPU fetch/serve/loop 相关计数。
- `[PERF-SEQ]`：sequencer block/hazard 相关计数。
- `[PERF-SEQ-LIFETIME]`：source-lifetime WAR 候选、边级释放和按命令去重的有效 relaxation 计数。
- `[PERF-ADDRGEN]`：demand/prefetch AR、hit、bytes、load/store 计数。
- `[PERF-ADDRGEN-PF]` / `[PERF-ADDRGEN-PF2]`：prefetch 被禁用、page cross、queue full、AVL low、ROB/lookup/pending 阻塞、late/unused/throttle 等原因。

这些日志分两类使用：

- **严格语义指标**：可以直接进入论文表格或图，例如 `task_cycles`、EP 数/宽度、vector command fire、demand/prefetch AR、prefetch hit、`war_relaxed_cmd_ratio`、vset visible wait。
- **诊断/压力指标**：用于解释瓶颈，但不要写成严格 stall breakdown，例如 queue full cycles、ready block cycles、early issue blocked reason、stream-break、future-keep、queue-match cycles。这些信号通常反映某个局部门禁在某周期为真，不一定互斥，也不一定能相加等于总停顿。

当前 sweep 汇总脚本会把各模块日志统一成 `paper_data.md` 中的字段。下面按 CSV 字段名列出含义；带 `ratio`、`per_cycle`、`avg`、`over` 或 `speedup` 的字段通常是脚本派生值，不是 RTL 中独立累加器。

### 15.1 汇总与性能对照字段

- `dataset`：数据集名称，例如 main real、main ideal 或 HDV representative metrics。
- `source`：生成该表的数据文件路径。
- `rows`：该数据源中的数据行数。
- `columns`：该数据源中的列数。
- `mtime`：源文件最后修改时间，用于追溯数据版本。
- `data`：`paper_data.md` 中代表点章节的列表容器，下面每个 `row_xx` 对应源 CSV 的一行。
- `kernel`：kernel 名称；在 HDV 表中是 HDV kernel 名，在对照表中是归一化后的显示名。
- `config`：代表点配置，例如 `AVL=1024`、`LMUL=4,N=128`。
- `main_real_cycles`：紧耦合 main real 模式的总周期，来自 main 分支 representative real CSV。
- `main_ideal_cycles`：main ideal 模式的总 RVV 周期，来自 main 分支 representative ideal CSV。
- `hdv_cycles`：HDV 本次代表点的 `task_cycles`。
- `hdv_result`：HDV 仿真结果，通常为 `PASSED`、`FAILED` 或没有对应新指标行。
- `speedup_vs_real`：`main_real_cycles / hdv_cycles` 的派生加速比。
- `speedup_vs_ideal`：`main_ideal_cycles / hdv_cycles` 的派生加速比。
- `hdv_over_real`：`hdv_cycles / main_real_cycles` 的派生归一化周期，越小越好。
- `hdv_over_ideal`：`hdv_cycles / main_ideal_cycles` 的派生归一化周期，越小越好。
- `raw_hdv_columns`：HDV 原始 CSV header 中的字段总数，用于检查文档和数据覆盖完整性。
- `covered_raw_columns`：已被 `paper_data.md` 分类表纳入展示的 HDV 原始字段数。
- `missing_raw_columns`：尚未被分类表覆盖的 HDV 原始字段名；为 `NONE` 时表示无遗漏。

### 15.2 HDV 顶层与旧有汇总字段

- `group`：sweep 分组，例如 `avl`、`blas`、`fixed`。
- `tag`：单点标签；BLAS/GEMM 点通常用于区分 LMUL、rows、N 等配置。
- `avl`：AVL sweep 点的向量长度；非 AVL sweep 时为 `NA`。
- `size`：固定规模或矩阵规模字段，具体含义由 kernel 决定。
- `rows`：GEMM/BLAS 类点中的行组数或 rows 配置。
- `n`：BLAS/GEMM 类点中的 N 维度。
- `result`：该 HDV 点的仿真结果。
- `task_cycles`：从任务开始到任务完成的总执行周期，是大多数归一化指标的分母。
- `cyc_per_elem`：脚本从 `task_cycles` 和元素数派生的每元素周期。
- `cyc_per_macc`：脚本从 `task_cycles` 和 MAC 数派生的每 MAC 周期。
- `wall_cycles`：仿真日志中任务外层观测到的 wall-clock cycle 计数，通常包含少量包装开销。
- `eps`：旧汇总字段中的 EP 数，保留用于兼容早期表格；新分析优先使用 `ep_count`。
- `vec_busy`：旧汇总中的向量忙碌计数；它是诊断信号，不应单独解释成完整后端利用率。
- `imem_outstanding`：IPU/取指侧观测到的 outstanding 取指请求或相关压力计数。
- `ep_ack`：HEU/VDU 路径收到的 EP acknowledge 计数。
- `ep_vset_ack`：与 vset/vl 可见性相关的 EP acknowledge 计数。
- `vq_push`：旧向量请求队列 push 次数。
- `vq_pop`：旧向量请求队列 pop 次数。
- `vq_max_occ`：旧向量请求队列最大占用。
- `vq_bypass`：旧向量请求队列 bypass 次数。
- `vq_full_stall`：旧向量请求队列 full 相关阻塞计数；是局部压力指标。
- `dispatch_slots`：VDU/dispatch 路径消耗的 dispatch slot 次数。
- `dispatch_cycles`：dispatch 路径处于相关状态的周期数。
- `fsm_could_bypass`：VDU FSM 观察到可走 bypass 路径的机会数。
- `operand_wait_cycles_raw`：早期 operand wait 原始计数，保留作兼容；严格语义优先看 `scalar_operand_wait_cycles`。
- `ara_backpressure_cycles`：Ara 后端对 VDU/HDV 请求路径施加 backpressure 的周期数；它是压力签名，不和其它 stall 项互斥。
- `real_wait_stall`：旧汇总中真实等待相关 stall 计数，主要用于调试。
- `resp_meta_stall`：VDU response metadata 资源导致的局部 stall 周期。
- `resp_meta_max`：response metadata 队列最大占用。

### 15.3 EP 形成与指令供给字段

- `ep_count`：HEU 实际接收并推进的 EP 数量。
- `packed_inst_count`：被打包进入 EP 的有效业务指令总数，不包含 HINT header、NOP 或无效 slot。
- `packed_scalar_inst_count`：EP 中的标量业务指令数，包括地址更新、循环控制、标量计算和分支等。
- `packed_vector_inst_count`：EP 中的向量业务指令数，即后续可能进入 VDU/Ara 的 vector slice 数。
- `ep_width_sum`：所有 EP 的有效业务指令数总和，用于派生平均 EP 宽度。
- `ep_width_gt1_count`：宽度大于 1 的 EP 数量，用于判断是否退化为逐条执行。
- `ep_scalar_vector_count`：同时含 scalar slice 和 vector slice 的 EP 数量。
- `used_issue_slots`：EP 中被有效业务指令占用的 issue slot 总数。
- `available_issue_slots`：这些 EP 在硬件最大宽度下理论可用的 issue slot 总数。
- `avg_ep_width`：`ep_width_sum / ep_count` 的派生平均 EP 宽度。
- `non_singleton_ep_ratio`：`ep_width_gt1_count / ep_count` 的派生宽 EP 占比。
- `mixed_ep_ratio`：`ep_scalar_vector_count / ep_count` 的派生混合 EP 占比。
- `slot_utilization`：`used_issue_slots / available_issue_slots` 的派生 slot 利用率。
- `packed_inst_per_cycle`：`packed_inst_count / task_cycles` 的派生前端有效指令供给吞吐。

### 15.4 HEU、prefetch hint 分布与跨 EP 重叠字段

- `heu_to_current`：HEU 将新 EP 放入 current 执行槽的次数。
- `heu_to_buffer`：HEU 将新 EP 放入 buffered EP 槽的次数。
- `heu_scalar_only`：只包含 scalar-side work 的 EP 数。
- `heu_vector_only`：只包含 vector-side work 的 EP 数。
- `heu_pf_hint_ep`：带有效 prefetch hint 的 EP 数。
- `heu_pf_disable_ep`：软件显式关闭 prefetch 的 EP 数。
- `heu_pf_mode_1x`：prefetch hint 选择 1X 距离的 EP 数。
- `heu_pf_mode_2x`：prefetch hint 选择 2X 距离的 EP 数。
- `heu_pf_mode_4x`：prefetch hint 选择 4X 距离的 EP 数。
- `heu_pf_mode_8x`：prefetch hint 选择 8X 距离的 EP 数。
- `heu_valid_cyc`：HEU 前端 valid 或内部有待推进 EP 的周期数。
- `heu_ready_block_cyc`：HEU valid 但下游或内部条件使其不能推进的周期数；是局部压力指标。
- `heu_block_buffer_cyc`：buffered EP 槽占用导致 HEU 不能接收/推进的周期数。
- `heu_block_branch_cyc`：未解析分支或控制边界导致 HEU 不能推进的周期数。
- `heu_current_busy_cyc`：current EP 槽仍忙的周期数。
- `heu_buffer_valid_cyc`：buffered EP 槽有效的周期数。
- `heu_scalar_out_cyc`：HEU scalar-side 输出路径活跃或待发的周期数。
- `heu_vector_out_cyc`：HEU vector-side 输出路径活跃或待发的周期数。
- `early_issue_attempts`：buffered vector early issue 被考虑尝试的次数。
- `early_issue_grants`：通过安全检查并实际允许 buffered vector early issue 的次数。
- `early_issue_blocked_by_dispatch`：已有 vector dispatch 占用输出路径导致 early issue 未发出；它不是队列满语义。
- `early_issue_blocked_by_queue`：因 command window、VDU 接收侧、后端 ready 或 vector queue 资源不足导致 early issue 被阻止的次数。
- `early_issue_blocked_by_branch`：因前序 EP 存在未解析 branch/control 不确定性导致 early issue 被阻止的次数。
- `early_issue_blocked_by_scalar_mem`：因 scalar memory 或 memory-order 约束导致 early issue 被阻止的次数。
- `early_issue_blocked_by_dependency`：因跨 EP 依赖汇总条件导致 early issue 被阻止的次数。
- `early_issue_blocked_by_gpr_dependency`：因 GPR 相关性导致 early issue 被阻止的次数。
- `early_issue_blocked_by_fpr_dependency`：因 FPR 相关性导致 early issue 被阻止的次数。
- `early_issue_blocked_by_vector_dependency`：因 vector/config 相关性导致 early issue 被阻止的次数。
- `cross_ep_inflight_cycles`：多个 EP 同时处于 HEU/VDU 后端管理域的周期数。
- `overlap_cycles`：标量侧 outstanding 与向量侧 outstanding 在同周期重叠的周期数。

### 15.5 VDU command window、队列压力与标量操作数字段

- `vector_cmd_valid_cycles`：VDU 有有效 vector command 等待发送到 Ara 的周期数。
- `vector_cmd_fire_count`：VDU 与 Ara 后端完成 valid/ready 握手的 vector command 数量。
- `vector_cmd_blocked_cycles`：VDU 有有效 vector command 但 Ara/下游未 ready 的周期数。
- `vector_cmd_per_cycle`：`vector_cmd_fire_count / task_cycles` 的派生向量命令投放吞吐。
- `cmd_window_avg_occ`：`cmd_window_sum_occ / cmd_window_sample_cycles` 的派生 command window 平均占用。
- `cmd_window_sum_occ`：command window 占用采样值之和。
- `cmd_window_sample_cycles`：command window occupancy 的采样周期数。
- `cmd_window_max_occ`：command window 最大占用。
- `cmd_window_full_cycles`：command window 满的周期数；它表示窗口资源压力，不等价于全系统 stall。
- `cmd_window_empty_cycles`：command window 为空的周期数；它只描述 VDU window，不等价于整个向量后端空闲。
- `cmd_window_full_ratio`：`cmd_window_full_cycles / task_cycles` 的派生窗口满占比。
- `vq_avg_occ`：向量请求队列平均占用；脚本从队列 occupancy 采样派生。
- `vq_empty_cycles`：向量请求队列为空的周期数，是供给连续性的诊断信号。
- `vq_full_cycles`：向量请求队列满的周期数，是后端消费压力诊断信号。
- `vq_full_ratio`：`vq_full_cycles / task_cycles` 的派生队列满占比。
- `resp_meta_sum_occ`：VDU response metadata 队列 occupancy 采样值之和。
- `resp_meta_sample_cycles`：response metadata occupancy 的采样周期数。
- `scalar_operand_capture_count`：VDU 成功捕获 vector slice 所需标量操作数的次数。
- `scalar_operand_bypass_hit`：标量操作数通过 lookahead/bypass 提前命中的次数。
- `scalar_operand_wait_cycles`：因标量操作数尚未就绪导致 VDU 不能推进当前 vector command 的周期数。
- `vset_visible_wait_cycles`：因等待 `vset/vl` 标量可见结果导致前端/VDU 不能推进的周期数。
- `scalar_operand_bypass`：VDU dispatch 阶段使用同周期标量 bypass 的次数。
- `scalar_operand_lookahead_req`：VDU 发起 next-slot scalar operand lookahead 读取的次数。
- `scalar_operand_lookahead_hit`：next-slot scalar operand lookahead 被后续 vector slot 使用的次数。
- `scalar_operand_port_busy`：标量 operand 读端口或服务路径忙导致的局部压力计数。
- `vector_ep_enqueue`：vector EP 被放入 VDU 处理路径的次数。
- `vector_ep_pending_enqueue`：vector EP 因 pending 条件进入等待/挂起路径的次数。
- `vector_ep_ready_block`：vector EP 因 VDU 接收侧 not-ready 被阻止入队或推进的次数。
- `ipu_ready_cyc`：IPU/前端供给路径 ready 的周期数。
- `ipu_ready_stall`：IPU/前端 ready 相关阻塞周期。
- `ipu_sram_stall`：IPU SRAM 访问或取指 buffer 相关阻塞周期。
- `ipu_serve_cyc`：IPU 向后级提供 instruction packet 的周期数。

### 15.6 VLSU demand、prefetch 与 memory 诊断字段

- `packets`：addrgen/VLSU 侧观测到的访存 packet 或请求片段数量。
- `bypass_hits`：VLSU/addrgen 局部 bypass 或快速路径命中的次数。
- `demand_reads`：真实 demand read 数据返回或消费相关计数。
- `avg_cyc_per_pkt`：脚本从周期和 packet 数派生的每 packet 周期。
- `demand_ar`：demand load 产生的真实 AXI AR 请求数。
- `pf_ar`：prefetch 产生并被接受的 AXI AR 请求数。
- `pf_hit`：后续 demand request 命中已完成或可等待 prefetch 的次数。
- `loads`：向量 load 指令或 load 请求相关计数。
- `pf_hit_rate`：`pf_hit / pf_ar` 的派生命中率；`pf_ar=0` 时为 `NA`。
- `pf_coverage`：`pf_hit / demand_ar` 的派生覆盖率；它表示 demand AR 中有多少被 prefetch 覆盖。
- `pf_late`：demand 到来时存在同地址 prefetch 已发出但数据尚未 ready 的次数。
- `pf_late_rate`：`pf_late / pf_ar` 的派生 late 占比。
- `pf_unused`：prefetch 发出后到 stream-break、drain、entry 清理或任务结束仍未被 demand 使用的 entry 数。
- `pf_unused_rate`：`pf_unused / pf_ar` 的派生未使用占比。
- `pf_en_cyc`：addrgen 判断当前上下文 prefetch enable 的周期数。
- `demand_aw`：demand store 产生的 AXI AW 请求数。
- `demand_B`：demand 访存字节数或 beat 字节量累计，具体来自 addrgen 统计口径。
- `pf_B`：prefetch 访存字节数或 beat 字节量累计。
- `pf_ar_rob_full`：prefetch 因 ROB 没有可用 entry 而不能发 AR 的事件或周期计数。
- `pf_ar_lkup_full`：prefetch 因 lookup FIFO 没有可用 entry 而不能发 AR 的事件或周期计数。
- `pf_ar_pending`：prefetch 因已有同流 pending/in-flight 状态而不能发 AR 的计数。
- `pf_ar_dis`：prefetch 因软件关闭、模式不适配或门禁条件关闭而未发 AR 的计数。
- `pf_2nd`：page-cross 或 split prefetch 的第二段请求计数。
- `dem_rob_block`：demand 侧因 ROB/相关资源不可用被阻塞的计数。
- `pf_disabled`：prefetch 被显式关闭或未启用的次数。
- `pf_page_cross`：prefetch 地址跨 4KB page 需要拆分处理的次数。
- `pf_queue_full`：prefetch AR queue 满导致不能接收新 prefetch 的计数。
- `pf_avl_low`：剩余 AVL 不足以保证未来同流 demand，因而抑制 prefetch 的计数。
- `pf_throttled_cycles`：prefetch 因 credit、队列、pending、store pacing 等局部门禁被抑制的周期数。
- `pf_wait_match_cyc`：demand 等待同地址 in-flight prefetch 变为可命中的周期数。
- `pf_wait_match_evt`：demand 进入等待同地址 in-flight prefetch 的事件数。
- `pf_queue_valid_cyc`：prefetch AR queue 有有效请求的周期数。
- `pf_queue_block_cyc`：prefetch AR queue 有请求但受下游门禁不能发出的周期数。
- `pf_lkup_full_cyc`：lookup FIFO full 造成 prefetch 受限的周期数。
- `pf_rob_full_cyc`：prefetch ROB full 造成 prefetch 受限的周期数。
- `pf_pending_cyc`：prefetch pending/in-flight 限制为真的周期数。
- `pf_stream_break`：addrgen 判断 prefetch stream 与 demand stream 分叉并触发清理的次数。
- `pf_future_keep`：addrgen 判断 prefetch 仍可能被未来 demand 使用而保留的次数。
- `pf_queue_match_cyc`：demand 地址与 prefetch AR queue 中尚未发出的请求匹配的周期数；它只说明 prefetch 太晚或仍在队列中，不会单独让 demand 等待。
- `pf_rob_match_cyc`：demand 地址与 prefetch ROB/in-flight entry 匹配的周期数。
- `pf_page_wait_cyc`：page-cross 或分段 prefetch 相关等待周期。

### 15.7 Sequencer 与 hazard 语义消费字段

- `seq_issue`：Ara sequencer 成功 issue 的 vector instruction/request 数。
- `seq_blocked_cycles`：sequencer 处于 blocked 状态的周期数；包含多类局部原因，不是互斥 stall breakdown。
- `seq_blocked_ratio`：`seq_blocked_cycles / task_cycles` 的派生阻塞占比。
- `seq_raw_cycles`：RAW 候选相关阻塞条件为真的周期数。
- `seq_war_cycles`：WAR 候选相关阻塞条件为真的周期数。
- `seq_waw_cycles`：WAW 候选相关阻塞条件为真的周期数。
- `seq_waw_block`：WAW block 条件触发或保持的计数。
- `seq_full`：sequencer 或后端队列 full 相关局部压力计数。
- `hazard_check_count`：sequencer 执行相关性检查的总次数。
- `seq_true_hazard_stall`：请求未获接受且存在 RAW 条件的周期数；它可能与其它局部阻塞原因重叠。
- `seq_false_hazard_stall`：请求未获接受、没有 RAW、但存在 WAR 或 WAW 条件的周期数。字段名为兼容旧数据保留；它不证明该相关一定是“假相关”。
- `seq_queue_full_stall`：sequencer/后端队列 full 导致的 stall 计数。
- `seq_lane_desync_stall`：lane 同步或 lane desync 相关条件导致的 stall 计数。
- `seq_operand_req_stall`：operand request 或 operand 服务路径导致 sequencer 受限的计数。
- `seq_wait_state_cyc`：sequencer wait state 持续周期。
- `seq_mem_wait_cyc`：sequencer 因 memory wait 状态受限的周期数。
- `src_capture_done_count`：所有 lane 均完成某条 eligible vector instruction 的源操作数读取后，source-lifetime 状态转为 released 的指令数。
- `war_candidate_count`：新 writer 到达时，其目的寄存器在 read list 中对应的在飞 reader 边数。该计数按边累计。
- `war_pruned_count`：source-lifetime 在 writer 到达时省去的 WAR 候选边，加上 writer 在飞期间被释放的 WAR-only 边。该计数按边累计；同一 writer 可贡献多次。
- `war_arrival_pruned_count`：新 writer 到达时，因对应 reader 已完成源读取而未形成的 WAR 边数。若同一前驱仍构成 RAW/WAW，旧调试字段仍会累计该 WAR 分量。
- `war_release_edge_count`：writer 在飞期间，reader 完成全部源读取后从 global hazard row 清除的纯 WAR 边数；RAW/WAW 与 WAR 重合的边不在此列。
- `war_relaxed_cmd_count`：source-lifetime 至少一次真正缩小有效 predecessor hazard 集合的 sequencer command 数，每条 command 最多计一次。到达时只有未被同一前驱 RAW/WAW 覆盖且前驱仍在飞的剪除才有效；运行期只接受纯 WAR 边释放。
- `war_cmd_total_count`：sequencer 接收并分配 `vid` 的 command 总数，是 `war_relaxed_cmd_ratio` 的严格分母。
- `war_relaxed_cmd_ratio`：`war_relaxed_cmd_count / war_cmd_total_count`。图中可简写为 **WAR-Relaxed Cmds**；它表示 source-lifetime 机制触及并有效缩小 hazard 集合的命令占比，不等价于周期收益或 stall reduction。没有有效剪除时取 0，而不是 `NA`。
- `release_lead_vid_cycles`：source 已 released 但对应 vector instruction 仍在飞的 `vid × cycle` 累计值，用于观察 source completion 与整条指令完成之间的时间窗口。
- `war_prune_rate`：`war_pruned_count / war_candidate_count` 的旧边级诊断比率。它衡量候选 WAR 边被处理的比例，可能因 fanout 和重复边累计而饱和；`war_candidate_count=0` 时为 `NA`，不建议作为主图唯一指标。

### 15.8 Main real/ideal baseline 字段

这些字段来自 `/home/wangwy/openproject/ara_main/hardware/kernel_sweep_out_representative/` 下的 main real/ideal CSV。它们用于和 HDV 代表点做性能与后端压力对照；其中 lane/bank 类字段是 Ara 后端诊断计数，和 HDV counter 不构成逐项一一对应。

- `blas_lmul`：main BLAS kernel 编译/运行使用的 LMUL 配置。
- `gemm_rows`：main GEMM kernel 的 row blocking/row group 配置。
- `status`：main representative 仿真状态，通常为 `OK`。
- `IPC`：main real 模式中统计得到的 scalar core IPC。
- `ara_req_blocked_cycles`：main 中 Ara 请求接口 valid 但未被后端接受的周期数。
- `ara_req_fire_count`：main 中 Ara 请求接口完成 valid/ready 握手的请求数。
- `ara_req_valid_cycles`：main 中 Ara 请求接口 valid 为真的周期数。
- `cva6-d$-stalls`：CVA6 数据 cache stall 计数。
- `cva6-i$-stalls`：CVA6 指令 cache stall 计数。
- `cva6-sb-full`：CVA6 store buffer full 相关 stall 计数。
- `duration`：仿真输出的 wall-clock 仿真时间字符串。
- `hw-cycles`：main representative 日志中的硬件周期数。
- `lane utilization`：Ara lane 平均利用率。
- `lane0 bank0_conflict_ratio`：lane 0 中 bank 0 的 bank conflict ratio。
- `lane0 bank0_total_conflicts`：lane 0 中 bank 0 的 bank conflict 总次数。
- `lane0 bank0_total_requests`：lane 0 中 bank 0 的 bank request 总次数。
- `lane0 bank1_conflict_ratio`：lane 0 中 bank 1 的 bank conflict ratio。
- `lane0 bank1_total_conflicts`：lane 0 中 bank 1 的 bank conflict 总次数。
- `lane0 bank1_total_requests`：lane 0 中 bank 1 的 bank request 总次数。
- `lane0 bank2_conflict_ratio`：lane 0 中 bank 2 的 bank conflict ratio。
- `lane0 bank2_total_conflicts`：lane 0 中 bank 2 的 bank conflict 总次数。
- `lane0 bank2_total_requests`：lane 0 中 bank 2 的 bank request 总次数。
- `lane0 bank3_conflict_ratio`：lane 0 中 bank 3 的 bank conflict ratio。
- `lane0 bank3_total_conflicts`：lane 0 中 bank 3 的 bank conflict 总次数。
- `lane0 bank3_total_requests`：lane 0 中 bank 3 的 bank request 总次数。
- `lane0 bank4_conflict_ratio`：lane 0 中 bank 4 的 bank conflict ratio。
- `lane0 bank4_total_conflicts`：lane 0 中 bank 4 的 bank conflict 总次数。
- `lane0 bank4_total_requests`：lane 0 中 bank 4 的 bank request 总次数。
- `lane0 bank5_conflict_ratio`：lane 0 中 bank 5 的 bank conflict ratio。
- `lane0 bank5_total_conflicts`：lane 0 中 bank 5 的 bank conflict 总次数。
- `lane0 bank5_total_requests`：lane 0 中 bank 5 的 bank request 总次数。
- `lane0 bank6_conflict_ratio`：lane 0 中 bank 6 的 bank conflict ratio。
- `lane0 bank6_total_conflicts`：lane 0 中 bank 6 的 bank conflict 总次数。
- `lane0 bank6_total_requests`：lane 0 中 bank 6 的 bank request 总次数。
- `lane0 bank7_conflict_ratio`：lane 0 中 bank 7 的 bank conflict ratio。
- `lane0 bank7_total_conflicts`：lane 0 中 bank 7 的 bank conflict 总次数。
- `lane0 bank7_total_requests`：lane 0 中 bank 7 的 bank request 总次数。
- `lane0 hp_block_lp`：lane 0 中 high-priority request 阻塞 low-priority request 的计数。
- `lane0 total_bank_conflicts`：lane 0 所有 bank conflict 总次数。
- `lane0 total_bank_requests`：lane 0 所有 bank request 总次数。
- `lane0 total_hp_bank_conflicts`：lane 0 high-priority bank conflict 总次数。
- `lane0 total_hp_bank_requests`：lane 0 high-priority bank request 总次数。
- `lane0 total_lp_bank_conflicts`：lane 0 low-priority bank conflict 总次数。
- `lane0 total_lp_bank_requests`：lane 0 low-priority bank request 总次数。
- `lane1 bank0_conflict_ratio`：lane 1 中 bank 0 的 bank conflict ratio。
- `lane1 bank0_total_conflicts`：lane 1 中 bank 0 的 bank conflict 总次数。
- `lane1 bank0_total_requests`：lane 1 中 bank 0 的 bank request 总次数。
- `lane1 bank1_conflict_ratio`：lane 1 中 bank 1 的 bank conflict ratio。
- `lane1 bank1_total_conflicts`：lane 1 中 bank 1 的 bank conflict 总次数。
- `lane1 bank1_total_requests`：lane 1 中 bank 1 的 bank request 总次数。
- `lane1 bank2_conflict_ratio`：lane 1 中 bank 2 的 bank conflict ratio。
- `lane1 bank2_total_conflicts`：lane 1 中 bank 2 的 bank conflict 总次数。
- `lane1 bank2_total_requests`：lane 1 中 bank 2 的 bank request 总次数。
- `lane1 bank3_conflict_ratio`：lane 1 中 bank 3 的 bank conflict ratio。
- `lane1 bank3_total_conflicts`：lane 1 中 bank 3 的 bank conflict 总次数。
- `lane1 bank3_total_requests`：lane 1 中 bank 3 的 bank request 总次数。
- `lane1 bank4_conflict_ratio`：lane 1 中 bank 4 的 bank conflict ratio。
- `lane1 bank4_total_conflicts`：lane 1 中 bank 4 的 bank conflict 总次数。
- `lane1 bank4_total_requests`：lane 1 中 bank 4 的 bank request 总次数。
- `lane1 bank5_conflict_ratio`：lane 1 中 bank 5 的 bank conflict ratio。
- `lane1 bank5_total_conflicts`：lane 1 中 bank 5 的 bank conflict 总次数。
- `lane1 bank5_total_requests`：lane 1 中 bank 5 的 bank request 总次数。
- `lane1 bank6_conflict_ratio`：lane 1 中 bank 6 的 bank conflict ratio。
- `lane1 bank6_total_conflicts`：lane 1 中 bank 6 的 bank conflict 总次数。
- `lane1 bank6_total_requests`：lane 1 中 bank 6 的 bank request 总次数。
- `lane1 bank7_conflict_ratio`：lane 1 中 bank 7 的 bank conflict ratio。
- `lane1 bank7_total_conflicts`：lane 1 中 bank 7 的 bank conflict 总次数。
- `lane1 bank7_total_requests`：lane 1 中 bank 7 的 bank request 总次数。
- `lane1 hp_block_lp`：lane 1 中 high-priority request 阻塞 low-priority request 的计数。
- `lane1 total_bank_conflicts`：lane 1 所有 bank conflict 总次数。
- `lane1 total_bank_requests`：lane 1 所有 bank request 总次数。
- `lane1 total_hp_bank_conflicts`：lane 1 high-priority bank conflict 总次数。
- `lane1 total_hp_bank_requests`：lane 1 high-priority bank request 总次数。
- `lane1 total_lp_bank_conflicts`：lane 1 low-priority bank conflict 总次数。
- `lane1 total_lp_bank_requests`：lane 1 low-priority bank request 总次数。
- `lane2 bank0_conflict_ratio`：lane 2 中 bank 0 的 bank conflict ratio。
- `lane2 bank0_total_conflicts`：lane 2 中 bank 0 的 bank conflict 总次数。
- `lane2 bank0_total_requests`：lane 2 中 bank 0 的 bank request 总次数。
- `lane2 bank1_conflict_ratio`：lane 2 中 bank 1 的 bank conflict ratio。
- `lane2 bank1_total_conflicts`：lane 2 中 bank 1 的 bank conflict 总次数。
- `lane2 bank1_total_requests`：lane 2 中 bank 1 的 bank request 总次数。
- `lane2 bank2_conflict_ratio`：lane 2 中 bank 2 的 bank conflict ratio。
- `lane2 bank2_total_conflicts`：lane 2 中 bank 2 的 bank conflict 总次数。
- `lane2 bank2_total_requests`：lane 2 中 bank 2 的 bank request 总次数。
- `lane2 bank3_conflict_ratio`：lane 2 中 bank 3 的 bank conflict ratio。
- `lane2 bank3_total_conflicts`：lane 2 中 bank 3 的 bank conflict 总次数。
- `lane2 bank3_total_requests`：lane 2 中 bank 3 的 bank request 总次数。
- `lane2 bank4_conflict_ratio`：lane 2 中 bank 4 的 bank conflict ratio。
- `lane2 bank4_total_conflicts`：lane 2 中 bank 4 的 bank conflict 总次数。
- `lane2 bank4_total_requests`：lane 2 中 bank 4 的 bank request 总次数。
- `lane2 bank5_conflict_ratio`：lane 2 中 bank 5 的 bank conflict ratio。
- `lane2 bank5_total_conflicts`：lane 2 中 bank 5 的 bank conflict 总次数。
- `lane2 bank5_total_requests`：lane 2 中 bank 5 的 bank request 总次数。
- `lane2 bank6_conflict_ratio`：lane 2 中 bank 6 的 bank conflict ratio。
- `lane2 bank6_total_conflicts`：lane 2 中 bank 6 的 bank conflict 总次数。
- `lane2 bank6_total_requests`：lane 2 中 bank 6 的 bank request 总次数。
- `lane2 bank7_conflict_ratio`：lane 2 中 bank 7 的 bank conflict ratio。
- `lane2 bank7_total_conflicts`：lane 2 中 bank 7 的 bank conflict 总次数。
- `lane2 bank7_total_requests`：lane 2 中 bank 7 的 bank request 总次数。
- `lane2 hp_block_lp`：lane 2 中 high-priority request 阻塞 low-priority request 的计数。
- `lane2 total_bank_conflicts`：lane 2 所有 bank conflict 总次数。
- `lane2 total_bank_requests`：lane 2 所有 bank request 总次数。
- `lane2 total_hp_bank_conflicts`：lane 2 high-priority bank conflict 总次数。
- `lane2 total_hp_bank_requests`：lane 2 high-priority bank request 总次数。
- `lane2 total_lp_bank_conflicts`：lane 2 low-priority bank conflict 总次数。
- `lane2 total_lp_bank_requests`：lane 2 low-priority bank request 总次数。
- `lane3 bank0_conflict_ratio`：lane 3 中 bank 0 的 bank conflict ratio。
- `lane3 bank0_total_conflicts`：lane 3 中 bank 0 的 bank conflict 总次数。
- `lane3 bank0_total_requests`：lane 3 中 bank 0 的 bank request 总次数。
- `lane3 bank1_conflict_ratio`：lane 3 中 bank 1 的 bank conflict ratio。
- `lane3 bank1_total_conflicts`：lane 3 中 bank 1 的 bank conflict 总次数。
- `lane3 bank1_total_requests`：lane 3 中 bank 1 的 bank request 总次数。
- `lane3 bank2_conflict_ratio`：lane 3 中 bank 2 的 bank conflict ratio。
- `lane3 bank2_total_conflicts`：lane 3 中 bank 2 的 bank conflict 总次数。
- `lane3 bank2_total_requests`：lane 3 中 bank 2 的 bank request 总次数。
- `lane3 bank3_conflict_ratio`：lane 3 中 bank 3 的 bank conflict ratio。
- `lane3 bank3_total_conflicts`：lane 3 中 bank 3 的 bank conflict 总次数。
- `lane3 bank3_total_requests`：lane 3 中 bank 3 的 bank request 总次数。
- `lane3 bank4_conflict_ratio`：lane 3 中 bank 4 的 bank conflict ratio。
- `lane3 bank4_total_conflicts`：lane 3 中 bank 4 的 bank conflict 总次数。
- `lane3 bank4_total_requests`：lane 3 中 bank 4 的 bank request 总次数。
- `lane3 bank5_conflict_ratio`：lane 3 中 bank 5 的 bank conflict ratio。
- `lane3 bank5_total_conflicts`：lane 3 中 bank 5 的 bank conflict 总次数。
- `lane3 bank5_total_requests`：lane 3 中 bank 5 的 bank request 总次数。
- `lane3 bank6_conflict_ratio`：lane 3 中 bank 6 的 bank conflict ratio。
- `lane3 bank6_total_conflicts`：lane 3 中 bank 6 的 bank conflict 总次数。
- `lane3 bank6_total_requests`：lane 3 中 bank 6 的 bank request 总次数。
- `lane3 bank7_conflict_ratio`：lane 3 中 bank 7 的 bank conflict ratio。
- `lane3 bank7_total_conflicts`：lane 3 中 bank 7 的 bank conflict 总次数。
- `lane3 bank7_total_requests`：lane 3 中 bank 7 的 bank request 总次数。
- `lane3 hp_block_lp`：lane 3 中 high-priority request 阻塞 low-priority request 的计数。
- `lane3 total_bank_conflicts`：lane 3 所有 bank conflict 总次数。
- `lane3 total_bank_requests`：lane 3 所有 bank request 总次数。
- `lane3 total_hp_bank_conflicts`：lane 3 high-priority bank conflict 总次数。
- `lane3 total_hp_bank_requests`：lane 3 high-priority bank request 总次数。
- `lane3 total_lp_bank_conflicts`：lane 3 low-priority bank conflict 总次数。
- `lane3 total_lp_bank_requests`：lane 3 low-priority bank request 总次数。
- `main_vector_req_blocked_ratio`：`ara_req_blocked_cycles / ara_req_valid_cycles` 的派生 blocked ratio。
- `main_vector_req_per_cycle`：`ara_req_fire_count / total_cycles` 或 ideal 中对应 RVV 周期的派生请求投放吞吐。
- `rvv_axi_ar_count`：main representative CSV 中的原始指标字段；用于 baseline 诊断和对照。
- `rvv_axi_aw_count`：main representative CSV 中的原始指标字段；用于 baseline 诊断和对照。
- `rvv_axi_b_count`：main representative CSV 中的原始指标字段；用于 baseline 诊断和对照。
- `rvv_axi_r_count`：main representative CSV 中的原始指标字段；用于 baseline 诊断和对照。
- `rvv_axi_w_count`：main representative CSV 中的原始指标字段；用于 baseline 诊断和对照。
- `rvv_op`：main representative CSV 中的原始指标字段；用于 baseline 诊断和对照。
- `rvv_op_fd`：main representative CSV 中的原始指标字段；用于 baseline 诊断和对照。
- `rvv_op_fs1`：main representative CSV 中的原始指标字段；用于 baseline 诊断和对照。
- `rvv_op_load`：main representative CSV 中的原始指标字段；用于 baseline 诊断和对照。
- `rvv_op_store`：main representative CSV 中的原始指标字段；用于 baseline 诊断和对照。
- `seq_block_cycles`：main/Ara sequencer block 周期数。
- `seq_false_hazard_cycles`：main/Ara sequencer 中被归类为 false/conservative hazard 的周期数。
- `seq_raw_hazard_cycles`：main/Ara sequencer RAW hazard 相关周期数。
- `seq_war_hazard_cycles`：main/Ara sequencer WAR hazard 相关周期数。
- `seq_waw_hazard_cycles`：main/Ara sequencer WAW hazard 相关周期数。
- `total_cycles`：main real 模式的总执行周期。
- `total_insns`：main representative CSV 中的原始指标字段；用于 baseline 诊断和对照。
- `total_rvv_cycles`：main ideal 模式的总 RVV 执行周期。
- `total_rvv_lane_cycles`：main ideal 中所有 lane 活跃周期的聚合计数。
- `total_rvv_load_lane_cycles`：main ideal 中 load lane 活跃周期计数。
- `total_rvv_load_only_cycles`：main ideal 中仅 load 路径活跃的周期计数。
- `total_rvv_mem_lane_cycles`：main ideal 中 memory lane 活跃周期计数。
- `total_rvv_mem_only_cycles`：main ideal 中仅 memory 路径活跃的周期计数。
- `total_rvv_store_lane_cycles`：main ideal 中 store lane 活跃周期计数。
- `total_rvv_store_only_cycles`：main ideal 中仅 store 路径活跃的周期计数。
- `total_vector_insns`：main representative CSV 中的原始指标字段；用于 baseline 诊断和对照。
- `vector inst rate`：main representative CSV 中的原始指标字段；用于 baseline 诊断和对照。
- `lane0 compute utilization`：lane 0 的 compute utilization。
- `lane0 conflict_ratio`：lane 0 聚合 bank conflict ratio。
- `lane1 compute utilization`：lane 1 的 compute utilization。
- `lane2 compute utilization`：lane 2 的 compute utilization。
- `lane3 compute utilization`：lane 3 的 compute utilization。
- `total_rvv_lane0_compute_cycles`：main ideal 中 lane 0 的 RVV compute cycle 计数。
- `total_rvv_lane1_compute_cycles`：main ideal 中 lane 1 的 RVV compute cycle 计数。
- `total_rvv_lane2_compute_cycles`：main ideal 中 lane 2 的 RVV compute cycle 计数。
- `total_rvv_lane3_compute_cycles`：main ideal 中 lane 3 的 RVV compute cycle 计数。

调 prefetch 时，`+HDV_PF_PROBE` 会打开多处 `$display`，包括 HEU/VDU/scalar/addrgen/vldu 的周期级事件。该探针用于定位真实原因，不能作为最终论文数据。

### 15.9 累积式消融开关

当前 RTL 支持用 `hdv_ablation` 编译期开关跑 5.3 的累积式消融。默认值是 `full`，不改变当前仿真行为；只有显式设置其它模式才会加 disable define，并使用独立仿真目录。

| 模式 | Make 变量 | 关闭机制 | 机制含义 |
|---|---|---|---|
| 完整设计 | `hdv_ablation=full` | 无 | 默认全套 HDV 机制 |
| `H_base` | `hdv_ablation=base` | VLSU prefetch、buffered early issue、same-EP hazard bypass、VDU scalar-operand lookahead/bypass | 只保留 HDV 前端、EP 形成、HEU/VDU 最小执行通路 |
| `H_pf_only` | `hdv_ablation=pf_only` | buffered early issue、same-EP hazard bypass、VDU scalar-operand lookahead/bypass | 在 `H_base` 上只打开 request-bound VLSU prefetch |
| `H_haz` | `hdv_ablation=haz` | VLSU prefetch、buffered early issue、VDU scalar-operand lookahead/bypass | 在 `H_base` 上只打开 same-EP hazard handling |
| `H_pf_haz` | `hdv_ablation=pf_haz` | buffered early issue、VDU scalar-operand lookahead/bypass | 同时打开 VLSU prefetch 和 same-EP hazard handling |

`sweep` 脚本使用环境变量 `HDV_ABLATION` 映射到 Make 变量：

```bash
HDV_ABLATION=base ./kernel_sweep.sh --skip-long all
HDV_ABLATION=pf_only ./kernel_sweep.sh --skip-long all
HDV_ABLATION=haz ./kernel_sweep.sh --skip-long all
HDV_ABLATION=pf_haz ./kernel_sweep.sh --skip-long all
./kernel_sweep.sh --skip-long all   # full, unchanged default
```

单点手动仿真直接传给 Make 时使用小写 Make 变量，避免 shell 中残留的大写环境变量误改默认 full 行为：

```bash
make sim app=vsaxpy_hdv avl=4096 hdv_ablation=base
make sim app=vsaxpy_hdv avl=4096 hdv_ablation=pf_haz
```

如果要一键跑全部 HDV 消融，并且不覆盖当前默认 `kernel_sweep_out` 或 `sim`，使用：

```bash
./kernel_ablation.sh --parallel --skip-long all
```

该 wrapper 默认运行 `base/pf_only/haz/pf_haz`，把结果写到 `kernel_sweep_out_ablate_<mode>`，并显式使用 `sim_ablate_<mode>`。如果 `mc=1`，对应仿真目录为 `sim_mc_ablate_<mode>`。完整 `full` 设计不由 wrapper 默认重复运行，仍使用普通 `kernel_sweep.sh` 和默认 `kernel_sweep_out`。如果只想跑某几个模式，可设置：

```bash
HDV_ABLATION_MODES="base pf_only haz pf_haz" ./kernel_ablation.sh --parallel --skip-long all
```

如果要自定义单次 sweep 的输出目录，可设置 `KERNEL_SWEEP_OUT=<dir>`。消融结果汇总仍使用同一个脚本：

```bash
./kernel_sweep_sum.sh kernel_sweep_out_ablate_base
./kernel_sweep_sum.sh kernel_sweep_out_ablate_pf_only
./kernel_sweep_sum.sh kernel_sweep_out_ablate_haz
./kernel_sweep_sum.sh kernel_sweep_out_ablate_pf_haz
./kernel_sweep_sum.sh kernel_sweep_out
```

这些开关的目的是关闭“后端对 EP metadata 的性能化消费”，不是移除 HDV 程序运行所需的最小 dispatch plumbing。尤其 `H_base` 仍保留 HEU/VDU、基本 operand snapshot、EP acknowledge 和 command window，否则 HDV kernel 无法通过 Ara 执行。当前实验拆法不强行把所有机制排成单一路径，而是先分别测两个主要后端消费路径：`H_pf_only` 观察 request-bound prefetch 的独立贡献，`H_haz` 观察 same-EP hazard handling 的独立贡献，`H_pf_haz` 观察二者叠加后的效果。`H_full` 相比 `H_pf_haz` 继续打开 buffered vector early issue 和 VDU scalar-operand lookahead/bypass；后者指 VDU 在当前 vector slot 发射时提前读取下一 slot 的标量操作数，以及 DISPATCH 阶段的同周期 operand bypass。

## 16. 学习与教学路线

如果把这份设计讲给没有读过代码的人，建议不要从每个 RTL 文件逐个讲起，而是先用第 2 章的 S0-S9 端到端流水线建立全局图，再按四层递进：

1. **先讲任务和 EP**：host 只提交 task，IPU/VLIWPU 把 instruction stream 变成 EP。重点讲清 `task done`、`scalar_ep_done`、`vec_ep_acknowledged`、`heu_top_ep_acknowledged` 不是同一个事件。
2. **再讲前端如何安全推进**：HEU 拆 scalar/vector slice，current EP 和 buffered EP 最多两个 outstanding。early issue 只提前 buffered vector，并受 branch、scalar write mask、vset write mask、memory-order mask 约束。
3. **再讲后端如何消费语义**：VDU snapshot scalar operand，command window 吸收 Ara backpressure，request 携带 `hdv_meta` 进入 Ara。Ara sequencer 用 `ep_id` 裁剪 same-EP hazard，但这要求软件保证同 EP 内没有真实非法依赖。
4. **最后讲 VLSU prefetch**：prefetch 是 request-bound hint，不是单独的 ISA 操作。它只在 demand 地址精确匹配 lookup 时替代 demand load；失配时 flush 或退回 demand-driven。

讲课时最容易混淆的点有五个：

- **EP acknowledge 不是 vector 完成**：它只表示前端可推进，普通 vector 指令还可能在 Ara 内执行。
- **same-EP bypass 不是硬件自动并行化所有指令**：同 EP 是软件承诺，真实 RAW/WAR/WAW 必须切 EP。
- **operand snapshot 固定的是标量版本**：一条 vector request 发出后，后续 scalar 修改不会影响它；但同 EP 内 scalar 写、vector 读没有自动新值旁路。
- **memory 正确性靠多个局部互锁**：HEU 挡 scalar memory 被后续 vector early issue 越过，VDU/标量后端挡 vector store 被后续 scalar memory 越过，VLSU 负责 demand/prefetch 数据归属。
- **prefetch mode 只描述同一条 load 的未来地址距离**：不是 LMUL，不是 load 条数，也不是关闭开关；关闭由 `prefetch_disable` 独立表示。

读代码时可以把每个模块映射到一句话：

| 模块 | 一句话理解 |
|---|---|
| TIU/TSU | 把 host task 请求变成按序进入本地前端的 active task |
| IPU | 本地取指和 loop replay，减少循环体重复 instruction fetch |
| VLIWPU | 把 hint/header/p-bit/cross 解释成 EP |
| HEU | 拆 scalar/vector，维护 current/buffer，决定前端何时能推进 |
| Scalar backend | 执行 scalar slice，维护 XRF/FRF，解析 branch，服务 vector operand |
| VDU | 把 vector slice 变成 resolved Ara request，snapshot operand，管理 EP ack |
| Ara dispatcher/sequencer | 原 RVV 后端入口，消费 HDV metadata 做 same-EP hazard handling |
| VLSU addrgen/vldu | 发 demand/prefetch AR，匹配 lookup，保存/消费 prefetched data |

画 SEAM-V 框图前，建议检查图中是否已经包含下面这些元素：

| 框图元素 | 必须表达的含义 |
|---|---|
| Task 控制面 | host 只提交 task，不逐条驱动 RVV 指令 |
| Local instruction supply | IPU 本地 fetch buffer 和 loop replay 是前端供给增强来源 |
| EP formation | VLIWPU 根据 header/p-bit/packet256/cross 形成 EP |
| Hybrid split | HEU 把同一 EP 拆成 scalar slice 和 vector slice |
| Scalar backend | 执行地址更新、循环控制、分支、标量 LSU，并服务 vector operand |
| Vector request resolution | VDU snapshot scalar operand，把 vector slice 变成 resolved Ara request |
| Command window | 吸收 Ara backpressure，把前端 request 生成与后端 ready 解耦 |
| HDV metadata sideband | `ep_id` 和 prefetch hint 随每条 vector request 进入 Ara |
| Ara semantic consumption | sequencer 用 same-EP metadata 裁剪保守 hazard，但 Ara 仍负责真实后端执行 |
| VLSU prefetch path | demand load 触发 request-bound prefetch，lookup hit 后替代同地址 demand |
| Ack/drain path | EP ack 只推进前端；task done 必须等待 VDU/Ara 相关状态 drain |

如果图中只画了“前端 -> Ara”一条粗箭头，而没有画 scalar operand、HDV metadata、EP ack 和 prefetch side path，就还不能准确表达 SEAM-V 的前后端协同。

## 17. 当前设计边界

当前 HDV RTL 已经打通真实标量后端、VDU 到 Ara、sequencer EP-aware handling 和 VLSU request-bound prefetch，但仍有明确边界：

- `hdv_scalar_backend` 是 HDV 专用后端，不是完整 CVA6 core。
- HEU/VDU 当前只支持两个 outstanding vector EP slice，即 current + buffered。
- `ep_id` 当前是 1 bit。
- EP acknowledge 不是 vector instruction retirement。
- VLSU prefetch 主要服务 unit-stride load，不覆盖 strided/gather/scatter 的有效预取。
- Prefetch 是性能提示，不是正确性条件；失配时应能退化为 demand-driven。
- Header/p-bit/cross 只允许硬件利用局部并行性，硬件仍可按控制边界、依赖边界和资源边界拆分 EP。
- 同 EP 内真实 vector RAW/WAR/WAW、同 EP scalar 写后 vector 读新值、同 EP 必须保序 memory 关系都必须由软件拆 EP 表达。
- `AXI_ID_PREFETCH` 常量虽然存在，当前 prefetch 数据路径采用 same-id demand/prefetch 加 tag 区分。

## 18. 阅读 RTL 的建议顺序

建议按下面顺序读代码：

1. `hardware/src/hdv/hdv_top.sv`：先看全局 wiring、AXI mux、flush/task done。
2. `hardware/src/hdv/hdv_task_interface_unit.sv` 和 `hdv_task_schedule_unit.sv`：理解 task 边界。
3. `hardware/src/hdv/hdv_instruction_prefetch_unit.sv`：理解 fetch packet、loop replay、redirect。
4. `hardware/src/hdv/hdv_vliw_pack_unit.sv`：理解 header/p-bit/packet256/cross 到 EP。
5. `hardware/src/hdv/hdv_hybrid_execution_unit.sv`：理解 scalar/vector split、current/buffer、early issue。
6. `hardware/src/scala_backend/hdv_scalar_backend.sv`：理解 scalar slice 真实执行和互锁。
7. `hardware/src/hdv/hdv_vec_dispatch_unit.sv`：理解 operand snapshot、command window、acknowledge。
8. `hardware/src/ara_dispatcher.sv`、`ara_sequencer.sv`：理解 metadata 进入后端和 same-EP hazard handling。
9. `hardware/src/vlsu/addrgen.sv`、`vldu.sv`、`vlsu.sv`：理解 EP-driven prefetch。

这份文档应作为当前硬件设计说明的唯一入口。若后续 RTL 修改了 HINT 编码、EP depth、VDU wait table、prefetch ID/tag 机制或 scalar backend issue 规则，应优先更新本文。
