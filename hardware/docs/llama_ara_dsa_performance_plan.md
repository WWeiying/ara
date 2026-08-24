# llama.cpp 典型场景的 Ara 性能观测与 DSA 设计方案

## 1. 目标与方法

本方案以 Qwen2.5 Q4_K_M 的真实量化线性层为第一组测量对象，并以 Q3_K、Q5_K、Q6_K
和 Q8_0 模型中的真实算子切片检查格式扩展性；硬件研究边界是
`llama.cpp/ggml` 的块量化 `MUL_MAT` 路径，不绑定单个模型或固定 shape。目标不是只让
一个人工点积变快，而是建立以下闭环：

```text
真实模型数据与算子形状
  -> 分阶段性能观测
  -> 判断软件布局、RVV 后端或硬件资源的主瓶颈
  -> 选择指令语义和 DSA 粒度
  -> RTL 实现
  -> 相同输入、golden 和计数器下重新验证
```

当前第一批代表点是 Qwen2.5-1.5B layer 0 的六个真实量化线性算子：

- Decode：`attn_q`、`ffn_gate`、`ffn_down`。
- Prefill：`attn_q`、`ffn_gate`、`ffn_down`。
- `attn_q` 和 `ffn_gate` 使用 Q4_K 权重；`ffn_down` 使用 Q6_K 权重。
- 输入、权重、输出和 golden 均来自真实 QEMU/llama.cpp 捕获，而不是随机生成。

六点用于高成本 RTL 性能测量，不是硬件支持列表。完整软件数据集还包括 Attention
Q/K/V/O 和 FFN gate/up/down 在 Decode/Prefill 下的 14 个量化线性点；格式、M/N/K tail
和第二模型的通用性由更小的 directed sweep 验证。

### 1.1 技术实施大纲

LLM 的主要计算负载是量化矩阵计算：Decode 以矩阵乘向量（GEMV）为主，Prefill 以矩阵乘矩阵（GEMM）为主。Ara 上的 DSA 优化按以下顺序推进：

1. 用真实 Qwen2.5 数据建立 Q4_K/Q6_K GEMV、GEMM 的标准 RVV 基线。
2. 先完成面向 `VLEN=1024` 的软件优化，包括权重 repack、多输出 GEMV 和多输入 GEMM，确定标准 RVV 的性能上限。
3. 利用分阶段计数器判断主要开销来自量化解包、低位宽乘加、归约、缩放、重复读取还是内存等待。
4. 冻结 format profile、storage layout、M/N/K tile、tail、capability 和 fallback 契约，不把模型名称或固定 shape 固化进 ISA。
5. 先在 standalone profile engine 中验证 decoder/dot/correction/FP update 的逐 block 正确性和吞吐，不把它伪装成系统级 speedup。
6. 增加 tagged block request、metadata-bound token 和 command-local accumulator，使压缩数据直接从 VLSU 进入 QBS。
7. 使用统一 K-block-major controller，由 M/N shape 推导 activation/weight consumer count 和释放时刻，再逐级打开复用与 weight ping-pong。
8. 将阻塞式 `ara.qbexec` 接入 Ara sequencer、MMU、fault containment、atomic commit 和正常 RVV destination path；不支持的 profile、layout 或 shape 继续走标准 RVV。
9. 在 ggml 模型加载阶段执行权重 repack，运行时依据量化类型与 M/N/K 选择 RVV 或 DSA kernel。
10. 使用相同真实输入和 golden 比较原始 RVV、`VLEN=1024` RVV、多输出 RVV 与 DSA，并同时报告周期、总线流量、利用率、面积和功耗。

首个接入目标仍是 `Q4_K x Q8_K` 多输出 Decode GEMV，但它必须使用已经冻结的公共命令和
profile 接口，其核心路径为：

```text
读取量化块 -> 解包 -> 低位宽乘加 -> 多输出累加 -> 缩放/反量化 -> 写回
```

完成该路径并确认收益后，在相同框架中补充 Q6_K 和 Prefill GEMM，再通过新增 profile
覆盖 Q3_K、Q5_K、Q8_0 与 Q4_0。Q4 是实施顺序，不是把首版 ISA 定义为 Q4 专用后再
重新设计一次。

### 1.2 DSA 定位与扩展契约

