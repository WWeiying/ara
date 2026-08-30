# QBS 显式激活上下文探索

## 1. 问题边界

当前 QBS 已经在一条 `qbexec` 内把一个量化激活 block 复用于最多 32 个输出行，但
复用边界止于单条命令。`llama.cpp` 的一个大矩阵会被拆成多条 32-output 命令；每条
命令都以量化激活内存地址作为 `rs2`，QBS 因此重新读取相同的 Q8 激活。Qwen2.5 的
Q/K/V projection 又共享同一个 Attention RMSNorm 输出，gate/up projection 共享
同一个 FFN RMSNorm 输出；GGML 当前仍在每个独立 `GGML_OP_MUL_MAT` 内重新执行
F32-to-Q8 动态量化。

这里有两层重复工作：

1. **算子内重复 Q8 读取**：同一矩阵的多个输出 tile 重复读取相同 Q8 激活。
2. **算子间重复动态量化**：Q/K/V 或 gate/up 对同一 F32 tensor 分别量化。

第一阶段探索针对第一层，同时设计能够承接第二层的软件与硬件契约。它不把 FFN-down
的 `K=8960` 输入当作主要复用对象，因为该激活在当前 Qwen block 中只有一个直接矩阵
消费者。

## 2. 真实模型证据

### 2.1 数据身份

Qwen2.5-1.5B-Instruct Q4_K_M Layer 0 Decode capture 中：

- `attn_q`、`attn_k`、`attn_v` 的 `activation_f32.bin` 均为 6144 B，SHA-256
  完全相同；它们是同一个 1536-element Attention RMSNorm 输出。
- `ffn_gate`、`ffn_up` 的 `activation_f32.bin` 均为 6144 B，SHA-256 完全相同；
  它们是同一个 1536-element FFN RMSNorm 输出。

这与 Qwen2 图构建源码一致：`build_qkv()` 把同一个 `cur` 分别传给 Q/K/V，
`build_ffn()` 把同一个 `cur` 分别传给 gate/up。GGML 的 repack `MUL_MAT` 路径则在
每个算子自己的 `params->wdata` 中调用 `from_float`，没有跨算子量化复用。

### 2.2 当前 RTL 的命令级证据

现有 Q4_K Decode `attn_q` 实测包含 48 条 QBS 命令：

| 指标 | 实测值 |
| --- | ---: |
| QBS busy cycles | 110571 |
| Activation phase cycles | 10320 |
| Activation bytes | 84096 B |
| 单份 Q8_K 激活 | 1752 B |
| 重复读取 | 82344 B |

`84096 = 48 x 1752`，说明每个输出 tile 都完整重读六个 Q8_K block。若只把首条命令
作为 context fill，其余 47 条命令复用，激活流量可减少 97.9%。按现有 phase 比例得到
的理想上界是移除约 10105 个 QBS busy cycles；这是确定后续实现价值的上界，不是尚未
实现的实测加速。

裁剪为 4096 输出行的 Decode `ffn_gate` 也呈现相同结构：128 条命令读取 224256 B
激活，而唯一数据只有 1752 B。该现象不是 Attention 特例，而是当前 32-output 命令
粒度的系统性结果。

## 3. 不采用隐式地址缓存

仅比较 `activation_base`、profile 和 shape，在地址相同时自动命中，硬件改动最小，
但不满足内存语义。软件可能在两条命令之间原地更新同一地址；若硬件无法观察所有标量
和向量写路径，地址命中会返回旧数据。仅在 `fence` 或普通 store 时清空也难以覆盖别名、
DMA 和未来一致性扩展。

因此上下文复用必须是**显式软件承诺**。软件声明某一份量化激活进入上下文，并用 token
引用它；硬件只在 token 和完整元数据匹配时复用。普通 `qbexec` 保持原行为。

## 4. 建议的架构契约

### 4.1 命令模式

描述符 v2 增加 activation access mode：

- `DIRECT`：现有路径；每条命令从 `activation_base` 读取，不改变上下文。
- `FILL`：从内存读取并执行，同时写入指定 context；命令成功后 context 才变为有效。
- `REUSE`：不读取激活内存，从指定 context 取得数据并执行。
- `RELEASE`：使 context 失效；可由独立控制操作或最后一次使用标志表达。

描述符还携带 context ID 和 generation。`REUSE` 必须同时满足：

```text
valid
&& context_id match
&& generation match
&& activation_profile match
&& activation_layout match
&& M match
&& K-block count match
```

任一条件不满足都产生精确的 validation fault，不静默回退到内存，因为静默回退会掩盖
软件生命周期错误。

### 4.2 故障与可见性

- `FILL` 期间可以写入暂存数据，但只有整条命令成功后才提交 context metadata 和 valid。
- 激活读、权重读或计算故障都不得留下可被 `REUSE` 观察的半有效 context。
- `REUSE` 不观察 `activation_base` 后续内容；显式 token 表示软件有意使用已保存快照。
- reset、上下文 release 和新的同 ID `FILL` 会使旧 generation 失效。
- 普通 RVV 和 `DIRECT` QBS 不依赖 context 状态，保证现有功能与 ABI 回退路径不变。

## 5. 容量与适用范围

Q8_K 每 256 个元素占 292 B。典型 Decode 共享输入需要：

