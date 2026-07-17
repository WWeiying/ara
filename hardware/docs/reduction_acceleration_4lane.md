# 4-lane 规约加速原型：ordered 递归环与 tree reduction 数据通路压缩

本文记录 4-lane 规约优化的设计、消融开关、正确性边界和实测结果。方案同时覆盖 ordered token 递归环压缩、mask/token 解耦、masked-off 浮点运算消除，以及整数/无序浮点 tree reduction 的跨模块输入直通和无序浮点末级完成融合。当前只对 `NR_LANES=4`、`VLEN=1024` 给出性能结论，没有进行多 lane 扩展性实验。

## 1. 瓶颈与优化目标

`vfredosum` 必须严格保持元素顺序，因此它不能像 unordered reduction 那样构造并行规约树。当前 Ara 实现让一个累加 token 按元素、按 lane 循环，每个新元素都依赖前一个浮点结果。

原始 ordered 递归环可简化为：

```text
VMFPU/FPU
   │
   ▼
VMFPU result queue       固定 1 cycle/element
   │
   ▼
SLDU result queue        固定 1 cycle/element
   │
   ▼
next-lane VMFPU input spill
   │
   └──────────────► 下一次浮点累加
```

队列原本用于切断组合路径、吸收背压，是正确且保守的通用设计；但 ordered reduction 只有一个在途递归 token，中间两次完整入队/出队会直接增加 recurrence interval。VL 越长，这部分开销越接近 `2 × VL`，而不是一次性的启动延迟。

本原型保留 VMFPU 输入 spill，把它重新解释为隔离 mask-ready 与跨 lane token-ready 的弹性 credit；在此基础上压缩中间两段队列，并让 masked-off 元素直接转发累加 token。各机制可独立消融。

## 2. 机制一：VMFPU ordered output bypass

开关：`reduction_output_bypass=1`

宏：`ARA_RED_OUTPUT_BYPASS`

实现位置：`hardware/src/lane/vmfpu.sv`

在 `OSUM_REDUCTION` 状态时，基础开关只作用于无 mask 指令；启用 mask fastpath 后作用于全部 ordered reduction：

- `vfpu_processed_result` 直接成为送往 SLDU 的规约数据；
- `vfpu_out_valid` 直接成为 `mfpu_red_valid_o`；
- `mfpu_red_ready_i` 直接控制 fpnew 输出端是否退休；
- `to_process_cnt` 只在 `valid && ready` 的端到端握手发生时递减；
- 非 lane 0 只在最后一个输出确实被 SLDU 接受后进入 `MFPU_WAIT`。

因此，下游背压时 fpnew 保持 valid 和结果数据，计数器、状态机和 token 所有权都不前进，不会发生“结果只看见一次却没有被接收”的丢 token 问题。

最终结果仍回到 lane 0，并通过原有正式 result queue 写回 VRF。旁路只作用于中间递归 token，不改变体系结构提交点。

mask fastpath 没有把 mask-ready 组合接入 fpnew/SLDU ready 链。返回 token 先进入原有 VMFPU input spill，mask word 也已由 lane 内独立 spill 缓冲，因此二者可以分别等待；只有 VMFPU 同时观察到 token、源数据和 mask valid 才消费元素。

## 3. 机制二：SLDU ordered one-hop route

开关：`reduction_route_bypass=1`

宏：`ARA_RED_ROUTE_BYPASS`

实现位置：`hardware/src/sldu/sldu.sv`

在 `SLIDE_RUN_OSUM` 时，基础开关只优化 `vm=1`；启用 mask fastpath 后，masked token 也不再先写入通用 result queue，而是组合路由到下一个 owner lane：

```text
source VMFPU valid
        │
        ▼
SLDU one-hop route ──► target VMFPU valid
        ▲                    │
        └──── source ready ◄─┘ target ready
```

核心约束如下：

- 普通 token 的 target 是 `(source_lane + 1) mod NrLanes`；
- `issue_cnt == 1` 时强制把最终 token 送回 lane 0；
- source ready 只等于目标 lane 的 grant；
- `issue_cnt` 只在目标 grant 成立时递减；
- valid 被阻塞时，source VMFPU 保持数据，路由和计数器均保持不变。

这使传输仍具有端到端原子性，只去掉中间存储周期。未启用 mask fastpath 时，masked ordered 自动回退到原 SLDU result queue。

## 4. 机制三：mask-decoupled fast loop

开关：`reduction_mask_fastpath=1`

宏：`ARA_RED_MASK_FASTPATH`

该机制必须与 output 或 route bypass 配合。它利用两个已经存在的弹性资源：

1. lane 内 mask spill 保存当前 mask word；
2. VMFPU input spill 保存跨 lane 返回的 accumulator token。

token-ready 只终止在 VMFPU input spill，mask-ready 只终止在 mask spill，两者之间没有组合环。VMFPU 在 `OSUM_REDUCTION` 内做 join：源向量、mask 和 accumulator 三者同时 valid 后才发射下一步。由此，masked ordered 可以安全使用 output/route 快速环，而无需增加专用 mask FIFO。

与简单地删除 input spill 不同，本机制保留一个 token credit。开发中的反例表明，这个 credit 是连续 ordered 和 masked e16 能够保持进度性的必要边界。

## 5. 机制四：masked-off accumulator token relay

开关：`reduction_mask_skip=1`

宏：`ARA_RED_MASK_SKIP`

RVV 语义规定 masked-off 元素不参加规约，也不应产生该元素的浮点异常。原实现仍把它替换成 neutral value 并执行一次 FPU 累加，因此执行时间和能量基本不随 mask 密度下降。

token relay 检查 `osum_issue_cnt` 对应的真实 mask bit。元素 inactive 时：

- 不拉高 `vfpu_in_valid`；
- 将当前 accumulator（`operand_b`）原样作为 VMFPU 输出；
- 只有 `mfpu_red_valid_o && mfpu_red_ready_i` 成立时，才同时消费输入 token、当前元素和 mask；
- 同一握手中递减 `issue_cnt` 与 `to_process_cnt`；
- 一个 64-bit operand 内仍按原 shuffled element 顺序推进 `osum_issue_cnt`；
- mask word 的最后一个元素完成后才拉高 `mask_ready_o`。

因此 stall 时 token、源操作数、mask 和所有计数器保持不变；fire 时它们原子前进。active 元素继续严格按原顺序经过 FPU，inactive 元素只是不进入运算序列，符合 ordered reduction 语义。

`reduction_mask_skip=1` 会自动启用 output bypass 和 mask fastpath，防止生成握手前提不完整的配置；route bypass 仍可独立消融。

## 6. 机制五：capture-on-stall dense input cut

开关：`reduction_dense_input_bypass=1`

宏：`ARA_RED_DENSE_INPUT_BYPASS`

无 mask ordered reduction 不依赖 mask-ready，因此可以进一步压缩 SLDU→VMFPU 的 input spill 周期。但不能简单在 transparent/stored 两条独立路径间切换，否则指令边界会出现 token 所有权歧义。

最终机制保留原始双项 spill，并把它改造成 capture-on-stall fall-through cut：

- spill 内已有 token 时，stored token 始终优先；
- 仅当当前指令是 unmasked ordered 且 spill 为空时，允许 direct valid/data；
- direct token 只有在 VMFPU 同周期 ready 时才真正旁路；
- VMFPU 不 ready 时，token 自动捕获进原双项 spill；
- masked、unordered 和边界阶段的 valid/ready 行为与原 spill 完全相同。

因此任意 token 只有两种互斥所有权：已经由 VMFPU 当周期消费，或已经被 spill 接收。模式切换不需要 flush，也不会把 stored token 隐藏在 mux 后面。

## 7. 机制六：tree reduction capture-on-stall input cut

开关：`reduction_tree_input_bypass=1`

宏：`ARA_RED_TREE_INPUT_BYPASS`，并与 dense 开关共同生成内部总开关 `ARA_RED_INPUT_BYPASS`