详细 ISA 和微结构定位见 [ara_llm_kquant_dsa_proposal.md](ara_llm_kquant_dsa_proposal.md)。
性能计划使用同一组边界：

- **format profile** 定义 block payload、metadata、scale 和 correction 数学语义；
- **storage layout** 定义 row-major 或 repacked block 的地址排列，不改变数学格式；
- **execution mapping** 定义 M/N/K tile、统一 K-block-major schedule 和 shape-derived token
  lifetime/reuse，不进入格式编号；
- 逻辑矩阵尺寸由软件循环平铺，物理 micro-tile 和 4-lane/VLEN=1024 参数不进入 ISA；
- Q3_K/Q4_K/Q5_K/Q6_K/Q8_0/Q4_0 已作为独立 profile 实现；Q2_K 仍是需要新增 decoder
  的自然扩展，IQ/MXFP 只共享块流基础设施，不声称免费支持；
- unsupported profile、layout、K 对齐或 tile 必须明确回退到标准 RVV。

这套契约先于 RTL 冻结。后续软件优化、QBS-Serial/Reuse/Full 消融都必须使用相同输入、
输出、tile 语义和 fallback 条件，防止为某个性能点重新定义问题。

## 2. 从进迭时空实现得到的约束

进迭时空的主要优化层级不是单独替换 `ggml_vec_dot_q4_K_q8_K()`，而是替换完整的 `GGML_OP_MUL_MAT` 执行路径：

1. 模型加载时对权重进行专用布局转换。
2. 运行时只量化一次 activation。
3. 按 M/N/K 对计算分块。
4. 一个内核同时产生多个输出，复用 activation 和权重元数据。
5. Decode 使用 M=1 的多输出 GEMV；Prefill 使用多输入、多输出 GEMM。
6. 专用矩阵指令、TCM 和线程调度位于这一完整路径内部。

因此 Ara 的研究顺序应为：

```text
单输出 RVV 基线
  -> VLEN=1024 单输出实现
  -> 多输出 RVV + repack
  -> 定位多输出后的剩余瓶颈
  -> 再确定 fused dot、tile 指令或数据搬运 DSA
```

单输出优化仍有价值，因为它给出正确性基线并揭示解包、乘法和归约的单行成本；但它不能代表最终 Decode GEMV 的最优执行粒度。

## 3. 必须分开的执行阶段

真实 benchmark 现在使用 `hw_cnt_en_o[15:8]` 传递阶段编号，bit 0 仍保留原有硬件计数使能语义：

| phase | 编号 | 严格边界 |
| --- | ---: | --- |
| `quantize` | 1 | FP32 activation 转换为 Q8_K block |
| `pack` | 2 | Prefill Q4 路径把四个 Q8_K 输入重排成 `block_q8_Kx4` |
| `matmul` | 3 | Q4 多输出 GEMV/GEMM，或当前 Q6 单输出循环 |
| `total` | 0 | 上述阶段所在的完整计时区间 |

阶段切换通过测试程序写 SoC 控制寄存器实现，不新增 ISA，也不进入 Ara 综合数据路径。阶段写入及其 fence 会带来少量边界开销，因此：

- 软件打印的 `quantize_cycles/pack_cycles/matmul_cycles` 用于报告阶段延迟；
- RTL phase row 用于归属向量请求、AXI、队列和阻塞活动；
- 不应要求三个 phase row 的周期与 `compute_cycles` 在每个周期上严格相加相等。

## 4. 当前已实现的仿真计数器

计数器位于 `hardware/tb/llm_perf_monitor.sv`，仅观测现有 RTL 信号。它不进入综合，不改变面积、时序、队列容量或功能行为。每次 benchmark 结束生成：

```text
llm_perf_report_<TESTCASE>.log
```

文件包含 `total/quantize/pack/matmul` 四行。无实际工作的阶段保持为 0。

### 4.1 时间和请求投放

- `cycles`：该观测区间的周期数。
- `backend_busy_cycles`：Ara sequencer 非 idle 的周期数。
- `lane_active_cycles`：至少一个 lane 持有尚未完成的向量指令的周期数。该计数包含执行、等待操作数和等待写回等状态，是在飞占用而非计算利用率。
- `req_valid_cycles`：dispatcher 对 sequencer 保持有效请求的周期数。
- `req_fire_count`：dispatcher 与 sequencer 完成握手的请求数。该数不包含只在 CVA6 内完成的 `vset*`。
- `req_blocked_cycles`：请求有效但 sequencer 未接收的周期数。
- `vector_element_count`：每个已接收请求的 `vl` 之和。它是指令覆盖的架构元素数，不等于实际 lane micro-op 数。
- `retired_inst_count`：CVA6 提交的全部指令数。
- `retired_vector_inst_count`：提交时归属于 accelerator/vector FU 的指令数，包含 `vset*`。
- `retired_scalar_inst_count`：前两者之差，用于观察循环、地址和阶段控制开销。

