# Ara RVV 性能指标完备性与瓶颈归因使用指南

目标：回答“是否能做瓶颈归因、可否支撑优化决策”。

结论先行：`ara_tb.sv` 这套监控链路已经覆盖了**指令入口 -> 调度 -> 执行 -> 回写 -> VLSU 内存 -> 主机内存接口**的关键瓶颈维度。按以下矩阵可直接用于瓶颈归因。

## 1) 指标覆盖矩阵

### A. 架构/指令分类层（能回答“哪个RVV类别慢”）
- `print_frontend_report`：按 `ExecValu/Mul/Div/Fp/Slide/Mask/Load/Store/MoveToVec/MoveFromVec/Reshuffle` 汇总
  - 架构指令数、zero-vl、Uop/Byte 形状、SEW/LMUL 形态、异常/配置影响。
- `print_opcode_report`：按单条 RVV opcode (`VADD...VSXE`) 汇总
  - 架构计数、Zero-VL 削减、backend uop 数、完成率、吞吐形状、shape 直方图。

### B. 调度瓶颈层（能回答“为什么卡住/不出发”）
- `dispatch_request_cycles`（请求数）
- `dispatch_blocked_cycles` 与原因分解（比例已输出）
  - `fu_queue_full`（目标VFU队列背压）
  - `mask_queue_full`（mask unit队列背压）
  - `slide_queue_full`（slide队列背压）
  - `id_pool_full`（后端 ID 池满）
  - `response_wait`（sequencer 状态等待）
  - `other_dispatch_blocked`（补集）
  - `operand_request_blocked`（operander 发放阶段背压）
- `dispatch_wait_hist`：等待周期分布（0/1-4/5-16/>16）
- `dispatch_reasons_within_request`：一致性校验 `blocked <= request`

### C. 执行效率层（能回答“卡在谁的执行资源上”）
- `active_cycle`、`issue_progress_cycle`、`no_issue_progress_cycle`
- `operand_wait / unit_input_backpressure / result_queue_full / result_backpressure / latency_order_stall / long_latency_busy`
- 主路径/排他路径：`primary_*`（已按优先级归一化）
- `execution_latency` / `end_to_end_latency`
- `result_queue_occupancy`、lane sample 计数（并行度利用率）

### D. Memory/L/S 内存层（能回答“load/store 是否被 AXI 拿去拖死”）
- `print_memory_pipeline_report` 已覆盖
  - addrgen 阶段（active/progress/no_progress）
  - MMU 请求-响应计数与等待
  - AXI 地址/数据/响应通道有效/握手/反压
  - AXI outstanding 直方图与平均值
  - 读写带宽（transfer/useful bytes）
  - vlsu operand/result 队列压降、异常计数

### E. 掩码/向量特征层（能回答“mask 特征导致的额外开销”）
- `predicate_density_hist`、`predicate_active_ratio`
- `masku` 相关 fifo push/pop、gather broadcast 指标、压缩选择率

## 2) 直接可做瓶颈归因的推荐顺序

1. **先看前端分类负载**：`*_arch_insns`、`*_backend_uops`、`*_dispatch_request_cycles`。
2. **再看调度阻塞组成**：
   - 对每个类/Opcode 看各阻塞原因占 `dispatch_request_cycles` 的比例。
   - 若 `fu_queue_full`/`mask_queue_full`/`slide_queue_full` 高，优先看对应 VFU 深度/发射并发；
   - 若 `id_pool_full` 高，重点看 `vinsn_running` 路径与完成吞吐。
3. **接着看执行“是否有真正进度”**：`primary_*` 比例与 `no_issue_progress_cycle`。
4. **内存程序再核对 VLSU+AXI**：`axi_*_backpressure`、`axi_outstanding`、`outstanding_hist`。
5. **最后看形态影响**：按 `op` 的 `dispatch_wait_hist` 与 SEW/LMUL/shape，找出是特定 shape 的热点。