实现位置：`hardware/src/lane/valu.sv`、`hardware/src/lane/vmfpu.sv`

整数规约和无序浮点规约使用 SLDU 构造跨 lane 规约树。原实现中，SLDU 每次把局部结果送回 VALU/VMFPU 前都必须经过接收端 spill；即使接收状态机当拍空闲，也会固定多出一拍。tree input cut 把第 6 节已经验证过的 capture-on-stall 所有权规则推广到两条 tree 接收路径：

- VALU 只对 `[VREDSUM:VWREDSUM]` 的规约 opcode 开放 direct input；
- VMFPU 只对 `VFREDUSUM/VFREDMIN/VFREDMAX/VFWREDUSUM` 开放 direct input；
- stored token 永远优先，spill 非空时完全保持旧行为；
- direct token 遇到接收状态机 ready 时当拍消费；
- direct token 遇到 stall 时自动捕获进原 spill，生产者仍获得一个弹性 credit；
- ordered `VFREDOSUM/VFWREDOSUM` 不满足 tree 条件，继续走 dense/ordered 条件或原始路径。

tree 条件只按 opcode 判断，不额外把状态机枚举拉进 spill 前端。原因是 RX 之外的状态本来就不拉高 consumer ready：提前到达的 token 会自然捕获进 spill，只有真正进入 RX 且 ready 后才会 direct fire。这样既避免跨层状态组合路径，又保留完整的 phase safety。

RTL 断言检查两个核心不变量：direct active 时 spill 必须为空；direct valid 被 stall 时，跨-lane transaction、RX 次数、SIMD 次数和 first-op 状态必须稳定。

## 8. 机制七：无序浮点 terminal-result fusion

开关：`reduction_terminal_fusion=1`

宏：`ARA_RED_VMFPU_TERMINAL_FUSION`

实现位置：`hardware/src/lane/vmfpu.sv`

无序浮点规约完成跨 lane 合并后，lane 0 还要根据 SEW 在 `SIMD_REDUCTION` 中横向折叠一个 64-bit word。原状态机在最后一次 fpnew 结果返回时只设置内部 valid，下一拍再次观察该 valid 后才进入 `MFPU_WAIT`、增加正式 result-queue count 并推进写指针。

融合机制利用 `simd_red_cnt_q == simd_red_cnt_max_q` 判断当前 fpnew response 已经是最终体系结构结果。在同一个 response valid 周期中完成以下动作：

- 把 `vfpu_processed_result` 写入原 result queue slot；
- 设置 slot valid；
- 增加正式 result-queue count；
- 推进 result-queue write pointer；
- 状态直接进入 `MFPU_WAIT`。

它没有旁路体系结构写回队列，只融合“内部最终结果返回”和“结果正式发布”两个相邻状态，因此 VRF grant、尾部策略和提交顺序仍走原路径。该条件只位于 `SIMD_REDUCTION`，不会作用于 ordered `OSUM_REDUCTION`。

## 9. 被否决的原型

开发过程中评估了两个更简单的 input bypass 原型，它们都没有保留在最终设计中：

- 独立 direct/spill mux：短微基准通过，但官方回归在长 unmasked→masked 边界（用例4→5）活锁；
- 单项 mode-switchable buffer：解决了第一个边界，却在全 mask-off e16→masked e32（用例15→16）停滞，说明 masked 协议需要原双项容量和完全切断的 ready 路径。

根因不是简单的数值错误，而是同一返回端口在 transparent/stored 两种握手语义间切换时，SLDU 同步 dummy token、指令完成脉冲和下一指令 token 可能跨越边界。局部 flush 也不能证明所有状态组合安全。

最终 capture-on-stall 方案保留原双项 spill，只允许“同周期被消费”的 token 直通。这个负结果链说明：优化递归环时必须同时证明 token 生命周期、缓冲容量和进度性，不能只验证一条指令的数值结果。

本轮还尝试过整数 VALU 的 terminal-result fusion。第一版在最后一次组合 ALU fold 当拍同时推进指令队列、提交计数和结果队列；定向探针出现不终止。二分后确认，提前一拍完成会与下一条指令的同拍接收及 `SIMD_REDUCTION` 完成条件竞争，单纯增加 wait state仍不足以闭合所有队列元数据时序。因此该整数融合没有保留。当前整数收益只来自已经通过完整回归的 tree input cut，避免为了少一拍引入难以证明的提交协议风险。

## 10. 编译开关与消融配置

所有开关默认都是 0，普通构建保持原始微架构。

```bash
# clean baseline
make compile sim_dir=sim_red_base no_fsdb=1

# 只旁路 VMFPU ordered result queue
make compile sim_dir=sim_red_output \
  reduction_output_bypass=1 no_fsdb=1

# 只旁路 SLDU ordered result queue
make compile sim_dir=sim_red_route \
  reduction_route_bypass=1 no_fsdb=1

# 两项组合
make compile sim_dir=sim_red_opt \
  reduction_output_bypass=1 \
  reduction_route_bypass=1 no_fsdb=1

# masked ordered 也进入两段快速环
make compile sim_dir=sim_red_maskfast \
  reduction_output_bypass=1 \
  reduction_route_bypass=1 \
  reduction_mask_fastpath=1 no_fsdb=1

# 完整方案：快速环 + masked-off token relay
make compile sim_dir=sim_red_maskskip \
  reduction_route_bypass=1 \
  reduction_mask_skip=1 no_fsdb=1

# 完整方案再加入 dense capture-on-stall input cut
make compile sim_dir=sim_red_dense \
  reduction_route_bypass=1 \
  reduction_mask_skip=1 \
  reduction_dense_input_bypass=1 no_fsdb=1

# 在 ordered 完整方案上加入整数/无序浮点 tree input cut
make compile sim_dir=sim_red_tree \
  reduction_route_bypass=1 \
  reduction_mask_skip=1 \
  reduction_dense_input_bypass=1 \
  reduction_tree_input_bypass=1 no_fsdb=1

# 4-lane 当前最终候选：再加入无序浮点末级完成融合
make compile sim_dir=sim_red_tree_fusion \
  reduction_route_bypass=1 \
  reduction_mask_skip=1 \
  reduction_dense_input_bypass=1 \
  reduction_tree_input_bypass=1 \
  reduction_terminal_fusion=1 no_fsdb=1
```

## 11. 无 mask 4-lane 性能实测

条件：`NR_LANES=4`、`VLEN=1024`、`SEW=32`、`LMUL=1`、`VL=32`。`perf_reduction_probe` 的同一个 ROI 包含四类整数规约、三类 unordered FP 规约和一条 ordered FP sum。末尾以 `vmv.x.s` 建立真实结果依赖，确保窗口不会在 Ara 后端完成前关闭。下表是第一阶段六项正确性探针的逐项消融数据；最终八项探针因新增 phase-boundary 检查而在 ROI 外多 1 cycle，但目标指令延迟不变。

| 配置 | ROI cycles | `VFREDOSUM` latency | ordered 相对 clean 改善 |
|---|---:|---:|---:|
| clean | 424 | 287 | - |
| output bypass | 392 | 255 | 11.15% |
| route bypass | 392 | 255 | 11.15% |
| output + route bypass | 360 | 223 | 22.30% |

output-only 和 route-only 都恰好节省 32 cycles；两项组合可叠加为 64 cycles。由于实验 `VL=32`，两项结果分别对应消除一个 `1 cycle/element` 的队列开销，而不是偶然减少固定启动时间。route-only 也独立通过当时的六项正确性测试，证明第二个开关不依赖第一个开关才能工作。

在两项组合上继续加入 capture-on-stall input cut，`VFREDOSUM` 从 223 降到 191，又减少 32 cycles。三个 cut 各自稳定消除 `1 cycle/element`：

