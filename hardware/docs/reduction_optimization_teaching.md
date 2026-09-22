# Ara 规约优化实现教学文档

本文解释 `reduction-optimization` 分支在原始 Ara 规约协议之上做了什么、
为什么这样做，以及如何从代码和仿真中复现这些机制。它是一份面向阅读 RTL
和继续开发的教学文档；逐次实验的完整记录仍在
[`reduction_acceleration_4lane.md`](reduction_acceleration_4lane.md)。

本文所说的当前优化配置是：

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
| 输出 | `reduction_output_bypass` | `ARA_RED_OUTPUT_BYPASS` | VMFPU/VALU 完成后直接满足下一 stage 的输出握手 | 基础旁路 |
| 路由 | `reduction_route_bypass` | `ARA_RED_ROUTE_BYPASS` | SLDU route 可用时绕过固定 spill 返回 | 基础旁路 |
| mask | `reduction_mask_fastpath` | `ARA_RED_MASK_FASTPATH` | 有效 mask 的 fast loop | 基础旁路 |
| mask | `reduction_mask_skip` | `ARA_RED_MASK_SKIP` | masked-off token 不启动浮点运算，只消费协议 credit | 要求 output + mask fastpath |
| 输入 | `reduction_dense_input_bypass` | `ARA_RED_DENSE_INPUT_BYPASS` | dense vector body 在 capture-on-stall 时直送 | 基础旁路 |
| 输入 | `reduction_tree_input_bypass` | `ARA_RED_TREE_INPUT_BYPASS` | tree 输入端减少固定等待 | 基础旁路 |
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
| exact | `reduction_exact_fp16` | `ARA_RED_EXACT_FP16_4LANE` | FP16→FP32 widening exact | 要求 global |
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

`output_bypass` 在 producer 输出已 valid、consumer 已 ready 且 opcode/context
仍匹配时直接完成这次握手；`route_bypass` 则在 SLDU 的 route 已经确定且目标
lane 可以接收时绕过固定 route/spill。二者看起来都叫 bypass，但匹配的接口
不同：前者是执行单元到后继 stage，后者是 SLDU 内部的跨 lane 返回。

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

`dense_input_bypass` 主要改善 ordered/dense body；`tree_input_bypass` 主要
改善整数和 unordered FP tree。二者都必须同时保存 valid、mask、opcode、SEW
和 context tag，不能只保存 64-bit data。否则一个 stall 跨过 context 切换时，
旧 beat 会被错误地交给另一条规约。

第一阶段 ordered probe 从 output+route 的 223 cycles 进一步降到 191；
第二阶段 tree input cut 让混合 ROI 从 329 降到 311，terminal fusion 再降到
308。ordered 在 tree 消融中的少量变化来自前序指令缩短后的调度上下文，不能
把它们全部归给 ordered datapath。

### 3.4 terminal fusion

unordered tree 的最后一个 active root 在协议上已经具备“这是最终结果”的
信息。基线仍可能把它送回普通 FPU feedback、再经过一个固定状态后提交。
terminal fusion 在 final tree token、最后一个有效元素和提交条件同时成立时，
直接生成 result queue entry。

它只适用于允许重排的 unordered 路径。ordered sum 不能使用这个融合，因为
ordered 的每一个元素都必须按架构顺序经过前一个 rounded accumulator。

## 4. 第二层：tagged context 和流式调度

### 4.1 为什么需要 context

单条规约即使减少了固定 cycle，也会在下面几段之间留下空洞：

```text
local accumulation -> tree merge -> SIMD/finalizer -> VRF commit
```

基线全局 FSM 往往只服务当前 instruction，下一条独立规约要等它完全退出。
优化在 4-lane 配置内为规约保留有限的 context 元数据，让前台 context 做
必须按序的树/提交工作，后台 context 使用空闲的 local ALU/FPU 或输入接口。

一个 context 至少携带：

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
相同 eligibility 的后继 context 进入。`slack_schedule` 使用已知不会影响
当前 root 的空槽提前发射；`heterogeneous_stream` 放宽到安全的整数、FP sum、
min/max 组合；`masked_stream` 额外检查 MASKU credit。

后继是否能流式进入不是简单的“两个 opcode 相同”。门禁会比较完整的
instruction fingerprint，包括 opcode、vtype/SEW、VL、vstart、vm、rounding
mode、resize 控制和 context 状态。任一项变化就回到安全的串行或 legacy
路径。这样不同宽度、不同 mask 语义和不同异常规则不会共享一个不兼容的
accumulator。

已有数据：16 条独立 `vfredusum` 流的 ROI 从 612 降到 402 cycles；FP/integer
连续流还覆盖了 masked、min/max 和 widening。流式机制只改变启动间隔和
operand-wait，结果提交仍由主 sequencer 按原架构顺序完成。

### 4.3 early release：为什么可以复用一个 accumulator

