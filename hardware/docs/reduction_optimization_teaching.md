# Ara 规约优化实现教学文档

本文解释 `reduction-optimization` 分支在原始 Ara 规约协议之上做了什么、
为什么这样做，以及如何从代码和仿真中复现这些机制。它是一份面向阅读 RTL
和继续开发的教学文档；逐次实验的完整记录仍在
[`reduction_acceleration_4lane.md`](reduction_acceleration_4lane.md)。

本文所说的当前优化配置是（最后一条 RTL 优化提交，不含本文档提交）：

```text
branch:       reduction-optimization
baseline:     30c6971b
latest RTL:   4eafb06b
NrLanes:      4
VLEN:         1024
```

`30c6971b` 是本轮优化开始前的基线快照，原始实现请先阅读
[`reduction_baseline_ara_teaching.md`](reduction_baseline_ara_teaching.md)。
本文中的“最终候选”专指 `NrLanes=4` 的已验证 profile，不表示所有 lane 数和
所有 RVV 浮点格式都已经参数化完成。

## 0. 读文档前先统一术语

| 术语 | 在本文中的简单含义 |
|---|---|
| bypass | 在 valid/ready 和 owner 标签都匹配时，绕过一个本来必经的寄存器或队列；不匹配就回到原路径。 |
| token | 一条规约当前拥有的 accumulator、局部 root 或跨 lane 部分和，以及它的指令 owner。 |
| context | 一条规约独立保存的控制和数值状态；多个 context 可以交错执行，但不能合并彼此的 accumulator。 |
| stream | 让独立规约重叠 local、tree 和提交的空槽；它不表示把不同指令的数值相加。 |
| exact | 对满足门禁的 unordered sum，在统一整数域中延迟中间舍入，最后只舍入一次；不是所有 reduction 都进入这条路径。 |
| epoch | 向量寄存器写入版本号，用来区分同一寄存器地址的不同定义。 |
| fallback | 当格式、依赖、tag 或握手条件不满足时使用的基线/legacy 路径。 |

## 1. 优化前后先看同一条数据流

基线把规约看成一条串行的局部 accumulator → SLDU tree/token → lane 0
提交链。优化没有改变 RVV 的结果语义，而是缩短这条链上可以证明安全的等待
和搬运：

```text
基线
  VRF -> operand_queue -> ALU/FPU -> result_queue
                                  -> spill -> SLDU
                                  -> next lane / lane 0 fold -> VRF

优化
  VRF ───────────────┐
  producer/result ───┼─ direct output/route bypass ──┐
  mask/VL metadata ──┘                                │
                                                       ▼
  local accumulator -> tagged context stream -> sparse/tree SLDU
             │                  │                       │
             │                  └─ early release ───────┘
             └─ exact packet (active windows, one final round)
                                                       │
  versioned seed/source/result cache ─────────────────┘
```

可以把优化分为四层来理解：

1. **同一条规约内部的旁路**：删掉 output、route、input 和 mask-off 的无效
   队列往返。
2. **多个规约上下文的流式调度**：在保留每条规约自身顺序的前提下，填充
   VMFPU、VALU 和 SLDU 的空槽。
3. **浮点 unordered sum 的 exact packet**：把中间舍入推迟到唯一的最终
   finalizer，并让稀疏指数窗口通过 SLDU 传输。
4. **跨指令数据流旁路**：用寄存器 epoch、producer ID 和完整地址标签，把
   尚未进入或刚离开 VRF 的结果安全地提供给后继规约或标量读取。

每一层都由独立的 Make 开关控制，因此可以做严格消融；`reduction_complete_4lane`
只是把已通过验证的开关组合成一个可复现 profile。

## 2. 构建开关和最终 profile

开关定义在 [`hardware/Makefile`](../Makefile) 的 reduction-acceleration
段。它们默认都是 `0`，所以普通构建仍保持基线行为。主要开关可按下表阅读：

