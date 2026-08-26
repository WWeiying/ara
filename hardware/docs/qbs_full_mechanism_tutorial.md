# QBS 全机制教学：从 Qwen2.5/llama.cpp 到 RVV 协同执行

> 文档状态：2026-08-26 逐项对照当前 `ara_dsa` RTL、QBS ABI、验证参考模型和本地
> llama.cpp QBS backend 核查。对应的最新 QBS RTL 基线为提交 `8260b70d`；其后的提交只更新
> ABI 生成物和本文档。本文描述的是当前可执行实现；实验性数值顺序和未来扩展会单独标注，
> 不能视作 v1 已冻结语义。

## 1. 阅读目标与一句话定位

本文希望回答六个连续的问题：

1. 文本如何经过 Qwen2.5 的 token、Attention、FFN 和 LM head 变成下一 token；
2. llama.cpp 的块量化线性层到底在计算什么，为什么普通 RVV 仍有明显开销；
3. QBS（Quantized Block Streams）把哪些软件语义显式交给硬件；
4. GGML 如何选择、重排、分块并发出 QBS 命令，何时必须回退到标准 RVV；
5. QBS 如何在不破坏普通 RVV 功能的前提下复用 MMU、AXI、sequencer、VRF 和完成域；
6. 当前方案与矩阵扩展、外置加速器、商用 CPU AI 扩展以及块量化研究之间是什么关系。

QBS 不是一种新的模型量化算法，也不是把整个 Transformer graph 固化为硬件。它是一个
**面向 GGML 块量化线性层的、命令级、profile 驱动的压缩数据流执行路径**：软件描述
量化格式、数据布局和 `M/N/K` shape，硬件直接读取压缩权重与动态量化激活，在命令内部完成
解包、整数点积、scale/min correction、FP32 累加。只有全部潜在故障访问和计算完成后，它才
通过现有 lane result port 分周期写入普通 RVV 向量寄存器；提交期间 sequencer 仍阻止年轻指令
观察部分结果，因此保持单条命令的故障原子性。

可以先记住下面这条端到端链路：

```text
GGUF 原始块量化权重
  -> 模型加载时持久化 R4 repack
  -> GGML_OP_MUL_MAT 运行时量化 activation
  -> qbinfo 能力检查与 M/N/K 分块
  -> qbexec(descriptor, activation, vd, M)
  -> QBS 读取压缩块、解码、点积、修正、FP32 累加
  -> 结果写入从 vd 开始的普通向量寄存器组（软件示例使用 v8...v11）
  -> 标准 RVV vse32.v 写回 GGML 输出 tensor
```

### 1.1 建议阅读顺序

如果目标是能够独立修改和验证 QBS，而不只是知道它“能加速量化矩阵乘”，建议按以下顺序阅读：

1. 先读第 2 至 4 节，建立量化数学、profile 和 Q8 activation 的概念；
2. 再读第 5、6 节，理解软件怎样把一个 GGML operator 转换成 descriptor 和多条命令；
3. 然后读第 7 至 10 节，沿控制、数据、完成三条路径走完 RTL；
4. 用第 11、12 节判断性能计数器，而不是从单个 utilization 数字猜瓶颈；
5. 最后用第 13 至 16 节区分功能证明、模型质量、研究贡献和未来扩展。

读完后至少应能回答四个问题：某个 weight byte 怎样参与一个 FP32 输出；为什么 R4/M4 不改变
数学结果；为什么 fault 前不能写 VRF；为什么一个不支持的 tensor 会回到普通 RVV，而不是进入
“近似兼容”的 QBS 路径。

### 1.2 三种“正确”不能混用

本文反复区分三类结论：

| 层次 | 要证明什么 | 主要证据 |
| --- | --- | --- |
| 架构正确 | 指令、异常、寄存器和内存可见行为符合 contract | canonical reference、QEMU、RTL command/fault test |
| 算术正确 | block decode、整数 subtotal 和 FP update 顺序一致 | constructed vectors、逐 accumulator bit comparison |
| 模型可用 | 合法浮点差异没有造成不可接受的模型质量变化 | logits、KL、PPL、Top-k 和生成回归 |

QEMU 跑通模型不能替代 RTL 算术证明，RTL 与 reference bit-exact 也不能自动证明长文本质量无损。
同样，microtile 加速不能直接等价为端到端 token/s 加速。

## 2. 从一句自然语言到 QBS：先完整理解 Qwen2.5 推理

QBS 位于一条很长的实现链路底部。若只观察 `Q4_K x Q8_K` 点积，很容易知道硬件“算了什么”，
却不知道这个数为什么存在、属于模型的哪一步、加速它能影响多少端到端时间。本章因此先从用户
输入的一句话开始，沿 Qwen2.5、llama.cpp、GGML、量化 kernel 一直走到 QBS。后续章节再展开
QBS 的 ISA、RTL 和验证细节。

### 2.1 大语言模型在推理时究竟做什么

以聊天为例，用户输入：

```text
请解释向量处理器。
```

模型并不是一次性“理解整句并写出整段答案”。它执行的是**自回归 next-token prediction**：

1. tokenizer 把文本转换为一串离散 token ID；
2. 模型根据全部已知 token，计算下一个位置对整个词表的分数 `logits`；
3. sampling/greedy policy 从 logits 选择一个 token；
4. 把新 token 追加到输入末尾，再计算下一个 token；
5. 遇到结束 token 或达到长度上限后停止，tokenizer 再把 token ID 解码为文本。

若已知 token 为 `t[0:S]`，模型实现的抽象函数是：

```text
logits_next = Model(t[0], t[1], ..., t[S-1])
token_next  = Sample(logits_next)
```

这里的“知识”主要存储在训练完成后的权重矩阵中。本文讨论的是**推理**：权重固定，不执行
反向传播，也不更新参数。输入变化时，变化的是 activation、attention score 和 KV cache。

#### 2.1.1 这些权重是怎样学到的

预训练时，模型看到海量 token 序列。对每个位置，它只能观察当前位置以前的 token，并预测真实
的下一个 token。若真实 token 为 `y`，训练目标通常是降低 cross entropy：

```text
p = softmax(logits)
loss = -log(p[y])
```

训练系统把许多 token 的 loss 聚合，通过 backpropagation 求每个 weight 对 loss 的梯度，再用
optimizer 更新数十亿参数。反复训练后，语言规律、事实关联和推理模式被分布式编码到 embedding、
attention 和 FFN 权重中。Instruction tuning 再用“指令-回答”数据训练模型遵循对话格式和任务
要求；偏好优化还可改变模型更倾向输出哪类回答。

训练与本文硬件推理的主要区别是：训练需要保存中间 activation、计算梯度和更新权重，计算/存储
规模远大于单次前向；推理只加载固定权重并执行 forward pass。QBS 当前是 inference-oriented
路径，不定义 gradient、optimizer 或 weight update 语义。

#### 2.1.2 从训练模型到本项目 GGUF 的生命周期

把模型“产生”和模型“运行”分开，可以避免把量化误认为训练的一部分：

```text
原始文本/代码/数学等训练数据
  -> tokenizer 形成训练 token
  -> next-token pretraining
  -> instruction tuning / preference alignment
  -> BF16/FP16 等高精度发布权重
  -> 离线 GGUF 转换与 block quantization
  -> Q4_K_M 等 GGUF 文件
  -> llama.cpp 加载并执行推理
  -> 本项目 QBS backend 选择合法的量化 MUL_MAT
```

Q4_K_M 是部署表示，不表示模型最初用 4-bit 完成训练；`_M` 还表示 llama.cpp quantizer 对不同
tensor 采用混合精度策略。模型结构决定矩阵 shape，量化方案决定这些矩阵在 GGUF 中的 block
编码和误差，QBS profile 则决定硬件如何精确消费该编码。这三个层次不能互换。

### 2.2 从字符到 token：模型真正接收的输入

token 不是固定等于一个汉字、一个英文单词或一个字节。Qwen tokenizer 使用词表把常见字符片段、
子词、标点、空格和控制标记映射为整数 ID。同一段对话还会先经过 chat template，加入“system”、
“user”、“assistant”等角色边界。概念上：

```text
messages
  -> chat template 字符串
  -> tokenizer
  -> token IDs [S]
  -> model
  -> next-token logits [V]
  -> selected token ID
  -> detokenizer
  -> 新增文本片段
```

`S` 是当前序列长度，`V` 是词表大小。本机用于 QBS 闭环的
Qwen2.5-1.5B-Instruct 配置中 `V=151936`。token ID 本身没有可计算的连续数值意义：ID 1000
不是 ID 500 的“两倍语义”。它只是 embedding table 的行号。

### 2.3 本文贯穿使用的真实 Qwen2.5 配置

本文所有具体 shape 均以本机真实 Qwen2.5-1.5B-Instruct Q4_K_M GGUF 和对应 Qwen2 配置为准，
而不是用一个虚构的缩小网络。官方配置与本机 GGUF/capture 一致的核心参数如下：

| 符号 | 配置项 | 数值 | 物理含义 |
| --- | --- | ---: | --- |
| `L` | `num_hidden_layers` | 28 | 串行执行 28 个 Decoder Transformer Block |
| `D` | `hidden_size` | 1536 | 每个 token 的内部状态有 1536 个元素 |
| `F` | `intermediate_size` | 8960 | FFN 中间状态宽度 |
| `Hq` | `num_attention_heads` | 12 | query head 数 |
| `Hkv` | `num_key_value_heads` | 2 | 共享的 key/value head 数 |
| `Dh` | head dimension | 128 | 每个 head 的特征维，`D/Hq=128` |
| `V` | `vocab_size` | 151936 | 每次预测需要给出的词表 logits 数 |
| `Smax` | `max_position_embeddings` | 32768 | 该配置声明的最大位置范围 |
| `eps` | `rms_norm_eps` | `1e-6` | RMSNorm 防止除零的稳定项 |
| `theta` | `rope_theta` | `1e6` | RoPE 位置旋转的频率基数 |

这是一种 dense、decoder-only、causal Transformer，采用 pre-RMSNorm、RoPE、Grouped-Query
Attention（GQA）、QKV bias 和 SwiGLU。`tie_word_embeddings=true` 表示输入 embedding 与输出
词表映射在逻辑模型中共享权重。量化 GGUF 如何物理保存或复制 tensor，应以实际文件为准，不能
仅凭模型配置推断存储字节数。

### 2.4 先统一 tensor 和矩阵记号

本文用“每个 token 是一行”的数学记号：

```text
X: [T, D]
W: [N, K]
Y: [T, N]
Y[m,n] = sum_k X[m,k] * W[n,k]
```

- `T`：本次 graph 中处理的 token 行数；
- `K`：输入特征/归约维；
- `N`：输出特征或输出通道数；
- `D=1536`：模型 hidden width；
- `F=8960`：FFN width。

GGML 的 `ne[0]` 是最内层连续维，日志常把同一个 tensor 打印为 `[K,T]` 或把 weight 打印为
`[K,N]`。这与本文数学写法 `[T,K]`、`[N,K]` 只是存储/显示约定不同，不是矩阵形状矛盾。
后文谈 QBS 时改用 microtile 记号 `A[M,K] x B[N,K] -> C[M,N]`，其中 `M` 就是本次命令
处理的 token/activation 行数。

### 2.5 Embedding：token ID 如何变成 1536 维状态

模型首先执行 embedding lookup：

```text
token IDs: [T]
E:         [V, D] = [151936, 1536]
X0:        [T, D]
X0[t,:] = E[token_id[t], :]
```

这不是普通矩阵乘，而是按 token ID 从大表中取行。在 llama.cpp/GGML 中通常表现为
`GET_ROWS`。每个取出的 1536 维向量是模型学习到的内部表示。单个坐标通常没有稳定的人工语义，
不应解释成“第 17 维就是名词”；信息由许多维度的联合方向和后续层共同表达。

从硬件角度看，embedding 的主要行为是离散索引读取；QBS 当前加速的是量化线性
`MUL_MAT`，不接管 `GET_ROWS`。

### 2.6 一个 Qwen Decoder Block 的全貌

28 层中的每一层都保持外部 shape `[T,1536]`。内部先通过 attention 让 token 从历史上下文取回
信息，再通过 FFN 对每个 token 的特征做非线性变换：

```text
X_l [T,1536]
  -> RMSNorm
  -> Q/K/V projections
  -> RoPE(Q,K)
  -> causal GQA attention
  -> output projection
  -> + X_l                         attention residual
  -> RMSNorm
  -> gate/up projections
  -> SiLU(gate) .* up              SwiGLU
  -> down projection
  -> + attention residual          FFN residual
  -> X_(l+1) [T,1536]
```

“Block 保持 shape 不变”很重要：层与层能直接串联；`256` 维 KV 和 `8960` 维 FFN 都只是层内
临时展开，最后分别被 attention output 和 FFN down 投影回 1536 维。

### 2.7 RMSNorm：稳定数值尺度而不改变 shape

对一个 token 的 hidden vector `x[0:D]`，RMSNorm 计算：

```text
rms(x) = sqrt((1/D) * sum_i x[i]^2 + eps)
y[i]   = weight[i] * x[i] / rms(x)
```

输入输出都是 `[T,1536]`。它的物理作用不是提取新 token 信息，而是控制进入后续大矩阵乘的
数值尺度，使不同层、不同 token 的 activation 不因幅值漂移而失稳。Qwen2.5 使用 pre-norm：
先归一化，再进入 attention/FFN；原始 `X` 保留给 residual。

硬件行为包括逐元素平方、1536 元素归约、标量开方/倒数和逐元素缩放。它是 reduction-heavy
算子，不属于 QBS 的压缩权重矩阵路径。

### 2.8 Q/K/V 投影：同一个 token 被变成“查询、索引和内容”

归一化后的 `Xn[T,1536]` 分别乘三组训练权重：

```text
Qflat = Xn * Wq^T + bq : [T,1536] x [1536,1536]^T -> [T,1536]
Kflat = Xn * Wk^T + bk : [T,1536] x [ 256,1536]^T -> [T, 256]
Vflat = Xn * Wv^T + bv : [T,1536] x [ 256,1536]^T -> [T, 256]

Q = reshape(Qflat): [T,12,128]
K = reshape(Kflat): [T, 2,128]
V = reshape(Vflat): [T, 2,128]
```

可以用检索系统类比三者，但不要把类比误认为精确定义：

- `Q`（query）描述当前 token 在当前层“希望从历史中匹配什么”；
- `K`（key）描述一个历史 token 可被匹配的特征；
- `V`（value）是匹配后真正汇聚回来的内容表示。

Qwen2.5-1.5B 使用 GQA：12 个 Q heads 共享 2 个 K/V heads，即每 6 个 Q heads 共用一组 K/V。
这样 Q 仍保留 12 组不同关注子空间，但 KV cache 容量和读取带宽相对 12 个独立 KV heads 减少
6 倍。

这三个 projection 都是量化权重线性层，是 QBS 的直接目标。真实 Q4_K_M 文件中 `attn_q`、
`attn_k` 为 Q4_K，`attn_v` 为 Q6_K，说明同一模型层内也必须支持多 profile 或可靠 fallback。

### 2.9 RoPE：把位置信息写入 Q/K 的相位

纯点积 attention 若只看 token 内容，无法区分“前一个 token”和“很早以前的 token”。RoPE 将
Q、K 的相邻特征维组成二维向量，并按 token position 和频率执行旋转：

```text
[x_2i']     [ cos(theta_i*p)  -sin(theta_i*p) ] [x_2i  ]
[x_2i+1'] = [ sin(theta_i*p)   cos(theta_i*p) ] [x_2i+1]
```

shape 不变：Q 仍是 `[T,12,128]`，K 仍是 `[T,2,128]`，V 不旋转。旋转后 Q 与 K 的点积自然
带有相对位置关系。`rope_theta=1e6` 控制不同维度的频率分布，不是一个直接加到 embedding 上的
位置编号。

RoPE 主要是三角函数/预计算系数、逐元素乘加和数据布局操作，当前由普通 GGML/RVV 路径执行。

### 2.10 GQA Attention：从历史 token 中按权重取回信息

设本次 query token 数为 `Tq`，当前可见 KV 长度为 `S`。对每个 query head `h`：

```text
score[h,q,s] = dot(Q[h,q,:], K[kv(h),s,:]) / sqrt(128)
score shape  = [12, Tq, S]
```

其中 `kv(h)=floor(h/6)`，把 12 个 Q heads 映射到 2 个 KV heads。之后：

1. causal mask 将未来位置设为不可选；
2. Softmax 沿 `S` 维把 score 转为非负且和为 1 的权重；
3. 每个 query 用这些权重对历史 `V` 做加权和；
4. 12 个 head 的 128 维输出拼接回 1536 维。

```text
P       = softmax(mask(score))        : [12,Tq,S]
HeadOut = P * V                       : [12,Tq,128]
Concat  = reshape/permute(HeadOut)    : [Tq,1536]
```

Attention 的物理意义是**内容相关的信息路由**：模型不平均读取所有历史 token，而是为当前
token 动态计算一组权重。score 和 P 都依赖运行时文本，不能像模型权重一样预先存入 GGUF。

随后执行输出投影：

```text
Aout = Concat * Wo^T : [Tq,1536] x [1536,1536]^T -> [Tq,1536]
Xatt = X + Aout      : [Tq,1536]
```

`Wo` 是 QBS 可覆盖的量化线性层；QK score、Softmax 和 P*V 属于动态 attention core，不由
当前 QBS profile 执行。

### 2.11 KV cache：为什么 Decode 不必重算所有历史 K/V

生成第 `S` 个 token 时，历史 token 的 K/V 不会因新 token 到来而改变。因此每层把已经算出的
K/V 保存到 KV cache：

```text
new K/V for one token: [2,128] + [2,128]
conceptual cache:      [layer, position, kv_head, head_dim]
```

Decode 每步只为新 token 计算一份 Q/K/V，把新 K/V 追加到 cache，再让新 Q 读取全部历史 cache。
若 cache 按 FP16 保存：

```text
每层每 token KV bytes = 2(K/V) * 2 heads * 128 * 2 bytes = 1024 bytes
28 层每 token         = 28672 bytes = 28 KiB
32768-token 全 cache  = 939524096 bytes = 896 MiB
```