| 对比 | `VFREDOSUM` latency | 增量改善 |
|---|---:|---:|
| clean | 287 | - |
| output + route | 223 | 22.30% |
| output + route + dense input cut | 191 | 33.45%（相对 clean） |

使用包含新增 phase-boundary 定向检查的最终探针，ROI 总周期为 425→329，改善 22.59%；dense input cut 相对两项组合的指令延迟为 223→191，增量改善 14.35%。两组报告的 ready 与 workload-equivalent 门禁均通过。

第一阶段 output + route 组合的 ROI 从 424 降到 360，改善 15.09%。加入 dense input cut 后，最终八项探针得到 425→329。各指令对比如下：

| 指令 | clean latency | 组合 latency | 变化 |
|---|---:|---:|---:|
| `vredsum` | 24 | 24 | 0 |
| `vredand` | 40 | 40 | 0 |
| `vredor` | 39 | 39 | 0 |
| `vredxor` | 39 | 39 | 0 |
| `vfredusum` | 49 | 49 | 0 |
| `vfredmin` | 55 | 55 | 0 |
| `vfredmax` | 55 | 55 | 0 |
| `vfredosum` | 287 | 191 | **-96 cycles / 33.45%** |

非目标指令完全不变，说明收益来自 ordered token 环压缩，而不是 workload、前端发射或计数窗口变化。

### 11.1 整数与无序浮点 tree 路径

以下数据来自同一份最终八项 `perf_reduction_probe`，control 与 candidate 的 ready、workload-equivalent 门禁均为 true。control 已开启 ordered 的 output/route/mask/dense 机制，但关闭本节新增的 tree input cut 和 terminal fusion，因此是严格增量消融，而不是拿不同功能配置比较。

| 指令 | tree control | + tree input cut | + FP terminal fusion | 最终相对 control |
|---|---:|---:|---:|---:|
| `vredsum` | 24 | 21 | 21 | 12.50% |
| `vredand` | 31 | 25 | 25 | 19.35% |
| `vredor` | 39 | 32 | 32 | 17.95% |
| `vredxor` | 39 | 32 | 32 | 17.95% |
| `vfredusum` | 49 | 46 | 45 | 8.16% |
| `vfredmin` | 55 | 51 | 49 | 10.91% |
| `vfredmax` | 55 | 47 | 44 | 20.00% |
| ROI total cycles | 329 | 311 | 308 | 6.38% |

tree input cut 单独把 ROI 从 329 降到 311，改善 5.47%。整数四类降低 12.5%–19.35%，无序浮点三类降低 6.12%–14.55%。terminal fusion 在其上再把 ROI 从 311 降到 308，三条无序浮点分别继续减少 1/2/3 cycles；它是固定尾部开销优化，因此短 VL 下相对比例更明显，长 VL 下绝对收益保持近似常数。

探针是顺序指令流，前一条指令提前完成会让后续指令的观测 latency 也发生少量变化。`vfredosum` 在 tree/fusion 版本中也从 191 变为 186/184，但新增条件明确排除了 ordered opcode，因此不能把这 5/7 cycles 写成 ordered 数据通路自身的直接收益；这是 ROI 内前序指令缩短带来的调度上下文效应。

第一阶段 output + route 性能比较门禁结果：

```text
baseline ready       : true
candidate ready      : true
workload equivalent  : true
total cycles         : 424 -> 360 (+15.094%)
VFREDOSUM latency    : 287 -> 223 (+22.300%)
```

### 11.2 ordered widening 路径

`perf_widening_reduction_probe` 单独测量 e16→e32、VL=32 的
`vfwredosum.vs`。源元素均为 FP16 1.0，FP32 seed 为 0；目标寄存器使用满足
widening group 对齐约束的偶数编号。默认版和完整优化版都得到
`0x42000000`（FP32 32.0），且 `fflags=0`。

| 配置 | ROI cycles | `VFWREDOSUM` latency | 相对默认改善 |
|---|---:|---:|---:|
| default | 278 | 264 | - |
| 完整优化 | 182 | 168 | **36.36%** |

两者相差 96 cycles，与普通 ordered sum 的三个 cut 各减少
`1 cycle/element` 完全一致。性能比较的 baseline/candidate ready 均为 true，
workload-equivalent 为 true，ROI 总周期改善 34.53%。这证明三个弹性 cut
不仅在 opcode 条件上包含 `VFWREDOSUM`，而且确实覆盖了 e16→e32 的实际
ordered widening recurrence。

## 12. mask 密度响应

`perf_reduction_mask_probe` 每次只测量一条 e32、VL=32 的 masked `vfredosum`。源元素均为 1.0，mask 分别选择 32/16/8/0 个元素。原始实现的 FPU issue 数和延迟与 active density 无关；完整方案只对 active 元素发射 FPU 运算。

| Active density | 原始 latency | mask fast-loop | fast-loop + relay | 完整方案相对原始改善 | FPU issues（原始→完整） |
|---:|---:|---:|---:|---:|---:|
| 100% | 268 | 204 | 204 | 23.88% | 32→32 |
| 50% | 268 | 204 | 140 | 47.76% | 32→16 |
| 25% | 268 | 204 | 108 | 59.70% | 32→8 |
| 0% | 268 | 204 | 74 | 72.39% | 32→0 |

固定的 mask fast-loop 贡献 64 cycles。对于 100%→25% 区间，每增加一个 skipped element，relay 再减少约 4 cycles；0% 情况还消除了最后一次 FPU drain，实测比线性模型再少 2 cycles。

在本 4-lane、e32、VL=32 配置下，可用以下经验模型描述完整方案，其中 `S` 是 masked-off 元素数：

```text
L_base = 268
L_fast = L_base - 2 × VL = 204
L_relay ≈ L_fast - 4 × S
```

该模型的前两项对应两个被旁路队列，第三项对应被消除的 FPU feedback。全 mask-off 的最终 drain 特例为实测 74 cycles。FPU 动态运算次数则从固定 `VL` 变为 `active_count`，可以作为综合功耗数据出来前的结构性能耗代理，但不能替代真实功耗分析。

ROI 总周期及报告门禁：

| Active density | 原始 total cycles | 完整方案 | 改善 | workload equivalent |
|---:|---:|---:|---:|:---:|
| 100% | 282 | 218 | 22.70% | 是 |
| 50% | 281 | 153 | 45.55% | 是 |
| 25% | 281 | 121 | 56.94% | 是 |
| 0% | 282 | 82 | 70.92% | 是 |

四组 baseline/candidate 的单日志 ready 门禁均为 true。该曲线同时证明两类收益：快速环提供与密度无关的 recurrence 缩短，token relay 提供与稀疏度相关的无效运算消除。

## 13. 正确性与进度性验证

`apps/perf_reduction_probe/main.c` 在 ROI 外执行八个精确检查：

- integer `vredsum`，e32、VL=32；
- unordered `vfredusum`，e32、VL=32；
- unmasked `vfredosum`，e32、VL=32；
- odd `vfredosum`，e32、VL=31；
- masked `vfredosum`，e32、VL=31、mask=`0x55555555`，预期 16 个 active elements；
- masked `vfredosum`，e16、VL=16、mask=`0x5555`，预期 8 个 active elements；
- masked `vfredosum`，e16、VL=7、全 mask-off；
- 紧接上一条执行 e32、VL=1、单元素 active，专门覆盖 opaque phase 切换。

组合版本结果：

```text
integer=20 unordered=20 ordered=20 odd=1f masked=10 masked16=8 transition=0/1 (PASSED)
Core Test *** SUCCESS ***
```

mask 密度探针的 100%/50%/25%/0% 四种结果分别为 32/16/8/0，全部通过；0% active 时 FPU issue 为 0，仍能完成最终 lane-0 归集和 VRF 写回。这是 relay 自身终止能力的极端进度性测试。

0% 探针还把所有源元素替换为 signaling NaN，并在指令前清空 `fflags`。baseline 与完整方案都得到 seed 结果且 `fflags=0`；完整方案同时观测到 FPU issue=0，说明 inactive NaN 没有误入 fpnew。