推荐派生：

```text
req_per_cycle       = req_fire_count / cycles
elements_per_cycle  = vector_element_count / cycles
lane_any_inflight_ratio = lane_active_cycles / cycles
req_blocked_ratio   = req_blocked_cycles / cycles
```

旧 CSV 字段 `lane_active_ratio` 为兼容已有数据而保留，其严格含义与
`lane_any_inflight_ratio` 相同，不能解释为 ALU、MFPU 或全部 lane 的真实计算利用率。

### 4.2 Lane 执行和结果写回

以下计数直接来自功能单元的执行或结果握手，不由“指令仍在飞”近似：

- `lane_inflight_slot_cycles`：逐周期活跃 lane 数之和；一个周期四个 lane 均有在飞指令时累加 4。
- `compute_active_cycles`：至少一个 lane 的 ALU、整数乘除或 FP pipeline 真正发射微操作的周期数。
- `compute_lane_slot_fires`：每周期至少发射一个计算微操作的 lane 数之和；同一 lane 同周期 ALU 和 MFPU 都发射时仍只计一个 lane slot。
- `compute_unit_lane_fires`：所有 ALU/MFPU 执行发射数之和；同一 lane 同周期两个单元均发射时计 2。
- `alu_exec_active_cycles/alu_exec_lane_fires`：ALU 至少一个 lane 发射的周期数，以及所有 lane 的64-bit ALU微操作发射总数。事件为 `valu_valid`，此时完整操作数和必要 mask 已经就绪，ALU 正在计算。
- `mfpu_exec_active_cycles/mfpu_exec_lane_fires`：MFPU 至少一个 lane 发射的周期数，以及整数乘法、整数除法和 FP pipeline 输入握手的总数。
- `int_mul_exec_lane_fires`：整数乘法流水线的 `valid && ready` 输入握手数，包括普通乘法与整数 MAC。
- `int_mac_exec_lane_fires`：上述整数乘法发射中操作为 `VMACC/VNMSAC/VMADD/VNMSUB` 的子集。
- `int_mac_element_count`：整数 MAC 发射时根据实际 `issue_be` 和该 MFPU 请求的有效结果 SEW 计算的 MAC 元素数，已经排除 tail、predicate 和 `vstart` 抑制的元素。对 widening MAC，Ara 在 dispatcher 中已把 `vtype.vsew` 提升为结果宽度，因此该计数按每周期真正被 MFPU 接受的 widened result element 计数，不把原始窄源操作数个数误当成当前流水线容量。
- `int_div_exec_lane_fires/fp_exec_lane_fires`：整数除法与 FP pipeline 的真实输入握手数。
- `alu_result_lane_fires/mfpu_result_lane_fires`：ALU/MFPU 结果请求被 VRF 写回端接受的 lane 次数；mask-unit 内部结果不属于 VRF 写回，不计入该项。
- `alu_result_active_bytes/mfpu_result_active_bytes`：上述成功写回结果中 byte enable 置位数之和。

推荐派生：

```text
lane_inflight_slot_utilization = lane_inflight_slot_cycles / (cycles * NrLanes)
compute_active_ratio           = compute_active_cycles / cycles
compute_lane_utilization       = compute_lane_slot_fires / (cycles * NrLanes)
alu_issue_utilization          = alu_exec_lane_fires / (cycles * NrLanes)
mfpu_issue_utilization         = mfpu_exec_lane_fires / (cycles * NrLanes)
int_mac_issue_utilization      = int_mac_exec_lane_fires / (cycles * NrLanes)
int_mac_elements_per_cycle     = int_mac_element_count / cycles
int_mac_vector_fill_ratio      = int_mac_element_count / int_mac_element_capacity
int8_equivalent_mac_throughput_ratio = int_mac_element_count / (cycles * NrLanes * 8)
compute_result_active_bytes_per_cycle =
    (alu_result_active_bytes + mfpu_result_active_bytes) / cycles
```

