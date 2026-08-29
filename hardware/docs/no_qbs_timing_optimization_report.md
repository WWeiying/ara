# No-QBS 时序优化实验报告

## 1. 报告范围

本文记录 Ara DSA 项目中 no-QBS 配置的 setup 时序诊断、RTL 结构优化、综合流程对齐、功能回归和性能回归结果。这里的 no-QBS 指不集成 QBS 执行引擎的通用 CVA6 + Ara 设计，用于隔离基础 RVV 前端、dispatcher、sequencer、lane、SLDU 和 VLSU 本身的时序问题。

本轮工作的目标是：

1. 在不改变 `1.0 ns` 目标周期和 `0.15 ns` setup uncertainty 的前提下缩短 no-QBS Ara 新增语义形成的长组合路径。
2. 保留从 `main` 之后积累的 RVV 正确性修复，不能通过直接恢复简化的 main RTL 获得表面上的时序改善。
3. 尽量不增加架构可见延迟，不降低代表 kernel 的周期性能。
4. 用可综合的结构性修改替代依赖 DC 偶然优化的宽算术、动态索引和 ready/valid 反馈路径。

本报告只评价综合后的寄存器到寄存器 setup 路径。DC 的 hold 数值一并记录，但不把理想时钟条件下的 hold 修复作为本轮结论；hold closure 应在 CTS 和布线后完成。

## 2. 版本和实验环境

### 2.1 工作树

| 用途 | 本地工作树 | 基准提交/状态 |
| --- | --- | --- |
| 当前 QBS 开发主工作树 | `/home/wangwy/openproject/ara_dsa` | 当前文档所在仓库 |
| no-QBS 第一轮候选 | `/home/wangwy/openproject/ara_dsa_no_qbs` | `d0c7d62d` 上的未提交实验修改 |
| no-QBS 完整 C910 候选 | `/home/wangwy/openproject/ara_dsa_no_qbs_pulp_eval` | `d0c7d62d` 上的未提交实验修改 |
| PULP div/sqrt 独立 A/B | `/home/wangwy/openproject/ara_dsa_no_qbs_round_full_eval` | 独立正确性和性能实验，不属于完整 C910 综合结果 |
| 紧耦合 main_real 参考 | `/home/wangwy/openproject/dc_ara_main_real` | 独立 main_real 综合环境 |

共同 no-QBS 基准提交为：

```text
d0c7d62d3be3c6c05f320252b95d65f0ca0a323a
Add Qwen workload metrics and Zvfh scale optimization
```

实验候选仍是本地未提交修改。报告中的完整 C910 候选不能通过一个提交号单独复现，必须结合上述工作树和本报告列出的 diff 范围保存。

### 2.2 综合条件

| 项目 | 设置 |
| --- | --- |
| 综合工具 | Synopsys Design Compiler `T-2022.03-SP2` |
| 工艺库 | TSMC 28HPC+ `tcbn28hpcplusbwp12t40p140` |
| 标准 corner | `tt0p9v25c` |
| 时钟周期 | `1.0 ns` |
| setup uncertainty | `0.15 ns` |
| hold uncertainty | `0.075 ns` |
| 时钟 transition | `0.08 ns` |
| 最大 data transition | `0.3 ns` |
| 输入 max delay | `0.5 ns` |
| 输出 max delay | `0.4 ns` |
| SRAM macro 数量 | 56 |
| 关键 path group | `clk_i`, weight 10 |

第一轮和完整候选使用相同的最终 SDC，因此二者之间可以直接比较。历史 no-QBS 基线来自修改前的综合记录，其原始报告后来被覆盖，且当时综合脚本和 SDC 尚未完全与 `main_real` 对齐；历史基线只用于表示工程演进，不能视为严格的单变量 A/B。

## 3. 原始问题

### 3.1 历史 no-QBS setup 状态

修改前记录的 no-QBS 结果为：

| 指标 | 历史 no-QBS 基线 |
| --- | ---: |
| `clk_i` WNS | `-0.922 ns` |
| `clk_i` TNS | `-14548.149 ns` |
| `clk_i` 违例路径数 | `45130` |
| 总面积 | 约 `3181412 um^2` |
| `i_system` 面积 | `1466681.86 um^2` |
| `i_system/i_ara` 面积 | `1154427.72 um^2` |

原始最差路径从 dispatcher 的请求寄存器 `ara_req_o_reg_vs2__2_` 出发，经过 sequencer 的相关性判断和接受条件，再反馈到 dispatcher/CVA6 scoreboard 一侧。该路径不是单个运算器延迟，而是以下控制链在一个周期内串联：

```text
dispatcher request state/data
  -> Ara sequencer access-list and hazard construction
  -> backend ready/accept decision
  -> dispatcher request/state response
  -> CVA6 scoreboard or dispatcher state register
```

