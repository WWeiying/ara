# Ara 规约优化实现教学文档

本文解释 `reduction-optimization` 分支在本仓库**优化前基线**之上做了什么、
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

`30c6971b` 是本轮优化开始前的本仓库快照，已包含此前相对官方 Ara 的
调度、operand 请求和工程环境修改；它不是官方仓库的原样提交。
这层来源关系和优化前实现请先阅读
[`reduction_baseline_ara_teaching.md`](reduction_baseline_ara_teaching.md)。
本文中的“最终候选”专指 `NrLanes=4` 的已验证 profile，不表示所有 lane 数和
所有 RVV 浮点格式都已经参数化完成。

**阅读路线：**第 1～6 节认清原始链路和四类优化；第 7～13 节是核心，
按代码入口、数据传输、精确数值和验证依次读；第 17 节用练习串起来。
第 2 节的开关表及第 14～16、18 节的测试记录、周期数据、命令和覆盖
边界可按需查阅，初读不必背下每个 define。遇到 `token`、`context`、
`epoch` 等术语时，先看下表中的具体例子，再读状态机。

## 0. 读文档前先统一术语

| 术语 | 在本文中的简单含义 |
|---|---|
| bypass（旁路） | 下一级已能接收时，数据直接过去，省掉一个排队周期；接收不了就由原队列保存。 |
| token（带身份的数据） | 一份部分和连同“属于哪条指令”的标记。例如 P 的和在 VMFPU 队列中，握手后转由 SLDU 保存。 |
| owner（当前持有者） | 当前必须保存 token、直到下一级接收它的模块或队列。 |
| context（指令上下文） | 一条规约自己的累加值、计数和状态；P 与 Q 可交错执行，但各自保存自己的数。 |
| stream（流式重叠） | P 做跨 lane 合并时，Q 提前做自己的 lane 内计算；P/Q 的值不相加。 |
| exact（精确中间和） | 对支持的 unordered 浮点求和，先用整数位权保存中间和，只在最后按浮点格式舍入。 |
| epoch（寄存器版本） | 每次写向量寄存器时推进的版本；`v8` 的旧值和新值虽同地址，版本不同。 |
| fallback（回退） | 条件不满足时仍走原有执行路径，例如 EW64 浮点求和不进当前 exact 路径。 |
| limb（分段传输的字） | 把 288-bit 精确整数从低位起切成最多五段，经 64-bit 通道逐段发送。 |
| credit（可消费名额） | 队列或接收方确认还能接收一次传输；没有名额时发送方必须保持原数据。 |
| rendezvous（会合） | SLDU 等四个 lane 都交出属于同一指令的 header，才开始合并。 |
| `fflags`（浮点异常标志） | 记录无效运算、溢出、不精确等情况；仅比较结果数值不足以检查浮点指令。 |

`SLDU` 是跨 lane 数据交换单元，`VRF` 是向量寄存器文件，`MASKU` 管理
mask 数据；`FPnew` 是所用的浮点运算实现。`ROI` 是性能统计选定的起止
区间。后文的“门禁”指代码中决定某条指令**能否走某条优化路径**的条件，
并非异常处理或新指令类别。

## 1. 优化前后先看同一条数据流

基线中，一条规约从 lane 内计算，经 SLDU 跨 lane 合并，再由 lane 0
写回。优化缩短可安全省去的等待，并为部分指令换用精确浮点求和算法。
这四层是**按作用分类**，不是说每条指令依次经过四层：

```text
基线
  VRF -> operand_queue -> ALU/FPU -> result_queue
                                  -> spill -> SLDU
                                  -> next lane / lane 0 fold -> VRF

优化后的几条主要路径
  整数：lane 内 VALU -> context/tree -> SLDU -> lane 0
  ordered FP：逐项 FPnew -> output/route/input 旁路 -> 下一项
  unordered FP min/max：lane 内 VMFPU context -> SLDU tree -> lane 0
  支持格式的 unordered FP sum：lane 内 exact 状态 -> packet
                                      -> SLDU 整数合并 -> 最终舍入

  跨指令版本化旁路可给后继指令提供 seed、source 或已写回的结果。
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

主要机制各有 Make 开关，但有些开关要求前置机制；按依赖关系改变其中一个
开关，就能做受控对照。`reduction_complete_4lane` 把当前已验证的开关
组合成一个可复现配置。

## 2. 构建开关和最终 profile

开关定义在 [`hardware/Makefile`](../Makefile) 的 reduction-acceleration
段。它们默认都是 `0`，所以普通构建仍保持基线行为。主要开关可按下表阅读：

| 层次 | Make 开关 | RTL define | 作用 | 依赖/范围 |
|---|---|---|---|---|
| 输出 | `reduction_output_bypass` | `ARA_RED_OUTPUT_BYPASS` | ordered VMFPU 结果直接满足 SLDU 的输出握手 | 基础旁路 |
| 路由 | `reduction_route_bypass` | `ARA_RED_ROUTE_BYPASS` | ordered SLDU one-hop 绕过固定 result-queue 返回 | 基础旁路 |
| mask | `reduction_mask_fastpath` | `ARA_RED_MASK_FASTPATH` | 在 output/route 旁路已启用时，也允许 masked ordered token 使用它们 | 基础旁路 |
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

`mask_fastpath` 让 masked ordered 指令也能走**已启用的** output 和 route 旁路。
原实现只对 `vm=1` 的无 mask 指令打开这些旁路；打开该开关后，VMFPU
与 SLDU 不再用 `vm=1` 限制旁路。lane 输入端已有 spill，可分别缓冲
返回的累计值和 mask 的等待，避免在两条 ready 路径间形成错误的直接依赖。
`mask_skip` 进一步让 masked-off 元素不启动 FPU，只完成必要握手。
Makefile 会在启用它时补开 output bypass 与 mask fastpath，因为 skip
要依赖这套旁路/握手协议。

这种优化不只是性能技巧。masked-off 的 sNaN、Inf 不能产生新的浮点异常，
所以 skip 路径必须完全跳过 FPU special-value sideband；它只能同步消费协议
所需的 token。现有回归覆盖了 active/masked-off 混合、全 mask-off 和不同
`VL` 尾部。

### 3.3 dense input bypass 和 tree input bypass

这两项都利用“能直接消费就直送，不能消费仍存回原 spill”的方式。它省掉
无背压时的固定等待，同时保留背压时的原有缓冲：

```text
输入 beat 到达
       │
       ├─ consumer ready: 直接进入运算
       └─ consumer stall: 存入原 spill register
                          下次 ready 时再从 spill 取出
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