exact packet 或普通 tree 的最后一个 local limb/root 被 SLDU 接受后，lane
accumulator 的数值已经由 SLDU 持有。后面等待 global merge、finalizer 和
返回 token 的时间不再读取这个 local accumulator。

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

## 5. 第三层：FP32 exact unordered sum

### 5.1 为什么普通 tree 不等于 exact sum

unordered 浮点规约允许改变结合顺序，但如果希望结果对 tree 形状不敏感，
不能在每个 lane 或每个 tree stage 都把 binary32 再舍入一次。优化新增：

```text
fp32 source/seed -> exact integer-domain accumulator
                 -> segmented local state
                 -> tagged SLDU global merge
                 -> one central finalizer/rounding
```

源文件是 [`fp32_exact_reduction_accum.sv`](../src/lane/fp32_exact_reduction_accum.sv)
和 [`fp32_exact_reduction_finalize.sv`](../src/lane/fp32_exact_reduction_finalize.sv)。
对有限 binary32，最小单位为 `2^-149`；当前 4-lane、VLEN=1024 配置采用
至少 288 bit 的统一精确域，保证 256 个向量元素和 scalar seed 能在最终
舍入前表示。

### 5.2 16 个指数段和低宽反馈

直接让每个 lane 每拍更新 288-bit accumulator 会产生很宽的反馈加法器。当前
segmented 版本把 finite significand 按指数分成 16 个窗口，每个窗口保存
低宽有符号计数；元素只更新命中的窗口。

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
FP16→FP32 widening 可以复用同一 288-bit 域：binary16 最小非零量 `2^-24`
对应 binary32 exact 域中的 bit 125，不需要增加新的舍入点；
EW64 unordered 则超出当前域，继续使用经过回归的 legacy fallback。

### 5.4 packet header 和 sparse active window

每个 lane 不再把完整固定宽度 accumulator 当作普通数据发送，而是发送带
header 的 packet。header 用来恢复上下文和精确语义，典型信息包括：

```text
lane / instruction / packet identity
format (FP32 or FP16->FP32)
rounding mode / seed identity
special flags / signed-zero metadata
active-window bitmap or min/max window
limb count / end-of-packet
```

`fixed_window` 会发送统一的密集窗口，适合作为控制；最终 sparse 协议只发送
实际出现的 active windows，并用隐含符号扩展补足未发送的高位。SLDU 必须按
header tag 对齐来自不同 lane 的 packet，不能只依赖到达周期。

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
指令重定义。优化在 [`ara_pkg.sv`](../include/ara_pkg.sv) 中为每个 vector
register 维护 8-bit epoch（`VRegVersionWidth=8`），并在
[`ara_typedef.svh`](../include/ara/ara_typedef.svh) 的 `pe_req_t` 中传递：

```text
seed_version, vd_version, vs1_version, vs2_version,
vd_operand_version, ordered_source_alias
```

真正的旁路匹配至少是：

```text
producer ID + register epoch + full VRF address + byte coverage + valid
```

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

late seed 改变的是 seed 到达时间，不增加一次浮点舍入。若 producer ID、epoch、
destination 或完整指令 fingerprint 不匹配，consumer 必须保留原 VRF/legacy
路径。seed table 不会在第一次读取后立刻销毁，因此一个 producer 可以安全地
被多个 consumer 扇出；ID 被重新分配给新 producer 时先使旧槽失效。

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
store 还没有立刻读到它。每个 lane 保存两个短寿命 result-cache entry：

```text
valid, destination epoch, full VRF address,
64-bit rounded data, byte-enable, age
```

命中要求地址、epoch 和所需 byte coverage 全部满足。规约只定义 destination
element 0，因此普通大 VL 的完整 64-bit store 不能只用 cache 替代整个 word；
`VL=1` 的标量 store 只请求已定义的低字节，才可以直接命中。未命中时仍走
VRF fallback。

结果 entry 自带 `is_reduction`，不能在延迟写回时从 live commit head 推导，
否则 stream 中旧规约结果会被误归类为后继非规约结果，造成 commit count 错误。

### 6.5 ordered source alias

ordered source fusion 还会记录 `ordered_source_alias`，用于识别当前 source
是否与上一次 ordered source 具有允许复用的完整 fingerprint。它不能只用
`vs2` 地址比较，必须同时检查 opcode、SEW、VL、mask、rounding 和版本；否则
不同语义的 ordered 指令会共享错误的 source token。

## 7. 正确性保护：优化可以绕过数据，但不能绕过协议

继续开发时应把以下检查当作不可删除的安全边界：

### 7.1 valid/ready 和 owner 守恒