## 3) 目前新增的“可直接用于优化决策”的强化项
- 所有阻塞原因（class/Opcode）均补齐了 `..._ratio`，不用手工换算。
- 新增 `dispatch_reasons_within_request` 一致性，防止误判“阻塞计数超请求计数”。
- Hazard/序列器/错序等活动态事件新增比例（`*_ratio`），用于快速比较类间瓶颈差异。
- 新增 class 级主归因 Top 指标：
  - `..._top_primary_exec_bottleneck_reason`
  - `..._top_primary_exec_bottleneck_cycles`
  - `..._top_primary_exec_bottleneck_ratio`
  - `..._top_primary_dispatch_bottleneck_reason`
  - `..._top_primary_dispatch_bottleneck_cycles`
  - `..._top_primary_dispatch_bottleneck_ratio_dispatch_request`
  - `..._top_primary_dispatch_bottleneck_ratio_dispatch_blocked`
- 新增 opcode 级主归因 Top 指标：
  - `op_%s_top_primary_dispatch_bottleneck_reason`
  - `op_%s_top_primary_dispatch_bottleneck_cycles`
  - `op_%s_top_primary_dispatch_bottleneck_ratio_dispatch_request`
  - `op_%s_top_primary_dispatch_bottleneck_ratio_dispatch_blocked`
  - `op_%s_top_secondary_dispatch_bottleneck_reason`
  - `op_%s_top_secondary_dispatch_bottleneck_cycles`
  - `op_%s_top_secondary_dispatch_bottleneck_ratio_dispatch_request`
  - `op_%s_top_secondary_dispatch_bottleneck_ratio_dispatch_blocked`
  - `op_%s_top_dispatch_bottleneck_reason_gap`
  - `op_%s_top_dispatch_bottleneck_gap_ratio_dispatch_request`
  - `op_%s_top_dispatch_bottleneck_dominance_ratio`
  - `op_%s_top_secondary_dispatch_bottleneck_dominance_ratio`
  - `op_%s_top_primary_dispatch_bottleneck_advice`
  - `op_%s_top_primary_exec_bottleneck_reason`
  - `op_%s_top_primary_exec_bottleneck_cycles`
  - `op_%s_top_primary_exec_bottleneck_ratio_exec_active`
  - `op_%s_top_secondary_exec_bottleneck_reason`
  - `op_%s_top_secondary_exec_bottleneck_cycles`
  - `op_%s_top_secondary_exec_bottleneck_ratio_exec_active`
  - `op_%s_top_exec_bottleneck_reason_gap`
  - `op_%s_top_exec_bottleneck_gap_ratio_exec_active`
  - `op_%s_top_exec_bottleneck_dominance_ratio`
  - `op_%s_top_secondary_exec_bottleneck_dominance_ratio`
  - `op_%s_top_primary_exec_bottleneck_advice`
- 新增全局统一 Top 榜：
  - `global_top_primary_dispatch_bottleneck_reason`
  - `global_top_secondary_dispatch_bottleneck_reason`
  - `global_top_primary_dispatch_bottleneck_cycles`
  - `global_top_primary_dispatch_bottleneck_ratio_dispatch_request`
  - `global_top_primary_dispatch_bottleneck_ratio_dispatch_blocked`
  - `global_top_dispatch_bottleneck_dominance_ratio`
  - `global_top_primary_exec_bottleneck_reason`
  - `global_top_secondary_exec_bottleneck_reason`
  - `global_top_primary_exec_bottleneck_cycles`
  - `global_top_primary_exec_bottleneck_ratio_exec_active`
  - `global_top_exec_bottleneck_dominance_ratio`
  - `global_top_primary_dispatch_bottleneck_advice`
  - `global_top_primary_exec_bottleneck_advice`
  - `global_top_dispatch_blocked_class` / `_cycles` / `_ratio`
  - `global_top_dispatch_blocked_opcode` / `_cycles` / `_ratio_dispatch_request` / `_ratio_dispatch_blocked`
  - `global_top_exec_wait_class` / `_cycles` / `_ratio_wait`
  - `global_top_exec_wait_opcode` / `_cycles` / `_ratio_exec_active` / `_ratio_wait`
  - `global_top_dispatch_request_class` / `_cycles` / `_ratio_request` / `_ratio_active`
  - `global_top_active_class` / `_cycles` / `_ratio_active`
  - `global_top_completed_class` / `_cycles` / `_ratio_active`
  - `global_top_dispatch_request_opcode` / `_cycles` / `_ratio_request` / `_ratio_active`
  - `global_top_active_opcode` / `_cycles` / `_ratio_active`
  - `global_top_completed_opcode` / `_cycles` / `_ratio_active`
  - `global_primary_dispatch_partition_consistent`
  - `global_primary_exec_partition_consistent`
  - `global_exec_primary_reason_cycles`
  - 全局执行推进层级补充：
  - `global_total_issue_progress_cycles`
  - `global_total_no_issue_progress_cycles`
  - `global_issue_progress_ratio`（`issue_progress / active`）
  - `global_no_issue_progress_ratio`（`no_issue_progress / active`）
  - `global_exec_progress_partition_consistent`（`issue_progress + no_issue_progress == active`）
  - 全局阶段/闭环建议：
  - `global_stage_mode`
  - `global_bottleneck_focus`
  - `global_bottleneck_secondary_hint`
  - `global_top_class_request_share`
  - `global_top_class_active_share`
  - `global_top_class_share_skew`
  - `global_top_opcode_request_share`
  - `global_top_opcode_active_share`
  - `global_top_opcode_share_skew`