这解释了 GQA 的硬件价值，也说明长上下文 Decode 会逐渐从量化权重 GEMV 转向 KV-cache 带宽和
attention core 压力。上述是按 FP16、单序列、不含 allocator/padding 的理论 payload；实际
llama.cpp cache type、对齐和多序列调度可能改变物理容量。

### 2.12 SwiGLU FFN：每个 token 独立完成的大型非线性变换

Attention residual `Xatt[T,1536]` 先经第二个 RMSNorm 得到 `Z`，然后执行：

```text
Gate = Z * Wgate^T : [T,1536] x [8960,1536]^T -> [T,8960]
Up   = Z * Wup^T   : [T,1536] x [8960,1536]^T -> [T,8960]
Mid  = SiLU(Gate) .* Up                         -> [T,8960]
Down = Mid * Wdown^T: [T,8960] x [1536,8960]^T -> [T,1536]
Xnext = Xatt + Down                             -> [T,1536]
```

`SiLU(x)=x*sigmoid(x)`；`.*` 是逐元素乘，不是矩阵乘。Gate 分支像一个由输入决定的连续开关，
控制 Up 分支的哪些特征和幅度通过。FFN 不在 token 间交换信息；每个 token 独立执行同一组权重，
主要作用是把 attention 取回的信息映射到更宽的特征空间，经非线性组合后压回 hidden space。

三次 FFN projection 占单层固定线性 MAC 的 88.24%，是 QBS 优先覆盖量化线性层的最直接理由。
`ffn_gate/up` 的真实权重为 Q4_K，`ffn_down` 为 Q6_K；SwiGLU 本身仍走普通 RVV/标量路径。

### 2.13 28 层之后：LM head 如何产生下一个 token

第 28 层输出经最终 RMSNorm 后，最后一个有效 token 的 1536 维 hidden state 被映射到词表：

```text
h_last: [1,1536]
W_vocab: [151936,1536]
logits = h_last * W_vocab^T: [1,151936]
```

每个 logit 是对应词表 token 的未归一化分数。Sampling 通常还会应用 temperature、top-k、top-p、
repetition penalty 等策略，再选出 token。这些策略改变“如何从分布选 token”，不改变前面 28 层
的网络计算。

LM head 在 Decode 每生成一个 token 都要执行一次，理论上有 `1536*151936=233,373,696` MAC。
逻辑 tied embedding 允许它与输入 embedding 共享参数，但输入阶段是行查找，输出阶段仍是大矩阵
向量乘，计算量不会因共享权重自动消失。

### 2.14 Prefill 与 Decode：同一个模型的两种硬件形态

推理分为两个阶段：

| 阶段 | 输入 | 主要目的 | 线性层形态 | Attention 特征 |
| --- | --- | --- | --- | --- |
| Prefill | 整段 prompt 的 `T>1` tokens | 建立所有层的 prompt KV cache，并得到首个输出分布 | 多 activation rows，GEMM/小 M GEMM | causal attention，计算量随 prompt 长度近似二次增长 |
| Decode | 每次一个新 token，`Tq=1` | 逐 token 生成 | GEMV，`M=1` | Q 读取不断增长的 KV cache，带宽随上下文增长 |

对某个线性层，weight shape 不变；变化的是 activation 行数：

```text
Prefill: A[T,K] x W[N,K] -> C[T,N]
Decode:  A[1,K] x W[N,K] -> C[1,N]
```

Prefill 能让一块 weight 被多行 activation 复用，算术强度较高；Decode 每个 token 都要重新扫描
大量权重，通常更受 weight bandwidth 和低比特解码开销影响。QBS 因此同时提供 M1 GEMV 与
M1..M4 micro-GEMM，而不是只优化一个固定 batch shape。

#### 2.14.1 一层完整 shape ledger

下面把前述步骤压到一张表中。`Tq` 是本次计算的 query token 数，`S` 是加入当前 K/V 后的逻辑
可见长度。Fresh 15-token Prefill 中 `Tq=15`、最大逻辑 `S=15`，causal mask 让第 `q` 行只看
`0..q`；Prefill 的最后一行 logits 选出首个新 token，把该 token 作为下一次模型输入时，Decode
才取 `Tq=1`、`S=16` 并继续预测第二个新 token。

| 阶段 | 数学输入 | 数学输出 | Fresh Prefill 示例 | Decode 示例 | 信息/硬件含义 |
| --- | --- | --- | --- | --- | --- |
| Embedding | IDs `[Tq]` | X `[Tq,1536]` | `[15,1536]` | `[1,1536]` | indexed row read |
| Attention RMSNorm | `[Tq,1536]` | `[Tq,1536]` | `[15,1536]` | `[1,1536]` | 1536-element reduction/scale |
| Q projection | `[Tq,1536]` | `[Tq,1536]` | `[15,1536]` | `[1,1536]` | Q4_K linear |
| Q reshape | `[Tq,1536]` | `[Tq,12,128]` | `[15,12,128]` | `[1,12,128]` | 12 query heads |
| K projection/reshape | `[Tq,1536]` | `[Tq,2,128]` | `[15,2,128]` | `[1,2,128]` | 2 shared key heads |
| V projection/reshape | `[Tq,1536]` | `[Tq,2,128]` | `[15,2,128]` | `[1,2,128]` | 2 shared value heads |
| RoPE | Q/K | 同 shape Q/K | 不变 | 不变 | 写入 position-dependent phase |
| KV append/view | 新 K/V | K/V `[S,2,128]` | `[15,2,128]` | `[16,2,128]` | persistent cache state |
| QK score | Q 与 K cache | `[12,Tq,S]` | `[12,15,15]` | `[12,1,16]` | 12 组动态 dot products |
| Mask/Softmax | score | P `[12,Tq,S]` | 同 shape | 同 shape | causal probability weights |
| P*V | P 与 V cache | `[Tq,12,128]` | `[15,12,128]` | `[1,12,128]` | history value aggregation |
| Head concat | `[Tq,12,128]` | `[Tq,1536]` | `[15,1536]` | `[1,1536]` | layout/reshape |
| O projection | `[Tq,1536]` | `[Tq,1536]` | `[15,1536]` | `[1,1536]` | Q4_K linear |
| Attention residual | 两个 `[Tq,1536]` | `[Tq,1536]` | `[15,1536]` | `[1,1536]` | elementwise add |
| FFN RMSNorm | `[Tq,1536]` | `[Tq,1536]` | `[15,1536]` | `[1,1536]` | reduction/scale |
| Gate projection | `[Tq,1536]` | `[Tq,8960]` | `[15,8960]` | `[1,8960]` | Q4_K linear |
| Up projection | `[Tq,1536]` | `[Tq,8960]` | `[15,8960]` | `[1,8960]` | Q4_K linear |
| SwiGLU | Gate、Up | `[Tq,8960]` | `[15,8960]` | `[1,8960]` | SiLU + elementwise multiply |
| Down projection | `[Tq,8960]` | `[Tq,1536]` | `[15,1536]` | `[1,1536]` | Q6_K linear |
| FFN residual | 两个 `[Tq,1536]` | `[Tq,1536]` | `[15,1536]` | `[1,1536]` | 下一层输入 |

本项目 capture 中 K/V tensor 可显示为 `[128,256,2]`，其中 256 是预分配 view 容量/stride，
不是每个 case 都有 256 个有效历史 token。有效范围由 cache index 和 mask 决定。做硬件流量分析时，
必须区分 logical `S`、tensor capacity 和实际发出的 memory transactions。

### 2.15 Qwen2.5-1.5B 的计算量：哪些矩阵真正占大头

下面先只统计**每个 Decode token、每层七个固定 projection 的 MAC**。一个 MAC 是一次乘法加
一次累加；若论文以 FLOP 计，常近似记为 2 FLOPs/MAC。bias、RMSNorm、RoPE、Softmax、逐元素
运算和地址/搬运未计入本表。

| Projection | 数学 shape `N x K` | 每层 MAC | 固定线性 MAC 占比 |
| --- | ---: | ---: | ---: |
| Q | `1536 x 1536` | 2,359,296 | 5.04% |
| K | `256 x 1536` | 393,216 | 0.84% |
| V | `256 x 1536` | 393,216 | 0.84% |
| Attention output | `1536 x 1536` | 2,359,296 | 5.04% |
| FFN gate | `8960 x 1536` | 13,762,560 | 29.41% |
| FFN up | `8960 x 1536` | 13,762,560 | 29.41% |
| FFN down | `1536 x 8960` | 13,762,560 | 29.41% |
| **每层合计** | - | **46,792,704** | **100%** |

因此：

```text
每层 FFN projections       = 41,287,680 MAC = 88.24%
每层 Attention projections =  5,505,024 MAC = 11.76%
28 层固定 projections      = 1,310,195,712 MAC/token
LM head                    =   233,373,696 MAC/token
二者合计                   = 1,543,569,408 MAC/token
```

若把 LM head 也放入这个“固定线性 MAC”分母，28 层 FFN、28 层 attention projection、LM head
分别约占 74.9%、10.0%、15.1%。这不是端到端周期占比：低比特格式每个 MAC 的实际代价不同，
memory traffic、activation quantization 和非线性算子也会消耗周期。

### 2.16 Attention core 的计算量为什么随上下文变化

Decode 时每层 attention score 和 value aggregation 各约执行 `Hq*S*Dh` MAC，因此：

```text
Attention core MAC/layer/token ~= 2 * 12 * S * 128 = 3072*S
```

| 当前上下文 `S` | Attention core MAC/层 | 相对该层固定 projection MAC |
| ---: | ---: | ---: |
| 256 | 786,432 | 1.68% |
| 1024 | 3,145,728 | 6.72% |
| 4096 | 12,582,912 | 26.89% |
| 16384 | 50,331,648 | 107.56% |
| 32768 | 100,663,296 | 215.13% |

这张表解释了两个看似矛盾的判断为何都成立：短上下文时量化 FFN/GEMV 是主要工作，QBS 的目标
很合理；长上下文时 attention/KV cache 可能成为主要瓶颈，仅优化量化权重线性层不足以保证端到端
token/s 同比例提高。

Prefill 的 causal attention 对 `T` 个 prompt tokens 访问一个三角区域，QK 与 P*V 的总工作量
近似按 `O(T^2)` 增长；七个 weight projections 则近似按 `O(T)` 增长。因此任何“算子占比”都必须
同时报告 prompt 长度、decode context、batch 和线程/后端配置。

### 2.17 参数占比、MAC 占比、时间占比不能混为一谈

硬件分析常见三种“占比”：

| 占比 | 分子/分母 | 能回答的问题 | 不能直接回答的问题 |
| --- | --- | --- | --- |
| 参数/权重元素占比 | 某组 weight elements / 全部 parameters | 模型容量主要存在哪里 | 实际运行多久、压缩后占多少 bytes |
| MAC 占比 | 某算子理论 MAC / 指定范围总 MAC | 理想算术工作量结构 | unpack、cache miss、reduction、频率和并行度 |
| 实测时间占比 | 某算子周期/时间 / 端到端周期/时间 | 当前平台真正的 Amdahl 比例 | 换 shape、后端或缓存后是否仍相同 |

对这一 Qwen 配置，每层七个 projection 的 weight element 数与每个 Decode token 的 MAC 数相同，
所以 FFN 在**该局部分母**中的参数元素和 MAC 占比都是 88.24%。但 Q4_K_M 混合使用 Q4_K/Q6_K，
因此存储字节占比不同；算子运行时间还取决于 profile decode 和内存系统。本文的 88.24% 是解析
shape 得到的固定 projection MAC 占比，不是 profiler 给出的 88.24% 端到端周期。

### 2.18 llama.cpp 如何把模型公式变成可执行 graph

llama.cpp 不是手写一个 `qwen_forward()` C 循环后立即逐句计算。其主要层次是：

```text
GGUF loader
  -> 读取 metadata、tensor type/shape/data
Qwen2 model implementation
  -> 根据架构构建 GGML tensor graph
GGML graph
  -> operator nodes + tensor views + dependencies
backend scheduler
  -> 选择 CPU/accelerator backend，规划 buffer 和执行顺序
operator implementation
  -> MUL_MAT / RMS_NORM / ROPE / SOFTMAX / elementwise kernel
architecture microkernel
  -> scalar / RVV / QBS backend
ISA and RTL
  -> load, vector instructions, qbinfo/qbexec, memory and VRF
```

本机当前 `src/models/qwen2.cpp` 的实际 graph 构建顺序与第 2.6 节一致：

1. `build_inp_embd()` 构造 token embedding；
2. 每层 `build_norm(..., LLM_NORM_RMS)`；
3. `build_qkv()` 分别构造 Q/K/V `MUL_MAT` 和 bias；
4. `ggml_rope_ext()` 处理 Q/K；
5. `build_attn()` 处理 KV cache、attention core 和 `Wo`；
6. `ggml_add()` 形成 attention residual；
7. 第二个 RMSNorm；
8. `build_ffn(..., LLM_FFN_SILU, LLM_FFN_PAR)` 形成并行 gate/up、SiLU、逐元素乘和 down；
9. 第二个 `ggml_add()` 形成 FFN residual；
10. 最终 RMSNorm 和 `build_lora_mm(output, cur)` 形成 logits。

这里的 graph node 描述“结果依赖谁”，不是 RTL clock cycle。`reshape/view/permute` 可能只是修改
tensor metadata，也可能因连续性要求引入 copy；是否消耗大量周期取决于 backend 实现。

### 2.19 模型数学到 GGML operator 的对应表

| 模型步骤 | 典型 GGML 行为 | 输入 -> 输出 shape | 主要底层行为 | QBS v1 |
| --- | --- | --- | --- | --- |
| Token embedding | `GET_ROWS` | `[T] -> [T,1536]` | indexed gather | 不覆盖 |
| RMSNorm | `RMS_NORM` + `MUL` | `[T,1536] -> [T,1536]` | square/reduce/scale | 不覆盖 |
| Q/K/V/O projection | `MUL_MAT`，QKV 后接 `ADD` | `[T,K] -> [T,N]` | quantized GEMV/GEMM | 覆盖合法量化 weight |
| RoPE | `ROPE` | head tensor -> 同 shape | rotate element pairs | 不覆盖 |
| QK score | `MUL_MAT`/attention kernel | Q,K -> `[Hq,Tq,S]` | dynamic FP dot | 不覆盖 |
| Mask/Softmax | mask + `SOFT_MAX` | score -> probability | exp/reduction/divide | 不覆盖 |
| P*V | `MUL_MAT`/attention kernel | P,V -> head output | dynamic FP matmul | 不覆盖 |
| Residual | `ADD` | 两个 `[T,1536]` -> 同 shape | elementwise add | 不覆盖 |
| FFN gate/up/down | `MUL_MAT` | `[T,K] -> [T,N]` | quantized GEMV/GEMM | 覆盖合法量化 weight |
| SwiGLU | `SILU` + `MUL` | 两个 `[T,8960]` -> `[T,8960]` | nonlinear + elementwise | 不覆盖 |
| LM head | `MUL_MAT` | `[T,1536] -> [T,V]` | large quantized GEMV/GEMM | type/shape/capability 合法时可覆盖 |
| Sampling | CPU sampling pipeline | logits `[V]` -> token ID | penalty/top-k/top-p/RNG | 不覆盖 |

“总共有多少算子”没有脱离 graph shape 的固定答案：28 层会重复上述模板，llama.cpp 还可能把
attention 融合为 flash-attention node、按 microbatch 分图、插入 copy/cont/view，或只对最后
token 计算 logits。研究时应把**数学算子类别**、**GGML graph node 数**和**底层 kernel 调用数**
分别统计。

若只按 Qwen 数学模板计数，不考虑 backend fusion 和 view/copy，每次完整 forward 包含：

| 数学操作类别 | 每层次数 | 28 层次数 | 层外次数 | 说明 |
| --- | ---: | ---: | ---: | --- |
| 固定权重 projection | 7 | 196 | LM head 1 次 | Q/K/V/O + gate/up/down |
| RMSNorm | 2 | 56 | final norm 1 次 | 共 57 次 |
| RoPE | 2 | 56 | 0 | Q 和 K 各一次 |
| Attention dynamic matmul | 2 | 56 | 0 | QK 与 P*V |
| Residual add | 2 | 56 | 0 | attention 与 FFN 各一次 |
| Softmax | 1 | 28 | 0 | 沿可见 KV 序列归一化 |
| SwiGLU nonlinear | 1 | 28 | 0 | SiLU(gate) 与 up 的逐元素乘 |

一次“数学操作”可能被切成很多底层命令。例如 Decode `ffn_gate` 的 N=8960 会按 N<=32 发出许多
QBS commands；反过来，flash attention 又可能把 QK、mask、Softmax 和 P*V 融合为较少 kernel。
所以性能计数必须注明统计层次。

### 2.20 `MUL_MAT` 如何继续下沉为量化 microkernel

以 Decode `ffn_gate` 为例：

```text
模型语义:
  [1,1536] F32 activation x [8960,1536] Q4_K weight -> [1,8960] F32

GGML:
  GGML_OP_MUL_MAT
  -> 根据 weight type/shape/backend 选择 trait
  -> activation 从 F32 动态量化为 Q8_K
  -> 遍历 8960 个 output rows

传统单输出 microkernel:
  每个 output row 执行 ggml_vec_dot_q4_K_q8_K(K=1536)

QBS backend:
  模型加载时把 weight 持久化 R4 repack
  -> 运行时把 M 行 activation 量化/布局
  -> N<=32、M<=4、K-block 分命令
  -> qbexec 直接计算 MxN 量化线性 microtile
```

QBS 不是跳过 GGML，也不是把 Qwen Block 固化进 RTL。它替换的是 `MUL_MAT` 中一段满足
profile/shape/capability 条件的底层执行路径。RMSNorm、RoPE、attention、SwiGLU、residual 和
sampling 仍按原 graph 执行，因此普通 RVV 功能和 fallback 始终是完整模型可运行的基础。

### 2.21 块量化为什么不能只看“4-bit 乘 8-bit”

llama.cpp/GGUF 不只保存低比特整数。一个块通常同时包含：

- packed low-bit payload；
- block scale；
- 某些格式的 subgroup scale；
- 某些格式的 minimum/zero-point correction；
- 动态激活块的 scale 和辅助和 `bsums`。