RTL 内加入六条协议断言：

- skip active 时必须 `mfpu_red_valid_o=1` 且 `vfpu_in_valid=0`；
- skip valid 被 downstream stall 时，`issue_cnt/to_process_cnt/osum_issue_cnt/first_op` 必须跨周期稳定；
- dense bypass 只能在 unmasked ordered 请求且 spill 为空时激活；
- dense direct input 被 stall 时，issue-side 位置必须保持。
- integer tree direct input 只能在请求有效且 spill 为空时激活；
- integer/FP tree direct input 被 stall 时，跨-lane与 SIMD 位置必须保持。

带断言的混合 e16/e32 微基准通过，没有触发协议错误。

官方 `rv64uv-ara-vfredosum` 回归共 17 项：优化版本通过 16 项，并完整运行到测试结束，没有 masked/连续 ordered 活锁。唯一失败与 clean baseline 完全一致：测试用 `VSET(64, e32, m1)` 并硬编码 64 元素期望值，但本配置 `VLEN=1024` 时 e32/m1 的 VLMAX=32。clean 与 optimized 都得到前 32 元素结果 `0x43110000`，测试期望 64 元素的 `0x43908000`。这是测试与配置不匹配，不是优化差异。

官方 `rv64uv-ara-vfwredosum` 回归在 default 和完整优化配置下均为
12/12 通过。它覆盖 e16→e32、e32→e64、masked、奇数 VL 和
tail-undisturbed，因此 widening 正确性不再只是从共享 `OSUM_REDUCTION`
状态推断。

本轮最终候选还执行了仓库中现有的全部 9 个规约官方二进制：

- `vredsum` 20/20、`vredand` 8/8、`vredor` 8/8、`vredxor` 4/4；
- `vfredmin` 17/17、`vfredmax` 17/17；
- `vfwredosum` 12/12；
- `vfredusum` 16/17、`vfredosum` 16/17。

后两者唯一失败均是各自第 4 项的 `VSET(64, e32, m1)` 长向量测试，并且关闭 tree input cut 与 terminal fusion 的 control 得到相同失败。`vfredosum` 的 control/candidate 都只能按本配置 e32/m1 的 VLMAX=32 规约；`vfredusum` 的 control/candidate 都得到 0。因而它们应记录为既有测试/配置问题，不能计作候选通过，也不能归因于本轮优化。除这两个共同失败外，候选未新增官方用例差异。

补充探针开发中还观察到一个未完成最小化的问题：使用 `vmv` 紧邻地产生
active masked widening 的 source/mask，并以很短间隔连续发射 ordered
widening 时，default 和 optimized 都可能停在结果读取或后续 `vsetvli`；
改用与官方回归相同的 `vle8/vle16/vle32` producer 后可以继续执行。该现象
目前只应标记为原路径的 producer-consumer/retire 进度性疑点，不能归因于
本轮旁路，也不能在没有独立最小复现和协议波形前写成已确认 RTL bug。

## 14. 当前结论与论文边界

当前数据能够支持以下结论：

- 三段弹性延迟确实处在 ordered recurrence critical loop 中；
- 每压缩一段，4-lane、VL=32 实测稳定减少 32 cycles；
- valid/ready 端到端握手保持数值正确性和连续指令进度性；
- VMFPU input spill 作为 token credit，使 masked fast loop 不产生 mask-ready 组合环；
- masked-off relay 让实际 FPU 运算数从 VL 降为 active element count；
- capture-on-stall input cut 将 dense ordered 延迟进一步降到 191 cycles；
- 同一 capture-on-stall 原则推广到 integer/unordered-FP tree 接收路径后，目标指令降低 6.12%–19.35%；
- 无序浮点 terminal-result fusion 在 tree cut 之上再消除 1–3 cycles；
- 延迟收益随 mask 稀疏度从 23.88% 扩展到 72.39%，具备可建模的参数化趋势；
- 默认开关关闭，不影响原微架构。

当前已经形成比“普通队列旁路”更完整的论文基本方案：recurrence-aware elastic compression、capture-on-stall phase-safe input cut、mask/token decoupling 和 predicate-aware operation elimination 四部分有明确依赖关系，并有独立消融与密度曲线。

尚不能直接宣称最终论文级 PPA 优势：组合 ready 路径被拉长，必须补综合后的 Fmax、面积和功耗；也尚未按要求开展 2/8/16-lane 实验。论文必须把周期改善换算成 `cycles × clock_period`，并报告面积/能量代价。

## 15. 自适应反馈上下文与返回驱动 DAG

在上述稳定版本之上，新增了一个默认关闭的 4-lane 实验开关：

```text
reduction_context_flow=1
```

Makefile 会在 `nr_lanes!=4` 时直接拒绝该配置，避免把尚未验证的拓扑静默推广到其它 lane 数。RTL 目前只选择 unmasked、e32、lane-local VL 不小于 8 的 `vfredusum`；其它 SEW、mask、opcode 和短 workload 完整回退到原状态机。

该机制不是简单增加一个 accumulator。VMFPU 内保存四个带 `valid/pending/data` 的显式反馈上下文，每个 fpnew 请求携带“DAG 层级 + 目标上下文”tag。返回值按 tag 直接写回唯一 owner；返回处理位于同拍发射判断之前，因此上下文完成当拍即可再次被调度。局部合并采用固定的 `4→2→1` 平衡 DAG，并采用返回驱动调度：0/1 最终就绪后即可先发射第一对，不等待无关的 2/3；两个 pair root 就绪的当拍立即发射总 root；总 root 返回当拍直接进入已有跨-lane tree，不再经过 publish 状态。

关键的新策略是按 lane-local 工作量选择反馈宽度，而不是固定追求最大并行度：

- lane-local VL=8（e32 时为 4 个 64-bit source word）使用 2-context，反馈指针只在 0/1 间轮转，最后直接执行 `2→1`；
- lane-local VL>8 使用 4-context，以四条反馈链覆盖 fpnew ADD latency，再执行 `4→2→1`；
- lane-local VL<8 使用旧路径，避免为极短向量支付上下文启动成本。

固定 4-context 对短 workload 虽能填满输入流水线，却需要三次尾部合并，实测没有胜过原最优路径。2-context 会在反馈未返回时产生少量空拍，但少做两次尾部合并，关键路径反而更短。这说明最优上下文数由“输入阶段吞吐”和“尾部 DAG 深度”共同决定，不能简单设成 FPU latency。当前阈值是 4-lane/e32 的实测落点，后续应推广成由 `source_words`、FPU latency 和 merge depth 共同决定的参数化选择器。

### 15.1 增量消融结果

条件与第 10 节一致：4 lanes、VLEN=1024、e32/m1、architectural VL=32；每 lane 实际处理 VL=8。比较对象是已经启用 tree input cut 和 terminal fusion 的上一版最优候选，不是最初 baseline。

| 版本 | `vfredusum` latency | active cycles | ROI total cycles | 定向结果 |
|---|---:|---:|---:|:---:|
| 上一版最优候选 | 45 | 44 | 308 | PASS |
| 固定 4-context、分阶段控制 | 49 | 48 | 312 | PASS |
| 4-context、返回驱动流式 DAG | 45 | 44 | 308 | PASS |
| 自适应 2/4-context | **43** | **42** | **306** | PASS |

最终自适应版本相对上一版最优候选将目标指令再降低 2 cycles，即 4.44%；相对第 10 节最初 49-cycle control 共降低 6 cycles，即 12.24%。整个混合 ROI 只含一条 `vfredusum`，因此总周期只下降 0.65%，不能把该数字当作纯 `vfredusum` kernel 的收益。

### 15.2 可执行不变量和回归

新增五条局部断言：context 的 resident owner 与 in-flight owner 必须互斥；每个 tagged response 必须命中 pending owner；只允许 4-lane/e32/unmasked `vfredusum` 进入新路径；2-context 指针不得访问 2/3；root 阶段必须始终保有唯一 pending/result owner。带断言的定向探针结果为：