- producer 在 consumer 未 ready 时必须保留 data 和所有 metadata；
- 一个 token 只能有一个 owner，旁路不能让 queue 和 bypass 同时消费；
- 每个 bypass 都必须有 fallback，不能把未命中的情况当作零数据；
- context 的 issue/promotion 数必须守恒，不能只看总 cycles；
- early release 只能发生在最后一个 limb 被 SLDU 接受之后。

### 7.2 语义标签完整性

旁路和 stream 的 tag 至少覆盖 opcode、SEW、VL、vstart、vm、rounding、resize、
destination/source epoch 和 mask 状态。exact packet 还需要 format、special、
seed 和 active-window 信息。任何标签不完整时，应选择 legacy fallback。

### 7.3 顺序和异常

- unordered tree/exact 可以改变内部结合顺序，但 ordered token 不能重排；
- exact finalizer 才能执行唯一最终舍入，不能在 packet merge 中偷偷舍入；
- masked-off sNaN/Inf 不能触发 active FPU 的异常；
- late seed 必须保持 seed 的 NaN、Inf、signed zero 和 fflags 语义；
- result cache 只覆盖已定义字节，未覆盖字节必须从 VRF 合并或读取；
- unsupported EW64 exact、不同 vtype 或版本不匹配自动回退。

### 7.4 用哪些检查确认没有破坏基线

当前资料中的验证分为三类：

1. **RTL 编译**：最终 profile VCS clean，0 error、0 warning。
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

| workload / 对比 | control | candidate | 改善 | 说明 |
|---|---:|---:|---:|---|
| `VFREDOSUM` 第一阶段 clean→output+route+dense | 287 | 191 | 33.45% | 同一 ordered probe |
| tree/fusion 混合 ROI | 329 | 308 | 6.38% | tree input + terminal fusion |
| exact 混合 ROI（普通 tree→sparse） | 187 | 170 | 9.09% | 先后包含 exact 协议差异 |
| 单条 exact `vfredusum`（segmented→sparse） | 38 | 21 | 44.74% | 对应阶段的 execution latency |
| 16× exact `vfredusum` stream | 399 | 260 | 34.84% | 包含 sparse 和 early release |
| chain probe | 949 | 881 | 7.17% | 14 个结果全 PASS |
| `vsdot_asm` kernel | 1398 | 1308 | 6.44% | 32 组乘法规约，Core Test PASS |

`vsdot_asm` 的 90-cycle 收益不是单个旁路事件的简单相加：candidate 中有
29/29 late seed issue/bind、512 个 `MulFPUC` beat 和 3 个 versioned
result-cache 命中；同时 WAR/false-hazard 从 621 降到 506，sequencer block
从 558 降到 474。剩余压力仍是跨迭代 WAR/false-hazard 和全局 sequencer
blocking，说明下一步应研究 destination renaming、有限窗口 scoreboard 或
producer-consumer co-scheduling。

这些周期结果尚不能推出论文级 PPA 结论。现有文档有 exact wrapper 的结构
面积预算，但整机还需要把新增 SLDU limb merger、ready 组合路径、Fmax、面积
和功耗一起综合评估；报告执行时间时应使用 `cycles × clock_period`。

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
reduction_complete_4lane_chain_bypass=0
```

具体 probe、比较脚本和瓶颈归因工具分散在 `hardware/apps`、`hardware/scripts`
和实验记录中；建议先复制现有 `sim_red_complete4*` 目录名，避免覆盖已有
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
| exact local state | `hardware/src/lane/fp32_exact_reduction_accum.sv` | 288-bit/segmented accumulator |
| exact final rounding | `hardware/src/lane/fp32_exact_reduction_finalize.sv` | special、rounding、FP32/FP16 结果 |
| operand credit | `hardware/src/lane/operand_queue.sv` | mask、byte coverage、forwarded beat 时序 |

## 10. 适合继续工作的边界

当前最稳妥的继续方式是保留 `reduction_complete_4lane=1` 作为功能基准，
每次只改一个机制并用 chain-off/clean 对照。需要明确的边界有：

- 最终候选只对 4 lanes、VLEN=1024 给出完整性能结论；2/8/16 lanes 尚未
  作为同等覆盖的最终 profile。
- exact global 当前覆盖 FP32、FP16→FP32 widening 和相应 masked/unmasked
  stream；EW64 unordered 仍走 legacy fallback。
- ordered reduction 保持顺序语义，不能直接套 unordered exact tree。
- exact state 的宽度、SLDU packet merger 和组合 ready 路径必须做综合后评估。
- `vsdot` 中仍有明显 WAR/false-hazard 和 sequencer block，下一阶段应在不
  放宽版本/顺序安全条件的前提下减少这些等待。

如果要重新开始某一条优化实验，最有区分度的 control 是关闭对应的单个
`reduction_*` 开关，而不是回退整个分支；如果要验证最终闭环，则用
`reduction_complete_4lane=1` 并只把 `reduction_complete_4lane_chain_bypass`
设为 `0` 做同 profile 对照。
