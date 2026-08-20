# llama.cpp Workload Extraction Plan for Ara DSA

> RTL 分阶段计数器、瓶颈判定方法和后续 DSA/指令扩展路线见
> `llama_ara_dsa_performance_plan.md`。本文档保留 workload、shape、数据来源和
> 当前软件 kernel 的说明，二者不要用同名指标表达不同语义。QBS-Ara 的格式、layout、
> tile、capability 和 fallback 边界见 `ara_llm_kquant_dsa_proposal.md`；本文列出的真实
> Qwen 点是评测样本，不等于硬件支持列表。

## 1. 目标与边界

本计划从 QEMU 中已经跑通的 Qwen2.5-1.5B-Instruct Q4_K_M 真实 `llama.cpp` 推理流程提取工作负载，用于后续功能验证、性能分析和指令扩展评估。提取对象分为三个层级：微内核、完整算子和 Decoder Transformer Block。每个层级内部的叶子项均保存独立输入、配置和 golden，可以单独选择运行；本阶段不在 Ara 上执行。

三个层级承担不同职责：

- 微内核用于定位某一类 RVV 指令序列的吞吐和依赖瓶颈。
- 完整算子用于评价量化、数据搬运、矩阵计算和缩放共同构成的实际计算路径。
- Transformer Block 用于评价多个算子之间的数据流、访存和执行重叠。

主要性能结论应来自完整算子和 Transformer Block。微内核只用于解释结果，不应单独代表 LLM 推理性能。

## 2. Level 1：RVV 微内核

### 2.1 动态激活量化

- 对象：`quantize_row_q8_K`
- 输入：FP32 activation row。
- 输出：`block_q8_K`，包括 INT8 数据、block scale 和辅助统计量。
- 覆盖行为：FP32 绝对值归约、scale 计算、舍入、限幅和 FP32 到 INT8 转换。
- 用途：测量完整量化线性层中 activation quantization 的独立成本。

### 2.2 Q4_K 与 Q8_K block dot

- 对象：`ggml_vec_dot_q4_K_q8_K` 和 Q4_K_M 混合量化实际使用的 `ggml_vec_dot_q6_K_q8_K`。
- 输入：一个或多个 `block_q4_K` 权重块和对应的 `block_q8_K` 激活块。
- 输出：FP32 dot-product partial sum。
- 覆盖行为：Q4 nibble 解包、scale/min 解码、Q4 与 Q8 整数乘法、INT32 归约和 FP32 缩放。
- 用途：定位低比特解包、整数点积和向量归约的开销。
- 定位：诊断微基准，不作为主要模型性能结果。

### 2.3 Decode 矩阵路径的覆盖边界

- 当前 RV64GCV 构建关闭 `Zvfh`，且 llama.cpp 的 RISC-V repack 选择器未为 VLEN=1024 启用专用 `16x1` Q4_K GEMV，因此真实 Decode 路径由动态 Q8_K 量化和重复调用 Q4_K/Q6_K vec-dot 的通用 `GGML_OP_MUL_MAT` 构成。
- 当前 replay 已为单输出 Q4_K x Q8_K vec-dot 增加 VLEN=1024 专用实现；这只优化每一行点积，不改变上述 `nrc=1` 矩阵循环，也不等同于 repacked 多输出 GEMV。
- 微内核层按 QEMU 实际调用的 `n`、`nrc` 和量化类型保存 vec-dot case；完整的单 token GEMV 行为由算子层 `Quantized Linear Decode` 覆盖。
- 不把未被当前构建选择的 repacked GEMV 实现标记为真实模型 case。若后续启用专用 repack 路径，应新增独立 capture hook 和对应 golden。

### 2.4 Prefill 矩阵路径的覆盖边界

- 当前构建同样未为 VLEN=1024 选择专用 repacked Q4_K GEMM。微内核层保存 Prefill 期间实际出现的动态量化和 vec-dot 形状，完整多 token 矩阵行为由 `Quantized Linear Prefill` case 覆盖。
- 这样划分避免把通用 matmul 内部的一次 dot 调用误称为完整 GEMM tile，也避免用人工输入替代真实 QEMU 数据。

## 3. Level 2：完整 GGML 算子

### 3.1 Quantized Linear Decode

- GGML 边界：一个完整的 `GGML_OP_MUL_MAT`。
- 数学形式：`Y_FP32 = W_Q * X_FP32`，其中 `W_Q` 保留 GGUF 中的真实 Q4_K 或 Q6_K 类型。
- 工作模式：`M=1`，对应单 token decode。
- 包含步骤：
  - FP32 activation 动态量化为 Q8_K；
  - Q4_K 权重或其 repacked layout 的读取；
  - Q4_K x Q8_K GEMV；
  - INT32 partial sum 归约；
  - block scale/min 处理；
  - FP32 输出写回。
- 用途：作为 Ara DSA decode 性能的主要算子级 benchmark。

### 3.2 Quantized Linear Prefill

- GGML 边界：一个完整的 `GGML_OP_MUL_MAT`。
- 数学形式：`Y_FP32 = W_Q * X_FP32`，并保留真实混合量化类型。
- 工作模式：`M>1`，对应多个 prompt token。
- 提取实例：保留 QEMU 实际调用尺寸，并补充若干不同 token batch 的规模点。
- 包含步骤：动态 Q8_K 量化、Q4_K GEMM、缩放、归约和 FP32 输出。
- 用途：作为 Ara DSA prefill 吞吐和矩阵数据复用的主要算子级 benchmark。

### 3.3 RMSNorm

- 输入：FP32 hidden-state vector 和 norm weight。
- 输出：归一化后的 FP32 vector。
- 包含步骤：平方和归约、均值与 `rsqrt`、逐元素缩放。
- 用途：评价归约、标量结果广播以及向量逐元素计算之间的协同。

### 3.4 RoPE

- 输入：Q/K tensor、position 和旋转参数。
- 输出：完成位置旋转后的 Q/K tensor。
- 包含步骤：偶奇通道重排、乘加和位置相关系数读取。
- 用途：评价规则重排、成对计算和小规模查表行为。

### 3.5 Self-Attention

- 子算子：`Q * K^T`、scale、causal mask、softmax 和 `P * V`。
- 当前回放边界：输入为 KV-cache 更新后的 K/V 视图，覆盖历史 K/V 读取和 Attention 数学路径，不把尚未独立抓取的 cache append 计为已验证行为。
- 输出：attention context。
- 用途：评价矩阵计算、归约、非线性操作和 KV-cache 访存组合形成的瓶颈。

### 3.6 FFN activation

- 数学形式：`SiLU(gate_proj(x)) * up_proj(x)`。
- 输入：gate projection 和 up projection 的 FP32 输出。
- 输出：送入 down projection 的 FP32 activation。
- 用途：评价非线性函数和逐元素乘法；与三个量化线性算子共同构成完整 FFN。

### 3.7 Residual add

- 对象：attention 或 FFN 输出与原 hidden state 的逐元素加法。
- 用途：覆盖完整 Block 中必须执行但计算密度较低的向量操作和额外内存流量。