| 层次 | Make 开关 | RTL define | 作用 | 依赖/范围 |
|---|---|---|---|---|
| 输出 | `reduction_output_bypass` | `ARA_RED_OUTPUT_BYPASS` | ordered VMFPU 结果直接满足 SLDU 的输出握手 | 基础旁路 |
| 路由 | `reduction_route_bypass` | `ARA_RED_ROUTE_BYPASS` | ordered SLDU one-hop 绕过固定 result-queue 返回 | 基础旁路 |
| mask | `reduction_mask_fastpath` | `ARA_RED_MASK_FASTPATH` | 有效 mask 的 fast loop | 基础旁路 |
| mask | `reduction_mask_skip` | `ARA_RED_MASK_SKIP` | masked-off token 不启动浮点运算，只消费协议 credit | 要求 output + mask fastpath |
| 输入 | `reduction_dense_input_bypass` | `ARA_RED_DENSE_INPUT_BYPASS` | ordered VMFPU 的 dense vector body 在 capture-on-stall 时直送 | 基础旁路 |
| 输入 | `reduction_tree_input_bypass` | `ARA_RED_TREE_INPUT_BYPASS` | integer VALU 和 unordered FP tree 输入端减少固定等待 | 基础旁路 |
| 尾部 | `reduction_terminal_fusion` | `ARA_RED_VMFPU_TERMINAL_FUSION` | unordered FP tree 的最后结果直接完成 | 基础旁路 |
| 上下文 | `reduction_context_flow` | `ARA_RED_CONTEXT_FLOW_4LANE` | 4 个 lane 的 tagged context 调度 | 4 lanes |
| 上下文 | `reduction_context_stream` | `ARA_RED_CONTEXT_STREAM_4LANE` | 同构规约在 local/tree/提交间流式重叠 | 要求 context flow，4 lanes |
| 上下文 | `reduction_slack_schedule` | `ARA_RED_SLACK_SCHED_4LANE` | 使用可证明的空槽做提前发射 | 要求 context stream |
| 上下文 | `reduction_heterogeneous_stream` | `ARA_RED_HETERO_STREAM_4LANE` | 对不同整数/FP opcode 使用安全的异构流规则 | 要求 context stream |
| 上下文 | `reduction_masked_stream` | `ARA_RED_MASKED_STREAM_4LANE` | 让 masked 流保留 MASKU credit 语义 | 要求 context stream |
| tree | `reduction_tree_stage_pipeline` | `ARA_RED_TREE_STAGE_PIPE_4LANE` | tree stage 间流水化 | 4 lanes |
| ordered | `reduction_ordered_interleave` | `ARA_RED_ORDERED_INTERLEAVE_4LANE` | ordered token 的 pre-arm/interleave | 4 lanes |
| ordered | `reduction_source_fusion` | `ARA_RED_SOURCE_FUSION_4LANE` | ordered source 的安全融合 | 要求 ordered interleave |
| ordered | `reduction_ordered_fast` | `ARA_RED_ORDERED_FAST_4LANE` | ordered 路径的短控制和快速完成 | 要求 output bypass |
| exact | `reduction_exact_sum` | `ARA_RED_EXACT_SUM_4LANE` | 打开 FP32 exact accumulator | 4 lanes |
| exact | `reduction_exact_segmented` | `ARA_RED_EXACT_SEGMENTED_4LANE` | 16 个指数段、低宽反馈累加 | 要求 exact sum |
| exact | `reduction_exact_global` | `ARA_RED_EXACT_GLOBAL_4LANE` | tagged packet 跨 lane 全局合并 | 要求 segmented，4 lanes |
| exact | `reduction_exact_fixed_window` | `ARA_RED_EXACT_FIXED_WINDOW_4LANE` | dense fixed-window 消融协议 | 要求 global；不在最终 profile |
| exact | `reduction_exact_fp16` | `ARA_RED_EXACT_FP16_4LANE` | native FP16 sum 和 FP16→FP32 widening exact | 要求 global |
| exact | `reduction_exact_stream` | `ARA_RED_EXACT_STREAM_4LANE` | packet N 完成中央阶段时提前发 packet N+1 | 要求 global |
| 跨指令 | `reduction_chain_bypass` | `ARA_RED_CHAIN_BYPASS_4LANE` | late seed、post-rounded source forwarding、result cache | 要求 global，4 lanes |

最终 profile 的 Make 入口只有：

```bash
cd hardware
make compile nr_lanes=4 vlen=1024 config=default \
  reduction_complete_4lane=1 no_fsdb=1 sim_dir=sim_red_complete4
```

Make 会强制打开表中的最终机制，并强制 `nr_lanes=4`。链旁路的严格 control
只需改一个变量：

```bash
make compile nr_lanes=4 vlen=1024 config=default \
  reduction_complete_4lane=1 reduction_complete_4lane_chain_bypass=0 \
  no_fsdb=1 sim_dir=sim_red_complete4_chain_off
```

`fixed_window` 没有被最终 profile 强制打开，因为它是 exact packet 的密集
窗口对照；最终候选使用 sparse active-window 协议。

## 3. 第一层：删掉规约内部的固定等待

### 3.1 output bypass 和 route bypass

基线的一个局部规约结果通常要先写入 result queue，再经过一个固定 spill 或
route 寄存器，下一拍才能被后继 stage 消费。对于 valid/ready 已经同时成立的
情况，这两个寄存器只保存了一个可以直接传输的值。

