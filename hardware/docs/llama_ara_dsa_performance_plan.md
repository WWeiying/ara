# llama.cpp 典型场景的 Ara 性能观测与 DSA 设计方案

## 1. 目标与方法

本方案面向 Qwen2.5 Q4_K_M 在 `llama.cpp/ggml` 中的真实量化线性层，目标不是只让一个人工点积变快，而是建立以下闭环：

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
- `lane_active_cycles`：至少一个 lane 的 ALU/MFPU operand handshake 活跃的周期数。
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
lane_active_ratio   = lane_active_cycles / cycles
req_blocked_ratio   = req_blocked_cycles / cycles
```

### 4.2 向量操作类别

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

### 4.3 向量访存和 AXI

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

### 4.4 队列和在飞请求

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

### 4.5 阻塞活动签名

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
- 32×4 内核的 lane active ratio 和 MFPU operand fires 是否提升；
- M 继续增大时，是算力、寄存器压力还是内存带宽先饱和。

## 6. 用数据选择硬件方向

### 6.1 先做融合低比特指令的条件

只有同时满足以下现象，才优先设计 fused unpack-dot：

- `bitwise_count + shift_count + narrow_count` 在 `matmul` 请求中占比高；
- 多输出 RVV 已经减少归约，但解包请求仍占关键路径；
- AXI 流量接近理论值，说明主要问题不是布局浪费；
- queue 和 operand block 表明现有 ALU/MFPU 间的数据传递限制吞吐。

候选语义应是“从标准 Q4_K/Q8_K block 中提取并累加一个可定义的子块”，而不是把完整 GGML 数据结构硬编码进一条不可复用的大指令。指令需明确：输入打包格式、带符号规则、累加宽度、尾部处理、异常与精确状态。

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
- lane active ratio 低但 backend busy 高；

则应先优化 repack、burst、双缓冲或局部 SRAM/TCM，而不是增加 MAC。局部存储需要分别统计 weight bytes、activation bytes、metadata bytes、scratchpad hit/miss 和 DMA stall，不能只看总 AXI 字节。

## 7. 建议的 DSA 分阶段实现

### 阶段 A：建立不含新指令的基线

- 跑完六个真实线性层的阶段计数。
- 比较 Q4 Decode、Q4 Prefill、Q6 Decode、Q6 Prefill。
- 验证 32-output repack 是否减少归约和 activation 流量。
- 以输出 golden 保证所有布局变化保持数值语义。

### 阶段 B：定义最小融合运算

- 只融合数据解包和 widening MAC 中反复出现、语义稳定的部分。
- 先做 intrinsic/inline assembly 和指令级 directed test。
- 保留标准 RVV fallback。
- 用 `matmul` phase 证明请求数、ALU operand traffic 或周期确实下降。

### 阶段 C：多输出 tile engine

- 增加 tile descriptor 或短命令接口。
- 让同一 activation block 服务 4/8/16/32 个输出。
- 逐步扩大 N tile，依据寄存器、SRAM 和带宽数据选择最终宽度。
- 不直接假设 `n32` 对 Ara 最优；进迭时空的宽度只是参考点。

### 阶段 D：Prefill 多输入支持

- 在同一 tile engine 上增加 M=2/4。
- 比较 activation pack 成本与 weight tile 复用收益。
- 若 pack 成本显著，应将布局转换移到上游或由 DMA/DSA 融合完成。

### 阶段 E：GGML backend 接入

- 模型加载时 repack 权重并保存 Ara buffer type。
- runtime 根据 M/N/K、量化类型和硬件能力选择 kernel。
- unsupported shape/type 回退标准 RVV。
- 保持 Decode 与 Prefill 共用数据布局和调度框架。

## 8. 后续 DSA 自身必须增加的计数器

DSA RTL 出现后，应在其接口和内部补充严格事件计数：

- `dsa_cmd_valid_cycles/dsa_cmd_fire_count/dsa_cmd_blocked_cycles`。
- `dsa_busy_cycles/dsa_tile_count/dsa_k_block_count`。
- `dsa_useful_mac_count`，按实际执行且属于架构结果的 MAC 定义。
- `dsa_weight_bytes/dsa_activation_bytes/dsa_metadata_bytes/dsa_output_bytes`。
- `dsa_input_wait_cycles/dsa_output_wait_cycles`。
- `dsa_scratchpad_hit_count/miss_count`，若加入局部存储。
- `dsa_dma_read_bytes/write_bytes/outstanding_max`，若加入 DMA。
- `dsa_accumulator_spill_count`，判断 tile 是否超过本地累加容量。

这些计数器应在接口定义时一并设计。特别是 `useful_mac_count` 和各类 byte counter，必须以明确握手或实际执行事件为准，不能由峰值吞吐乘周期估算。

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

阶段 CSV 一行对应一个 phase，并自动给出 `req_per_cycle`、`elements_per_cycle`、`lane_active_ratio`、`avg_queue_occ`、`avg_inflight` 和 `avg_read_outstanding`。分析时应始终保留原始计数，避免只凭归一化比例下结论。