这说明首要问题是前后级之间缺少真正的非穿透时序边界。单纯提升 cell drive、增加 timeout 或依赖 DC replication 不能消除该组合反馈结构。

### 3.2 代表路径分类

历史审计对 `clk_i_max.tim` 中 999 条可分类代表路径得到以下分布。它不是所有违例路径的精确占比，但能说明优化对象不只集中在 dispatcher：

| 路径类别 | 条数 |
| --- | ---: |
| lane 到 lane 数据/控制路径 | 452 |
| dispatcher 内部 | 158 |
| dispatcher 到其他 CVA6 逻辑 | 136 |
| dispatcher 到 scoreboard | 82 |
| VLSU | 76 |
| CVA6 到标量 FPU | 37 |
| 标量/向量 FPU 内部 | 36 |
| SLDU | 13 |
| sequencer 到 dispatcher | 6 |
| 其他 | 3 |

由此形成两级根因假设：

1. 第一优先级是切断 dispatcher、sequencer 和 CVA6 之间的 request/ready/hazard 组合反馈。
2. 切断全局反馈后，lane 算术、动态 hazard table 行选择、segment 控制、SLDU shuffle 和 VLSU 地址对齐等局部数据路径会成为下一层瓶颈。

后续综合结果中的关键路径迁移与该假设一致。

## 4. 第一轮优化：切断全局请求和相关性反馈

第一轮候选位于 `ara_dsa_no_qbs`。相对 `d0c7d62d`，主要修改以下文件：

```text
hardware/src/ara_dispatcher.sv
hardware/src/ara_sequencer.sv
hardware/src/lane/simd_alu.sv
hardware/src/segment_sequencer.sv
hardware/src/sldu/sldu.sv
backend/syn/ara_soc/v1-dc/global_scripts/dc.tcl
backend/syn/ara_soc/v1-dc/local_scripts/ara_soc.sdc
hardware/Makefile
```

### 4.1 Dispatcher 非穿透请求队列

原实现把 dispatcher 生成的请求直接暴露给 sequencer，sequencer 的 `ready` 又参与 dispatcher 本周期状态和请求生成，形成长组合环路。

第一轮在 dispatcher 和 sequencer 之间加入深度为 2、`FALL_THROUGH=0` 的 `fifo_v3`：

```text
CVXIF/dispatcher decode
  -> non-fall-through request FIFO, depth 2
  -> Ara sequencer hazard/issue logic
```

该结构具有四个关键行为：

1. dispatcher 的 enqueue ready 只由 FIFO `full` 状态决定，不再直接依赖 sequencer 本周期的 hazard 结果。
2. sequencer 只读取已寄存的 FIFO 队首，请求数据和接受反馈跨越寄存器边界。
3. 两个 entry 允许 enqueue/dequeue 稳态并行，目标是保留每周期一个请求的峰值投放率。
4. FIFO 必须非 fall-through，否则空 FIFO 时数据和 valid 仍可能直接穿透，重新形成组合路径。

队列加入后，`ara_idle_internal` 定义为：

```text
ara_idle_internal = ara_idle_i && !ara_req_valid_o
```

即 sequencer 空闲但 FIFO 仍有请求时，dispatcher 不能误认为整个 Ara 已空闲。该条件对维护请求、reshuffle 和异常恢复尤其重要。

### 4.2 防止 held CVXIF 请求重复入队

CVXIF 请求可能保持 valid，直到收到 dispatcher 的确认。加入 FIFO 后，如果只把 `valid && !full` 当作入队条件，同一条架构请求可能连续入队多次。

`normal_req_issued_q` 用于记录当前 held 请求已经进入解耦队列：

1. 第一次正常请求成功 enqueue 后置位。
2. held 请求仍在接口上时禁止重复 enqueue。
3. 请求完成或 dispatcher 正式结束该请求时清零。
4. segment memory 请求由 segment sequencer 的微操作接受语义单独管理。

该状态不是性能优化附属细节，而是增加请求队列后必须具备的正确性条件。

### 4.3 请求 token 和 segment 接受事件对齐

请求 token 改为在实际 enqueue 时翻转，而不是在候选请求形成时变化。这样 token 对应进入后端管理域的请求，不会因 FIFO 满、重试或候选回滚而漂移。

segment request 的 accepted 事件改为以 FIFO dequeue 为准。enqueue 只说明微操作已经被前级缓存，不能代表 sequencer 已经接收并执行。

### 4.4 Overlap 上下文预计算

原 dispatcher 在 overlap/reshuffle 状态中动态组合计算当前寄存器、边界寄存器、每寄存器元素数、边界元素位置和旧 EEW 状态。这些结果同时影响请求数据、状态推进和 EEW scoreboard 更新。

第一轮增加并寄存以下上下文：

```text
overlap_current_vd_q
overlap_boundary_vd_q
overlap_elements_per_reg_q
overlap_reg_first_element_q
overlap_current_old_eew_q
overlap_boundary_old_eew_q
overlap_current_old_eew_valid_q
overlap_boundary_old_eew_valid_q
```