当前实现只在 unordered 路径的 `SIMD_REDUCTION` 末尾使用这个融合。
ordered sum 走的是 `OSUM_REDUCTION` 状态，因此不经过此处；这不表示
ordered 的最后一次写回在理论上不能另作优化，但任何改动都须保留逐项
舍入后的 token 顺序。

### 3.5 tree stage 和 ordered interleave

`reduction_tree_stage_pipeline` 是 SLDU 侧的“本拍能接收就直送”：unordered
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
门禁。尤其 VMFPU 的 `red_stream_compatible()` 在打开 `masked_stream` 后仍
要求前台和后台 `vm=1`：masked FP 可以走加速的前台 context DAG，**不做**
投机后台 stream，因为 MASKU 与 FPU 返回的时序可能不同。整数 VALU 的门禁
另行定义，不能从 Make 开关名推断两者行为一样。

exact early-release stream 使用更严格的兼容函数：要求 opcode、完整 vtype、
VL、vstart、vm、rounding mode 和 `cvt_resize` 相同；ordered source alias
则使用自己的 request 字段比较。不要把 exact stream 的完整兼容性字段
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
设计容量而不是一条当前指令的 `VL`。最终舍入前，finite limb 保持在同一个
整数域；普通 seed 可以在 lane 0 进入该域，late-bound seed 则在 central
finalizer 前插入一次，不能重复加入。

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

`fixed_window` 会发送统一的密集窗口，适合作为实验对照；最终 sparse 协议
从最低 limb 开始，发到最高非符号扩展 limb 之后的一个保护 limb。未发送的
高位由符号位补足。它不是一个 bitmap；`active limb count` 记录需要发送的
连续低位 limb 数。late seed 的 producer ID/epoch 由 `pe_req` 和 SLDU 的
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
是否与上一次 ordered source 具有允许复用的完整语义字段组合。它不能只用
`vs2` 地址比较，必须同时检查 opcode、SEW、VL、vstart、mask、rounding、
`vs1`/`vs2`、scalar seed 和 use flags；版本化 hazard 仍由 sequencer 单独
负责。否则不同语义的 ordered 指令会错误复用 leader 的 memoized result/fflags。

## 7. 从源码重建最终 profile：先找门禁，再找状态

前面给出机制地图；下面按一个 RTL 阅读者真的会走的顺序，把每层的关键
条件、状态和握手摊开。阅读当前代码时先在
[`Makefile`](../Makefile) 查宏定义，再定位宏内的 `eligible` 或
`compatible` 函数，随后看状态机如何使用它。只有看见某个宏被编译进来，
并不能说明每条规约都走那条路。尤其 `exact`、`context stream`、
`ordered` 分别代表三类不同执行算法，不能把它们的收益相加。

| 输入类型 | 4-lane 最终配置中的主要路径 | 为什么 |
|---|---|---|
| `VREDSUM` 等整数，`VL>=8` | VALU tree/context stream（满足本地兼容条件时） | 可以并行做局部和跨 lane 合并；不牵涉 FP 舍入 |
| `VFREDUSUM` e32，`VL>=1` | exact local + packet + SLDU merge + finalizer | 该格式落在 288-bit exact 域内 |
| `VFREDUSUM` e16 | native FP16 exact（打开 `exact_fp16`） | 最终按 FP16 舍入 |
| `VFWREDUSUM`，目的域 e32 | FP16 源精确扩展后进入 FP32 exact 域 | `vtype.vsew` 门禁读的是目的/累加域 |
| `VFREDMIN/MAX` e16/e32 | VMFPU context DAG | 不使用 exact sum 的整数域 |
| `VFREDOSUM` / `VFWREDOSUM` | ordered token 路径与定向旁路 | 每一步仍按元素顺序舍入 |
| EW64 unordered FP | legacy fallback | 当前 exact 域未覆盖这个格式 |
| 不满足 4-lane 或其它门禁 | 相应基线路径 | 不能把特定 profile 的验证外推 |