因此一个量化点积不是单纯 `int4 * int8`。软件需要读取元数据、拆 bit-plane、恢复有符号值、
按 subgroup 归约、计算 correction，再把整数结果转换并缩放到 FP32 accumulator。低比特权重
减少模型容量和 weight traffic，却增加 unpack、metadata、correction 和 reduction 工作；“每个
weight 约 4 bit”不意味着硬件只需一个 4x8 multiplier。

### 2.22 标准 RVV 的价值、开销与 QBS 的切入点

RVV 1.0 提供 VLA（vector-length agnostic）编程模型，软件通过 `vsetvl*` 在不同 VLEN 上
strip-mine，使用 32 个向量寄存器完成加载、整数运算、归约和浮点运算。它仍是 QBS 的正确性
基线和通用 fallback。

但对 llama.cpp 块量化内核，纯 RVV 往往仍要显式执行：

```text
packed bytes load
 -> mask/shift/unpack/high-bit merge/table lookup
 -> scale/min metadata decode
 -> vector widening multiply-accumulate
 -> vector reduction to scalar or short vector
 -> integer-to-float conversion
 -> scale/min floating-point update
 -> repeat for each output row
```

同一 activation block 会被许多输出行重复消费；Prefill 时同一 weight block 又会被多个 token
rows 消费。若每个输出行都从“单点积”开始，格式解析、activation 递送和 reduction 控制会反复
出现。QBS 的优化对象正是这个**完整量化线性 microtile**，不是只替换一个乘法器。

### 2.23 当前项目中的真实数据怎样放回这条链路

本项目不只保存了合成 block。真实 Qwen2.5-1.5B Q4_K_M capture 固定了 layer 0 的 Prefill
`T=15` 和 Decode `T=1` 数据，并拆成 36 个可独立回放的叶子：

| 层次 | 数量 | 内容 |
| --- | ---: | --- |
| Micro | 6 | F32->Q8_K 与 Q4_K/Q6_K x Q8_K 点积 |
| 量化线性 operator | 14 | Prefill/Decode 各 7 个 Q/K/V/O/gate/up/down |
| 非线性/数据流 operator | 16 | 两阶段各 8 个 norm、RoPE、attention core、residual、SwiGLU |

这 36 个叶子能回答“某个局部 kernel 是否正确”，完整 block suite 能回答“按模型顺序组合后是否
正确”，整模型 QEMU/llama.cpp 则回答“真实 graph dispatch、fallback 和 token generation 是否
成立”。三者不能相互替代。

严格配对的真实 Decode `attn_q` 切片还给出了当前标准 RVV 与 QBS 的算子级性能数据。前三行
来自 1.5B 模型，Q8_0 行来自 hidden size 为 896 的 Qwen2.5-0.5B，因而只用于验证该 profile，
不能与前三行做同 shape 的格式优劣比较：

| Weight | Model | `K x N x M` | RVV/QBS matmul cycles | Matmul speedup | QBS/RVV 逻辑读取 |
| --- | --- | --- | ---: | ---: | ---: |
| Q3_K | Qwen2.5-1.5B | `1536 x 256 x 1` | 1,281,131 / 17,614 | 72.73x | 30.3% |
| Q5_K | Qwen2.5-1.5B | `1536 x 256 x 1` | 2,011,748 / 21,750 | 92.49x | 40.1% |
| Q6_K | Qwen2.5-1.5B | `1536 x 256 x 1` | 1,273,230 / 25,120 | 50.69x | 44.1% |
| Q8_0 | Qwen2.5-0.5B | `896 x 256 x 1` | 548,583 / 26,923 | 20.38x | 51.9% |

这些数来自 `hardware/format_closure.csv`，两侧 source weight、activation、golden 和 shape 严格
配对，全部 PASS 且 mismatch 为 0；离线 R4 repack 不计入周期。它们证明当前 microtile 路径
确实消除了大量 RVV unpack/reduction 工作，但**不是完整 Qwen token/s 加速比**：表中只取一个
量化线性算子切片，未包含前述 28 层其余算子、LM head、KV cache、sampling 和软件运行时。

整模型功能闭环中，10-token prompt 加 2-token greedy generation 的 trace 记录到 Q4_K
`gemv/gemm=8032/2656`、Q6_K `gemv/gemm=1360/432`。这些是 GGML 进入新 backend 的调用证据，
不是 RTL 周期数据。模型级数值结果和六种 profile 的 PPL/KL/Top-k 数据见第 13.9 节。

到这里，模型侧的因果链已经完整：自然语言变为 token，token 经 28 层 attention/FFN 变为
logits；七个量化 projection 构成每层固定乘加的主体；GGML 将它们表示为 `MUL_MAT`；量化
backend 再把 `MUL_MAT` 降为 block dot/microtile。第 3 节开始讨论 QBS 如何在保留这条软件链路
和普通 RVV fallback 的前提下，把 block 语义安全地交给硬件。

## 3. QBS 的核心设计原则

### 3.1 三层契约

QBS 把机制拆为三层，避免将模型名称、GGUF 位布局和硬件 datapath 绑死：

| 层次 | 描述内容 | 当前载体 |
| --- | --- | --- |
| Format/profile | block 字节数、元素数、subgroup、scale、correction、激活配对 | `config/qbs_abi.json` |
| Layout | 权重/激活如何按行、K block 和 M/N tile 排列 | descriptor + GGML repack |
| Shape/command | `M`、`N`、`K-blocks`、地址、目的寄存器和舍入模式 | `qbexec` + descriptor |

这种拆分带来两点通用性：

1. 同一硬件调度骨架可以接多个量化 profile，而不是每种 GGUF type 建一套独立 engine；
2. unsupported format、layout 或 shape 可以由软件在命令发出前回退，不影响普通 RVV 程序。

### 3.2 命令局部状态，不增加长期架构状态

QBS 内部有 block buffer、整数 subtotal、FP update table 和 128 个 FP32 accumulator，但这些
状态只在一条 `qbexec` 生命周期内存在。命令成功后结果进入普通 VRF；命令失败则不提交。
软件不需要保存或恢复独立 tile register file，也不能跨命令观察内部 accumulator。

这与 Intel AMX 的八个 1 KiB architectural tile registers 不同，也与 RISC-V Attached Matrix
Extension 所设想的独立 matrix state 不同。QBS 更接近“附着在现有向量完成域内的长命令”。

### 3.3 复用 RVV，而不是替代 RVV

QBS 与 RVV 的关系是：

- **ISA 共存**：普通 RVV 指令解码、lane、VLSU 和 sequencer 行为保留；QBS 未启用时不选新路径。
- **软件共存**：同一 GGML operator 有 QBS trait 和标准 RVV trait；能力或 shape 不匹配即回退。
- **状态共存**：QBS 输出是普通 FP32 vector register 内容，后续使用标准 `vse32.v`。
- **资源复用**：QBS 复用 CVA6/Ara 的虚拟地址翻译、PMA、AXI、异常报告、vid 完成和 VRF 写回域。
- **执行互斥**：当前实现不是 QBS 与普通 VLSU 并发运行；一条 QBS 命令期间 QBS 独占相关接口。

RTL 还受 `ARA_QBS_ENABLE` 编译开关控制；关闭时普通 RVV 数据通路仍按原设计工作。启用后 QBS
内部时钟只在 command valid/active 时打开，idle 的 block storage 和 FP scheduler 不持续翻转。

最后一点很重要。当前“合理并存”是**明确仲裁和架构兼容**，不是宣称两条访存路径同时工作。

### 3.4 控制、数据和完成三条路径

理解 QBS 时应把三条路径分开，再观察它们在命令边界处如何汇合：

```text
控制路径: GGML shape -> descriptor/qbexec -> dispatcher -> sequencer vid -> QBS FSM
数据路径: weight/activation VA -> MMU/PMA -> AXI -> block adapter -> integer/FP pipeline
完成路径: hidden accumulators -> atomic commit -> LDU result port -> lane VRF -> vid terminal
```

- 控制路径决定“允许做什么”，包括 profile、layout、M/N/K 和目的寄存器组；
- 数据路径决定“实际读到什么”，包括翻译、burst、range tag、block 边界和格式解码；
- 完成路径决定“程序何时能看见结果”，包括 VRF grant、`fflags`、success 和 fault。

很多错误来自把三者混在一起。例如 descriptor 合法只证明控制路径接受了命令，不证明 payload
读取成功；FP accumulator 有结果也不意味着架构结果已经可见；AXI 已返回全部数据也不意味着
整数和 FP pipeline 已经排空。

### 3.5 当前实现必须保持的六条不变量

下面六条比具体状态名更接近 QBS 的设计骨架：

1. **先验证后读 payload**：非法 descriptor 不得触发 weight/activation 越界访问；
2. **单一资源所有者**：QBS active 时，QBS 与普通 VLSU 不能同时驱动 MMU、AXI 或 result port；
3. **range 和 response 可归属**：每个返回 beat 必须能映射到已发出的 descriptor、activation 或
   weight range，并满足 RRESP/RLAST；
4. **同一 accumulator 更新有序**：不同 block 对同一 FP32 partial sum 的更新不能任意重排；
5. **fault 前不可见**：任何 payload fault 都只能丢弃 hidden state，不能留下部分 VRF 结果；
6. **terminal 后才释放命令**：success/fault 被 sequencer 接收后，vid、VLSU 所有权和命令局部
   buffer 才能回收。

RTL assertion 和验证用例应围绕这些不变量组织。新增 prefetch、更多 outstanding、activation
quantizer 或跨命令复用时，也必须逐条重新证明。

### 3.6 QBS 是否属于数据流架构

准确说，QBS 在一条命令内部使用**有界的压缩块流数据流**：block 到达后依次经过 decode、整数
点积、correction、FP update，结果驻留在命令局部 accumulator；调度由数据有效性和资源 ready
共同推进。但它不是 graph-level dataflow processor，也没有让多个 Transformer operator 以 token
形式在独立节点间自由流动。命令之间仍由标量软件和 sequencer 按程序顺序组织。

因此 QBS 的定位应是“带 command-local dataflow 的 RVV 协同执行路径”，而不是泛称为完整
数据流处理器。

### 3.7 核心设计思想：传递结构化语义，而不是增加一个孤立乘法指令

QBS 的核心不是“把 RVV 的乘法器换成更宽的乘法器”，而是改变软硬件之间的工作划分。普通
RVV 只看到 load、mask、shift、widening multiply、reduction 和 scalar update 等逐条指令；
weight block 属于哪种格式、哪些 metadata 共同描述一个 subgroup、同一 activation 将被多少
output rows 复用，这些信息已经在 GGML kernel 中存在，却在进入硬件前被展开成了长指令流。

QBS 保留这些高层但仍具有通用边界的语义，并通过 profile、layout 和 shape 三层 contract 一次
交给硬件：

1. **Profile 描述数学**：block bytes、quant 位布局、scale/min correction 和 activation 配对
   决定每个 block 的严格数值含义；
2. **Layout 暴露数据邻接**：R4/M4 使硬件知道哪些 weight/activation block 可作为一个连续 tile
   读取和复用，而不依赖地址流猜测；
3. **Shape 给出复用边界**：`M/N/K-blocks` 明确一条命令内 activation、weight 和 accumulator
   的生命周期；
4. **命令局部数据流执行**：压缩数据从 memory 直接进入 decoder、整数点积、correction 和
   FP32 accumulator，不先物化完整解量化 tensor；
5. **标准向量状态收口**：结果仍提交到普通 VRF，异常、`fflags`、依赖和 fallback 仍进入现有
   RVV 系统边界。

这种设计选择了一个有意受限的抽象层次。它比单条 dot-product 指令更能消除完整 block kernel
的控制、解包和 reduction 开销，又不像固定 Transformer engine 那样认识 Qwen layer 名称或整张
graph。新增格式主要扩展 profile decoder 和软件 trait；不支持的格式或 shape 则回到标准 RVV。
因此 QBS 的通用性来自“可查询、可版本化、可回退的块语义”，而不是声称一条命令能覆盖所有
LLM 算子。

## 4. 当前支持的量化 profile

### 4.1 Profile 总表

ABI v1 支持九组严格的权重/激活配对：

| Weight profile | ID | Bytes/block | Elements | Subgroups | Group size | Activation | Correction |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Q2_K | 7 | 84 | 256 | 16 | 16 | Q8_K | affine min |
| Q3_K | 5 | 110 | 256 | 16 | 16 | Q8_K | none |
| Q4_K | 1 | 144 | 256 | 8 | 32 | Q8_K | affine min |
| Q5_K | 4 | 176 | 256 | 8 | 32 | Q8_K | affine min |
| Q6_K | 2 | 210 | 256 | 16 | 16 | Q8_K | none |
| Q4_0 | 3 | 18 | 32 | 1 | 32 | Q8_0 | none |
| Q5_0 | 8 | 22 | 32 | 1 | 32 | Q8_0 | none |
| Q8_0 weight | 6 | 34 | 32 | 1 | 32 | Q8_0 | none |
| IQ4_NL | 9 | 18 | 32 | 1 | 32 | Q8_0 | nonlinear table |

激活 profile：

| Activation | Bytes/block | Elements | Scale | Quant payload | Auxiliary data |
| --- | ---: | ---: | --- | ---: | --- |
| Q8_K | 292 | 256 | FP32, 4 B | 256 signed bytes | 16 x int16 `bsums` |
| Q8_0 | 34 | 32 | FP16, 2 B | 32 signed bytes | none |

这些字节数和配对来自当前 `qbs_abi.json`，而不是根据格式名字推断。新增 profile 必须同时更新
ABI 生成物、参考模型、RTL decoder、QEMU、GGML trait 和验证向量。

### 4.2 三类数学模板

#### A. 带 min correction 的 K-quant：Q2_K/Q4_K/Q5_K

对某个 weight block 和 activation block，先按 subgroup 形成整数结果：

```text
dot_g = sum_i q_w[g,i] * q_a[g,i]
aux_g = sum_i q_a[g,i]                 // 来自 Q8_K bsums
D     = sum_g scale_g * dot_g
AUX   = sum_g min_g   * aux_g
```

然后按数值 contract 将整数 subtotal 转为 FP32，并应用 block scale：

```text
sd = fp32(weight.d)    * activation.d
sm = fp32(weight.dmin) * activation.d
acc = fma(sd, fp32(D), acc)
acc = fma(-sm, fp32(AUX), acc)
```

这解释了为什么 `bsums` 不是可选元数据：它使 min correction 不必重新遍历 activation。

#### B. 仅 scale 的 K-quant：Q3_K/Q6_K

```text
D   = sum_g signed_scale_g * dot_g
sd  = fp32(weight.d) * activation.d
acc = fma(sd, fp32(D), acc)
```

Q3_K 的 3-bit 值由 low plane 和 high mask 恢复；Q6_K 的 6-bit 值由 low/high plane 合并后
减去 32。硬件 profile decoder 负责 exact bit layout，不先生成完整 FP32 权重块。

#### C. 32-element profile：Q4_0/Q5_0/Q8_0/IQ4_NL

```text
D   = sum_i q_w[i] * q_a[i]
sd  = fp32(weight.d) * fp32(activation.d)
acc = fma(sd, fp32(D), acc)
```

- Q4_0 的 nibble 解码后减 8；
- Q5_0 合并 4-bit low plane 和 1-bit high plane，再减 16；
- Q8_0 weight 直接读取 signed int8；
- IQ4_NL 用 4-bit index 查固定 16-entry 非线性码本。

### 4.3 当前数值顺序与实验边界

`numerical_contract_version=1` 当前对 affine profile 使用“正 dot 更新在前、min correction 在后”
的两次 FP32 FMA。`qbs_ref.c`、RTL FP accumulator 和 QEMU canonical model 以此为准。

已经进行过让 Q2_K min correction 先执行的实验；短测试显示它可能更接近当前 RVV 的求和顺序，
但这仍不是生产 contract。不同 profile 的 llama.cpp/RVV 累加组织并不完全相同，例如 Q5_K
可能分别累计 correction 和 positive contribution，因此不能用一次全局交换假定所有格式都
bit-identical。若未来更改顺序，必须提升 numerical contract version，并同步参考模型、RTL、
QEMU、GGML 能力检查和整模型质量验证。

### 4.4 两个最小算术例子

先看没有 correction 的 Q4_0。真实 block 有 32 个元素；下面只展示四个非零位置，其余位置视为
零，以便看清数据流。假设 nibble 解码并减 8 后得到：

```text
weight quant      qw = [ 1, -1, 2, 0 ]
activation quant  qa = [ 3, -2, 1, 4 ]
weight scale      dw = 0.25
activation scale  da = 0.50
```

整数路径先计算：

```text
D = 1*3 + (-1)*(-2) + 2*1 + 0*4 = 7
```

FP 路径再做一次 contract update：

```text
sd  = dw * da = 0.125
acc = fma(sd, fp32(D), acc)       // acc 初始为 0 时得到 0.875
```

硬件没有先生成四个 FP32 weight 再相乘；低比特点积在整数域完成，只在 block subtotal 边界进入
FP pipeline。这是 QBS 减少解量化工作量的核心。

再看 affine profile。假设一个 block 汇总得到 `D=40`、`AUX=6`、`sd=0.125`、`sm=0.03125`：

```text
acc = fma( sd, 40.0, 0.0) = 5.0000
acc = fma(-sm,  6.0, acc) = 4.8125
```

这里 `D` 来自 `quant_weight * quant_activation` 的 group dot，`AUX` 来自 Q8_K `bsums` 与 group
minimum metadata。第二项不是误差修补，而是 affine weight 表达式本身的一部分。交换两次 FMA
在实数数学中等价，但在 FP32 舍入下未必 bit-identical，所以执行顺序属于 numerical contract。

## 5. ISA 与 ABI

### 5.1 两条指令

QBS 使用 custom-2 opcode `0x5b`：

| 指令 | funct3 | 作用 |
| --- | ---: | --- |
| `qbinfo` | 1 | 查询架构版本、contract、shape 上限、profile/layout 支持和对齐要求 |
| `qbexec` | 0 | 启动一条阻塞式量化 block-stream 命令 |