其中 ratio 含义：
- `ratio_dispatch_request = top_reason_cycles / dispatch_request_cycles`
- `ratio_dispatch_blocked = top_reason_cycles / dispatch_blocked_cycles`
- `ratio_exec_active = top_exec_bottleneck_cycles / opcode_active_cycle`
  - 全局新增 `global_top_*_ratio_request/ratio_active`：
  - class 级：对 `global_total_dispatch_request_cycles` / `global_total_exec_active_cycles` 做归一化；
  - opcode 级：同理以 dispatch/request 与 active 为分母。
- 额外新增（用于瓶颈归因闭环）：
  - `global_top2_dispatch_bottleneck_share`
  - `global_top2_exec_bottleneck_share`
  - `global_dispatch_exec_class_overlap`
  - `global_dispatch_exec_opcode_overlap`
  - `global_bottleneck_pressure_alignment`
  - `global_bottleneck_opcode_alignment`

补充指标：
- `..._secondary_*`：第二候选原因，避免“第一名单点误导”；
- `..._dominance_ratio`：主因覆盖率（`top_reason_cycles / 总归因周期`）；
- `..._reason_gap`：`top` 与 `second` 的差值（衡量可分离空间）；
- `..._advice`：给出可执行的首选优化方向（导航性质，不是最终定论）。
- 全局 `global_stage_mode` 字段的语义：
  - `dispatch_bound`：调度端阻塞主导，优先看 `global_top_dispatch_*` 与 `dispatch` bottleneck 原因；
  - `execution_progress_bound`：可发指令但缺少执行推进，优先看 `global_top_exec_*` 与 `global_top_exec_wait_*`；
  - `mixed_dispatch_exec_stress`：调度与执行均有显著压力，需先区分主导权重后再分组对齐；
  - `moderate_progress`：两侧无明显失配，瓶颈更可能来自 workload 形状与前后端耦合；
  - `inactive_or_no_exec_activity`：执行侧无活动，请先检查 ROI 边界与 trace 是否已稳定。
- `..._share` 与 `..._skew` 用于快速检查 dispatch 与 exec 的热点类/op 对齐程度：
  - `share` 是 Top 类或 Top Op 在 request/active 两侧的占比；
  - `skew` 是两侧占比差值；`skew` 高时通常意味着前端分配与后端执行负载分布错位。
- 额外集中度/对齐指标解释：
  - `global_top2_dispatch_bottleneck_share`：全局调度端瓶颈前两名合计占比，越高说明瓶颈可被少数阻塞原因覆盖；
  - `global_top2_exec_bottleneck_share`：执行端瓶颈前两名合计占比，越高说明瓶颈可被少数执行停顿路径覆盖；
  - `global_dispatch_exec_class_overlap`：class 维度下 `dispatch_blocked` 与 `exec_wait` 的 overlap 之和，越高说明两阶段瓶颈更同频；
  - `global_dispatch_exec_opcode_overlap`：opcode 维度同上；
  - `global_bottleneck_pressure_alignment`：比较 `top_class` 在调度堵塞与执行等待是否一致；
  - `global_bottleneck_opcode_alignment`：比较 opcode 在调度堵塞与执行等待是否一致。