目的不是改变 overlap 算法，而是让重放/修复阶段消费稳定的寄存值，减少同一周期内重复 decode、索引和边界计算。

### 4.5 Sequencer retirement pulse

访问表清理不能简单使用当前 `vinsn_running` 的组合值，因为 vid 可能在同周期完成并被复用。第一轮增加 `vinsn_retired_q`，显式记录：

```text
vinsn_retired_q = previous_running & ~next_running
```

read/write list 和 read mask 使用 retirement pulse 清理旧 vid。这样把“上一条指令刚完成”和“该 vid 当前已重新分配”区分开，既避免 stale entry，也减少清理逻辑对广域 running vector 的组合依赖。

相关 `$onehot`/`$onehot0` 判断改为等价位运算，避免综合出通用计数/比较网络。对于不分配普通 vid 的 unmasked scalar-return 请求，不再建立无生命周期可清理的 access-list 项。

验证断言检查：

1. retirement pulse 与 running vector 的边沿一致。
2. access list 不引用既不 running 也不刚 retired 的 vid。
3. read mask 中不存在 stale vid。

### 4.6 SIMD averaging 算术收敛

`VAADD/VAADDU/VASUB/VASUBU` 原实现同时构造 signed 和 unsigned 宽加减结果，再在结果端选择，并另行执行 rounding add。该结构使每个 SEW 同时存在两条宽算术链。

第一轮把 signed/unsigned 差异折叠为条件符号扩展，只保留一条加法或减法链；保留位 LSB 和丢弃位由低位代数关系直接得到，round increment 以低位加数形式并入同一条算术链。该重写保持四种 `vxrm` 语义，但减少重复宽加法器和结果 mux。

### 4.7 Segment 和 SLDU 第一阶段整理

segment sequencer 开始区分 FIFO ready 和 backend accepted，并引入 queued/wait-response 状态，使微操作不能因前级可缓存而提前推进架构计数。

SLDU spill register 输入改为显式 packed-struct wire，避免大结构体在模块连接处反复展开和重组。该修改主要改善综合可见性，功能语义不变。

## 5. 第二轮优化：局部 lane、算术和地址路径

完整候选位于 `ara_dsa_no_qbs_pulp_eval`。目录名中包含 `pulp_eval`，但本次完整 DC 综合仍使用 C910 div/sqrt；PULP 只在单独工作树中做 A/B。

第二轮保留第一轮 dispatcher FIFO、sequencer retirement 和 SIMD average 修改，并进一步修改：

```text
hardware/src/ara_dispatcher.sv
hardware/src/lane/lane.sv
hardware/src/lane/lane_sequencer.sv
hardware/src/lane/operand_requester.sv
hardware/src/lane/simd_mul.sv
hardware/src/segment_sequencer.sv
hardware/src/sldu/sldu.sv
hardware/src/vlsu/addrgen.sv
```

`hardware/src/lane/vmfpu.sv` 相比第一轮只有注释差异，不构成功能或时序优化。

### 5.1 Dispatcher 常数幂算术替换

对于合法 RVV 配置，VLEN、每寄存器 byte 数和每寄存器元素数均为 2 的幂。原代码仍使用通用 `/` 和 `%` 计算 active register、边界 register 和 overlap 位置，综合器可能产生较宽除法/余数选择网络。

完整候选使用：

```text
elements_per_register_shift = log2(VLENB) - EEW
first_register              = vstart >> elements_per_register_shift
last_register               = (vl - 1) >> elements_per_register_shift
offset_in_register          = element_index & (elements_per_register - 1)
```

同时收窄中间量到实际所需的 `vlen_t`、4 bit register count 等宽度。该转换成立的前提是 VLEN 和合法 EEW 对应的每寄存器元素数为 2 的幂；断言和 RVV 配置约束必须继续保证该前提。

### 5.2 Lane request 非穿透 FIFO

lane sequencer 原有 depth-1 fall-through request register 仍允许 sequencer 控制直接影响 lane 内 requester。完整候选改为 depth-2、非 fall-through FIFO，并在 LSU exception 时 flush。

这样形成第二个明确的时序边界：

```text
global sequencer
  -> registered lane request FIFO
  -> operand requester and lane execution
```

请求 ID mask 和异常恢复语义保持不变。两个 entry 用于吸收前后端速率差，避免单纯增加一级寄存器造成持续吞吐下降。

### 5.3 Completion-only hazard mask 去动态行选择

operand requester 原先按请求 id 动态选择：

```text
global_hazard_table_i[request_id]
```

该表达式在每个 lane 上形成宽表动态行 mux。对于已经由 sequencer 标记为 `hazard_wait_complete` 的依赖，真正需要判断的只是目标 vid 是否仍在运行，不需要重新读取完整 hazard table 行。