## 4. Level 3：Decoder Transformer Block

### 4.1 Decode Block

- 输入：单 token hidden state、当前位置和已有 KV cache。
- 输出：一个 Decoder Block 处理后的 hidden state，并更新 KV cache。
- 完整路径：
  1. Attention RMSNorm；
  2. Q、K、V 三个 Q4_K quantized linear；
  3. RoPE；
  4. KV-cache 写入和读取；
  5. `Q * K^T`；
  6. scale、mask 和 softmax；
  7. `P * V`；
  8. attention output projection；
  9. residual add；
  10. FFN RMSNorm；
  11. gate projection 和 up projection；
  12. `SiLU(gate) * up`；
  13. down projection；
  14. residual add。
- 用途：评价单 token 生成阶段的端到端 Block 延迟、权重流量和 KV-cache 压力。

当前 `block/decode/all` 是上述计算路径的 ordered golden-isolated suite，而不是跨叶子传递中间结果和可变 KV-cache 的端到端状态机：各叶子读取真实 QEMU 边界输入并独立对照 golden。KV-cache append 是唯一明确保留的有状态缺口；补充该项需要同时保存更新前 cache、写索引、本轮 K/V 和更新后 cache，不能只根据 post-update view 构造循环论证式 golden。

### 4.2 Prefill Block

- 输入：多个连续 prompt token 的 hidden states 和初始或已有 KV cache。
- 输出：对应 token 的 Block 输出，并批量更新 KV cache。
- 算子组成：与 Decode Block 相同，但各 projection 使用 GEMM，attention 处理多个 query token。
- 用途：评价多 token 并行、矩阵复用、向量单元利用率和持续吞吐。

当前 `block/prefill/all` 与 Decode Block 采用相同的 golden-isolated 组织方式，适合逐项正确性和性能测量；它不等同于一个把回放输出逐步送入下一算子的独立模型执行器。

### 4.3 Block 规模选择

- 第一组使用当前 QEMU 中 Qwen2.5-1.5B-Instruct Q4_K_M 的实际 Block 参数和真实中间数据。
- 第二组保留相同算子结构，将矩阵尺寸替换为较大模型的代表尺寸，用于压力测试 Ara 的稳态吞吐。
- Decode 至少覆盖一个短 KV-cache 和一个较长 KV-cache 位置。
- Prefill 至少覆盖短 prompt 和中等 prompt 两组 token 数量。

## 5. 每个提取项保存的数据

每个工作负载实例应保存：

- 算子或 Block 类型；
- 模型、量化格式以及 Decode/Prefill 模式；
- 所有 tensor 的维度、stride、数据类型和量化 block 布局；
- 原始输入 tensor；
- 已 repack 权重和未 repack 权重，若该路径使用 repack；
- QEMU/llama.cpp 产生的 FP32 golden output；
- 数值比较容差；
- 实际调用的 kernel 名称；
- RVV ISA、VLEN、编译选项和 llama.cpp commit；
- Ara 执行周期、向量指令数、访存流量和结果检查状态。

其中最后一项只在后续明确选择 Ara 回放时生成，不属于当前 QEMU 抽取的完成条件。

## 6. 独立选择与回放粒度

- 微内核层按“操作类型、量化类型、实际 `n/k`、`nrc` 和所选 RVV kernel”去重，每个组合是独立 case。
- 算子层按 `prefill/decode × layer × weight tensor` 建立 case；Qwen2.5 第 0 层每个 phase 包含七个线性算子。
- 算子层除七个量化线性层外，还包含 Attention RMSNorm、Q/K RoPE、attention core、attention residual、FFN RMSNorm、SwiGLU 和 FFN residual；每项均可独立回放。
- Block 层按真实执行顺序聚合上述算子，分别提供 Prefill Block 和 Decode Block case。聚合运行时，每个子算子仍使用其 QEMU 捕获输入和 golden，避免前一子项的浮点误差掩盖后续子项错误。
- 运行某个叶子 case 不要求先运行同层其他 case，也不要求先运行更低层级；case 只读取自己的输入、权重、参数和 golden。
- 每一层均提供 `all` 入口；同时保留任意叶子 ID 的精确选择入口。例如可只运行一个 Q4_K dot、一个 `attn_q` 投影或一个 attention core。
- 完整性工具对 `.json` shape/type/nbytes 与 `.bin` 文件逐项核对，并记录 SHA-256，防止不同捕获轮次的数据混用。

当前 Qwen2.5-1.5B layer-0 的独立项如下：

- Micro：`F32->Q8_K` 的 `k=1536/8960`，Q4_K×Q8_K 与 Q6_K×Q8_K dot 的 `n=1536/8960`。
- 每个 Prefill/Decode phase 的量化线性算子：`attn_q`、`attn_k`、`attn_v`、`attn_output`、`ffn_gate`、`ffn_up`、`ffn_down`；其中 `attn_v` 和 `ffn_down` 保留模型中的 Q6_K，其余为 Q4_K。
- 每个 phase 的非线性/数据流算子：Attention RMSNorm、Q-RoPE、K-RoPE、Attention core、Attention residual、FFN RMSNorm、SwiGLU 和 FFN residual。
- Block：`block/prefill/all` 与 `block/decode/all` 按模型顺序运行；也可只运行 `block/<phase>/attention` 或 `block/<phase>/ffn`。其中任意算子叶子仍可绕过 Block suite 单独执行。

Attention core 的输入 K/V 是 KV-cache 写入完成后的实际 cache view，因此该 case 覆盖 cache 读取、QK matmul、mask/softmax、PV matmul和输出重排。KV-cache 写入是有状态的数据搬运，不和 Attention 数学 core 混为同一个叶子；若后续把 cache 更新本身作为性能对象，应另建带 pre-state、index、current K/V 和 post-state golden 的 stateful case。

常用选择命令：

```bash
# 列出所有叶子与 suite
hardware/scripts/llama_q4km_extract/run-case.sh

# 只运行一个 micro
hardware/scripts/llama_q4km_extract/run-case.sh \
  micro/q6_k_x_q8_k_dot_n8960_nrc1

# 只运行一个完整线性算子
hardware/scripts/llama_q4km_extract/run-case.sh \
  operator/decode/blk_0_ffn_down_weight

# 只运行 Attention core、Attention/FFN 子块或完整 Decode Block suite
hardware/scripts/llama_q4km_extract/run-case.sh operator/decode/attention_core
hardware/scripts/llama_q4km_extract/run-case.sh block/decode/attention
hardware/scripts/llama_q4km_extract/run-case.sh block/decode/ffn
hardware/scripts/llama_q4km_extract/run-case.sh block/decode/all
```

## 7. 实施优先级

1. 抽取 `Q4_K x Q8_K` block dot，建立最小正确性检查。
2. 抽取完整 Quantized Linear Decode，作为第一项主要 benchmark。
3. 抽取完整 Quantized Linear Prefill。
4. 抽取 RMSNorm、RoPE、Self-Attention 和 FFN activation 算子。
5. 组合并验证完整 Decode Block。
6. 组合并验证完整 Prefill Block。