当前工具链尚以 raw `.word` 发出 `qbexec`。软件包装器固定使用：

```text
rs1 = 16-byte descriptor 地址
rs2 = activation base 地址
vd  = FP32 输出向量寄存器组起点
funct7[1:0] = M - 1
```

`M=1/2/3/4` 分别占用 1/2/4/4 个 architectural vector registers。`M=3` 仍按 LMUL=4 对齐并
保留第四个寄存器，但只提交三行有效结果。

### 5.2 Descriptor v1

descriptor 固定 16 B、16 B 对齐：

```c
struct qbs_descriptor_v1 {
    uint64_t header;
    uint64_t weight_base;
};
```

header 位域：

| Bits | 字段 | 编码 |
| --- | --- | --- |
| 3:0 | descriptor version | 当前为 1 |
| 7:4 | weight profile | profile ID |
| 11:8 | activation profile | profile ID |
| 15:12 | weight layout | row-major 或 R4 block-major |
| 19:16 | activation layout | row-major 或 M4-interleaved |
| 24:20 | `N-1` | 1..32 |
| 32:25 | `K-blocks-1` | 1..256 |
| 63:33 | reserved | 必须为 0 |

`M` 不放在 descriptor 中，而在指令 encoding 中；activation base 由 `rs2` 传入；目的向量组由
`vd` 传入。这使 descriptor 可在调用点临时构造，同时让 register dependency 对 sequencer 可见。

### 5.3 `qbinfo` 为什么不可省略

软件不能只凭编译宏假定硬件能力。`qbinfo` 返回：

- architecture、descriptor、numerical-contract version；
- descriptor 大小；
- 最大 M/N/K-blocks；
- 权重和激活 layout bitmask；
- descriptor/weight/activation 对齐；
- 每个 weight profile 可配对的 activation profile；
- profile 的 block bytes/elements/subgroup/scale/correction 属性。

GGML 只有在用户显式启用 QBS 且 capability 完整匹配时才选择 QBS trait。这样同一 binary 能在
无 QBS 的 RVV 处理器、旧 contract 硬件或只实现部分 profile 的硬件上安全回退。

### 5.4 合法性与地址检查

descriptor decoder 在发出 payload 访问前检查：

- descriptor 对齐、version 和 reserved bits；
- profile 是否存在、weight/activation 是否兼容；
- layout 是否支持；
- `M/N/K-blocks` 范围；
- `vd` 对目标寄存器组的对齐；
- weight/activation base 对齐；
- 由 block bytes、padded rows 和 K-blocks 计算的末地址是否溢出。

R4 权重会将 N 向上补齐到 4 行，但 logical N 仍保存在 descriptor 中；padding 只解决存储布局，
不产生额外 architectural output。

## 6. llama.cpp/GGML 端完整调用链

### 6.1 编译和运行开关

当前 backend 由 `GGML_USE_RISCV_QBS` 编译开关接入。运行时关键环境变量包括：

- `GGML_RISCV_QBS=1`：允许 native capability probe 和 QBS 选择；
- `GGML_RISCV_QBS_EMULATE=1`：执行软件 emulation，用于框架功能验证，不代表硬件性能；
- `GGML_RISCV_QBS_FORMATS=...`：profile allowlist，便于单格式隔离；
- trace/coverage 变量：记录 tensor 选择、fallback 原因、GEMV/GEMM、M 分布、split-K 和命令数。

这里要区分两种“模拟”：GGML 环境变量打开的是 backend 内的标量反量化执行路径，主要用于
检查 trait、repack、分块和 dispatch，浮点求和顺序不保证与 v1 block contract 逐位相同；
`verification/qbs/qemu/` 中的 `Xaraqbs` 则把 `qbexec` 作为 guest 指令执行，并直接复用 canonical
reference，是架构语义检查。二者都不是 RTL timing model。

### 6.2 模型加载时选择和持久化 repack

原始 GGUF 通常按 output row 保存整行 K blocks。QBS 为了同时消费四个输出行，将其改为
`R4_BLOCK_MAJOR`：

```text
原 row-major:
row0: b0 b1 b2 ...
row1: b0 b1 b2 ...
row2: b0 b1 b2 ...
row3: b0 b1 b2 ...

R4 block-major:
(row0,b0) (row1,b0) (row2,b0) (row3,b0)
(row0,b1) (row1,b1) (row2,b1) (row3,b1)
...
```

这一重排发生在模型加载/CPU repack buffer 初始化阶段，运行时不计入每个 token 的 matmul
周期。输出行不足 4 的最后一组会 padding；3D expert tensor 只有在每个 expert 的行数能保持
R4 group 边界时才允许选择，否则回退，避免一组四行跨越 expert。

R4 的意义不是改变数学，而是使同一 K block 的四个 output rows 物理连续。read engine 可以用
一个连续 range 读取四行，profile engine 可在一份 activation 上同时推进四行 dot。

### 6.3 运行时 activation 量化和布局

GGML 的量化 matmul path 先把 FP32 activation 动态量化：

- K-quant 权重使用 Q8_K activation；每 256 元素有 FP32 scale、256 个 int8 和 16 个 bsums；
- `_0`/IQ4_NL 路径使用 Q8_0 activation；每 32 元素有 FP16 scale 和 32 个 int8。

`M<4` 使用 row-major activation；`M=4` 使用 `M4_INTERLEAVED`，即同一 K block 的四个
activation row 相邻。这样硬件可以在 weight block 保持不变时，把同一权重用于四个 context。

### 6.4 GEMV：Decode 的 M=1 路径

`ggml_riscv_qbs_gemv()` 要求输入行数为 1：

1. 计算 `k_blocks = K / block_elements`；
2. 按硬件 `max_n` 将输出行分成 N tile，VLEN=1024 时通常 N=32；
3. 为每个 tile 构造 descriptor；
4. `qbexec` 把 N 个 FP32 结果写到一个向量寄存器；
5. `vse32.v` 只存 logical N 个结果。

M=1 是权重带宽最敏感的 decode 形态。当前 engine 对 `M=1 + R4` 开启下一 weight tile
lookahead：current bank 计算时，inactive bank 可以预取**同一 K block 的下一组四个输出行**。
它不会跨 K block 猜测；K block 推进时 activation 和 weight bank 生命周期重新建立。

### 6.5 GEMM：Prefill 的 M=1..4 路径

`ggml_riscv_qbs_gemm()` 将 input rows 每次取最多 4 行：

```text
for input rows in groups of M<=4:
    choose row-major or M4-interleaved activation
    for output rows in N<=32 tiles:
        qbexec(M, N, K-blocks)
        store M output vectors
```

一条 M4 命令形成 4 x N 个 FP32 accumulator。硬件读取每个 weight block 后将它复用到四个
activation context；读取每个 activation block 后又将它复用到 N 个 output rows。复用范围
完全由 descriptor shape 推导，没有由地址预测产生的隐式流状态。

### 6.6 长 K 的软件分段

硬件单命令最多 256 个 native K blocks。更长 K 不直接失败，而由 backend 分段：

1. 每段构造独立 descriptor；
2. 每段 QBS 输出一个 partial FP32 tile；
3. 软件按 K 段顺序累加 partial results。

现有 R4 layout 的任意 K 子段只在单个四行组内连续，因此 split-K functional path 将 N 限制
为最多 4。M<4 时还需复制出 row-major activation segment。这保证功能覆盖，但不是长 K 的
最终高性能布局；若它成为常见路径，应设计 segment-friendly layout 或扩展 descriptor，而不是
隐藏不连续性。

### 6.7 选择条件和 fallback

QBS 只有在以下条件同时成立时才接管 tensor：

- 用户显式启用，`qbinfo` contract 匹配；
- weight type 属于九种 profile；
- tensor 为支持的 2D，或不会跨 expert R4 group 的 3D；
- K 可被 profile block size 整除，shape 和地址合法；
- profile、layout、M/N/K 容量均被硬件声明支持。

否则 `ggml_repack_get_optimal_repack_type()` 继续选择原来的 RISC-V/RVV 或通用 CPU trait。
这是 QBS 保持通用性的关键：**新路径是受能力和 shape 约束的优化，不是改变全部 MUL_MAT 的语义。**

### 6.8 覆盖哪些模型算子，不覆盖哪些

只要权重格式和 shape 合法，QBS 可以覆盖 `GGML_OP_MUL_MAT` 中的：

- Attention Q/K/V/O projection；
- FFN gate/up/down projection；
- 兼容格式的 embedding/output projection；
- 普通 2D 以及受 R4 边界约束的 expert/MoE 3D tensor。

它当前不直接执行：

- FP32 到 Q8_K/Q8_0 的动态量化本身；
- RMSNorm、LayerNorm、RoPE、Softmax；
- Attention score、value aggregation 和 KV-cache 管理；
- elementwise activation/residual；
- 未列入 ABI 的 GGUF type，例如其他 IQ、TQ、MXFP profile。

因此 QBS 可显著加速主要线性层，但不能仅凭 microtile speedup 推导完整模型 token/s；端到端
Amdahl 比例、activation quantization、非线性算子和内存系统仍需单独测量。

### 6.9 用 Qwen2.5-1.5B Q4_K_M 具体理解覆盖范围

当前真实数据集来自 Qwen2.5-1.5B-Instruct Q4_K_M 的第 0 层：28 层、hidden size 1536、
12 个 query heads、2 个 KV heads、head dimension 128、FFN dimension 8960。该层七个线性
权重及其 shape 为：

| GGML tensor | Weight | `K` | `N` | Decode `M` | Prefill capture `M` | 作用 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `attn_q` | Q4_K | 1536 | 1536 | 1 | 15 | 生成 12 个 query heads |
| `attn_k` | Q4_K | 1536 | 256 | 1 | 15 | 生成 2 个 key heads |
| `attn_v` | Q6_K | 1536 | 256 | 1 | 15 | 生成 2 个 value heads |
| `attn_output` | Q4_K | 1536 | 1536 | 1 | 15 | 合并 attention 输出 |
| `ffn_gate` | Q4_K | 1536 | 8960 | 1 | 15 | SwiGLU gate projection |
| `ffn_up` | Q4_K | 1536 | 8960 | 1 | 15 | SwiGLU up projection |
| `ffn_down` | Q6_K | 8960 | 1536 | 1 | 15 | FFN 投影回 hidden size |

表中 weight matrix 按 `N x K` 理解。Decode 的一行 activation 对应 M1 GEMV；Prefill 的
15 行由 `4+4+4+3` 个 input-row groups 执行，其中 M4 使用 interleaved activation，M3 使用
row-major activation并保留 4-register destination group。每组内部 N 再按最多 32 行切分。

Q4_K_M 是混合格式模型，名称中的 Q4_K 不意味着所有 tensor 都是 Q4_K。`attn_v` 和
`ffn_down` 使用 Q6_K 正是多 profile capability 和 fallback 必须在真实模型中验证的原因。
RMSNorm、RoPE、Attention core、SwiGLU 和 residual 仍由 RVV/标量 GGML kernels 执行。

### 6.10 三层循环怎样映射到软件和硬件

完整执行不是“一条指令计算整个模型矩阵”。它包含三个不同层次的 tiling：

```text
GGML operator
  for each input-row group M<=4:                 // software
    quantize/pack activation rows
    for each output-row command tile N<=32:      // software
      qbexec(M, N, all K blocks)

qbexec command
  for each K block:                              // hardware
    load this K block of M activation rows once
    for row_base = 0; row_base < N; row_base += 4:
      load up to four weight rows, with two-bank lookahead when legal
      decode and compute up to 4 x M logical streams
      update hidden accumulators[m][row]
  drain pipelines and atomically commit M x N results
```

这段伪代码揭示了两个容易忽略的复用边界：

- **命令内**，一个 activation K block 被该命令的 N 个输出行复用，一个 weight block 被 M 个
  activation context 复用；
- **命令间**，hidden accumulator、weight bank 和 activation block storage 都不持久。下一个
  N tile 会重新读取 activation blocks，但不需要重新执行软件量化，因为量化结果仍在内存中。

因此未来若融合 activation quantization，不能让每条 N-tile 命令重复量化同一 activation。合理
方向是先建立可复用的 activation context，再让多条 `qbexec` 消费；这属于未来 contract，不是
当前 v1 已实现行为。

### 6.11 当前覆盖深度，而不只是格式数量

“支持九种格式”只说明 profile decoder 的横向覆盖。当前能力应按以下五层描述：

| 覆盖层 | 当前范围 | 不能据此推导的结论 |
| --- | --- | --- |
| Format | 9 组 weight/activation profile | 不等于覆盖全部 GGUF types |
| Shape | M1-M4、命令 N<=32、K<=256 blocks，软件处理 N/M/K 外层分块 | 不等于所有 shape 都同样高效 |
| Operator | quantized `GGML_OP_MUL_MAT` 的 GEMV/小 M GEMM | 不等于覆盖完整 Transformer block |
| Model mapping | Qwen2.5 中主要 Q/K/V/O 和 FFN linear projections | 不等于所有模型家族和 MoE layout 已验证 |
| Implementation evidence | reference、directed RTL、QEMU native model、部分真实 RTL workload | 不等于完成 P&R、功耗和标准数据集质量闭环 |

对已经隔离测试的目标 profile，`selected_tensors == candidate_tensors` 和
`selected_elements == candidate_elements` 才表示该 profile 的候选线性层达到 100% 软件选择覆盖。
这个百分比不能用作“整个模型 100% 被 QBS 加速”，因为非 `MUL_MAT` 算子根本不在分母中。

### 6.12 未覆盖操作是否适合并入 QBS

当前未覆盖操作应按计算结构判断，而不是为了提高算子数量全部塞入同一命令：

| 操作 | 主要行为 | 与 QBS 的合理关系 |
| --- | --- | --- |
| FP32 -> Q8_K/Q8_0 动态量化 | abs-max reduction、scale、round/clamp、Q8_K bsums | 与输入准备紧邻，适合未来 context 化和流水化，但必须量化一次供多个 N tile 复用 |
| RMSNorm/LayerNorm | 平方、sum reduction、rsqrt、scale | 更适合增强 RVV reduction/SFU；除非与下一次量化形成可证明的 fusion |
| RoPE | 成对旋转、sin/cos 系数和逐元素运算 | 规则 RVV kernel 更自然，不宜改造成 block-matmul profile |
| Softmax | max/sum reduction、exp、division | 需要 reduction 和特殊函数支持，不属于当前压缩权重点积数据流 |
| Attention score/value | 动态 Q/K/V 上的矩阵乘和归一化后聚合 | 有独立加速价值，但数据来源、精度和 KV 生命周期不同，应作为新机制而非伪装成 weight profile |
| KV-cache | token/head 寻址、读写、layout、容量和带宽 | 主要是存储系统问题，适合地址生成、layout、预取或压缩协同 |
| SiLU/SwiGLU/residual | elementwise 激活、乘法和加法 | 保留普通 RVV；只有实测成为主瓶颈时再考虑 fusion |
| 其他 GGUF quant | 新的 block 字节布局和数学 | 仅当可复用现有 decoder/dot/correction 主路径且真实模型常用时增加 profile |

由此得到的合理总体架构不是“QBS 执行全部 LLM”：QBS 负责量化线性层，普通 RVV 负责通用
elementwise/reduction，后续再以实测 Amdahl 比例决定是否增加 activation 或 Attention/KV 协同。

## 7. QBS 如何接入 Ara

### 7.1 原 Ara 数据通路

Ara 是 RVV 1.0 lane-based vector processor。dispatcher 解码并维护 vector CSR，sequencer
跟踪 vid 和相关性，lanes 保存分片 VRF 并执行 ALU/FPU，VLSU 处理虚拟地址、MMU、AXI 和
load result，SLDU/MASKU 处理跨 lane 和 mask 操作。

QBS 没有旁路整个向量系统。它选择接在 dispatcher/sequencer 可见的 vector command 与 VLSU
资源域内，使命令仍具有目的向量组、vid、完成和异常语义。

### 7.2 Dispatcher 和 sequencer

dispatcher 对 custom opcode 做两类处理：

- `qbinfo`：读取 capability，直接返回标量结果，不进入长时延 sequencer 流程；
- `qbexec`：解码为内部 `VQBEXEC`，声明使用 `vd`，根据 M 建立目标 register group，并送入
  sequencer/VLSU。

sequencer 为命令分配 vid 并保持目标寄存器 hazard 可见。QBS terminal success/fault 到达后，
该 vid 才完成；QBS FP operations 产生的 `fflags` 通过已有完成路径返回。

### 7.3 VLSU 资源所有权

dispatcher 只有在 `ara_idle_i` 为真、即全部更老的 Ara 工作已经排空后，才把 `VQBEXEC` 发给
sequencer；VLSU 还用 `normal_vlsu_idle` 检查本地 address generator、load/store unit、AXI cut
和 result port 都没有残留活动，随后才接受命令。命令 active 期间：

- MMU request、physical range check 和 AXI read 由 QBS read engine 驱动；
- QBS 不发 AXI write；
- 普通 VLSU 不接受新 issue；
- FP32 commit 通过已有 LDU result ports 写入 lanes/VRF；
- success/fault 被 sequencer 接收后，资源才归还普通 VLSU。

RTL assertion 检查 QBS/normal VLSU 不能同时拥有接口、QBS 不能写 memory、normal VLSU 在 QBS
active 时不能产生冲突活动。这是一种保守但清晰的首版集成。

### 7.4 为什么输出到 VRF

QBS 若直接写 GGML 内存，会绕开向量寄存器 dependency、完成和异常边界；若引入独立 tile
register，又会增加上下文状态。当前设计选择：

```text
hidden command-local accumulator
  -> fault-free commit phase
  -> existing LDU result interface
  -> ordinary Ara VRF (from vd; e.g. v8...v11)
  -> standard RVV store
```

因此后续 RVV 指令可以正常消费结果，操作系统看到的仍是标准 vector state。这里的“原子”是
命令级故障可见性：任何写回开始前，所有可能产生 fault 的读取和计算已经完成；真正的 VRF 写回
仍通过 LDU port 分多个 cycle 完成，年轻消费者在 terminal 前由 sequencer completion gating
阻塞。代价是 commit 受到 LDU result port 和 VRF grant 的带宽约束，但当前计数器可直接观察该
backpressure。