完整候选把 completion-only mask 改为直接与 `pe_vinsn_running_i` 相与：

```text
wait_mask = hazard_wait_complete & pe_vinsn_running_i
```

这不是放宽依赖。sequencer 仍负责构造 `hazard_wait_complete`，operand requester 只把其生命周期条件从动态表行改写为等价的 running vector。仿真断言逐周期验证：

```text
(hazard_wait_complete & pe_vinsn_running_i)
==
(hazard_wait_complete & global_hazard_table_i[request_id])
```

只有该等价性持续成立时，去除动态 mux 才是安全的。

### 5.4 Indexed load/store 范围计算移位化

lane sequencer 中 indexed load/store 的 `vstart`、`vl` 和元素范围计算原本包含通用乘除。完整候选根据 EEW/SEW 的 2 的幂关系替换为移位和 mask，并收窄中间位宽。

目标是减少 request FIFO 输出到 operand 请求范围之间的组合深度，不改变每个 lane 接收的元素区间。

### 5.5 VSMUL 结果切片

`VSMUL` 只需要乘积中目标宽度对应的固定点结果位和 1 bit rounding increment。原实现先对完整的 128/64/32/16 bit 乘积右移，再进行宽结果相加。

完整候选直接选取最终所需切片：

```text
EW64: product[126:63] + round
EW32: product[62:31]  + round
EW16: product[30:15]  + round
EW8 : product[14:7]   + round
```

这避免把完整乘积移位网络放在结果关键路径上。专门的 `vsmul` directed regression 验证了四种元素宽度和 rounding 行为。

### 5.6 Segment 微操作接受/完成解耦

完整候选进一步严格定义 segment 微操作生命周期：

```text
candidate -> queued -> backend accepted -> response -> next field
```

新增或完善 `micro_op_queued_q`、`micro_op_wait_resp_q` 和 `micro_op_last_q`。下一 field 的 metadata 在前一 field response 之前已由寄存计数器准备，但 response 只控制 valid，不直接进入下一请求 data cone。

该改动同时实现两个目标：

1. 避免 response、counter update 和下一请求 data 在同一组合链中串联。
2. 明确区分 FIFO 接收与 backend 执行，避免 segment field 重复、跳过或提前结束。

### 5.7 SLDU 位宽收敛和逻辑顺序 zero mask

SLDU 的 LMUL group byte 数改为常量 case decode，并使用覆盖最大合法 group 的最小宽度。对于 `vslidedown` 超出源 group 的 byte，原实现先计算 shuffle 后索引，再动态改写目标 byte；完整候选先在逻辑 byte 顺序生成 `source_zero_seq`，然后与正常 byte enable 一起经过固定 shuffle。

```text
logical source byte index
  -> out-of-range zero mask
  -> fixed lane shuffle
  -> result-byte select
```

这样移除了动态 `shuffle_index` 反查、除 8、模 8 和可变 byte write。功能上仍只在架构规定的源 group 边界外补零。

### 5.8 VLSU AddrGen 实际宽度对齐

VLSU 地址生成原先通过通用 128 bit 变量移位实现 AXI 地址对齐，并使用较宽中间量计算最大 burst bytes。完整候选：

1. 按实际 AXI 数据宽度使用局部 `align_axi_addr` case。
2. 用常量 decode 得到最大 burst byte 数。
3. 把串行地址加法折叠进对齐操作数，减少连续加法级数。
4. 保持 demand/prefetch 地址和 burst 边界语义不变。

## 6. 综合脚本和约束对齐

以下修改用于让 no-QBS 与 `dc_ara_main_real` 在同一目标下比较，同时提高 DC 对高扇出时序网的优化自由度：

| 文件 | 修改 | 目的 |
| --- | --- | --- |
| `dc.tcl` | `compile_register_replication false -> true` | 允许复制高扇出寄存器，降低广域控制网负载 |
| `dc.tcl` | `verilogout_no_tri ture -> true` | 修正拼写，保证网表输出变量生效 |
| `synopsys_dc.setup.gui` | clock-gating 最小 bitwidth `4 -> 8` | 避免过细粒度门控引入过多局部控制 |
| `synopsys_dc.setup.gui` | gating setup `0.2 -> 0.05` | 减轻门控 setup 约束对映射的干扰 |
| `ara_soc.sdc` | 时钟改为 `1.0 ns` | 直接以 1 GHz 为目标 |
| `ara_soc.sdc` | setup uncertainty 固定为 `0.15 ns` | 与 main_real 对齐 |
| `ara_soc.sdc` | max transition `0.4 -> 0.3 ns` | 提高数据网 transition 要求 |
| `ara_soc.sdc` | `clk_i` path weight `5 -> 10` | 提高寄存器路径优化优先级 |
| `ara_soc.sdc` | 增加 min input/output delay 0 | 完整定义 I/O min 分析 |
| `ara_soc.sdc` | RVFI false path 使用 quiet/guarded collection | 避免层次不存在时脚本失败 |
| `hardware/Makefile` | 增加 synthesis/no-default-target 和 SRAM exclusion target | 生成正确的综合文件列表，排除行为 SRAM 重复实现 |