`compute_lane_utilization` 是通用的“lane 正在真实发射计算”比例；
`int_mac_issue_utilization` 是整数 MAC 流水线 lane-slot 利用率；
`int_mac_vector_fill_ratio` 只考察已经发射的 MAC lane-slot 内有多少元素有效；
`int8_equivalent_mac_throughput_ratio` 将全部有效 MAC 元素按每个64-bit lane 每周期8个
INT8 元素归一化，仅用于比较潜在 INT8 点积硬件的等效吞吐，不能解释为当前混合 SEW
MFPU 的物理利用率。原始计数还按 EW8/EW16/EW32/EW64 分别记录发射次数和有效元素数，
用于说明工作负载实际使用的数据宽度。

### 4.3 向量操作类别

以下计数均以 Ara request fire 为事件，统计后端实际接受的请求：

- `load_count/store_count`：全部向量 load/store。
- `load_unit_count/load_strided_count/load_indexed_count`：三类 load。
- `store_unit_count/store_strided_count/store_indexed_count`：三类 store。
- `bitwise_count`：`vand/vor/vxor` 类请求。
- `shift_count`：普通及定点 shift；不包含 narrowing shift。
- `int_alu_count`：普通、饱和及 averaging 整数算术请求。
- `int_mul_count/int_mac_count`：整数乘法与乘加请求。
- `int_widen_mul_count/int_widen_mac_count`：其中 `cvt_resize=CVT_WIDE` 的子集。它们与前两个计数重叠，不是额外指令。
- `int_reduction_count/fp_reduction_count`：整数和浮点归约。
- `narrow_count`：`vnclip/vnclipu/vnsrl/vnsra`。
- `fp_arith_count`：非归约浮点运算及转换。
- `permute_count`：gather、compress 和 slide。
- `mask_count`：比较、mask logical、mask scan、iota、popcount/first 等。
- `scalar_move_count`：vector-scalar move。
- `other_count`：未落入上述互斥主类别的请求。

注意：`bitwise_count` 和 `shift_count` 只能说明低比特解包相关操作的活动强度，不能严格命名为 “Q4 unpack 指令数”。相同操作也可能服务于量化、地址处理或其他算法。

### 4.4 向量访存和 AXI

- `unit_load_span_bytes/unit_store_span_bytes`：已接收 unit-stride 请求的 `vl × element_bytes × (nf+1)` 之和。
- `masked_mem_count`：`vm=0` 的向量访存请求数。
- `axi_ar_count/axi_aw_count`：AXI 地址握手数。
- `axi_ar_bytes/axi_aw_bytes`：由 `len/size` 解码出的总 burst 字节数。
- `axi_r_beat_count/axi_w_beat_count`：完成握手的数据 beat 数。
- `axi_r_bus_bytes`：R beat 数乘总线字节宽度，是总线传输槽位字节数。
- `axi_w_useful_bytes`：W channel 上置位 strobe 的字节数。
- `axi_b_count`：写响应握手数。
- `axi_*_stall_cycles`：对应 channel valid 且未 ready 的周期数。
- `read_outstanding_occ_sum/read_outstanding_max`：AR transaction 发出到 RLAST 返回之间的读事务占用积分和峰值。

`unit_*_span_bytes` 是架构访问跨度，不是 masked load/store 的精确有效字节；`axi_r_bus_bytes` 是总线槽位流量，也不等于 cache line 中被算法真正使用的字节。两者结合使用可以识别过取数和布局浪费。

### 4.5 队列和在飞请求

- `queue_occ_sum/queue_occ_max`：七类 VFU instruction queue 占用总和的周期积分和峰值。
- `queue_full_cycles`：至少一个 VFU queue 达到容量的周期数。
- `inflight_occ_sum/inflight_occ_max`：sequencer `vinsn_running` 的周期积分和峰值。
- `lane_alu_operand_fires/lane_mfpu_operand_fires`：各 lane ALU/MFPU operand 端口握手数。

推荐派生：

```text
avg_queue_occ  = queue_occ_sum / cycles
avg_inflight   = inflight_occ_sum / cycles
```

operand handshake 反映执行端口消费输入的活动量，不等价于完成的向量元素数或 MAC 数。

### 4.6 阻塞活动签名