```text
integer=20 unordered=20 ordered=20 odd=1f masked=10 masked16=8 transition=0/1 (PASSED)
Core Test *** SUCCESS ***
vfredusum average execution latency: 43 cycles
```

官方 `rv64uv-ara-vfredusum` 的 17 项中通过 16 项，失败集合与上一版最优候选逐项相同：仍只有第 4 项超出本配置 e32/m1 VLMAX 的既有配置问题。该回归覆盖未选择新路径的 e16/e64/masked/短 e32，以及实际 VLMAX=32 的 2-context e32。另用 e32/m2、architectural VL=64 的定向程序让每 lane 实际处理 16 个元素，强制 4-context 指针完成二次回绕；结果为 64，测试通过且五条 context 断言均未触发。

### 15.3 当前论文边界

本节已经证明“上下文数自适应 + tagged fixed-DAG + return-driven scheduling”在当前 4-lane 短归约上可以胜过固定宽度上下文，并给出了固定 4-context 的负消融。它比单纯多 accumulator 更适合作为论文机制的一部分，但目前仍只是单条 unordered 指令内部的反馈上下文，尚不是跨多条独立指令的 context interleaving。

下一阶段最有研究价值的方向仍是跨指令/跨 tree stage 的 context-interleaved accumulators：在保持每个 ordered context 严格顺序的同时，让不同规约上下文轮转占用 FPU 和 SLDU 空槽。随后应加入参数化上下文选择、综合后的 Fmax/面积/功耗以及不同 VL 分布，联合搜索 `cycles × clock_period × energy`，避免只减少周期却损失 PPA。

## 16. 前台 tree / 后台 local 双上下文流

单条 `vfredusum` 从 45 降到 43 cycles 后，继续压缩局部 DAG 的空间已经很小。16 条相互独立的 e32/m1、VL=32 `vfredusum` 流显示，上一版虽然每条局部计算只有约 14 cycles，但 local、跨-lane tree、SIMD 和提交仍由一个全局 FSM 完全串行，总共需要 612 cycles，平均启动间隔为 38.25 cycles。因此新增第二个默认关闭的实验开关：

```text
reduction_context_flow=1
reduction_context_stream=1
```

`reduction_context_stream` 依赖前一节的 tagged context，并继续限制为 4 lanes。本节记录的第一版只重叠算术配置相同的 unmasked e32 `vfredusum`，要求 opcode、SEW、`vm` 和 rounding mode 相同；不满足条件时不提前移动 issue pointer，完整回退原顺序路径。第 17 节在不改变该门禁原则的前提下继续扩展了适用 opcode。

### 16.1 状态解耦

实现将原来绑定在同一条指令上的三个位置拆开：

- processing/commit pointer 始终指向前台指令 A，A 按原协议经过 SLDU tree、lane-0 SIMD 和顺序提交；
- issue pointer 可以提前移动到独立的后继指令 B，B 使用 tagged 2/4-context DAG 消费自己的 operand queue；
- B 的局部 root 暂存在专用 64-bit background result 中，不允许越过 A 写回；A 完成后，B 的 root 才注入原 `INTER_LANES_REDUCTION_TX`，processing pointer 同时按程序顺序推进。

这不是新增第二套 FPU。调度器采用 foreground-first、work-conserving 仲裁：如果当前周期 tree/SIMD 必须占用 fpnew，则 B 保持 context；否则 B 使用该空闲输入槽。tagged B response 可以与 A 的 untagged tree response交错返回，前者按 context ID 写回，后者仍进入 A 的临时 result slot。A 完成、B 升为前台后，队列释放出的下一条 C 又可成为新的后台，从而形成稳定的跨指令 wavefront。

### 16.2 连续规约实测

条件：4 lanes、VLEN=1024、e32/m1、VL=32，16 条无数据依赖的 `vfredusum`，相同 source/seed、不同 destination。control 是第 15 节已经达到 43-cycle 单指令延迟的自适应 context 版本；candidate 仅额外开启 context stream。

| 指标 | control | context stream | 改善 |
|---|---:|---:|---:|
| 16 条 ROI total cycles | 612 | **402** | **34.31%** |
| 平均启动间隔（ROI/16） | 38.250 | **25.125** | **34.31%** |
| `vfredusum` active cycles | 597 | **387** | **35.18%** |
| 平均 execution latency | 77.000 | **51.625** | **32.95%** |
| 平均 dispatch wait | 30.750 | **19.375** | **36.99%** |
| operand-wait cycles | 492 | **282** | **42.68%** |
| INTRA lane samples | 904 | **64** | **92.92%** |
| TX/RX lane samples | 192/1076 | **192/1076** | tree 工作量不变 |

总吞吐为 control 的 1.522 倍。TX/RX 样本完全不变而显式 INTRA 样本从 904 降为 64，说明收益不是少算了 tree，也不是改变 workload，而是除第一条以外的大部分 local 阶段都被隐藏在前一条指令的 global 阶段中。

### 16.3 正确性和协议门禁

连续流执行了三层检查：

1. 16 个 destination 全部逐个读回，均为预期的 32，而不是只检查最后一条；
2. 另一个 8 指令探针给每条规约配置不同 seed，使期望结果依次为 32～39，最终 mismatch 为 0，验证 context result、instruction ID 和 destination 没有串线；
3. 原混合规约探针仍为 306 cycles，并通过 integer/unordered/ordered/odd/masked/phase-transition 全部检查，说明非同构后继没有错误进入 stream。

在第 15 节五条 context 断言之上新增四条 stream 断言：后台只能在 issue/processing pointer 已解耦时存活；前后台算术配置必须相容；complete context 必须没有 pending fpnew owner；任何 tagged response 必须属于前台 context scheduler 或后台 scheduler。带九条相关断言的连续流、不同 seed 流和混合探针均未触发错误。

官方 `rv64uv-ara-vfredusum` 仍为 16/17，通过/失败集合与 control 完全一致；唯一失败仍是第 4 项超过 e32/m1 VLMAX 的既有测试配置问题。

### 16.4 当前边界

34.31% 是独立同构规约流的吞吐收益，不应写成任意程序或单条规约的加速比。本节版本尚未覆盖 masked、其它 SEW、min/max、整数规约、ordered FP 或不同 rounding mode 的混合流；其中 unordered min/max 和整数规约已由下一节补齐。整个工作仍没有综合后的 Fmax/面积/功耗。论文中应同时报告单条 latency 与 steady-state initiation interval，并把“同构流命中率”作为工作负载参数。后续对 ordered context 应引入 per-context strict-order token，而不是放宽相容性检查后直接共享算术控制。

## 17. 将双上下文流扩展到浮点 min/max 和整数规约

这一轮没有为每类 opcode 复制一套状态机，而是保留第 16 节的共同抽象：前台 context 负责跨 lane tree、最终 SIMD fold 和顺序提交；后台 context 在前台不占用本执行单元的周期中提前完成下一条独立同构规约的 lane-local 部分。两类执行单元的算术延迟不同，因此共享的是 context 解耦和调度原则，而不是强行共享同一种微结构。

### 17.1 `vfredmin/vfredmax`：带运算单位元的 tagged context

VMFPU 原有 tagged fixed-DAG 只允许 `vfredusum`，其 context 清零恰好等价于加法单位元。直接把 opcode 门禁放宽会令 min/max 的每个独立 context 从 0.0 开始，导致全正数的 `vfredmin` 或全负数的 `vfredmax` 得到错误结果。因此新增由 context owner 指令决定的单位元函数：

- `vfredusum` 使用 `+0.0`；
- `vfredmin` 使用 `+infinity`，IEEE-754 e32 编码为 `0x7f800000`；
- `vfredmax` 使用 `-infinity`，IEEE-754 e32 编码为 `0xff800000`。