`output_bypass` 在 ordered VMFPU 的 FPU 输出已 valid、SLDU 已 ready 且当前仍
处于 ordered reduction 时直接完成这次握手；`route_bypass` 则在 SLDU 的
ordered one-hop route 已经确定且目标 lane 可以接收时绕过固定 result queue。
二者看起来都叫 bypass，但匹配的接口不同：前者是 VMFPU 到 SLDU，后者是
SLDU 到下一个 lane 的返回。VALU 的 unordered tree 旁路由后面的
`tree_input_bypass` 和 `tree_stage_pipeline` 负责，不使用这个 output define。

最重要的实现规则是：旁路只改变数据到达的拍数，不改变 owner。若 consumer
没有 ready，producer 必须继续持有原值；若旁路条件中任一 tag 不匹配，就回到
原始 queue/spill 路径。这样可以避免组合 ready 路径因暂态信号而丢数据。

在第一阶段 directed probe 中，4 lanes、`VL=32` 的 ordered FP sum 从
287 cycles 降到 255（只开其中一项），output 与 route 各自减少 32 cycles；
二者组合继续降到 223。每个 32-cycle 收益对应 32 个元素各省一个固定的
queue/route cycle。

### 3.2 mask fastpath 和 masked-off skip

基线会让 masked-off 元素经历部分正常的 operand、FPU 和反馈协议。优化把
“数值上不参与”拆成两个问题：

```text
active element:     读取 -> 运算 -> 更新 accumulator -> 返回结果
masked-off element: 读取/确认 mask -> 消费 token/credit -> 不启动运算
```

`mask_fastpath` 把连续的有效 mask 字节组织成更短的 fast loop；
`mask_skip` 则让 masked-off token 直接走 VMFPU output protocol，并使用和
MASKU 对齐的 return credit。它不能自行打开，因为没有 output bypass 和
mask fastpath 时，skip token 的 owner/credit 会与旧协议不一致，Makefile 会
自动补开前置开关。

这种优化不只是性能技巧。masked-off 的 sNaN、Inf 不能产生新的浮点异常，
所以 skip 路径必须完全跳过 FPU special-value sideband；它只能同步消费协议
所需的 token。现有回归覆盖了 active/masked-off 混合、全 mask-off 和不同
`VL` 尾部。

### 3.3 dense input bypass 和 tree input bypass

这两项都利用 capture-on-stall：输入已经到达并且执行单元当前因为后级阻塞，
那么先把输入保存在真正的 accumulator/树输入 owner 中，解除一个不必要的
队列往返。

```text
输入 beat 到达
       │
       ├─ consumer ready: 直接进入运算
       └─ consumer stall: capture 到当前 context/tree stage
                          下次 ready 时继续，不重新读 VRF
```

`dense_input_bypass` 只对 ordered VMFPU 的 unmasked dense body 生效；
`tree_input_bypass` 在 VALU 中只对整数规约生效，在 VMFPU 中只对
`VFREDUSUM/VFREDMIN/VFREDMAX/VFWREDUSUM` 这组 unordered opcode 生效。
这些路径必须让原始 spill 对已到达 token 保持优先，并且不能在 consumer 未
ready 时推进计数器；这比抽象地说“保存一个 beat”更重要，因为当前实现的
phase/state 已经是 owner 的一部分。

第一阶段 ordered probe 从 output+route 的 223 cycles 进一步降到 191；
第二阶段 tree input cut 让混合 ROI 从 329 降到 311，terminal fusion 再降到
308。ordered 在 tree 消融中的少量变化来自前序指令缩短后的调度上下文，不能
把它们全部归给 ordered datapath。

### 3.4 terminal fusion

unordered tree 返回 lane 0 后，最后一次 SIMD/FPU fold 的结果已经具备“这是
最终结果”的信息。基线仍可能先观察普通 valid 状态，再经过一个固定状态后
提交；terminal fusion 在最后一次 fold 的 FPU response 到达并满足提交条件
时，直接生成 result queue entry 并进入等待/提交状态。

它只适用于允许重排的 unordered 路径。ordered sum 不能使用这个融合，因为
ordered 的每一个元素都必须按架构顺序经过前一个 rounded accumulator。

### 3.5 tree stage 和 ordered interleave

`reduction_tree_stage_pipeline` 是 SLDU 侧的 elastic fall-through：unordered
tree stage 的结果如果本拍能被 lane 输入 spill 接收，就直接走 tree route；
只有未获 grant 的 lane 才进入通用 result queue。部分 grant 仍然回退到 queue，
所以它不会把 backpressure 变成丢 token 的条件。这条路径和 ordered
`route_bypass` 不同，前者服务 unordered tree，后者服务 ordered one-hop。