## 8. 一条 `qbexec` 的完整生命周期

以 `M=1, N=32, K=1536, Q4_K x Q8_K` 为例，`k_blocks=6`：

1. **Issue**：软件设置 e32/m1，`rs1=descriptor`、`rs2=activation`、`vd=v8` 发出 `qbexec`。
2. **Descriptor read**：QBS 通过 MMU/AXI 读取 16 B descriptor。
3. **Validate**：检查版本、profile、layout、shape、对齐和地址范围。
4. **Activation load**：读取第一个 Q8_K block；block adapter 组装 292 B native block。
5. **Weight load**：读取 R4 中同一 K block 的四个 output rows；尾行按 logical N 屏蔽。
6. **Profile decode**：逐周期恢复 quant 值、subgroup scale/min、activation quant 和 bsums。
7. **Integer compute**：32 个 signed low-bit x int8 multiplier pair 形成 subgroup partial sums。
8. **Correction scheduling**：两套内部 context 吸收 decoder/dot 与结果排队速率差。
9. **FP update**：整数 subtotal 转 FP32，乘 block scales，以 contract 顺序 FMA 到 accumulator。
10. **Tile advance**：遍历 K blocks 和 N microtiles；M=1 时可预取下一 weight tile 到另一 bank。
11. **Drain**：等待 read、integer pipeline 和 FP table 全部排空。
12. **Commit**：按四 lane 聚合组分周期写满一个 architectural vector register，inactive N
    元素清零；这一步开始后已不存在尚未决议的 memory/compute fault。
13. **Terminal**：成功完成 vid；软件恢复 `vl=N`，用 `vse32.v v8` 存结果。

不同 fault 的收尾路径并不相同。descriptor read fault 或 validation fault 发生在 compute 启动前，
read engine 排空已发 burst 后直接进入 terminal fault；payload 的 MMU、PMA、AXI response/protocol
fault 才会在 read response 排空后进入 compute fault drain，停止新工作并清除隐藏计算状态。
两类路径都不会启动 commit，因此不会留下“前半个 tile 已写回”的部分状态。

## 9. RTL 模块逐项讲解

### 9.1 `qbs_engine.sv`：命令级总控制器

顶层状态机：

```text
IDLE
 -> DESCRIPTOR_REQUEST
 -> DESCRIPTOR_WAIT
 -> VALIDATE
 -> COMPUTE_START
 -> RUN
 -> COMMIT
 -> SUCCESS

fault path:
DESCRIPTOR_WAIT/VALIDATE -> FAULT
RUN payload fault -> COMPUTE_FAULT_DRAIN -> FAULT
```

它保存 command id、vd、M、descriptor/activation 地址、round mode、cache/prot 属性；调度 logical
read ranges；连接 compute 和 commit；保存 fault attribution；导出互斥 phase counter。

图中的直接 `FAULT` 不表示忽略在途 AXI response：`qbs_read_engine.sv` 只有在自身 burst FIFO 已
排空后才向顶层报告 fault。`COMPUTE_FAULT_DRAIN` 专门处理已经进入整数/FP pipeline 的 payload
工作，不用于尚未启动 compute 的 descriptor/validation fault。

当前 M=1 且 R4 layout 时启用同 K block、下一 4-row microtile 的 weight lookahead。注释和逻辑
明确限制在该形态，因为 M>1 的 compute interval 与返回时机不同，未经额外 bank 生命周期保护，
过早发第三个 response 可能覆盖仍在消费的 bank。K block 边界不会保留可被下一块误认的 bank。

### 9.2 `qbs_descriptor_decoder.sv`：静态契约守门

该模块不解码量化 payload，只解 descriptor。它根据 profile 函数得到 block bytes，根据 layout
计算 padded weight rows 和实际存储跨度，再做末地址扩展加法检查。所有 payload request 都依赖
该模块的 `valid_o`，防止非法 descriptor 触发越界读取。

### 9.3 `qbs_read_engine.sv`：共享的 translated read path

descriptor、activation 和 weight 共用一条 read engine：

- 2-entry logical range FIFO；
- 将 range 切成合法 AXI bursts，单 burst 最多 256 beats；
- 需要时等待 scalar store 排空；
- 通过 CVA6 MMU 翻译虚拟地址；
- 检查物理区间允许访问；
- 发 AXI AR，按 R beat 返回 payload 和 range tag；
- 跟踪最多两个有序 outstanding burst。

两个 outstanding 使用同一 AXI ID，因此响应按发出顺序归属到 burst-tag FIFO 头。read engine
仍逐项检查 RRESP/RLAST；发生 fault 后停止新 AR，排空已发响应，并保留最早应报告的 fault。

“read outstanding=2”不等于任意乱序 cache miss engine。它是有界、有序、带 range tag 的预取/
传输重叠，便于证明 fault 和 payload 归属。

### 9.4 `qbs_block_adapter.sv`：字节流到 native block

AXI beat 边界不必与 18/34/84/110/144/176/210/292 B native block 对齐。block adapter 根据
range tag、offset、layout 和 bank，把返回字节写入：

- activation block storage；
- active/inactive weight bank；
- 每个 bank 的最多四个 output rows。

它解决的是“传输粒度”和“计算格式粒度”不一致，而不是量化数学。

### 9.5 `qbs_compute_engine.sv`：shape 调度和 buffer 生命周期

compute engine 负责：

- 清空一条命令的 accumulator；
- 请求 activation/weight ranges；
- 选择 active weight bank；
- 向 profile engine 发 `(K block, row_base, row_count, M)` tile；
- 等待整数结果和 FP update 排空；
- 判断何时可切换 bank、推进 row tile 或 K block；
- fault 时停止新工作并完成 drain。

activation 跨同 K block 的多个 N tile 复用；weight 跨 M context 复用。这里的复用由 shape
和循环顺序精确决定，不依赖命中预测。

### 9.6 `qbs_profile_decoder.sv`：格式位级语义

这是支持多格式的关键组合模块。它按 `profile` 和当前 element/group：

- 从 low/high plane、mask、nibble 或 IQ table 得到 signed weight quant；
- 读取 activation int8；
- 解 subgroup scale/min；
- 对 affine profile读取相应 Q8_K `bsums`；
- 提取 weight `d/dmin` 和 activation `d`。

格式差异在这里被规范化为：

```text
weight_quant, activation_quant,
group_scale, group_min, group_aux,
weight_d, weight_dmin, activation_d
```

后面的 dot array、correction scheduler 和 FP accumulator不需要知道 GGUF 字节偏移。

### 9.7 `qbs_dot_array.sv`：32 个整数 pair/cycle

物理结构为四个 row cluster，每个 cluster 有八个 signed int8 x int8 乘法器，共 32 pair。虽然
weight 原始位宽可为 2/3/4/5/6/8 bit，decoder 先扩展为 signed int8，所以 dot array 保持统一。

M 改变每个 row cluster 的并行分配：

- M=1：每行 8 pair，形成一个 8 项和；
- M=2：每个 context 4 pair；
- M=3/4：每个 context 2 pair。

因此物理 pair capacity 固定，而 M/N shape 决定 pair 在 output-row 和 activation-context 间的
分配。balanced reduction tree 避免综合成串行加法链。

### 9.8 `qbs_profile_engine_int.sv`：整数流水与结果整形

该模块包含两个内部 context 和 16 个 logical streams（4 weight rows x 4 activation contexts）。
它将 decoder 输出送入 dot array，按 subgroup 累计 partial dot，再应用 integer scale/min：

```text
subtotal_dot += group_scale * group_dot
subtotal_aux += group_min   * group_aux
```

完成一个 native block 后，它以 round-robin 方式把每个有效 stream 的 `dot/aux/d/dmin` 送给
FP accumulator。两 context 的作用是吸收 decode、dot reduction 和 FP consumer 之间的速率差，
不是对两条 architectural commands 做乱序。

### 9.9 `qbs_fp_accumulator.sv`：共享 FP32 update pipeline

逻辑上最多有 `M*N=4*32=128` 个 FP32 accumulators。物理上按 8 bank x 16 row 组织，另有
16-entry FP update table。每个 table entry 保存 accumulator index、profile、dot/aux、scale、
round mode 和中间 FP 值。

一条非 affine block update 经历：

```text
int dot -> FP32
weight_d * activation_d
FMA(scale, dot_f, accumulator)
```

affine block 还执行 aux conversion、`dmin*activation.d` 和第二次 FMA。模块复用一个 fpnew
primitive，并用 tag 将多 entry 的返回值写回正确状态。对同一 accumulator index 的重叠 update
必须受控，因为 FP 加法不满足任意重排的 bitwise 等价性。

### 9.10 `qbs_commit.sv`：故障原子、物理上分周期的 lane VRF 提交

commit 只有在所有读取和计算无 fault 后启动。它按 VLEN 和 4 lanes 将 FP32 accumulator word
转换为 LDU result request：

- 每个 64-bit lane word承载两个 FP32 elements；
- 每次提交四个 lane word，共八个 FP32 results；
- 对每个有效 M 写满一个 architectural vector register；
- `element >= N` 的 inactive output 清零；
- M=3 不写保留的第四个 destination register。

这里一次“word”是四条 lane 各一个 64-bit word 组成的 256-bit aggregate group，共承载八个
FP32 元素，不是整个 VLEN-bit register 同周期写入。当前计数器 `commit_word_count` 在四条 lane
均收到 request grant 和 final grant 后加一，最终必须等于 `M * (VLEN/256)`；日志字段仍沿用
`commit_groups`。每个 active element 在 commit 前都必须已有 valid accumulator。VRF grant 不足
时状态机停在当前 group，并计入 backpressure。

当前 v1 mapping 由 RTL assertion 明确限制为 4 lanes、128-bit AXI read data，以及 256--1024-bit、
按 256-bit 整除的 VLEN。结合 RVV 的 VLEN 约束，本项目实际使用 1024-bit VLEN；这些是当前实现
边界，不是 profile/layout/shape ABI 本身天然要求的通用限制。

## 10. 正确性、内存顺序和异常

### 10.1 为什么要“先算完，再提交”

QBS 一条命令会产生 M x N 个输出。如果边计算边写 VRF，后续 weight page fault 可能让一部分
结果可见、一部分不可见，难以符合单条指令的异常模型。当前设计将 FP32 accumulators 保持为
隐藏状态，直到：

- descriptor 和全部 payload 访问成功；
- read outstanding 排空；
- profile/dot/FP pipelines 排空；
- 所有 active accumulators valid。

之后才进入 commit。因此 fault command 的 destination 不应出现部分更新。

### 10.2 内存访问属性

QBS 只有读请求，descriptor/weight/activation 都通过同一 MMU 和 physical-range check。logical
range 会先按 4 KiB page 和 AXI 最大 burst 边界切分；当前 PMA 门控要求每个翻译后的完整 AXI
burst 覆盖范围落在同一 cacheable region 且不与 non-idempotent region 相交。非幂等 MMIO 或
跨越不允许区域的子请求以 load-access fault 结束，而不会把长 block stream 投向有副作用的设备
地址。当前
软件 wrapper 在命令前执行 `fence rw,rw`，保证先前对 descriptor、activation 和 repacked
weight 的写入在 QBS 读取前可见。

命令期间普通 VLSU 被阻塞，避免两套 address generator 竞争同一外部接口。QBS 不自行实现
cache coherence 协议；它继承所在 SoC 的 AXI/cache/MMU 语义。

### 10.3 Fault 分类

内部区分：

- descriptor validation fault；
- request planning fault；
- MMU translation fault；
- PMA/physical range fault；
- AXI response fault；
- AXI protocol fault，例如错误 RLAST。

fault attribution 记录 fault kind、虚拟地址和 MMU exception。内部详细分类未全部作为软件 ABI
暴露，但对验证和定位至关重要。

### 10.4 当前恢复边界

QBS 是阻塞、原子提交的长命令，不实现 RVV 那种按 element `vstart` 精确重启。QEMU model 会
检查 `vstart` 和 vector/FP state，非法状态拒绝命令。若未来要求 page-fault resume，需要显式
定义 command progress 的 architectural visibility，不能仅保存内部 FSM。

## 11. 性能机制：收益到底来自哪里

### 11.1 消除软件 unpack/reduction 指令流

profile decoder 直接在 block bytes 上产生 quant/metadata，dot array 直接消费，避免把完整
解量化权重写入 VRF 或 memory，也避免每个 output row执行相同 mask/shift/reduction 序列。

### 11.2 M/N 二维复用

对一个 tile：

- 一个 activation block 被 N 个 output rows使用；
- 一个 weight block 被 M 个 activation rows使用；
- 32 pair/cycle 在 M 和 output rows之间调度；
- M x N 个 FP32 partial sums驻留命令内 accumulator。

这就是“多输出”比单点积更重要的原因。单点积只能优化一行 `B[n,:] dot A[m,:]`；QBS 通过
tile contract 让读取和控制开销在多个输出上摊薄。

### 11.3 R4/M4 layout 与请求粒度

R4 使四个 output rows 的同一 K block 连续，M4 使四个 activation rows 的同一 K block 连续。
如果 layout 与计算 tile 不匹配，硬件即使 dot throughput 足够，也会被大量小 range、翻译和 AR
启动开销限制。

当前历史实测中，将 R4 四行从四个串行 weight ranges 合并为一个连续 range，在 payload bytes
和 useful pairs 不变时显著减少 range/AR 数。这类证据说明：QBS 的核心不是只增加 MAC，数据
布局和事务粒度同样属于软硬件契约。

### 11.4 双 weight bank 和有界 lookahead

M=1/R4 当前可在 active bank 计算时，向 inactive bank 读取同 K block 的下一组四个 output
rows。两个 ordered outstanding 让 AR/R 传输与整数/FP 工作重叠。只有 inactive bank 的生命周期
确定安全时才切换，避免“为了预取覆盖尚在消费的数据”；K block 边界不做跨块预测。

### 11.5 FP update 可能成为新瓶颈

低比特 pair throughput 提高后，瓶颈可能转移到：

- subgroup correction 结果排队；
- int32-to-FP32 转换；
- scale multiplication；
- affine profile 的第二次 FMA；
- 同 accumulator 的顺序约束。

因此不能只看 dot-active ratio。`fp_table_full_cycles`、`fp_uop_issue`、occupancy 和
accumulator updates 必须共同解释。

### 11.6 Commit 通常不是主瓶颈，但必须测量

结果 tile 最终仍走 lane/VRF port。若 `commit_backpressure_cycles` 升高，说明 QBS core 已经
把瓶颈推到写回；若为零，则扩大 commit 带宽不会改善当前点。

### 11.7 为什么 QBS 相对标准 RVV 会出现数量级加速

第 2.23 节的 `20.38x--92.49x` 是严格配对的真实量化 `MUL_MAT` 切片加速，不是“32 个整数
乘法器相对 RVV 有几十倍峰值算力”。大幅差异来自下面五项同时作用：

1. **消除整个软件展开序列**。RVV 对每个 output row 显式执行 bit unpack、metadata decode、
   widening MAC、vector reduction、标量/FP scale update 和循环控制；QBS 用一条 `qbexec` 描述
   整个 `M x N x K-blocks` tile，再由内部状态机推进。四个多格式点的 timed region 中，QBS
   侧退休的普通指令数约为 RVV 的 `0.5%--0.7%`，普通向量指令数约为 `0.4%--0.6%`。这些比例
   表示架构指令流被命令替代，不表示 QBS 内部没有执行等价的 decode、dot 和 FP 工作。
2. **直接在压缩表示上计算**。QBS 读取 GGUF native block，decoder 只在整数 datapath 的入口
   恢复 quant 和 metadata，不把完整 FP32/INT8 weight tensor 物化到 memory 或 VRF。四个点的
   QBS logical reads 仅为 RVV 的 `30.3%--51.9%`。
3. **在 tile 内摊薄重复工作**。一个 activation block 被 N 个 output rows 共享，一个 weight
   block 在 Prefill 中被 M 个 activation contexts 共享；subgroup correction 和 128 个 FP32
   partial sums 都驻留在 command-local state，避免每行重新装载、归约和往返 scalar/VRF。
4. **让 layout 与事务粒度一致**。R4 把同一 K block 的四个 weight rows 放成连续 range，避免
   “数据本来连续、软件/硬件却发四个小请求”。完整 Decode Attention-Q 中，仅合并这四个
   range 就在 payload 和 pair 数不变时把 matmul 从 293,329 降到 217,297 cycles。
5. **有界覆盖取数延迟**。M1/R4 使用两个 weight banks 和最多两个有序 read outstanding，在
   当前 tile 计算时读取同 K block 的下一 4-row tile。该点进一步从 217,297 降到 133,861
   cycles，且数值、payload 和 useful pairs 不变。

Decode Attention-Q 的机制演进可把“专用数据通路收益”和“后续供数优化”分开：

| 等价 Q4_K matmul 路径 | Cycles | 相对同一 RVV baseline |
| --- | ---: | ---: |
| 标准 RVV | 1,495,946 | 1.000x |
| 首个正确 QBS 系统闭环 | 293,329 | 5.100x |
| + R4 四行 range 合并 | 217,297 | 6.884x |
| + 双 bank / 双 outstanding lookahead | 133,861 | 11.175x |

这不是可简单相加的 ablation：后两步都改变 memory/compute overlap。但它证明最终加速并非来自
减少数学工作或放宽精度，而是把 RVV 软件已知的 block/layout/shape 语义保留到硬件后，消除了
解释性指令流、重复数据移动和细粒度请求，再用受控 buffering 覆盖剩余延迟。

当前四个多格式代表点的 matmul 几何平均为 `51.34x`，但格式间差异不能解释成 bit 数越低就一定
越快。Q5_K 的标准 RVV unpack/reduction 指令序列比 Q3_K/Q6_K 更重，而 QBS 将差异主要吸收到
profile decoder，因此该点相对加速最高；Q8_0 block 只有 32 个元素，block-level FP update 更
频繁，QBS 自身固定成本占比更高，因此相对加速较低。完整模型还包含 activation quantization、
Attention、Norm、RoPE、KV cache 和 sampling，必须用端到端 Amdahl 比例评价，不能把这里的
operator speedup 直接当成 token/s speedup。

## 12. 计数器及其严格含义

