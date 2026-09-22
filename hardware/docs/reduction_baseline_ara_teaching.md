# 原始 Ara 规约实现教学文档

本文解释 Ara 在本轮 4-lane 优化之前的规约实现。这里的“原始”不是指
RVV 规约指令的最早历史版本，而是本仓库本轮优化的基线快照：

```text
baseline commit: 30c6971b  (2026-07-09)
optimization branch: reduction-optimization
```

基线代码可以用下面的方式复现：

```bash
git show 30c6971b:hardware/src/lane/valu.sv
git show 30c6971b:hardware/src/lane/vmfpu.sv
git show 30c6971b:hardware/src/sldu/sldu.sv
```

当前分支新增的专门优化说明见
[`reduction_optimization_teaching.md`](reduction_optimization_teaching.md)，
实验记录见 [`reduction_acceleration_4lane.md`](reduction_acceleration_4lane.md)。

## 1. 先建立整体认识

RVV 规约把一个向量和一个标量 seed 合并成一个结果。以
`vredsum.vs vd, vs2, vs1` 为例，语义可以抽象为：

```text
acc = vs1[0]
for i in active_elements(vs2):
    acc = acc + vs2[i]
vd[0] = acc
```

浮点规约的运算符可能是加法、最小值或最大值；widening 版本还会改变
累加器的元素宽度。硬件不能把它当作普通的逐元素向量运算，因为每一步都
依赖前一步产生的 accumulator。

Ara 的基本组织方式是：

```text
                 ┌──────────────────────────┐
                 │  ara_sequencer            │
                 │  指令分类、依赖、提交顺序  │
                 └────────────┬─────────────┘
                              │ pe_req
             ┌────────────────┴────────────────┐
             │ 每个 lane 的 lane_sequencer      │
             │ operand_requester / operand_queue│
             └───────┬───────────────┬──────────┘
                     │               │
                  ┌──▼──┐         ┌──▼───┐
                  │VALU │         │VMFPU │
                  │整数 │         │浮点  │
                  └──┬──┘         └──┬───┘
                     │ partial/root  │ partial/root
                     └──────┬────────┘
                            ▼
                          SLDU
                跨 lane 树 / ordered 单跳传递
                            │
                 lane 0 SIMD fold 或最终结果
                            │
                         result queue
                            │
                            ▼
                           VRF
```

每个 lane 只处理自己负责的向量元素。规约的局部结果先在 lane 内累加，
再由 SLDU 负责跨 lane 合并。这样既复用了 Ara 的 SIMD ALU/FPU，也复用了
原本用于 slide 的跨 lane 数据通路。

### 1.1 先固定五个概念

| 概念 | 本文中的含义 |
|---|---|
| lane | Ara 的一个并行执行分片。`NrLanes=4` 时，一个向量元素只会被一个 lane 负责，跨 lane 合并由 SLDU 完成。 |
| VRF | 向量寄存器文件。lane 通常以 64-bit word 读写它；`SEW` 决定一个 word 中有几个元素。 |
| operand queue | 从 VRF 返回的数据进入执行单元之前的队列，负责转换、重排、mask 和 neutral 填充。 |
| result queue | ALU/FPU 或 SLDU 已经产生、但还没有获得 VRF/MASKU grant 的结果队列。它既保存数据，也保存地址、byte-enable 和 instruction owner。 |
| valid/ready | 两端在同一拍都为 1 才算一次传输。只有握手完成后，生产者才可以推进计数器或释放 token。 |

`SEW` 是元素宽度，`VL` 是本条指令的活动元素数，`vm=1` 表示不使用
`v0` mask；`vm=0` 时还要读取 mask。规约教学中最容易混淆的是：`VL` 是
架构元素数，不是每个 lane 的元素数，lane 内部还要根据 lane 映射和尾部
补齐来生成自己的 operand beat。

## 2. 支持的规约指令和执行单元

操作码在 [`ara_pkg.sv`](../include/ara_pkg.sv) 中定义，基线主要分成四组：