最终报告应以 Quantized Linear 和 Decoder Transformer Block 为主，微内核结果用于解释性能来自 Q4 解包、点积、归约、访存还是算子间数据流。

### 7.1 Simulation-only 大容量内存模式

需要回放无法装入默认 1 MiB L2 的单个真实算子时，可以使用独立的 behavioral-memory
配置。该模式默认提供 16 MiB，仅改变 RTL 仿真顶层和应用 linker，不改变 `ara_soc` 的
综合默认参数，也不能与 SRAM macro、DC 或 SAIF 流程组合使用。

```bash
# 构建应用、独立 simv，并运行一次 16 MiB behavioral-memory 仿真
make -C hardware sim_large app=<app-name> large_l2_mb=16 no_fsdb=1

# 只编译大容量 simv
make -C hardware compile_large large_l2_mb=16

# 分开构建时，两侧容量必须一致
make -C apps <app-name> sim_l2_mb=16
make -C hardware sim app=<app-name> sim_l2_mb=16 no_fsdb=1
```

生成物位于 `hardware/build_sim_l2_16m/` 和 `hardware/sim_l2_16m/`，不会覆盖默认
`hardware/build/`、`hardware/sim/` 或后台验证使用的既有 `simv`。支持的容量为
1/2/4/8/16/32/64 MiB；超过 1 MiB 的配置都只用于功能和周期探索，不能作为当前物理
L2 的面积、功耗或后端实现依据。

## 8. 实际收集内容

本节只记录当前数据目录中已经存在并经过检查的内容，不把计划项或尚未抓取的状态描述为已完成。数据根目录为：

```text
/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/
```

### 8.1 数据集总览

| 项目 | 当前值 |
| --- | --- |
| 模型 | Qwen2.5-1.5B-Instruct Q4_K_M，GGUF 描述为 `qwen2 1.5B Q4_K - Medium` |
| 模型结构 | 28 层，hidden size 1536，12 个 query head，2 个 KV head，head dimension 128，FFN dimension 8960 |
| 捕获层 | Layer 0 |
| 执行环境 | RV64GCV QEMU，VLEN=1024，单线程 |
| Prefill | 15 个 token |
| Decode | 1 个 token |
| KV view 容量 | 256 个 token |
| 量化类型 | Q4_K_M 混合量化；`attn_v` 与 `ffn_down` 为 Q6_K，其余五个 Layer-0 线性权重为 Q4_K |
| 可选 ID | 48 个：36 个叶子与 12 个 suite |
| 叶子组成 | 6 个 Micro、14 个量化线性算子、16 个非线性/数据流算子 |
| 捕获 tensor | 86 个，每个均有 JSON 元数据和二进制数据，并在 manifest 中记录 SHA-256 |

当前数据集的 manifest 为 `replay/manifest.json`。本轮抓取发生在 provenance 字段写入功能加入之前，因此该 manifest 中的 `llama_commit`、compiler 和 build target 为空；模型结构、执行 phase、tensor 数据和 RVV 微内核信息均已保存。后续重新抓取时会自动补充这些构建来源字段，但不能倒推填写到本轮数据中。

### 8.2 Micro 层：6 个独立叶子

| Case ID | 操作 | 实际尺寸 | 捕获时 / 当前 replay kernel | 独立输入与 golden |
| --- | --- | ---: | --- | --- |
| `micro/quantize_f32_to_q8_k_k1536` | F32 -> Q8_K | `k=1536` | `quantize_row_q8_K` | F32 输入行、Q8_K 输出块 |
| `micro/quantize_f32_to_q8_k_k8960` | F32 -> Q8_K | `k=8960` | `quantize_row_q8_K` | F32 输入行、Q8_K 输出块 |
| `micro/q4_k_x_q8_k_dot_n1536_nrc1` | Q4_K x Q8_K dot | `n=1536, nrc=1` | `vl256` / `vl1024` | Q4_K 权重、Q8_K activation、单个 F32 结果 |
| `micro/q4_k_x_q8_k_dot_n8960_nrc1` | Q4_K x Q8_K dot | `n=8960, nrc=1` | `vl256` / `vl1024` | Q4_K 权重、Q8_K activation、单个 F32 结果 |
| `micro/q6_k_x_q8_k_dot_n1536_nrc1` | Q6_K x Q8_K dot | `n=1536, nrc=1` | `vl1024` / `vl1024` | Q6_K 权重、Q8_K activation、单个 F32 结果 |
| `micro/q6_k_x_q8_k_dot_n8960_nrc1` | Q6_K x Q8_K dot | `n=8960, nrc=1` | `vl1024` / `vl1024` | Q6_K 权重、Q8_K activation、单个 F32 结果 |

上述 dot case 均保留真实推理第一次出现的输入，累加语义为 INT32 partial sums 加 FP32 block scaling。`nrc=1` 反映当前 VLEN=1024 构建实际采用的通用 vec-dot 路径，而不是人工构造的 repacked GEMV/GEMM tile。

### 8.3 量化线性算子：每个 phase 7 个

每个线性叶子对应真实 `GGML_OP_MUL_MAT`，保存原始量化权重、F32 activation、F32 golden output 和 `operator.json`。运行时由 GGML 完成动态 Q8_K activation 量化和量化矩阵乘法。

| 叶子后缀 | 权重类型 | 权重 shape | Prefill 输入 -> 输出 | Decode 输入 -> 输出 |
| --- | --- | --- | --- | --- |
| `blk_0_attn_q_weight` | Q4_K | `[1536,1536]` | `[1536,15] -> [1536,15]` | `[1536,1] -> [1536,1]` |
| `blk_0_attn_k_weight` | Q4_K | `[1536,256]` | `[1536,15] -> [256,15]` | `[1536,1] -> [256,1]` |
| `blk_0_attn_v_weight` | Q6_K | `[1536,256]` | `[1536,15] -> [256,15]` | `[1536,1] -> [256,1]` |
| `blk_0_attn_output_weight` | Q4_K | `[1536,1536]` | `[1536,15] -> [1536,15]` | `[1536,1] -> [1536,1]` |
| `blk_0_ffn_gate_weight` | Q4_K | `[1536,8960]` | `[1536,15] -> [8960,15]` | `[1536,1] -> [8960,1]` |
| `blk_0_ffn_up_weight` | Q4_K | `[1536,8960]` | `[1536,15] -> [8960,15]` | `[1536,1] -> [8960,1]` |
| `blk_0_ffn_down_weight` | Q6_K | `[8960,1536]` | `[8960,15] -> [1536,15]` | `[8960,1] -> [1536,1]` |

14 个完整线性叶子 ID 为：

```text
operator/prefill/blk_0_attn_q_weight
operator/prefill/blk_0_attn_k_weight
operator/prefill/blk_0_attn_v_weight
operator/prefill/blk_0_attn_output_weight
operator/prefill/blk_0_ffn_gate_weight
operator/prefill/blk_0_ffn_up_weight
operator/prefill/blk_0_ffn_down_weight

operator/decode/blk_0_attn_q_weight
operator/decode/blk_0_attn_k_weight
operator/decode/blk_0_attn_v_weight
operator/decode/blk_0_attn_output_weight
operator/decode/blk_0_ffn_gate_weight
operator/decode/blk_0_ffn_up_weight
operator/decode/blk_0_ffn_down_weight
```