### 12.1 命令和 phase

| Counter | 严格含义 |
| --- | --- |
| `command_cycles` | QBS 从接受命令到 terminal 的 busy 周期 |
| `phase_setup_cycles` | descriptor request/wait、validate、compute start |
| `phase_activation_cycles` | compute engine 等待/装载 activation 的主状态周期 |
| `phase_weight_cycles` | 等待/装载当前 weight 的主状态周期 |
| `phase_compute_cycles` | compute active 且无并发 weight read 的周期 |
| `phase_overlap_cycles` | compute active 且同时存在 weight read/range 活动的周期 |
| `phase_drain_cycles` | 正常 drain 周期 |
| `phase_scheduler_cycles` | RUN 中不属于上述 compute 子状态的调度周期 |
| `phase_commit_cycles` | architectural commit 周期 |
| `phase_fault_cycles` | fault drain 周期 |
| `phase_terminal_cycles` | success/fault 等待 sequencer 接收周期 |

这些 phase 对每个 busy cycle 互斥，和应等于 `command_cycles`。不要把多个可重叠 activity counter
也相加为 stall breakdown。

### 12.2 Read path

| Counter | 严格含义 |
| --- | --- |
| `read_range_count` | logical range handshake 数 |
| `read_translation_count` | MMU translation handshake 数 |
| `read_ar_count` | AXI AR handshake 数 |
| `read_beat_count` | AXI R beat handshake 数 |
| `read_payload_bytes` | 实际属于请求 payload 的字节数，不含总线对齐浪费 |
| `read_store_wait_cycles` | read engine 因 scalar store pending 等待的周期 |
| `read_backpressure_cycles` | R valid 而本地不能接收的周期 |
| `read_outstanding_occupancy_sum` | 每周期 outstanding burst 数的积分 |
| `read_outstanding_max` | 单命令最大 outstanding，当前不得超过 2 |
| `read_outstanding_full_cycles` | 两个槽均占用的周期 |

常用派生：

```text
average_outstanding = occupancy_sum / command_cycles
payload_bandwidth   = read_payload_bytes / command_cycles
AR_efficiency       = read_payload_bytes / read_ar_count
```

### 12.3 Compute/FP/commit

| Counter | 严格含义 |
| --- | --- |
| `tiles_computed` | profile engine 实际完成的 native compute tiles |
| `weight_bytes` / `activation_bytes` | block adapter 接收的对应 payload bytes |
| `useful_pairs` | 实际参与有效 stream 的乘法 pair 数 |
| `pair_capacity` | 同期 dot array 可提供的 pair slots |
| `dot_active_cycles` | dot array `valid` 的周期 |
| `weight_prefetch_wait_cycles` | 当前 tile 完成但下一 weight bank 尚未完整的等待周期 |
| `fp_uop_issue` | 向 fpnew 发出的转换/乘法/FMA micro-op 数 |
| `fp_table_occupancy_sum/max/full_cycles` | FP update table 占用积分、峰值和满周期 |
| `accumulator_updates` | 完成并写回一个 block 对一个 accumulator 的次数 |
| `commit_word_count` | 四 lane 的 256-bit aggregate group 完成数；日志名为 `commit_groups` |
| `commit_backpressure_cycles` | commit 请求存在但未获全部所需 grant 的周期 |

常用派生：

```text
pair_utilization = useful_pairs / pair_capacity
dot_duty         = dot_active_cycles / command_cycles
FP_table_avg_occ = fp_table_occupancy_sum / command_cycles
```

`dot_duty` 低不自动证明 dot array 太小或太大；必须结合 weight wait、read payload/cycle、FP table
和 phase。`pair_utilization=1` 只说明发出 dot 的周期没有浪费 pair，不说明 dot 每周期都在发。

## 13. 验证体系

### 13.1 Canonical C reference

`verification/qbs/qbs_ref.c` 是 ABI 的可执行规范，独立于 RTL datapath。它负责：

- descriptor validation；
- 九种 profile 的 exact decode 和数值 contract；
- row-major/R4 与 row-major/M4 layout；
- trace group/block events；
- fault 前不写结果的 atomic commit。

### 13.2 Standalone 和 command RTL

验证从小到大包括：

- constructed format vectors；
- profile decoder/integer engine/FP accumulator unit tests；
- descriptor/read/compute/commit command testbench；
- M1/M2/M3/M4、N tails、K blocks；
- MMU/PMA/AXI response/RLAST 和 backpressure fault；
- real Qwen2.5 weight、activation 和 llama.cpp golden。

### 13.3 QEMU functional model

QEMU 10.2.0 `Xaraqbs` model复用生成的 ABI header 和 canonical C reference。它检查 capability、
vector/FP state、destination alignment、guest memory fault、inactive elements、M=3 保留寄存器和
`fflags`。这是**架构/软件功能模型，不是 timing model**。

完整模型测试在同一 Qwen2.5 prompt 上分别运行普通 RVV 和 native QBS opcode，检查输出文本、
profile dispatch、GEMV/GEMM 和 fallback。QEMU 通过只能证明 GGML graph 和命令语义可工作，不能
作为 RTL speedup。

### 13.4 数值验证应分三层

1. **bit-exact contract**：RTL vs canonical reference，应逐 accumulator bit 匹配；
2. **operator accuracy**：QBS contract vs llama.cpp baseline，记录 max error/RMSE 等；
3. **model quality**：相同 prompt/token policy 下比较 logits、top token、KL/RMSE 和长文本行为。

若改变 FP 累加顺序，即使数学实数表达式相同，也必须重新完成第 2、3 层，不能把误差简单归为
“浮点允许不同”。

### 13.5 模型级比较为什么使用 teacher forcing

模型级精度实验需要比较普通 RVV 路径与 QBS 路径在**相同模型、相同权重、相同历史 token**下
给出的下一个 token 分布。若让两条路径各自自由生成，一旦某一步选择了不同 token，后续上下文
就不同；之后观察到的 logits 差异同时包含“计算路径误差”和“输入序列已经分叉”两种因素，无法
继续归因。

当前 `verification/qbs/qemu/qbs_token_init.c` 因此采用 teacher-forced 比较：给定包含 69 个
token 的固定真实文本，两条路径依次观察相同前缀，并在每个位置预测固定序列中的下一个 token，
形成 68 条 logits record。每条 record 包含：

```text
step          当前预测位置
n_vocab       词表大小
target_token  固定文本中的真实下一个 token
RVV logits    普通 RVV 路径给整个词表的未归一化分数
QBS logits    只启用目标 QBS profile 后给整个词表的未归一化分数
```

这种方法能把每一步的差异归因到执行路径，但它不直接测量自由生成时误差是否会逐 token 累积。
完整评价应同时包含：

1. teacher-forced logits/PPL 比较，用于稳定、可重复的数值归因；
2. free-running generation，用于观察真实解码序列是否分叉；
3. 标准数据集 perplexity 或下游任务质量，用于论文级模型质量结论。

本测试中的 `QBS_TOKEN_OUTPUT_EQUAL=1` 只表示两次运行打印的 teacher record 文本相同。输入
token 本来就是固定的，因此它**不表示 RVV 与 QBS logits 逐位相等**。真正的数值判断必须看
PPL、KL、Top-k、RMSE 和最大误差。

### 13.6 单个预测位置上的 logits 指标

设某一步的词表大小为 `V`，普通 RVV logits 为 `zR[i]`，QBS logits 为 `zQ[i]`。logit 是
softmax 前的未归一化分数，不是概率。

#### 13.6.1 `mean_abs`：平均绝对 logit 误差

```text
mean_abs = (1/V) * sum_i abs(zR[i] - zQ[i])
```

它回答“该位置上一个普通词表元素平均相差多少”。越小越好，但它没有区分误差发生在高概率 token
还是几乎不可能出现的 token 上，因此不能单独代表生成质量。

#### 13.6.2 `rmse`：logits 均方根误差

```text
rmse = sqrt((1/V) * sum_i (zR[i] - zQ[i])^2)
```

RMSE 对较大误差的惩罚强于 `mean_abs`，适合检测系统性数值漂移。它仍是 logit 空间指标：
例如给所有 logits 加同一个常数不会改变 softmax 概率，却会改变直接 logit 误差，所以必须与
KL 和 Top-k 一起解释。

#### 13.6.3 `max_abs` 与 `max_index`：最坏单点误差

```text
max_abs   = max_i abs(zR[i] - zQ[i])
max_index = 产生该误差的词表索引
```

它们用于发现局部异常和 decoder/correction 错误。较大的 `max_abs` 可能只来自一个低概率
token，不等于整个分布都发生同等偏移；反过来，max 很小是较强的数值一致性证据。

#### 13.6.4 Top-1、margin 与 `top_equal`

```text
rvv_top1 = argmax_i zR[i]
qbs_top1 = argmax_i zQ[i]
top_equal = (rvv_top1 == qbs_top1)
margin = top1_logit - top2_logit
```

`top_equal=1` 表示两条路径在该位置选择相同的最高分 token。它不是模型对 ground truth 的
准确率，而是 QBS 对 RVV 决策的保持程度。如果第一、第二名分数非常接近，微小的合法浮点差异
就可能交换排名。因此 margin 很小时发生 Top-1 交换不一定意味着分布质量明显恶化；margin 很大
仍发生交换则需要重点排查。

#### 13.6.5 `top5_common`：Top-5 集合交集

```text
top5_common = |Top5(RVV) intersect Top5(QBS)|
```

单步取值为 0 到 5。它只看两个候选集合是否包含相同 token，不要求集合内部排序一致。因此它比
Top-1 更不敏感，适合判断概率质量是否仍集中在相似候选上，但不能发现 Top-5 内部概率重排。

#### 13.6.6 `kl_rvv_qbs`：全词表概率分布差异

程序分别对两组 logits 做稳定 softmax：

```text
p[i] = softmax(zR)[i]
q[i] = softmax(zQ)[i]
KL(RVV || QBS) = sum_i p[i] * log(p[i] / q[i])
```

当前打印的是非对称的 `KL(RVV || QBS)`：把 RVV 当参考分布，衡量 QBS 对 RVV 认为重要的
概率质量改变了多少。

- `0` 表示两个概率分布相同；
- 越小表示越接近；
- 它观察整个词表，通常比单独 Top-1 更能反映分布质量；
- `KL(RVV || QBS)` 与 `KL(QBS || RVV)` 不相等，不能交换方向解释。

KL 没有跨模型通用的绝对合格线。必须固定模型、prompt、token policy 和样本数，并与同一软件
baseline 对照。

#### 13.6.7 `target`、`rvv_nll` 与 `qbs_nll`

`target` 是固定文本中的真实下一个 token。设其索引为 `y`：

```text
NLL_RVV = logsumexp(zR) - zR[y] = -log(p[y])
NLL_QBS = logsumexp(zQ) - zQ[y] = -log(q[y])
```

NLL 越低，表示路径给真实下一个 token 的概率越高。与 Top-1 agreement 不同，NLL 使用
ground-truth token，而不是把 RVV 的最高分 token 当作正确答案。

### 13.7 聚合到整个模型片段的指标

设有效记录数为 `T`，当前实验 `T=68`。

#### 13.7.1 `records` 与 `target_records`

- `records`：成功成对读取且 step、词表大小、target 都一致的 logits record 数；
- `target_records`：其中具有合法 ground-truth target、可用于 NLL/PPL 的记录数。

两者均为 68 才说明固定片段完整。记录不足时，即使前几个位置误差很小，也不能宣称模型级实验
通过。

#### 13.7.2 `rvv_ppl`、`qbs_ppl` 与 `ppl_ratio`

```text
PPL_RVV = exp((1/T) * sum_t NLL_RVV[t])
PPL_QBS = exp((1/T) * sum_t NLL_QBS[t])
ppl_ratio = PPL_QBS / PPL_RVV
```

perplexity 越低通常越好。对同一模型和同一固定 token 序列：

- `ppl_ratio = 1`：两条路径平均 NLL 相同；
- `ppl_ratio > 1`：QBS 在该片段上的 PPL 较高；
- `ppl_ratio < 1`：QBS 在该片段上的 PPL 较低。

这里主要判断 ratio 是否接近 1，而不是比较不同 GGUF 模型的绝对 PPL。不同量化模型、参数规模
和文本片段的绝对 PPL 不具有直接可比性。68-token 结果是工程回归，不足以替代标准 perplexity
数据集或下游任务评测。

#### 13.7.3 `mean_kl`

```text
mean_kl = (1/T) * sum_t KL_t(RVV || QBS)
```

它衡量整个固定片段上的平均概率分布漂移，越接近 0 越好。它不会指出漂移集中在哪一步，异常时
仍应回看逐步 KL、margin 和 `max_index`。

#### 13.7.4 `top1_agreement`

```text
top1_agreement = 相同 Top-1 的记录数 / T
```

它衡量 QBS 保持 RVV greedy 决策的比例，不是与 ground truth 比较的准确率，也不是自由生成文本
一致率。低 agreement 配合很低 KL 和较高 Top-5 overlap，通常说明若干位置存在接近候选交换；
若 KL、RMSE 也同时升高，则更像广泛数值漂移。

#### 13.7.5 `top5_overlap`

```text
top5_overlap = (1/T) * sum_t (top5_common[t] / 5)
```

例如 `0.94` 表示每个位置的两个 Top-5 集合平均有约 4.7 个共同 token。它不衡量集合内部排序，
也不代表“Top-5 accuracy”。

#### 13.7.6 `mean_rmse` 与聚合 `max_abs`

```text
mean_rmse = (1/T) * sum_t rmse[t]
max_abs   = max_t max_abs[t]
```

`mean_rmse` 是先对每条记录算 RMSE、再对记录取平均，不是把全部 token/step 展平后计算一个
全局 RMSE。最终 `max_abs` 则是全部步骤、全部词表元素中的最坏单点误差。

### 13.8 覆盖与执行指标：证明比较的确使用了 QBS

精度接近并不能自动证明 QBS 被执行；若所有算子都 fallback 到 RVV，两边当然完全相同。因此模型
精度日志必须同时检查：

| 字段 | 严格含义 |
| --- | --- |
| `candidate_tensors` | 类型和基本 shape 使其成为该 profile 候选的 tensor 数 |
| `selected_tensors` | capability/layout/shape 检查后实际选择 QBS backend 的 tensor 数 |
| `segmented_tensors` | 因单命令 K 上限而需要软件 K 分段的 tensor 数 |
| `candidate_elements` | 候选 tensor 包含的权重元素数 |
| `selected_elements` | 实际由 QBS 覆盖的权重元素数 |
| `fallback_format_filter` | 因本次格式 allowlist 被明确排除的候选数 |
| `fallback_capability` | 硬件 capability 不支持导致的回退数 |
| `fallback_dimensions` | tensor 维度条件不满足导致的回退数 |
| `fallback_shape` | M/N/K shape 不满足导致的回退数 |
| `fallback_layout` | 无合法 repack/layout 导致的回退数 |
| `fallback_profile` | weight/activation profile 不兼容导致的回退数 |
| `fallback_dispatch` | 运行时派发条件不满足导致的回退数 |
| `gemv_calls/gemm_calls` | 分别进入 QBS Decode 型和 Prefill 型路径的 GGML 调用数 |
| `commands_m1..m4` | 实际按 M=1..4 发出的 QBS command 数 |
| `native_qbexec` | QEMU 实际执行的原生 `qbexec` 指令数 |
| `emulated_commands` | GGML 内部软件模拟执行的命令数；硬件闭环应为 0 |

单格式隔离实验通过 `GGML_RISCV_QBS_FORMATS` 只允许目标 profile。模型中的其他格式出现
`fallback_format_filter>0` 是实验设计所致，不是能力失败；目标 profile 自身应满足
`selected_tensors == candidate_tensors`，且 capability/shape/layout/profile/dispatch
fallback 为 0。

结束状态也必须同时成立：

```text
QBS_TOKEN_RUN_EXIT=RVV:0         普通 RVV 模型运行成功
QBS_TOKEN_RUN_EXIT=QBS_NATIVE:0  QBS 模型运行成功
QBS_LOGITS_RECORDS=68 status=OK  两组 record 完整且元数据对齐
LLAMA_GUEST_EXIT=0               guest 总体验证成功
```

### 13.9 当前真实模型闭环结果及读法

2026-08-25 使用真实 Qwen2.5 GGUF、相同 69-token 文本和 68 个 teacher-forced 检查点完成以下
单 profile 隔离实验：

| Profile | QBS/RVV PPL | Mean KL | Top-1 agreement | Top-5 overlap | Mean RMSE | Global max abs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Q3_K | 1.0012 | 0.00833 | 91.18% | 94.12% | 0.1656 | 1.2151 |
| Q4_K | 0.9893 | 0.00866 | 89.71% | 92.65% | 0.1715 | 1.1663 |
| Q5_K | 1.0230 | 0.00905 | 94.12% | 94.71% | 0.1754 | 1.1069 |
| Q6_K | 0.9855 | 0.00745 | 82.35% | 94.12% | 0.1676 | 1.0965 |
| Q8_0 | 1.0174 | 0.00235 | 97.06% | 95.59% | 0.0901 | 0.8997 |
| IQ4_NL | 1.0080 | 0.00217 | 98.53% | 95.00% | 0.0887 | 0.6807 |

这组数据支持以下有限结论：

- 六种目标 profile 均完成 68 条 record，目标 tensor 100% 进入原生 QBS，软件模拟为 0；
- PPL ratio 位于约 `0.986..1.023`，Mean KL 均低于 `0.01`，未见模型分布整体崩坏；
- Q8_0/IQ4_NL 的 KL 和 RMSE 最低；Q5_K 在该短片段上的 PPL 增幅最大，约 2.3%；
- Q6_K Top-1 agreement 最低，但 Top-5 overlap 仍为 94.12%、Mean KL 为 0.00745，说明许多
  差异更可能是接近候选的排名交换，而不是直接证明功能错误；仍需结合逐步 margin 和长文本回归；
- 这些数据证明的是当前固定文本上的工程精度闭环，不能表述成标准数据集精度无损，也不能将
  `ppl_ratio<1` 宣称为 QBS 提高了模型质量。