`reduction_ordered_interleave` 只压缩控制空洞，不改变 ordered arithmetic
recurrence。SLDU 在当前 ordered token 完成端到端 route、下一条指令已经在
queue 中且与当前指令同 opcode、`vtype`、`VL`、`vstart`、mask 形态时，提前
arm successor；两条指令的 token 仍然分别拥有自己的 owner。
`reduction_ordered_fast` 则为 ordered add 使用只保留加法 recurrence 的
FPnew 实现，删除未使用的除法、转换、分类等实现组；它改变硬件资源配置，
不改变舍入和结果语义。

## 4. 第二层：tagged context 和流式调度

### 4.1 为什么需要 context

单条规约即使减少了固定 cycle，也会在下面几段之间留下空洞：

```text
local accumulation -> tree merge -> SIMD/finalizer -> VRF commit
```

基线每个执行单元的 active FSM 一次只推进当前 reduction context；下一条独立
规约即使已经进入 instruction queue，通常也不能占用同一段 active datapath。
优化在 4-lane 配置内为规约保留有限的 context 元数据，让前台 context 做
必须按序的树/提交工作，后台 context 使用空闲的 local ALU/FPU 或输入接口。

从协议角度看，一个 context 至少需要能恢复：

```text
instruction id / opcode / ordered-or-unordered
SEW / VL / vstart / vm / rounding mode
destination / source / mask metadata
accumulator valid + data
tree stage / processing pointer / issue pointer
```

因此“流式”不是把不同指令的数值相加，而是让每条指令的状态在自己的 tag
下交错出现：

```text
cycle:       0   1   2   3   4   5   6
context A:  local local tree tree  final wait commit
context B:      local local local tree tree final ...
```

任何需要 ordered token 的 context 仍然只有一个 owner；stream 只填补另一个
context 的空槽，不允许跨 context 合并 accumulator。

### 4.2 context flow、stream、slack 和异构门禁

`context_flow` 提供四 lane 的 tagged 状态和指针；`context_stream` 才允许
后继 context 进入。普通 context stream 的兼容函数按机制开关检查 opcode、
SEW、mask 形态和（浮点路径的）rounding 等字段；打开 heterogeneous stream
后会有意放宽其中一些相同性要求，但只对已经证明可共存的 local DAG 生效。
`masked_stream` 还要处理 MASKU credit。它不是一个统一的“所有字段都相等”
门禁。

exact early-release stream 使用更严格的兼容函数：要求 opcode、完整 vtype、
VL、vstart、vm、rounding mode 和 `cvt_resize` 相同；ordered source alias
则使用自己的 request 字段比较。不要把 exact stream 的完整 fingerprint
检查误套到普通 context stream，也不要把普通 stream 的放宽条件用于 exact
packet。

已有数据：16 条独立 `vfredusum` 流的 ROI 从 612 降到 402 cycles；FP/integer
连续流还覆盖了 masked、min/max 和 widening。流式机制只改变启动间隔和
operand-wait，结果提交仍由主 sequencer 按原架构顺序完成。

### 4.3 early release：为什么可以复用一个 accumulator

exact packet 的最后一个 local limb 被 SLDU 接受后，lane accumulator 的数值
已经由 SLDU 持有。后面等待 global merge、finalizer 和返回 token 的时间不再
读取这个 local accumulator；普通 context stream 使用自己的 root FIFO 和
context 状态，不应被理解为自动复制了同一份 exact accumulator。

因此 `reduction_exact_stream` 使用两个 owner 指针，而不是复制第二份
288-bit accumulator：

```text
processing pointer: packet N，仍需按序完成/退休
issue pointer:      packet N+1，可以开始 local accumulate

N:   local -> packet/SLDU -> global merge -> finalizer -> retire
N+1:                  local accumulate -> 等 N 的 promotion
```

N+1 只有在 N 的最后一个 limb 完成握手后才能使用 accumulator；N+1 即使已
完成 local work，也必须等 N 的 final token 被接受后再 promotion。这样重叠
的是 local input 和上一条的 central completion，SLDU finalizer 与架构写回仍
只有一个 owner。

4-lane 的严格消融结果为：16 条 FP32 stream `260→215`，8 条 FP16→FP32
widening `156→135`，8 条 masked FP32 `275→254`。这些数字来自相同 exact
算法，只切换 early-release 开关。

## 5. 第三层：FP exact unordered sum（以 FP32 域为主）

### 5.1 为什么普通 tree 不等于 exact sum

unordered 浮点规约允许改变结合顺序，但如果希望结果对 tree 形状不敏感，
不能在每个 lane 或每个 tree stage 都把 binary32 再舍入一次。优化新增：

```text
fp32 source/seed -> exact integer-domain accumulator
                 -> segmented local state
                 -> tagged SLDU global merge
                 -> one central finalizer/rounding
```

这里的 `exact` 只覆盖通过门禁的 unordered sum（当前是 `VFREDUSUM`、
`VFWREDUSUM`，以及打开 FP16 开关后的 native FP16 `VFREDUSUM`）；ordered
sum、min/max 和不满足格式条件的规约仍走各自的 legacy/tree 路径。