### 8.4 Prefill 非线性与数据流叶子：8 个

| Case ID | 运算及参数 | 输入 shape/type | Golden shape/type |
| --- | --- | --- | --- |
| `operator/prefill/attention_norm` | RMSNorm，`epsilon=1e-6`，再乘 1536-element norm weight | hidden `[1536,15]` F32；weight `[1536]` F32 | `[1536,15]` F32 |
| `operator/prefill/rope_q` | Q RoPE，NEOX mode 2，128 rotary dimensions，base `1e6` | Q `[128,12,15]` F32；position `[15]` I32 | `[128,12,15]` F32 |
| `operator/prefill/rope_k` | K RoPE，参数同 Q RoPE | K `[128,2,15]` F32；position `[15]` I32 | `[128,2,15]` F32 |
| `operator/prefill/attention_core` | QK、scale `1/sqrt(128)`、mask、softmax、PV、输出重排 | Q `[128,15,12]` F32；K/V `[128,256,2]` F16；mask `[256,15]` F16 | `[1536,15]` F32 |
| `operator/prefill/attention_residual` | Attention output + Block input | 两个 `[1536,15]` F32 | `[1536,15]` F32 |
| `operator/prefill/ffn_norm` | RMSNorm，`epsilon=1e-6`，再乘 norm weight | hidden `[1536,15]` F32；weight `[1536]` F32 | `[1536,15]` F32 |
| `operator/prefill/ffn_activation` | `SiLU(gate) * up` | gate/up 均为 `[8960,15]` F32 | `[8960,15]` F32 |
| `operator/prefill/ffn_residual` | FFN output + FFN input | 两个 `[1536,15]` F32 | `[1536,15]` F32 |

### 8.5 Decode 非线性与数据流叶子：8 个

| Case ID | 运算及参数 | 输入 shape/type | Golden shape/type |
| --- | --- | --- | --- |
| `operator/decode/attention_norm` | RMSNorm，`epsilon=1e-6`，再乘 1536-element norm weight | hidden `[1536,1]` F32；weight `[1536]` F32 | `[1536,1]` F32 |
| `operator/decode/rope_q` | Q RoPE，NEOX mode 2，128 rotary dimensions，base `1e6` | Q `[128,12,1]` F32；position `[1]` I32 | `[128,12,1]` F32 |
| `operator/decode/rope_k` | K RoPE，参数同 Q RoPE | K `[128,2,1]` F32；position `[1]` I32 | `[128,2,1]` F32 |
| `operator/decode/attention_core` | QK、scale `1/sqrt(128)`、mask、softmax、PV、输出重排 | Q `[128,1,12]` F32；K/V `[128,256,2]` F16；mask `[256,1]` F16 | `[1536,1]` F32 |
| `operator/decode/attention_residual` | Attention output + Block input | 两个 `[1536,1]` F32 | `[1536,1]` F32 |
| `operator/decode/ffn_norm` | RMSNorm，`epsilon=1e-6`，再乘 norm weight | hidden `[1536,1]` F32；weight `[1536]` F32 | `[1536,1]` F32 |
| `operator/decode/ffn_activation` | `SiLU(gate) * up` | gate/up 均为 `[8960,1]` F32 | `[8960,1]` F32 |
| `operator/decode/ffn_residual` | FFN output + FFN input | 两个 `[1536,1]` F32 | `[1536,1]` F32 |

Attention core 使用的是 KV-cache 更新后的真实 K/V view。它已经覆盖 cache 读取、QK、mask/softmax、PV 和输出重排，但没有把 cache append 本身算入该叶子。

### 8.6 Block 与聚合 suite：12 个

Suite 不创建新的人工输入，而是按顺序调用上述独立叶子。每个叶子都读取自己在真实 QEMU 推理边界抓取的输入并比较自己的 golden，因此一个前序叶子的浮点误差不会传播并掩盖后续错误。

| Suite ID | 内容 |
| --- | --- |
| `micro/all` | 6 个 Micro 叶子 |
| `operator/prefill/all` | Prefill 的 7 个线性叶子与 8 个非线性/数据流叶子 |
| `operator/decode/all` | Decode 的 7 个线性叶子与 8 个非线性/数据流叶子 |
| `operator/all` | `operator/prefill/all` + `operator/decode/all` |
| `block/prefill/attention` | Prefill Attention Norm、Q/K/V projection、Q/K RoPE、Attention core、output projection、residual |
| `block/prefill/ffn` | Prefill FFN Norm、gate/up projection、SwiGLU、down projection、residual |
| `block/prefill/all` | Prefill Attention 子块 + FFN 子块 |
| `block/decode/attention` | Decode Attention Norm、Q/K/V projection、Q/K RoPE、Attention core、output projection、residual |
| `block/decode/ffn` | Decode FFN Norm、gate/up projection、SwiGLU、down projection、residual |
| `block/decode/all` | Decode Attention 子块 + FFN 子块 |
| `block/all` | `block/prefill/all` + `block/decode/all` |
| `all` | `micro/all` + `block/all`，覆盖全部 36 个叶子且不重复运行同一叶子 |

### 8.7 每个叶子实际保存的文件

- Micro quantize：`microkernel.json`、`input_f32.bin`、`output_q8_k.bin`。
- Micro dot：`microkernel.json`、量化权重 `.bin`、`activation_q8_k.bin`、`output_f32.bin`。
- 量化线性算子：`operator.json`、量化权重 `.json/.bin`、`activation_f32.json/.bin`、`output_f32.json/.bin`。
- 非线性/数据流叶子：`replay/cases/.../case.json`；其中记录输入、参数和 golden 的相对路径，实际 tensor 位于对应 phase 的 `block/` 目录。
- Tensor JSON：记录 role、原 GGML tensor name、type、四维 shape、stride 和 nbytes。
- `replay/manifest.json`：记录全部 case ID、suite 关系、捕获规模及每个 tensor 文件的 SHA-256。
- `validation/host-all.log`：记录 Host 上全量回放的逐叶比较结果；该目录不受 `cases.py prepare` 重建 `replay/` 的影响。

### 8.8 已完成验证

- `cases.py prepare --strict`：通过；严格要求 6 个 Micro、每 phase 7 个线性算子及每 phase 8 个非线性/数据流叶子，缺少任一项都会失败。
- `cases.py verify-data`：通过；86 个 tensor 的 JSON、二进制文件、nbytes 和 SHA-256 一致。
- Host `run-case.sh all`：36 个叶子全部 PASS。
- Q/K RoPE、Attention/FFN residual 和 RMSNorm 在 Host 回放中为逐元素零误差。
- Attention core 因 x86 与 RVV 浮点归约顺序不同，使用该算子独立容差 `atol=4e-3, rtol=2e-3`；Prefill 最大绝对误差 `0.00284076`，Decode 最大绝对误差 `0.000849962`，均无超容差元素。
- RV64GCV QEMU 单叶回放已实测以下三类代表项，结果均与 RVV QEMU golden 完全一致，Guest 与 Host 退出状态均为 0：
  - `micro/q4_k_x_q8_k_dot_n1536_nrc1`；
  - `operator/decode/attention_norm`；
  - `operator/decode/blk_0_attn_k_weight`。