解读建议：
1. 若 `ratio_dispatch_request` 高：该瓶颈原因是主要全局损失源；
2. 若 `ratio_dispatch_request` 不高但 `ratio_dispatch_blocked` 高：说明阻塞事件占比很集中，但总阻塞比例不一定高（先看 `dispatch_blocked_ratio`）；
3. 同时对比执行 Top 与调度 Top，可区分是“发不出”还是“发了但不进展”。
4. 先看 `global_stage_mode` 决定动作优先级，再用 `dominance_ratio`/`reason_gap` 做收益排序：
   - `global_stage_mode = dispatch_bound`：优先处理 `global_top_primary_dispatch_bottleneck_reason` 与 `global_bottleneck_focus`；
   - `global_stage_mode = execution_progress_bound`：优先处理 `global_top_primary_exec_bottleneck_reason` 与 `global_top_exec_wait_*`；
   - `global_stage_mode = mixed_dispatch_exec_stress`：先确定主导侧，再在同一 `class/op` 上交叉复核 dispatch 与 exec 两侧；
5. `global_top_class_share_skew` / `global_top_opcode_share_skew` 高时先核对 `dispatch_request` 与 `active` 分布：
   - 高 skew 通常提示前端发射、队列拥塞或 shape 切换导致热点未真正转化为执行推进；
- `dominance_ratio` 和 `reason_gap` 用于收益排序：
   - `dominance_ratio` 高 + `reason_gap` 小：主因高度集中，第一优先级优化通常性价比高；
   - `dominance_ratio` 低 + `reason_gap` 小：瓶颈多元化，建议先做交叉归因再拆分策略；
- 两者都低：优先改进 workload 形状或并发行为（SEW/LMUL 分布、前端供给），再谈单点微优化。

## 4) 自动归因脚本（接近闭环关键环节）

新增 `hardware/scripts/analyze_perf_bottleneck.py`，用于把 `ara_tb` 的 `[PERF]` 日志转成可直接执行的瓶颈优先级。支持：

- 阶段判断：`global_stage_mode` + `global_bottleneck_focus`
- 候选优先级：`global_top_primary_dispatch_bottleneck_reason` 与 `global_top_primary_exec_bottleneck_reason` 的优先评分
- `opcode`/`class` 级候选排序：自动提取 `op_<name>_*` 与 `<class>_*` 的 top bottleneck 指标，给出可直接落地的优化候选 Top N
- 一致性检查：`global_primary_dispatch_partition_consistent` / `global_primary_exec_partition_consistent` / `global_exec_progress_partition_consistent`
- 风险提示：alignment/overlap/skew 异常
- 可输出文本、markdown 风格、JSON；支持 `--top-n` 控制 opcode/class 候选条目数

调用方式：
```bash
python3 hardware/scripts/analyze_perf_bottleneck.py <perf.log> [--md] [--json-out report.json]
python3 hardware/scripts/analyze_perf_bottleneck.py <perf.log> --top-n 10 --md
```

或通过 Makefile：
```bash
cd hardware
make analyze_perf log=sim_16_lanes/perf.log
make analyze_perf log=sim_16_lanes/perf.log md=1
make analyze_perf log=sim_16_lanes/perf.log json_out=tmp/report.json
make analyze_perf log=sim_16_lanes/perf.log top_n=12 md=1
make analyze_perf log=sim_16_lanes/perf.log require_ready=1
```

这个脚本可以作为你“后续瓶颈归因”步骤的入口，搭配你已有的 `kernel_sweep` 做每个 kernel 的统一归因比对。

### 4.1 审计输出增强（你现在能直接看到“完备性”）