已有 Q2_K 68-step 实验得到 `ppl_ratio=0.9943`、`mean_kl=0.00352`、Top-1 92.65%、
Top-5 97.06%；Q4_0/Q5_0 也已有真实模型严格生成输出回归。九种 profile 的算子级 directed
test 全部通过，但论文级“所有格式质量等价”仍应补充更长文本、多个 prompt/seed 和标准
perplexity 数据集。

### 13.10 当前验证覆盖清单和剩余空白

截至本文状态，已经形成的验证深度如下：

| 层次 | 已有覆盖 | 主要证明 |
| --- | --- | --- |
| ABI 生成 | JSON 到 C/SV 生成物一致性、padded tail/link regression | 软件和 RTL 使用同一字段定义 |
| C reference | 九种 profile、两种 activation、两类 layout、shape/地址/原子提交 | canonical arithmetic/validation contract 可执行 |
| Profile RTL | 9 profiles x M1-M4 x row-count 1-4 x 3 data patterns，共 432 cases | decoder、integer subtotal、correction 和 FP 更新逐格式成立 |
| Command RTL | 22 个功能命令，覆盖 M1-M4、不同 N/K、tail/layout | descriptor 到 commit 的组合路径成立 |
| Fault RTL | validation、MMU、PMA、AXI/protocol fault | pre-compute 直接 fault、payload drain 和“失败不提交”均成立 |
| QEMU directed | 九种 profile、M1-M4、N=35 tail、三 expert `MUL_MAT_ID` | ISA、guest memory、repack、dispatch 与软件 shape 组合成立 |
| 真实 RTL 数据 | `format_closure.csv` 中 Q3_K/Q5_K/Q6_K/Q8_0 代表点及既有 Q4_K/Q6_K workload | 真实 GGUF bytes、activation 和 golden 可穿过 timing RTL |
| 模型级 QEMU | 七种 profile 有 68-step teacher-forced 指标；Q4_0/Q5_0 有严格生成回归 | 原生 `qbexec` 能运行真实模型且短片段质量未崩坏 |

这仍留下四类空白：

1. Q4_0/Q5_0 尚未达到其余七种 profile 相同的 68-step 指标深度；
2. 模型质量主要基于 Qwen2.5 和短固定文本，缺少多模型、标准数据集和长上下文；
3. module-level fault 已覆盖，但长命令中的 reset、interrupt、debug/kill 系统级压力仍需专门闭环；
4. QEMU 是功能模型，真实 RTL 的全格式、全模型执行成本以及综合/P&R/功耗不能由其替代。

因此“九种 profile 功能闭环”和“九种格式论文级模型质量闭环”是两条不同结论。前者已经具备，
后者尚未完全具备。

### 13.11 当前测试结果总览

下面汇总的是与本文所核 RTL 对应的当前结果。表中“通过”只对该行列出的证明目标有效，不能跨层
替代。例如 432 个 profile cases 不能证明 MMU fault，QEMU 模型运行也不能证明 RTL timing。

| 验证层次 | 当前结果 | 覆盖范围 | 可以得出的结论 |
| --- | --- | --- | --- |
| ABI/generated check | PASS（2026-08-26 复跑） | JSON 到 C/SV、R4 padded tail、hard-link alias | 软件和 RTL 字段、profile ID 与生成物一致 |
| Canonical C reference | PASS（2026-08-26 复跑） | descriptor、9 profiles、layout/tail/failure | numerical contract 和 validation 有可执行真源 |
| Profile RTL | 432/432 PASS | 9 profiles x M1--M4 x row-count 1--4 x 3 patterns | decoder、32-pair integer path、correction 和 FP update 组合成立 |
| Descriptor/read/commit RTL | 三个 standalone bench 均 PASS | descriptor legality；page/burst/outstanding/fault；4-lane commit/backpressure | 三个接口边界各自满足定向 contract |
| Compute command RTL | 22/22 PASS，fault discard PASS | 9 profiles、M1--M4、N/K/layout/tail | block adapter 到 hidden accumulator 的命令内路径成立 |
| End-to-end QBS RTL | 22/22 PASS，加 4 类 atomic-fault PASS | descriptor 到 VRF commit；validation/MMU/AXI/PMA fault | 成功结果可提交，失败命令在提交前不可见 |
| 真实数据 RTL closure | 4 对 RVV/QBS 点全部 PASS，两侧对同一 golden 的 mismatch 均为 0 | Q3_K/Q5_K/Q6_K 的 1.5B `attn_q`，Q8_0 的 0.5B `attn_q` | 当前 timing RTL 可消费真实 GGUF bytes 和 activation |
| 整模型 native QEMU | RVV/QBS 均退出 0，10-token prompt + 2-token greedy 输出逐字节一致 | Qwen2.5-1.5B Q4_K_M，Q4_K/Q6_K GEMV/GEMM、R4/M4、fallback | 真实 GGML graph 能发出并执行 native `qbexec`；不代表 RTL speedup |
| 模型级数值 | 7 profiles 有 68-step teacher-forced；Q4_0/Q5_0 有生成回归 | Q2_K/Q3_K/Q4_K/Q5_K/Q6_K/Q8_0/IQ4_NL logits；其余格式的定向模型回归 | 短固定文本未见分布崩坏；尚不是标准数据集质量结论 |

当前严格配对的四个真实 operator 点如下。`logical read` 是 timed region 中的逻辑 load payload，
不是 AXI 总线包含对齐、cache line 或 speculative traffic 后的物理字节数：

| Profile | Shape `K x N x M` | RVV/QBS matmul cycles | Speedup | QBS/RVV logical read | QBS/RVV retired instructions |
| --- | --- | ---: | ---: | ---: | ---: |
| Q3_K | `1536 x 256 x 1` | 1,281,131 / 17,614 | 72.73x | 30.3% | 0.51% |
| Q5_K | `1536 x 256 x 1` | 2,011,748 / 21,750 | 92.49x | 40.1% | 0.58% |
| Q6_K | `1536 x 256 x 1` | 1,273,230 / 25,120 | 50.69x | 44.1% | 0.68% |
| Q8_0 | `896 x 256 x 1` | 548,583 / 26,923 | 20.38x | 51.9% | 0.49% |

四点 matmul 几何平均为 `51.34x`。所有点的 `useful_pairs == pair_capacity`、
`read_outstanding_max=2`、`fp_table_full_cycles=0`、`commit_backpressure_cycles=0`，且 source
weight、activation、golden 和模型 metadata 的 hash 在 RVV/QBS 两侧严格配对。完整原始字段
位于 `hardware/format_closure.csv`；QBS phase 和 probe 是可重叠活动签名，不能相加成严格 stall
breakdown。

测试结论的边界同样明确：当前已经证明多格式功能、命令级 fault atomicity、真实算子 RTL 性能
和短文本模型数值闭环；尚未完成所有九种 profile 的统一 68-step/标准数据集质量、完整模型 RTL
token/s、跨 4-lane/1024-bit 以外配置、综合后时序、P&R 和功耗闭环。

## 14. 与相关研究和产品的关系

本节是截至 2026-08-25 的研究位置快照。需要先区分成熟度：Intel AMX、Arm SME2 和 NVIDIA
Blackwell 是已公开的工业 ISA/产品能力；SpacemiT IME 是已经落地的厂商 RISC-V 扩展；RISC-V
IME/AME 是标准工作组方向，不能写成已经 ratified 的统一矩阵 ISA；MixPE、F-BFQ 和 Gemmini
属于论文或开源研究平台。它们可以比较设计取舍，但不能把提案能力当作现成产品数据。

### 14.1 对照总表

| 路线 | 代表 | 架构状态 | 主要优化对象 | 与 QBS 的关键差异 |
| --- | --- | --- | --- | --- |
| 通用 VLA vector | RVV 1.0、Ara | 标准 vector registers | 通用 data parallel | QBS 在其上增加 profile/shape 命令，RVV 保留为 fallback |
| 集成矩阵扩展 | SpacemiT IME/Zvvm 方向 | 复用 vector registers 表示 2D tile | register-to-register matrix ops | QBS 从 memory 直接流入压缩 blocks，不把完整输入 tile 都架构化 |
| 独立/扩展 tile state | Intel AMX、Arm SME2 ZA、RISC-V AME 方向 | 独立或扩展二维矩阵状态 | dense matrix/outer-product | QBS 无长期 tile state，command-local accumulator 后提交 VRF |
| 软件微内核库 | Arm KleidiAI | 由 NEON/SVE/SME 状态决定 | pack + GEMV/GEMM microkernel | QBS 将 block decode/correction/reuse 下沉到硬件，但同样强调 capability、packing 和 fallback |
| 原生块缩放 Tensor Core | NVIDIA Blackwell NVFP4 | Tensor Core 原生消费 microscaled FP4 | 大规模 GPU GEMM/训练与推理 | 展示 block scale 已进入商用计算格式；其 FP4 数学、GPU execution model 与 GGUF/QBS 不同 |
| 外置/生成式加速器 | Gemmini 类 | 常有 scratchpad/DMA/专用 ISA | tile dataflow | QBS 复用 Ara MMU/AXI/异常/VRF，不建立独立 DMA 软件栈 |
| 量化算法-系统协同 | QServe | GPU kernel/runtime | 降低 W4A8 dequant 开销 | QBS 不提出新量化算法，直接执行现有 GGUF profile |
| 混合精度 PE | MixPE | 专用 PE | group scale/zero point 与 MAC | QBS 的 profile/correction 思路相近，但强调 llama.cpp ABI、RVV 共存和完整系统闭环 |
| llama.cpp block accelerator | F-BFQ | 可切换 block formats 的矩阵单元 | BFP/block quant matmul | 研究重叠较强；QBS 需以多 profile GGML 集成、命令原子性和 Ara/RVV 共存区分，不能声称首次支持 block quant |

### 14.2 从 SpacemiT/进迭时空学到什么

SpacemiT IME 的公开设计复用 RVV 的 32 个 vector registers 表示二维 tile，提供 int4/int8、
FP16/BF16、block quant 和 layout transform 类矩阵指令；其 llama.cpp/GGML 集成也强调模型加载
repack、完整 MUL_MAT kernel、GEMV/GEMM 分流与 RVV fallback。

QBS 借鉴的工程原则是：

- 不停留在单 `vec_dot`；优化完整 quantized linear operator；
- 存储格式与执行 layout 分离；
- Decode 和 Prefill 共享机制，但按 M 选择不同 reuse；
- 标准 RVV 永远作为功能回退。

QBS 没有照搬的部分是 vector-register matrix tile ISA。它选择 memory-to-VRF block stream，
因为 GGUF 权重本来就以压缩 block 驻留内存，若先用 RVV load/unpack到寄存器再执行矩阵指令，
会重新引入软件指令和 VRF traffic。

还要注意，当前 upstream llama.cpp 已经持续完善 RISC-V/RVV 的 repack GEMV/GEMM。研究比较不能
把早期逐行标量或未 repack 实现当作“RVV 上限”；QBS 应对比同一模型、同一量化格式和同等软件
优化程度的当前 RVV backend，才能把收益归因到 profile-aware hardware execution。

### 14.3 从 Arm KleidiAI 学到什么

KleidiAI 的 int4 matmul流程明确分为 RHS persistent packing、LHS dynamic quant/packing 和 matmul
microkernel，并用 shape/capability 选择 NEON/SVE/SME 变体。这与 QBS 的 R4 weight、Q8 activation
和 M/N tile 层次高度一致。重要启示不是复制 Arm 指令，而是保持：

- packer 与 microkernel layout 契约一致；
- weight packing 只做一次，activation packing按调用做；
- kernel selection 显式检查 type/shape/capability；
- 优化失败时能回到正确 baseline。

Arm SME2 又提供了另一个硬件参照：它使用可扩展 ZA 二维状态和 outer-product/multi-vector 指令
提高矩阵密度，KleidiAI 再把 framework operator、packing 和 microkernel 连接起来。QBS 与它
共享“CPU 内矩阵加速必须有软件库落地”的判断，但不采用可长期观察的 ZA tile，也没有把通用
dense outer-product 作为 ISA 中心。

### 14.4 从 Intel AMX 和 RISC-V Matrix 提案看状态成本

AMX 通过八个 1 KiB tile registers 和 TMUL 获得高密度矩阵计算，但 OS 需要管理 tile config 和
tile state。RISC-V 当前也同时探索 Integrated Matrix Extension（复用 vector registers）和
Attached Matrix Extension（独立 matrix state）。这些方案更适合广泛 dense matrix programming。

QBS 用较窄的 software contract 换取较小的 architectural surface：没有通用 tile load/store、
transpose 或持久 tile state，只支持声明的 block profiles 和 M/N/K。其优势是系统接入简单、
与现有 GGML 语义贴合；限制是不能冒充通用矩阵 ISA。

截至本文状态，RISC-V IME charter 的明确方向是基于现有 vector registers，并先聚焦 INT8、
BF16、FP32/FP64，后续再考虑 FP8、4-bit block FP 和 sparsity；AME 则定义与 vector state 正交的
attached matrix state。QBS 与二者都不是包含关系：它更窄地绑定 GGUF block semantics，同时
更强调 memory-to-VRF stream、异常原子性和现有 RVV fallback。

### 14.5 与近期块量化硬件研究的重叠边界

QServe、MixPE、F-BFQ 等工作已经说明低比特 payload、group metadata、dequantization 和混合精度
PE 的协同很重要。因此以下表述不能单独作为 QBS 创新：

- “支持 int4/int8 点积”；
- “支持多种 block quant format”；
- “融合 scale/zero-point correction”；
- “量化矩阵单元比标量解包快”。

QBS 更可辩护的研究中心是组合关系：

1. 用可查询、可版本化的 profile/layout/shape contract 承接 llama.cpp 现有量化生态；
2. 在 lane-based RVV processor 内，以命令局部状态直接消费 compressed blocks；
3. 复用普通向量的 MMU、异常、sequencer、VRF 和 fallback，避免独立 accelerator software island；
4. 用真实模型数据同时闭环多 profile、Decode/Prefill、tail、MoE 边界和模型级数值质量。

### 14.6 工业界正在收敛的共性

虽然 ISA 和产品形态不同，公开实现呈现出四个共同趋势：

1. **低比特只是起点**：scale、zero point/min、lookup table 和 accumulation precision 必须成为
   kernel 或硬件 contract 的一部分；
2. **持久权重与动态激活分工**：模型权重适合加载时一次 repack，activation 需要每次运行时量化
   和 packing；KleidiAI 的三微内核流程是典型软件实例；
3. **矩阵吞吐依赖数据布局**：AMX/SME/IME、GPU Tensor Core 和 GGML repack 都要求 tile/layout
   与计算原语配套，单独增加乘法器不能解决小请求、shuffle 和 metadata traffic；
4. **高性能路径必须可选择**：产品通过 feature discovery、kernel dispatch 和 fallback 保持同一
   framework 在不同硬件上运行，而不是让模型文件依赖一个不可查询的隐藏实现。

NVIDIA Blackwell 的 NVFP4 进一步说明 microscale/block scale 已经成为商用低精度计算的一部分，
但其每 16 元素 FP4 microblock 和两级 scale 与 GGUF K-quants 并不相同。它支持的是“块缩放值得
进入硬件”这一大方向，不能作为 QBS 九种 GGUF profile 已有工业等价实现的证据。

### 14.7 QBS 当前真正占据的位置

可以用两条轴定位现有方案：

```text
架构状态:  通用 vector state ---- command-local hidden state ---- 独立 tile/scratchpad state
格式语义:  通用整数/浮点 ---- profile 驱动 block quant ---- 固定模型/固定层数据流
```

QBS 位于两条轴的中间：比纯 RVV 更理解 GGUF block 和 tile shape，但比独立 NPU/矩阵 ISA 更少
长期状态；比单一 Q4 加速器覆盖更多 profile，但没有把 Transformer graph 固化。这个位置带来的
研究价值是系统组合，而不是某个低比特乘法本身。

同时，这个位置也产生必须正面回答的风险：profile 数增加会不会把 decoder 变成面积/时序负担；
阻塞 VLSU 会不会限制与普通 RVV 的重叠；软件 repack 和动态量化是否吞噬硬件收益；短命令的
descriptor/translation/commit 固定成本是否过高。论文评价应围绕这些问题给出面积、时序、覆盖率、
端到端性能和模型质量证据。

## 15. 当前方案的优势、限制与不能过度声称的内容

### 15.1 已形成的完整性

- 九组 profile 共用 decoder/dot/correction/FP/commit 主路径；
- M1-M4、N<=32、K 分段和尾块有软件/RTL/QEMU支撑；
- GGML 模型加载 repack、运行时 dispatch、普通 RVV fallback 已接通；
- QBS 与 Ara normal VLSU 有明确互斥和 assertion；
- fault 前结果不可见，成功后结果进入普通 VRF；
- 有真实 Qwen2.5 数据、完整 MUL_MAT 和整模型 QEMU 功能闭环。

### 15.2 当前限制

- QBS 命令阻塞 VLSU，尚未与普通 vector memory traffic 并发；
- dynamic activation quantization 仍在软件/RVV path；
- K>256 blocks 依赖软件分段，现有 R4 子段令 N 降为 4；
- 只覆盖列出的 profile，未覆盖全部 llama.cpp/IQ/TQ/MXFP type；
- M 最大 4，N 最大受 VLEN/32 和 32 上限约束；
- v1 数据接入固定为 128-bit AXI read beat，commit mapping 固定为 4 lanes；RTL 约束 VLEN 位于
  256..1024 且为 256 的整数倍，结合
  RVV 对 VLEN 为 2 的幂的要求，实际合法配置为 256/512/1024；这不是任意 Ara 配置已经自动
  支持的声明；
- 当前 ABI JSON、canonical reference 和 QEMU 尚未完整编码上述 `NrLanes/VLEN` 实现约束；reference
  接受的抽象 VLEN 范围比 `qbs_commit.sv` 更宽。VLEN=1024 固定实验不受影响，但在宣称跨配置
  可移植前，必须让 `qbinfo`、reference、QEMU、软件选择和 RTL 使用同一能力边界；
- 只直接覆盖 quantized `MUL_MAT`，不覆盖完整 Transformer block；
- current v1 contract 追求可执行一致性，不等于所有 GGML kernel 的 bitwise 累加顺序；
- QEMU 是 functional model，不能替代 RTL、综合、P&R 和 power 结果。