| 类别 | 操作码 | 执行单元 | 特征 |
|---|---|---|---|
| 整数单宽 | `VREDSUM`、`VREDAND`、`VREDOR`、`VREDXOR`、`VREDMIN(U)`、`VREDMAX(U)` | `VALU` | lane 内整数累加/逻辑/比较，再跨 lane 合并 |
| 整数 widening | `VWREDSUM`、`VWREDSUMU` | `VALU` | 源元素较窄，累加结果较宽 |
| 浮点 unordered | `VFREDUSUM`、`VFREDMIN`、`VFREDMAX`、`VFWREDUSUM` | `VMFPU` | 可使用跨 lane tree，但 FP 加法顺序由 tree 决定 |
| 浮点 ordered | `VFREDOSUM`、`VFWREDOSUM` | `VMFPU` | 必须保持架构元素顺序，不能任意重排 |

基线中的 `is_reduction()` 函数分别位于 `valu.sv` 和 `vmfpu.sv`。整数版本
判断 `[VREDSUM:VWREDSUM]`，浮点版本判断 `[VFREDUSUM:VFWREDOSUM]`。
`ara_sequencer` 则把这些 opcode 映射到 `VFU_Alu` 或 `VFU_MFpu`，使 lane
和 SLDU 知道当前是哪一种规约。

### unordered 和 ordered 的根本差别

unordered reduction 允许实现选择一棵满足 RVV 语义的组合树。对于普通浮点
加法，不同的结合顺序可能带来不同的舍入结果，但这正是 unordered 语义
允许的范围。

ordered reduction 的每一个新元素必须接在前一个累加结果之后：

```text
seed -> element 0 -> element 1 -> element 2 -> ...
```

它不能把元素分成任意两棵树后再合并。因此基线对 unordered 和 ordered 使用
不同的 VMFPU/SLDU 状态路径。

## 3. 从指令进入 lane

### 3.1 主 sequencer 的作用

[`ara_sequencer.sv`](../src/ara_sequencer.sv) 维护全局运行指令集合和寄存器
读写关系。对一条规约指令，它至少要决定：

1. 由 `VALU` 还是 `VMFPU` 执行；
2. 哪些源寄存器需要从 VRF 读取；
3. `vd`、`vs1`、`vs2` 和 `v0` 之间的 RAW/WAR/WAW 依赖；
4. 什么时候允许下一条向量指令进入；
5. 什么时候所有 lane 都完成，才能向 CVA6 报告指令结束。

基线的 hazard table 以向量指令 ID 为列。新指令会把依赖它的旧 writer/reader
写入自己的 hazard 位；这些位通常等到对应 PE 报告 `vinsn_done` 后清除。
因此，基线安全但保守：一条规约在跨 lane 阶段停留时，后续可能复用同一
寄存器的指令通常要等待它完全结束。

### 3.2 lane_sequencer 和 operand requester

[`lane_sequencer.sv`](../src/lane/lane_sequencer.sv) 把主 sequencer 的
`pe_req` 拆成三类信息：

- operand requester command：从哪个向量寄存器读取、读取多少元素、怎样转换；
- `vfu_operation`：送给 VALU/VMFPU 的 opcode、mask、VL、SEW、seed 和目的寄存器；
- hazard metadata：当前 operand 在哪些旧指令结束前不能读取。

[`operand_requester.sv`](../src/lane/operand_requester.sv) 根据每个 lane 的
分片位置生成 VRF 请求；[`operand_queue.sv`](../src/lane/operand_queue.sv)
把返回的 64-bit word 排队，并完成：

- EEW/SEW 转换；
- widening 的符号扩展或浮点格式扩展；
- `vstart`、lane 起始位置和 VL 缩放；
- mask 对应的有效字节；
- 规约所需的 neutral value 填充。

规约的第一步和普通向量指令不同：它同时需要 vector body 和 scalar seed。
之后的步骤不再从 VRF 读取 accumulator，而是从执行单元自己的 result queue
取上一轮结果。

### 3.3 neutral value

当某个 lane 没有实际元素，或者一个 64-bit word 中只有部分元素有效时，
硬件必须提供不会改变结果的单位元：