源文件是 [`fp32_exact_reduction_accum.sv`](../src/lane/fp32_exact_reduction_accum.sv)
和 [`fp32_exact_reduction_finalize.sv`](../src/lane/fp32_exact_reduction_finalize.sv)。
对有限 binary32，最小单位为 `2^-149`。exact 模块的 288-bit 参数按源码
注释预留了“最多 256 个 binary32 向量元素加一个 scalar seed”的容量；在
本文的 `VLEN=1024`、e32/m1 配置中，架构 `VLMAX` 实际是 32，256 是状态
设计容量而不是一条当前指令的 `VL`。最终舍入前，finite limb 和 seed 都
保持在同一个整数域中。

### 5.2 16 个指数段和低宽反馈

直接让每个 lane 每拍更新 288-bit accumulator 会产生很宽的反馈加法器。当前
segmented 版本把 finite significand 按指数分成 16 个窗口，每个窗口使用
49-bit 有符号 bin；元素只更新命中的窗口。

```text
decode(binary32)
      │ sign / exponent / significand
      ▼
select one of 16 exponent windows
      │ local shift + signed add
      ▼
segmented state -> merge slots -> 288-bit global state
```

这不是近似截断：窗口保存的是精确整数域中的部分和，最终 merge 时仍恢复
完整的 limb 位权。窗口化的收益是稳态反馈宽度从 288 bit 收窄；代价是多窗口
写入网络和更复杂的 packet metadata。

### 5.3 special value 和唯一 finalizer

exact accumulator 不把 NaN/Inf 当作普通整数。每个 packet 携带 special
metadata，至少区分有限项、正/负无穷、qNaN/sNaN 和符号零。global merge
只合并 metadata 和 finite limbs；finalizer 最后根据 RVV rounding mode 完成：

1. seed 是否需要插入 exact 域；
2. sNaN 是否产生 `NV`；
3. `+Inf + -Inf` 的 invalid 规则；
4. signed zero 规则；
5. overflow、subnormal、tie-to-even 和 `NX/OF`；
6. binary32 或 FP16 结果的最终编码。

`fp32_exact_reduction_finalize.sv` 的 `AccWidth` 断言保证状态不会被错误缩窄。
exact family 还可以支持 native FP16 unordered sum；它的最终结果按 FP16
格式舍入。FP16→FP32 widening 可以复用同一 288-bit 域：binary16 最小非零量 `2^-24`
对应 binary32 exact 域中的 bit 125，不需要增加新的舍入点。当前代码用
`vtype.vsew == EW32` 表示这条 widening reduction 的 destination/累加格式，
operand queue 再把 binary16 source 精确扩展到 binary32；不要把这个门禁读成
“source 必须是 e32”。
EW64 unordered 则超出当前域，继续使用经过回归的 legacy fallback。

### 5.4 packet header 和 sparse active window

每个 lane 不再把完整固定宽度 accumulator 当作普通数据发送，而是发送带
header 的 packet。当前 RTL 的 header 用来恢复 lane/指令 rendezvous 和精确
语义，字段包括：

```text
lane id / instruction id
seed value + seed-valid（普通 exact packet 由 lane 0 携带）
rounding mode / accumulation format (FP32 domain or native FP16 result)
special flags / finite-source / signed-zero metadata
active limb count + sign bit
masked-operation marker
```

`fixed_window` 会发送统一的密集窗口，适合作为控制；最终 sparse 协议只发送
从最高非符号扩展 limb 到 guard limb 的必要窗口，并用隐含符号扩展补足未
发送的高位。它不是一个 bitmap；`active limb count` 和 sign bit 描述的是
连续的高位窗口。late seed 的 producer ID/epoch 由 `pe_req` 和 SLDU 的
versioned table 传递，不编码在这个 64-bit header 中。SLDU 必须按 lane/id
magic tag 对齐来自不同 lane 的 packet，不能只依赖到达周期。

已有公平对照：混合规约 `187→181→173→170`（普通 tree、segmented local、
global fixed-window、global sparse）；16 条 `vfredusum` stream 从 399 降到
260，单条 exact `vfredusum` latency 在对应阶段降至 21 cycles。普通整数、
ordered FP、min/max 和不满足 exact eligibility 的 FP 路径不进入此 packet
协议。

## 6. 第四层：跨指令数据流和版本化旁路

### 6.1 为什么 instruction ID 不够

规约链中常见三种等待：

```text
reduction P 写 vd[0] -> reduction Q 从 vs1[0] 读 seed
VFMUL P 写完整向量 -> VFREDUSUM Q 读 source
reduction P 写 vd[0] -> VFMV.F.S / VL=1 store 读结果
```