- `queue_resource_block_cycles`：请求未接收且目标 VFU queue 不能 issue。
- `no_vid_block_cycles`：没有可分配 vector instruction ID。
- `lane_desync_block_cycles`：lane 完成状态不同步造成的门控。
- `operand_block_cycles`：至少一个 lane operand requester 未 ready。
- `mask_block_cycles`：mask requester 未 ready。
- `slide_block_cycles`：slide requester 未 ready。
- `hazard_block_cycles`：当前 `multi_reader_war` 条件参与阻止请求推进。
- `scalar_result_wait_cycles`：sequencer 已准备接收 vector-to-scalar 结果，但结果尚未有效。

这些信号可能在同一周期同时成立，只能作为瓶颈活动签名，不能相加后称为总 stall breakdown。要构造严格互斥的 stall breakdown，需要在 sequencer 内增加单一优先级 reason 编码；在确定论文或 DSA 接口确实需要之前，不应为统计目的改动关键组合路径。

## 5. 第一轮实验矩阵

### 5.1 需要比较的实现

同一份真实输入和 golden 下至少比较：

1. upstream 风格单输出 RVV。
2. 当前 VLEN=1024 单输出 RVV。
3. 当前 32-output repacked GEMV。
4. 当前 32×4 repacked GEMM。
5. 后续候选 DSA。

每组必须使用相同的 K、输出行数、输入行数和量化格式。不能拿单个 block dot 与完整线性层直接比较 speedup。

### 5.2 Decode 重点

Decode 的 M=1，优先观察：

- activation 是否只量化一次；
- `matmul` 中 Q4/Q6 权重总线流量是否接近理论下限；
- `int_reduction_count` 和 vector-to-scalar 等待是否随输出行数线性增长；
- 多输出实现能否降低 activation 重复读取和归约次数；
- `avg_read_outstanding` 是否足以覆盖存储延迟；
- 多输出后 `queue_resource_block` 或 MFPU operand 压力是否成为新瓶颈。

### 5.3 Prefill 重点

Prefill 的 M>1，优先观察：

- `pack_cycles` 相对总周期的比例；
- 同一 weight tile 是否被多个输入复用；
- 单位输出的 `axi_r_bus_bytes` 是否下降；
- 32×4 内核的 `compute_lane_utilization`、`int_mac_issue_utilization` 和实际 MAC 元素吞吐是否提升；
- M 继续增大时，是算力、寄存器压力还是内存带宽先饱和。

### 5.4 RTL 快速相对评估集

完整 `M=15` Prefill 和 Q6_K FFN-down 在 RTL 仿真中的墙钟时间过长。日常 DSA
迭代使用下列真实数据子矩阵，完整规模只用于最终确认：

| case | M | N（输出行） | K | 权重量化 | 保留机制 |
| --- | ---: | ---: | ---: | --- | --- |
| `decode_attn_q_eval` | 1 | 1536 | 1536 | Q4_K | 完整 Attention-Q Decode GEMV |
| `decode_ffn_gate_eval` | 1 | 4096 | 1536 | Q4_K | 32-output Decode GEMV 与 FFN 宽输出 |
| `decode_ffn_down_eval` | 1 | 256 | 8960 | Q6_K | 完整长 K、Q6 解包与单输出归约 |
| `prefill_attn_q_eval` | 4 | 1536 | 1536 | Q4_K | 一个完整 `32x4` GEMM 输入 tile |
| `prefill_ffn_gate_eval` | 4 | 4096 | 1536 | Q4_K | 32x4 GEMM 与较宽 FFN 输出 |
| `prefill_ffn_down_eval` | 4 | 64 | 8960 | Q6_K | 长 K、四输入及两个 32-row 输出组 |

裁剪只作用于彼此独立的输入 token 和输出行，K、量化 block、scale/metadata、内核
控制流和真实数值均保持不变。Q4_K 的 N 始终为 32 的整数倍，Prefill 的 M 固定为
4，以完整覆盖当前 repacked `32x4` 路径。生成器先校验完整 capture，再分别裁剪：

- 权重取原始矩阵前 N 行，然后执行 Q4_K x32 repack；
- activation 取前 M 个完整 K 向量；
- golden 按原始 N stride 对每个 token 独立提取前 N 个结果，不能直接截取文件前缀；
- `provenance.json` 保存原始 `capture_rows/capture_inputs`、评估 slice、字节数与 SHA-256。