| 运算 | neutral value |
|---|---|
| `VREDSUM`、`VREDOR`、`VREDXOR`、`VREDMAXU`、widening sum | 每个元素全 0 |
| `VREDAND`、`VREDMINU` | 每个元素全 1 |
| signed `VREDMIN` | 该 SEW 的最大正数，例如 EW8 为 `0x7f` |
| signed `VREDMAX` | 该 SEW 的最小负数，例如 EW8 为 `0x80` |
| FP sum | `+0` |
| FP min | `+∞` |
| FP max | `-∞` |

表中的 neutral 只描述空 lane、tail 或 masked-off 元素的单位元；真实 active
operand 的 NaN、signed zero 和 `fflags` 仍由 FPnew/FPU 数据通路处理，不能把
neutral 表当成完整的 IEEE 特殊值规则。

基线通过 `cvt_resize` 的编码复用字段把 FP reduction 的 neutral 类型传入
operand queue/VMFPU。这个字段在 `ara_pkg.sv` 中有注释：`00` 表示零，
`01` 表示正无穷，`10` 表示负无穷。

neutral value 的目的不是“填充无关数据”，而是保证以下情况仍可走统一
握手流程：

- `VL=0`；
- `VL` 不能被 lane 数整除；
- 某个 tree stage 中某些 lane 没有新的实际元素；
- masked-off 元素不应改变结果。

## 4. VALU 的整数规约路径

基线 [`valu.sv`](../src/lane/valu.sv) 使用六个主要状态：

```text
NO_REDUCTION
    │
    ▼
INTRA_LANE_REDUCTION
    │
    ▼
INTER_LANES_REDUCTION_TX <──┐
    │                       │
    ▼                       │
INTER_LANES_REDUCTION_RX ───┘
    │
    ├── lane 0: SIMD_REDUCTION -> commit
    └── other lanes: LN0_REDUCTION_COMMIT
```

### 4.1 `INTRA_LANE_REDUCTION`

第一拍的两个输入具有特殊含义：

- accumulator 输入来自 `vs1` 的 scalar seed；
- vector 输入来自 `vs2` 的第一个元素或第一个元素包；
- 非 lane 0 或空 lane 使用 neutral seed。

后续拍中，`first_op_q=0`，`alu_operand_a` 改为 result queue 当前写入位置的
累加结果，另一侧继续接收 vector body。每次 ALU 完成后，结果按 mask byte
选择性写回：

```text
active element   -> 写入 ALU 新结果
masked-off       -> 保留旧 accumulator
```

这保证 masked-off 元素在数值上不参加规约；但基线仍可能为它们经历一次
普通 ALU/FPU 的流水和握手。

`issue_cnt_q` 跟踪尚未发射的 vector 元素。当它降到零时，lane 进入
`INTER_LANES_REDUCTION_TX`，但此时还不能立即把架构指令标记为完成，因为
其它 lane 和 SLDU tree 仍在工作。

### 4.2 `INTER_LANES_REDUCTION_TX/RX`

每个 lane 把自己的局部 accumulator 送到 SLDU。SLDU 返回的数据有两种情况：

- 当前 lane 是 tree 的参与者：用返回值和自己的 accumulator 再做一次 ALU；
- 当前 lane 在这一轮不参与：仍然 handshake，用来和其它 lane 保持同步。

`reduction_rx_cnt_q` 表示当前 lane 还要真正执行多少次接收合并。基线用
`reduction_rx_cnt_init()` 给最多 16 个 lane 的 lane ID 写出静态映射，例如
lane 1 参与一轮，lane 3 参与两轮，lane 7 参与三轮。偶数 lane 通常只是
同步或旁路，不会在每个 tree level 都执行运算。

`sldu_transactions_cnt_q` 则是整个 instruction 的 tree transaction 计数，
用于让所有 lane 在相同的 tree 边界退出。

### 4.3 lane 0 的 SIMD fold 和提交

最后一个 tree 结果回到 lane 0 后，lane 0 进入 `SIMD_REDUCTION`。它把一个
64-bit word 中仍然并列存在的多个 SEW 子元素逐步折叠成一个结果：

```text
EW8 : 最多 8 个子元素
EW16: 最多 4 个子元素
EW32: 最多 2 个子元素
EW64: 已经只有 1 个子元素
```