- 新增字段：`coverage_audit`
  - `coverage_audit.global`：
    - `required`：脚本按关键闭环指标统计的全局必需字段总数；
    - `present`：命中的字段数；
    - `coverage`：全局齐套率（百分比）；
    - `missing_fields`：缺失字段列表；
  - `coverage_audit.op`：
    - `entity_count`：出现且有活动的 opcode 数；
    - `covered_count`：完全齐套 opcode 数；
    - `avg_coverage`：opcode 级平均齐套率；
    - `incomplete_count`：未齐套 opcode 数；
    - `top_incomplete`：按缺失程度排序的最严重样例（默认前 20）；
  - `coverage_audit.class`：同上，按 class 维度统计；
  - `coverage_audit.close_loop_ready`：是否建议直接进入闭环优化决策。
  - `coverage_audit.confidence`：`high` 可用于 RTL 优化决策，`exploratory` 仅适合探索，`insufficient` 表示日志或计数基础不足；
  - `coverage_audit.readiness_blockers`：逐项列出阻断闭环的原因，包括缺字段、无工作负载样本、无活跃 opcode/class、实体字段不齐、计数分区不一致或主原因不占优；
  - `coverage_audit.attribution_ambiguous`：主原因 dominance 小于 0.5 时置位，防止在两个接近的原因中误选优化方向。

`--require-ready`（Makefile 中为 `require_ready=1`）适合回归和 CI：报告不满足闭环条件时退出码为 2。特别注意，**空日志或旧版日志不再被视为 100% 齐套**；没有活跃 opcode/class 样本时齐套率为 0。

闭环门禁同时检查活跃实体的计数不变量，而不只是字段是否存在：

- opcode：dispatch primary 分区、execution primary 分区、dispatch 原因边界、dispatch/latency 直方图、SEW/LMUL/shape 直方图，以及 ROI 生命周期完整性；
- class：dispatch/latency 直方图、active/primary attribution 分区、predicate 密度与 VRF 请求分区，以及 ROI 生命周期完整性。

任何活跃实体出现 `*_consistent: 0` 都会进入 `consistency_failures`，使 `close_loop_ready=false`。这可以防止“字段 100% 齐全、但分母或生命周期定义错误”的报告进入 RTL 优化决策。

### 4.3 真实仿真闭环验收

已用两 lane VCS 和 `imatmul` 的首个 ROI 做端到端验收。该 ROI 覆盖 `VMERGE`、`VMACC`、`VLE`、`VSE`，以及 valu/mul/load/store 四类执行路径。验收过程中实际发现并修复了两项计数错误：

1. opcode dispatch-wait 直方图原先错误地与“等待周期和”比较；直方图记录的是样本数，现改为与 opcode uop 数比较；
2. opcode active cycle 原先把仍保留历史映射、但已不在途的 ID 也算作活跃，现要求对应 `vinsn_running_q[id]` 为真，并在形成当前周期 primary class 标签后再投影到 opcode。

修复后的 `perf_report_imatmul_recheck2.log` 验收结果：

- 全局关键字段：`28/28`；
- 活跃 opcode top 字段：`4/4` 实体完全齐套；
- 活跃 class top 字段：`4/4` 实体完全齐套；
- opcode/class/global 一致性检查全部通过；
- `--require-ready` 返回 `0`，`confidence=high`，`close_loop_ready=true`。

这证明单个已覆盖 workload 的归因链可闭环；它不等价于所有 RVV 类别都已被回归激活。全类别结论仍应由 valu、mul、div、fp、slide、mask、load/store、move、reshuffle，以及不同 SEW/LMUL/VL/mask 密度的测试集合共同证明。

### 4.4 多日志 RVV 套件覆盖门禁

`scripts/analyze_perf_suite.py` 聚合多个 ROI 日志，避免把“单日志可归因”和“全 RVV 已覆盖”混为一谈。它同时报告：

- 11 个执行类别的真实激活覆盖；
- 实际出现过的 opcode 集合；
- SEW 8/16/32/64；
- 合法 LMUL 编码 0/1/2/3/5/6/7；
- masked 与 unmasked 两种形态；
- unit-stride、strided、ordered/unordered indexed、segment、whole-register、mask memory、fault-only-first；
- 每个输入日志自身的 `close_loop_ready`、置信度和阻断项。

调用示例：

```bash
cd hardware
make analyze_perf_suite logs="sim/perf_a.log sim/perf_b.log"
make analyze_perf_suite logs="sim/perf_*.log" require_complete=1 \
  json_out=sim/perf_suite_coverage.json
```