该评估集用于比较相同 shape 下的 `cycles/output`、`cycles/MAC`、总线字节、请求数、
利用率和 DSA speedup。它不应直接替代完整模型端到端延迟；在 DSA 方案确定后，仍需
用至少一个完整规模点检查固定开销和线性外推。

## 6. 用数据选择硬件方向

### 6.1 先做融合低比特指令的条件

只有同时满足以下现象，才优先设计 fused unpack-dot：

- `bitwise_count + shift_count + narrow_count` 在 `matmul` 请求中占比高；
- 多输出 RVV 已经减少归约，但解包请求仍占关键路径；
- AXI 流量接近理论值，说明主要问题不是布局浪费；
- queue 和 operand block 表明现有 ALU/MFPU 间的数据传递限制吞吐。

候选算术语义应是“从标准 Q4_K/Q8_K block 中提取并累加一个可定义的子块”，而不是把
完整 GGML 数据结构硬编码进一条不可复用的大指令。冻结方案先把该语义实现为 QBS
profile engine 的内部接口和 standalone 验证边界，不单独发布一个仍需软件显式搬运、
解包和归约的 fused-dot opcode。

### 6.2 先做多输出 tile DSA 的条件

若单输出的归约和重复 activation 读取占主导，而 32-output RVV 明显改善，则优先做 tile 级计算：

- 一次 request 描述多个输出行和一个 K block；
- activation 在 DSA 内部广播或缓存；
- 每个输出保持独立的 INT32/FP32 accumulation；
- 到 tile 结束才执行缩放和写回；
- Decode 使用 M=1，Prefill 支持 M=2/4 的同一接口。

这一路径更接近进迭时空的 `m1×n32` 和 `m4×n32`，通常比只加一条单输出 dot 指令更能改变完整 `GGML_OP_MUL_MAT` 的执行效率。

### 6.3 先做数据搬运和局部存储的条件

若多输出后：

- `axi_r_bus_bytes` 仍明显高于理论权重和 activation 流量；
- AR stall 高或 outstanding 深度不足；
- `compute_lane_utilization` 低但 `backend_busy_cycles/cycles` 高；

则应先优化 repack、burst、两个有序 outstanding、weight ping-pong 或 block-buffer banking，
而不是增加 MAC。需要分别统计 weight、activation、descriptor、output bytes、block loads/
consumer uses 和 read-engine stall，不能只看总 AXI 字节。

### 6.4 当前冻结选择

现有数据同时表现出细粒度解包/归约开销、跨输出/输入复用机会以及普通 RVV 请求和 VRF
流量膨胀，因此 v1 不在上述三条中只选一条。冻结方案以一个阻塞式 `ara.qbexec` 组织完整
command tile：profile engine 解决压缩域算术，shape-derived schedule 解决 M/N 复用，
VLSU block stream 和 weight ping-pong 解决供数。三者使用同一 opcode、descriptor、
numerical contract 和 reference；`QBS-Serial -> QBS-Reuse -> QBS-Full` 只逐级打开内部
机制，用于分别归因。

## 7. 建议的 DSA 分阶段实现

### 阶段 A：建立不含新指令的基线

- 跑完六个真实线性层的阶段计数。
- 比较 Q4 Decode、Q4 Prefill、Q6 Decode、Q6 Prefill。
- 验证 32-output repack 是否减少归约和 activation 流量。
- 以输出 golden 保证所有布局变化保持数值语义。

### 阶段 B：冻结 profile/layout/tile 契约

- 明确定义 Q4_K/Q6_K weight profile、Q8_K activation profile 和支持的 storage layout。
- 定义 M/N/K tile、tail、capability negotiation 和标准 RVV fallback。
- 用 C/Spike functional model 跑 format、shape 和 negative-path directed test。
- profile/layout/execution 三层冻结后，性能实现不得修改其数学语义。

### 阶段 C：Standalone profile engine

- 在独立 unit-test top 中实现 Q4/Q6 profile decoder、32-pair dot、correction、FP update
  和 accumulator，输入直接使用完整 native block。
- 逐级比较 decoded quant、group partial、INT32 subtotal、逐 block FP update 和最终 result；
  单独报告 pair/cycle 与 queue stability，不把它作为完整 GGML kernel 的系统级 speedup。