这些 flow 变化与 RTL 修改是累积生效的。本轮没有对每个 flow 开关做独立综合，因此不能把 WNS 改善中的某一固定比例单独归因给 register replication、clock gating 或某个 RTL hunk。

## 7. 综合结果

### 7.1 Setup 汇总

| 设计 | `clk_i` logic levels | path length | WNS | TNS | 违例路径数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| main_real 参考 | 6 | `0.857 ns` | `-0.019 ns` | `-17.616 ns` | 2513 |
| 历史 no-QBS | 未保留 | 未保留 | `-0.922 ns` | `-14548.149 ns` | 45130 |
| no-QBS 第一轮 | 62 | `1.345 ns` | `-0.484 ns` | `-7706.107 ns` | 40579 |
| no-QBS 完整 C910 候选 | 85 | `1.034 ns` | `-0.180 ns` | `-1389.477 ns` | 14442 |

logic levels 是 DC 映射后报告的 cell level 数，不应脱离 cell 类型、重构和路径端点直接比较。完整候选虽然 level 数高于第一轮，但路径由较小逻辑单元组成且总 delay 更低，因此实际 WNS 更好。

本表严格取 `Timing Path Group 'clk_i'`。`qor.rpt` 末尾的 Design 汇总还可能合并 `INPUTS` 等 path group，例如完整候选的 Design 汇总为 TNS `-1392.760 ns`、14539 条违例；它与表中 `clk_i` 的 `-1389.477 ns`、14442 条不是同一统计口径。

### 7.2 改善幅度

| 比较 | WNS 违例幅度降低 | TNS 降低 | 违例路径数降低 | 总面积变化 |
| --- | ---: | ---: | ---: | ---: |
| 第一轮相对历史 no-QBS | 47.51% | 47.03% | 10.08% | +0.423% |
| 完整候选相对历史 no-QBS | 80.48% | 90.45% | 68.00% | +0.309% |
| 完整候选相对第一轮 | 62.81% | 81.97% | 64.41% | -0.114% |

历史 no-QBS 与后两轮的 SDC/flow 不完全相同，因此第一、二行是工程进展指标。最可信的直接 A/B 是第一轮与完整候选：二者约束一致，完整候选把 WNS 再改善 `0.304 ns`，TNS 减少 `6316.630 ns`，违例路径减少 26137 条。

### 7.3 关键路径迁移

第一轮最差路径为：

```text
Start:
i_system/i_ara/gen_lanes_1__i_lane/
  i_operand_queues/i_operand_queue_alu_a/i_cmd_buffer/
  mem_q_reg_3__conv__2_

End:
i_system/i_ara/gen_lanes_1__i_lane/
  i_vfus/i_valu/result_queue_q_reg_0__wdata__32_

WNS = -0.484 ns
```

该路径从 operand queue 进入 VALU averaging/rounding 结果队列。全局 dispatcher-sequencer 反馈不再是第一名，说明第一轮非穿透边界确实暴露了下一层 lane datapath 瓶颈。

完整候选最差路径为：

```text
Start:
i_system/i_ara/i_dispatcher/overlap_reg_first_element_q_reg_2_

End:
i_system/i_ara/i_dispatcher/eew_valid_q_reg_6_

Arrival  = 1.034 ns
Required = 0.854 ns
WNS      = -0.180 ns
```

路径已迁移为 dispatcher 内部 overlap context 到 EEW validity 状态的局部更新。它不再跨越 sequencer、lane 或 CVA6 scoreboard，表明大范围组合反馈已经基本移除。当前剩余问题是 overlap/EEW 状态更新 cone 仍然过深，不是原来的全局 request-ready 环。

### 7.4 面积

| 设计 | 总面积 | `i_system` | `i_ara` | dispatcher |
| --- | ---: | ---: | ---: | ---: |
| main_real | `2928017.204` | `1215433.4958` | `915540.9599` | `6347.7119` |
| 历史 no-QBS | 约 `3181412` | `1466681.86` | `1154427.72` | 未保留 |
| no-QBS 第一轮 | `3194884.696` | `1479354.4354` | `1164899.4917` | `32551.5117` |
| no-QBS 完整候选 | `3191246.824` | `1475943.0275` | `1168327.5317` | `24733.6318` |

单位为综合报告中的 `um^2`。完整候选相对第一轮：

1. 总面积减少 `3637.872 um^2`，约 0.114%。
2. dispatcher 减少 `7817.880 um^2`，约 24.0%，说明常数幂算术和逻辑收窄抵消了请求 FIFO 的部分面积。
3. `i_ara` 增加 `3428.040 um^2`，约 0.294%，主要与 lane request FIFO、附加寄存状态和局部重构有关。