所有 context 创建位置——新指令入队、普通后继切换、stream 后台启动和外部 issue 初始化——都使用拥有者自己的 opcode 生成单位元，不能使用当前前台的组合控制。这样即使 A 正在提交而 B 被提升，B 的 tagged accumulator 也不会继承 A 的运算身份。新路径仍只选择 4-lane、unmasked、e32、VL≥8 的 `vfredmin/vfredmax`；opcode、SEW、`vm` 和 rounding mode 不同的后继继续走原串行路径。

### 17.2 整数规约：单 shadow accumulator 的 work-conserving 流

整数规约位于 VALU，其 `simd_alu` 是单周期组合数据通路，不存在 fpnew 那种多周期返回和乱序 tag 匹配问题。因此整数路径没有照搬多个 tagged accumulator，而是增加一个后台 shadow context：

- `bg_acc` 保存后继指令已经完成的 lane-local 部分；
- `bg_first` 区分第一次操作需要读取标量 seed，还是后续操作应把 `bg_acc` 反馈到 operand A；
- `bg_active/bg_complete` 区分仍需消费 operand queue 与本地结果已经冻结；
- `foreground_advanced` 记录 issue pointer 已经提前越过前台，防止前台在 TX/SIMD 完成时再次递减 issue count。

启动条件是前台已经进入 TX、RX 或 SIMD，队列中至少还有一条指令，且前后台都是 4-lane、unmasked、VL≥8、相同 opcode 和相同 SEW 的规约。启动只移动 operand issue pointer，architectural commit pointer 仍停在前台，因此后台不能越序写回。

调度采用前台优先：SLDU RX 和最终 SIMD fold 若需要 VALU，本周期完全归前台；否则后台读取下一条指令的 operand queue，依据本周期有效 element 数形成 byte enable，用 `valu_result` 更新 shadow accumulator。若前台比后台先完成，后台的部分 accumulator 被复制到普通 result queue，并回到既有 `INTRA_LANE_REDUCTION` 继续执行；若后台先完成，其结果被冻结，等前台提交后直接进入 `INTER_LANES_REDUCTION_TX`。因此机制不要求后台一定能完全隐藏，只要存在空槽就能取得部分收益。

覆盖的整数 opcode 为：

| 类别 | 指令 |
|---|---|
| 加法 | `vredsum.vs` |
| 位逻辑 | `vredand.vs`、`vredor.vs`、`vredxor.vs` |
| 无符号比较 | `vredminu.vs`、`vredmaxu.vs` |
| 有符号比较 | `vredmin.vs`、`vredmax.vs` |
| widening 加法 | `vwredsumu.vs`、`vwredsum.vs` |

### 17.3 result queue 所有权修正

扩展过程中发现一个只在跨指令 context 重叠时暴露的所有权问题：原 `alu_result_wdata_o` 始终读取 result queue 的 read pointer。在普通串行规约中 read/write pointer 通常相等，所以问题被掩盖；当前台最终结果仍等待写回、后台已经成为 SLDU 输入时，后台 accumulator 实际属于 write pointer。继续读 read pointer 会把前一条指令的最终值当成下一条的 tree partial，产生随指令序号递增的错误结果。

现在仅当 `alu_red_valid_o` 表示向 SLDU 发送 live reduction accumulator 时选择 write pointer；普通 VRF 写回仍选择 read pointer。这个选择显式编码了“SLDU 消费正在构造的 context，VRF 消费最老的已完成 context”，也使后续增加更多 context 时所有权关系可检查。

### 17.4 4-lane 实测

配置保持 4 lanes、VLEN=1024、e32/m1、VL=32。control 打开第 15 节 context flow、关闭 context stream；candidate 仅额外打开同一个 `reduction_context_stream` 开关。

浮点探针包含 8 条连续 `vfredmin` 和 8 条连续 `vfredmax`，每个 destination 都逐一读回验证：

| 指标 | control | candidate | 改善 |
|---|---:|---:|---:|
| ROI total cycles | 351 | **267** | **23.93%** |
| total RVV cycles | 336 | **252** | **25.00%** |
| FP active cycles | 333 | **249** | **25.23%** |
| FP avg execution latency | 41.375 | **31.625** | **23.56%** |
| FP dispatch-wait cycles | 231 | **171** | **25.97%** |
| FP operand-wait cycles | 225 | **141** | **37.33%** |

总吞吐提升为 1.315 倍。该 ROI 还包含两条用于切换 min/max 数据的向量广播，但 A/B workload 完全相同，因此总周期比较有效；它不应被表述成单条 `vfredmin/max` 的 latency 加速比。

整数吞吐探针包含 16 条连续独立 `vredsum.vs`，同样逐一检查 16 个 destination：

| 指标 | control | candidate | 改善 |
|---|---:|---:|---:|
| ROI total cycles | 261 | **201** | **22.99%** |
| total RVV cycles | 245 | **185** | **24.49%** |
| VALU active cycles | 245 | **185** | **24.49%** |
| VALU avg execution latency | 31.438 | **24.188** | **23.06%** |
| VALU dispatch-wait cycles | 189 | **137** | **27.51%** |
| VALU operand-wait cycles | 144 | **84** | **41.67%** |

总吞吐提升为 1.299 倍。operand wait 在两类数据通路都下降最多，符合“后台先消费后继本地 operands、前台继续执行 tree”的设计目标。

### 17.5 正确性、断言和当前边界

整数综合探针以四条连续指令为一组，覆盖上表全部 10 个 opcode，并检查每个目的寄存器；浮点探针覆盖正数 min、负数 max 和 seed 参与；原混合探针继续覆盖 integer/unordered/ordered/odd/masked/e16/phase transition。最终编译后这三组探针全部通过，且 context/stream 断言均未触发。

仓库官方回归结果为：`vfredmin` 17/17、`vfredmax` 17/17、`vredsum` 20/20，`vredand`、`vredor`、`vredxor` 的全部测试项通过。新增的整数断言保证后台 context 始终与前台同构、后台 ALU issue 只出现在允许重叠的 tree/commit 状态、完成结果在提升前保持稳定。

目前可以声称的是：同一前台/后台 context-interleaving 机制已覆盖 unordered FP sum/min/max 和全部整数规约，并在两个连续流 probe 上得到约 23% 的总周期下降。尚未覆盖 masked stream、ordered FP、不同 opcode/SEW 混合流和多 lane 数；也尚未给出综合后的 Fmax、面积和功耗。尤其 VALU 新增了 mux、shadow accumulator 和控制比较，论文结论必须在综合后用 `cycles × clock period` 复核，不能默认周期收益等于实际执行时间收益。

## 18. 第二阶段 1～8 项机制的最终实现状态

本阶段的八项工作不是八套彼此独立的数据通路，而是从“能观察”到“能重叠”、再到“能消除重复工作”的递进结构：第 1 项建立调度归因；第 2～4 项增加 root 缓冲、自适应 slack 和异构控制调度；第 5 项处理 ordered recurrence 的跨指令控制空隙；第 6 项把 context stream 扩展到 masked 路径；第 7 项消除 unordered tree 的固定队列级；第 8 项在严格门禁下复用完全重复的 ordered 结果。