### 8.9 当前没有收集或没有声明覆盖的内容

- KV-cache append 的独立状态变换：还缺更新前 cache、写索引、本轮 K/V 和更新后 cache golden；当前只有更新后的 Attention K/V view。
- 跨叶子传递回放输出的端到端独立模型执行器：现有 Block 是 ordered golden-isolated suite，而非另一个 llama.cpp runtime。
- Layer 1 至 Layer 27 的独立张量：当前只抓取 Layer 0，利用同构层代表单层结构。
- 不同 prompt 长度、不同 KV 长度或不同模型尺寸的规模 sweep：当前固定为 Prefill 15 token、Decode 1 token 和 KV capacity 256。
- 当前完整 `llama.cpp` 构建仍未把实验性的 RISC-V repacked Q4_K GEMV/GEMM 接入默认模型路径；第 10 节使用真实 Qwen2.5 权重、activation 和 golden 构造受控的等计算量 microkernel 对比，不能冒充完整 `ffn_gate` 算子性能。
- Ara 上已经收集第 10 节所述 Q4_K 单输出、32 行 GEMV 和 32x4 GEMM microkernel 的功能、周期、向量指令和向量 AXI 读取数据；其余 36 个叶子的 Ara 全量性能统计仍未完成。

## 9. Benchmark 计算与模型阶段索引

本节按 `replay/manifest.json` 中的实际 ID 解释每个可运行 benchmark。当前共有
36 个计算叶子和 12 个 suite。计算叶子拥有独立输入与 golden；suite 只是按模型顺序
组织叶子，不引入新的数学计算。

### 9.1 阶段约定

- **Prefill**：一次处理当前 prompt 的 15 个 token，主要关注矩阵复用和持续吞吐。
- **Decode**：一次处理 1 个新 token，主要关注单 token 延迟、权重读取和 KV-cache
  访问。
- **Attention 子层**：`RMSNorm -> Q/K/V projection -> RoPE -> Attention core ->
  output projection -> residual add`。
- **FFN 子层**：`RMSNorm -> gate/up projection -> SiLU(gate) * up -> down
  projection -> residual add`。
- **Micro benchmark**：从真实量化线性算子内部抽出的底层计算，不等同于一个完整
  Transformer 算子；它用于定位量化、解包、整数点积或归约的成本。

### 9.2 Micro：6 个底层计算

| Benchmark ID | 计算 Shape | 计算内容 | 对应的大模型阶段 | 作用 |
| --- | --- | --- | --- | --- |
| `micro/quantize_f32_to_q8_k_k1536` | `[1536] F32 -> 6 x block_q8_K`，输出 1752 B | 将 FP32 activation 按 256-element Q8_K block 动态量化，生成 INT8 值、scale 和辅助统计量 | Attention Q/K/V、Attention output、FFN gate/up 等输入维度为 1536 的量化线性层内部 | 单独衡量 activation 动态量化成本 |
| `micro/quantize_f32_to_q8_k_k8960` | `[8960] F32 -> 35 x block_q8_K`，输出 10220 B | 将长 FP32 activation 动态量化为 Q8_K | FFN down projection 的 8960 维中间 activation 输入 | 衡量大 FFN 中间向量的量化成本 |
| `micro/q4_k_x_q8_k_dot_n1536_nrc1` | `[1536] Q4_K dot [1536] Q8_K -> [1] F32`，6 个 K-block | 解包一个 Q4_K 权重行，与 Q8_K activation 做整数点积、归约和 FP32 scale/min 修正 | Q4_K 量化线性层内部的单输出通道计算 | 定位 Q4 解包、整数乘法和归约开销 |
| `micro/q4_k_x_q8_k_dot_n8960_nrc1` | `[8960] Q4_K dot [8960] Q8_K -> [1] F32`，35 个 K-block | 长 K 维 Q4_K×Q8_K 单行点积 | 真实推理中出现的长 K 维 Q4_K 点积路径 | 观察长向量下 Q4 解包和归约的稳态行为 |
| `micro/q6_k_x_q8_k_dot_n1536_nrc1` | `[1536] Q6_K dot [1536] Q8_K -> [1] F32`，6 个 K-block | Q6_K×Q8_K 单行点积 | Q6_K Attention-V 等混合量化线性层内部 | 衡量 Q6 解包与 Q8 activation 点积 |
| `micro/q6_k_x_q8_k_dot_n8960_nrc1` | `[8960] Q6_K dot [8960] Q8_K -> [1] F32`，35 个 K-block | 长 K 维 Q6_K×Q8_K 单行点积 | Q6_K FFN down projection 内部 | 衡量 FFN down 的长向量点积核心成本 |

`nrc=1` 表示当前 VLEN=1024 构建实际采用通用逐行 vec-dot 路径，而不是一次计算
多个输出行的人工 repacked GEMV/GEMM tile。

### 9.3 Quantized Linear：14 个完整量化线性算子

下表每行包含 Prefill 和 Decode 两个独立叶子，因此共 14 个 benchmark。二者使用相同
权重和数学操作，但 activation 分别包含 15 个 token 和 1 个 token。每个叶子都执行
完整的 `GGML_OP_MUL_MAT`，包括 FP32 activation 的 Q8_K 动态量化、量化权重读取、
Q4_K/Q6_K×Q8_K 点积、归约、缩放和 FP32 输出写回。

| Prefill / Decode ID 后缀 | 计算 Shape | 模型中的位置 | 作用 |
| --- | --- | --- | --- |
| `operator/{prefill,decode}/blk_0_attn_q_weight` | Q4_K，`[1536,1536] x [1536,M] -> [1536,M]` | Attention RMSNorm 之后，生成 12 个 query head 的 Q | 产生用于查询 KV-cache 的 query 向量 |
| `operator/{prefill,decode}/blk_0_attn_k_weight` | Q4_K，`[1536,256] x [1536,M] -> [256,M]` | Attention RMSNorm 之后，生成 2 个 KV head 的 K | 产生随后执行 RoPE 并写入 KV-cache 的 key |
| `operator/{prefill,decode}/blk_0_attn_v_weight` | Q6_K，`[1536,256] x [1536,M] -> [256,M]` | Attention RMSNorm 之后，生成 2 个 KV head 的 V | 产生写入 KV-cache、供 `P*V` 使用的 value |
| `operator/{prefill,decode}/blk_0_attn_output_weight` | Q4_K，`[1536,1536] x [1536,M] -> [1536,M]` | Attention core 输出之后、第一次 residual add 之前 | 将多头 Attention context 投影回 hidden size |
| `operator/{prefill,decode}/blk_0_ffn_gate_weight` | Q4_K，`[1536,8960] x [1536,M] -> [8960,M]` | FFN RMSNorm 之后的 gate 分支 | 生成 SwiGLU 的门控输入 |
| `operator/{prefill,decode}/blk_0_ffn_up_weight` | Q4_K，`[1536,8960] x [1536,M] -> [8960,M]` | FFN RMSNorm 之后的 up 分支 | 将 hidden state 扩展到 8960 维 FFN 空间 |
| `operator/{prefill,decode}/blk_0_ffn_down_weight` | Q6_K，`[8960,1536] x [8960,M] -> [1536,M]` | `SiLU(gate)*up` 之后、第二次 residual add 之前 | 将 FFN 中间结果压回 1536 维 hidden state |