仅按 instruction ID 匹配会遇到 ID 循环复用；仅按寄存器地址匹配会遇到中间
指令重定义。优化在 [`ara_pkg.sv`](../include/ara_pkg.sv) 中定义 8-bit epoch
的类型和宽度（`VRegVersionWidth=8`）；真正为 32 个 vector register 维护
当前 epoch 的是 [`ara_sequencer.sv`](../src/ara_sequencer.sv)。epoch 和 request
metadata 在
[`ara_typedef.svh`](../include/ara/ara_typedef.svh) 的 `pe_req_t` 中传递：

```text
seed_version, vd_version, vs1_version, vs2_version,
vd_operand_version, ordered_source_alias
```

不同旁路的匹配键不同，常见的 source/result forwarding 至少包含：

```text
producer/hazard owner + source epoch + full VRF address + byte coverage + valid
```

late seed 使用 `producer ID + producer destination + seed epoch`；SLDU 的
exact result table 也用这个关系验证命中。它不需要把 VRF word address 当作
seed 的匹配键，不能把所有旁路机制简化成同一个 tuple。

### 6.2 late-bound seed

`ara_sequencer.sv` 的 `exact_chain_eligible()` 只对已经满足 exact profile
条件的 producer/consumer 开启 late seed。流程是：

```text
1. sequencer 分配 producer destination 的新 epoch
2. 发现 consumer vs1 期待这个仍在途的 epoch
3. 清除可以证明无害的 seed RAW/WAW/WAR
4. 不为旧 seed 发起 MulFPUA/VRF read
5. consumer 先累加自己的 vs2 body
6. producer finalizer 完成后，以 ID+epoch 写入 seed table
7. consumer 在 final boundary 绑定 rounded seed
```

late seed 改变的是 seed 到达时间，不增加一次浮点舍入。若 producer ID、epoch
或 destination 不匹配，consumer 必须保留原 VRF/legacy 路径；其它 source、
mask 和真实数据依赖仍由 sequencer hazard 保留。seed table 不会在第一次读取
后立刻销毁，因此一个 producer 可以安全地被多个 consumer 扇出；ID 被重新
分配给新 producer 时先使旧槽失效。

### 6.3 `VFMUL` 的 post-rounded source forwarding

VFMUL 的 result queue 写回顺序按 VRF bank grant 决定，不保证地址单调。正确
的 forwarding 因此不能只看 producer ID：

```text
producer hazard + source epoch + full word address + byte-enable
       全部匹配 -> grant 后的已舍入 beat 可旁路给 operand queue
       地址不匹配 -> 暂停请求，等待目标地址，不读旧 VRF 值
```

旁路的是 VFMUL 已按架构 rounding mode 舍入的结果，不是 fpnew 内部未舍入乘积。
forwarded beat 还要注册一拍，与正常 VRF read response 对齐，并消耗同一个
operand queue credit；这样 `先写 VRF 再读 VRF` 与 `直接旁路` 的观察结果一致。

### 6.4 reduction result cache

规约结果可能已经获得 VRF grant，但后继 `VFMV.F.S`、`VMV.X.S` 或 `VL=1`
store 还没有立刻读到它。lane 内的 `operand_requester.sv` 保存两个短寿命
result-cache entry；这是“规约结果到后继 operand”的 cache，与 SLDU 中按
instruction ID 保存的 exact late-seed table 是两个不同结构。每个 lane 的
entry 保存：

```text
valid, destination epoch, full VRF address,
64-bit rounded data, byte-enable, age
```

命中要求地址、epoch 和所需 byte coverage 全部满足。规约只定义 destination
element 0，因此普通大 VL 的完整 64-bit store 不能只用 cache 替代整个 word；
`VL=1` 的标量 store 只请求已定义的低字节，才可以直接命中。未命中时仍走
VRF fallback。`age` 每拍递增，entry 在 8-bit epoch 回绕前失效，避免旧结果
跨越版本回绕后再次命中。

VALU/VMFPU 的 result-queue entry 自带 `is_reduction`，填入 cache 和延迟写回
时都必须沿用这个 owner 标签，不能从 live commit head 临时推导；否则 stream
中旧规约结果会被误归类为后继非规约结果，造成 commit count 错误。

### 6.5 ordered source alias

ordered source fusion 还会记录 `ordered_source_alias`，用于识别当前 request
是否与上一次 ordered source 具有允许复用的完整 fingerprint。它不能只用
`vs2` 地址比较，必须同时检查 opcode、SEW、VL、vstart、mask、rounding、
`vs1`/`vs2`、scalar seed 和 use flags；版本化 hazard 仍由 sequencer 单独
负责。否则不同语义的 ordered 指令会错误复用 leader 的 memoized result/fflags。

## 7. 正确性保护：优化可以绕过数据，但不能绕过协议