完整候选相对 main_real 总面积高约 9.0%，但该差值不能解释成“时序优化开销”。no-QBS 基线本身已经包含 main 没有的后续 RVV 正确性、group span、overlap 修复和 source-lifetime 状态；时序修改只占其中很小一部分。

### 7.5 Design-rule 和 hold 记录

| 设计 | max transition 违例 | max fanout 违例 | hold WNS | hold TNS | hold 违例路径 |
| --- | ---: | ---: | ---: | ---: | ---: |
| main_real | 7 | 659 | `-0.150 ns` | `-1020.112 ns` | 27897 |
| 第一轮 | 0 | 72 | `-0.150 ns` | `-1201.341 ns` | 37786 |
| 完整候选 | 0 | 252 | `-0.150 ns` | `-1216.020 ns` | 37001 |

DC 使用 ideal clock，且本轮目标是 setup 结构优化。表中 hold 数据不能作为布局布线后的 hold signoff 结论；需要 Innovus CTS、route 和 post-route extraction 后统一修复。

### 7.6 综合耗时

| 设计 | DC compile wall time | 含准备/报告阶段的 console elapsed |
| --- | ---: | ---: |
| main_real | `27222.277 s`，约 7 h 34 min | 未单独记录 |
| no-QBS 第一轮 | `34754.406 s`，约 9 h 39 min | 约 10 h 30 min |
| no-QBS 完整候选 | `30600.303 s`，约 8 h 30 min | 约 9 h 24 min |

compile wall time 来自 `qor.rpt`，console elapsed 还包括文件列表生成、elaboration 前后步骤和报告/网表输出。两者用途不同，不能混为同一个综合 runtime。

## 8. 功能和性能验证

### 8.1 Directed regression

完整 C910 候选的关键回归结果如下：

| 回归目录 | 用途 | 结果 |
| --- | --- | ---: |
| `timing_candidate_corners` | averaging、widen/narrow、mask、slide 等 RVV corner | 32/32 PASS |
| `timing_candidate_corners_addrgen_mul` | 加入 AddrGen/VSMUL 修改后的同组 corner | 32/32 PASS |
| `timing_candidate_wait_complete_assert` | completion-mask 等价断言 | 32/32 PASS |
| `lane_req_queue_corners` | lane request FIFO | 32/32 PASS |
| `timing_candidate_regression` | FP div/nanbox 和重点 RVV 修复 | 6/6 PASS |
| `segment_queue_edge_eval` | segment EMUL/异常恢复边界 | 2/2 PASS |
| `timing_addrgen_align_segment` | 地址对齐和 segment 组合点 | 1/1 PASS |
| `timing_simd_mul_width_vsmul` | VSMUL 切片和 rounding | 1/1 PASS |

这些目录有重复的 32-case matrix，不能相加宣称为 138 个独立测试。正确表述是：完整候选在连续修改检查点上多次通过同一组 32 个 directed corner，并通过各修改对应的额外定向测试。

### 8.2 代表性能点

已记录的代表点在优化前后周期保持一致：

| Kernel | 配置 | 原 no-QBS cycles | 候选 cycles | 结论 |
| --- | --- | ---: | ---: | --- |
| AXPY | AVL=32 | 108 | 108 | 完全一致，`hw-cycles=50` 也一致 |
| AXPY | AVL=1024 | 1342 | 1342 | 无周期回退 |
| AXPY | AVL=4096 | 5179 | 5179 | 大规模持续流 A/B 完全一致 |
| DOTP | AVL=1024 | 1832 | 1832 | 无周期回退 |
| GEMM | m1, 4-row, N=32 | 12461 | 12461 | 无周期回退 |

这些点覆盖短流式、长流式、规约和矩阵计算，但不是全 benchmark sweep。因此结论应限定为“代表点未观察到性能回退”，不能替代完整 kernel sweep。

请求 FIFO 在空闲启动时会引入寄存边界，但已有控制和队列深度允许其与原有请求生命周期重叠。上述周期不变结果说明至少在代表点上没有转化为 task-cycle 损失。

AVL=4096 的补充 A/B 使用同一个 ELF，旧 RTL 和完整候选均报告 `Core Test *** SUCCESS ***`。除 `total_cycles=5179` 外，两边的 `total_rvv_cycles=5117`、`total_vector_insns=640`、`hw-cycles=5120`、IPC、lane utilization、request blocked 和 sequencer hazard 计数均完全一致。进一步逐字节比较得到：

```text
commit trace SHA-256:
51a95cba1ab518e839e9c1de855d8186f462d044f84d3ce8ccdf9601d4c6eef3

performance report SHA-256:
1f27e13fd5d10d5c68a56ae31ca2064646cce040ee72728bec3a73af999a483a
```

两边哈希分别一致，且日志中没有 assertion、fatal 或 test failure。实验文件保存在：