- 保留相同 numerical contract 和 golden，不把软件 repack 收益计入硬件贡献。

### 阶段 D：QBS block-stream engine

- 增加 descriptor-driven `ara.qbinfo/ara.qbexec`、tagged subrequest、token assembly 和
  command-local accumulator；不引入 `vqbset` 或跨命令隐藏状态。
- 让 compressed payload/metadata 绕过普通 VRF 中间表示，同时复用 Ara MMU、异常和提交域。
- 先完成 Q4 Decode，再以同一公共路径加入 Q6 profile。

### 阶段 E：跨 shape 复用与 GGML backend

- Decode 和 Prefill 使用同一 K-block-major controller；activation 跨 N microtile 复用，weight
  跨 active M context 复用，范围和释放时刻只由 command shape 推导。
- 模型加载时按受支持 layout 决定是否 repack，并保存 Ara buffer type。
- runtime 根据 M/N/K、profile、layout 和 capability 选择 QBS 或 RVV kernel。
- 用七类线性层、M/N/K tail、第二模型和 unsupported case 验证框架边界。

## 8. QBS 自身计数器

当前 `QBS_PERF` 已按命令导出：

- terminal outcome、`busy_cycles` 和十类严格互斥的 `phase_*_cycles`；十项之和必须等于
  `busy_cycles`。
- logical range、translation、AR/R handshake、有效 payload byte 和 R backpressure。
- `read_outstanding_occ_sum/max/full_cycles`，严格跟踪 AR 到对应 RLAST 的两个有序槽位。
- weight/activation byte、tile、useful pair、pair capacity 和 dot active cycle。
- FP update table 占用、uop issue、accumulator update、commit group 和 commit backpressure。
- `weight_prefetch_wait_cycles`，表示当前 tile 已结束但下一 weight bank 尚未完整的等待。