这里沿用 GGML 权重元数据方向，统一写成 `[K,N] weight x [K,M] activation ->
[N,M] output`；`M=15` 对应 Prefill，`M=1` 对应 Decode。Q4_K_M 是混合量化格式：当前模型
Layer 0 的 `attn_v` 和 `ffn_down` 为 Q6_K，其余五组线性权重为 Q4_K。

### 9.4 Prefill：8 个非线性与数据流算子

| Benchmark ID | 计算 Shape | 计算内容 | 模型中的位置 | 作用 |
| --- | --- | --- | --- | --- |
| `operator/prefill/attention_norm` | hidden `[1536,15]` + weight `[1536] -> [1536,15]` F32 | 逐 token RMSNorm，再乘 norm weight | Transformer Block 入口、QKV projection 之前 | 稳定 Attention 子层输入尺度 |
| `operator/prefill/rope_q` | Q `[128,12,15]` + position `[15] -> [128,12,15]` F32 | 对 12 个 query head、15 个 token 做 NEOX RoPE | Q projection 之后、QK 计算之前 | 将相对位置信息编码到 query |
| `operator/prefill/rope_k` | K `[128,2,15]` + position `[15] -> [128,2,15]` F32 | 对 2 个 KV head、15 个 token 做 NEOX RoPE | K projection 之后、KV-cache/Attention 之前 | 将位置信息编码到 key |
| `operator/prefill/attention_core` | Q `[128,15,12]` F32；K/V `[128,256,2]` F16；mask `[256,15]` F16；输出 `[1536,15]` F32 | 执行 `Q*K^T`、`1/sqrt(128)` scale、causal mask、softmax、`P*V` 和输出重排 | Q/K RoPE 之后、Attention output projection 之前 | 完成多头自注意力核心，并读取更新后的 K/V cache view |
| `operator/prefill/attention_residual` | `[1536,15] + [1536,15] -> [1536,15]` F32 | 逐元素加法 | Attention output projection 之后 | 将 Attention 输出加回 Block 输入 |
| `operator/prefill/ffn_norm` | hidden `[1536,15]` + weight `[1536] -> [1536,15]` F32 | 逐 token RMSNorm 和权重缩放 | FFN gate/up projection 之前 | 稳定 FFN 子层输入尺度 |
| `operator/prefill/ffn_activation` | gate `[8960,15]` + up `[8960,15] -> [8960,15]` F32 | `SiLU(gate) * up` | gate/up projection 之后、down projection 之前 | 实现 Qwen2.5 FFN 的 SwiGLU 非线性 |
| `operator/prefill/ffn_residual` | `[1536,15] + [1536,15] -> [1536,15]` F32 | 逐元素加法 | FFN down projection 之后、Block 出口 | 形成最终 Block 输出 |

### 9.5 Decode：8 个非线性与数据流算子

| Benchmark ID | 计算 Shape | 计算内容 | 模型中的位置 | 作用 |
| --- | --- | --- | --- | --- |
| `operator/decode/attention_norm` | hidden `[1536,1]` + weight `[1536] -> [1536,1]` F32 | 单 token RMSNorm 和权重缩放 | Decode Block 入口、QKV projection 之前 | 准备当前 token 的 Attention 输入 |
| `operator/decode/rope_q` | Q `[128,12,1]` + position `[1] -> [128,12,1]` F32 | 当前 token 的 12 个 query head 做 NEOX RoPE | Q projection 之后、查询历史 KV 之前 | 编码当前 decode position |
| `operator/decode/rope_k` | K `[128,2,1]` + position `[1] -> [128,2,1]` F32 | 当前 token 的 2 个 KV head 做 NEOX RoPE | K projection 之后、写入 KV-cache 之前 | 生成带位置信息的当前 key |
| `operator/decode/attention_core` | Q `[128,1,12]` F32；K/V `[128,256,2]` F16；mask `[256,1]` F16；输出 `[1536,1]` F32 | 当前 Q 与更新后历史 K 做点积、scale、mask、softmax，再与历史 V 相乘 | RoPE/KV-cache 更新之后、output projection 之前 | 从已有上下文中聚合当前 token 所需的信息 |
| `operator/decode/attention_residual` | `[1536,1] + [1536,1] -> [1536,1]` F32 | 逐元素加法 | Attention output projection 之后 | 保留当前 token 的 residual path |
| `operator/decode/ffn_norm` | hidden `[1536,1]` + weight `[1536] -> [1536,1]` F32 | 单 token RMSNorm 和权重缩放 | FFN gate/up projection 之前 | 准备当前 token 的 FFN 输入 |
| `operator/decode/ffn_activation` | gate `[8960,1]` + up `[8960,1] -> [8960,1]` F32 | `SiLU(gate) * up` | gate/up projection 之后、down projection 之前 | 实现单 token SwiGLU |
| `operator/decode/ffn_residual` | `[1536,1] + [1536,1] -> [1536,1]` F32 | 逐元素加法 | FFN down projection 之后、Block 出口 | 形成当前 token 的最终 Block 输出 |

### 9.6 Suite：12 个组合入口

suite 不保存额外 tensor，也不代表新的算子。它们只是把上述叶子按指定范围顺序执行，
每个叶子仍独立读取真实 QEMU 输入并检查自己的 golden。suite 因包含异构算子而没有
单一计算 shape，其 shape 集合就是下表所列子叶子的 shape。

| Suite ID | 包含内容 | 适合回答的问题 |
| --- | --- | --- |
| `micro/all` | 全部 6 个 Micro | 底层量化与点积实现是否整体正确 |
| `operator/prefill/all` | Prefill 的 7 个线性算子和 8 个非线性/数据流算子 | Prefill 层所有独立算子是否通过 |
| `operator/decode/all` | Decode 的 7 个线性算子和 8 个非线性/数据流算子 | Decode 层所有独立算子是否通过 |
| `operator/all` | Prefill 与 Decode 的全部算子叶子 | 两种推理阶段的算子级完整回归 |
| `block/prefill/attention` | Prefill Attention Norm、Q/K/V、RoPE、Attention core、output projection 和 residual | Prefill Attention 子层回归 |
| `block/prefill/ffn` | Prefill FFN Norm、gate/up、SwiGLU、down 和 residual | Prefill FFN 子层回归 |
| `block/prefill/all` | Prefill Attention suite 与 FFN suite | 一个 Prefill Block 的 ordered golden-isolated 回归 |
| `block/decode/attention` | Decode Attention Norm、Q/K/V、RoPE、Attention core、output projection 和 residual | Decode Attention 子层回归 |
| `block/decode/ffn` | Decode FFN Norm、gate/up、SwiGLU、down 和 residual | Decode FFN 子层回归 |
| `block/decode/all` | Decode Attention suite 与 FFN suite | 一个 Decode Block 的 ordered golden-isolated 回归 |
| `block/all` | Prefill 与 Decode 两个 Block suite | 单层两种执行阶段的联合回归 |
| `all` | `micro/all` 与 `block/all` | 全部 36 个计算叶子且不重复执行 |