```text
/home/wangwy/openproject/ara_dsa_no_qbs_pulp_eval/hardware/
  timing_large_ab_axpy4096_20260824/old/
  timing_large_ab_axpy4096_20260824/full/
```

## 9. PULP div/sqrt 独立实验

PULP div/sqrt 不是完整 C910 候选综合的一部分。该实验用于判断 main 中较简单的 PULP 单元能否替换 no-QBS 的 C910 单元，并避免把 FPU 复杂度错误归因给 HDV 控制路径。

原 PULP 路径先补齐了 RDN、RUP、RMM、sticky 和 overflow 等语义，随后通过：

```text
verification/out/pulp_timing_candidate_corners_r2/summary.csv
32/32 PASS
```

测得延迟对比如下：

| 操作宽度/指标 | C910 | PULP |
| --- | ---: | ---: |
| EW16 divide latency | 12 cycles | 9 cycles |
| EW32 first/interval | 15/12 | 13/10 |
| EW64 first/interval | 22/19 | 23/20 |
| `vfdiv` 完整测试 | 基准 | PULP 快 10 cycles |
| `vfrdiv` 完整测试 | 基准 | PULP 快 15 cycles |
| `vfsqrt` 完整测试 | 基准 | PULP 快 6 cycles |

AXPY AVL=32、DOTP AVL=1024 和 GEMM m1/4-row/N32 的候选周期未变化。PULP 方向目前只完成 RTL 正确性和性能 A/B，尚未完成与完整候选同条件的 DC 综合，因此不能据此给出面积或 WNS 结论，也没有并入 no-QBS 完整 C910 候选。

## 10. 结果解释

### 10.1 已被证据支持的结论

1. 原始主要问题确实包含 dispatcher 到 sequencer 再反馈的长组合 request-ready-hazard 路径。加入非穿透边界后，最差路径迁移到 lane datapath。
2. 第二轮针对 lane FIFO、动态 hazard 行选择、SIMD 结果切片、SLDU shuffle 和 AddrGen 宽算术的重构有效降低了大面积负 slack。第一轮到完整候选的 TNS 减少约 82%，违例路径减少约 64%。
3. 关键路径再次迁移到 dispatcher 内部 overlap/EEW 更新，说明全局反馈和第一轮 lane datapath 已不再占据最差位置。
4. 完整候选的总面积没有随第二轮时序优化增加，反而比第一轮略降；时序改善不是以显著面积膨胀换取。
5. 当前 directed regression 和代表性能点没有发现语义错误或周期回退。

### 10.2 不能由当前实验单独证明的结论

1. 不能给每个 RTL hunk 分配独立 WNS/TNS 贡献，因为两轮内部均为累积修改，没有逐 hunk DC ablation。
2. 不能把完整候选与历史 no-QBS 的全部差值解释为 RTL 收益，因为综合脚本和 SDC 同时被对齐。
3. 不能声称达到 1 GHz closure。完整候选仍有 `-0.180 ns` WNS、`-1389.477 ns` TNS 和 14442 条 `clk_i` 违例。
4. 不能用 DC hold 数值判断 post-route hold 是否可收敛。
5. 不能仅凭当前五个代表配置断言全 workload 性能不变。

## 11. 当前剩余问题

### 11.1 Dispatcher overlap 到 EEW 状态路径

当前最差路径完全位于 dispatcher：

```text
overlap_reg_first_element_q
  -> overlap register/boundary decode
  -> EEW state update qualification
  -> eew_valid_q
```

下一轮应先从 `clk_i_max.tim` 的前 1000 条路径重新分类，确认该 cone 是孤立 top path 还是一组重复路径，再决定以下方案：

1. 把 overlap 修复结果和 EEW scoreboard commit 分为两个寄存阶段。
2. 预解码 affected-register mask，避免从 element index 到 32-entry EEW 状态形成串行比较链。
3. 将 current/boundary 两类更新拆成并行 one-hot mask 后在寄存器输入端合并。
4. 对重复高扇出 overlap 条件使用局部寄存或受控 replication。

不能直接再增加任意流水级。修改前必须核对 CVXIF completion、reshuffle replay、异常 flush 和队列 empty 的周期关系，并用 overlap/widen/narrow directed case 验证。

### 11.2 DC `CMD-025`

完整候选 `dc_final_candidate.console.log` 的 message summary 记录：

```text
CMD-025  Error  count=1
```

持久化日志只保留 message summary，没有找到该 error 的原始命令文本。DC 最终仍生成 `qor.rpt`、`clk_i_max.tim`、DDC、SDC 和 Verilog 网表。该问题不能被当作 RTL 编译失败，但在把网表用于 PnR 或 signoff 前必须重新捕获完整 DC transcript，定位 `CMD-025` 对应命令并确认其未跳过关键约束或输出步骤。

### 11.3 与 main_real 的差距