这些计数器均以明确握手、状态或实际执行事件为准，不能由峰值吞吐乘周期估算。汇总器会
拒绝 phase 漏计、outstanding 超过 2、占用积分越界和 prefetch wait 逃逸出 weight phase 的
日志。尚未单独导出 block load/consumer-use 与 correction-slot stall，因此不得由 byte/tile
近似命名为严格复用率或 correction stall。严格定义与派生公式以
[QBS-Ara 方案第 6.10 节](ara_llm_kquant_dsa_proposal.md#610-性能计数器与严格口径)为准。

## 9. 使用方法

重新编译并运行某个真实算子后，除原有 `perf_report_*.log` 外会得到 `llm_perf_report_*.log`。汇总命令为：

```bash
cd /home/wangwy/openproject/ara_dsa/hardware
make llama_real_metrics_sum \
  metrics_log=sim_l2_16m/llm_perf_report_llama_qwen25_decode_attn_q.log \
  output=llama_qwen25_decode_attn_q.metrics.csv
```

原有整体结果仍使用：

```bash
make llama_real_sum \
  run_log=sim_l2_16m/run.vcs.log \
  perf_log=sim_l2_16m/perf_report_llama_qwen25_decode_attn_q.log \
  output=llama_qwen25_decode_attn_q.result.csv
```

阶段 CSV 一行对应一个 phase，并自动给出请求吞吐、在飞占用、真实计算发射、整数 MAC、结果写回、队列占用和 AXI outstanding 等派生比例。分析时应始终保留原始计数，避免只凭归一化比例下结论；尤其不能把兼容字段 `lane_active_ratio` 当成功能单元利用率。

快速评估集使用一份仿真模板和六个独立运行目录：

```bash
cd /home/wangwy/openproject/ara_dsa

# 列出、构建并在 Spike 上验证单个 eval case
make -C hardware llama_real_eval_list
make -C hardware llama_real_build case=decode_attn_q_eval
make -C hardware llama_real_spike case=decode_attn_q_eval

# RTL 只编译一次，然后六路独立后台运行
make -C hardware llama_real_eval_compile
make -C hardware llama_real_eval_parallel
make -C hardware llama_real_eval_status
```

最新运行目录由 `hardware/llama_eval_runs/latest` 指向。每个 case 独立保存
`run.vcs.log`、`perf_report_*`、`llm_perf_report_*`、`result.csv`、`metrics.csv`、
`exit_code` 和 `status`，不会复用或覆盖 `hardware/sim_l2_16m` 中的旧结果。

QBS-Full 使用独立模板和运行目录：

```bash
make -C hardware llama_qbs_eval_build
make -C hardware llama_qbs_eval_compile
make -C hardware llama_qbs_eval_parallel
make -C hardware llama_qbs_eval_status
make -C hardware llama_qbs_eval_sum
```

每点额外生成 `qbs_perf.csv` 和逐命令 `qbs_commands.csv`。当前 Full 在不改变 payload 和
数值结果的前提下，用 weight ping-pong 与两个同 ID、有序 read outstanding 覆盖下一
weight microtile 的取数；物理闭环不属于本阶段。

## 10. 多格式真实模型闭环

当前 Q3_K、Q5_K、Q6_K 和 Q8_0 闭环均取真实 Qwen2.5 Decode Attention-Q 的一个
activation 和前 256 个输出行。标准 RVV 与 QBS 使用相同 source weight、activation、
golden、K/N/M 和 capture commit，三类文件的字节数与 SHA-256 均由汇总器严格配对；八个
执行点全部 `PASS` 且 mismatch 为 0。离线 R4 repack 不计入周期。

| 格式 | KxNxM | RVV/QBS compute cycles | compute 加速 | RVV/QBS matmul cycles | matmul 加速 | 逻辑读取减少 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Q3_K | 1536x256x1 | 1,292,742 / 29,250 | 44.20x | 1,281,131 / 17,614 | 72.73x | 69.7% |
| Q5_K | 1536x256x1 | 2,023,388 / 33,386 | 60.61x | 2,011,748 / 21,750 | 92.49x | 59.9% |
| Q6_K | 1536x256x1 | 1,284,870 / 36,756 | 34.96x | 1,273,230 / 25,120 | 50.69x | 55.9% |
| Q8_0 | 896x256x1 | 553,720 / 31,986 | 17.31x | 548,583 / 26,923 | 20.38x | 48.1% |

四个代表点的 compute 和 matmul 几何平均加速分别为 35.68x 和 51.34x。它们衡量真实数据
算子切片相对当前标准 RVV 路径的差异，不是完整模型 token/s 加速。完整原始字段、数值误差、
provenance、QBS phase、outstanding、执行和提交计数位于 `hardware/format_closure.csv`，
可读摘要位于 `hardware/format_closure.md`。

微结构证据显示，Q3_K 的 dot-active ratio 为 70.7%，且没有 weight-prefetch wait；Q5_K
和 Q6_K 的该等待分别增至 15.2% 和 25.4%，说明较大 native block 使 weight stream 更容易
进入关键路径。Q8_0 每个输出包含 28 个 K block，其 profile-result-blocked 与 FP-input-blocked
活动分别为 23.3% 和 5.8%，而 dot-active ratio 仅 26.9%；该点首先受频繁 block 结果缩放/
累加及供数间隙限制，不应只扩大 dot array。所有格式的 pair utilization 均为 100%，且
FP-table-full 和 commit-backpressure 均为 0。上述阻塞信号允许同周期重叠，只作为活动签名，
不能相加为严格 stall breakdown。

## 11. GGML 整模型功能闭环

QBS 已接入 llama.cpp/GGML 的普通二维 `GGML_OP_MUL_MAT`。模型加载阶段根据 weight type
和硬件 capability 选择持久化 R4 repack；运行阶段根据 `M/N/K` 自动选择 M1 GEMV、M4
GEMM、N=32 分块以及 M/N 尾块，unsupported type、shape、alignment 或 capability 保留
原有 CPU/RVV fallback。Q3_K、Q4_K、Q5_K、Q6_K 使用 Q8_K activation，Q8_0、Q4_0
使用 Q8_0 activation。

整模型功能测试使用 Qwen2.5-1.5B-Instruct Q4_K_M，对普通 RVV 和 QBS emulation 分别执行
10-token prompt 与 2-token greedy generation。两者均正常退出且生成文本逐字节相同；QBS
trace 记录 Q4_K `gemv/gemm=8032/2656`，Q6_K `gemv/gemm=1360/432`，证明 decode、prefill
和两种真实模型 weight profile 均进入新路径。QEMU emulation 只验证 GGML 图、repack、分块、
dispatch 和数值语义，不能作为周期或 token/s 结果；RTL 性能结论仍以第 10 节严格配对的真实
算子切片为准。