`require_complete=1` 只有在所有类别和形态均被激活、且每个日志都通过单日志一致性门禁时才返回 0；否则返回 2。当前 `imatmul` 首个 ROI 的实际结果为类别覆盖 `36.36%`，明确缺少 div/fp/slide/mask/move/reshuffle、SEW 8/16/32、多个 LMUL 编码、masked，以及非 unit-stride 内存形态，因此不会误报全套件完备。

### 4.5 快速执行路径覆盖内核

`apps/perf_rvv_coverage` 是一个短 ROI，不替代 ISA 正确性测试，只用于稳定激活性能监控路径。它覆盖整数/比较、masked 运算、乘法、scalar-to-vector、vector-to-scalar、内部 reshuffle，以及全部 SEW 和合法 LMUL 编码。末尾使用 vector-to-scalar 响应作为后端排空点；实测证明仅使用标量 `fence` 可能让最后一条 VMERGE 留在 ROI 外，导致 lifecycle 检查失败。

当前三日志套件（imatmul、vsaxpy、perf_rvv_coverage）实测结果：

- 三个日志均 `close_loop_ready=true`、`confidence=high`；
- 执行路径覆盖达到 `81.82%`；
- SEW、合法 LMUL、masked/unmasked 均已覆盖；
- move-to-vector、move-from-vector、reshuffle 和内部 VSLIDEDOWN 路径已覆盖；
- 尚未闭环的执行类别为 div 和原生 mask；复杂内存形态也仍未补齐。

特别需要保留的负向证据：当前 DUT 上，短 ROI 中加入 `vdiv.vv`、原生 slide 或 `vcompress.vm` 后，指令在日常 smoke timeout 内不退休；完整 vdiv/vcompress ISA 测试同样未在合理时间内结束。因此这些类别不能被标记为“指标已验证”，应作为功能/流水线停顿问题优先诊断，而不是为了让覆盖率变绿而绕过。

### 4.6 超时 workload 的监控边界

`ara_tb` 已实现 ROI 内部看门狗。使用 `+PERF_WATCHDOG_CYCLES=<N>` 后，从首个 ROI marker 开始计数；若软件未能执行结束 marker，testbench 会冻结当时的 counter delta，输出完整 PERF 报告，并附加：

- `watchdog_timeout/limit_cycles/observed_cycles`；
- dispatcher 状态与 sequencer RAW/WAR/WAW/block 状态；
- 所有在途 instruction ID 及其 opcode；
- class/opcode/global 的调度、执行、延迟、队列和一致性指标。

分析器把这类报告标为 `confidence=exploratory`，并加入 `watchdog_timeout` blocker。未完成的 opcode/class 生命周期检查会失败，这是正确行为：超时快照可以用于定位停顿，但不能伪装成正常闭环性能样本。

调用示例：

```bash
cd hardware/sim
./simv +NO_FSDB +PRELOAD=<elf> +TESTCASE=<name> \
  +PERF_WATCHDOG_CYCLES=1000
python3 ../scripts/analyze_perf_bottleneck.py perf_report_<name>.log --md
```

真实验证结果：

- `perf_rvv_memory_coverage`：抓到在途 `VLXE`；428 个 load addrgen 活跃周期中，391 周期（91.36%）为 indexed-address spill consumer 未就绪。地址生成主状态驻留 `indexed_offset_generation` 395 周期，AXI 子状态驻留 `axi_request_generation` 400 周期；两个状态直方图一致性均通过。
- `vdiv`：抓到在途 `VDIV`；723 个 div 活跃周期中 713 周期（98.62%）归入 `primary_long_latency_busy`，且完成数为零。
- `vcompress`：mask 类及 `VCOMPRESS` 指标被激活，1000 周期快照时已经无在途向量指令；因此该样本说明窗口包含较长的软件检查/收尾，不能据此宣称 mask 单元永久挂住。
- `vslideup`：原生 slide 类及 `VSLIDEUP` 指标被激活，1000 周期快照时无在途指令；同样应与向量执行停顿区分。