| Hidden K | K blocks | 单行 context |
| ---: | ---: | ---: |
| 1536 | 6 | 1752 B |
| 2048 | 8 | 2336 B |
| 4096 | 16 | 4672 B |
| 8192 | 32 | 9344 B |

第一版建议：一个 context、`M=1`、最多 16 个 Q8_K block。它覆盖当前 Qwen2.5-1.5B、
hidden size 2048/4096 的常见 Decode 投影，并把存储控制在 4.7 KiB。超过容量、`M>1`
或 Q8_0 等未实现组合通过 capability query 选择 `DIRECT`，而不是在硬件内部分段后产生
难以解释的部分命中。

该限制是第一版实现边界，不应写成 QBS 架构的永久限制。capability word 必须报告
context 数量、支持的 activation profile、最大 M 和最大 K-block 数。

## 6. 微结构组织

上下文存储不应直接扩成大量触发器。建议采用单端口或简单双口 SRAM，并利用 QBS 当前
计算间隔隐藏 context replay：

1. `FILL` 的 AXI activation beat 同时写当前 block adapter 和 context SRAM。
2. `REUSE` 从 context SRAM 读取下一 K block。
3. 复用 `qbs_compute_engine` 中当前未使用的第二套 activation block storage，形成双缓冲。
4. 当前 K block 计算时，下一 block 从 context SRAM 填入非活动 bank；切换 K 时交换 bank。
5. weight 双缓冲和 activation 双缓冲分别维护 tag，只有 `(generation, k_block)` 匹配才可
   启动整数点积。

这一组织避免用 2336-bit 组合总线一次搬运完整 Q8_K block，也避免把 context SRAM 的
逐 beat 读取完全暴露在关键路径上。若 SRAM replay 不能被当前 block 计算隐藏，性能会
低于第 2 节的理想上界，但仍可由专门计数器量化。

## 7. 软件映射

### 7.1 单个矩阵

对一个被拆成多个 output tile 的矩阵：

```text
tile 0: FILL(context=0, generation=g)
tile 1..last: REUSE(context=0, generation=g)
last: RELEASE(context=0, generation=g)
```

这一步不改变 GGML 动态量化，只消除 QBS 内部重复 Q8 读取，适合作为第一版 RTL 的
独立收益验证。

### 7.2 Q/K/V 与 gate/up

后续 GGML backend 按 F32 source tensor identity、shape、activation profile 和执行 epoch
建立量化缓存：Q 或 gate 首次量化并 `FILL`；K/V 或 up 跳过 `from_float` 并引用同一
context。缓存必须绑定图执行 epoch，不能只按 data pointer 判断，因为 GGML workspace
可能在下一层复用相同地址。

Q/K/V 可使用不同 weight profile；context 只绑定 activation profile，因此 Q4_K 的 Q/K
和 Q6_K 的 V 可以共享同一个 Q8_K context。

## 8. 必须增加的证据计数器

实现前后都应保留以下严格语义：

- `qbs_context_fill_count`：成功提交的新 context 数。
- `qbs_context_reuse_count`：通过全部 metadata 检查并执行的 REUSE 命令数。
- `qbs_context_reuse_block_count`：从 context 提供给 compute 的 block 数。
- `qbs_context_read_bytes`：context SRAM 到 block adapter 的有效字节数。
- `qbs_activation_axi_bytes_saved`：按成功 REUSE 命令本应读取的激活字节数累加。
- `qbs_context_replay_cycles`：compute 等待 context block 就绪的周期。
- `qbs_context_prefetch_hidden_cycles`：context replay 与当前 block compute 重叠的周期。
- `qbs_context_validation_fault_count`：token 或 metadata 不匹配的命令数。

其中 `activation_axi_bytes_saved` 是流量收益，`context_replay_cycles` 才是暴露到关键路径
上的代价；二者不能混写成一个“context hit rate”。

## 9. 可证伪假设与定向验证

根因假设：QBS 的约 9% activation phase 主要来自每条 output-tile 命令重新获取同一份
Q8 数据；显式 context + 双缓冲 replay 可消除大部分外部读取，并把内部 replay 隐藏在
当前 block 计算下。

区分该假设与其他瓶颈需要观察：

```text
command mode / context valid / generation / metadata match
context SRAM read request, response and block-bank write
active activation bank and (generation, k_block) tag
integer tile start
AXI activation-range request
context replay wait
weight wait and FP scheduler occupancy
```

最小判别测试使用真实 `decode_attn_q` 数据，但只计算连续两个 32-output tile：第一条
`FILL`，第二条 `REUSE`。通过条件为输出逐元素与现有 QBS 完全一致、第二条无 activation
AXI range、无 stale-generation 使用，且普通 `DIRECT` 路径计数和结果不变。通过后再跑
完整 `attn_q`、裁剪 `ffn_gate`、一个 Q6_K profile 和普通 RVV 回归点。

## 10. 复现实证

```bash
python3 hardware/scripts/qbs/analyze_activation_reuse.py \
  --capture-root /home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m \
  --phase decode \
  --qbs-perf attn_q=/path/to/decode_attn_q_qbs/qbs_perf.csv \
  --metrics attn_q=/path/to/decode_attn_q_qbs/metrics.csv
```

该工具检查真实 capture 的输入哈希，并从现有 `QBS_PERF` CSV 计算重复流量和理想周期
上界。周期结果只能用来决定是否值得实现，不能作为 context 版本的最终性能结果。