在相同 1 ns/0.15 ns setup 条件下，完整 no-QBS 候选仍比 main_real 差 `0.161 ns` WNS，且 TNS 和违例路径数高一个数量级。原因不是单一 no-QBS 模块：

1. no-QBS 保留更多 RVV 正确性状态，包括完整 register-group span、source lifetime、overlap/reshuffle 和恢复语义。
2. main dispatcher 和 lane request 边界更简单，但不能直接替换当前实现。
3. no-QBS 使用 C910 div/sqrt，main 使用 PULP；两者的物理影响尚未在同条件 DC 中隔离。
4. 当前 top path 已是 no-QBS 特有 dispatcher overlap/EEW cone，后续应优先解决该局部路径。

## 12. 向后续 QBS 分支移植的边界

完整 no-QBS 候选不能整文件覆盖到后续 QBS RTL。QBS 的 `VQBEXEC` 是阻塞式命令，并可能让 CVXIF 请求保持到 terminal response。盲目移植 dispatcher 的 `normal_req_issued_q`、WAIT_IDLE 或队列处理，可能导致 QBS 副作用重复、请求丢失或过早完成。

适合低冲突优先吸收的修改包括：

1. dispatcher 常数幂除法/余数替换。
2. lane request 非穿透 FIFO，但需重新验证 QBS 到 lane 的流量是否经过同一路径。
3. completion-only hazard running-mask 等价重写和断言。
4. VSMUL 固定切片。
5. SLDU 位宽和 logical zero-mask。
6. VLSU AddrGen 实际宽度对齐，但必须覆盖 QBS 新地址源。

需要高强度专门审核的修改包括：

1. dispatcher request FIFO 和 held-request 去重。
2. segment accepted/response 生命周期。
3. sequencer vid retirement 与 QBS command 生命周期交互。
4. overlap/EEW scoreboard 更新。

移植原则是逐 hunk 合并，并在每一类修改后先跑最小定向回归，再跑 QBS command/descriptor/engine 回归，不能用 no-QBS 文件整体替换 QBS 分支。

## 13. 复现和报告位置

### 13.1 综合启动

EDA 工具必须在许可证环境中运行。从 home 目录进入 EDA 容器后，在目标工作树的 `hardware` 目录执行：

```bash
cd ~
make enter_eda

cd /home/wangwy/openproject/ara_dsa_no_qbs_pulp_eval/hardware
make dc mc=1
```

DC 通常运行超过十分钟，应在独立目录后台启动并确认进程正常，不应持续轮询。

### 13.2 关键报告

第一轮：

```text
/home/wangwy/openproject/ara_dsa_no_qbs/backend/syn/ara_soc/v1-dc/
  dc_queuefix_aligned.console.log
  reports/qor.rpt
  reports/clk_i_max.tim
  reports/area.rpt
```

完整 C910 候选：

```text
/home/wangwy/openproject/ara_dsa_no_qbs_pulp_eval/backend/syn/ara_soc/v1-dc/
  dc_final_candidate.console.log
  reports/qor.rpt
  reports/clk_i_max.tim
  reports/area.rpt
  outputs/ara_soc_dc.ddc
  outputs/ara_soc_dc.sdc
  outputs/ara_soc_dc.v
```

main_real 参考：

```text
/home/wangwy/openproject/dc_ara_main_real/backend/syn/ara_soc/v1-dc/reports/
  qor.rpt
  clk_i_max.tim
  area.rpt
```

PULP directed regression：

```text
/home/wangwy/openproject/ara_dsa_no_qbs_round_full_eval/
  verification/out/pulp_timing_candidate_corners_r2/summary.csv
```

### 13.3 快速核对命令

```bash
sed -n '1,130p' backend/syn/ara_soc/v1-dc/reports/qor.rpt
sed -n '1,180p' backend/syn/ara_soc/v1-dc/reports/clk_i_max.tim
rg -n '^i_system[[:space:]]|^i_system/i_ara[[:space:]]|^i_system/i_ara/i_dispatcher[[:space:]]' \
  backend/syn/ara_soc/v1-dc/reports/area.rpt
```

## 14. 最终结论

no-QBS 时序优化已经把问题从跨 dispatcher、sequencer、lane 和 CVA6 的大范围反馈路径，收敛为 dispatcher 内部 overlap/EEW 状态更新路径。完整 C910 候选相对历史记录把 WNS 违例幅度降低约 80.5%，TNS 降低约 90.4%；在约束一致的第一轮到第二轮比较中，WNS 改善 `0.304 ns`，TNS 降低约 82%，总面积略降，代表性能点保持不变。

该结果证明结构性优化方向有效，但还不能称为 1 GHz closure。下一步应针对当前 `overlap_reg_first_element_q -> eew_valid_q` 路径做一次有明确语义边界的局部重构，并重新审计完整 `clk_i` top-path 分布和 `CMD-025`。在这些问题完成前，当前网表适合继续工程评估，不应作为最终 signoff 网表。