复杂访存内核现将 indexed 路径放在最后，并补充 store counterparts；另有独立的 `apps/perf_rvv_memory_ordered_coverage`，防止 unordered indexed 挂起遮蔽 ordered indexed。最新实测中：

- 正常完成并由退休侧计数验证：unit-stride、strided、segment、whole-register、mask-memory、fault-only-first；
- sequencer 请求侧已经接受：上述全部形态，以及 indexed-unordered、indexed-ordered；
- indexed 两类均在 `VLXE` 内停住，所以退休侧仍将它们列为未完成形态，不能误报为闭环通过。

为保留挂起指令的原始 `mop/nf/lumop` 信息，frontend 现在同时维护两套口径：

- `*_arch_*`：只有架构响应完成后计数，用于正常闭环验证；
- `*_accepted_*`：新架构请求进入 dispatcher 时计数并去重，用于证明指令已进入、以及 watchdog subtype 归因。

套件分析器分别输出“内存形态缺失”“sequencer 已接受的访存形态”和“backend 已接收的访存形态”，不会把接受、后端执行和退休三个阶段混为一个覆盖数字。

### 4.7 VLSU 专属归因

通用 backend 为保证执行分区闭合，会把 load/store 活动归入 `special_path`。这只是统计类别，不足以指导内存优化。现已增加 VLSU 专属指标和分析器排名：

- addrgen 主状态 0..4 驻留直方图：idle、普通地址生成、indexed offset 生成、indexed drain、末次翻译等待；
- AXI addrgen 子状态 0..3 驻留直方图；
- indexed spill wait、last translation wait、addrgen queue consumer wait；
- 原有 operand wait、queue full、MMU wait、AXI 各通道 backpressure/wait、outstanding/latency、mask wait、result queue/backpressure；
- 两组状态直方图与 active 周期的一致性检查。

`analyze_perf_bottleneck.py` 的 `VLSU 专属归因` 段会给出 primary cause、占 addrgen active 的比例、Top 候选、主状态/AXI 子状态驻留和对应优化建议，避免再把 indexed load 停顿误报成 reduction/microcode 问题。

当 `close_loop_ready = false` 时，建议优先补齐：
1. 全局关键字段（例如 `global_stage_mode`、`global_bottleneck_focus`、分区一致性、top2/overlap 等），
2. 活跃实体（OP/class）缺失的 `top_primary/top_secondary`、`ratio`、`gap`、`dominance`、`advice`。

### 4.2 class 与 op top 指标的取值兼容

为了兼容 tb 里已存在的输出差异，脚本在 class 场景支持两种 exec 比例字段：
- `top_primary_exec_bottleneck_ratio`（class）
- `top_primary_exec_bottleneck_ratio_exec_active`（op）
- 同样对 `top_secondary_exec_bottleneck_ratio*` 做了兼容取值。

这避免了仅因字段命名风格不同导致的“假性缺失”。

### 4.8 优化前后闭环比较

新增 `scripts/compare_perf_reports.py`，用于 RTL 优化前后的同 workload 比较。它不是简单相减，而是先建立 workload fingerprint：

- 每个 opcode 的架构指令数、backend uop、请求元素、nominal element ops、masked uop；
- 每个 opcode 的 SEW/LMUL 分布；
- vset SEW/LMUL 分布；
- 架构访存 subtype 分布。

只有 baseline/candidate 都通过单日志 `close_loop_ready`，并且 fingerprint 完全一致时，报告才标记 `comparison_valid=true`。否则逐指标改善/退化榜会被抑制，防止把“少执行了指令”“换了 SEW/LMUL”“改变了访存形态”误报成 RTL speedup。

合法对比会输出：

- total cycles 和 IPC 变化；
- dispatch blocked、issue/no-issue progress 变化；
- class/opcode 执行延迟；
- operand wait、长延迟忙、结果回压、VRF bank conflict 等比例变化；
- VLSU 有效带宽、请求到响应延迟、outstanding 变化；
- 改善 Top 与退化 Top。

调用方式：

```bash
cd hardware
make compare_perf \
  baseline=sim/perf_before.log candidate=sim/perf_after.log \
  require_ready=1 require_equivalent=1 fail_regression_pct=1.0

python3 scripts/compare_perf_reports.py before.log after.log \
  --require-ready --require-equivalent --json-out compare.json
```