其它 lane 进入 `LN0_REDUCTION_COMMIT`，等待 lane 0 和主 sequencer 的提交
边界。`alu_red_complete_o` 只在整个规约对 SLDU/ADDRGEN 资源释放时产生，
而不是在 lane 内部第一次得到局部结果时产生。

## 5. VMFPU 的浮点规约路径

基线 [`vmfpu.sv`](../src/lane/vmfpu.sv) 复用整数路径的跨 lane 状态，同时
增加了 `OSUM_REDUCTION` 和 `MFPU_WAIT`：

```text
unordered:
NO_REDUCTION -> INTRA_LANE_REDUCTION
             -> INTER_LANES_REDUCTION_TX/RX
             -> SIMD_REDUCTION / LN0_REDUCTION_COMMIT

ordered:
NO_REDUCTION -> OSUM_REDUCTION -> MFPU_WAIT
```

### 5.1 unordered FP reduction

`VFREDUSUM/VFREDMIN/VFREDMAX/VFWREDUSUM` 的局部路径与整数规约相似，
但每个 micro-op 要经过 pipelined FPU。基线用以下状态保存输入和输出的
不同时间点：

- `first_op_q`：是否还在处理 scalar seed；
- `intra_op_rx_cnt_q`：已经从 operand queue 取了多少 vector 元素；
- `intra_issued_op_cnt_q`：已经向 FPU 发射了多少拍；
- `ntr_filling_q`：FPU pipeline 尚未返回第一个真正结果时，是否继续送 neutral；
- `first_result_op_valid_q`：result queue 中是否已有可以作为下一次 accumulator
  的结果。

基线允许 FPU latency 和 operand queue 的发射节拍重叠。`vfpu_tag_in` 区分
正常元素、一个或两个 neutral 输入；返回端用 `vfpu_tag_out` 调整待处理
元素数。这样即使一开始还没有真实 FPU 结果，也能把 pipeline 填满。

### 5.2 unordered 的跨 lane tree

局部 FPU 结果先进入 result queue，再由 `INTER_LANES_REDUCTION_TX` 送到
SLDU。接收阶段把：

```text
operand_a = SLDU 返回的其它 lane 部分和
operand_b = 本 lane 的 accumulator
operand_c = 与 FPU 接口匹配的复制值
```

送入 FPU。lane 0 最后执行 SIMD fold；其它 lane 在 `LN0_REDUCTION_COMMIT`
或 `MFPU_WAIT` 结束。

FP min/max 的 neutral 不是零，必须根据操作选择正无穷或负无穷。widening
规约还要在 operand queue 和 VMFPU 的 `fp_src_fmt/fp_int_fmt` 选择中完成
源格式到累加格式的扩展。

### 5.3 ordered FP reduction

`VFREDOSUM/VFWREDOSUM` 不能使用 unordered tree。基线 `OSUM_REDUCTION` 的
关键约束是：**同一时刻只有一个 lane 持有有效的 ordered token**。

每次 FPU 完成一个元素后：

1. 当前 lane 把 accumulator 放入 result queue；
2. 通过 SLDU 把 token 送到下一个 lane；
3. 下一个 lane 从 SLDU 输入得到 token，再与自己的 vector body 元素相加；
4. 最后一个元素直接把 token 送回 lane 0；
5. lane 0 将最终 token 写入 VRF。

`red_hs_synch_q` 防止 token 在当前 lane 尚未准备好时被重复消费。对于
masked ordered reduction，operand 和 mask 必须同时有效；masked-off 元素
不改变 accumulator，但基线仍保留完整的握手节拍。

## 6. SLDU 如何承担规约通信

### 6.1 普通数据和规约数据共用 SLDU

[`sldu.sv`](../src/sldu/sldu.sv) 同时服务：

- `vslideup/vslidedown`；
- NP2 slide 的中间 buffer；
- VALU integer reduction；
- VMFPU unordered/ordered reduction。

因此规约路径必须通过 `sldu_mux_sel_o` 选择 ALU reduction、MFPU reduction
或普通 slide，并使用独立的 `sldu_red_valid_o`/`sldu_result_gnt_i` 握手。

每个 lane 的输入先经过 spill register。这个寄存器切断了 lane 到 SLDU 的
组合路径，也吸收了背压，但它同时给每个规约 token 增加了固定的队列往返。