继续开发时应把以下检查当作不可删除的安全边界：

### 7.1 valid/ready 和 owner 守恒

- producer 在 consumer 未 ready 时必须保留 data 和所有 metadata；
- 一个 token 只能有一个 owner，旁路不能让 queue 和 bypass 同时消费；
- 每个 bypass 都必须有 fallback，不能把未命中的情况当作零数据；
- context 的 issue/promotion 数必须守恒，不能只看总 cycles；
- early release 只能发生在最后一个 limb 被 SLDU 接受之后。

### 7.2 语义标签完整性

设计旁路或新增 stream 时，必须明确它实际比较哪些字段：exact stream 比较
opcode、完整 vtype、VL、vstart、vm、rounding 和 resize；普通 stream 的兼容函数可能
按开关放宽 opcode/SEW/rounding 的相同性。exact packet 的真实 header 还需要
format、special、seed-valid、limb count 和 sign 等字段。字段无法证明兼容时，
应选择 legacy fallback。

### 7.3 顺序和异常

- unordered tree/exact 可以改变内部结合顺序，但 ordered token 不能重排；
- exact finalizer 才能执行唯一最终舍入，不能在 packet merge 中偷偷舍入；
- masked-off sNaN/Inf 不能触发 active FPU 的异常；
- late seed 必须保持 seed 的 NaN、Inf、signed zero 和 fflags 语义；
- result cache 只覆盖已定义字节，未覆盖字节必须从 VRF 合并或读取；
- unsupported EW64 exact、不同 vtype 或版本不匹配自动回退。

### 7.4 用哪些检查确认没有破坏基线

当前资料中的验证分为三类：

1. **RTL 编译**：最终 profile 已完成 VCS elaboration，记录为 0 error。
2. **功能回归**：整数、unordered/ordered FP、min/max、mask、widening 和
   EW64 fallback 继续 PASS；官方 `vfredusum/vfredosum` 集合为 16/17，唯一
   失败与 clean baseline 相同，是 VLEN=1024 时测试硬编码 `VL=64` 超过
   e32/m1 的实际 VLMAX=32。
3. **定向数据流**：late seed、交错/扇出、VFMUL forwarding、整数/FP result
   cache 和 `VL=1` store 都做位级检查；当前链旁路 probe 的 14 个结果全 PASS，
   analyzer 28/28 指标覆盖，`--require-ready` 为 high confidence。

## 8. 当前实测结果和正确的解读方式

下表汇总已有记录中的代表性结果。所有数字都是 RTL 仿真 cycle，不是综合后
时钟时间；不同 workload 的 ROI 不能直接相加。

表中的“单条指令延迟”是 probe 记录的目标 reduction execution latency；“ROI
total cycles”是包含多条指令、依赖检查和结果校验的完整测试区间。二者的统计
边界不同，不能互相替代。

| workload / 对比 | 对照配置 | 优化配置 | 改善 | 说明 |
|---|---:|---:|---:|---|
| `VFREDOSUM` 第一阶段 clean→output+route+dense | 287 | 191 | 33.45% | 同一 ordered probe |
| tree/fusion 混合 ROI | 329 | 308 | 6.38% | tree input + terminal fusion |
| exact 混合 ROI（普通 tree→sparse） | 187 | 170 | 9.09% | 先后包含 exact 协议差异 |
| 单条 exact `vfredusum`（segmented→sparse） | 38 | 21 | 44.74% | 对应阶段的 execution latency |
| 16× exact `vfredusum` stream | 399 | 260 | 34.84% | 包含 sparse 和 early release |
| chain probe | 949 | 881 | 7.17% | 14 个结果全 PASS |
| `vsdot_asm` kernel | 1398 | 1308 | 6.44% | 32 组乘法规约，Core Test PASS |

这些行来自不同阶段的严格消融，不能把整张表看成一条单调累加曲线：例如
287→191 只隔离 ordered bypass/input cut，187→170 比较 exact packet 协议，
399→260 还包含 exact stream early release，而 1398→1308 是最终 4-lane
profile 的 chain-bypass 对照。每个百分比只在同一行的对照/优化配置之间成立。

`vsdot_asm` 的 90-cycle 收益不是单个旁路事件的简单相加：candidate 中有
29/29 late seed issue/bind、512 个 `MulFPUC` beat 和 3 个 versioned
result-cache 命中；同时 WAR/false-hazard 从 621 降到 506，sequencer block
从 558 降到 474。剩余压力仍是跨迭代 WAR/false-hazard 和全局 sequencer
blocking，说明下一步应研究 destination renaming、有限窗口 scoreboard 或
producer-consumer co-scheduling。