`fail_regression_pct` 是 total cycles 的 CI/回归门禁阈值。实测自比较返回 workload 等价、两侧 ready、cycles 变化 0%；将 imatmul 与 vsaxpy 错配时，工具识别出 opcode/工作量/shape 差异并返回 2，且不再显示可能误导的“改善榜”。

### 4.9 MASKU phase/commit 专属归因

通用 `operand_wait` 无法判断 VCOMPRESS 是尚未取得输入，还是元素扫描结束后卡在提交。现增加：

- `mask_operand_incomplete_cycles`；
- `mask_issue_end_cycles`；
- `mask_commit_pending_cycles`；
- `mask_result_queue_nonempty_cycles`；
- `mask_final_grant_wait_cycles`；
- `mask_index_fifo_nonempty_cycles` / `mask_request_fifo_nonempty_cycles`。

`analyze_perf_bottleneck.py` 会独立生成 `MASKU 专属归因`，并同时显示 compress examined/selected 和 gather grant ratio。短 VCOMPRESS ROI 的实测结果为：4 个元素全部 examined、2 个 selected、broadcast grant 100%，但 `commit_pending=436/437 mask-active cycles`，而 result queue 仅非空 3 周期。这把原来的泛化 `operand_wait` 结论收敛到 mask commit counter / `vinsn_done` 生成路径。

## 5) 当前可直接用于瓶颈归因的结论

对“能否做瓶颈归因”：**可以**，你现在已有足够字段完成第一轮瓶颈归因与优化方向筛选。原因是：
- 类级与 opcode 级均有主归因；
- 主归因有主次名次 (`top_primary`/`top_secondary`)；
- 有“可压缩度”指标（`dominance`/`gap`）；
- 有建议字段，能直接连到优化动作（增加队列深度、减少跨周期等待、优化执行路径等）。

对“能否做完整瓶颈归因（闭环归因）”：**已覆盖全部 11 类的激活监测，但尚未完成全部类别的正常退休闭环验证**。七日志套件的当前证据为：

- 11/11 类均有实际激活样本；
- valu/mul/fp/slide/load/store/move-to/move-from/reshuffle 已出现在 `close_loop_ready=true` 的样本中；
- div、原生 mask 目前只有 watchdog/探索性证据；
- SEW 8/16/32/64、全部合法 LMUL 编码、masked/unmasked 已覆盖；
- 复杂访存中 segment、whole-register、mask-memory、fault-only-first 已有退休侧证据；ordered/unordered indexed 已有独立请求侧和 backend 超时证据，但仍缺少退休侧闭环样本。

因此当前指标足以做第一轮归因和挂起定位，但全 RVV 的优化验收仍需补齐正常完成样本及因果/反事实层：
- 原因之间的交叉归因关系（例如 `response_wait` 与 `fu_queue_full` 的因果先后关系）；
- 竞争资源下的反事实分析（比如 queue depth sweep）；
- 指标之间一致性与归因唯一性联合验证（互斥打拍或事件流水）。

你新增的这批全局 `*_top_*` 与 `partition_consistent` 字段能做的升级点：
- 先看 `global_top_dispatch_request_class / top_active_class / top_completed_class`：确认资源瓶颈是否是“类分布问题”还是“指令分布问题”；
- 再看 `global_primary_*_partition_consistent`：一旦出现 0，需先修口径再谈优化；
- 之后再看 `global_top_primary_*_bottleneck_*`：能把“哪个原因占用了瓶颈预算”直接映射到 RTL 模块（队列、ID 池、响应路径等）并给出优化方向。

## 6) 当前局限性（说明真实性）
- 调度阻塞原因信号中存在重叠统计；`*_ratio` 是“与 request 的重叠占比”，不是独占归因。
- Top 指标只输出单一“最大原因”（同值并列时按最近比较顺序决定），用于快速归因；若你要完整重叠分解与优先级归因，还需额外的互斥分类流水线打拍。
- 若要“严格分摊到单一瓶颈原因”，可再加一组优先级互斥计数（如按固定优先级打拍）作为第二份 `primary_dispatch_*`。