这些是**路径选择**，不是 RVV 的语义分类。例如 RVV 允许 unordered FP
实现自选确定性树，当前 exact 算法选择了更强的“在支持格式上只最终舍入
一次”行为；[RVV 规范的 Reduction Operations](https://docs.riscv.org/reference/isa/extensions/vector/_attachments/riscv-v-spec.pdf)
规定的是架构可观察结果和有序/无序边界。源码里的 `vstart` 字段同样是
兼容性字段组合的一部分，不意味着归约已支持从非零 `vstart` 重新开始。

源码导航时可在每个模块上回答四个问题：**何时成为 owner、owner 存在
哪个寄存器、何时把 owner 交给下一级、背压时谁保存它**。把答案写在状态图
旁，比先看数值加法器更容易发现丢 token、重复消费和错误早释放。

## 8. 第一层旁路的逐拍推导

### 8.1 输入 spill 的“存储优先”规则

[`valu.sv`](../src/lane/valu.sv) 和 [`vmfpu.sv`](../src/lane/vmfpu.sv)
都保留原始 spill register，只在消费者**本拍确实接收**时允许透明路径。
以 VMFPU 的 `reduction_input_bypass_active` 为例，核心关系是：

```systemverilog
active = opcode_is_eligible && !sldu_mfpu_valid_spill;
operand = sldu_mfpu_valid_spill ? sldu_operand_spill : sldu_operand_i;
input_to_spill = sldu_mfpu_valid_i && !(active && sldu_mfpu_ready_d);
```

第一行的 `!valid_spill` 让已经存下的旧 token 优先；第二行使读到的数据
与这个优先级一致；第三行是**恰好一次**条件：透明路径消费成功时，绝不能
再写 spill。若 `ready_d=0`，第三行恢复为写入 spill，下一拍它就是稳定
的 owner。VALU 的 `tree_input_bypass` 用同样结构，但只对整数归约 opcode
申请。VMFPU 的 dense 输入只给未遮蔽的 ordered 操作申请；unordered tree
输入由另一个开关申请。三个条件看似相似，适用阶段并不相同。

逐拍检查可用这个小表。`V/R` 指上游 valid/消费者 ready；`S` 是 spill
已有 token：

| S | V/R | 本拍选择 | 下一拍 owner |
|---:|---|---|---|
| 1 | 任意 | 先消费 spill；新输入按 spill ready 决定是否入队 | 消费者或 spill |
| 0 | 1/1 | 透明直达消费者 | 消费者 |
| 0 | 1/0 | 输入写入 spill | spill |
| 0 | 0/任意 | 没有传输 | 无 |

这也是常见弹性流水线做法：缩短无背压时的空拍，同时让背压仍由既有
缓冲吸收。`ready` 若跨多个模块直接组合传播，会形成长时序路径，极端
情况下还可能有组合环；所以需要检查旁路选择和队列优先级，而非机械地
把所有寄存器删掉。[AMD AXI4-Stream 的 valid/ready 说明](https://docs.amd.com/r/en-US/ug897-vivado-sysgen-user/AXI4-Stream-Support-in-System-Generator)
可作为握手检查参考；Ara 这些端口是内部协议，不是 AXI 接口。

### 8.2 output、route、input 省掉的是不同的拍

可把 ordered `VFREDOSUM` 的单个元素画成：

```text
FPU response
  -- output --> VMFPU/SLDU 边界
  -- route  --> SLDU/目标 lane 边界
  -- input  --> 目标 VMFPU 的下一次 FPU request
```

`output_bypass` 只改变第一段；`route_bypass` 只改变第二段；
`dense_input_bypass` 作用于第三段。它们的条件包含不同 `ready/grant`，
不能因为某一个波形少了一拍就认为其他边界也可删。资料里的 `287→255→223`
是特定 32 元素 probe 上两段定向旁路的效果，不表示每个 VL 或 mask
排列都线性省 `2*VL` 拍。要复核自己的结果，记录从请求被接受到完成的
逐阶段等待时间，并对照 `vfpu_out_valid`、`mfpu_red_ready_i`、
`sldu_result_gnt_i` 与 `sldu_mfpu_ready_o`。

### 8.3 mask skip 是协议动作，不能只替换数值

[`vmfpu.sv`](../src/lane/vmfpu.sv) 的 ordered mask skip 有
`osum_mask_skip_active/fire` 两层：前者说明当前元素被遮蔽且 mask 可用，
后者还要求 downstream 可接收。只有 `fire` 才推进元素计数与 mask credit。
这类路径的正确性包含三件事：结果 accumulator 不变、被遮蔽的 sNaN
不进 FPU/不产生 `NV`、MASKU/operand token 被消费一次。单纯把 masked-off
数值改成 `+0.0`，可能改变有序 FP signed-zero 结果，也无法保证异常
sideband，因此不能代替显式 skip。

### 8.4 最后一个结果与下一条指令：两个不同的空拍

`terminal_fusion` 处理**本条 unordered FP 规约末尾**的空拍。在 VMFPU 的
`SIMD_REDUCTION` 中，当 `vfpu_out_valid` 到达且
`simd_red_cnt_q==simd_red_cnt_max_q`，这个 FPU response 已是最终结果；
代码同拍写 result queue 并转 `MFPU_WAIT`，省去下拍再观察队列 valid 的
等待。它不改变局部求和或跨 lane tree 的运算顺序。

`tree_stage_pipeline` 处理**SLDU 到 lane**的空拍。在 SLDU 的 `SLIDE_RUN`
中，只有 4 lanes、result queue 空、issue/commit 属于同一指令并满足
VFU 条件时，`tree_route_bypass_active` 才允许本拍把 tree 数据送给 lane。
目标 lane 没 grant 的数据仍由 result queue 持有。检查这个路径时同时看
`tree_route_valid` 和 `sldu_result_gnt_i`，不要只看 SLDU 内部是否算出数据。

`ordered_interleave` 处理**两条 ordered 指令之间**的空拍。VMFPU 在
`MFPU_WAIT` 中预取兼容后继的 seed 和首个 source beat；SLDU 的
`ordered_successor_prearm` 在前一条最终 token 路由/提交时准备下一条
`SLIDE_RUN_OSUM`。两处都要求同类操作和一致的 `VL/vtype/vstart`，
预取还限制为未遮蔽 EW32。预取数据属于后一条指令，前一条的最终 token
仍按原顺序退休。把三个优化分别定位到“本条尾部”“树返回”“两条之间”，
就不容易把它们误当成一个总开关。

## 9. Context flow：一个流水 FPU 如何服务多条规约

### 9.1 为什么需要 tag 和 pending 位

在基线中，FPU request 和 response 隔着流水延迟；发出某条规约的下一次
局部加法时，上一次结果可能尚未返回。如果允许另一条规约填空，返回值
就不能靠“当前指令”推断归属。当前 [`vmfpu.sv`](../src/lane/vmfpu.sv)
用 `red_context_data/valid/pending` 保存四个局部上下文槽，并把 `vfpu_tag_in`
编码成：

```text
bit 7 = 1             context-flow 标记，避免和基线 neutral tag 0/1/2 混淆
bits 5:4 = 00/01/10  accumulator 更新 / pair 合并 / root 合并
bits 1:0              目标 context 槽号
```

`RedContextTagMarker=8'h80`、`Accum=8'h00`、`Pair=8'h10`、
`Root=8'h20` 在源码中直接定义。发射时先把对应槽 `valid` 清掉并置
`pending`；返回时按 tag 把数值送回正确槽，重新置 `valid`。如果只在
发射时改 `data`，下一条操作就可能读到尚未完成的旧值；如果只用指令 ID
而不编码 DAG level，pair response 还可能被当成局部累加结果。

四个局部槽最终经两层固定的运算图（DAG，即每个结果只流向后续指定
节点）：

```text
slot0 ──┐
        ├─ pair0 ─┐
slot1 ──┘         │
                  ├─ root -> 跨 lane tree
slot2 ──┐         │
        ├─ pair1 ─┘
slot3 ──┘
```

当 `vl<=8`，RTL 的 `red_context_two_way_q` 只在两个槽之间轮转，直接
用两路 root，避免为了很短的向量等待四路填满。这里的 DAG 是**一条指令
内部**的局部合并。后面的 instruction stream 让另一条指令的独立 DAG
在前一条做跨 lane tree 时运行；两条指令的数据永不进入同一槽。

### 9.2 foreground、background 和 root FIFO

VMFPU 的四项 instruction queue 容纳一个架构 foreground 和至多三个预取
context；代码设置 `RedStreamRootDepth = VInsnQueueDepth - 1`，为已完成的
lane-local root 提供独立 FIFO。典型时间线是：

```text
时间       t0       t1       t2       t3
指令 P     local -> root -> SLDU tree ----> commit
指令 Q              local -> root -> wait ----> SLDU tree
```

Q 的 local root 可以排队，但不能越过 P 的跨 lane/提交边界。代码中
`red_stream_bg_active`、`red_stream_bg_complete` 与
`red_stream_foreground_advanced` 分别描述后台是否执行、是否形成 root、
架构前台是否已经推进。读状态机时要分清 `issue_pnt`（开始运算）与
`commit_pnt`（可以按序退休）；同一个 FIFO 条目被创建和被消费是两个
事件。可以理解为“Q 先算自己的局部结果，但要等 P 走完跨 lane 合并
才能提交”。

### 9.3 兼容门禁要按模块分别读

整数 [`valu.sv`](../src/lane/valu.sv) 的 `red_stream_eligible()` 要求
4 lanes、整数规约和 `VL>=8`；未开 masked stream 时要求 `vm=1`。
默认 `red_stream_compatible()` 还比较 opcode、SEW、vm，打开 hetero
define 后有意放宽这些相同性检查。浮点 `vmfpu.sv` 的 context 门禁只收
特定 e16/e32 unordered opcode；如果 exact sum 已接管，则把符合 exact
资格的指令排除。浮点的普通 stream 还涉及 rounding mode 和 MASKU
时序；当前即使开启 masked-stream，投机后台也要求两条 `vm=1`。

exact 的 `red_exact_stream_compatible()` 更严格，直接比较完整 `vtype`、
`VL`、`vstart`、`vm`、`fp_rm`、`cvt_resize`、opcode。原因不是数值
需要相同：不同向量寄存器当然可以连续处理；原因是四个 lane 要在不知道
彼此队列背压细节的条件下，对 packet 边界作出**相同的推进决定**。
如果其中一个 lane 把 Q 当作后继、另一个仍把 P 当作当前，header rendezvous
无法修复数据归属错位。把 opcode、`VL`、舍入模式等共同决定执行节奏的
字段组成一份兼容性检查，是多通道流水中常用的防错方式。

`slack_schedule` 只控制**何时预取后台指令**，不改变算术。VALU 估计下一条
需要多少 local word、当前 tree/SIMD 还会空出多少周期；VMFPU 用类似的
local FPU 操作数和剩余空槽估计。若已经预取了 context，只有预测可容纳
且 `red_stream_slack_score_q` 达到阈值时才继续预取；否则推迟并计入
`red_stream_slack_defer_cycles_q`。这是防止后台占满队列、反而阻塞前台的
资源调度条件；读数值路径时可以暂时略过它。

### 9.4 exact early release 是资源所有权转移

在 `EXACT_GLOBAL_TX`，最后一个 limb 与 SLDU 完成握手的那一拍，所有 finite
局部状态已由 SLDU 输入 spill/merger 持有。代码把
`exact_sum_out_ready=1` 并置 `exact_stream_early_release`；若队列下一条
满足严格兼容，就推进 `issue_pnt` 并重置 local accumulator 的输入计数。
前一条仍占据 processing/commit owner，直到 SLDU final token 返回。
因此它复用的是**一套 local accumulator 在两个不同时间段的所有权**，
不是同时让两条指令改写同一个 288-bit 状态。可在波形中要求：

```text
last_limb_fire(P) <= first_accumulate(Q)
completion_fire(P) <= publish_header(Q)
```

若去掉第一条约束，会混合两条 finite sum；若去掉第二条约束，会让
SLDU 按错误顺序看到 packet。两条约束也解释了 early release 何时真的
能改善吞吐：Q 的 local body 应足够长，能覆盖 P 的中央合并和 finalizer
等待；孤立单条指令没有这种重叠收益。

## 10. Exact sum 的数值推导：从 IEEE 位型到一次舍入

### 10.1 binary32 为什么可以变成整数加法

有限 binary32 正规数的值是
`(-1)^sign × (2^23 + fraction) × 2^(E-150)`；这里 `E` 是 1 到 254
的 biased exponent。非正规数是
`(-1)^sign × fraction × 2^-149`。因此把所有输入乘 `2^149` 后，
两者都变成整数：正规数贡献
`(2^23+fraction) << (E-1)`，非正规数贡献 `fraction`。
[`fp32_exact_reduction_accum.sv`](../src/lane/fp32_exact_reduction_accum.sv)
的 `fp32_to_fixed()` 正是在构造这个二补码整数。binary16 最小单位
`2^-24`，映射到同一域就是左移 125 位，源码的 `fp16_to_fixed()` 与
`fp16_segment_index()` 可核对这个关系。

例如三个数 `2^100, 1, -2^100`，若按某种普通 FP32 tree 先做
`2^100+1`，小的 1 会被舍掉，最终可能得到 0；exact 域先做整数加法，
得到整数 `2^149`，finalizer 一次舍入为 `1.0`。这说明改动可能改变
`VFREDUSUM` 的末位结果，但 RVV 对 unordered reduction 允许确定性树的
不同中间精度/结合方式；**不能**拿此算法替换 `VFREDOSUM`，后者规定
逐元素、逐步舍入。这里的例子是说明算法，不代替对 NaN、signed zero、
异常标志的验证。

### 10.2 288 bit 与 16×49 bit 各解决什么问题

`AccWidth=288` 的完整二补码域覆盖 binary32 从极小非正规到最大正规数
的位权，并给支持的输入数留有进位空间。若每个输入 beat 都直接更新
288-bit feedback，关键路径会经过长加法器。segmented 模式依据 exponent
把源送到 16 个窗口之一：

```text
binary32 segment = ((E == 0) ? 0 : E-1) >> 4
local shift       = ((E == 0) ? 0 : E-1) & 15
segment update    = old_bin + signed(significand << local_shift)
```

单个正常数的 significand 有 24 位，窗口内最多移 15 位；最多 257 项
（256 个向量元素加 seed）还需要 9 位 population carry，再留 1 个有符号
位，总计 `24+15+9+1=49` 位。这里的 256 是此模块的设计容量，不是
当前 e32/m1 指令的实际 `VLMAX`。源码还保留非 segmented 的四个
288-bit bank 形式，便于比较算法与反馈路径；最终 profile 选 16 段。

完成所有输入后，状态机按
`IDLE→ACCUMULATE→MERGE_PAIRS→MERGE_ROOT→ROUND_RESULT→HOLD_RESULT`
合并这些精确 partial sum，再由
[`fp32_exact_reduction_finalize.sv`](../src/lane/fp32_exact_reduction_finalize.sv)
做唯一的格式化舍入。第一拍可以同时接受新任务和首个 beat，所以看
`IDLE` 时不能误以为它纯粹是启动空拍。`HOLD_RESULT` 则一直保持稳定
输出，直到下游 `out_ready_i` 才释放 owner。

### 10.3 数值位和语义位为什么必须分开

NaN、无穷和有符号零没有适合直接相加的固定整数值。每个 lane 还记录
`special={nan,invalid,pos_inf,neg_inf}`、`source_seen`、
`finite_nonzero_seen`、`pos_zero_seen`、`neg_zero_seen`。这几个位不是
冗余的：

| 情形 | 单看有限整数和会丢掉什么 |
|---|---|
| `+0.0 + -0.0` | 零的符号及 rounding-mode 相关规则 |
| `+Inf + -Inf` | 必须识别 invalid，而不是把两者抵消 |
| 被 mask 掉的 sNaN | 应完全不参与，不能凭原始 source 位型设置 `NV` |
| `VL>0` 且没有 active source | 应按规范的空源规则处理 seed，不能把“整数和=0”误判成真的零和 |
| late seed | seed 尚未在 lane 插入；finalizer 必须只插入一次 |

特别是 `source_seen` 表示**真实 active source 被处理过**，不是
`VL>0` 或“收到了 neutral beat”。RVV 规定 `VL=0` 不执行规约，
`VL>0` 而所有 source inactive 的行为另有 seed 规则；两者不可合并。
更多边界见[RVV 规范](https://docs.riscv.org/reference/isa/extensions/vector/_attachments/riscv-v-spec.pdf)
及基线文档第 12 节。当前 exact 门禁要求 `vl>=1`，而内部队列仍会生成
neutral beat；验证时要分别检查门禁、active metadata 和最终 VRF 写回。

## 11. Exact packet：64-bit 通道承载 288-bit 结果

### 11.1 header 每一位的实际含义

[`vmfpu.sv`](../src/lane/vmfpu.sv) 的 `exact_packet_word` 在 beat 0
发 header，其后发 little-endian limbs。按**当前 RTL**解析 header：

| 位 | 字段 | 用途 |
|---|---|---|
| `[63:32]` | 32-bit seed 位型 | 普通路径 lane 0 携带；late seed 时不在 lane 预插入 |
| `[31:28]` | `4'he` magic | 防止把普通 SLDU word 当作 exact header |
| `[27:26]` | lane ID | 四个输入必须各占正确 lane |
| `[25:22]` | `{nan,invalid,pos_inf,neg_inf}` | special 合并 |
| `[21:18]` | source seen、finite nonzero、positive zero、negative zero | finalizer 语义 |
| `[17]` | seed valid | 普通路径仅 lane 0 应置 1 |
| `[16:14]` | rounding mode | 四 lane 必须一致 |
| `[13:11]` | local limb count `2..5` | 本 lane 何时停止发 limb |
| `[10]` | native FP16 结果格式 | 选择最终编码 |
| `[9]` | masked marker | 描述 `!vm`，不是该 lane 的 active 个数 |
| `[8]` | 完整二补码值的符号 | 省略高 limb 时用于 sign extension |
| `[7:0]` | instruction ID | 防止不同规约 packet 互串 |

这个 header 是内部协议版本，不能拿它当架构数据或对外 ABI。`magic`
只做类型区分，不足以识别 owner；SLDU 的 rendezvous 同时检查 magic、
lane ID 和当前 instruction ID。四个 header 都匹配后才确认它们，提前
到达的匹配 header 要保留；旧的、不匹配的 dummy token 可被丢弃。
SLDU 还断言四路 rounding mode、格式一致，并检查 seed 的唯一 owner。

### 11.2 sparse active window 手算一次

完整 exact 状态是 288 位，若固定用 64-bit 总线发出，需五个 limb
（前四个 64 位，第五个低 32 位加符号扩展）。当前 `exact_local_limb_count`
寻找最高的非符号扩展 limb，再多发一个 guard limb，范围 `2..5`。
比如 finite 值 `2^-149` 在固定整数域是 bit 0 置 1：只有 limb 1 的
最低位非零，lane 仍发 `header + limb1 + limb2`；limb2 是 guard。
值 `1.0` 对应 bit 149，在 limb3 中，因此至少还要发 limb4 作 guard。
不要把 header 中的 `2` 理解成两个 active 元素；它是两个**64-bit limbs**。

每个 lane 可以广告不同长度。SLDU 从四个 header 取最大 count；对还需
发送的 lane，必须等真实 `valid`；对已经结束的 lane，根据它广告的符号
生成全 0 或全 1 的隐式高 limb，并且不等待额外物理 beat。每轮执行：

```systemverilog
chunk_sum = lane0_limb + lane1_limb + lane2_limb + lane3_limb
          + carry_from_lower_limb;          // 66-bit 暂存
root_limb = chunk_sum[63:0];
carry_to_next_limb = chunk_sum[65:64];
```

这是四个二补码整数的分 limb 加法，不是四个 FP32 运算；没有中间浮点
舍入。最后一个 limb 把符号扩展填入未传的高位，形成 288-bit root，
送中央 finalizer。`fixed_window` 开关强制每 lane 发五个 limb，是衡量
sparse 协议控制复杂度与带宽收益的对照，不属于最终 profile。

源码里还能看见 `SLIDE_SEND_EXACT_WINDOW` 和 `8'he8` 控制 token，
这是保留的 global-window 同步路径；当前 sparse merge 可以直接用每 lane
header 长度和隐式符号扩展推进，不需要把它误当成每个 packet 都必经的
反馈轮次。读这块时以状态转移、define 和 `exact_packet_beat_q` 为准，
不要只凭某个 case 分支存在就画进最终时序。

### 11.3 结束 token 也有 owner

SLDU 合并最后一个 limb 后进入 finalizer/等待状态，再把完成 token
广播给四个 lane；只有 lane 0 分配架构结果。其余 lane 也必须消耗完成
token 来释放对应 local/exact owner，否则下一条 packet 可能在一个 lane
上被旧状态阻塞。这里可建立两个守恒式：

```text
每 lane：1 个匹配 header + 所广告 limb 数 = 该 packet 被网络消费的 beat 数
全局：1 次四路 header rendezvous -> 1 次 finalizer -> 1 次架构写回 owner
```

遇到 sporadic hang 时，应先看四路 `header_match`、各路 `limb_available`
和 `exact_late_seed_ready`。数值计算本身很短，真正停住的常是一个
lane 的 operand queue/MASKU credit 尚未送到，或 late seed 仍等 producer。

## 12. 跨指令链：版本、地址和所需字节组成安全条件

### 12.1 一个例子区分“物理地址”和“值的身份”

考虑 `P` 写 `v8[0]`，`Q` 用 `v8[0]` 作 seed，随后 `R` 又重写 `v8`。
若仅按 `v8` 地址匹配，`Q` 可能拿到 R 的值；若仅按 instruction ID
匹配，ID 环形复用后旧 cache 又可能误命中。主
[`ara_sequencer.sv`](../src/ara_sequencer.sv) 为 32 个向量寄存器分别
维护 8-bit `vreg_version`，并把 `seed_version/vd_version/vs1_version/
vs2_version` 随 request 发往 lane。地址说明**在哪儿**，epoch 说明
**哪一次定义**，producer ID 说明当前在途的 owner。正确的旁路用与自身
场景相应的组合键验证三者，而不是简单做“同一个 v 寄存器就能转发”。

版本号有限宽度，不能无限保存旁路值。因此 lane 内的两项 reduction
result cache 用 `age` 限定寿命，在可能的 epoch 回绕前失效；SLDU 的
late-seed table 在 ID 重新分配给 producer 时使旧槽失效。工程上这种
**有界版本 + 有界保存期**比盲目加宽版本号更容易给出硬件成本和安全证明。

### 12.2 late seed 的 hazard 放宽具体到哪些位

`exact_chain_eligible()` 先验证 producer/consumer 都是可用 exact 形态。
检测到 `consumer.vs1` 是在途 exact producer 的目的寄存器，且
`writer_vd` 和 `writer_version` 与 consumer 期待的一致，才建立
`late_seed_candidate`。代码无条件清除针对**这个 producer**的
`hazard_vs1`；若是就地 accumulator 形式 `vd==vs1`，才进一步清除可证明
为假的 `hazard_vd` 和相关旧 seed WAR。真正 `vs2` source 的 RAW、遮蔽时
对 `v0` 的 RAW，以及改写不同目的寄存器时有歧义的 WAR 继续保留。

结果是 Q 可以先读自己的 body，把精确有限和算完；P 在 SLDU finalizer
产出**已舍入**结果后，late-seed table 用 producer ID、目的寄存器和
seed epoch 确认身份。Q 的 header rendezvous 会等
`exact_late_seed_ready`，随后只在 central finalizer 插入这份 seed。
这并非把 P 的未舍入 288-bit 中间状态直接并入 Q：P 的架构边界已经完成
一次舍入，Q 必须以这个 rounded scalar 为 seed。这个区别是链式 FP
规约保持语义的关键。

可以写下检查式：

```text
Q.expected_seed_epoch == P.produced_vd_epoch
Q.seed_producer_id    == P.id
Q.vs1                == P.vd
Q.seed_insert_count   == 1
```

它们都成立时才允许跳过 VRF seed 读取。若 source 与 destination 别名、
mask 寄存器也复用相同地址，要逐个看 hazard 位是否仍表达真实依赖。

### 12.3 VFMUL forwarding 为什么要等 grant 后的 beat

`VFMUL→VFREDUSUM` 需要的是 VFMUL 已按其架构 rounding mode 舍入的
source word。`operand_requester.sv` 取 MFPU result queue **获得 VRF grant**
后的 `wdata`，再注册一拍，使 `forwarded_operand_valid/data` 与正常
VRF read response 对齐。匹配键包含 producer hazard、source epoch、
完整 word address 和所需 byte enable。由于各 VRF bank 的 grant 可
交错，MFPU result 地址可能不是线性递增：当前 beat 地址不等于 request
地址时，要保持 request 等待，不能把 VRF 中尚未写好的旧 word 读出来。

这里借鉴处理器旁路网络的通行思路：**生产者结果真正定型后、消费者
需要的字节全部可用时**才交付。它还要求接口时序和正常读取一致：旁路
数据不能在 operand queue 尚无 credit 时强塞，也不能把一次 grant
当成两次 response。看波形时并排放 `mfpu_result_gnt_o`、
`recent_mfpu_result_addr_q`、requester `addr`、`forwarded_operand_valid_o`
和 queue `ready`，比仅比较最后数值更容易发现错拍。

### 12.4 result cache 是已退休结果的短暂桥

同一 lane 的两项 cache 保存 `valid/version/full_addr/wdata/be/age`，
并保留结果来自 ALU 还是 MFPU。一次完整命中要求**所需的每一个字节**都
在 `be` 内。举例：e32 规约只写 `vd[31:0]`，e32 `VFMV.F.S` 所需低四
字节可命中；要求八字节的整 word 读不能用同一 entry 冒充。
未命中则走正常 VRF 请求。cache 被消费后会失效；若同拍多个 requester
命中，均观察旧的寄存 payload；同拍新 ALU/MFPU fill 的优先级在时序逻辑
中明确处理，两个 bank 同时完成也可放进不同 slot。

这个 cache 不等同于 SLDU late-seed table：前者面对**已经 grant/退休**
但下一次 VRF 读取尚未衔接的间隙，后者面对**还在途**的 P→Q seed
依赖。缓存类型不同，匹配键和失效时机自然也不同。教学调试时可构造
`P: VREDSUM -> Q: VMV.X.S` 与 `P: VFREDUSUM -> Q: VFREDUSUM` 两条
链，看两者分别命中哪个结构。

### 12.5 ordered alias 仍要按原序逐步舍入

ordered source fusion 记录上一条 source 的别名与语义字段组合；比较范围
包括 opcode、SEW、VL、vstart、vm、rounding、`vs1/vs2` 和 seed/use
flags。它试图复用的是可证明相同的 source 工作，不是开放 ordered
reduction 的重结合。对 `VFREDOSUM`，即使数学上 `a+b+c` 可交换，
IEEE 浮点每一步 rounding、sNaN/Inf 异常与 signed zero 仍使交换顺序
不可随意改变。源码里凡是 ordered 加速，都应能指出“下一项仍拿到上一项
已舍入 token”的路径；若找不到，先不要把它归为安全优化。

## 13. 怎样验证：结果正确，也要确保每份数据只传一次

### 13.1 先验证语义，再验证吞吐

单独的速度数字无法证明结果正确。对整数规约，参考模型应覆盖
SEW 截断、带符号/无符号扩展、mask 和 `vd[0]` 写使能。对 ordered FP，
参考模型必须按 RVV 元素顺序逐项调用目标格式加法和舍入；对 exact
unordered，可使用任意精度整数域重新求和，单次按目标格式舍入，并单独
检查 NaN/Inf/signed zero/`fflags`。随机数值对 cancellation、subnormal、
溢出、tie 点的覆盖不够，应加定向边界向量：

```text
2^100, 1, -2^100       检查 exact cancellation
最小 subnormal 与其负数  检查固定域低位和零号
+Inf 与 -Inf            检查 NV
masked-off sNaN         检查完全不触发 NV
全 masked-off, VL>0     检查 seed 的 bitwise-copy 路径
VL=0, vd!=vs1           检查目的寄存器不被改写
```

RVV 规范把 `VL=0`、非零 `vstart` 与普通 masked-off 情况明确区分；尤其
非零 `vstart` 对归约是非法，不能以结构中有 `vstart` 字段替代架构测试。
基线文档第 17 节也列出了这些未被当前文档“证明通过”的检查项目。

### 13.2 把旁路和 packet 的不变量写成断言

当前 RTL 已有多处 `assert property` 和仿真断言。继续扩展时，优先围绕
所有权写检查，而不是写“输出等于某公式”的实现镜像：

1. 输入 `valid && !ready` 时，payload 和 owner tag 在下一拍保持；
2. 透明输入 `fire` 时，同一 token 不再写 spill；spill 已有 token 时优先
   处理它；
3. 每个 context tag response 只能清除对应槽的 `pending`，不能更新
   另一槽；
4. 每个 exact header 的 lane/ID/format/rm 匹配后才被四路合并；每 lane
   实际 limb 消费数等于它广告的数；
5. `last_limb_fire(P)` 之后才 early release local accumulator；P 的完成
   token 之前不能发布 Q header；
6. late seed 只在版本和 producer 都匹配时绑定一次；cache forwarding 的
   `be` 必须覆盖 requester 所需字节；
7. 只有 lane 0 最终写 `vd[0]`，其他 lane 的完成仅释放内部 owner。

这些检查能把数值错误和数据传输错误分开：若测试超时，先查
`valid/ready` 与 packet 计数；若所有 token 走完但结果位型不同，再查
数值转换和 finalizer。验证通常也会把“结果是否正确”和“每份数据是否
恰好传递一次”分别检查。

## 14. 已有验证记录

上一节讲如何检查；本节只记录当前分支已经做过什么。具体测试命令、
输入和完整输出见[实验记录](reduction_acceleration_4lane.md)。

当前资料中的验证分为三类：

1. **RTL 编译**：最终 profile 已完成 VCS elaboration，记录为 0 error。
2. **功能回归**：整数、unordered/ordered FP、min/max、mask、widening 和
   EW64 fallback 继续 PASS；官方 `vfredusum/vfredosum` 集合为 16/17，唯一
   失败与 clean baseline 相同，是 VLEN=1024 时测试硬编码 `VL=64` 超过
   e32/m1 的实际 VLMAX=32。
3. **定向数据流**：late seed、交错/扇出、VFMUL forwarding、整数/FP result
   cache 和 `VL=1` store 都做位级检查；当前链旁路 probe 的 14 个结果全 PASS，
   analyzer 28/28 指标覆盖，`--require-ready` 为 high confidence。

## 15. 当前实测结果和正确的解读方式

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

“单条指令延迟”与“多条指令的总周期”不是同一个量。前者从目标指令开始
执行算到它完成，后者包含其它指令和可能的执行重叠。因此单条指令花
24 cycles，不代表 16 条连续指令一定花 `16×24` cycles。

这些行来自不同阶段的开关对照，不能把整张表看成一条单调累加曲线：例如
287→191 只隔离 ordered bypass/input cut，187→170 比较 exact packet 协议，
399→260 还包含 exact stream early release，而 1398→1308 是最终 4-lane
profile 的 chain-bypass 对照。每个百分比只在同一行的对照/优化配置之间成立。

`vsdot_asm` 的收益同时涉及 late seed、乘法结果转发和 result cache，
不能归因于单个事件。逐项命中和等待计数保留在实验记录中，学习 RTL
主线时不需要记住这些 probe 专用数字。

公平比较两种配置，应固定 lane 数、`VLEN`、测试二进制、mask/SEW/VL、
仿真器和 ROI 起止点，只改变要研究的开关。除了 cycles，还要看
`pass/fail`、operand 等待、SLDU header 等待、FPU busy 和 cache 命中；
否则可能把前序指令排队的变化误认成当前数据通路的收益。

这些周期结果尚不能推出论文级 PPA 结论。已有
[`fp32_exact_reduction_synth_wrappers.sv`](../tb/fp32_exact_reduction_synth_wrappers.sv)
结构面积预算，但整机还需要把新增 SLDU limb merger、ready 组合路径、Fmax、
面积和功耗一起综合评估；报告执行时间时应使用 `cycles × clock_period`。

## 16. 复现实验和继续开发的入口

### 16.1 最小编译/仿真流程

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

### 16.2 建议的阅读顺序

如果按章节读过第 7～12 节，重新打开源码时可按“VALU/VMFPU 输入 →
SLDU → exact accumulator/finalizer → sequencer/operand requester”的顺序
定位。下表列出每一步最值得搜索的符号。

### 16.3 代码导航表

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

## 17. 自学任务：沿一条指令把关键代码读透

下面四个练习都可以只用当前源码、基线快照和现有 probe 完成；记录波形
时把**条件、状态、owner、握手**写在同一张表。预期答案是检查方向，
不是对当前未跑过的配置作额外通过声明。

1. **整数 `VL=10, SEW=32`**：先按基线文档第 13 节算出四 lane 元素数，
   在 `valu.sv` 找 `red_stream_eligible`、`tree_input_bypass_active`、
   `sldu_transactions_cnt` 和最后的 `be(1,SEW)`。关掉 tree input bypass
   再看 SLDU→VALU 的返回多了哪一拍，确认最终 word 仍只写低 4 字节。
2. **ordered e32 `VL=2`，第二项 masked-off sNaN**：在 `vmfpu.sv` 跟
   `osum_issue_cnt`、`osum_mask_skip_active/fire`、`vfpu_in_valid`，在
   `sldu.sv` 跟 route grant。预期被遮蔽项不启动 FPU，不引入 `NV`；
   当前已舍入 token 仍以原次序交给下一项。
3. **exact e32 两条相依链**：P 的 `vd` 给 Q 的 `vs1`。先在
   `ara_sequencer.sv` 检查 `writer_version==seed_version` 才清 seed RAW；
   再在 VMFPU 观察 Q 是否先累加 body；最后在 SLDU 等 P final result
   被 late-seed table 命中并插入 Q。故意让另一条指令改写该寄存器，
   应不再错误绑定旧 seed。
4. **sparse packet**：给四个 lane 构造不同大小和正负号的 finite partial
   sum，分别手算 header count `2/3/4/5`、每轮真实/隐式 limb 与 carry。
   在 `SLIDE_RUN_EXACT` 看四路 `header_match` 和 `limb_available`，验证
   root 与一个软件 288-bit 二补码和一致，再比较最终 FP bit/fflags。

读完每项后，回到第 16.3 节导航表和
[`reduction_acceleration_4lane.md`](reduction_acceleration_4lane.md) 查对应
实验的 control、测量边界与已知局限。这样既能理解“代码如何实现”，也
能区分“已有实验观察”和“下一步需要证明的性质”。

## 18. 附录：目前验证覆盖的边界

当前最稳妥的继续方式是保留 `reduction_complete_4lane=1` 作为功能基准，
每次只改一个机制并用 chain-off/clean 对照。需要明确的边界有：

- 最终候选只对 4 lanes、VLEN=1024 给出完整性能结论；2/8/16 lanes 尚未
  作为同等覆盖的最终 profile。
- exact global 当前覆盖 FP32、native FP16、FP16→FP32 widening 和相应 masked/unmasked
  stream；EW64 unordered 仍走 legacy fallback。
- ordered reduction 保持顺序语义，不能直接套 unordered exact tree。
- exact state 的宽度、SLDU packet merger 和组合 ready 路径必须做综合后评估。
- `vsdot` 中仍有 WAR/false-hazard 和 sequencer 等待；具体瓶颈计数和下一步
  实验设想见实验记录，不能把它们当成当前 RTL 已解决的机制。

如果要重新开始某一条优化实验，最有区分度的 control 是关闭对应的单个
`reduction_*` 开关，而不是回退整个分支；如果要验证最终闭环，则用
`reduction_complete_4lane=1` 并只把 `reduction_complete_4lane_chain_bypass`
设为 `0` 做同 profile 对照。