这些周期结果尚不能推出论文级 PPA 结论。已有
[`fp32_exact_reduction_synth_wrappers.sv`](../tb/fp32_exact_reduction_synth_wrappers.sv)
结构面积预算，但整机还需要把新增 SLDU limb merger、ready 组合路径、Fmax、
面积和功耗一起综合评估；报告执行时间时应使用 `cycles × clock_period`。

## 9. 复现实验和继续开发的入口

### 9.1 最小编译/仿真流程

在 `hardware` 目录执行：

```bash
make compile nr_lanes=4 vlen=1024 config=default \
  reduction_complete_4lane=1 no_fsdb=1 sim_dir=sim_red_complete4

make sim nr_lanes=4 vlen=1024 config=default \
  reduction_complete_4lane=1 no_fsdb=1 \
  sim_dir=sim_red_complete4 app=perf_reduction_chain_bypass_probe
```

做 chain-off 对照时只改：

```bash
make sim nr_lanes=4 vlen=1024 config=default \
  reduction_complete_4lane=1 reduction_complete_4lane_chain_bypass=0 \
  no_fsdb=1 sim_dir=sim_red_complete4_chain_off \
  app=perf_reduction_chain_bypass_probe
```

具体 probe 在仓库根目录的 `apps/` 下，比较脚本和瓶颈归因工具在
`hardware/scripts/`，详细参数仍以实验记录为准；建议先复制现有
`sim_red_complete4*` 目录名，避免覆盖已有
波形/日志。

### 9.2 建议的阅读顺序

1. 先读本文第 1～2 节，确定 profile 和开关依赖。
2. 对照 `valu.sv` 和 `vmfpu.sv`，先理解 bypass/context 的 owner 和状态。
3. 再看 `sldu.sv`，确认 route、tree stage、packet merge 和 ordered token。
4. 阅读两个 exact 模块，理解 accumulator、special metadata 和 finalizer。
5. 最后看 `ara_sequencer.sv`、`ara_typedef.svh` 和 result queue，理解跨指令
   版本匹配；不要先从 hazard 清除代码推断数值语义。

### 9.3 代码导航表

| 主题 | 文件 | 重点内容 |
|---|---|---|
| 开关和 profile | `hardware/Makefile` | 默认开关、依赖、4-lane 强制组合 |
| opcode/epoch/neutral | `hardware/include/ara_pkg.sv` | reduction opcode、`VRegVersionWidth`、`resize_e` |
| request metadata | `hardware/include/ara/ara_typedef.svh` | seed/vd/vs 版本、alias、late seed |
| 全局调度 | `hardware/src/ara_sequencer.sv` | `exact_chain_eligible`、hazard 清除、版本分配 |
| 整数/context/tree | `hardware/src/lane/valu.sv` | input bypass、context stream、tree/commit |
| 浮点/context/exact | `hardware/src/lane/vmfpu.sv` | mask skip、ordered fast、exact packet、early release |
| 跨 lane | `hardware/src/sldu/sldu.sv` | route bypass、tree stage、packet merge、ordered alias |
| 跨指令 operand forwarding | `hardware/src/lane/operand_requester.sv` | VFMUL source forwarding、two-entry reduction result cache、byte coverage |
| chain probe | `apps/perf_reduction_chain_bypass_probe/main.c` | late seed、source forwarding、result cache 的定向检查 |
| exact local state | `hardware/src/lane/fp32_exact_reduction_accum.sv` | 288-bit/segmented accumulator |
| exact final rounding | `hardware/src/lane/fp32_exact_reduction_finalize.sv` | special、rounding、FP32/FP16 结果 |
| operand credit | `hardware/src/lane/operand_queue.sv` | mask、byte coverage、forwarded beat 时序 |

## 10. 适合继续工作的边界

当前最稳妥的继续方式是保留 `reduction_complete_4lane=1` 作为功能基准，
每次只改一个机制并用 chain-off/clean 对照。需要明确的边界有：

- 最终候选只对 4 lanes、VLEN=1024 给出完整性能结论；2/8/16 lanes 尚未
  作为同等覆盖的最终 profile。
- exact global 当前覆盖 FP32、native FP16、FP16→FP32 widening 和相应 masked/unmasked
  stream；EW64 unordered 仍走 legacy fallback。
- ordered reduction 保持顺序语义，不能直接套 unordered exact tree。
- exact state 的宽度、SLDU packet merger 和组合 ready 路径必须做综合后评估。
- `vsdot` 中仍有明显 WAR/false-hazard 和 sequencer block，下一阶段应在不
  放宽版本/顺序安全条件的前提下减少这些等待。

如果要重新开始某一条优化实验，最有区分度的 control 是关闭对应的单个
`reduction_*` 开关，而不是回退整个分支；如果要验证最终闭环，则用
`reduction_complete_4lane=1` 并只把 `reduction_complete_4lane_chain_bypass`
设为 `0` 做同 profile 对照。