### 15.3 三种容易误解的说法

**错误：QBS 是把 Qwen 算子写死进硬件。**

正确：硬件只认识 profile/layout/shape，不认识 layer 名称；Qwen 是真实数据验证来源。

**错误：QBS 取代了 RVV。**

正确：QBS 只接管可支持的量化线性 tile，普通 RVV 仍执行 activation quantization、store、其他
算子和所有 fallback。

**错误：32 pair/cycle 就等于每周期 32 个模型元素。**

正确：decoder、subgroup、M 分配、read wait 和 FP update 都会影响 duty；必须看 useful pairs、
capacity、dot active、phase 和 payload/cycle。

## 16. 合理的扩展路线

### 16.1 近期：扩大模型级精度样本

- 将九种 profile 的算子级 directed test、七种 profile 的 68-step teacher-forced 比较，以及
  Q4_0/Q5_0 的严格生成回归保留为固定回归基线；
- 扩展多个 prompt、seed、上下文长度和生成长度，检查误差是否随序列推进而累积；
- 在标准 perplexity 数据集上比较 RVV 与 QBS，并同时记录 profile 覆盖率和 fallback 原因；
- 基于扩展结果冻结 numerical contract，再进行最终物理综合和论文级质量结论。

### 16.2 中期：减少未覆盖的线性层开销

- 将 activation quantization 与 QBS command 更紧密地流水化，但先定义 FP 输入和异常边界；
- 设计对 K segmentation 友好的 R4K layout，避免 split-K 时 N 降为 4；
- profile decoder 参数化扩展更多 GGUF type，但只在共享 datapath 足够时加入；
- 根据 Q8_0 的 FP/result bottleneck 调整 FP pipeline，而不是盲目增大 dot array。

### 16.3 更长期：从线性层扩到 LLM 数据流

可以研究但不应直接塞进 v1：

- QBS output 到下一 activation quantizer 的 on-chip forwarding；
- Attention Q/K/V projection 的多 descriptor 批处理；
- 稀疏/MoE expert routing 下的 gather-aware block stream；
- RMSNorm/activation/quantization fusion；
- 与 cache/prefetch hint 联动的 persistent weight tile；
- 多 QBS command overlap 或 normal VLSU 并发。

每项扩展都必须回答：它增加的是 profile、layout、shape 还是新的 architectural state？是否还能
保持能力查询和 RVV fallback？fault 前如何撤销？对上下文切换有什么影响？

## 17. 学习和调试方法

### 17.1 先确认模型侧的心智模型

进入 RTL 前应能独立回答：

1. token ID 为什么不能被当成有连续数值意义的输入？
2. Embedding lookup 与 LM head 虽可共享逻辑权重，为什么一个是 gather、另一个仍是大 GEMV？
3. `[T,1536]` 为什么分别变成 Q `[T,12,128]` 和 K/V `[T,2,128]`？
4. GQA 为什么能把本文单 token、单层 FP16 KV payload 降到 1024 bytes？
5. 首个输出 token 的 logits 属于 Prefill 还是 Decode？首个 Decode 输入又是什么？
6. 为什么短上下文时 FFN projection 是主要 MAC，而长上下文时 attention/KV 可能接管瓶颈？
7. 为什么 88.24% 只能称作每层固定 projection MAC 占比，不能称作端到端时间占比？
8. `GGML_OP_MUL_MAT`、架构 microkernel 和一条 `qbexec` 为什么不是一一对应？
9. 哪七个层内 projection 可进入 QBS，哪些 attention/normalization 操作仍必须由普通路径执行？
10. 一次真实模型生成正确，为什么仍不能替代 profile 算术和 RTL fault/commit 验证？

若这些问题尚不清楚，应回看第 2 节的 shape ledger、计算占比和模型到 GGML 的映射，再进入命令
状态机。否则很容易把“局部 QBS 加速”“整层加速”和“token/s 加速”混成同一结论。

### 17.2 从一个命令建立心智模型

建议先选 `Q4_K x Q8_K, M=1, N=4, K-blocks=1`：

1. 在 `qbs_ref.c` 查看一个 block 的 group trace；
2. 对照 `qbs_profile_decoder.sv` 检查 quant/scale/min/bsum；
3. 对照 `qbs_dot_array.sv` 看每周期 pair 如何分配；
4. 对照 `qbs_profile_engine_int.sv` 看 subgroup subtotal；
5. 对照 `qbs_fp_accumulator.sv` 看 FP micro-op 顺序；
6. 对照 `qbs_commit.sv` 看四个 FP32 结果进入哪个 lane/word。

之后再扩到 M4、N32、多 K blocks 和 R4/M4 tails。直接从完整模型波形开始会把 format、layout、
memory 和 FP pipeline 四类问题混在一起。

### 17.3 性能问题的证据顺序

```text
先确认 workload/shape/profile 和 payload hash
 -> 确认数值与 command coverage
 -> 看严格 phase
 -> 看 read range/AR/payload/outstanding
 -> 看 dot duty 与 pair utilization
 -> 看 FP table/uop/update
 -> 看 commit backpressure
 -> 最后才提出 RTL 修改
```

若需要周期级解释，使用有界 `QBS_ROOT_TRACE` 或 focused FSDB，明确能区分假设的信号；不要通过
反复改 bank、timeout、profile hint 试出一个偶然更快的点。

### 17.4 从症状定位到哪一层

| 症状 | 优先检查 | 不应先做什么 |
| --- | --- | --- |
| 所有格式都错 | descriptor/layout、activation 地址、commit mapping | 先改某个 profile decoder |
| 只有一种格式错 | ABI block bytes、bit-plane、scale/min、reference trace | 先放大 timeout |
| 只有 M3/M4 错 | M4 activation layout、vd group、inactive register/row | 假定是浮点误差 |
| 只有 N tail 错 | logical N、R4 padding、commit zero-fill | 改 dot array 宽度 |
| 多 K block 才错 | accumulator first/update 顺序、bank clear、K advance | 只看最终最大误差 |
| fault 后目的寄存器改变 | hidden state 与 commit 门控、fault drain | 用软件重试掩盖 |
| 数值正确但慢 | phase -> read -> dot -> FP -> commit 逐层计数 | 只按 lane utilization 改硬件 |
| QEMU 快/对但 RTL 不同 | QEMU 只建模语义，核查 RTL timing/handshake | 用 QEMU 证明 RTL 时序 |

### 17.5 掌握当前机制的自检问题

能够独立回答下面问题，才算建立了完整心智模型：

1. Q4_K 的 `d/dmin`、group scale/min 和 Q8_K `bsums` 分别进入哪一项公式？
2. `M=4, N=32, K=1536` 在软件、descriptor、hardware row tile 和 accumulator 中分别怎样表示？
3. 为什么当前 hardware 循环是 K-block major，并在一个 K block 内遍历 N rows？
4. 为什么 R4 padding 可以多读存储行，却不能多提交 architectural outputs？
5. 一个 AXI RRESP fault 从 read engine 到 sequencer fault 的过程中，哪些状态需要 drain，哪些结果
   必须保持不可见？
6. `pair_utilization=1` 而 `dot_duty` 很低时，为什么不能继续增加 multiplier？
7. GGML 在哪些检查失败后回退，回退是否发生在 repack 前还是命令执行中？
8. 为什么 QEMU native QBS 与 GGML emulation 的“参考”含义不同？
9. 为什么 activation quantization 若按 N tile 重复执行会破坏融合收益？
10. QBS 与 IME/AME/AMX/SME2/F-BFQ 最核心的 architectural-state 和 software-contract 差异是什么？

## 18. 当前源码索引

### 18.1 单一 ABI 真源

- `config/qbs_abi.json`：版本、指令、limits、profile 和 layout 真源。
- `scripts/gen_qbs_abi.py`：生成 C/SystemVerilog ABI。
- `apps/common/qbs_abi.h`：软件/验证生成头。
- `hardware/include/qbs_pkg.sv`：RTL 生成 package。

不要手改后两者；修改 ABI 后应重新生成并检查 diff。

### 18.2 RTL

- `hardware/src/ara_dispatcher.sv`
- `hardware/src/ara_sequencer.sv`
- `hardware/src/vlsu/vlsu.sv`
- `hardware/src/vlsu/qbs/qbs_engine.sv`
- `hardware/src/vlsu/qbs/qbs_descriptor_decoder.sv`
- `hardware/src/vlsu/qbs/qbs_read_engine.sv`
- `hardware/src/vlsu/qbs/qbs_block_adapter.sv`
- `hardware/src/vlsu/qbs/qbs_compute_engine.sv`
- `hardware/src/vlsu/qbs/qbs_profile_decoder.sv`
- `hardware/src/vlsu/qbs/qbs_profile_engine_int.sv`
- `hardware/src/vlsu/qbs/qbs_dot_array.sv`
- `hardware/src/vlsu/qbs/qbs_fp_accumulator.sv`
- `hardware/src/vlsu/qbs/qbs_commit.sv`

### 18.3 llama.cpp fork

当前本地 GGML 集成位于：

- `/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/qbs.h`
- `/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/qbs.cpp`
- `/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/qbs-layout.h`
- `/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/repack.cpp`

### 18.4 验证

- `verification/qbs/qbs_ref.[ch]`：canonical contract。
- `verification/qbs/qbs_ref_test.c`：constructed format/shape/layout tests。
- `verification/qbs/qbs_real_test.c`：真实 Qwen2.5 数据。
- `verification/qbs/qbs_*_tb.sv`：standalone/command RTL。
- `verification/qbs/qemu/`：QEMU `Xaraqbs` functional model 和整模型脚本。

### 18.5 被本文吸收但仍有独立用途的旧文档

- `ara_llm_kquant_dsa_proposal.md`：研究提案、历史检查点和论文实验设计。
- `llama_ara_dsa_performance_plan.md`：性能计数器、评测命令和多格式闭环。
- `llama_q4km_workload_and_ara_optimization.md`：真实模型 benchmark 分层和 shape。
- `spacemit_ggml_backend_study.md`：进迭时空 GGML backend 的源码研究。
- `verification/qbs/README.md`：快速验证入口。
- `verification/qbs/qemu/README.md`：QEMU 构建和整模型检查。

本文是机制教学入口；实验数字、运行目录和历史 go/no-go 结论仍应回到对应评测文档确认。

## 19. 外部资料与延伸阅读

### Qwen、Transformer 与推理基础

1. [Qwen2.5-1.5B-Instruct 官方配置](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct/blob/main/config.json)：本文 `L/D/F/Hq/Hkv/V`、RoPE 和 RMSNorm 参数来源。
2. [Qwen2.5 Technical Report](https://arxiv.org/abs/2412.15115)：Qwen2.5 模型系列、训练和部署背景。
3. [Attention Is All You Need](https://arxiv.org/abs/1706.03762)：Transformer、self-attention、multi-head attention 和 FFN 的原始定义。
4. [RoFormer/RoPE](https://arxiv.org/abs/2104.09864)：通过旋转 Q/K 表示位置和相对距离。
5. [RMSNorm](https://arxiv.org/abs/1910.07467)：RMS normalization 的定义和动机。
6. [Grouped-Query Attention](https://arxiv.org/abs/2305.13245)：query heads 分组共享 KV heads，以降低 KV 开销。
7. [GLU Variants Improve Transformer](https://arxiv.org/abs/2002.05202)：SwiGLU 等 gated FFN 变体。
8. [llama.cpp Qwen2 graph](https://github.com/ggml-org/llama.cpp/blob/master/src/models/qwen2.cpp)：GGUF tensor shape 与 Qwen2 GGML graph 的当前实现入口。

### 标准和基础架构

1. [RISC-V Vector Extension 1.0](https://docs.riscv.org/reference/isa/unpriv/v-st-ext)：VLA、VLEN、vector state 和精确异常。
2. [Ara 官方模块说明](https://github.com/pulp-platform/ara/blob/main/docs/source/modules/ara.md)：dispatcher、sequencer、lanes、VLSU、SLDU 和 MASKU。
3. [A New Ara for Vector Computing](https://arxiv.org/abs/2210.08882)：Ara RVV 1.0 lane-based 微结构与吞吐设计。
4. [RISC-V Integrated Matrix Extension charter](https://github.com/riscv-admin/integrated-matrix-extension/blob/main/charter.adoc)：复用 vector registers 的矩阵扩展方向。
5. [RISC-V Attached Matrix Extension charter](https://github.com/riscv-admin/attached-matrix-extension/blob/main/charter.adoc)：独立 matrix state 的另一条方向。

### llama.cpp 与软件微内核

6. [llama.cpp Tensor Encoding Schemes](https://github.com/ggml-org/llama.cpp/wiki/Tensor-Encoding-Schemes)：GGUF 量化格式索引；exact 位布局仍应以源码为准。
7. [llama.cpp CPU repack](https://github.com/ggml-org/llama.cpp/blob/master/ggml/src/ggml-cpu/repack.cpp)：CPU tensor trait、persistent repack 和 GEMV/GEMM 路径。
8. [Arm KleidiAI int4 matmul guide](https://github.com/ARM-software/kleidiai/blob/main/docs/matmul_qsi4cx/README.md)：LHS dynamic quant/packing、RHS persistent packing 和 microkernel contract。

### 产品与实现视角

9. [SpacemiT AI Matrix Extension](https://github.com/spacemit-com/docs-ai/blob/main/en/architecture/ime_extension.md)：复用 RVV register file 的矩阵和 block-quant 指令设计。
10. [SpacemiT IME specification](https://github.com/spacemit-com/riscv-ime-extension-spec)：厂商指令语义、program model 和示例。
11. [Intel AMX overview](https://www.intel.com/content/www/us/en/products/docs/accelerator-engines/what-is-intel-amx.html)：八个 1 KiB architectural tile registers 与 TMUL。
12. [Arm SME/SME2 matrix model](https://developer.arm.com/community/arm-community-blogs/b/architectures-and-processors-blog/posts/matrix-matrix-multiplication-neon-sve-and-sme-compared)：ZA 二维状态、outer-product 和 scalable tile。
13. [NVIDIA NVFP4](https://developer.nvidia.com/blog/?p=102000)：Blackwell Tensor Core 的 16-element microscale FP4 与两级 scale。

### 块量化和协同加速研究

14. [QServe, MLSys 2025](https://proceedings.mlsys.org/paper_files/paper/2025/hash/fbe2b2f74a2ece8070d8fb073717bda6-Abstract-Conference.html)：低比特服务中 dequantization overhead、KV quantization 与软硬件协同。
15. [MixPE](https://arxiv.org/abs/2411.16158)：group quantization、mixed-precision PE 和“group dot 后反量化”。
16. [F-BFQ](https://arxiv.org/abs/2510.13401)：面向 llama.cpp block quantization 的可切换格式加速器，是 QBS 必须正面对照的相近工作。
17. [Gemmini](https://arxiv.org/abs/1911.09925)：生成式矩阵加速器的 ISA、scratchpad、软件栈和系统集成视角。

## 20. 术语速查

| 术语 | 含义 |
| --- | --- |
| QBS | Quantized Block Streams，量化块流执行机制 |
| Token | tokenizer 定义的离散文本单元；模型输入和输出使用其整数 ID |
| Embedding | 把 token ID 查表为 hidden vector；不是普通连续数值转换 |
| Hidden state | 某个 token 在某层的内部特征向量，本文 Qwen2.5 宽度为 1536 |
| Activation | 由当前输入运行时产生的中间 tensor，区别于固定模型权重 |
| Logits | 模型对词表中每个候选 token 给出的未归一化分数 |
| Head | Attention 中一个独立的 Q 子空间；每个 head 在本文为 128 维 |
| GQA | 多个 query heads 共享较少的 K/V heads，降低 KV-cache 容量和带宽 |
| KV cache | 保存历史 token 的 K/V，使 Decode 不必重算历史层状态 |
| Prefill | 一次处理 prompt 的多个 token，并建立各层 KV cache |
| Decode | 每次处理一个新 token，读取历史 KV cache 并继续自回归生成 |
| GGML operator | GGML graph 中带输入、输出和语义的计算节点，例如 `MUL_MAT` |
| Microkernel | operator 在特定架构、格式和小 tile 上调用的底层计算实现 |
| Profile | 一种 weight/activation block 数学与字节布局契约 |
| Native block | GGML 格式定义的最小量化块，当前为 32 或 256 elements |
| Subgroup | block 内共享局部 scale/min 的元素组 |
| R4 | 同一 K block 的四个 output rows 交错存放 |
| M4 | 同一 K block 的四个 activation rows 交错存放 |
| M | 同一命令的 activation/input rows |
| N | 同一命令的 output/weight rows |
| K-blocks | 归约维包含的 native block 数 |
| `bsums` | Q8_K 每 16 elements 的 int16 activation sum，用于 affine min correction |
| `qbinfo` | 软件查询 QBS capability 的指令 |
| `qbexec` | 执行一个 QBS MxNxK-block microtile 的阻塞命令 |
| Capability discovery | 软件在运行时查询版本、shape、layout 和 profile，而不是按 CPU 名称猜能力 |
| Command-local dataflow | 数据在一条命令内部按 valid/ready 流过多个阶段，但命令间不保留可见数据流状态 |
| Hidden accumulator | 命令内部 FP32 部分和，成功前不是架构可见状态 |
| Atomic commit | 所有访问/计算成功后，才将完整结果写入 VRF |
| Split-K | 软件把过长 K 分成多条命令，再按原顺序累加 FP32 partial results |
| Native QBS | guest 实际执行 `qbexec`，区别于 GGML 内部 scalar emulation |
| Selection coverage | QBS 实际选中的候选 tensor/elements 比例，不包含本就不支持的非线性算子 |
| Teacher forcing | 两条路径使用相同历史 token，逐位置比较下一 token 分布，避免自由生成分叉干扰归因 |
| RVV fallback | QBS 不适用时使用标准 RISC-V Vector 实现 |

掌握 QBS 的关键不是记住每个状态名，而是始终把四条线对齐：**量化数学、内存 layout、命令
shape 和架构可见性**。只有四者一致，软件选中的算子才会被硬件按正确字节解释、以可证明的
顺序完成，并在普通 RVV 程序中保持可组合性。