### 6.2 unordered tree

基线 tree 是对 lane 的局部结果做对数级合并。以 4 lane 为例：

```text
level 0: (lane0, lane1) -> partial0
         (lane2, lane3) -> partial2
level 1: (partial0, partial2) -> lane0
lane 0:  64-bit word 内 SIMD fold
```

`red_stride_cnt_q` 控制每一轮的跨 lane 位置；`issue_cnt_q` 按
`NrLanes * (clog2(NrLanes)+1)` 的 64-bit transaction 预算推进。即使某个
lane没有实际数据，也可能需要通过 neutral 或空同步 transaction 保持 tree
边界一致。

### 6.3 ordered one-hop

基线 `SLIDE_RUN_OSUM` 不构造 tree，而是对每个有效 lane 做：

```text
target = (lane == NrLanes-1) ? 0 : lane+1
```

当 `issue_cnt_q == 1` 时，最后一个 token 的 target 强制改为 lane 0。每个
token 写入 SLDU result queue，并等待下一 lane 的 operand requester/VMFPU
接收。这个路径严格保持 token 顺序，但 result queue 和 spill register 会
成为 recurrence interval 的固定开销。

## 7. mask、VL、vstart 和不平衡 lane

### mask

基线把 mask 作为独立 operand 送到 lane。VALU 用 `red_mask` 选择保留旧
accumulator 或写入新结果；VMFPU 用 `processed_red_operand()` 把 inactive
元素转换为 neutral。mask-ready 只有在当前 word 的相关元素被消费后才推进。

### `VL=0` 和不平衡 workload

规约不能简单像普通向量指令那样在 `vl==0` 时完全静音，因为所有 lane 仍
需要参与 neutral/完成握手。`lane_sequencer` 会给规约请求保留最小 operand
流程，operand queue 产生 neutral 数据，最终由 lane 0 写出 seed 语义要求
的结果。

### `vstart` 和尾部元素

operand requester 根据 `vstart/NrLanes` 计算每个 lane 的起始元素；低编号
lane 可能收到 mock 数据来平衡 packet。有效 byte enable 和 mask 共同决定
哪些元素真正进入 accumulator。widening 规约还要同时考虑源和目标 EEW。

### `prevent_commit`

当某些 lane 已经没有自己的 vector body、但其它 lane 仍在 tree 中运行时，
VALU/VMFPU 设置 `prevent_commit`。这能避免一个 lane 提前退休并覆盖主
sequencer 的 commit counter，保证所有 lane 在同一个架构指令边界完成。

## 8. 一条 4-lane 规约的时序示例

假设 `VLEN=1024`、`NrLanes=4`、`SEW=32`、`VL=32`：

```text
每 lane 约 8 个元素

1. lane_sequencer 接收 vfredusum.vs
2. operand requester 送 scalar seed 和 vector body
3. 每 lane 在 INTRA_LANE_REDUCTION 得到一个局部 root
4. 4 个 root 进入 SLDU tree
5. tree 经过两级跨 lane 合并
6. lane 0 在 SIMD_REDUCTION 折叠最后一个 64-bit word
7. result queue 等待 VRF grant
8. 所有 lane 报告 vinsn_done，主 sequencer 释放依赖
```

如果是 `vfredosum.vs`，第 4～5 步改为一个 token 按 lane 顺序传递：

```text
lane 0 -> lane 1 -> lane 2 -> lane 3 -> lane 0 final
```

这也是原始实现中 ordered reduction 比 unordered reduction 更容易受队列
往返延迟影响的原因。

## 9. 基线的正确性边界

基线正确性主要依赖四个不变量：

1. **token 所有权**：同一时刻只有拥有 accumulator 的 lane 可以更新它；
2. **元素顺序**：ordered reduction 不允许 SLDU 重排 token；
3. **neutral 语义**：空 lane、tail 和 masked-off 元素使用对应单位元；
4. **提交顺序**：result queue 的写回和主 sequencer 的 `vinsn_done` 按架构顺序发生。

FPU 的 NaN、无穷、符号零和异常标志由 FPnew/FPU 数据通路处理；规约控制
负责把每个有效源正确送入该通路，不自行改变 IEEE 特殊值规则。