### 9.7 使用这些 Benchmark 时应如何解释

- Micro 结果只能说明底层量化或点积实现，不能直接代表完整 LLM 吞吐。
- Quantized Linear 是评价 Ara 量化矩阵计算能力的主要算子级 benchmark。
- RMSNorm、RoPE、Attention core、SwiGLU 和 residual 用于覆盖矩阵计算之外的真实
  Transformer 数据流。
- `block/*` suite 用于回归和分阶段性能汇总，但当前是 ordered golden-isolated
  执行，不是跨叶子传递输出的第二套端到端 Qwen runtime。
- 当前 Attention core 读取 KV-cache 更新后的 K/V view；KV-cache append 本身尚未作为
  独立有状态 benchmark 抽取。

## 10. Ara Q4_K 多输出微内核对比

### 10.1 实验目的与统一任务

该实验比较从单输出点积到多输出量化矩阵内核的逐级变化，回答两个问题：单纯针对
VLEN=1024 减少向量归约是否足以提高 Ara 性能，以及跨输出行、跨输入行复用数据能够
带来多大收益。四种实现执行完全相同的数学任务：

```text
W: [32, 1536] Q4_K
X: [4, 1536] Q8_K
Y: [4, 32] FP32

Y = X * W^T
```

因此每种实现都完成 128 个长度为 1536 的 Q4_K x Q8_K 点积。权重取自真实
Qwen2.5-1.5B-Instruct Q4_K_M Layer 0 Decode `ffn_gate` 的前 32 个输出行；activation
取自同一算子边界的 FP32 输入，并按 `quantize_row_q8_K_ref` 的规则生成 Q8_K。为了使
四种实现具有一致、稳定的控制路径，实验将同一个真实 activation 复制为 4 个输入行。
所有实现都与该真实算子的前 32 个 FP32 golden 输出逐元素比较，4 行结果均通过。

四种实现分别使用内容相同但地址独立的数据副本，避免前一计量区间留下的标量 cache
状态影响后一实现。该实验只计量矩阵核心，不包括模型加载时权重 repack，也不包括
FP32 activation 到 Q8_K 的动态量化。

### 10.2 四种 microkernel

#### 10.2.1 原始单输出

`q4k_dot_original()`保留原始 `ggml_vec_dot_q4_K_q8_K` 风格：一次读取一个 Q4_K 权重
行和一个 Q8_K activation，产生一个 FP32 输出。每个 Q4_K block 内分别完成 nibble
解包、Q4 x Q8 widening multiply、分组归约、scale/min 修正和标量累加。统一任务需要
调用 `4 x 32 = 128` 次。

#### 10.2.2 VLEN=1024 单输出

`q4k_dot_vl1024()`仍然一次只产生一个输出，也调用 128 次。它使用 VLEN=1024 下
LMUL=1 可容纳的 32 个 I32 lane 保存一个 Q4_K block 的向量累加结果，把原始实现的
多个分组归约合并为 block 末尾的一次 I32 reduction。该版本改变的是单点积内部的
指令组织，不跨输出复用权重，也不减少 activation 或权重读取量。

#### 10.2.3 32 行 GEMV

`q4k_gemv_32()`将 32 个 Q4_K 输出行按 block 内相同字段交织重排。VL=32 的每个
vector lane 对应一个输出行，一条向量指令因而同时推进 32 个独立输出：

```text
Q8_K[1536] x Q4_K[32,1536] -> FP32[32]
```

同一个 activation block 只读取一次，Q4 解包后的向量结果直接沿 32 个输出 lane
累加，不再为每个输出单独执行向量归约。统一任务对 4 个输入分别调用一次，共调用 4 次。

#### 10.2.4 32x4 GEMM

`q4k_gemm_32x4()`在 32 行 GEMV 基础上同时维护 4 组输出累加器：

```text
Q8_K[4,1536] x Q4_K[32,1536] -> FP32[4,32]
```

每次读取一个 32-row weight vector 后，依次与 4 个 Q8_K 输入的对应标量相乘并更新
4 组 vector accumulator，使同一权重数据同时服务 4 个输入。完整的 128 个输出由一次
microkernel 调用完成。

### 10.3 Ara 配置与计量口径

| 项目 | 配置或定义 |
| --- | --- |
| Ara | 4 lanes，VLEN=1024 |
| 仿真内存 | 16 MiB simulation-only behavioral L2 |
| `cycles` | `rdcycle zero` 边界之间的 testbench `total_cycles` |
| 向量指令数 | testbench `total_vector_insns` |
| 逻辑读取量 | 按算法实际消费的 Q4_K/Q8_K 数据结构字节数计算 |
| Ara AXI 读流量 | `rvv_axi_r_count x 16 B`；4-lane 配置的 wide AXI 数据宽度为 128 bit |

Ara AXI 读流量只覆盖向量 AXI R channel，不包含 CVA6 标量侧读取。它按完整 R beat
计数，包含短向量访问带来的总线粒度开销，因此不等同于有效数据字节数。逻辑读取量则
表达数据复用算法应消费的数据量，但不反映总线过取和标量/向量通道划分。两项应同时
报告，不能互相替代。

### 10.4 实测结果

| 实现 | 周期 | 相对原始加速 | 向量指令数 | 逻辑读取量 | AXI AR | AXI R beats | Ara AXI 读流量 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 原始单输出 | 714,995 | 1.000x | 54,144 | 334,848 B | 22,348 | 36,096 | 577,536 B |
| VLEN=1024 单输出 | 721,519 | 0.991x | 47,360 | 334,848 B | 22,316 | 36,096 | 577,536 B |
| 32 行 GEMV | 138,755 | 5.153x | 19,104 | 117,600 B | 3,600 | 7,536 | 120,576 B |
| 32x4 GEMM | 52,390 | 13.648x | 10,717 | 34,656 B | 912 | 1,980 | 31,680 B |

四项数值检查均为 `PASS`，mismatch 为 0。完整 testbench 报告位于：

```text
hardware/sim_l2_16m/perf_report_llama_q4k_repack_bench.log
```

### 10.5 结果解释

- VLEN=1024 单输出将向量指令减少 12.53%，但周期增加 0.91%。减少 reduction 数量
  并未减少 11,520 条 vector load 和 AXI R 流量，同时 I32 vector accumulate 形成较长
  的相关依赖链。对当前 4-lane Ara，较少的动态指令不自动等价于较低延迟。