| 项 | 机制 | 实现位置 | 当前作用 |
|---:|---|---|---|
| 1 | stream 调度与瓶颈计数 | `ara_tb.sv` | 区分前台/后台、root 生产/消费、defer 和队列压力 |
| 2 | prefetched-root FIFO | `vmfpu.sv` | tree 忙时保存已完成 local root，避免重新计算或丢失 owner |
| 3 | slack-adaptive prefetch | `vmfpu.sv` | 依据 root 队列余量和 defer 历史动态决定后台发射 |
| 4 | heterogeneous control interleave | `vmfpu.sv` | 在可证明兼容的控制组合间复用空槽，同时保持 context tag 隔离 |
| 5 | ordered successor pre-arm 与首 beat look-ahead | `sldu.sv`、`vmfpu.sv` | 消除 `WAIT_OSUM`/`IDLE` 控制槽，并预取后继 seed/source |
| 6 | masked context 前台加速与安全门禁 | `valu.sv`、`vmfpu.sv` | masked 指令使用加速的前台 DAG；FP 后台 overlap 在无 tag 的 MASKU 接口上保持关闭 |
| 7 | 4-lane tree-stage fall-through | `sldu.sv` | 空队列时把 tree packet 直接送入 lane spill，队列仅作弹性 fallback |
| 8 | exact ordered-source fusion | `ara_sequencer.sv`、`sldu.sv`、`vmfpu.sv` | 对严格相邻且完整指纹相同的 `vfredosum` 排空 operands、跳过重复 recurrence、回放结果与 `fflags` |

### 18.1 第 5 项：控制重叠的收益边界

ordered interleave 仅允许 4-lane、unmasked、e32、相同 opcode/VL/vstart/vtype 的同构后继。SLDU 在前一条最终 token 完成端到端握手时直接预置下一条 `SLIDE_RUN_OSUM`；VMFPU 在前一条 `MFPU_WAIT` 中取得下一条 seed 和第一个 source beat。预取 credit 在整个 beat 发射完成前保持 owner，不会重复确认 operand queue。

8 条 VL=32 `vfredosum` 的独立消融结果为 1316 cycles；关闭第 8 项时，第 5 项命中 7 次 pre-arm、消除 14 个显式控制槽，并完成 28 个 lane 预取事件，但总周期仍为 1316。原因是 ordered FP add 的数据相关 recurrence 比两个控制槽更长，控制空隙被主瓶颈完全遮蔽。因此第 5 项是第 8 项的 feeder 和协议基础，不能单独宣称端到端加速。

### 18.2 第 7 项：tree 队列从必经级变为弹性后备

unordered tree packet 在目标 lane spill 可接收且 issue/commit owner 一致时组合直达；只有部分 lane backpressure 时，未完成部分才落入原 result queue。直达包必须在所有目标握手后一次性扣减 tree commit count，不能同时由普通队列退休逻辑再次扣减。为了避免不同 VMFPU lane 的指令队列位置不一致，FP 直达还要求 SLDU issue/commit 均只有一个 owner。

4-lane 回归中，混合规约由 290 降到 283 cycles，masked 流由 452 降到 432 cycles，浮点 min/max 流由 267 降到 261 cycles；三组结果检查均通过。这个收益来自删除固定 staging，而非减少规约元素数。

### 18.3 第 8 项：中央证明标签、协议化排空和结果回放

融合门禁由中央 `ara_sequencer` 产生，不能由 SLDU 和各 lane 根据自己的过滤队列分别推测。当前完整条件是：两条指令在架构向量指令流中立即相邻，均为 4-lane、e32 `vfredosum`，`vm` 必须相同，并且 `vtype`、VL、vstart、vs1、vs2、source-use、scalar seed 和 FP rounding mode 全部相同。masked 情况下两条指令都隐式读取 v0，原 hazard table 保证任何 v0 生产者不能穿越 leader/candidate。任何中间 load、VALU、slide、mask 或 `vmv` 都会更新中央“上一条指令”，从而使 alias 标签失效。

这个中央标签修复了一个重要的 lane-local 假等价问题：全局 VL=32 在四个 lane 中分解为 8/8/8/8，而 VL=31 分解为 8/8/8/7；若只比较 local VL，前三个 lane 会误判 alias，lane3 却执行正常 recurrence，最终等待永远不会到达的 token。现在 SLDU 和所有 lane 接收同一个中央标签，且标签使用全局 VL/vstart 生成。

alias 指令仍然拥有正常 operand request 和 hazard 生命周期。每个 VMFPU lane 进入 `OSUM_ALIAS_DRAIN`，以完整 source beat 为单位确认 operand queue；lane0 在排空完成后把 leader memoized result 写入 alias 的 destination，SLDU 同步跳过该指令的 token traversal。leader 每个 lane 产生的 FP exception flag 会做 OR 归并，alias 退休时重新产生相同的 `fflags` 脉冲，因此即使软件在两条向量指令之间清除 sticky flags，也不会因数值回放而漏掉异常贡献。

专项探针的 measured region 包含 8 条完全相同的 VL=32 `vfredosum`：

| 指标 | 第 5 项、关闭融合 | 第 5+8 项 | 改善 |
|---|---:|---:|---:|
| ROI total cycles | 1316 | **219** | **83.36%** |
| alias instructions | 0 | **7** | 7/7 后继命中 |
| drained lane beats | 0 | **112** | 7×4 lanes×4 beats |
| result replays | 0 | **7** | 与 alias 数一致 |

专项在 ROI 外还验证三种不命中情形：不同 source、不同 seed，以及 source 寄存器名称相同但中间被 `vmv` 改写；所有结果均正确。另用 signaling NaN 让 leader 产生 NV，等待 leader 完成、清除 `fflags` 后执行 alias，并确认 alias 重新置位 NV，覆盖 exception memo/replay。混合、masked、min/max、整数、widening 和原 stream 六类回归也全部通过，混合探针中的 VL32→VL31 边界专门防止 lane-local 指纹问题复现。

### 18.4 论文表述边界

83.36% 是“连续完全重复 ordered reduction”这一可复用工作负载上的结果，不是任意 `vfredosum` 的平均加速。第 8 项当前覆盖 vm 相同的 unmasked/masked e32 exact alias；它没有覆盖不同 destination 之外还存在数值变化的情况，也没有覆盖其它 SEW、min/max 或整数规约。论文应把 exact-alias hit rate、operand drain 成本和 memo 生命周期作为独立参数，并同时报告第 5 项关闭/开启与第 8 项关闭/开启的消融。面积、Fmax、功耗和更多 lane 数仍需综合与后续试验，周期结果不能直接替代物理实现结论。

## 19. 后续四项补齐：widening、非重复 ordered、masked exact stream 与格式/VL

本节对应第二阶段之后继续要求完成的四项。所有 candidate 均使用同一个 4-lane、VLEN=1024 最终构建；每个数字来自 `rdcycle zero` 标出的相同 ROI，且所有 destination 都做位级结果检查。周期下降只表示 RTL 仿真的 cycle count，尚未包含综合后的 Fmax、面积和功耗。

### 19.1 Widening FP reduction

exact-source 识别和 ordered memo/replay 已同时覆盖 `vfwredosum`，unordered context 门禁覆盖 `vfwredusum`。widening destination 使用 EMUL=2，专项程序只使用偶数目的寄存器组，避免非法重叠把性能问题伪装成寄存器配置问题。

| workload | control | candidate | 改善 | 结果 |
|---|---:|---:|---:|:---:|
| 8× `vfwredusum`, e16→e32, VL=32 | 329 | **215** | **34.65%** | PASS |
| 8× exact `vfwredosum`, e16→e32, VL=32 | 1316 | **220** | **83.28%** | PASS |

ordered widening 流命中 7 个 alias，排空 112 个 lane source beats，并回放 7 次结果；因此其大收益仍属于 exact-reuse workload，而不是一般 widening 规约的平均值。

### 19.2 非重复 `vfredosum` 的 recurrence cut

exact alias 对 source/seed 真正变化的 ordered 流没有帮助。为此保留 bulk fpnew 供吞吐型指令使用，并增加一条仅服务 4-lane `vfredosum/vfwredosum` 的单寄存器 ADD slice。一个寄存器是 SLDU token 协议允许的最短反馈距离；零寄存器原型会在 lane 边界漏掉元素，已作为负结果删除。bulk response 始终拥有返回仲裁优先级，避免指令类别边界串线。

8 条交替 source/seed、alias 命中为 0 的 e32 `vfredosum` 从 1317 降到 **549 cycles**，改善 **58.31%**，256 次输入和 256 次输出握手完全匹配，bulk-priority stall 为 0。重复 source 流在 recurrence cut 与 exact fusion 同时开启时为 123 cycles；这个值不能与只开启 fusion 的 219 cycles 混为单机制消融。