unordered FP reduction 的结果允许受 tree 结合顺序影响，因此它不提供
exact-sum 意义上的跨实现 bitwise 可重复性。ordered FP reduction 则保持
元素顺序，但仍受基础 FPU 舍入模式支配。

## 10. 基线的性能瓶颈和阅读方法

读基线波形时建议按以下顺序定位：

1. `INTRA_LANE_REDUCTION`：看 operand queue 是否断流、FPU latency 是否填满；
2. `INTER_LANES_REDUCTION_TX/RX`：看 SLDU spill register 和 tree handshake；
3. `SIMD_REDUCTION`：看 lane 0 的 word 内折叠；
4. result queue：看 VRF grant 或下游 mask 消费是否阻塞提交；
5. `ara_sequencer`：看后续指令是否被 RAW/WAR/WAW 保守地挡住。

基线的结构性限制是：

- ordered token 要经过 VMFPU result queue、SLDU result queue 和下一个 lane 输入；
- mask-off 元素通常仍经过完整的运算握手；
- reduction 指令基本按全局顺序运行，独立 reduction 很难重叠；
- tree 接收端有固定 spill，空闲时也可能多一个周期；
- hazard table 以指令完成为主要清除边界，跨迭代寄存器复用会产生较长 WAR/WAW 窗口；
- `reduction_rx_cnt_init()` 的静态 lane 映射注释只保证到 16 lane。

这些限制正是优化分支后来引入 output/route bypass、context stream、exact
backend 和 versioned chain bypass 的动机。

### 10.1 一个可用于对照的基线测量锚点

下面的数字来自已有 `perf_reduction_probe` 的 4-lane、`VLEN=1024`、e32/m1、
`VL=32` clean 配置。它们用于帮助读者建立量级，不是某条指令的固定理论
延迟；改动外围指令、仿真 ROI 或配置后不能直接复用。

| 指令 | 基线指令延迟 |
|---|---:|
| `vredsum` | 24 cycles |
| `vfredusum` | 49 cycles |
| `vfredmin` | 55 cycles |
| `vfredmax` | 55 cycles |
| `vfredosum` | 287 cycles |
| 混合 probe ROI | 424 cycles |

ordered sum 明显更长，是因为一个 token 必须按 lane 顺序反复经过 VMFPU、
SLDU 和下一个 lane；unordered tree 则可以在 lane 间并行合并。优化文档第
8 节用同一类 probe 给出对应的旁路和 exact/stream 对照。

## 11. 原始 Ara 的代码导航

| 主题 | 文件 | 重点符号 |
|---|---|---|
| 操作码、neutral 编码 | `hardware/include/ara_pkg.sv` | `VREDSUM`、`VFREDUSUM`、`resize_e` |
| 全局依赖和 VFU 选择 | `hardware/src/ara_sequencer.sv` | `vfu()`、hazard table |
| lane 请求和 operand 命令 | `hardware/src/lane/lane_sequencer.sv` | `is_reduct`、operand request |
| operand 转换和 neutral | `hardware/src/lane/operand_requester.sv`、`operand_queue.sv` | `ntr_red`、`OpQueueReductionZExt` |
| 整数局部/树形规约 | `hardware/src/lane/valu.sv` | `INTRA_LANE_REDUCTION`、`SIMD_REDUCTION` |
| 浮点局部/ordered 规约 | `hardware/src/lane/vmfpu.sv` | `OSUM_REDUCTION`、`ntr_filling_q` |
| 跨 lane 通道 | `hardware/src/sldu/sldu.sv` | `SLIDE_RUN_OSUM`、`red_stride_cnt_q` |
| 现有模块级说明 | `docs/source/modules/lane/valu.md` | Reduction Support |

阅读顺序建议是：先看本文第 1～3 节，再对照 `valu.sv` 的状态机，最后看
`vmfpu.sv` 与 `sldu.sv` 的握手。不要先从 `SIMD_REDUCTION` 开始，因为它
只是整个规约的最后一小段；真正决定性能的是局部 accumulator、跨 lane
token/tree 和提交队列三者的配合。