- 32 行 GEMV 相对原始单输出加速 5.153 倍，向量指令减少 64.72%，逻辑读取量减少
  64.88%，Ara AXI 读流量减少 79.12%。主要收益来自让向量 lane 表示独立输出行，消除
  逐输出归约，并在 32 个输出间共享 activation。
- 32x4 GEMM 相对原始单输出加速 13.648 倍，向量指令减少 80.21%，逻辑读取量减少
  89.65%，Ara AXI 读流量减少 94.51%。它进一步让同一权重 tile 服务 4 个输入，说明
  当前 Ara 上最有效的优化层级不是继续压缩单输出 dot 指令，而是 repack 后的多输出
  GEMV/GEMM。
- 这些数字不能直接解释为完整 Decode `ffn_gate` 的端到端加速。完整算子还包含动态
  Q8_K 量化、8960 个输出行、repack 选择与尾部处理、GGML 调度和输出写回。该实验的
  作用是验证核心数据布局和微内核方向，并量化其计算与访存收益上限。

### 10.6 复现实验

```bash
# 生成真实数据并构建 16 MiB 仿真 ELF
make -C apps bin/llama_q4k_repack_bench sim_l2_mb=16

# 先在 VLEN=1024 Spike 上检查四种实现
make -C apps spike-run-llama_q4k_repack_bench sim_l2_mb=16

# 在 Ara RTL 上收集四个独立性能区间
make -C hardware sim app=llama_q4k_repack_bench sim_l2_mb=16
```

实现和数据生成代码位于 `apps/llama_q4k_repack_bench/`。数据生成器依赖本机真实
Qwen2.5 capture 目录，因此换机器复现时必须先准备相同 capture，不能用随机数据替换
后仍把结果描述为真实模型数据。

## 11. Ara 真实模型算子评测集

### 11.1 评测边界

在微内核对比之外，当前仓库提供六个可独立构建和执行的真实算子 benchmark。它们均
来自 Qwen2.5-1.5B-Instruct Q4_K_M 第 0 层的一次完整 `llama.cpp` 推理 capture，保留
真实 GGUF 权重字节、真实 F32 中间 activation 和对应 F32 golden。该评测集用于回答
Ara 执行完整量化线性算子的性能，而不是只测一个 Q4_K block dot。

| Case | 推理阶段 | 权重矩阵 | 输入数 M | 量化类型 | 模型位置 |
| --- | --- | ---: | ---: | --- | --- |
| `decode_attn_q` | Decode | `1536 x 1536` | 1 | Q4_K | Query projection |
| `decode_ffn_gate` | Decode | `8960 x 1536` | 1 | Q4_K | SwiGLU gate projection |
| `decode_ffn_down` | Decode | `1536 x 8960` | 1 | Q6_K | FFN down projection |
| `prefill_attn_q` | Prefill | `1536 x 1536` | 15 | Q4_K | Query projection |
| `prefill_ffn_gate` | Prefill | `8960 x 1536` | 15 | Q4_K | SwiGLU gate projection |
| `prefill_ffn_down` | Prefill | `1536 x 8960` | 15 | Q6_K | FFN down projection |

表中的矩阵统一写成 `输出行数 x K`。每个输入都在运行时由 F32 动态量化为 Q8_K。
Q4_K case 使用 32-row weight layout：Decode 每次计算 32 个输出，Prefill 每次同时
推进 32 个输出行和最多 4 个输入；`M=15` 由三个 `32x4` tile 和三个尾部 GEMV 组成。
Q6_K down projection 当前保留 llama.cpp 的 Q6_K x Q8_K 单输出数学路径，作为后续
Q6 多输出优化的真实基线，不能与已 repack 的 Q4_K 性能直接解释为量化格式优劣。

### 11.2 数据可追溯性

构建一个 case 时，`apps/llama_qwen25_<case>/generated/` 会生成：

- `source_weight.bin`：未经修改的 GGUF row-major 权重字节；
- `activation_f32.bin`：完整模型运行中该算子边界的 F32 输入；
- `golden_f32.bin`：同一次运行得到的 F32 输出；
- `embedded_weight.bin`：ELF 实际嵌入的权重布局；Q4_K 为离线 x32 repack，Q6_K 与
  原始权重相同；
- `provenance.json`：模型、layer、phase、shape、量化类型、capture commit、每个文件
  的字节数和 SHA-256。

生成器逐项检查 JSON metadata 中的 `nbytes`、期望 shape 对应的大小和实际文件大小。
当前完整 capture 的 86 个 tensor 已通过统一 size/SHA-256 检查。`generated` 数据不进
Git；换机器时必须提供相同 capture，或通过 `LLAMA_CAPTURE_ROOT` 指向等价数据根目录。

### 11.3 计量口径

主计时区间为：

```text
F32 activation -> Q8_K dynamic quantization
                         +
Q4_K/Q6_K quantized matrix computation -> F32 output
```

模型文件读取、capture 加载、Q4_K 离线 weight repack、结果校验和打印均排除。由于
当前 Q4_K 权重在构建期完成 repack，运行时 `setup_cycles=0`；若以后改为运行时 repack，
其周期必须单独放入 `setup_cycles`，不能并入或隐藏在 `compute_cycles` 中。

应用输出提供 `compute_cycles`、`cycles_per_output`、逻辑读取量、输出 checksum、
mismatch、最大绝对误差和最大相对误差。RTL testbench 同一计时边界还提供
`total_vector_insns`、`ara_req_fire_count`、`rvv_axi_ar_count` 和 `rvv_axi_r_count`。
`logical_read_bytes` 表示完整计时区间按数据结构语义读取的字节数，包括 F32 动态量化
输入、prefill activation 打包输入和量化矩阵内核读取；AXI 计数表示实际总线事务，
包含 beat 粒度和重复访问，二者不能互相替代。

### 11.4 构建、验证与运行

```bash
# 查看六个 case
make -C hardware llama_real_list

# 生成数据并构建一个 16 MiB bare-metal ELF
make -C hardware llama_real_build case=decode_attn_q

# 在 VLEN=1024 Spike 上逐输出检查真实 golden
make -C hardware llama_real_spike case=decode_attn_q

# 在独立 16 MiB simulation-only L2 上运行 Ara RTL
make -C hardware llama_real_sim case=decode_attn_q no_fsdb=1

# 合并应用结果和 testbench 微结构计数器
make -C hardware llama_real_sum \
  run_log=sim_l2_16m/run.vcs.log \
  perf_log=sim_l2_16m/perf_report_llama_qwen25_decode_attn_q.log \
  output=llama_benchmark_runs/decode_attn_q.csv
```

六个 ELF 的总 section 大小为约 `1.36-12.17 MiB`，均小于 16 MiB behavioral L2。
该容量只用于 RTL 功能和周期评估，不改变可综合 L2，也不能据此报告物理面积或 SRAM
功耗。当前六个 case 已全部在 VLEN=1024 Spike 上通过真实 golden；VCS 结果应按 case
独立保存，避免后一次运行覆盖同名 `run.vcs.log`。