### 19.3 Masked ordered exact stream

直接让 masked FP 后继进入后台 context 的两个原型均被删除。第一个允许各 lane 异步移动 issue pointer，第二个增加全-lane barrier；两者都能在 `perf_masked_reduction_stream_probe` 中复现 context root 永久 pending。根因是原 MASKU 广播只有 valid/ready、没有 instruction tag，而前台 tree 的 lane 角色又不是同周期结束。没有 owner tag 时，barrier 只能证明“都有 mask”，不能证明“mask 属于同一个 successor”。最终 RTL 因此继续禁止 masked FP background context，不以死锁风险换取表面重叠。

保留的优化是 masked exact ordered fusion。中央比较器允许 leader/candidate 的 `vm` 同为 0，其他完整指纹仍必须相等；alias 状态跳过重复 FP recurrence 和 SLDU traversal，但每排空一个完整 source beat就同步拉高 `mask_ready`，所以 MASKU credit 数与正常执行一致。4 条连续 masked e32/VL=32 `vfredosum` 在旧路径上超时，最终路径为 **135 cycles、3/3 alias 命中、结果 PASS**。原 8 条 masked unordered 流仍为 432 cycles、结果 PASS，说明安全门禁没有误把 unordered 指令送入 alias 路径。

### 19.4 e16、e64 与短 VL

unordered context DAG 的中性元现在按 SEW 编码：e16 min/max 使用 `0x7c00/0xfc00`，e32 使用 `0x7f800000/0xff800000`；sum 使用 +0。选择门槛由 VL≥8 降为 VL≥1，并允许 e16/e32 普通 unordered FP reduction 以及合法 widening 格式。e64 unordered context 原型会在最终 `4→2→1` root 上丢失部分 lane 的返回 tag，因此没有保留；e64 unordered 继续走已验证 legacy path，e64 ordered 则由上一节的短 recurrence slice 加速。

| workload | control | candidate | 改善 | 结果 |
|---|---:|---:|---:|:---:|
| 8× e16 `vfredusum`, VL=16 | 240 | **215** | **10.42%** | PASS |
| 8× e32 `vfredusum`, VL=4 | 240 | **209** | **12.92%** | PASS |
| 8× e64 `vfredosum`, VL=16 | 804 | **292** | **63.68%** | PASS |

e64 专项还在 ROI 外执行一条 unordered e64 `vfredusum` 并做位级检查，用来保证未选择 context DAG 的 fallback 正确。最终关键回归保持：masked unordered 432 cycles、非重复 ordered e32 549 cycles、widening unordered 215 cycles、混合规约 187 cycles，全部 PASS。

## 20. 语义感知精确累加后端：第一阶段

在原 tagged fpnew context DAG 之外，新增默认关闭的实验开关：

```text
reduction_exact_sum=1
```

Makefile 当前只允许在 4-lane 配置下打开。第一阶段门禁进一步限定为
unmasked、EW32、非 widening 的 `vfredusum`；ordered sum、min/max、masked、
e16/e64 和 widening 均走原有已验证路径。这样可以独立测量新数据通路，而不把
MASKU/SLDU 协议扩展混入第一份消融。

### 20.1 从浮点反馈到四上下文精确整数域

每个有限 binary32 数都是 `2^-149` 的整数倍。新模块
`fp32_exact_reduction_accum` 将每个输入解码为以 `2^-149` 为最低位权的
288-bit 有符号定点数。连续 64-bit source beat 轮转写入四个独立 bank；
每拍可以同时接收两个 FP32 元素，且同一 bank 的反馈距离为四拍。最后执行
`4→2→1` 精确合并，只在 lane-local root 处按 RVV rounding mode 舍入一次。

288-bit 宽度覆盖当前 VLEN=1024、4-lane 配置下的最坏 EW32 局部元素数和
scalar seed，并留有符号及进位余量。模块另外显式跟踪：

- qNaN/sNaN、正负无穷及 `+Inf + -Inf`；
- 正零、负零、非零有限数和空 source；
- RNE/RTZ/RDN/RUP/RMM，另保留 fpnew 使用的 ROD；
- `NV/OF/NX`，以及 RVV 全 inactive 时原样复制 seed、不得产生异常的语义。

有限输入的精确和仍是 `2^-149` 的整数倍，因此最终 subnormal 不需要额外截断；
普通 `UF` 不会由这条精确路径产生。normal 的 guard/sticky、tie-to-even、
定向舍入和 overflow-to-infinity/max-finite 均在最终舍入器中完成。

### 20.2 与现有 tree/stream 的组合

第一阶段没有改动 64-bit SLDU 接口。每个 lane 把精确局部 root 放入低 EW32
元素，高 EW32 元素填入由舍入模式决定的空子树加法单位元，随后复用既有
跨-lane tree 和 lane-0 SIMD 收尾。因而当前是“lane 内精确、lane 间合法
SEW 精度树”，不是全向量 Kulisch 累加；后者需要在 SLDU 上传递更宽的精确
状态和 empty/special metadata。

连续规约流中，精确后端是独立于 fpnew 的算术域。前台指令在 SLDU tree 使用
fpnew 时，后台 successor 可以同拍读取 source beat 并更新精确 bank；局部
root 仍进入原来的 in-order root FIFO，processing/commit pointer 不提前，
因此保留了既有 context-stream 的顺序提交和目的寄存器隔离。这个并行关系是
第一阶段的主要性能来源，而不只是把一个多 accumulator 换成更宽的 accumulator。

### 20.3 定向验证和增量结果

独立 testbench 共 17 组检查，覆盖基本求和、`1e20 + 1 - 1e20` 精确抵消、
半 ULP 舍入、正负定向舍入、overflow、sNaN/qNaN、相反无穷、符号零、空
子树、inactive seed copy、四 bank 回绕和 output backpressure，全部 PASS。

整机使用与第 19 节相同的 4-lane 完整优化配置，仅增加
`reduction_exact_sum=1`：

| workload / 指标 | 第 19 节 control | exact backend | 改善 |
|---|---:|---:|---:|
| 混合规约 ROI total cycles | 187 | **181** | **3.21%** |
| 单条 `vfredusum` execution latency | 44 | **38** | **13.64%** |
| 单条 `vfredusum` active cycles | 43 | **37** | **13.95%** |
| 16× `vfredusum` stream | 399 | **393** | **1.50%** |

混合探针的八个结果全部通过；16 个独立 destination 的连续流全部通过；不同
seed 的 tag probe 得到 mismatch=0。所有 context/root FIFO 断言均未触发。
官方 `rv64uv-ara-vfredusum` 仍为 16/17，唯一失败仍是测试请求 e32/m1、
VL=64 而当前 VLEN=1024 的实际 VLMAX=32；失败值和既有 control 日志相同，
不是新后端引入的回归。关闭新开关的默认整机配置也已重新编译通过。

### 20.4 当前边界与下一步

这份结果证明了“RVV 语义门禁 + 精确 banked accumulation + 与近似 tree
并行的双算术域”可以在现有 Ara 控制和 64-bit SLDU 接口上形成可工作的最小
闭环，但不能据此宣称论文 PPA 已完成。每 lane 四组 288-bit bank 和宽加法器
面积较大，优先级编码/最终舍入也可能降低 Fmax；必须综合后报告
`cycles × clock_period`、面积和能量。

下一阶段应把单块宽加法改成 exponent-segmented carry-save bins，只在被命中
的指数段传播局部进位；同时为 SLDU 增加 tagged empty/special/exact-state
协议，使四个 lane 的精确状态在最终舍入前合并。随后再扩展 masked EW32、
e16/e64 和 widening，并分别报告数值可重复性、误差、周期和 PPA，而不是只把
更多 opcode 静默加入门禁。
