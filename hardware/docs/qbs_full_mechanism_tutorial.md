# QBS/AKV 全机制教学：从 llama.cpp 模型算子到 RVV 协同执行

> 文档状态：2026-09-03。硬件代码锚点为 `1cde6c45990a`，本地 llama.cpp/GGML backend
> 锚点为 `f896237df65c`。本文逐项对照 QBS/AKV ABI、RTL、公共运行时、QEMU functional model、
> GGML selector 和归档验证证据核查。本文只讲当前采用的机制和选择规则。实验数字的精确复现
> 仍以对应目录中的 manifest、source diff、binary 与输入哈希为准。

## 1. 阅读目标与一句话定位

本文希望回答九个连续的问题：

1. 文本如何经过 Qwen2.5 的 token、Attention、FFN 和 LM head 变成下一 token；
2. llama.cpp 的块量化线性层到底在计算什么，为什么普通 RVV 仍有明显开销；
3. QBS（Quantized Block Streams）把哪些块量化线性层语义显式交给硬件；
4. AKV（Attention K/V Context）为什么不增加私有 Attention 算术阵列，而是改变 K/V 的驻留和视图；
5. GGML 如何按 type、shape、layout、capability 和算法边界选择两条快路径；
6. QBS 的 activation context 与 AKV 的 K/V context 分别保存什么，为什么不能按地址隐式命中；
7. QBS/AKV 如何复用 MMU、AXI、sequencer、VRF 和异常完成域，同时保持普通 RVV fallback；
8. 当前机制实际验证过哪些模型、量化格式和 Attention shape，哪些只是功能兼容而非硬件加速；
9. 当前方案与矩阵扩展、外置加速器、商用 CPU AI 扩展以及块量化研究之间是什么关系。

QBS 不是一种新的模型量化算法，也不是把整个 Transformer graph 固化为硬件。它是一个
**面向 GGML 块量化线性层的、命令级、profile 驱动的压缩数据流执行路径**：软件描述
量化格式、数据布局和 `M/N/K` shape，硬件直接读取压缩权重与动态量化激活，在命令内部完成
解包、整数点积、scale/min correction、FP32 累加。只有全部潜在故障访问和计算完成后，它才
通过现有 lane result port 分周期写入普通 RVV 向量寄存器；提交期间 sequencer 仍阻止年轻指令
观察部分结果，因此保持单条命令的故障原子性。

AKV 解决的是另一类瓶颈。Attention 中的 Q/K/V 是运行时数据，不是 GGUF 块量化权重；将它们
伪装成新的 QBS profile 会混淆数据生命周期和数值算法。AKV 因此只提供**显式管理的 K/V
驻留上下文和 token-axis 局部视图**，而 QK 点积、scale/mask、online Softmax、PV 聚合与最终
归一化仍由标准 RVV 指令执行。这样既保留 RVV 的通用算术能力，又避免同一 K/V tile 被反复从
外部存储器读取、转置或以不利于 token-axis 计算的方式重放。

可以先记住下面两条端到端链路：

```text
GGUF 原始块量化权重
  -> 模型加载时持久化 R4 repack
  -> GGML_OP_MUL_MAT 运行时量化 activation
  -> qbinfo 能力检查与 M/N/K 分块
  -> qbexec(descriptor, activation, vd, M)
  -> QBS 读取压缩块、解码、点积、修正、FP32 累加
  -> 结果写入从 vd 开始的普通向量寄存器组（软件示例使用 v8...v15）
  -> 标准 RVV vse32.v 写回 GGML 输出 tensor

GGML_OP_FLASH_ATTN_EXT 的运行时 Q/K/V
  -> GGML 检查 dtype、D、GQA、stride、mask 和 Prefill/Decode 算法边界
  -> AKV FULL/REFILL 将一个有界 K/V tile 放入隐藏 context
  -> AKV row/column/panel view 经正常 VRF result path 提供给 RVV
  -> 标准 RVV 完成 QK、scale/mask、Softmax、PV 和输出归一化
  -> 不支持或测得无收益的 shape 完整回退到原 GGML/RVV Attention
```

当前机制地图如下。这里“驻留”表示命令管理的隐藏数据，不是新增长期可编程寄存器文件：

| 路径 | 加速对象 | 隐藏状态 | 算术执行者 | 当前生产边界 |
| --- | --- | --- | --- | --- |
| 标准 RVV | 所有未选择的 GGML operator | 无专用 context | lanes/MFPU/VLSU | 永远保留的正确性与兼容 fallback |
| QBS | 量化 `MUL_MAT`/受约束 `MUL_MAT_ID` | command-local FP32 accumulators；可选 Q8_K activation context | QBS decoder、32-pair integer dot 和共享 FP update | 9 种 weight profile；默认 M1--M4/N32，可显式启用受流量门控的 M5--M8/N16 |
| AKV Decode | 单个 Query token 读取历史 K/V | 64-token、8-bank K/V context | 标准 RVV | F32 Q、F16 K/V/mask、F32 output，D64/96/128，GQA1..8 |
| AKV Prefill | tiled causal Attention | 同一 64-token K/V context；软件维护 64-Query block | 标准 RVV | Query tokens >=64，并与 GGML tiled Attention 的计算顺序一致 |

### 1.1 建议阅读顺序

如果目标是能够独立修改和验证 QBS/AKV，而不只是知道它们“能加速 LLM”，建议按以下顺序阅读：

1. 先读第 2 至 4 节，建立量化数学、profile 和 Q8 activation 的概念；
2. 再读第 5、6 节，理解软件怎样把一个 GGML operator 转换成 descriptor 和多条命令；
3. 然后读第 7 至 10 节，分别沿 QBS 和 AKV 的控制、数据、完成路径走完 RTL；
4. 用第 11、12 节判断性能计数器，而不是从单个 utilization 数字猜瓶颈；
5. 最后用第 13 至 16 节区分功能证明、模型质量、研究贡献和未来扩展。

读完后至少应能回答六个问题：某个 weight byte 怎样参与一个 FP32 输出；为什么 R4/M4/M8 不改变
数学结果；为什么 QBS activation context 和 AKV K/V context 都必须显式管理；为什么 AKV 要按
token banking 而不是只增加缓存容量；为什么 fault 前不能暴露部分状态；为什么一个不支持的 tensor
或 Attention shape 会回到普通 RVV，而不是进入“近似兼容”的快路径。

### 1.2 三种“正确”不能混用

本文反复区分三类结论：

| 层次 | 要证明什么 | 主要证据 |
| --- | --- | --- |
| 架构正确 | 指令、异常、寄存器、隐藏 context 和内存可见行为符合 contract | canonical reference、QEMU、RTL command/fault test |
| 算术正确 | block decode、整数 subtotal 和 FP update 顺序一致 | constructed vectors、逐 accumulator bit comparison |
| 模型可用 | 合法浮点差异没有造成不可接受的模型质量变化 | logits、KL、PPL、Top-k 和生成回归 |

QEMU 跑通模型不能替代 RTL 算术证明，RTL 与 reference bit-exact 也不能自动证明长文本质量无损。
同样，microtile 加速不能直接等价为端到端 token/s 加速；Host selector 命中也不能替代实际命令
执行。文中所有覆盖率都必须说明分母是 tensor、operator call、命令、MAC，还是完整模型周期。

### 1.3 初学者先认识这些对象

后文会反复使用下面这些词。它们不是同一层的东西：模型文件保存数据，`llama.cpp` 组织推理，
GGML 描述计算，RVV/QBS/AKV 才负责在处理器上执行。

| 名词 | 用直白的话解释 | 在本项目中的例子 |
| --- | --- | --- |
| 大语言模型（LLM） | 一组固定参数和计算规则；输入已有 token，输出下一个 token 的分数 | Qwen2.5、Qwen3、Llama、Phi、Gemma |
| 参数/权重（weight） | 训练后固定下来的大量数字，决定模型学到的变换 | Q/K/V projection、FFN 和 LM head 的矩阵 |
| 激活（activation） | 模型处理当前输入时临时产生的数据；换一句话就会变化 | 某层某个 token 的 1536 维 hidden vector |
| 张量（tensor） | 多维数字数组；向量是 1 维张量，矩阵是 2 维张量 | `[token数, hidden维度]` |
| shape | 张量每个维度的长度 | `[15,1536]` 表示 15 个 token、每个 1536 个数 |
| token | tokenizer 划分出的文本单元及其整数编号，不一定等于一个汉字或单词 | 用户输入被转换成一串 token ID |
| GGUF | 磁盘上的模型文件格式，保存参数、shape、量化类型和模型 metadata | `Qwen...Q4_K_M.gguf` |
| `llama.cpp` | 读取 GGUF 并执行完整推理的程序，包括 graph、KV cache、线程和采样 | `llama-cli` 及其 CPU backend |
| GGML | `llama.cpp` 内部的张量、算子和计算图基础设施 | `MUL_MAT`、`FLASH_ATTN_EXT` |
| 算子（operator） | 计算图中的一项完整数学操作 | 矩阵乘、RMSNorm、RoPE、Attention |
| kernel | 某个算子在特定 CPU/数据类型上的底层实现 | RVV Q4_K GEMV kernel |
| backend | 为一批 GGML 算子选择并执行 kernel 的后端 | 标准 CPU/RVV、QBS、AKV |
| RVV | RISC-V 标准向量指令；它是所有未选择专用路径时的通用执行基础 | `vle`、`vwmacc`、`vfredsum`、`vse` |
| contract（契约） | 软件和硬件共同遵守的精确定义，包括字段、数据布局、合法范围和结果规则 | QBS/AKV ABI 与数值顺序 |
| profile | 一种量化 block 的精确字节布局和数学公式，不只是“几 bit” | Q4_K、Q6_K、Q8_0 |
| tile（分块） | 从大矩阵或长序列中取出、一次处理的有界小块 | QBS 的 MxN 输出块、AKV 的 64-token K/V 块 |
| view（视图） | 不复制数学数据，只按某种计算需要的方向读取同一份存储 | K column view、V row view |
| descriptor | 软件放在内存中的命令参数表，硬件读取后才知道地址、shape 和布局 | QBS 16 B descriptor、AKV 64 B descriptor |
| context | 专用命令管理的一小块隐藏片上数据；只有完整填充成功后才能使用 | QBS activation snapshot、AKV K/V tile |
| selector | 运行时的选择函数；先检查条件，再决定走快路径还是普通路径 | QBS tensor selector、AKV Attention selector |
| fallback | 专用路径不适用时，完整调用原来的正确实现 | D256 Attention 回到标准 RVV |
| native execution | 程序真的发出并执行自定义硬件指令，而不是在 C/C++ 中模拟结果 | QEMU 中执行 `qbexec` |
| functional emulation | 用软件按照同一规则算结果，适合检查功能，不代表 RTL 周期 | GGML 的 AKV reference 模式 |
| RTL leaf | 从真实模型中截取、可独立仿真的一个算子或小数据片段 | D128/GQA6 Decode Attention 测试 |
| 验证闭环 | 输入、执行路径、结果、计数和回退原因都能相互核对 | 模型输出正确且命令/工作量计数守恒 |

一次推理从文件到硬件的关系如下：

```text
GGUF 模型文件
  -> llama.cpp 读取权重和模型配置
  -> GGML 建立由许多 operator 组成的计算图
  -> 每个 operator 根据类型和 shape 选择执行 kernel
       -> 支持的量化 MUL_MAT：QBS
       -> 支持的 FLASH_ATTN_EXT：AKV 提供数据，RVV 完成算术
       -> 其他情况：标准 RVV/CPU fallback
  -> 得到 logits
  -> llama.cpp 的 sampler 选择下一个 token
  -> 重复直到生成结束
```

QBS 和 AKV 看不到用户输入的中文，也不知道“这一层在回答什么问题”。它们只接收数字、地址和
shape。模型通用性正来自这条边界：硬件不判断模型名字，只判断当前算子的数据格式和尺寸是否
满足已声明的规则。

### 1.4 给已经熟悉 Ara/RVV 的读者：先建立差分心智模型

如果你已经熟悉原 Ara 的 dispatcher、sequencer、lane、VRF 和 VLSU，不需要把
QBS/AKV 当成一台另外的处理器重新学习。最有效的方法是先固定“什么没变”，再跟踪
两类新语义在既有完成域中如何流动。

| 你已经熟悉的 RVV 部件 | 保持不变的职责 | QBS/AKV 增加的内容 |
| --- | --- | --- |
| Dispatcher | 解码指令并构造 vector request | 识别 `qbexec/qbinfo` 和 AKV 指令，将 GPR、`vd`、M 及命令类型放入请求 |
| Sequencer | 分配 `vid`、跟踪目的寄存器和功能单元完成 | 把长命令当作正常在飞 vector request；在 terminal 前阻止年轻指令观察部分结果 |
| VLSU | 拥有 MMU/PMA、AXI 和 load-result 路径 | 增加 normal/QBS/AKV owner 仲裁；三者复用同一翻译、存储请求和结果端口 |
| Lanes/VRF | 保存架构 vector state，执行整数、浮点、reduction 和 store | QBS 将 FP32 tile 结果提交到 VRF；AKV 将 F16 局部 view 送入 VRF，Attention 的 FP32 累加仍由 lanes/MFPU 执行 |
| Vector CSR/异常域 | 维持 `vl/vtype/vstart/fflags`、顺序和 trap 可见性 | wrapper 设置合法的 RVV 结果几何；专用命令在原子发布/提交前不改变可见状态 |
| 标准 RVV kernel | 执行任意未专用化的 vector 工作 | 成为每个 selector 的完整 fallback，也执行 activation 量化、Softmax、QK/PV 和其他算子 |

只需记住一个根本区别：**QBS 是在 VLSU 资源域中执行压缩矩阵 microtile 的长命令；
AKV 是向普通 RVV Attention 提供有生命周期局部数据 view 的长命令族。** 前者新增块量化
计算路径，后者不新增 Attention 乘加/Softmax 阵列。这个区别贯穿 ISA、RTL、验证和
性能解释。

### 1.5 先问“状态归谁、活多久、何时可见”

整套机制最容易混淆的不是乘加公式，而是状态边界。下表是后文所有模块的总索引：

| 状态域 | 主要内容 | 所有者 | 生命周期 | 软件何时可见 |
| --- | --- | --- | --- | --- |
| RVV 架构状态 | VRF、`vl/vtype/vstart`、`fflags`、内存结果 | sequencer/lanes/VLSU | 跨指令，按 RVV 规则更新 | 指令正常完成后 |
| 在飞命令状态 | `vid`、功能单元 owner、目的寄存器保留、success/fault | sequencer + VLSU | request accept 到 terminal handshake | 只通过完成、trap 和后续相关行为体现 |
| QBS 命令局部状态 | descriptor snapshot、block banks、integer subtotal、FP32 accumulators | `qbs_engine` 及其子模块 | 单条 `qbexec` | 成功后仅通过 VRF tile 结果可见；fault 时全部丢弃 |
| QBS activation context | ID/generation、profile/layout/shape metadata、Q8_K snapshot | `qbs_activation_context` | FILL 成功发布到 RELEASE/替换/invalid | 不可直接读；后续 `qbexec` 只能按显式 ID/generation REUSE |
| AKV context | Query group、K/V tile banks、D/GQA/tile metadata、valid state | `akv_context`/`akv_v2_context` | FULL 或 REFILL 成功发布到 RELEASE/替换/invalid | 不可直接读；只能经 row/column/panel view 进入 VRF |
| GGML 软件状态 | graph、tensor metadata、R4 cache、activation workspace、KV-cache 地址、online-Softmax 状态 | llama.cpp/GGML | 模型、graph、operator 或 tile 级 | 普通软件数据；不由专用命令自主推断 |

对任何新信号或优化，都应先回答四个问题：谁写它；哪个事件使它有效；哪个事件清除它；如果中途
fault，程序能否观察到部分状态。第 3.2 节给出设计原则，第 8 节沿命令走完生命周期，第 9 节再对应到
每个 RTL 模块。

## 2. 从一句自然语言到 QBS/AKV：先完整理解 Qwen2.5 推理

QBS 和 AKV 位于一条很长的实现链路底部。若只观察 `Q4_K x Q8_K` 点积或 K/V SRAM，很容易知道硬件“算了什么”，
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
tensor 采用混合精度策略。模型结构决定矩阵 shape，模型级量化配方决定不同 tensor 采用哪些
encoding，逐 tensor encoding 决定 block 字节和数值公式，QBS profile 则决定硬件如何严格消费
其中受支持的 encoding。这四个层次不能互换。

关于 llama.cpp/GGML/GGUF 的软件层级、模型级 recipe 与逐 tensor encoding 的区别，以及当前
格式族的公式，集中见第 2.22 至 2.24 节。这里先继续沿模型前向顺序理解 token 和 Transformer。

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
大量权重，通常更受 weight bandwidth 和低比特解码开销影响。当前 QBS 因此同时提供 M1 GEMV、
默认 M1--M4/N32 micro-GEMM，以及可显式启用的 M5--M8/N16 权重复用路径，而不是只优化一个
固定 batch shape。宽 M 路径只在 capability 支持且精确 byte-cost 模型预测输入流量至少降低 15% 时
可选；由于当前 RTL 周期证据尚不支持默认开启，它是可诊断的自适应能力，不是默认生产策略。

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

若只用理论 MAC 估算 QBS 所针对的固定量化线性层在“固定 projections + LM head + dynamic
attention core”中的比例，可写为：

```text
QBS-eligible fixed-linear MAC fraction
  = 1,543,569,408 / (1,543,569,408 + 86,016*S)
```

| Decode 上下文 `S` | 固定量化线性 MAC 占该 MAC 分母 |
| ---: | ---: |
| 256 | 98.6% |
| 1024 | 94.6% |
| 4096 | 81.4% |
| 16384 | 52.3% |
| 32768 | 35.4% |

这里的“eligible”只表示算术结构可能映射到 QBS，并假定 type/shape/capability 均合法；它不是
实测 dispatch coverage，更不是端到端周期占比。RMSNorm、RoPE、Softmax、activation quantization、
KV-cache traffic、sampling 和 runtime 开销均不在该 MAC 分母中。真正的模型覆盖必须把本表与
第 13.8 节的 tensor selection counter、operator trace 和端到端 profiler 分开报告。

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

| 模型步骤 | 典型 GGML 行为 | 输入 -> 输出 shape | 主要底层行为 | 当前 QBS |
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
  -> 默认按 M<=4/N<=32；显式启用且流量有利时可用 M<=8/N<=16
  -> K 超过命令上限时由软件分段
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

### 2.22 `llama.cpp`、GGML、GGUF 和 backend 分别是什么

“支持模型在硬件上运行”不是某一个文件或库的名称，而是一条软件栈。本文使用以下严格称呼：

| 层次 | 作用 | 与 QBS 的关系 |
| --- | --- | --- |
| `llama.cpp` | 完整 LLM 推理 runtime，负责模型加载、graph 构建、KV cache、sampling 和命令行接口 | 端到端模型执行入口 |
| GGML | tensor、operator、graph、buffer 和 CPU kernel 基础设施 | `MUL_MAT` 选择 QBS 或 RVV kernel 的位置 |
| GGUF | 模型文件容器，保存 metadata、tensor shape、逐 tensor type 和 payload | QBS 消费的压缩权重来源，但 GGUF 本身不是计算库 |
| GGML backend | 把 graph operator 映射到某类设备或 ISA 的实现 | 当前是带 QBS capability dispatch 的 RISC-V CPU backend |
| QEMU `Xaraqbs` model | 执行 `qbinfo/qbexec` 的 ISA/功能模型 | 验证 guest 软件和指令语义，不是 QBS 硬件本体，也不是性能模型 |
| QBS RTL | 集成在 RVV processor 中的可综合硬件实现 | 真实处理 descriptor、访存、block decode、计算和 VRF commit |

因此，准确的系统级表述是“**QBS-enabled llama.cpp RISC-V CPU backend**”或“端到端
QBS-enabled llama.cpp inference stack”，而不是把 GGUF、QEMU 或 llama.cpp 本身称为硬件。

### 2.23 文件名、模型量化配方和 tensor encoding 为什么不是一回事

一个 GGUF 模型同时存在三个容易混淆的标识：

| 标识 | 例子 | 严格含义 |
| --- | --- | --- |
| 文件名后缀 | `Qwen2.5-1.5B-Instruct-Q4_K_M.gguf` | 发布者采用的命名惯例，可以被任意重命名，不是可信的机器契约 |
| 模型级 file type/recipe | `LLAMA_FTYPE_MOSTLY_Q4_K_M` | quantizer 如何按 tensor 角色选择混合格式；`S/M/L` 等后缀表示配方档位 |
| 逐 tensor `ggml_type` | `GGML_TYPE_Q4_K`、`GGML_TYPE_Q6_K` | 该 tensor 在 GGUF 中真实采用的 block ABI、字节数和反量化公式 |

`Q4_K_M` 不是一种名为 `GGML_TYPE_Q4_K_M` 的 block。它通常让大部分矩阵使用 Q4_K，同时把
部分对质量敏感的矩阵保留为 Q6_K 或其他较高精度类型；具体混合规则还可能随模型架构、quantizer
版本和 importance matrix 改变。当前完整 Qwen2.5-1.5B Q4_K_M 验证文件的 QBS repack trace 中，
候选权重实际包含 169 个 Q4_K tensor 和 30 个 Q6_K tensor，正说明不能根据文件名把全部权重
解释成 Q4_K。这里的“候选”是加载期 repack 选择口径，不等同于这些 tensor 都在运行期执行了
`MUL_MAT`；实际执行还要检查 operator-call 和 `native_qbexec` counter。

可靠信息来自 GGUF metadata 和每个 tensor 的 type，而不是文件名。加载时可用：

```bash
./build/bin/llama-cli -m model.gguf -n 0
```

查看 loader 打印的 type 统计，也可用 `gguf-py` 的 dump 工具检查逐 tensor metadata。论文若写
“模型为 Q4_K_M”，应同时说明这是模型级配方；若讨论硬件 profile，则必须写实际的 Q4_K、Q6_K
等 tensor encoding。

### 2.24 llama.cpp 当前主要格式族、名称和数学含义

当前本地 llama.cpp 的 `ggml_type` 可按下表归纳。公式中的 `q_i` 是存储整数或码本索引，`d/D`
是 block scale，`m` 是 offset/min，`s_g/m_g` 是 subgroup metadata；帽号表示反量化近似值。

| 格式族 | 当前主要 tensor types | 代表性反量化关系 | 设计目的 |
| --- | --- | --- | --- |
| 原生数值 | F32、F16、BF16、F64、I8/I16/I32/I64 | 直接按相应数值格式解释 | 高精度 tensor、metadata 或普通整数 |
| 基础 `_0` | Q1_0、Q2_0、Q4_0、Q5_0、Q8_0 | Q1_0: `x_hat=d*q, q in {-1,+1}`；Q2_0: `d*(q-1)`；Q4_0/Q5_0: `d*(q-8/16)`；Q8_0: `d*q` | 单 scale、规则解码，块大小通常为 32，Q1_0/Q2_0 例外 |
| 基础 `_1` | Q4_1、Q5_1、Q8_1 | `x_hat=d*q+m`；Q8_1 还保存辅助 block sum | affine block；Q8_1 多用于点积中间表示而非主要模型权重配方 |
| K-quant | Q2_K、Q3_K、Q4_K、Q5_K、Q6_K、Q8_K | affine Q2/4/5_K 近似 `D*s_g*q-Dmin*m_g`；symmetric Q3/6_K 近似 `D*s_g*q`；Q8_K 为 `d*q` 并保存 `bsums` | 256-element superblock 内再分 subgroup，以 metadata 换取质量 |
| IQ | IQ1_S/M、IQ2_XXS/XS/S、IQ3_XXS/S、IQ4_NL/XS | `x_hat=d_g*C[index]`，由非线性码本、符号和局部 scale 组合 | importance-aware/codebook quantization，低 bit 下提高质量 |
| TQ | TQ1_0、TQ2_0 | `x_hat=d*t, t in {-1,0,+1}` | 紧凑 ternary quantization |
| Microscaling FP | MXFP4 | `x_hat=scale_E8M0*FP4_E2M1(q)` | OCP microscaling FP4，32-element block |
| NVIDIA FP4 | NVFP4 | 概念上为 `s_global*s_E4M3,g*FP4_E2M1(q)` | 16-element local block scale 加 tensor/global scale |

K-quant 的实际平均位宽必须把 metadata 算入，不能只读名称中的数字。按当前 block ABI，Q2_K、
Q3_K、Q4_K、Q5_K、Q6_K 分别约为 2.625、3.4375、4.5、5.5、6.5625 bit/weight。`_K` 表示
K-quant 的 256-element superblock 家族，**不是矩阵乘中的 K 维**；`S/M/L` 和
`XXS/XS/S/M` 通常是模型级质量/体积配方档位，也不是新的逐 tensor 数学类型。例如
`Q3_K_M` 可以混用多个 tensor type，却不存在一个同名的 `GGML_TYPE_Q3_K_M`。

Q1_0 每 128 个元素保存 16 B bit payload 和 2 B FP16 scale，约 1.125 bit/weight；Q2_0 每
64 个元素保存 16 B payload 和 2 B scale，约 2.25 bit/weight。这也说明名称中的“1/2 bit”只指
核心 quant payload，不能忽略 block metadata。

当前 `llama_ftype` 中仍有效的模型级 recipe 可按下表归类：

| Recipe 家族 | 当前名称 |
| --- | --- |
| 原生/高精度 | F32、mostly-F16、mostly-BF16 |
| 基础 Q | Q1_0、Q2_0、Q4_0、Q4_1、Q5_0、Q5_1、Q8_0 |
| K-quant | Q2_K、Q2_K_S、Q3_K_S/M/L、Q4_K_S/M、Q5_K_S/M、Q6_K |
| IQ | IQ1_S/M、IQ2_XXS/XS/S/M、IQ3_XXS/XS/S/M、IQ4_NL/XS |
| Ternary/FP4 | TQ1_0、TQ2_0、MXFP4_MOE、NVFP4 |

它们是“怎样量化整份模型”的策略，不保证所有 tensor 都使用同名 encoding。Q4/Q5 `_0/_1`、
K-quant、IQ 和 TQ 的精确 GGUF block ABI 主要由 GGML/llama.cpp 生态定义，虽也被 whisper.cpp
等同生态项目共享；F16/BF16 等是通用数值格式，MXFP4 来自 OCP 规范，NVFP4 则是 NVIDIA 定义
的格式。相似的低比特/分组缩放思想很通用，但 byte layout 不能跨生态仅凭名称互换。

当前 QBS 并不试图实现上述全部类型。它严格支持 Q2_K、Q3_K、Q4_K、Q5_K、Q6_K、Q4_0、
Q5_0、Q8_0 weight 和 IQ4_NL 九种 profile，activation 配对为 Q8_K 或 Q8_0；其余类型必须
经 capability/format 检查回退。第 4 节给出这九种 profile 的 exact block ABI 和计算公式。

### 2.25 标准 RVV 的价值、开销与 QBS 的切入点

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

### 2.26 当前项目中的真实数据怎样放回这条链路

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

| Weight | Model | `K x N x M` | RVV/QBS matmul cycles | Matmul speedup | QBS/RVV measured AXI R bytes |
| --- | --- | --- | ---: | ---: | ---: |
| Q3_K | Qwen2.5-1.5B | `1536 x 256 x 1` | 920,462 / 17,614 | 52.26x | 24.6% |
| Q5_K | Qwen2.5-1.5B | `1536 x 256 x 1` | 1,354,132 / 21,750 | 62.26x | 36.6% |
| Q6_K | Qwen2.5-1.5B | `1536 x 256 x 1` | 1,361,692 / 25,120 | 54.21x | 43.6% |
| Q8_0 | Qwen2.5-0.5B | `896 x 256 x 1` | 163,513 / 26,923 | 6.07x | 110.2% |

这些数来自 `hardware/paper_results/b73af277_20260827/format_closure.csv`，两侧 source weight、
activation、golden 和 shape 严格配对，全部 PASS 且 mismatch 为 0；离线 R4 repack 不计入周期。
`AXI R bytes` 是计时区间内在读数据通道实测的 bus bytes，不是公式化 tensor footprint。Q3/5/6_K
同时减少了指令流和总线读取；Q8_0 的 32-element block 令 QBS 读量略高，仍通过消除软件
unpack/reduction 和循环控制获得 6.07x matmul 加速。这些数据**不是完整 Qwen token/s 加速比**：
表中只取一个量化线性算子切片，未包含前述 28 层其余算子、LM head、KV cache、sampling 和
软件运行时。

当前归档整模型功能闭环记录到 Q4_K `gemv/gemm=2720/5312`、Q6_K
`gemv/gemm=496/864`，合计执行 92,480 条原生 `qbexec`。这些是 GGML 进入新 backend 的运行期
调用证据，不是 RTL 周期数据。模型级数值结果和七种 profile 的 PPL/KL/Top-k 数据见第 13.9 节。

Attention 也使用真实模型数据验证。当前 AKV 路径使用 Qwen2.5 D128/GQA6 的 Decode Q/K/V
数据，以及 Qwen3 D128/GQA2 的 tiled Prefill 节点，检查 K/V 外部读取、token-axis view、RVV
点积、Softmax 和 PV 聚合是否按同一数值规则工作。QEMU 用于证明完整模型能够正确选择路径；RTL
叶子测试用于测量命令周期和微结构活动，两类结果不能互相替代。

到这里，模型侧的因果链已经完整：自然语言变为 token，token 经多层 Attention/FFN 变为
logits；量化 projection 在 GGML 中下沉为 `MUL_MAT`/`MUL_MAT_ID`，由 QBS 接管合法 microtile；
Attention core 下沉为 `FLASH_ATTN_EXT`，由 AKV 对合法 shape 提供 K/V context 和局部视图，算术
仍由 RVV 执行。第 3 节开始讨论这两类结构化语义如何在保留普通 RVV fallback 的前提下安全进入
硬件。

## 3. QBS/AKV 的核心设计原则

### 3.1 QBS 三层契约与 AKV 三层边界

QBS 把机制拆为三层，避免将模型名称、GGUF 位布局和硬件 datapath 绑死：

| 层次 | 描述内容 | 当前载体 |
| --- | --- | --- |
| Format/profile | block 字节数、元素数、subgroup、scale、correction、激活配对 | `config/qbs_abi.json` |
| Layout | 权重/激活如何按行、K block 和 M/N tile 排列 | descriptor + GGML repack |
| Shape/command | `M`、`N`、`K-blocks`、地址、目的寄存器和舍入模式 | `qbexec` + descriptor |

这种拆分带来两点通用性：

1. 同一硬件调度骨架可以接多个量化 profile，而不是每种 GGUF type 建一套独立 engine；
2. unsupported format、layout 或 shape 可以由软件在命令发出前回退，不影响普通 RVV 程序。

AKV 使用相同的“先声明再执行”原则，但三层内容不同：

| 层次 | 描述内容 | 当前载体 |
| --- | --- | --- |
| Data contract | Q/K/V 为 F16 payload，Query 来源可为上层 F32 后显式转换 | `config/akv_abi.json` + GGML adapter |
| Shape/feature | D、GQA/q_rows、KV length、batch、scale、mask、Attention feature | descriptor + selector preflight |
| Lifetime/view | FULL/REFILL/RELEASE、row/column/panel、tile start/count | AKV command + hidden context |

QBS profile 解释“压缩 weight bytes 代表什么数学量”；AKV descriptor 解释“哪些运行时 bytes 构成
本次有界 Attention context”。二者都不使用模型名称做硬件分支，也都要求不支持条件在 side effect
前完整回退。

### 3.2 计算状态命令局部，可复用数据状态显式跨命令

QBS 内部有 block buffer、整数 subtotal、FP update table 和 128 个 FP32 accumulator，但这些
状态只在一条 `qbexec` 生命周期内存在。命令成功后结果进入普通 VRF；命令失败则不提交。
软件不需要保存或恢复独立 tile register file，也不能跨命令观察内部 accumulator。

当前又有两类**显式、有限、跨命令的数据 context**：

- QBS activation context 保存一份带 ID/generation 的 M1/Q8_K snapshot，供后续 output N tiles
  以 REUSE/RELEASE 使用；
- AKV context 保存一个 Query group 和有界 K/V tile，供多条 row/column/panel local-view 命令
  使用，并由 REFILL/RELEASE 更新生命周期。

它们不是长期可编程矩阵寄存器：软件不能用普通 vector register 编号直接寻址 context SRAM，
也不能观察半填充内容；只有专用命令和 capability 定义的 view 可访问。与此同时，它们也不能
被称为“纯微结构 cache”，因为软件必须显式建立、匹配、替换和释放，context switch 时还需要
invalid 或未来的 save/restore 规则。

这与 Intel AMX 的八个 1 KiB architectural tile registers 不同，也与 RISC-V Attached Matrix
Extension 所设想的通用独立 matrix state 不同。更准确的说法是：QBS compute state 属于
command-local hidden state，QBS/AKV reusable context 属于**软件管理生命周期、硬件隐藏内容的
bounded accelerator state**，最终结果和消费操作仍收口到普通 RVV architectural state。

### 3.3 复用 RVV，而不是替代 RVV

QBS/AKV 与 RVV 的关系是：

- **ISA 共存**：普通 RVV 指令解码、lane、VLSU 和 sequencer 行为保留；扩展未启用时不选新路径。
- **软件共存**：同一 GGML operator 保留标准 RVV 实现；capability、shape 或算法不匹配即完整回退。
- **状态共存**：QBS FP32 output 和 AKV F16 view 都进入普通 vector registers，由标准 RVV 继续消费。
- **算术复用**：AKV 不增加 QK/Softmax/PV arithmetic，直接使用现有 vector ALU/MFPU/reduction。
- **系统复用**：两者复用虚拟地址翻译、PMA、AXI、异常报告、`vid` 完成和 VRF 写回域。
- **执行互斥**：当前 normal VLSU、QBS 与 AKV 同时只允许一个 owner；这保证请求归属清楚，也限制 overlap。

RTL 分别受 `ARA_QBS_ENABLE`、`ARA_AKV_ENABLE` 和 `ARA_AKV_V2_ENABLE` 编译开关控制；关闭时普通
RVV 数据通路仍按原设计工作。启用后 QBS 内部时钟只在 command valid/active 时打开，idle 的
block storage 和 FP scheduler 不持续翻转；AKV context 是否进一步使用 macro clock gating 需以
综合实例和 macro enable 为准，不能仅由“当前无命令”推断零动态功耗。

最后一点很重要。当前“合理并存”是**明确仲裁和架构兼容**，不是宣称两条访存路径同时工作。

### 3.4 控制、数据和完成三条路径

理解 QBS/AKV 时应把三条路径分开，再观察它们在命令边界处如何汇合：

```text
QBS 控制: GGML shape/profile -> descriptor/qbexec -> dispatcher -> sequencer vid -> QBS FSM
QBS 数据: weight/activation VA -> MMU/PMA/AXI -> block adapter -> integer/FP pipeline
QBS 完成: hidden accumulators -> atomic commit -> LDU result port -> lane VRF -> vid terminal

AKV 控制: FLASH_ATTN shape/feature -> descriptor/command -> dispatcher -> sequencer vid -> AKV FSM
AKV 数据: Q/K/V VA -> MMU/PMA/AXI -> hidden context -> row/column/panel view
AKV 完成: validated view -> LDU result port -> lane VRF -> RVV Attention -> vid terminal
```

- 控制路径决定“允许做什么”，包括 profile、layout、M/N/K 和目的寄存器组；
- 数据路径决定“实际读到什么”，包括翻译、burst、range tag、block 边界和格式解码；
- 完成路径决定“程序何时能看见结果”，包括 VRF grant、`fflags`、success 和 fault。

很多错误来自把三者混在一起。例如 descriptor 合法只证明控制路径接受了命令，不证明 payload
读取成功；FP accumulator 有结果也不意味着架构结果已经可见；AKV SRAM 已写入 bytes 也不表示
context 已 READY；local-load request 获得 early acknowledgement 也不表示 VRF replay 和 `vid`
已经完成。

### 3.5 当前实现必须保持的八条不变量

下面八条比具体状态名更接近 QBS/AKV 的设计骨架：

1. **先验证后读 payload**：非法 descriptor 不得触发 weight/activation 越界访问；
2. **单一资源所有者**：normal、QBS 与 AKV 不能同时驱动 MMU、AXI 或 result port；
3. **range 和 response 可归属**：每个返回 beat 必须能映射到已发出的 descriptor、activation 或
   weight/Q/K/V range，并满足 RRESP/RLAST；
4. **同一 accumulator 更新有序**：不同 block 对同一 FP32 partial sum 的更新不能任意重排；
5. **context 原子发布**：fill/refill 期间写入的 SRAM 不可读，全部 range 成功后才能 READY；
6. **fault 前结果不可见**：任何 payload fault 都只能丢弃 hidden compute/context state，不能留下
   部分 VRF 结果或半有效 context；
7. **local view 先验证后 replay**：selector、D、tile、destination 任一非法时，不能发第一个 lane
   result request；
8. **terminal 后才释放命令**：success/fault 被 sequencer 接收后，`vid`、VLSU 所有权和命令局部
   buffer 才能回收。

RTL assertion 和验证用例应围绕这些不变量组织。新增 prefetch、更多 outstanding、activation
quantizer、多 context 或 normal-load overlap 时，也必须逐条重新证明。

### 3.6 QBS 是否属于数据流架构

准确说，QBS 在一条命令内部使用**有界的压缩块流数据流**：block 到达后依次经过 decode、整数
点积、correction、FP update，结果驻留在命令局部 accumulator；调度由数据有效性和资源 ready
共同推进。但它不是 graph-level dataflow processor，也没有让多个 Transformer operator 以 token
形式在独立节点间自由流动。命令之间仍由标量软件和 sequencer 按程序顺序组织。

因此 QBS 的定位应是“带 command-local dataflow 的 RVV 协同执行路径”，而不是泛称为完整
数据流处理器。

AKV 更不应单独称为 Attention dataflow processor。它只把一个 K/V tile 的 residency 和 view
固定下来，tile 外层循环、causal schedule、online Softmax state 和 operator graph 仍由软件/RVV
控制。整个设计可以称为“framework semantics guided RVV specialization”，但不能据此声称已经
实现自主调度完整 Transformer graph 的数据流 NPU。

### 3.7 核心设计思想：传递结构化语义，而不是增加一个孤立乘法指令

QBS 的核心不是“把 RVV 的乘法器换成更宽的乘法器”，而是改变软硬件之间的工作划分。普通
RVV 只看到 load、mask、shift、widening multiply、reduction 和 scalar update 等逐条指令；
weight block 属于哪种格式、哪些 metadata 共同描述一个 subgroup、同一 activation 将被多少
output rows 复用，这些信息已经在 GGML kernel 中存在，却在进入硬件前被展开成了长指令流。

QBS 保留这些高层但仍具有通用边界的语义，并通过 profile、layout 和 shape 三层 contract 一次
交给硬件：

1. **Profile 描述数学**：block bytes、quant 位布局、scale/min correction 和 activation 配对
   决定每个 block 的严格数值含义；
2. **Layout 暴露数据邻接**：R4/M4/M8 使硬件知道哪些 weight/activation block 可作为一个连续 tile
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

这里的“profile”是硬件执行契约，不应直接充当某个框架的 tensor enum。软件接口在 profile 前增加
一层稳定的 64-bit canonical encoding ID：GGML、ONNX Runtime 或其他 adapter 先声明自己持有或
转换得到的精确 encoding，公共运行时再依据 `qbinfo` 将它绑定到当前设备的 4-bit profile ID。
encoding ID 不进入 descriptor 和指令，因此这种解耦不会增加硬件命令或执行周期。

### 3.8 两类后端可见语义为什么必须分开

QBS 与 AKV 都把软件已经知道、普通逐条 RVV 指令会丢失的结构化信息交给后端，但二者传递的
不是同一种信息：

| 机制 | 软件掌握的事实 | 硬件据此做什么 | 不应据此做什么 |
| --- | --- | --- | --- |
| QBS | weight profile、block layout、M/N/K tile、activation 生命周期 | 直接解释压缩 bytes，复用 block，并在隐藏 accumulator 中完成 tile | 猜测任意量化格式、固化模型 layer 名称 |
| QBS activation context | 多条 output-tile 命令消费同一个逻辑 activation | 用显式 ID/generation 保存并重放 Q8_K snapshot | 仅凭地址相同判断内容未变 |
| AKV | 多个 Q heads/Query tokens 将复用同一 K/V tile，且需要 row/column 两种视图 | 保存有界 K/V tile，以 token banking 生成局部 row/column/panel view | 替代 Softmax、改变 mask、把 Attention 结果近似化 |

QBS 适合静态权重主导的压缩矩阵计算；AKV 适合运行时 K/V 的生命周期和访问方向转换。它们共享
VLSU、MMU、AXI、VRF 和 sequencer，但不共享 numerical profile，也不把一方的 context 当作
另一方的数据。这样的分离使“增加一种 weight encoding”和“增加一种 Attention shape”具有不同
的验证边界，避免把所有 LLM 优化堆进一个难以版本化的超级命令。

### 3.9 “支持某个模型”必须拆成三个层次

同一个模型可以在处理器上正确运行，却完全不进入 QBS 或 AKV。为了避免含糊，本文统一使用：

1. **功能支持**：llama.cpp 能用普通标量/RVV fallback 完成模型；这主要取决于基础 ISA、内存容量、
   GGML kernel 和操作系统环境。
2. **QBS 加速支持**：模型中的某个 `MUL_MAT`/`MUL_MAT_ID` tensor 具有受支持的 encoding，并通过
   capability、dimension、shape、layout 和 dispatch 检查，运行期实际发出 `qbexec`。
3. **AKV 加速支持**：某个 `FLASH_ATTN_EXT` 节点满足 dtype、D、GQA、batch、stride、mask、scale
   和 Prefill/Decode 算法边界，运行期实际发出 AKV 命令。

模型名称不是任何一级 RTL 判断条件。换成新的 Qwen、Llama 或 MoE 模型时，若 operator contract
和 shape 已在能力范围内，硬件可以不变；若不满足，节点应完整回退，而不是部分执行后再补救。
因此“无需改硬件即可适配模型”表示**选择契约具有 shape/model portability**，不表示所有新模型
节点都获得加速，更不表示端到端加速比与旧模型相同。

## 4. 当前支持的量化 profile

### 4.1 Profile 总表

当前 QBS architecture v3 / descriptor v2 / numerical contract v1 支持九组严格的权重/激活配对：

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
ABI 生成物、参考模型、RTL decoder、QEMU、至少一个实际运行时 adapter 和验证向量。

软件 encoding ID 与表中的 profile ID 有不同职责：前者跨运行时稳定地标识完整 byte/numerical
contract，后者只是在当前硬件 ABI 中压缩到 4 bit 的 selector。`qbs_device_bind_encodings()` 负责
严格的一一映射并同时检查 weight/activation 配对和设备能力。当前三个简单 block profile 还提供
精确的框架无关别名：

| Canonical alias | 对应 profile | 别名严格包含的语义 |
| --- | --- | --- |
| `S4_B32_F16_SPLIT_NIBBLE_OFFSET8` | Q4_0 | 32 元素、FP16 scale、前后半区分置于低/高 nibble、解码减 8 |
| `S5_B32_F16_NIBBLE_HIGHBIT_OFFSET16` | Q5_0 | 32 元素、FP16 scale、低 4-bit nibble 加独立高位平面、解码减 16 |
| `S8_B32_F16_TWOS_COMPLEMENT` | Q8_0 weight/activation | 32 个 signed int8 和一个 FP16 block scale |
| `S8_B256_F32_BSUM16_I16` | Q8_K activation | 256 个 signed int8、FP32 scale 和 16 个 int16 block sums |

这些名称使其他软件生态无需借用 `GGML_TYPE_*` 名字，但绝不表示任意 group-32 INT4 都能直接映射。
K-quant 和 IQ4_NL 的 packed scale/min/codebook 仍具有明确的 GGML/GGUF 契约，因此保留专用 encoding 名称。
外部格式若不同，只能由 adapter 在加载期显式转换并验证，或继续使用普通 RVV fallback。

#### 4.1.1 一个量化 block 在内存中究竟放了什么

上面总表中的 `Bytes/block` 不是只有容量意义。QBS profile decoder 按固定 byte offset 解释每一个
字段，因此两个格式即使都是“4 bit 权重”，只要 nibble 排列、scale 类型或 subgroup 规则不同，
就不能共用同一个 profile。当前九种权重 block 的原生 little-endian 字节组成如下。十六进制
offset 均相对于单个 block 起始地址：

| Profile | 原生 block 字节布局（按地址递增） | 总字节 | 每块元素 |
| --- | --- | ---: | ---: |
| Q2_K | `0x00: scales[16]`，`0x10: qs[64]`，`0x50: d(FP16)`，`0x52: dmin(FP16)` | 84 | 256 |
| Q3_K | `0x00: hmask[32]`，`0x20: qs[64]`，`0x60: scales[12]`，`0x6c: d(FP16)` | 110 | 256 |
| Q4_K | `0x00: d(FP16)`，`0x02: dmin(FP16)`，`0x04: scales[12]`，`0x10: qs[128]` | 144 | 256 |
| Q5_K | `0x00: d(FP16)`，`0x02: dmin(FP16)`，`0x04: scales[12]`，`0x10: qh[32]`，`0x30: qs[128]` | 176 | 256 |
| Q6_K | `0x00: ql[128]`，`0x80: qh[64]`，`0xc0: scales[16]`，`0xd0: d(FP16)` | 210 | 256 |
| Q4_0 | `0x00: d(FP16)`，`0x02: qs[16]` | 18 | 32 |
| Q5_0 | `0x00: d(FP16)`，`0x02: qh[4]`，`0x06: qs[16]` | 22 | 32 |
| Q8_0 weight | `0x00: d(FP16)`，`0x02: qs[32]` | 34 | 32 |
| IQ4_NL | `0x00: d(FP16)`，`0x02: qs[16]` | 18 | 32 |

这些字段可先用下面的直观含义理解：

- `qs` 是主要的低比特或 int8 payload；一个 byte 可能保存两个 4-bit 值，也可能保存多个低位平面，
  具体拆法由 profile 决定；
- `qh` 或 `hmask` 保存 `qs` 容纳不下的高位。它们必须与 `qs` 按该格式的 bit mapping 合并，不能
  简单地当成另一组独立权重；
- `scales` 保存 subgroup scale，某些 K-quant 还在同一 packed metadata 中保存 subgroup minimum。
  `scales[12]` 因而不表示“只有 12 个 subgroup”，也不表示每个 byte 就是一个可直接相乘的 scale；
- `d` 是 block 或 super-block 的主尺度；`dmin` 是 affine-min profile 的 minimum 尺度；
- IQ4_NL 的 nibble 不是有符号 INT4，而是 16-entry 固定码本的索引。

两种 activation block 的原生布局为：

| Activation | 原生 block 字节布局（按地址递增） | 总字节 | 每块元素 |
| --- | --- | ---: | ---: |
| Q8_K | `0x000: d(FP32)`，`0x004: qs[256]`，`0x104: bsums[16](int16)` | 292 | 256 |
| Q8_0 | `0x00: d(FP16)`，`0x02: qs[32](int8)` | 34 | 32 |

Q8_K 的 `bsums[g]` 是第 `g` 个 16-element activation subgroup 的 int8 和。它不参与普通 scale-only
profile 的结果，但 affine-min profile 可直接用它计算 minimum correction，省去第二次遍历
activation。这里的 `d`、`qs` 和 `bsums` 都属于同一个 block，不能只复制 260 B 的 scale/payload
而丢掉末尾 32 B auxiliary data。

还要区分**原生 block 格式**与**多行重排格式**：

```text
ROW_MAJOR weight:
    [row0 block0][row0 block1] ... [row1 block0][row1 block1] ...

R4_BLOCK_MAJOR weight:
    [row0 block0][row1 block0][row2 block0][row3 block0]
    [row0 block1][row1 block1][row2 block1][row3 block1] ...

M4_INTERLEAVED activation（对同一个 K block）：
    [4 个 row scale]
    [quant byte0 of row0..row3][quant byte1 of row0..row3] ...
    [aux item0 of row0..row3][aux item1 of row0..row3] ...
```

R4 仅改变完整 weight block 的先后顺序，表中的块内 offset 不变；末尾不足四行时补零到四行物理组，
但 logical `N` 不变。M4 则确实改变四个 activation block 之间的 byte 排列：先放四行 scale，再按
byte 交织 quant，最后按项交织 auxiliary data。`qbs_block_adapter.sv` 必须根据 descriptor 中的
layout 选择对应 steering，不能拿原生 row-major offset 直接解释 M4 字节流。这也是 layout ID 属于
ABI，而不是一个纯软件性能提示的原因。

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

### 4.3 当前数值顺序与比较边界

`numerical_contract_version=1` 固定使用 round-to-nearest-even（RNE），不读取动态 `frm`；对
affine profile 使用“正 dot 更新在前、min correction 在后”的两次 FP32 FMA。该固定舍入模式和
操作顺序均由 `config/qbs_abi.json` 定义，并生成 C/SV 常量；`qbs_ref.c`、RTL FP accumulator 和
QEMU canonical model 以此为准。

这里的“两次 FMA”也是普通 RVV 与 QBS 公平比较的一部分。当前专用 Q4_K RVV GEMV/GEMM 使用
标准 `vfnmsac` 完成负的 min correction，使 RVV 与 QBS 都按“正 dot 更新在前、min correction
在后”的两次 FMA 顺序执行。不能把第二项拆成先乘后减：虽然实数公式相同，单独乘法会多产生
一次 FP32 舍入，长模型中一 ULP 级差异也可能逐层传播。

AKV 也必须遵循实际执行路径的运算次序。其 native RVV Attention 先计算 `score*scale`，再加
mask；功能模型若被编译器收缩成一次 FMA，就会制造并非硬件机制导致的差异。因此当前功能模型
显式保持两步运算。逐节点 digest 只在诊断模式开启，并在节点完成后同步读取输出；它可定位首个
分歧，但其同步开销不能进入性能测量。

不同 profile 的 llama.cpp/RVV 累加组织并不完全相同，例如 Q5_K 可能分别累计 correction 和
positive contribution。因此，硬件不能按某一个软件 kernel 的临时循环结构交换全局更新顺序，
也不能假定所有格式都与各自 fallback bit-identical。任何数值顺序变更都必须提升 numerical
contract version，并同步参考模型、RTL、QEMU、GGML 能力检查和整模型质量验证。

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

## 5. 从标准 RVV 到专用命令：QBS/AKV ISA 与 ABI

这一节先回答“原来的程序在做什么”，再解释 QBS 如何表达同一个计算。两条路径的数学目标
相同。对一个量化线性层，记：

```text
W: [N_total, K]   静态量化权重
A: [M_total, K]   运行时 activation，由 F32 量化为 Q8_K 或 Q8_0
C: [M_total, N_total]

C[m,n] = dot(A[m,:], W[n,:])，并按量化 profile 执行 scale/min correction
```

注意 QBS descriptor 中的 `N` 是**一条命令计算的输出行数**，不是 llama.cpp 所有上层函数中
都使用的同名参数。本文为避免混淆，把完整维度写成 `M_total/N_total/K`，把单条命令的 tile
写成 `M/N/K-blocks`。

### 5.1 原始标准 RVV 程序是什么样的

“原 RVV 程序”不是唯一一个固定函数。GGML 会根据量化格式、VLEN、Decode/Prefill shape 和 repack
能力，选择单输出 `vec_dot`、多输出 GEMV 或多 activation GEMM kernel。当前代码中最容易理解的
代表是 `ggml_vec_dot_q4_K_q8_K_vl1024()`；当 repack 条件满足时，更高层还可调用一次处理多行的
`ggml_gemm_q4_K_32x1_q8_K_generic()` 等 kernel。它们的共同点是：量化格式语义已被展开为普通标量
和 RVV 指令。

以 `Q4_K x Q8_K` 的单个输出为例，等价的软件结构是：

```c
float sum = 0.0f;
for (unsigned b = 0; b < K / 256; ++b) {
    q4_block w = load_q4_k_block(weight_row, b);  // d, dmin, scales, qs
    q8_block a = load_q8_k_block(activation, b);  // d, qs, bsums

    decode_6bit_scales_and_mins(w.scales, scales, mins);

    int32_t dot = 0;
    int32_t min_correction = 0;
    for (unsigned g = 0; g < 8; ++g) {
        int8_vector q4 = unpack_low_or_high_nibbles(w.qs, g);
        int8_vector q8 = load_activation_group(a.qs, g);
        dot += scales[g] * reduce_sum(widen_mul(q4, q8));
        min_correction += mins[g] * activation_group_sum(a.bsums, g);
    }

    sum += (fp16_to_fp32(w.d)    * a.d) * dot;
    sum -= (fp16_to_fp32(w.dmin) * a.d) * min_correction;
}
output = sum;
```

当 `VLEN=1024` 时，当前 Q4_K 专用实现已经做了合理的 RVV 优化：用 32 个 i32 lane 保留中间和，
用 `vle8` 读取 payload，用 `vand/vsrl` 拆分低、高 nibble，用 `vwmul/vwmacc` 做 widening 乘累加，
并将原来多次的小归约收紧为最终 i32 reduction。因此本项目的 RVV baseline 不是纯标量或未优化
参照。即便如此，它仍必须为每个 block/输出 tile 显式执行：

1. 装载量化 payload 和 metadata；
2. 用 mask/shift/merge 恢复低比特数值和 subgroup scale/min；
3. 发出 widening integer multiply-accumulate；
4. 用 reduction 把 vector partial sum 收缩到标量或短向量；
5. 执行 int-to-FP、scale multiplication、min correction 和 FP accumulation；
6. 由标量循环维护 block、output row、activation row 和地址。

对 repacked GEMV/GEMM，多行数据已经被软件重排，且 activation 可在软件 tile 内复用；但上述
unpack、correction、reduction 和控制仍是可退休的普通指令流。这正是 QBS 试图消除的部分，而不是
重复声称“RVV 未向量化”。

### 5.2 QBS 程序是什么样的

QBS 不修改 GGML graph 中 `MUL_MAT` 的数学语义，也不删除 F32 activation 的动态量化。它改变的是
量化后的矩阵内核：模型加载时一次性将权重转换为 R4 block-major，运行时把 activation 分成
Q8_K/Q8_0 blocks。公共 planner 的默认几何是 `M<=4, N<=32, K-blocks<=256`；当上层显式
启用 wide-M，且 capability、layout、shape 与精确 byte-cost 阈值都通过时，还可将部分 Prefill
切成 `M=5..8, N<=16`。两种几何都受 128 个 FP32 result slots 约束：`4*32=8*16=128`。

当前软件被分成“运行时适配器”和“QBS 公共层”。GGML 适配器只解释 tensor type、生命周期、
allocator、trace 和 fallback；profile 元数据、能力解析、R4/M4/M8 packing、M/N/K 分块、descriptor
构造和原生指令 wrapper 属于不依赖 GGML 的公共层。调用关系可概括为：

```c
binding = ggml_type_to_exact_qbs_profile(tensor.type);
device  = qbs_device_query(qbinfo_reader);
if (!runtime_enabled || !binding.exact ||
    !ggml_tensor_shape_supported(tensor) ||
    !qbs_device_supports_profile(device, binding))
    return best_standard_rvv_kernel(...);

// 模型加载期：只做一次
weights_r4 = qbs_repack_weight_r4(binding.weight_profile,
                                  weights_native);

// MUL_MAT 运行期
activations_q8 = quantize_f32_rows(activations_f32);
problem = {binding, weight_layout, activation_storage,
           M_total, N_total, K};
plan = qbs_plan_create(device, problem);

// 公共层完成默认 M1-M4/可选 M5-M8、N tile、tail、split-K 和 descriptor 构造；
// GGML callback 只负责原生 qbexec 或功能 emulation，以及 trace。
qbs_execute(plan,
            weights_r4, weights_bytes,
            activations_q8, activations_bytes,
            C, output_capacity, output_stride,
            workspace, workspace_bytes,
            ggml_command_executor);
```

实际 wrapper 在指令前用 `fence rw,rw` 确保 descriptor、activation 和 repacked weight 对 QBS 可见；按 M
设置 e32/m1、m2 或 m4 向量状态；发出 raw `.word`；命令返回后把 `vl` 改成 logical N，用普通
`vse32.v` 存回结果。例如 M=4 的实际核心序列是：

```asm
fence    rw, rw
li       t0, 128
vsetvli  zero, t0, e32, m4, ta, ma
.word    0x06b5045b       # qbexec v8, a0, a1, M=4
mv       t0, n
vsetvli  zero, t0, e32, m1, ta, ma
vse32.v  v8,  (out0)
vse32.v  v9,  (out1)
vse32.v  v10, (out2)
vse32.v  v11, (out3)
```

这里 `a0` 指向 descriptor，`a1` 指向 activation tile；输出地址不是 `qbexec` 的参数，而是后续
`vse32.v` 的参数。当 K 大于命令上限时，软件按 K 分段发出多条命令，再用 FP32 加法合并
partial outputs；这是当前执行方案的一部分，不是隐含在单条指令中的无限 K。

对照源码时，可按下表跟踪：

| 层次 | 当前源码 | 主要职责 |
| --- | --- | --- |
| 标准 RVV 块点积 | 本地 llama.cpp fork 的 `ggml/src/ggml-cpu/arch/riscv/quants.c` | 按 VLEN 选择 Q3/Q4/Q6 等 RVV decode/dot/reduction 实现 |
| 标准 repacked GEMV/GEMM | 本地 llama.cpp fork 的 `ggml/src/ggml-cpu/repack.cpp` | 选择多行 trait、重排权重/激活并调用 GEMV/GEMM kernel |
| QBS 公共运行时 API | `software/qbs/include/qbs/qbs.h` | 与 framework 无关的 encoding binding、profile、capability、problem/plan、buffer 和 executor 契约 |
| QBS 公共运行时实现 | `software/qbs/src/qbs_runtime.c`、`qbs_native_riscv.c` | capability 核验、R4/M4/M8 packing、M/N/K 分块、tail/split-K、流量建议、descriptor、容量预检和原生 wrapper |
| QBS GGML 适配器 | 本地 llama.cpp fork 的 `ggml/src/ggml-cpu/arch/riscv/qbs.cpp` | `ggml_type` 映射、tensor 选择、activation 规划/packing、GGML trace/emulation、fallback 和公共 executor 回调 |
| QBS ABI 真源 | `config/qbs_abi.json` | canonical encoding、profile、layout、instruction 和 shape 的版本化定义 |
| 生成的软件 ABI | `apps/common/qbs_abi.h`、`software/qbs/include/qbs/qbs_abi.h` | 同源 encoding ID、C 宏、descriptor pack/unpack、capability word 和 raw instruction encoding |
| 生成的 RTL ABI | `hardware/include/qbs_pkg.sv` | 与 C 侧同源的 SystemVerilog 常量、enum 和 capability 函数 |

### 5.3 为什么参数分成指令、descriptor 和 profile

QBS 没有把整个程序的信息全部塞进 32-bit 指令。参数被有意分成三类：

| 载体 | 参数 | 为什么放在这里 |
| --- | --- | --- |
| `qbexec` 指令 | descriptor pointer、activation pointer、`vd`、`M` | sequencer 在读 descriptor 之前就必须知道 GPR 依赖、目的 VRF 组和要预留的寄存器数 |
| 16 B descriptor | weight pointer、profile/layout IDs、`N`、`K-blocks` | 比指令位宽更充足；每条命令拷贝一次，不形成跨指令隐藏配置 |
| profile capability table | block bytes/elements、scale、subgroup、correction 语义 | 同一 profile ID 只有一套严格数学和 byte mapping，避免软件逐条传递大量固定字段 |

如果 `M` 也只放在 descriptor 中，sequencer 就必须在目的相关性检查前先发起内存读取，这会破坏正常指令
解码与 hazard 预留边界。反过来，如果把 profile 全部展开到 instruction bits，32-bit 编码无法容纳，也会
让每种 GGUF 格式变成新 opcode。当前分层既保留了硬件可见依赖，又保留了 profile 扩展性。
软件 canonical encoding ID 仅在模型加载/dispatch 时用于绑定 profile，不随每条 `qbexec` 传输。

### 5.4 `qbexec` 指令的逐位编码

`qbexec` 使用 R-type 形状的 custom-2 编码，但 `rd` 字段在 Ara 中解释为 vector destination `vd`：

```text
31        28 27       25 24      20 19      15 14   12 11       7 6          0
+------------+-----------+----------+----------+-------+-----------+------------+
|reserved=0000|   M-1     |   rs2    |   rs1    |  000  |    vd     | 1011011    |
+------------+-----------+----------+----------+-------+-----------+------------+
 funct7[6:3]   funct7[2:0]                    funct3             custom-2
```

| Bits | 参数 | 严格含义 |
| --- | --- | --- |
| 6:0 | opcode=`0x5b` | RISC-V custom-2 major opcode；不是标准 RVV `OP-V` 指令 |
| 11:7 | `vd` | FP32 结果向量寄存器组起点；虽占用 R-type `rd` 位置，但不写标量 GPR |
| 14:12 | funct3=`000` | 选择 `qbexec`；`001` 属于 `qbinfo` |
| 19:15 | `rs1` | 包含 16 B descriptor **虚拟地址**的标量寄存器；地址必须 16 B 对齐 |
| 24:20 | `rs2` | 包含 activation tile **虚拟地址**的标量寄存器；地址必须 4 B 对齐 |
| 27:25 | `M-1` | activation/input row 数减 1；可表达 M=1..8，当前默认路径使用 M1--M4，wide-M 路径使用 M5--M8 |
| 31:28 | reserved | architecture v3 必须全为 0；非零产生 illegal instruction |

`M` 同时决定目的寄存器预留：

| M | `M-1` | 预留组 | `vd` 约束 | 架构结果 |
| ---: | --- | ---: | --- | --- |
| 1 | `000` | 1 register | 任意不越界 `vd` | `vd[0:N-1]` 有效，其余 FP32 元素清零 |
| 2 | `001` | 2 registers | `vd` 必须为 2 的倍数 | `vd` 和 `vd+1` 分别对应两个 activation rows |
| 3 | `010` | 4 registers | `vd` 必须为 4 的倍数 | 只修改 `vd..vd+2`；`vd+3` 保持原值 |
| 4 | `011` | 4 registers | `vd` 必须为 4 的倍数 | `vd..vd+3` 分别对应四个 activation rows |
| 5 | `100` | 8 registers | `vd` 必须为 8 的倍数 | 修改 `vd..vd+4` 的 logical N 元素；非活动寄存器和 tail bytes 保持原值 |
| 6 | `101` | 8 registers | `vd` 必须为 8 的倍数 | 修改 `vd..vd+5` 的 logical N 元素；其余保持原值 |
| 7 | `110` | 8 registers | `vd` 必须为 8 的倍数 | 修改 `vd..vd+6` 的 logical N 元素；其余保持原值 |
| 8 | `111` | 8 registers | `vd` 必须为 8 的倍数 | `vd..vd+7` 分别对应八个 activation rows，每行最多 N=16 |

当前 wrapper 固定 `vd=v8`、`rs1=a0`、`rs2=a1`，因而实际使用的八种裸编码为：

| M | 概念助记符 | Raw word |
| ---: | --- | --- |
| 1 | `qbexec v8, a0, a1, 1` | `0x00b5045b` |
| 2 | `qbexec v8, a0, a1, 2` | `0x02b5045b` |
| 3 | `qbexec v8, a0, a1, 3` | `0x04b5045b` |
| 4 | `qbexec v8, a0, a1, 4` | `0x06b5045b` |
| 5 | `qbexec v8, a0, a1, 5` | `0x08b5045b` |
| 6 | `qbexec v8, a0, a1, 6` | `0x0ab5045b` |
| 7 | `qbexec v8, a0, a1, 7` | `0x0cb5045b` |
| 8 | `qbexec v8, a0, a1, 8` | `0x0eb5045b` |

概念助记符用于说明语义；当前工具链仍由 `.word` 发出。指令中**没有** weight 地址、profile、
layout、N、K、输出内存地址、mask 或累加源寄存器；这些要么在 descriptor/profile 中，要么由后续普通
RVV store 表达。

`qbexec` 还使用以下隐式 architectural context，它们不是 encoding 字段：

- `mstatus.VS` 和 `mstatus.FS` 都必须非 Off；前者允许访问向量状态，后者对应命令内的
  FP32 update 和 `fflags`；
- `vstart` 必须为 0；当前命令不支持元素级 restart；
- CVA6 accelerator-consistent mode 必须开启，否则指令非法；
- dispatcher 将请求内部固定为 e32，并从 M 合成 LMUL 和 `vl=M*(VLEN/32)`；
- 软件仍在 wrapper 中设置相容的 e32 向量状态，命令后再设 `vl=N` 存回；
- QBS numerical contract v1 的 FP rounding mode 固定为 RNE，不继承动态 `frm`；命令累计的 `fflags` 仅在成功
  terminal 返回；
- 命令被 CVA6 归类为阻塞式 accelerator load，从发出到成功提交或 fault terminal 之间
  不向标量核报告完成。

### 5.5 Descriptor v2 的每个参数

descriptor 是 little-endian、固定 16 B、16 B 对齐的不可变命令描述：

```c
struct qbs_descriptor {
    uint64_t header;       // offset 0x00
    uint64_t weight_base;  // offset 0x08
};
```

header 位域和实际语义如下：

| Bits | 字段 | 编码与含义 |
| --- | --- | --- |
| 3:0 | `descriptor_version` | 必须为 2；用于拒绝与当前字段定义不匹配的实现 |
| 7:4 | `weight_profile` | 权重块的严格数学/byte-layout ID；当前 ID 见第 4.1 节 |
| 11:8 | `activation_profile` | activation block ID；Q2/3/4/5/6_K 配 Q8_K，Q4_0/Q5_0/Q8_0/IQ4_NL 配 Q8_0 |
| 15:12 | `weight_layout` | 1=`ROW_MAJOR`，2=`R4_BLOCK_MAJOR` |
| 19:16 | `activation_layout` | 1=`ROW_MAJOR`；2=`M4_INTERLEAVED`（只允许 M=4）；3=`M8_INTERLEAVED`（只允许 M=5..8） |
| 24:20 | `N-1` | 命令中的 logical output rows 减 1，因而可表达 1..32 |
| 32:25 | `K-blocks-1` | reduction 维的 native blocks 数减 1，因而可表达 1..256 |
| 34:33 | `activation_access` | 0=`DIRECT`，1=`FILL`，2=`REUSE`，3=`RELEASE` |
| 38:35 | `context_id` | 显式 activation context ID；当前仅允许 0 |
| 46:39 | `context_generation` | 调用者分配的 8-bit generation；不得按地址推断 |
| 63:47 | reserved | 当前 descriptor contract 必须为 0 |
| 127:64 | `weight_base` | 当前命令权重 tile 的虚拟基地址，至少 2 B 对齐 |

`K-blocks` 的实际元素数由 profile 决定：

```text
K_elements = K_blocks * weight_profile.block_elements
```

因此 Q4_K/Q6_K 等 256-element profile 的单命令 K 上限为 65,536 元素；Q4_0/Q5_0/Q8_0/IQ4_NL
等 32-element profile 的上限为 8,192 元素。这是当前 ABI/RTL 上限，不表示软件必须发出这么
长的命令。

硬件不从 descriptor 显式读 stride，而是由 profile、layout、M/N/K-blocks 推导存储范围：

```text
ROW_MAJOR weight bytes = N * K_blocks * weight_block_bytes
R4 weight bytes        = ceil(N/4) * 4 * K_blocks * weight_block_bytes

ROW_MAJOR activation bytes = M * K_blocks * activation_block_bytes
M4 activation bytes        = 4 * K_blocks * activation_block_bytes
M8 activation bytes        = 8 * K_blocks * activation_block_bytes
```

R4 的 padding row 只为了保证四行物理连续。硬件仍以 logical N 控制 accumulator 和 commit，不会把 padding
行变成额外输出。descriptor 与其指向的 weight/activation 在命令完成前必须保持不变；硬件在起始
时读取 descriptor 一次，不在运行中反复解析软件结构。

### 5.6 `qbinfo` 指令和 capability 参数

`qbinfo` 与 `qbexec` 共用 opcode `0x5b`，但 funct3=`001`：

```text
31                    25 24      20 19      15 14   12 11       7 6       0
+-----------------------+----------+----------+-------+-----------+---------+
|      funct7=0000000    | rs2=x0   | index rs1|  001  | scalar rd | 0x5b    |
+-----------------------+----------+----------+-------+-----------+---------+
```

| 参数 | 含义 |
| --- | --- |
| `rs1` | 运行时 capability selector；它是 GPR 中的值，不是指令 immediate |
| `rd` | 返回 XLEN=64 的 capability word 的标量 GPR |
| `rs2` | 当前 contract 要求为 `x0` |
| funct7 | 当前 contract 要求为 0 |

当前 wrapper 使用 `a0` 同时作为 selector 和结果，即 `.word 0x0005155b`。`qbinfo` 不进入长时延
sequencer，dispatcher 组合查表后返回标量结果。未知 selector 返回 0。
`qbinfo` 仍由 accelerator/vector decode 路径识别，因此当前实现要求 `mstatus.VS`
非 Off；它不执行浮点计算，不像 `qbexec` 那样额外要求 `mstatus.FS` 非 Off。

#### 5.6.1 Selector `0x00`：基本版本、shape 和执行属性

| Bits | 含义 | 当前值 |
| --- | --- | ---: |
| 7:0 | QBS architecture version | 3 |
| 15:8 | descriptor version | 2 |
| 23:16 | descriptor bytes | 16 |
| 26:24 | `max_M-1` | 7，即 max M=8 |
| 31:27 | `max_N-1` | `min(31, VLEN/32-1)`；VLEN=1024 时为 31 |
| 39:32 | `max_K_blocks-1` | 255，即 256 blocks |
| 43:40 | numerical-contract version | 1 |
| 44 | blocking completion | 1；指令到 terminal 前不返回 |
| 45 | fault-atomic destination | 1；任何可能 fault 的读取完成前不启动 VRF commit |
| 46 | requires `vstart==0` | 1 |
| 47 | idempotent normal-memory only | 1；不允许将 block stream 投向非幂等 MMIO |
| 48 | requires accelerator consistency | 1 |
| 55:49 | reserved | 0 |
| 63:56 | `max_results-1` | 127，即单命令最多形成 128 个 FP32 结果 |

公共 QBS runtime 检查 version、descriptor bytes、numerical contract、M/N/K/result 上限和 bits 44..48，
再通过 layout/profile selector 核验其余能力；GGML 和后续其他运行时共用这一解析，不各自复制
位域逻辑。Bits 44..48 是当前 contract 已广告的执行属性；不能把某个位为 1 单独解释成完整系统
证明，具体 fault/order 仍由第 10 和 13 节的 RTL 规则与验证支撑。

#### 5.6.2 Selector `0x01`：layout、对齐与输出粒度

| Bits | 含义 | 当前值 |
| --- | --- | --- |
| 15:0 | weight-layout bitmap | bit 1=`ROW_MAJOR`，bit 2=`R4_BLOCK_MAJOR` |
| 31:16 | activation-layout bitmap | bit 1=`ROW_MAJOR`，bit 2=`M4_INTERLEAVED`，bit 3=`M8_INTERLEAVED` |
| 39:32 | descriptor alignment log2 | 4，即 16 B |
| 47:40 | weight-base alignment log2 | 1，即 2 B |
| 55:48 | activation-base alignment log2 | 2，即 4 B |
| 63:56 | output element bits | 32，即 FP32 |

bitmap 中的 bit 位等于 layout ID，因此值 1 不是“第一个 bit”的序号，而是 `1ULL << 1`。软件
必须检查目标 layout 对应位，不能只判断整个 word 非零。

硬件 capability word 报告 `max_M=8` 和 `M8_INTERLEAVED` 位，且公共 runtime、原生 wrapper
与 GGML adapter 都能生成 M5--M8 命令。但 GGML 默认仍只发 M1--M4；只有显式设置
`GGML_RISCV_QBS_WIDE_M=1`，且精确 byte-cost 模型判断 M8 存储至少节省 15% 输入流量时，
才对合法 Prefill 运算使用 M5--M8/N16。这是已实现但非默认的策略，不是只在位域中
预留的未实现能力。

#### 5.6.3 Selector `0x10 + weight_profile`：格式配对

返回可与该 weight profile 配对的 activation-profile bitmap。例如：

```text
qbinfo(0x11)  # weight profile 1 = Q4_K
              # 返回 bit 1，表示可配 Q8_K(ID=1)

qbinfo(0x13)  # weight profile 3 = Q4_0
              # 返回 bit 2，表示可配 Q8_0(ID=2)
```

weight profile ID 不是按格式名字顺序连续分配；软件必须使用 ABI 宏，不能从名称猜数字。

#### 5.6.4 Selector `0x20 + weight_profile`：权重块详细属性

| Bits | 含义 |
| --- | --- |
| 15:0 | native weight block bytes |
| 31:16 | 每块对应的 K elements |
| 39:32 | subgroup count |
| 47:40 | subgroup elements |
| 55:48 | scale format：0=invalid，1=FP16，2=FP32 |
| 63:56 | correction mode：0=none，1=affine-min |

例如 `qbinfo(0x21)` 查询 Q4_K，返回 `144 B / 256 elements / 8 groups / 32 elements per group /
FP16 scale / affine-min`。该 word 描述严格格式属性，不是当前周期数或动态性能参数。

#### 5.6.5 Selector `0x30 + activation_profile`：activation 块属性

| Bits | 含义 |
| --- | --- |
| 15:0 | activation block bytes |
| 31:16 | 每块 K elements |
| 39:32 | auxiliary element count；Q8_K 中即 16 个 `bsums` |
| 47:40 | scale bytes |
| 55:48 | 每个 auxiliary element bytes |
| 63:56 | scale format：1=FP16，2=FP32 |

`qbinfo(0x31)` 对应 Q8_K：292 B、256 elements、16 个 2-byte `bsums`、4-byte FP32 scale。
`qbinfo(0x32)` 对应 Q8_0：34 B、32 elements、无 aux、2-byte FP16 scale。

### 5.7 一个完整参数展开例子

考虑当前严格配对性能点 `Q4_K x Q8_K, K=1536, N_total=256, M_total=1`：

1. Q4_K 每块 256 个 K elements，因此 `K_blocks=1536/256=6`；
2. VLEN=1024 且 ABI max N=32，因此 256 个 outputs 分成 8 个 N=32 tiles；
3. M=1，每条命令只使用 `v8`；
4. weight profile=Q4_K(ID 1)，activation profile=Q8_K(ID 1)；
5. weight layout=R4(ID 2)，activation layout=row-major(ID 1)；
6. 每个 tile 的 descriptor header 为 `0x000000000bf12111`；
7. 每个 descriptor 的 `weight_base` 指向对应 32 行 R4 tile；`rs2` 指向同一个 6-block Q8_K activation；
8. 软件循环发出 8 次 `.word 0x00b5045b`，每次存回 32 个 FP32 results。

对每条命令，descriptor 推导的逻辑 payload 为：

```text
weight     = 32 * 6 * 144 = 27,648 B
activation =  1 * 6 * 292 =  1,752 B
output     = 32 * 4       =    128 B   # 通过后续 vse32.v 存储
```

这个例子展示了各参数的责任边界：`M` 告诉 sequencer 预留几个目的寄存器，`N`
告诉命令每个 activation row 生成多少 outputs，`K_blocks` 告诉硬件对每个 output 累加多少块，profile
告诉 decoder 如何解释 bytes，layout 告诉 read scheduler 如何计算地址。没有任何参数直接写
“Attention-Q”或“Qwen2.5”，所以同一命令可用于任何满足 profile/layout/shape 契约的量化线性层。

### 5.8 合法性、异常与软件回退

dispatcher 在 descriptor 访存之前检查 encoding reserved bits、`vd` 对齐/越界、`vstart`、
accelerator-consistent mode、descriptor/activation 地址对齐，并等待更旧 Ara work 排空。descriptor decoder
在发出 payload 访问前继续检查：

- descriptor version 和 reserved bits；
- profile 是否存在、weight/activation 是否兼容；
- layout 是否支持，M4-interleaved 是否与 M=4 配对，M8-interleaved 是否仅用于 M=5..8；
- `M/N/K-blocks` 范围；
- `vd` 对目标寄存器组的对齐；
- weight base 的 2 B 对齐、activation base 的 4 B 对齐；
- 由 block bytes、padded rows 和 K-blocks 推导的末地址是否 64-bit 溢出。

GGML 只在用户显式启用 QBS，且公共 runtime 的 `qbinfo`、profile、layout、shape 和 buffer 检查，
以及 GGML 自己的 dimension/repack 检查全部满足时选择 QBS trait。不支持的 tensor 继续调用当前
最优标准 RVV kernel；不会用静默格式转换、越界 padding 或错误 profile 扩大覆盖率。公共层还要求
调用者传入 weight、activation 和 output 的真实容量，并在第一条命令投放前完成检查。一旦命令已经
投放，memory/architectural fault 必须作为执行错误上报，不能静默重跑同一操作。因此 QBS 是普通
RVV 之上的可查询加速路径，不是替代 RVV 的唯一执行模式。

### 5.9 AKV 指令族：管理数据视图，而不是执行 Attention 公式

QBS 使用 `custom-2` opcode `0x5b` 的 `funct3=0/1`；AKV 在同一个 major opcode 下使用互不重叠的
function class。所有 AKV 命令都采用同一 R-type 形状：

```text
31                    25 24      20 19      15 14   12 11       7 6          0
+-----------------------+----------+----------+-------+-----------+------------+
|        funct7          |   rs2    |   rs1    |funct3 |   rd/vd   | 1011011    |
+-----------------------+----------+----------+-------+-----------+------------+
```

这只是借用 R-type 的位位置，不表示每条命令都做“两个标量源寄存器到一个标量目的寄存器”的普通
整数运算。`rd` 在 `akvinfo` 中是 scalar destination，在 row/column load 中则解释为 vector
destination `vd`。当前 llama.cpp token-axis 路径使用下面五类命令：

| 概念助记符 | `funct3` | `funct7` | `rd/vd` | `rs1` 中的值 | `rs2` 中的值 | 严格作用 |
| --- | ---: | --- | --- | --- | --- | --- |
| `akvload.v` | 3 | D code：0=D64，1=D128，2=D96 | vector `vd` | row selector | 必须为 `x0` | 将 context 中一条 Q/K/V row 重放到 VRF |
| `akvinfo` | 4 | 必须为 0 | scalar `rd` | capability selector | 必须为 `x0` | 返回能力字，不改变 context |
| `akvrelease` | 5 | 必须为 0 | 必须为 `x0` | 必须为 `x0` | 必须为 `x0` | 使当前 committed context 无效 |
| `vakv2fill` | 6 | 0=FULL，1=REFILL | 必须为 `x0` | FULL 为 descriptor 地址；REFILL 为 `x0` | `tile_start` | 建立 context 或仅替换其中的 K/V tile |
| `vakv2kcol` | 7 | 0=单列，1=连续四列 panel | vector `vd` | column selector | 必须为 `x0` | 从驻留 K 生成 token-axis column/panel view |

表中的名称是便于阅读的概念助记符。当前编译器没有这些正式 mnemonic，软件通过 ABI helper 生成
raw word，原生 wrapper 再用 `.word` 发出。下面逐条说明每一个操作数。

#### 5.9.1 FULL 和 REFILL：把外部 K/V 变成有生命周期的本地 context

`vakv2fill` 的 `funct7` 只允许 0 或 1：

- **FULL (`funct7=0`)**：`rs1` 保存 64 B 对齐 descriptor 的虚拟地址，`rs2` 保存从 0 开始的
  `tile_start`。硬件读取 descriptor、该 GQA 组的 Query seed rows，以及从 `tile_start` 开始的
  `min(64, kv_length-tile_start)` 条 K/V rows。只有所有访问成功后才发布 READY context；
- **REFILL (`funct7=1`)**：`rs1` 必须是 `x0`，`rs2` 保存新的 `tile_start`。硬件复用 committed
  descriptor 和 Query，不重新读取 Q，只替换当前 K/V tile。它不能在 refill 时偷偷改变 D、GQA、
  base 或 stride；
- 其他 `funct7`、非零 `rd`、越界 tile 或不满足对齐的 descriptor 都非法。FULL/REFILL 会替换
  hidden state，因此必须等待更老的向量工作排空，并以 success/fault terminal 结束。

当前 wrapper 把 descriptor 放在 `a0`、tile start 放在 `a1`，对应：

| 操作 | 概念形式 | Raw word |
| --- | --- | --- |
| FULL | `vakv2fill.full x0, a0, a1` | `0x00b5605b` |
| REFILL | `vakv2fill.refill x0, x0, a0` | `0x02a0605b` |

这里 `tile_start` 是 K/V cache 的 token 索引，不是 byte address。真正地址由 descriptor 的
`k_base/v_base`、token stride、D 和该索引推导，并通过正常 MMU/PMA/AXI 路径读取。

#### 5.9.2 Row selector：指出要看 Q、K 还是 V 的哪一行

`akvload.v` 的 `rs1` 不是 memory address，而是由标量软件构造的 selector：

```text
bits 1:0  stream：0=Q，1=K，2=V，3=非法
bits 7:2  index：0..63
bits 63:8 必须为 0

selector = stream | (index << 2)
```

对 Q，`index < q_rows`；对 K/V，`index < 当前 tile_count`。例如 `selector=2|(5<<2)=22` 表示
当前 tile 的 `V[5,:]`。这个 selector 先由 engine 对 committed context 检查，再映射到 Query row
store 或 64-token K/V banks；它不会再次读取 `v_base + 5*stride`。

`funct7` 中的 D code 必须与 context 的 `head_dim` 一致，因为 dispatcher 在访问 hidden metadata
之前就要预留目的向量寄存器组：

| D code | Head dimension | RVV 目的形状 | `vd` 约束 | `vd=v8, rs1=a0` 的 raw word |
| ---: | ---: | --- | --- | --- |
| 0 | 64 | e16/m1，64 个 F16 | `vd<=31` | `0x0005345b` |
| 1 | 128 | e16/m2，128 个 F16 | 偶数 `vd<=30` | `0x0205345b` |
| 2 | 96 | e16/m2，前 96 个 F16 有效 | 偶数 `vd<=30` | `0x0405345b` |

目的寄存器中的这些 F16 bits 之后由普通 RVV `vfwcvt`、`vfwmacc` 或其他 Attention kernel 消费。
本地 row load 可在 engine 接受并完成合法性检查后提前释放 scalar-side request handshake，但
sequencer 中的 `vid` 和 destination hazard 要等所有 lane result grants 完成后才释放；因此年轻
指令不可能读到只写了一半的向量。

#### 5.9.3 Column selector：把 row-major K 当作 token 向量读取

QK 点积对固定 dimension `d` 需要：

```text
[K[token0,d], K[token1,d], ..., K[tokenT-1,d]]
```

`vakv2kcol` 用 `rs1` 指定这个视图。selector 的 bits 6:0 是 0..127 的 dimension，bit 7 是分段
组合时使用的 128-element segment，bits 63:8 必须为 0。当前生产选择的 D64/D96/D128 都使用
`segment=0`。单列命令 (`funct7=0`) 产生 64 个 e16 slot，使用 LMUL1；最后一个不足 64-token 的
tile 只使前 `tile_count` 个元素有效。

四列 panel (`funct7=1`) 一次返回 `d..d+3` 四个 64-token columns，等价于四条相邻单列命令的
数据内容，但只支付一次 decode/dispatch/context 启动开销：

```text
v[vd+0] <- K[:, d+0]
v[vd+1] <- K[:, d+1]
v[vd+2] <- K[:, d+2]
v[vd+3] <- K[:, d+3]
```

panel 使用 e16/m4，要求 `vd` 四寄存器对齐且 `vd<=v28`，dimension 四元素对齐，并要求
`dimension+4<=head_dim`。以 `vd=v8`、dimension selector 位于 `a0` 为例，单列是 `0x0005745b`，
panel4 是 `0x0205745b`。硬件验证 context、selector 和目的组之后，从八个 token banks 读取并
拼接 column；这条命令自身不做 QK 乘法。

#### 5.9.4 `akvinfo`：软件怎样确认硬件与 ABI 相符

`akvinfo` 的 `rs1` 保存 selector，返回值写入 scalar `rd`。当前 wrapper 以 `a0` 同时承载输入和
输出，对应 raw word `0x0005455b`。公共 runtime 会读取 selector 0、1、2、3，并把四个 64-bit
word 作为一份分层能力记录共同验证；未知 selector 返回 0。

| Selector | 主要字段 | 当前严格含义 |
| ---: | --- | --- |
| 0 | bits 7:0/15:8/23:16 | architecture=1、descriptor version=1、descriptor bytes=64 |
| 0 | bits 31:24/39:32/47:40 | max Q rows=8、common row-view tile=8、context count=1 |
| 0 | bits 48..51 | implementation enabled、F16 payload、D64、D128 均支持 |
| 1 | bits 7:0 | opcode=`0x5b` |
| 1 | bits 10:8/13:11/16:14/19:17 | common fill/load/info/release funct3=`2/3/4/5` |
| 1 | bits 27:20 | descriptor alignment log2=6，即 64 B |
| 2 | bits 7:0/15:8/23:16/31:24 | token-axis profile=2、tile=64、banks=8、row index bits=6 |
| 2 | bit 32 | token-axis implementation enabled |
| 2 | bits 35/36 | 1..64 token tail 和 row view 可用 |
| 2 | bits 38/39/40 | D-axis tail、segmented D256 composition、column panel4 能力 |
| 3 | bits 7:0/10:8/13:11/23:16 | opcode=`0x5b`、token-axis fill funct3=6、column funct3=7、physical row bound=128 |

Selector 2 的 bits 33、34、37 和 selector 3 的 bit 24 目前由生成 ABI 固定为 1，并由公共 runtime
作为完整 capability signature 的一部分核验；公共结构没有给它们暴露可独立选择的 feature 名称，
因此本文不把这些位另行解释成近似功能。Selector 0 中的 tile=8 描述同一 ABI 中的 common row-view
记录；当前 llama.cpp 路径只有在 selector 2/3 同时有效时才进入 64-token token-axis 数据流，不能
把 selector 0 的 8 或 selector 2 的 64 单独拿出来猜执行方式。

同理，selector 1 中公布的 common fill `funct3=2` 属于当前 ABI 保留的 row-view command surface；
本文描述的 llama.cpp token-axis 执行序列不发出它，而是使用 selector 3 公布的 `funct3=6` FULL/REFILL。
这不是运行时在两套数据流之间随机选择：公共 runtime 先完整核验四个 capability words，GGML
selected path 随后固定使用 64-token 命令族。

软件仍需先通过平台契约、设备树、OS hwprobe 或一次 trap-safe probe 确认处理器会解码 AKV；不能
在未知 CPU 上直接执行 `akvinfo`，再期待 illegal-instruction trap 自动变成普通函数式回退。

#### 5.9.5 `akvrelease` 和所有命令共有的隐式状态

`akvrelease` 没有显式操作数，所有 R-type 字段必须为 0，raw word 为 `0x0000505b`。它等待更老
向量工作完成后清除 context ready；之后任何 local row/column load 都必须失败，直到新的 FULL
成功提交。显式 RELEASE 让软件可以在一个 GQA group 结束时终止 K/V snapshot 生命周期，也为
异常清理和未来 protection-domain 切换提供明确边界。

上述指令还共同依赖以下不在 32-bit encoding 中的状态：

- `vstart` 必须为 0，当前不支持从某个 token 或 VRF word 断点重启；
- CVA6 accelerator-consistent mode 必须开启；
- 当前 RTL 实现只在 4 lanes、VLEN=1024 且对应 AKV build capability 开启时广告可用；
- payload 的 element format 是 descriptor 指定的 F16；scale、mask 和 Softmax 状态不在 context 中；
- FULL/REFILL/RELEASE 需要 `ara_idle`，本地 row/column load 则通过正常 sequencer、VLSU owner 和
  lane-result backpressure 推进。

这里的“load”需要分清两种动作：FULL/REFILL 通过 MMU/AXI 从模型内存取数；row/column load 只读
已经 committed 的片上 context，再通过正常 LDU lane-result handshake 写入 VRF。后续 QK、scale、
mask、Softmax 和 PV 都还是普通 RVV 指令，所以 AKV 增加的是数据驻留和数据视图，不是第二套
Attention 算术单元。

核对实现时应以 `config/akv_abi.json` 为 ABI 真源，以生成的
`software/akv/include/akv/akv_abi.h` 和 `hardware/include/akv_pkg.sv` 分别核对软件/RTL 常量；
`.word` 位于 `software/akv/src/akv_v2_native_riscv.c` 和
`software/akv/src/akv_v2_attention_rvv.S`，最终 decode 位于 `hardware/src/ara_dispatcher.sv`。
不要只修改其中一个 raw word 或手写常量，否则 reference、runtime 和 RTL 会产生静默 ABI 漂移。

### 5.10 AKV descriptor：描述一个 GQA 组的运行时张量

当前 AKV descriptor 的结构版本号为 1，是 little-endian、固定 64 B、64 B 对齐的对象：

| Offset | Bytes | Field | 严格含义 |
| ---: | ---: | --- | --- |
| 0 | 1 | `version` | 必须为 1 |
| 1 | 1 | `element_format` | 当前只允许 F16=1 |
| 2 | 1 | `q_rows` | 同一 KV head 对应的 Query rows，1..8 |
| 3 | 1 | `flags` | 当前必须为 0 |
| 4 | 2 | `head_dim` | 生产选择为 64、96 或 128 |
| 6 | 2 | `kv_length` | 该 KV head 的总有效 token 数，必须非零 |
| 8 | 4 | `q_row_stride_bytes` | Q 相邻 head row 的 byte stride |
| 12 | 4 | `k_token_stride_bytes` | K 相邻 token row 的 byte stride |
| 16 | 4 | `v_token_stride_bytes` | V 相邻 token row 的 byte stride |
| 20 | 4 | `reserved0` | 必须为 0 |
| 24 | 8 | `q_base` | 当前 GQA 组第一条 F16 Q row |
| 32 | 8 | `k_base` | 当前 KV head 的第一条 F16 K row |
| 40 | 8 | `v_base` | 当前 KV head 的第一条 F16 V row |
| 48 | 16 | `reserved1/2` | 必须为 0 |

当前生产路径要求 Q/K/V base 与相应 row/token stride 为 32 B 对齐，使每个 128-bit fill beat
可映射到一个 256-bit token-bank row，而无需暂停 read engine 处理跨 bank 写。所有末地址都先用
扩展精度检查，任何 64-bit wraparound 在发 payload 请求前拒绝。

descriptor 不携带 causal mask、ALiBi slope、softcap、attention sink 或 scale。它们仍是 RVV
算术的显式输入。这一边界非常重要：AKV 只承诺“这些 Q/K/V bytes 在一个 context 生命周期内
保持快照，并能按指定视图读取”，不承诺某一种模型专属 Softmax 公式。

### 5.11 AKV context 的状态、快照和故障语义

软件可见的抽象状态是：

```text
EMPTY --FULL--> FILLING --success--> READY
                         --fault----> EMPTY
READY --REFILL--> REFILLING --success--> READY(new tile)
                           --fault----> EMPTY
READY --row/column load--> READY
READY --RELEASE----------> EMPTY
```

FULL 一被接受就使旧 context 不再 ready；payload 写入只是 speculative hidden state，全部 descriptor、
translation、PMA、AXI response 和 range completion 成功后才发布新的 ready。REFILL 复用已提交的
shape/base/stride 元数据，只替换当前 K/V tile；发生任何读取故障时整份 context 失效，不能留下
新旧 token 混合。合法的本地 row/column load 不再访问外部内存；selector validation 失败不会
破坏已有 ready context，也不会部分写 `vd`。

这与 QBS 的“隐藏 accumulator 最后原子提交”同源：长操作可以在内部逐周期推进，但在故障边界上
只能暴露完整的新状态或保持无新状态。两者也都不提供 element-level `vstart` restart；当前命令
要求 `vstart=0`，系统若要支持抢占或 page-fault resume，必须另行定义可保存的进度语义。

### 5.12 原始 Attention 算子与 AKV 调用序列的对照

先看 AKV 未介入时，一个 GQA group 的 Decode Attention 在算法上做什么。设一条 KV head 被 `G`
条 Query heads 共享，当前历史长度为 `T`，head dimension 为 `D`：

```text
输入：Q[G,D]，K[T,D]，V[T,D]，mask[T]

for q = 0 .. G-1:
    for t = 0 .. T-1:
        score[q,t] = dot(Q[q,:], K[t,:]) * scale + mask[t]
    probability[q,:] = softmax(score[q,:])
    for t = 0 .. T-1:
        output[q,:] += probability[q,t] * V[t,:]
```

高质量标准 RVV kernel 会把 token 分块、在寄存器中维护 online-softmax 状态，并避免把完整
`score[G,T]` 写回内存，因此不能把它描述成“完全没有 tiling”。但从 RVV 可见的数据供给看，它仍需
为 QK 沿 row-major `K[t,:]` 取数据，再组织固定 dimension 跨多个 token 的运算；PV 又按 token 读取
完整 `V[t,:]`。同一 K/V tile 被 G 条 Query rows 使用时，软件循环、向量 load 和临时寄存器必须
共同维持这种复用，K 的 row-major 存储方向与 QK 希望的 token-axis 消费方向也不一致。

当前 AKV 保持同一个 Attention 公式，把循环改写为“先建立 64-token 数据视图，再用普通 RVV
计算”。概念序列如下：

```text
preflight：检查 capability、D、GQA、stride、mask、scale 和算法边界

for each GQA group:
    for tile_start = 0; tile_start < T; tile_start += 64:
        第一个 tile：FULL(descriptor, tile_start)
        后续 tile：  REFILL(tile_start)

        // QK：一次取 K 的 4 个相邻 dimension，供 G 条 Q rows 复用
        for d = 0; d < D; d += 4:
            Kpanel = AKV_COLUMN_PANEL4(d)
            用普通 RVV widening FMA 更新各 Query row 的 score

        用普通 RVV 执行 scale、mask、max、exp、sum 和 online-softmax merge

        // PV：当前 token 的 V row 只从 context 重放一次，再供 G 条 Q rows 使用
        for t = 0; t < tile_count; ++t:
            Vrow = AKV_ROW_LOAD(V, t)
            用普通 RVV FMA 更新各 Query row 的 output

    RELEASE()
```

FULL 按 descriptor contract 也填充 F16 Query seed，但当前 score kernel **并不保证总是通过
`akvload.v` 取 Q**。为了保持所选 GGML 路径的数值顺序，部分 shape 继续直接使用软件 workspace
中的 F32 Query，另一些路径使用 F16 Query。AKV 的已测硬件收益因此应归因于 K/V 驻留、视图和
GQA 复用，不能把 Query 也一概计作已消除的外部读取。

Prefill 使用同一套 64-token K/V context，但外层还有 Query-token block。软件为一个 Query block
维护各自的 max、sum 和 output，并按 causal 可见范围决定每条 Query 能消费多少 K/V token。AKV
不替软件决定 causal mask，也不把不同 Query token 的 online-softmax 状态藏进硬件；它只为当前
可见 tile 提供相同的 row/column view。

两条路径的变化与不变项可以直接对照：

| 项目 | 标准 RVV Attention | 当前 AKV + RVV Attention |
| --- | --- | --- |
| GGML graph 节点 | `FLASH_ATTN_EXT` 或对应 RVV Attention 路径 | 同一个节点，adapter 通过 preflight 后选择快路径 |
| Q/K/V 数值 | F16/F32 tensor 按 GGML layout 读取 | K/V 以 F16 bits 做 snapshot；Query 按所选 kernel 保留 F16/F32 数值路径 |
| K 数据视图 | 软件从 row-major K load 并组织 QK 运算 | context 直接给出 1 列或连续 4 列 token-axis view |
| V 数据视图 | 软件按 token load V row | `akvload.v` 从 context 返回同一 V row |
| GQA 复用 | 由软件 loop/register tiling 尽量保留 | 一次 K panel/V row 明确供同 KV head 的多条 Q rows 使用 |
| QK/PV 乘加 | 标准 RVV F16/F32 widening/FMA | 仍是相同类型的普通 RVV widening/FMA |
| scale/mask/Softmax | 标准 RVV/标量代码 | 保持所选 numerical contract，仍由普通 RVV/标量代码执行 |
| 外部访存 | RVV kernel 按自身 tiling 读取 K/V | 每个有效 K/V tile 由 FULL/REFILL 各读取一次，local view 不再访问外部内存 |
| 不支持条件 | 使用普通 RVV | 在任何 AKV side effect 前回退到同一普通 RVV 路径 |

因此 AKV 的收益不是“用专用 Attention 单元替换 RVV 算术”，而来自三项具体变化：

1. **驻留**：一个 64-token K/V tile 从外部内存读取一次，后续 row/column 命令只访问片上 context；
2. **转置式视图**：row-major K 在写入时按 token banks 保存，读取时可直接聚合固定 dimension 的
   token vector，省去软件重复 load、shuffle 或不利 stride；
3. **GQA 共享**：同一 KV head 对应的多条 Query rows 消费同一 K panel 和 V row，数据复用发生在
   明确的 context 生命周期内，不靠地址相等猜测。

相应代价也很明确：FULL/REFILL 有 descriptor、translation 和填充延迟；local view 仍占用 LDU
result port；短 T、G=1、低复用或不匹配的 layout 可能无法摊薄固定成本。因此软件保留 shape gate
和普通 RVV fallback。第 11.9 节把当前 AKV 同时与标准 RVV 和强 tiled-RVV 比较，后者用于区分
“软件 tiling 本身的收益”和“数据驻留/视图硬件的增量收益”。

## 6. llama.cpp/GGML 端完整调用链与模型适用范围

### 6.1 公共运行时边界、编译和运行开关

`software/qbs` 是严格 C11、可单独构建和安装的公共运行时库，不包含 `ggml_type`、GGUF 文件名、
Qwen layer 名称或 GGML operator ID。它对上层暴露 `qbs::runtime` CMake target，以及下面六层接口：

| 公共层 | 作用 | framework 仍负责什么 |
| --- | --- | --- |
| encoding binding | 用稳定 encoding ID 严格绑定当前设备的 profile pair | 核实 native bytes，或提供经过验证的加载期 converter |
| profile metadata | 查询 block bytes/elements、subgroup、scale、correction 和合法 activation 配对 | 使用绑定结果构造 framework tensor cache |
| capability discovery | 统一解析并核验 `qbinfo` | 先通过 ISA/platform discovery 确认扩展存在 |
| packing | row-major weight 到 R4、Q8 activation 到 M4/M8 grouped | 决定持久缓存和临时 buffer 生命周期 |
| planning | 默认 M1--M4/可选 M5--M8、N tile/tail、K segmentation 和 workspace | 提供逻辑 `M/N/K`、源 layout 和 wide-M 策略开关 |
| checked execution | 校验输入/输出容量，构造 descriptor，合并 split-K | 提供 allocator、错误传播和 command executor |
| native ISA | `qbinfo/qbexec` wrapper | 决定何时使用 native、emulation 或普通 fallback |

另一运行时接入时有三种明确结果：若其 native byte layout 和数值公式与某个 canonical encoding
完全一致，提交对应 encoding ID 并由公共层绑定；若不一致但允许加载期转换，可由该运行时提供经过
数值验证的 converter，再以转换目标的 encoding ID 绑定并缓存；若两者都不成立，则保持原有 kernel。
相同 bit width 或 group size 不能作为直接映射依据。例如外部 group-64 INT4 不能因为也是 4 bit
就冒充 Q4_K。当前 llama.cpp adapter 已改为 encoding-ID binding，不再把 `ggml_type` 直接解释为
硬件 profile 编号。当前没有宣称 ONNX Runtime 或 ExecuTorch 已经完成集成；
`software/qbs/examples/runtime_adapter.c` 只用于证明上述接口不依赖 GGML。

当前 backend 由 `GGML_USE_RISCV_QBS` 编译开关接入。运行时关键环境变量包括：

- `GGML_RISCV_QBS=1`：允许 native capability probe 和 QBS 选择；
- `GGML_RISCV_QBS_EMULATE=1`：执行软件 emulation，用于框架功能验证，不代表硬件性能；
- `GGML_RISCV_QBS_FORMATS=...`：profile allowlist，便于单格式隔离；
- `GGML_RISCV_QBS_WIDE_M=1`：允许 planner 为流量明显有利的 Prefill shape 选择 M5--M8/N16；
  未设置时保持 M1--M4/N32 默认策略；
- trace/coverage 变量：记录 tensor 选择、fallback 原因、GEMV/GEMM、M 分布、split-K 和命令数。

这里要区分两种“模拟”：GGML 环境变量打开的是 backend 内的标量反量化执行路径，主要用于
检查 trait、repack、分块和 dispatch，浮点求和顺序不保证与硬件 numerical contract 逐位相同；
`verification/qbs/qemu/` 中的 `Xaraqbs` 则把 `qbexec` 作为 guest 指令执行，并直接复用 canonical
reference，是架构语义检查。二者都不是 RTL timing model。

AKV 采用同样的“公共运行时 + GGML adapter + native wrapper + reference”分层。`software/akv`
定义 descriptor、capability、Decode/Prefill plan 和标准 RVV arithmetic helpers；
`ggml/src/ggml-cpu/arch/riscv/akv.cpp` 只负责检查 `FLASH_ATTN_EXT` tensor 与选择执行路径。关键开关为：

- `GGML_RISCV_AKV=1`：允许查询真实 AKV capability 并选择 native path；
- `GGML_RISCV_AKV_EMULATE=1`：在 Host/QEMU 模型闭环中执行功能 reference，不提供 RTL 周期；
- `GGML_RISCV_AKV_KERNEL=auto`：由 capability 自动选择本文描述的 token-axis AKV 路径；
- `GGML_RISCV_AKV_TRACE=1`：输出 candidate/executed、Decode/Prefill、Attention MAC 和逐原因 fallback。

QBS 和 AKV 可以在同一次模型运行中同时启用：QBS 接管合格的量化 `MUL_MAT`，AKV 接管合格的
`FLASH_ATTN_EXT`。两者不是二选一，也不会改变其余 GGML node 的普通 RVV 实现。

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

默认 GGML 路径中，`M<4` 使用 row-major activation，`M=4` 使用
`M4_INTERLEAVED`，即同一 K block 的四个 activation row 相邻。显式启用 wide-M 后，公共
byte-cost 模型会比较 M4/N32 与 M8/N16 的总 `weight + activation` 输入；对通过阈值的
M>=5 分组使用 `M8_INTERLEAVED`，末尾 M5--M7 在物理存储中补到八行，但 logical M 仍决定提交行数。

GGML 原有 `from_float` 量化器先产生 Q8 row-major 数据，随后公共 packing 层在需要时
组织为 M4 或 M8 layout。packing 使用 GGML 既有 worker barrier 保证所有行量化完成后才开始
矩阵命令，因此硬件不会读取仍在写入的 activation buffer。当前 M8 路径先在独立 staging
区完成 row-major 量化，再由单 worker packing；这个软件开销是实际代价，不能算作免费。

### 6.4 GEMV：Decode 的 M=1 路径

GGML 的 `ggml_riscv_qbs_gemv()` 要求输入行数为 1，公共 planner 随后：

1. 计算 `k_blocks = K / block_elements`；
2. 按硬件 `max_n` 将输出行分成 N tile，VLEN=1024 时通常 N=32；
3. 为每个 tile 构造 descriptor；
4. `qbexec` 把 N 个 FP32 结果写到一个向量寄存器；
5. `vse32.v` 只存 logical N 个结果。

M=1 是权重带宽最敏感的 decode 形态。当前 engine 对 `M=1 + R4` 开启下一 weight tile
lookahead：current bank 计算时，inactive bank 可以预取**同一 K block 的下一组四个输出行**。
它不会跨 K block 猜测；K block 推进时 activation 和 weight bank 生命周期重新建立。

### 6.5 GEMM：Prefill 的默认 M=1..4 与可选 M=5..8 路径

GGML 先对完整 `MUL_MAT` 调用执行一次 activation 规划。默认由 `ggml_riscv_qbs_gemm()`
使用 row-major 或 M4-grouped storage；wide-M 明确开启且计划通过时，由
`ggml_riscv_qbs_gemm_wide()` 使用 M8-grouped storage：

```text
for input rows:
    choose default M<=4,N<=32 or admitted wide M<=8,N<=16
    choose row-major, M4-interleaved, or M8-interleaved activation
    for output rows in the selected N tiles:
        qbexec(M, N, K-blocks)
        store M output vectors
```

一条命令最多形成 128 个 FP32 results：窄几何为 `4 x 32`，宽几何为 `8 x 16`。
M4 让同一 weight block 同时服务四条 activation row；M8 不复制 32-pair/cycle dot array，而是用
两个顺序的四行 wave 延长 weight block 生命期。R4 让四个 output rows 的对应 weight block 连续。
宽几何会减少重读 weight，但 N32 降为 N16 也会增加 activation 读取和命令组织开销，所以
必须用流量模型与 RTL 周期分开判断。复用范围完全由 descriptor 的 shape/layout 推导，没有按
地址猜测的隐式流状态。

### 6.6 长 K 的软件分段

硬件单命令最多 256 个 native K blocks。更长 K 不直接失败，而由公共 planner/executor 分段：

1. 每段构造独立 descriptor；
2. 每段 QBS 输出一个 partial FP32 tile；
3. 软件按 K 段顺序累加 partial results。

现有 R4 layout 的任意 K 子段只在单个四行组内连续，因此 split-K functional path 将 N 限制
为最多 4。M=4 的 interleaved segment 和满足基址对齐的 M=1 row-major segment 可直接引用原
activation buffer；只有 M=2/3 的跨行 K 子段，或少数起始地址不满足 ABI 对齐的 row-major 子段，
才复制到连续的 gather workspace。公共 planner 只在至少一条命令确实需要复制时预留这部分空间；
split-K partial tile 则始终使用独立的小型 FP32 workspace。该路径保证长 K 的功能覆盖，但 R4 下
N 最多为 4 仍不是最终高性能布局；若长 K 成为常见路径，应设计 segment-friendly layout 或扩展
descriptor，而不是隐藏不连续性。

### 6.7 选择条件和 fallback

QBS 只有在公共层与 GGML 适配层的条件同时成立时才接管 tensor：

- 用户显式启用，`qbinfo` contract 匹配；
- weight type 属于九种 profile；
- tensor 为支持的 2D，或不会跨 expert R4 group 的 3D；
- K 可被 profile block size 整除，shape 和地址合法；
- profile、layout、M/N/K 容量均被硬件声明支持。
- weight、activation、output 和 workspace 的容量在投放前通过公共层检查。

否则 `ggml_repack_get_optimal_repack_type()` 继续选择原来的 RISC-V/RVV 或通用 CPU trait。
这是 QBS 保持通用性的关键：**新路径是受能力和 shape 约束的优化，不是改变全部 MUL_MAT 的语义。**

### 6.8 覆盖哪些模型算子，不覆盖哪些

只要权重格式和 shape 合法，QBS 可以覆盖 `GGML_OP_MUL_MAT`，并对满足 R4 expert 边界的
`GGML_OP_MUL_MAT_ID` 提供受约束路径，包括：

- Attention Q/K/V/O projection；
- FFN gate/up/down projection；
- 兼容格式的 embedding/output projection；
- 普通 2D tensor，以及不会让四行 repack group 跨 expert 的 MoE 3D tensor。

除三 expert directed case 外，当前还使用真实 OLMoE-1B-active/7B-total Q4_K_M 模型完成了
Host 图与全系统 QEMU 功能闭环。该模型包含 64 个 expert、每 token 选择 8 个 expert；单个
Decode 图中观察到 65 个普通 `MUL_MAT` 节点和 48 个 `MUL_MAT_ID` 节点。llama.cpp 在进入
expert 循环前只量化一次源 activation，随后对被路由到的 expert 执行矩阵计算，因此 source
activation rows、动态 routed rows 和完整 expert tensor 容量是三个不同统计量，不能相互替代。
这一结果证明一个真实 64-expert/top-8 layout 已接通，但仍不代表任意 expert 数、routing/layout
和所有 MoE 模型已经闭环。Expert routing、token-to-expert gather/scatter 和 load balancing
仍由 GGML/runtime 处理，QBS 只接管最终满足条件的量化矩阵 tile。

QBS 当前不直接执行：

- FP32 到 Q8_K/Q8_0 的动态量化本身；
- RMSNorm、LayerNorm、RoPE、Softmax；
- Attention score、value aggregation 和 KV-cache 管理；其中满足 AKV selector 的
  `FLASH_ATTN_EXT` 可由 AKV 提供 K/V context 和局部视图，但计算仍由标准 RVV 完成；
- elementwise activation/residual；
- 未列入 ABI 的 GGUF type，例如其他 IQ、TQ、MXFP profile。

因此 QBS 可显著加速主要线性层，AKV 则减少 Attention 的 K/V 外部读取和不利视图转换；两者都
不能仅凭局部 speedup 推导完整模型 token/s。端到端 Amdahl 比例、activation quantization、
非线性算子、未选择的 Attention shape 和内存系统仍需单独测量。

### 6.9 用 Qwen2.5-1.5B Q4_K_M 具体理解覆盖范围

当前真实 leaf 数据集取自 Qwen2.5-1.5B-Instruct Q4_K_M 的第 0 层；完整模型共有 28 层，
hidden size 为 1536，包含 12 个 query heads、2 个 KV heads、128 维 head 和 8960 维 FFN。
第 0 层七个线性权重及其实际 encoding/shape 为：

| GGML tensor | Weight | `K` | `N` | Decode `M` | Prefill capture `M` | 作用 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `attn_q` | Q4_K | 1536 | 1536 | 1 | 15 | 生成 12 个 query heads |
| `attn_k` | Q4_K | 1536 | 256 | 1 | 15 | 生成 2 个 key heads |
| `attn_v` | Q6_K | 1536 | 256 | 1 | 15 | 生成 2 个 value heads |
| `attn_output` | Q4_K | 1536 | 1536 | 1 | 15 | 合并 attention 输出 |
| `ffn_gate` | Q4_K | 1536 | 8960 | 1 | 15 | SwiGLU gate projection |
| `ffn_up` | Q4_K | 1536 | 8960 | 1 | 15 | SwiGLU up projection |
| `ffn_down` | Q6_K | 8960 | 1536 | 1 | 15 | FFN 投影回 hidden size |

表中 weight matrix 按 `N x K` 理解。Decode 的一行 activation 对应 M1 GEMV。默认策略下，
Prefill 的 15 行由 `4+4+4+3` 个 input-row groups 执行，每组内部 N 按最多 32 个输出行切分。
最后一个 M3 group 只提交三条有效输出向量，不会把物理保留位置写成第四条模型结果。
若显式启用 wide-M 且该 profile/shape 通过 byte-cost 判定，同一 M15 逻辑问题可改为
`8+7` 两个宽组，每组 N<=16；这只改变 tiling 与数据复用，不改变 15 行模型语义。

Q4_K_M 是混合格式模型，名称中的 Q4_K 不意味着所有 tensor 都是 Q4_K。`attn_v` 和
`ffn_down` 使用 Q6_K 正是多 profile capability 和 fallback 必须在真实模型中验证的原因。
RMSNorm、RoPE、SwiGLU 和 residual 仍由 RVV/标量 GGML kernels 执行；Attention 的 QK、Softmax
和 PV 算术也仍是 RVV，但合法 `FLASH_ATTN_EXT` 可由 AKV 提供 resident K/V 和 token-axis
view，因此“算术仍为 RVV”不等于“Attention 完全没有硬件协同”。

### 6.10 三层循环怎样映射到软件和硬件

完整执行不是“一条指令计算整个模型矩阵”。它包含三个不同层次的 tiling：

```text
GGML operator
  choose default row-major/M4 or admitted M8 storage once    // software
  for each input-row group M<=4, or wide group M<=8:         // software
    quantize/pack activation rows
    for each output tile N<=32 (narrow) or N<=16 (wide):     // software
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
  activation row 复用；
- **命令间**，hidden accumulator 和 weight bank 不持久；descriptor v2 可由软件显式选择 activation
  context，使首个 N tile 以 `FILL` 建立 Q8_K 快照，中间 tile 以 `REUSE` 消费，最后一个 tile
  以 `RELEASE` 消费并释放。未选择该选项的 `qbs_execute()` 仍为逐命令 `DIRECT`。

当前 context 实现只覆盖一个 `M=1`、row-major Q8_K context，最多 16 个 K blocks。token 的
ID/generation、profile、layout、M 和 K 必须全部匹配；硬件不按地址隐式命中，也不在失配时
静默回退。`FILL` 只有在整条命令成功 commit 后才有效，故障和 reset 会阻止半有效快照被后续
命令观察。该机制解决同一矩阵多个 N tile 的重复 Q8_K 读取，但尚未跨 Q/K/V 或 gate/up 共享
F32-to-Q8 动态量化结果；跨 operator 扩展还需要绑定 tensor identity 与 graph execution epoch。

### 6.11 当前覆盖深度，而不只是格式数量

“支持九种格式”只说明 profile decoder 的横向覆盖。当前能力应按以下五层描述：

| 覆盖层 | 当前范围 | 不能据此推导的结论 |
| --- | --- | --- |
| Format | 9 组 weight/activation profile | 不等于覆盖全部 GGUF types |
| Shape | 默认 M1--M4/N<=32；可选 wide-M 为 M5--M8/N<=16；K<=256 blocks，软件处理 N/M/K 外层分块 | 不等于所有 shape 都同样高效；wide-M 当前非默认，过长 K 会增加分段与合并开销 |
| Operator | quantized `GGML_OP_MUL_MAT` 和受约束 `MUL_MAT_ID` 的 GEMV/小 M GEMM | 不等于覆盖完整 Transformer block |
| Model mapping | Qwen2、Llama、Gemma3、Phi3 和 OLMoE 中的主要量化线性层 | 不等于所有模型家族、量化类别和 MoE layout 已验证 |
| Implementation evidence | reference、directed RTL、QEMU native model、部分真实 RTL workload | 不等于完成 P&R、功耗和标准数据集质量闭环 |

对已经隔离测试的目标 profile，`selected_tensors == candidate_tensors` 和
`selected_elements == candidate_elements` 只表示该 profile 的候选权重达到 100% **repack trait
选择覆盖**。它不是 operator-call coverage；还必须检查 `gemv/gemm_calls`、`native_qbexec` 和
`emulated_commands`。这个百分比不能用作“整个模型 100% 被 QBS 加速”。

### 6.12 未覆盖操作是否适合并入 QBS

当前未覆盖操作应按计算结构判断，而不是为了提高算子数量全部塞入同一命令：

| 操作 | 主要行为 | 与 QBS 的合理关系 |
| --- | --- | --- |
| FP32 -> Q8_K/Q8_0 动态量化 | abs-max reduction、scale、round/clamp、Q8_K bsums | 与输入准备紧邻，适合未来 context 化和流水化，但必须量化一次供多个 N tile 复用 |
| RMSNorm/LayerNorm | 平方、sum reduction、rsqrt、scale | 更适合增强 RVV reduction/SFU；除非与下一次量化形成可证明的 fusion |
| RoPE | 成对旋转、sin/cos 系数和逐元素运算 | 规则 RVV kernel 更自然，不宜改造成 block-matmul profile |
| Softmax | max/sum reduction、exp、division | 需要 reduction 和特殊函数支持，不属于当前压缩权重点积数据流 |
| Attention score/value | 动态 Q/K/V 上的矩阵乘和归一化后聚合 | 当前由 AKV 提供有界 K/V 驻留/view、普通 RVV 完成算术；它保持独立机制，不伪装成 weight profile |
| KV-cache | token/head 寻址、读写、layout、容量和带宽 | 主要是存储系统问题，适合地址生成、layout、预取或压缩协同 |
| SiLU/SwiGLU/residual | elementwise 激活、乘法和加法 | 保留普通 RVV；只有实测成为主瓶颈时再考虑 fusion |
| 其他 GGUF quant | 新的 block 字节布局和数学 | 仅当可复用现有 decoder/dot/correction 主路径且真实模型常用时增加 profile |

由此得到的合理总体架构不是“QBS 执行全部 LLM”：QBS 负责量化线性层，AKV 负责受约束的
Attention K/V 驻留和视图，普通 RVV 负责 QK/Softmax/PV 以及通用 elementwise/reduction；再以
实测 Amdahl 比例决定是否扩展 activation lifetime、更多 Attention shape 或通用 RVV 算术。

### 6.13 不改硬件时能否迁移到其他模型家族

QBS RTL 不识别 `Qwen`、`Llama`、`Mistral`、layer number 或 `ffn_gate` 等模型名称。只要另一个
模型的线性算子最终下沉为受支持的 GGML `MUL_MAT`/受约束 `MUL_MAT_ID`，权重采用九种 profile
之一，shape/layout 能由软件切成合法命令，它就可以复用同一硬件。Dense decoder-only 模型的
Q/K/V/O、FFN 和 LM head 因而是最直接的可迁移对象。

这种通用性来自明确的数据格式和 shape 规则，而不是一张模型名称白名单；它不表示“所有
llama.cpp 模型无需验证即可加速”：

- 模型使用未支持的 IQ/TQ/MXFP/NVFP encoding 时，相应 tensor 自动回退；
- MoE 模型还受 expert tensor layout 和 R4 边界约束，routing 本身不由 QBS 执行；
- encoder、multimodal、convolution 或非 GGML backend 可能使用不同 operator/data layout；
- M/N/K 虽可由软件分块，但极小 tail、长 K segmentation 或频繁短命令可能功能可用而性能不佳；
- KV-cache 容量管理、Attention 数值计算和非线性算子仍依赖普通软件/RVV；AKV 只在受支持
  `FLASH_ATTN_EXT` 上改变 K/V 供给和局部视图。因此模型家族、D/GQA、上下文长度和 Attention
  feature 会改变端到端 Amdahl 比例，即使量化线性层本身完全命中 QBS。

评价“支持一个新模型”至少应同时给出逐 tensor type/shape 清单、selection/fallback counter、
真实模型数值结果和端到端 operator time；只看到文件名中有 `Q4_K_M` 不足以证明覆盖。

### 6.14 当前已经核验的 llama.cpp 模型

先解释表中的模型结构。**稠密模型（Dense）**在每个 Transformer 层中，让每个 token 都经过同一组
FFN gate/up/down 权重。**混合专家模型（Mixture of Experts，MoE）**则先由 router 为当前 token
挑选少数 expert，再只执行被选 expert 的 FFN。GGML 中普通二维权重矩阵通常形成 `MUL_MAT`；
MoE 根据 expert ID 选择三维权重中的某一片，通常形成 `MUL_MAT_ID`。QBS 不负责 router、expert
选择或 token 搬运，只接管选择完成后满足格式、shape 和 R4 边界的量化矩阵计算。

Attention 一栏中的 `D` 是每个 attention head 的特征维数；`GQA` 是共享同一组 K/V 的 Query
head 数。`Decode` 表示模型已有一段上下文、现在一次生成一个新 token；`Prefill` 表示一次处理
用户刚输入的多个 token。它们使用同一套模型权重，但 Query 数和 K/V 访问方式不同，因此 AKV
必须分别检查其 shape 和算法路径。

先澄清“支持模型”的含义。加载 GGUF、建立计算图、管理 KV cache、采样并生成文本的是
`llama.cpp`；QBS 和 AKV 只是它的两条 CPU/RVV 快路径。只要上游 `llama.cpp` 本身支持某个模型，
未命中 QBS/AKV 的节点仍可由普通 RVV 执行。因此，下面的“支持”表示**已经证明该模型中的一部分
真实节点能够进入快路径并保持正确**，不是说硬件中写死了这些模型名称，也不是说整张计算图都由
专用硬件执行。

| 已核验模型 | 模型结构 | 实际量化线性层 | QBS 状态 | Attention 形状 | AKV 状态 | 当前局限 |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen2.5-1.5B | `qwen2`，稠密 | Q4_K、Q6_K `MUL_MAT` | 已核验 | D128，GQA6 | Decode 已核验；长 Prefill 满足 M>=64 时可选择 | 长 Prefill 尚缺完整模型级 RTL 周期 |
| Qwen3-1.7B | `qwen3`，稠密 | Q4_K、Q6_K `MUL_MAT` | 已核验 | D128，GQA2 | Decode 已核验；M84 tiled Prefill 已做节点级数值核验 | Qwen3-MoE 和超长上下文尚未闭环 |
| TinyLlama-1.1B | `llama`，稠密 | Q4_K、Q6_K `MUL_MAT` | 已核验 | D64，GQA8 | Decode shape 受支持并已核验 | 未单独完成长 Prefill 性能闭环 |
| SmolLM2-135M | `llama`，稠密 | Q4_K、Q5_0、Q6_K、Q8_0 `MUL_MAT` | 已核验 | D64，GQA3 | Decode 已核验 | 未单独完成长 Prefill 性能闭环 |
| Llama-3.2-1B | `llama`，稠密 | Q4_K、Q6_K `MUL_MAT` | 已核验 | D64，GQA4 | Decode shape 受支持并已核验 | 未单独完成长 Prefill 性能闭环 |
| Phi-3.5-Mini | `phi3`，稠密 | Q4_K、Q5_K、Q6_K `MUL_MAT` | 已核验 | D96，GQA1 | Decode 已核验 | 未单独完成长 Prefill 性能闭环 |
| OLMoE-1B/7B | `olmoe`，混合专家 | Q4_K、Q6_K `MUL_MAT`/`MUL_MAT_ID` | MoE 专家矩阵已核验 | D128，GQA1 | Decode shape 受支持并已核验 | 其他 MoE 拓扑和 expert 数据布局仍需逐项检查 |
| Gemma-3-1B | `gemma3`，稠密 | Q4_K、Q5_0、Q6_K、Q8_0 `MUL_MAT` | 已核验 | D256，GQA4 | 不选择 AKV，使用普通 RVV Attention | 当前 AKV 不接管 D256 |

表中出现六种 GGML architecture 名称、七个稠密模型和一个混合专家模型。它们共同说明 selector
不是按模型名工作：QBS 查看每个 weight tensor 的实际 encoding 和矩阵形状；AKV 查看每个
`FLASH_ATTN_EXT` 节点的 D、GQA、数据类型、stride、mask 和 Query 数。只要另一个模型形成相同
契约，就可复用现有硬件；只要某个条件不满足，就只回退该节点，不会让整个模型失败。

当前模型级证据可概括为：量化线性层覆盖 Q4_K、Q5_K、Q6_K、Q5_0、Q8_0 等真实 tensor，
`MUL_MAT_ID` 的 MoE 路径也已穿过 QBS；Attention 已覆盖 D64、D96、D128 和 GQA1..8 的 Decode。
Qwen3-1.7B 中，169/169 个 Q4_K 和 30/30 个 Q6_K 候选 tensor 选择 QBS，56/56 个 Decode
Attention call 选择 AKV，记录的 logits、Top-1、生成输出和节点 digest 与普通路径一致。

还必须保留两个证据边界。第一，完整模型 QEMU 中 QBS 已执行原生 custom instruction；AKV
目前通过 GGML functional reference 验证模型选择和数值，AKV 的周期来自真实数据 RTL 叶子测试。
第二，Prefill 只有在 Query 数不少于 64、上游已经采用 tiled Attention 时才进入 AKV；短 Prefill
继续使用上游算法。这是当前最终选择规则，不是运行失败。

### 6.15 一个 GGML graph 节点怎样决定走哪条路径

模型加载和每次 graph compute 的选择发生在不同时间，理解这一点可以避免把 repack coverage
误认为运行期覆盖：

```text
模型加载期，遇到 weight tensor
  -> type 是否属于九种 QBS encoding？
  -> K/row/expert layout 是否可被当前 capability 表示？
  -> 是：建立并缓存 R4 repack trait
  -> 否：保留普通 GGML/RVV trait

运行期，遇到 MUL_MAT 或 MUL_MAT_ID
  -> source activation、M/N/K、workspace、线程和 repack trait 是否完整匹配？
  -> 是：动态量化 activation，按 M/N/K 切成 qbexec
  -> 否：整项回退到原 CPU/RVV kernel

运行期，遇到 FLASH_ATTN_EXT
  -> Q/K/V/mask/output dtype 是否为 F32/F16/F16/F16/F32？
  -> batch=1、D in {64,96,128}、GQA in 1..8、stride/alignment 是否满足？
  -> scale 是否有限且为正，且无 sinks/ALiBi/softcap/ref path？
  -> mask 是否为可证明的 dense causal prefix？
  -> Decode：Query tokens 是否为 1？
  -> Prefill：Query tokens 是否至少 64，并已进入 GGML tiled algorithm？
  -> 全部满足：建立 AKV plan；否则整项走原 Flash Attention/RVV path
```

当前 GGML adapter 只由 worker 0 执行隐藏 context 命令，其他 workers 在 GGML 节点结束的既有
barrier 汇合。这避免多个 CPU worker 同时争用单一 context。选择函数必须在任何 context 状态或
输出被修改前完成全部 preflight；native 执行一旦开始后发生 fault，则按架构异常处理，不允许
在已经部分修改输出后静默重新调用 fallback。

AKV Prefill 的 64-token 门限不仅是“工作量够大才值得加速”。`GGML_FA_TILE_Q=64` 同时是上游
从短 Query `one_chunk` 数值算法切换到 tiled Attention 的边界。M33 使用 F16 Query 与逐 token
更新，而 AKV tiled path 使用 F32 Query、tile reduction 和 online merge；即便实数公式等价，FP
舍入顺序也不等价。把 M<64 返回上游是保持 numerical contract，而不是单纯调一个性能阈值。

### 6.16 换模型、上下文长度或量化文件时会发生什么

三个变化作用在不同层次：

- **换模型家族**：只要 graph 最终仍包含受支持的 `MUL_MAT`/`MUL_MAT_ID` 和
  `FLASH_ATTN_EXT` contract，RTL 不需要认识模型名称；变化主要体现在 tensor shape、D/GQA
  和算子占比。
- **换 GGUF 量化 recipe**：文件名如 Q4_K_M 只是模型级配方。每个实际 tensor type 都要独立
  绑定 profile；未支持的 tensor 自动回退，已支持的 Q4_K/Q6_K 等仍可选择 QBS。
- **换上下文长度**：QBS 的固定 projection shape 通常不随 KV 长度变化；Decode Attention 的
  K/V 工作近似随有效 KV 线性增长，AKV 用连续 64-token FULL/REFILL tiles 和 1..64 尾 tile 处理，
  不要求把最大上下文全部放入 SRAM。上下文变长会改变端到端时间占比，但不会自动使合法 shape
  失效。
- **换 prompt 长度**：短 Prefill 保留上游 `one_chunk`；达到 64 tokens 后，AKV 按固定 64-Query
  软件 block 消费 resident K/V tiles。隐藏硬件容量保持有界，模型输出和软件 workspace 按问题
  shape 管理。

因此当前机制对模型和上下文的可迁移性来自**有界 tile + runtime selection + fallback**，不是靠
为某个固定序列长度分配同等大小的片上缓存。性能是否仍有收益则要重新看 QBS/AKV 实际执行占比、
tile tail、外部带宽和 RVV 算术瓶颈。

### 6.17 拿到一个新 GGUF 时，怎样独立判断支持程度

不要先问“这个模型是不是 Llama/Qwen”，而应从 graph 中的每个候选节点向下检查。模型名称只帮助
预测 topology；真正决定执行路径的是 operator、tensor encoding、shape、layout 和 capability。
可以按下面四步完成一次可审计的判定。

**第一步：区分模型级配方与逐 tensor encoding。** 文件名中的 `Q4_K_M` 表示量化 recipe，不表示
所有矩阵都是 Q4_K。应从加载后的 tensor metadata 统计每个 `MUL_MAT`/`MUL_MAT_ID` weight 的实际
`ggml_type`。只有 Q2_K、Q3_K、Q4_K、Q5_K、Q6_K、Q4_0、Q5_0、Q8_0 和 IQ4_NL 才能映射到
当前 QBS profile；其余 tensor 继续使用原 GGML/RVV kernel。

**第二步：检查 QBS 的完整命令契约。** 对每个候选量化矩阵依次确认：

1. activation 能否按配对要求量化为 Q8_K 或 Q8_0；
2. weight 能否在加载期形成当前 capability 接受的 ROW_MAJOR/R4 layout；
3. K 能否按 native block 对齐，过长 K 是否可由软件按原数值顺序分段；
4. M/N tail 能否拆成合法 microtile；默认路径是否保持 M1--M4，显式 wide-M 策略是否通过精确流量判定；
5. destination group、descriptor 地址和 payload 地址是否满足对齐；
6. `qbinfo` 返回的 architecture、descriptor、profile、layout 和 shape 能力是否全部匹配。

只有以上条件在产生 side effect 前全部成立，运行时才应选择 QBS。之后还要用
`candidate/executed/fallback`、原生命令数和 dot-element 守恒证明它确实执行，不能只用“模型正常
输出”推断快路径被采用。

**第三步：独立检查 AKV，而不是从 QBS 命中推断 Attention 命中。** 对每个
`FLASH_ATTN_EXT` 节点检查：

1. Q/K/V/mask/output 是否为当前 F32/F16/F16/F16/F32 contract；
2. batch 是否为 1，D 是否属于 64/96/128，GQA 是否在 1..8；
3. scale 是否有限且为正，stride、32 B K/V 对齐和 destination group 是否规则；
4. 是否没有 reference path、attention sinks、ALiBi、softcap 等未支持 feature；
5. mask 是否可证明为有限 causal prefix 后接 `-inf`，而不是任意稀疏 mask；
6. Decode 是否为单 Query；Prefill 是否达到 64 Query，并已进入 GGML tiled Attention。

上下文长度本身不是 capability 常量。合法 D/GQA 的 Decode 可把任意较长历史拆成连续 64-token
K/V tiles；最后 1..64 token 作为 tail。上下文越长，AKV 能避免的重复 K/V traffic 可能越多，但
RVV QK/PV 算术也线性增加，所以仍需用实际周期判断收益。

**第四步：把结论写成分层覆盖，而不是一个布尔值。** 推荐至少报告：

| 覆盖层 | 应回答的问题 | 最低证据 |
| --- | --- | --- |
| 功能兼容 | 未支持节点能否继续运行 | fallback 输出与原 RVV 一致 |
| QBS 覆盖 | 哪些量化 projection 真正执行专用命令 | 逐 type/shape selector counter、native command 和数值守恒 |
| AKV 覆盖 | 哪些 Decode/Prefill Attention 真正使用 context/view | executed/fallback reason、tile/pair/MAC counter 和输出比较 |
| 性能覆盖 | 快路径是否降低代表性工作量的周期 | 同数据、同算法边界的 RTL baseline 对比 |
| 模型质量 | 局部浮点差异是否影响模型行为 | logits、KL、PPL、Top-k 与生成检查 |

三个例子可以帮助建立直觉：

- **Qwen3-1.7B Q4_K_M**：实际 projection 中的 Q4_K/Q6_K 可走 QBS；D128/GQA2 Decode 可走
  AKV；短 M33 Prefill 因上游仍用 `one_chunk` 回退，M84 已进入 tiled algorithm，因而可选择
  AKV。这里同一模型内部同时存在执行和回退，不矛盾。
- **Gemma-3-1B**：支持的 Q4_K/Q5_0/Q6_K/Q8_0 projection 仍可走 QBS；D256 Attention 即使
  directed RTL 功能正确，也因当前分段数据流慢于强 tiled-RVV 而回退。QBS 命中不意味着 AKV
  也必须命中。
- **F16/BF16 非量化模型**：没有当前 QBS weight profile，因此线性层走普通 RVV；若其
  `FLASH_ATTN_EXT` 满足 D/GQA/type/mask 契约，Attention 仍可独立使用 AKV。反过来，一个使用
  支持量化格式但带 ALiBi 的模型可以使用 QBS，同时让 Attention 回退。

这套方法说明“模型通用性”的来源：两条快路径在 graph 节点处独立选择，普通 RVV 始终承接剩余
工作。增加新模型通常先扩充软件 mapping 和证据；只有出现现有 profile 无法表达的新 block 数学，
或 D/feature 无法由当前 AKV view 表达时，才需要改变硬件 contract。

## 7. QBS/AKV 如何接入 lane-based RVV 后端

### 7.1 既有 RVV 数据通路和接入位置

当前处理器是 RVV 1.0 lane-based vector processor。dispatcher 解码指令并维护 vector CSR；
sequencer 分配 `vid`、跟踪源/目的寄存器和功能单元完成；lanes 保存分片 VRF 并执行整数/FPU
操作；VLSU 负责地址生成、MMU/PMA、AXI load/store 与 load-result 写回；SLDU/MASKU 处理跨 lane
和 mask 类操作。

QBS/AKV 没有旁路这套系统。两者都在 dispatcher/sequencer 可见的 vector request 边界进入 VLSU
资源域，所以 custom command 仍具有：

- 明确的源/目的 GPR 或 vector register group；
- sequencer 分配的 `vid` 和正常 destination hazard；
- 与普通 load 一致的 result-port backpressure；
- success/fault terminal、异常原因和程序顺序；
- 未选择快路径时完全不变的标准 RVV 实现。

### 7.2 Dispatcher：把指令编码翻译成可调度请求

dispatcher 对无隐藏状态的查询和长操作采用不同处理：

- `qbinfo`/`akvinfo`：组合查询 capability，直接返回 scalar `rd`，不分配长时延 `vid`；
- `qbexec`：生成内部 `VQBEXEC`，按 M 将目的组设为 LMUL1/2/4/8，并合成 e32 的虚拟 `vl`；
- AKV FULL/REFILL/RELEASE：生成内部 `VAKVFILL`/`VAKVRELEASE`，作为阻塞 load-like 请求；
- AKV row/column/panel load：生成内部 `VAKVLOAD`，按 D 或 panel width 预留 e16 的 LMUL1/2/4 目的组。

必须在 dispatcher 完成的检查包括 opcode reserved bits、`vstart=0`、accelerator-consistent mode、
descriptor alignment 和目的寄存器组对齐。原因是目的组必须在 descriptor 尚未读取时就交给
sequencer；不能等 hidden engine 发现 M/D 后才回头扩大 hazard reservation。

`qbexec` 和会替换 context 的 AKV FULL/REFILL/RELEASE 只有在更老 vector work 排空后才进入，
避免长命令改变隐藏状态时仍有旧请求访问共享接口。合法 AKV local view load 不改变 context，
可以与非访存 RVV 算术形成重叠，但仍受 VLSU/result port 所有权和目的寄存器 hazard 约束。

### 7.3 Sequencer：让 custom command 留在正常完成域

sequencer 将 `VQBEXEC`、`VAKVFILL`、`VAKVLOAD` 和 `VAKVRELEASE` 归入 load-like 功能单元类别，
为其分配 `vid` 并维护目的寄存器占用。QBS 的 FP exception flags 在成功 terminal 时沿既有响应
路径合并；fault terminal 则返回 load/illegal-instruction 语义对应的异常。

QBS 的 `vid` 一直保留到完整 tile 原子 commit 或 fault。AKV fill/refill/release 也一直阻塞到
terminal。AKV local row/column load 有一个更细的两级完成：

1. engine 接受并验证本地 load 后可产生 **early acknowledgement**，让 scalar-side accelerator
   handshake 不必等所有 VRF words 写完；
2. 该向量请求的 `vid` 仍然在飞，只有 replay 经所有 lane grants 完成并产生 terminal 后，
   `load_complete` 才释放 destination hazard。

所以“早确认”只缩短 request 接口占用，不是让年轻指令提前读到半个向量。将握手完成与向量结果
完成分开，是局部 context load 能与 RVV 算术组合而又不破坏寄存器正确性的关键。

### 7.4 VLSU：QBS、AKV 与普通访存的单一所有权

VLSU 显式维护 `qbs_active_q` 和 `akv_active_q`，并以 `normal_vlsu_idle` 检查 address generator、
load/store unit、AXI pipeline 和 result port 已排空。接受条件保证同一周期只有一种 owner：

```text
normal VLSU owner  xor  QBS owner  xor  AKV owner
```

owner 生效后，VLSU 分别复用和仲裁：

- MMU translation request/response；
- physical-range/PMA 检查；
- AXI AR/R read channel；
- LDU lane-result request、byte enable、data 和 final grant；
- terminal acknowledgement、异常和 `vid` completion。

QBS 和 AKV 都只读外部 memory，不驱动 AXI write。QBS 读取 descriptor/weight/activation 并在最后
提交 FP32 result；AKV FULL/REFILL 读取 descriptor/Q/K/V，local view command 则只从 context
重放 F16 数据。RTL assertions 检查 owner 互斥、读写方向、terminal 唯一性和 result `vid` 对齐。

sequencer 可能在 WAIT 状态保持同一个 level-valid PE request 穿过 engine terminal。VLSU 因此记录
该 held request 是否已经 fire，在上游撤销 valid 前禁止把同一请求接受第二次；同时 assertion 要求
held request 的所有字段保持稳定。这个细节防止一条 AKV 指令因“engine 已空闲但上游 valid 尚未
拉低”而重复执行。

### 7.5 为什么结果必须回到普通 VRF

QBS 若直接写 GGML memory，会绕开 vector-register dependency、完成和异常边界；AKV 若让 RVV
算术直接读取一个私有端口，又会引入第二套 operand network。当前设计统一收口为：

```text
QBS hidden accumulator --fault-free commit--+
                                              +-> existing LDU result ports
AKV hidden context ------validated replay----+-> lane VRF -> ordinary RVV consumer/store
```

因此 QBS 输出可以被后续 RVV store/elementwise 指令消费，AKV 的 row/column/panel view 可以被普通
RVV widening FMA/reduction 消费。操作系统可见的计算结果仍在标准 vector state 中；hidden context
只是有界、显式创建和释放的加速状态，不替代 VRF。

QBS 的“原子”表示任何 VRF 写回开始前，全部潜在 fault 访问和计算已完成；真正写回仍会跨多个
cycle，年轻消费者靠 sequencer completion gating 看不到部分结果。AKV local replay 已没有 payload
memory fault，但仍在第一个 write 前验证 context、selector 和 destination，并依靠同一 completion
gating 阻止部分向量被消费。两条路径的代价都是 result-port/VRF grant 可能成为 backpressure，
因此必须用对应 counter 判断，而不能假定“片上数据一定一周期可用”。

### 7.6 哪些硬件被复用，哪些逻辑是新增的

“复用 RVV 后端”不表示 QBS/AKV 没有新增硬件，也不表示把 custom instruction 翻译成一串普通
RVV 指令。准确边界如下：

| 层次 | 直接复用的既有 RVV 机制 | QBS 新增逻辑 | AKV 新增逻辑 | 为什么这样划分 |
| --- | --- | --- | --- | --- |
| CVA6-Ara 接口 | accelerator request/response、GPR source tracking、异常返回 | 识别 `qbexec/qbinfo` 的 source/destination 属性 | 识别 fill/load/info/release 的 source/destination 属性 | 让标量核仍按一条有依赖、有完成的指令观察命令 |
| Dispatcher | RVV CSR 检查、请求构造、等待/响应状态 | 从 M 合成 e32 LMUL/VL，检查 `vd`、地址和 reserved bits | 从 D/panel 合成 e16 LMUL/VL，检查 selector 类别和目的组 | descriptor 尚未读取时就必须确定要保留哪些 VRF 寄存器 |
| Sequencer | `vid` 分配、read/write list、destination hazard、功能单元完成 | `VQBEXEC` 作为 load-like 长请求保持到 tile terminal | fill/release 保持到 terminal；local view 保持到所有 VRF writes 完成 | 不建立第二套乱序、scoreboard 或退休规则 |
| VLSU 前端 | normal request 生命周期、load completion 与异常映射 | QBS owner 和 active-request latch | AKV owner 和 active-request latch | 三种 owner 共享接口但必须有唯一 fault/result 归属 |
| 地址与内存 | MMU translation、PMA/range check、AXI AR/R、page/burst 切分 | descriptor/weight/activation range scheduler | descriptor/Q/K/V range scheduler | 继续继承系统地址保护和 memory ordering，不建立旁路 DMA 地址空间 |
| 量化计算 | 不直接复用 lane ALU 执行逐项 unpack/dot | profile decoder、32-pair integer dot、FP update table、hidden accumulator | 无 | QBS 要消除的正是普通 RVV 中反复出现的 unpack/reduction 指令流 |
| Attention 计算 | lane VRF、integer/FPU、widening FMA、reduction、mask/SLDU | 无 | 无新的 QK、Softmax 或 PV 算术单元 | AKV 只改变 K/V 供给和 view，数值算法继续由 RVV 表达 |
| 片上状态 | architectural VRF 和现有 lane storage | command-local block buffers、FP accumulators、可选 Q8 activation context | Query row store、64-token K/V banks、committed metadata | 只保存可由显式命令创建、使用和释放的有界状态 |
| 结果路径 | LDU lane-result request/grant、VRF byte enable、`vid` completion | fault-free FP32 tile commit | validated F16 row/column replay | 后续普通 RVV 指令可直接消费，不增加私有 operand network |
| Fallback | 原有 GGML scalar/RVV kernels | profile/shape/capability 不匹配时不发 `qbexec` | Attention contract 不匹配时不发 AKV 命令 | 普通 RVV 功能不依赖专用机制是否开启 |

从一条指令的物理路径看，可以把复用关系记成：

```text
QBS:
custom decode -> normal sequencer/vid -> shared MMU+AXI
              -> new quant decode/dot/FP state -> shared LDU result -> VRF

AKV fill:
custom decode -> normal sequencer/vid -> shared MMU+AXI
              -> new Query/K/V context -> terminal

AKV local view:
custom decode -> normal sequencer/vid -> new context row/column read
              -> shared LDU result -> VRF -> ordinary RVV Attention arithmetic
```

这里最关键的界线是：QBS 新增了量化块算术，因为标准 lane 指令流正是它要压缩的对象；AKV 没有
新增 Attention 算术，因为现有 RVV lanes 已能高效表达 F16/F32 FMA、mask 和 reduction，真正缺口是
K/V 的驻留与访问方向。两者都复用地址保护、顺序、异常和 VRF 可见状态，所以关闭
`ARA_QBS_ENABLE`、`ARA_AKV_ENABLE` 或 `ARA_AKV_V2_ENABLE` 后，标准 RVV 数据通路仍保持原有功能。

## 8. QBS/AKV 命令的完整生命周期

### 8.1 一条 `qbexec` 怎样完成量化 microtile

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

### 8.2 一个 AKV Decode tile 怎样被消费

以 D128、GQA6、当前有效 KV=128 为例，一个 KV head 对应六个 Query heads，KV 被拆为两个
64-token tiles。软件和硬件的协作过程是：

1. **Selector preflight**：GGML 检查 F32 Q、F16 K/V/mask、F32 output、batch1、D128/GQA6、
   contiguous/regular strides、32 B K/V 对齐、finite positive scale 和 dense prefix mask。
2. **Query preparation**：软件把该 KV head 对应的六行 Query 转成 descriptor 所需的有界 F16
   seed；具体 QK helper 可按 shape 使用 F16 或原始 F32 Query，不把 descriptor seed 自动等同于
   算术输入精度。
3. **FULL**：读取 64 B descriptor、六行 Q seed，以及 token 0..63 的 K/V；只有所有 range
   成功后 context 才 ready。
4. **K column views**：对 D 维逐列或四列 panel 发 local command。八个 token banks 每个 bank
   取一组 token，形成长度 64 的 token-axis K vector，写入普通 VRF。
5. **QK/Softmax**：标准 RVV 对同一个 K column 更新六个 score accumulators，再执行 scale、mask、
   max/sum reduction 和稳定 online Softmax 状态更新。
6. **V row views**：每个有效 token 的 V row 只重放一次，标准 RVV 用该 token 的 Softmax weight
   更新六个 D128 output numerators。
7. **REFILL**：第二个 tile 仅替换 K/V，继续合并 online Softmax 状态；尾 tile 用显式
   `tile_count` 屏蔽无效 token，不依赖 SRAM 中的旧值恰好为零。
8. **RELEASE/normalize**：最后一个 tile 后释放 context，软件/RVV 用最终 denominator 归一化输出。

这个数据流的关键不是 34 KiB context 本身，而是**同一列 K 被所有 GQA Query rows 复用，同一行 V
也只为这一组 Query 重放一次**。只增加 SRAM 容量而不提供这种读取方向，仍会留下重复的数据整理、
Query 装载和 reduction。

### 8.3 AKV Prefill 为什么还需要软件 Query block

Prefill 有多个 Query tokens。若把全部 prompt Q/K/V 放进隐藏状态，硬件容量会随上下文增长，既
不通用也不利于综合。当前方案固定一个 64-Query **软件 block** 和一个 64-token **硬件 K/V tile**：

```text
for each KV head:
  for each Query block QB <= 64:
    initialize max/sum/output state for QB
    for each visible K/V tile <= 64:
      FULL for first tile, REFILL for later tiles
      for each Query token in QB that can see this tile:
        RVV QK -> causal mask -> online Softmax -> RVV PV
    RELEASE and normalize QB outputs
```

不同 Query token 的 causal prefix 不同，软件用 `past_tokens + query_index + 1` 计算本行可见 token，
未来 token 不参与 QK、denominator 或 PV。每个 tile 使用稳定 online Softmax：

```text
m_new = max(m_old, max(score_tile))
a     = exp(m_old - m_new)
w_j   = exp(score_j - m_new)
l_new = a*l_old + sum(w_j)
o_new = a*o_old + sum(w_j*V_j)
```

`m/l/o` 在 tile 间保持 F32；tile 内 denominator reduction 按当前 GGML/RVV 契约用 F64 widening
求和，再舍入回 F32 状态。这只是标准 RVV 的数值调度，不是 AKV 新增 FP64 Attention 单元。
固定 workspace 为 137,472 B，不随总 prompt/KV 长度增长；输出 tensor 作为正常软件可见数据按
实际 shape 增长。该方案用多次有界 tile 覆盖长上下文，避免把“支持 40K context”错误理解为
必须在 AKV SRAM 中放下 40K 条 K/V。

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

它保存 command id、vd、M、descriptor/activation 地址和 cache/prot 属性；调度 logical
read ranges；连接 compute 和 commit；保存 fault attribution；导出互斥 phase counter。

图中的直接 `FAULT` 不表示忽略在途 AXI response：`qbs_read_engine.sv` 只有在自身 burst FIFO 已
排空后才向顶层报告 fault。`COMPUTE_FAULT_DRAIN` 专门处理已经进入整数/FP pipeline 的 payload
工作，不用于尚未启动 compute 的 descriptor/validation fault。

当前 M=1 且 R4 layout 时启用同 K block、下一 4-row microtile 的 weight lookahead。注释和逻辑
明确限制在该形态，因为 M>1 的 compute interval 与返回时机不同，未经额外 bank 生命周期保护，
过早发第三个 response 可能覆盖仍在消费的 bank。K block 边界不会保留可被下一块误认的 bank。

descriptor v2 还使该状态机承担 activation context 的事务边界。`FILL` 在 validation 后开始旁路
写 context，`REUSE/RELEASE` 先做 token/metadata lookup 再启动 compute；只有 `COMMIT` 完成后
才分别发布新 context 或释放旧 context。payload fault 进入 `COMPUTE_FAULT_DRAIN` 时触发 fill
abort，因此失败命令留下的 SRAM bytes 永远不会被标成 valid。

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

这里的 `M` 需要再分成“命令几何”和“物理计算 wave”两个概念。M1--M4 命令只执行一个
context wave，`wave_m=M`、`context_base=0`。M5--M8 命令则在同一个 weight tile 上顺序执行
两个 wave：第一个固定处理 context 0--3，第二个处理 context 4--`M-1`。第二个 wave 的
`wave_m=M-4`，因此 M5 只在第二个 wave 使用一个 context，M8 才使用四个。只有第二个 wave
完成后，状态机才允许切换 weight bank、推进 N tile 或进入下一个 K block。这样扩大了同一份
weight 的生命周期和复用范围，却没有把整数乘法阵列复制为八 context；代价是每个 weight tile
需要两轮顺序计算。

### 9.6 `qbs_profile_decoder.sv`：格式位级语义

这是支持多格式的关键组合模块。它按 `profile` 和当前 element/group：

- 从 low/high plane、mask、nibble 或 IQ table 得到 signed weight quant；
- 读取 activation int8；
- 解 subgroup scale/min；
- 对 affine profile 读取相应 Q8_K `bsums`；
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

dot array 每次只接收一个 `wave_m=1..4` 的物理 wave。`wave_m` 改变每个 row cluster 的并行分配：

- M=1：每行 8 pair，形成一个 8 项和；
- M=2：每个 activation row 4 pair；
- M=3/4：每个 activation row 2 pair。

M5--M8 命令不把 `5..8` 直接送入 dot array，而是由 compute engine 拆成 `4 + (M-4)` 两个
wave。两个 wave 读取不同的 activation bank，但保留同一个 active weight bank；第二个 wave
通过 `context_base=4` 把结果送到 logical context 4--7。因而物理 pair capacity 始终固定，命令
几何只改变 pair 在 output row、activation row 和时间上的分配。balanced reduction tree 避免
综合成串行加法链。

### 9.8 `qbs_profile_engine_int.sv`：整数流水与结果整形

该模块包含两个内部流水槽位和 16 个 logical streams（4 weight rows x 4 activation rows）。
它将 decoder 输出送入 dot array，按 subgroup 累计 partial dot，再应用 integer scale/min：

```text
subtotal_dot += group_scale * group_dot
subtotal_aux += group_min   * group_aux
```

完成一个 native block 后，它以 round-robin 方式把每个有效 stream 的 `dot/aux/d/dmin` 送给
FP accumulator。两 context 的作用是吸收 decode、dot reduction 和 FP consumer 之间的速率差，
不是对两条 architectural commands 做乱序。

### 9.9 `qbs_fp_accumulator.sv`：共享 FP32 update pipeline

当前命令最多有 128 个有效 FP32 accumulators，对应两种合法上界：窄几何 `4*32` 或宽几何
`8*16`。物理上统一按 8 bank x 16 row 组织，另有 16-entry FP update table。窄几何中逻辑索引为
`context*32 + output_row`；宽几何中逻辑索引为 `context*16 + output_row`。compute engine 将第二个
wide wave 的 `context_base=4` 加到 stream 内 context 后再形成索引，因此两个 wave 更新同一条
命令中互不重叠的 accumulator 区域，而不是覆盖第一轮结果。每个 table entry 保存 accumulator
index、profile、dot/aux、scale 和中间 FP 值；所有 FP primitive 直接使用 ABI 生成的固定 RNE
常量，不保存每请求 rounding mode。

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
- 窄 M1--M4 命令对每个有效 context 写满一个 architectural vector register，`element >= N` 的
  inactive output 写零；
- 宽 M5--M8 命令只对每个 context 的前 N 个 FP32 元素置 byte enable，保留同一寄存器的尾部；
- 两种模式都只修改前 M 个 destination registers，保留对齐寄存器组中的其他寄存器。

这里一次“word”是四条 lane 各一个 64-bit word 组成的 256-bit aggregate group，共承载八个
FP32 元素，不是整个 VLEN-bit register 同周期写入。当前计数器 `commit_word_count` 在本组所有
active lanes 均收到 request grant 和 final grant 后加一，日志字段仍沿用 `commit_groups`。窄模式
每个 context 的 group 数为 `VLEN/256`，总数为 `M*(VLEN/256)`；宽模式每个 context 的 group 数为
`ceil(N/8)`，总数为 `M*ceil(N/8)`，当前 N 上限 16，所以每个 context 只需一组或两组。每个 active
element 在 commit 前都必须已有 valid accumulator。VRF grant 不足时状态机停在当前 group，并
计入 backpressure。

当前 implementation mapping 由 RTL assertion 明确限制为 4 lanes、128-bit AXI read data，以及 256--1024-bit、
按 256-bit 整除的 VLEN。结合 RVV 的 VLEN 约束，本项目实际使用 1024-bit VLEN；这些是当前实现
边界，不是 profile/layout/shape ABI 本身天然要求的通用限制。

### 9.11 `qbs_activation_context.sv`：显式 Q8_K snapshot

该模块保存一个 `M=1`、Q8_K、row-major activation context，最多 16 个 K blocks：

```text
16 * 292 B = 4,672 B logical payload
```

Q8_K block 的 292 B 不是 16 B 的整数倍，因此相邻 block 会在 128-bit row 中产生旋转。模块按
32-bit word steering，将相邻偶/奇 128-bit rows 放入两个单端口 banks；一个对齐到 4 B、长度最多
16 B 的 fill/replay beat 即使跨 row，也可同时访问两个 bank。generic 仿真使用两个 128-bit SRAM
banks；目标宏映射中每个 parity bank 使用两个 64x256 macros，共四个 macros。

控制上，它分别保存 committed metadata 和 in-progress fill metadata。`fill_begin` 先清旧 valid，
每个完成的 K block 置一位 completion bitmap；只有声明范围内所有 completion bits 均为 1，
`fill_ready_to_commit` 才成立。成功 command commit 复制 ID、8-bit generation、profile、layout、M
和 K-block 数并置 valid；abort/reset 清除进行中状态。lookup 逐字段比较，明确区分 invalid context、
stale generation 和 metadata mismatch。

`REUSE/RELEASE` 每次从指定 K block 重放 19 个 beats：18 个 16 B beat 加最后一个 4 B beat，数据
重新进入原 block adapter。后面的 profile decode、dot、FP update 和 result commit 与 DIRECT 完全
相同，因此 context 只改变 activation 来源，不复制第二套算术逻辑。

### 9.12 `akv_engine.sv`：Attention context 命令控制器

AKV engine 的状态机为：

```text
IDLE -> DESCRIPTOR_REQUEST -> DESCRIPTOR_WAIT -> VALIDATE -> PAYLOAD -> SUCCESS
IDLE -> COLUMN_GATHER -> REPLAY_WRITE -> SUCCESS
IDLE -> REPLAY_READ -> REPLAY_WRITE -> SUCCESS
any checked stage -> FAULT
```

FULL 从 64 B descriptor 开始，validation 后按 Q/K/V role 生成 logical ranges；REFILL 复用已保存
metadata，只读取新 K/V tile。PAYLOAD complete 后才发布 context ready。row load 先读相应 SRAM
word，column load 先由 token-bank context 聚合数据，再共同通过 REPLAY_WRITE 向所有 lanes 提交。
每个 lane 的 request accepted 与 final grant 均被逐位跟踪，最后一个 word 全部完成后才能 terminal。

engine 同时保存 active command、`vid`、`vd`、tile start/count、descriptor metadata 和 fault
attribution。命令计数、external bytes、replay bytes、bank cycles、conflict/reject 以及 read-engine
计数都在真实 handshake 上更新，不把计划值冒充已发生的事务。

### 9.13 `akv_context.sv`：保存当前 Query group

这个模块的 RTL 阵列为 8 条 Q、8 条 K 和 8 条 V 各保留一个最大 D128 的 256 B slot，共：

```text
(8 + 8 + 8) * 128 * 2 B = 6,144 B
```

当前 token-axis AKV 只使用其中最多 8 条 Q slot；64-token K/V 由下一节的 token-bank 模块保存。
每个 slot 包含八个 256-bit logical rows。相邻 logical row 分到两个 banks，使任意 F16 对齐的
128-bit AXI beat 即使跨 32 B row，也能拆成两个不同 bank 的写。为避免在关键路径上综合一个
不可达的 byte-granular barrel shifter，写 steering 只按 halfword 对齐移动；这是 descriptor 已
验证 F16 对齐后的硬件化约束。row replay 一次读取 256 bits，再由 AKV engine 按 lane result
word 写入 VRF。

Query 使用 row view 是自然的：一条 Query 本来就是沿 head dimension 连续的 D 个元素，RVV
需要完整 row 参与后续 column/panel 点积。K 则需要沿 token 方向读取，因此使用不同的物理组织。

### 9.14 `akv_v2_context.sv`：当前 64-token、8-bank K/V 存储

该模块把 token index 的低 3 bits 作为 bank，较高 bits 作为 token group；每个 bank分别保存 K/V
stream 的 256-bit D-axis words。一个完整 ready context 的逻辑数据量为：

```text
(8 Query seed rows + 64 K rows + 64 V rows) * 128 * 2 B
= 34,816 B
```

公式中的 8 条 Query **不在** `akv_v2_context.sv` 内，而是写入 `akv_context.sv` 的 Q slots；
只有 K/V payload 写入 `akv_v2_context.sv`。因此当前物理组织是：

- `akv_context.sv`：保存最多 8 条 Q row；
- `akv_v2_context.sv`：保存 64 K + 64 V，共 32 KiB logical K/V payload；
- `akv_engine.sv`：保存 descriptor metadata、tile start/count、ready 属性和 replay 控制，不保存
  Query payload 本身。

目标宏映射中，K/V 有八个 token banks，每 bank 两个 64x256 macros，共 16 个 macros；Query
row store 使用四个 64x256 macros。20 个 macros 的原始容量为 40 KiB，其中 Query row store
存在 padding 和当前未使用的 K/V slot；所以“有效逻辑 context 为 34,816 B”和“集成实现配置
40 KiB SRAM macro capacity”同时成立。前者描述当前命令有效数据，后者描述物理阵列容量，二者
都不是综合网表面积结论。

同一份 row-major K/V 写入可提供两种局部 view：

- **row view**：选择一个 token bank 和 token group，连续读取 D-axis words，适合 V 聚合；
- **column view**：八个 banks 同周期读取同一 dimension 所在 word，抽取对应 F16 element，跨
  1..8 个 token groups 拼成最多 64-token vector，适合 QK；
- **panel4 view**：一次命令收集连续四个 dimensions，返回四个 1024-bit column payload，减少
  command/dispatch 开销，输出映射到 e16/m4。

tail tile 由 `column_token_count` 控制 group 数和有效元素，不读取不存在的 token。写、row read、
column start/active 互斥；`conflict_o` 和 assertions 检查任何重叠请求。token banking 的意义是让
数据按模型原生 row-major 方式填充，又在消费时得到 column view，不在软件或 fill 阶段先做 K
transpose。

### 9.15 顶层接线模块各自负责什么

- `cva6_accel_first_pass_decoder.sv`：只识别 custom-2 指令使用哪些 scalar source/destination，
  让 CVA6 正确保留依赖和 load-like 计数；不解释 descriptor。
- `ara_dispatcher.sv`：完成 opcode、reserved field、目的寄存器组、`vstart` 与 capability legality，
  生成 `VQBEXEC/VAKVFILL/VAKVLOAD/VAKVRELEASE`。
- `ara_sequencer.sv`：分配 `vid`、保留 destination hazard、等待功能单元完成/异常；不访问 context
  SRAM，也不重算 profile。
- `vlsu.sv`：选择 normal/QBS/AKV owner，复用 MMU/AXI/result port，锁存 active request，并把
  terminal 映射回正常 load completion。
- `ara_pkg.sv` 与 `ara_typedef.svh`：定义新增 operation 和随请求传播的 AKV refill/v2/column 元数据。
- `ara.sv`：把这些字段、QBS `fflags` 和 VLSU completion 接到既有 dispatcher/sequencer/lane 域；
  不解释模型名称，也不承担 GGML 选择策略。

这种职责划分保证格式数学留在 QBS profile path，Attention 数据视图留在 AKV，体系结构顺序留在
dispatcher/sequencer，外部存储保护留在 VLSU/MMU。定位问题时应先判断属于哪一层，再选择 probe，
而不是从最终 mismatch 同时修改四层逻辑。

## 10. 正确性、内存顺序和异常

### 10.1 两种原子边界：结果提交与 context 发布

QBS 一条命令会产生 M x N 个输出。如果边计算边写 VRF，后续 weight page fault 可能让一部分
结果可见、一部分不可见，难以符合单条指令的异常模型。当前设计将 FP32 accumulators 保持为
隐藏状态，直到：

- descriptor 和全部 payload 访问成功；
- read outstanding 排空；
- profile/dot/FP pipelines 排空；
- 所有 active accumulators valid。

之后才进入 commit。因此 fault command 的 destination 不应出现部分更新。

AKV 的原子边界不同。FULL/REFILL 的目标不是立即产生 Attention 结果，而是建立一份隐藏数据
快照。payload 可以逐 beat 写入 SRAM，但 `context_ready` 只有在 descriptor 合法、全部 logical
range 完成、outstanding read 排空且未见 fault 后才发布：

```text
QBS: hidden accumulators --all work succeeds--> commit complete VRF result
AKV: speculative SRAM bytes --all fills succeed--> publish one READY context
```

FULL 被接受时旧 context 立即失效，防止 local load 读到“旧 metadata + 新 payload”；REFILL
期间也暂时不可读。任一 descriptor、translation、PMA、AXI response、protocol 或 payload fault
都使整份 context invalid，软件必须重新 FULL，不能把旧 tile 与新 tile 拼接。相反，READY 状态下
一个非法 local selector 在第一个 lane-result request 前被拒绝，既不修改 VRF，也不破坏已提交
context。两种机制都把多周期内部过程压缩成清楚的软件可见状态转换，但提交对象不同。

### 10.2 内存访问属性

QBS 与 AKV 都只产生 read request。QBS 的 descriptor/weight/activation，AKV 的 descriptor/Q/K/V
都通过同一 MMU、physical-range check 和 AXI read path。logical range 会先按 4 KiB page 和 AXI
最大 burst 边界切分；当前 PMA 门控要求每个翻译后的完整 AXI burst 落在同一 cacheable、
idempotent region，且不与 non-idempotent region 相交。非幂等 MMIO 或跨越不允许区域的子请求
以 load-access fault 结束，而不会把长 stream 投向有副作用的设备地址。

软件 wrapper 在命令前执行 `fence rw,rw`，保证先前写入 descriptor、activation、repacked weight
或 Q/K/V buffer 的数据在专用 read master 观察前可见。成功 AKV fill 具有 snapshot semantics：
之后软件即使改写原 Q/K/V memory，也不会自动更新 hidden context；要观察新数据必须显式 REFILL
或 FULL。AKV/QBS 不自行增加 CVA6 private cache 与 vector AXI master 之间的 coherence，仍继承
平台原有一致性和 cache-maintenance 责任。

命令期间普通 VLSU 被阻塞，避免 normal、QBS 与 AKV 三套 request source 竞争同一外部接口。
这是当前保守的互斥策略，不表示 ISA 契约永远禁止未来的多 owner overlap；若将来放宽，必须先
定义 translation response、AXI ID、fault attribution、result port 和 memory ordering 的独立归属。

### 10.3 Fault 分类

QBS/AKV read path 内部区分：

- descriptor validation fault；
- request planning fault；
- MMU translation fault；
- PMA/physical range fault；
- AXI response fault；
- AXI protocol fault，例如错误 RLAST。

fault attribution 记录 fault kind、虚拟地址和 MMU exception。translation fault 保留 MMU cause
并报告检测到的虚拟地址；PMA、AXI response 和 protocol fault 归为 load-access fault。descriptor
字段、reserved bits、context 状态、selector、destination alignment 等本地 contract 错误归为
illegal instruction，并要求在任何外部 payload 或 VRF side effect 前发现。内部详细分类未全部
作为软件 ABI 暴露，但对验证和定位至关重要。

### 10.4 当前恢复边界

QBS 与 AKV fill 都是阻塞的长命令，不实现 RVV 那种按 element `vstart` 精确重启。QEMU/dispatcher
检查 `vstart` 和所需 vector/FP state，非法状态拒绝命令。当前恢复策略是 fault 后由软件重新执行
完整操作，而不是从某个 K block、token 或 AXI beat 继续。

这还带来操作系统责任：hidden context 虽非普通 architectural vector register，却可能含有进程
私有 activation 或 K/V 数据。当前 bare-metal contract 依赖 reset/release；若进入多进程系统，
context switch、保护域切换、debug kill 和 interrupt policy 必须至少使 context invalid，或者定义
完整 save/restore ABI。仅保存 engine FSM 而不保存 SRAM、metadata 和 outstanding attribution
不能实现正确恢复。

### 10.5 AKV 为什么不改变 Attention 数值规则

AKV fill/load 只搬运 F16 payload bits，不做乘法、指数、比较或归约。因此它不依赖动态 `frm`，
不设置 `fflags`，也不能把 NaN canonicalize、把 subnormal flush 为零。local view 返回的有效 F16
元素必须与成功 fill 的源 bytes bit-identical；token banking 和 column gather 只改变观察顺序。

QK、scale、mask、max/sum、exp、online merge、PV 和最终 normalization 均由普通 RVV kernel
定义其 FP 舍入与操作顺序。这里必须区分**数学公式相同**和**浮点算法相同**：短 Query 的 GGML
`one_chunk` 与 tiled Attention 即使计算同一实数公式，也可能因 F16/F32 Query、归约树和 merge
顺序不同而产生 ULP 差异。当前 M<64 回退正是为了与 GGML 算法边界一致，而不是把差异藏进更宽
tolerance。AKV 的正确性由“payload bit-exact + 被选 RVV 算法 contract”共同构成。

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

### 11.3 R4/M4/M8 layout 与请求粒度

R4 使四个 output rows 的同一 K block 连续，M4 使四个 activation rows 的同一 K block 连续。
如果 layout 与计算 tile 不匹配，硬件即使 dot throughput 足够，也会被大量小 range、翻译和 AR
启动开销限制。

R4 让 read engine 用一个连续 range 取得四行 weight block，在 payload bytes 和 useful pairs
不变时减少 range/AR 数。这说明 QBS 的核心不是只增加 MAC，数据布局和事务粒度同样属于软硬件
契约。

M8 则把 5..8 条 activation rows 放入固定八路交错 block。硬件不同时计算八行，而是用
两个四行 wave 重用同一 weight block。这会减少 weight traffic，但也把 N tile 从 32 缩到 16，
增加 activation traffic 和 staging/packing 成本。因此当前它只是显式启用、精确流量门控的路径；
“逻辑读取字节更少”不能自动推导“RTL 周期更少”。

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

第 2.26 节的 `6.07x--62.26x` 是严格配对的真实量化 `MUL_MAT` 切片加速，不是“32 个整数
乘法器相对 RVV 有几十倍峰值算力”。大幅差异来自下面五项同时作用：

1. **消除整个软件展开序列**。RVV 对每个 output row 显式执行 bit unpack、metadata decode、
   widening MAC、vector reduction、标量/FP scale update 和循环控制；QBS 用一条 `qbexec` 描述
   整个 `M x N x K-blocks` tile，再由内部状态机推进。四个多格式点的 timed region 中，QBS
   侧退休的普通指令数约为 RVV 的 `0.55%--1.70%`，普通向量指令数约为 `0.43%--1.40%`。这些比例
   表示架构指令流被命令替代，不表示 QBS 内部没有执行等价的 decode、dot 和 FP 工作。
2. **直接在压缩表示上计算**。QBS 读取 GGUF native block，decoder 只在整数 datapath 的入口
   恢复 quant 和 metadata，不把完整 FP32/INT8 weight tensor 物化到 memory 或 VRF。Q3/5/6_K
   的 QBS/RVV 实测 AXI R bytes 为 `24.6%--43.6%`；Q8_0 则为 `110.2%`，说明该格式的收益主要
   来自指令/归约消除，而不是总线流量减少。不能把一种格式的 traffic 结论推广到全部 profile。
3. **在 tile 内摊薄重复工作**。一个 activation block 被 N 个 output rows 共享，一个 weight
   block 在 Prefill 中被 M 个 activation rows 共享；subgroup correction 和 128 个 FP32
   partial sums 都驻留在 command-local state，避免每行重新装载、归约和往返 scalar/VRF。
4. **让 layout 与事务粒度一致**。R4 把同一 K block 的四个 weight rows 放成连续 range，避免
   “数据本来连续、软件/硬件却发四个小请求”。硬件因此能用一个逻辑 range 填充四行 block，
   而不改变 payload 和有效点积数量。
5. **有界覆盖取数延迟**。M1/R4 使用两个 weight banks 和最多两个有序 read outstanding，在
   当前 tile 计算时读取同 K block 的下一 4-row tile。最终路径由 R4 连续请求、双 bank 和有序
   outstanding request 共同工作；这些部件不能拆成互不相关的加速比相加。

因此最终加速并非来自减少数学工作或放宽精度，而是把软件已知的 block、layout 和 shape 语义
保留到硬件后，消除解释性指令流、重复数据移动和细粒度请求，再用受控 buffering 覆盖剩余延迟。

当前四个多格式代表点的 compute 几何平均为 `22.51x`，matmul 几何平均为 `32.17x`，但不能把
格式间差异解释为 bit 数越低就一定越快。Q5_K 的标准 RVV unpack/reduction 指令序列比
Q3_K/Q6_K 更重，而 QBS 将差异主要吸收到
profile decoder，因此该点相对加速最高；Q8_0 block 只有 32 个元素，block-level FP update 更
频繁，QBS 自身固定成本占比更高，因此相对加速较低。完整模型还包含 activation quantization、
Attention、Norm、RoPE、KV cache 和 sampling，必须用端到端 Amdahl 比例评价，不能把这里的
operator speedup 直接当成 token/s speedup。

### 11.8 QBS activation context：消除的是重复读取，不是重复计算的全部来源

普通 DIRECT 命令的每个 N tile 都重新从外部 memory 读取同一份 Q8_K activation。显式
`FILL -> REUSE -> ... -> RELEASE` 把这份 activation 的**内容身份和生命周期**交给硬件：第一条
命令建立 snapshot，后续命令从 context replay，最后一条命令完成后释放。它不按虚拟地址猜测
复用，也不消除 FP32 到 Q8_K 的动态量化本身。

真实 Qwen trace 按 graph epoch、source tensor/data object、profile、shape 和 byte content 判断
可复用 identity，而不是按 pointer 相等。per-operation 策略有 394 次量化，跨 operator lifetime
分析降为 309 次，消除 85 次；对应 F32 quantization-input bytes 从 21,971,968 降到 21,449,728，
Q8_K bytes 从 6,265,444 降到 6,116,524。这里是 Host trace 的软件机会统计，不是 RTL 周期。

在保持三条 matrix operation 完全相同的 controlled RTL workload 中，context 复用将周期从
48,634 降到 25,480，即 1.91x，并精确消除 15,792 logical read bytes。然而将其放回完整 Decode
projection，投影收益只有 0.94%。这说明 lifetime context 的局部机制有效，但 activation traffic
在已经很快的完整 QBS 路径中只占有限比例。论文应把它作为“语义复用能消除重复取数”的证据，
不能把 1.91x 局部结果外推成模型级提升。

### 11.9 AKV：数据驻留必须配合适合计算方向的视图

当前 AKV 不只是把 K/V 搬进一块 SRAM。QK 计算固定一个 head dimension，并同时处理多个历史
token；PV 计算则按 token 读取一整行 V。若 SRAM 只能返回普通 row，QK 仍需重复读取和整理数据。
因此当前 context 同时提供 token-axis K column/panel view 和 V row view：K 的一列可一次覆盖
最多 64 个 token，同一 KV head 下的多个 Query rows 共用这份数据；V row 也只为这一组 Query
读取一次。

下面是同一真实 Qwen2.5-1.5B、D128/GQA6 capture 的严格配对 RTL 结果。`强 tiled-RVV` 已经采用
合理的软件 tiling，因此它比原始 RVV 更适合作为硬件增量收益的基线：

| Effective KV | 标准 RVV cycles | 强 tiled-RVV cycles | 当前 AKV cycles | RVV/AKV | tiled-RVV/AKV |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 16 | 121,338 | 41,293 | 33,799 | 3.59x | 1.22x |
| 128 | 725,838 | 157,400 | 100,530 | 7.22x | 1.57x |
| 256 | 1,413,791 | 309,540 | 193,369 | 7.31x | 1.60x |

三点几何平均上，当前 AKV 相对标准 RVV 和强 tiled-RVV 分别达到 5.74x 和 1.45x。后一个比较
更接近 token banking、resident K/V 和 local view 本身的硬件贡献，因为软件 tiling 的收益已经
包含在基线中。

严格计数进一步排除了少算工作：KV=16/128/256 时，external Query bytes 均为 3,072，external
K/V bytes 分别为 16,384/131,072/262,144，恰好各读取一次有效 F16 数据；K column command 为
256/512/1,024，V row command 为 32/256/512；FP reduction 为 24/48/96；bank conflict 和 rejected
command 均为 0。周期降低因此来自数据驻留和 view/reuse 改写，而不是跳过 Query、token 或 tail。

### 11.10 Prefill：固定硬件 tile 如何覆盖可变 prompt

Prefill 不应为每个 prompt 长度配置同等大的硬件 SRAM。当前数据流固定 64-Query 软件 block 和
64-token AKV K/V tile，再由外层循环覆盖更长序列。每次只保存当前有用的 K/V tile，完成后再
REFILL 下一段，因此 prompt 从几百 token 增长到几千 token 时，硬件容量仍保持不变。

当前选择规则要求 Query 数 `M>=64`，因为 llama.cpp 从这个边界开始使用与 AKV 相同的 tiled
Attention 计算顺序。真实 Qwen3 M84 节点中，AKV 执行 57,120 个 causal pairs、14,622,720 次
MAC，产生的 172,032 个 F32 输出与上游 tiled 路径逐位一致。短于 64 的 Prefill 继续使用上游
路径。当前仍缺少 M>=512 长 Prefill 的匹配 RTL 周期，因此不能仅根据外部 K/V 流量下降推导完整
模型加速比。

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

### 12.4 QBS activation-context counter

| Counter | 严格含义 |
| --- | --- |
| `activation_access` | 当前 descriptor 的 DIRECT/FILL/REUSE/RELEASE 编码；它是模式，不是次数 |
| `context_fill_count` | 本命令成功 commit 并正式发布一份新 activation context 时置 1 |
| `context_reuse_count` | 本命令 validation 时 REUSE/RELEASE lookup 严格匹配已提交 context 时置 1 |
| `context_reuse_block_count` | context replay 完整交付一个 native activation block 的次数 |
| `context_read_bytes` | context replay beat 与 block adapter 握手的有效 strobe bytes |
| `activation_axi_bytes_saved` | 严格 context lookup 命中时，按 descriptor activation storage size 记账的未发外部 payload bytes |
| `context_replay_cycles` | RUN 状态中 context replay busy 的周期数 |
| `context_replay_compute_overlap_cycles` | 上述 replay busy 且 compute phase 同时 active 的周期数；它是重叠活动，不是可相加 phase |
| `context_validation_fault_count` | context lookup 有效但 ID/generation/profile/layout/M/K 任一不匹配，导致 validation fault 时置 1 |

`context_fill_count=1` 只表示该命令最后发布了 context，不表示其 activation 完全来自 SRAM；FILL
本身仍从 AXI 读取 activation。`activation_axi_bytes_saved` 是根据合法 descriptor 得到的逻辑避免量，
不是从 AXI 总线计数器相减得到的物理 cache/DRAM traffic。判断机制是否有效，应同时满足 lookup
命中、replay block/bytes 与期望相等、外部 activation range 消失、matrix work 保持不变。

### 12.5 AKV command、view 和 traffic counter

`[AKV_PERF]` 是逐命令记录，`[AKV_PERF_SUMMARY]` 只对 terminal command 累加。主要字段如下：

| Counter | 严格含义 |
| --- | --- |
| `busy_cycles` | 从 command fire 到 success/fault terminal 被观察的命令占用周期；日志已包含接受周期 |
| `v2_full/v2_refill` | 接受一条当前 token-axis FULL/REFILL 命令时的一次性标志；`v2_` 是 RTL 日志保留前缀 |
| `release` | 接受一条使当前 context 无效的 RELEASE 命令时的一次性标志 |
| `v2_row_load` | 接受一条从当前 K/V context 重放完整 row 的命令数 |
| `v2_column_load` | 接受一条当前 token-axis column 命令数；单列和 panel 都各算一条 command |
| `v2_column_panel` | 上述 column command 中请求连续四列 panel 的命令数 |
| `v2_logical_column` | column command 表示的逻辑 K dimensions 数；单列加 1，panel 加 4 |
| `v2_k_view_bank_cycles` | `akv_v2_context` 为当前 column/panel gather 实际启动一轮 token-bank read 的周期数 |
| `v2_bank_conflict_cycles` | context 同周期收到互斥 write/row/column 活动而拉高 conflict 的周期数；正确执行应为 0 |
| `v2_rejected` | command 因 context/profile/tile/selector 等本地条件不合法而被 engine 拒绝的次数 |
| `q_external_bytes` | payload read handshake 中 role=Q 的有效 strobe bytes；不含 descriptor |
| `kv_external_bytes` | payload read handshake 中 role=K/V 的有效 strobe bytes |
| `replay_bytes` | 一个 VRF replay word 获得所有 lane request/final grant 后累计的有效 byte 数 |
| `replay_backpressure_cycles` | REPLAY_WRITE 有 lane result request，但该 word 尚未获得全部 accepted/final grants 的周期 |
| `read_ranges/translations/ar/r_beats/read_payload_bytes` | AKV translated read engine 中实际完成的 logical range、MMU、AXI 与 payload handshake 数 |
| `store_wait_cycles` | read engine 因 older scalar store pending 而不能推进的周期 |
| `read_backpressure_cycles` | AXI R valid 但本地 sink 当前不能接收的周期 |
| `read_outstanding_occ_sum/max/full_cycles` | outstanding burst occupancy 积分、峰值和全部槽占用周期 |

这些字段可构造三组守恒关系。例如 D128/GQA=`G`、有效 KV=`T` 的一个 Decode Attention layer，若
每个 KV head 只填一次，则全部 head 汇总应满足：

```text
Query external bytes = number_of_query_heads * D * 2
K/V external bytes   = number_of_kv_heads * T * D * 2 * 2
K logical columns    = number_of_kv_heads * D
V logical rows       = number_of_kv_heads * T
```

若周期下降但这些等式不成立，首先应怀疑漏算 head/token/tail，而不是宣布优化成功。`replay_bytes`
大于 external bytes 并不自动表示错误：同一 resident K column/V row 被多个 RVV 操作消费正是 local
reuse 的目的；必须对照算法要求的 view 次数解释。

### 12.6 GGML selector 与模型覆盖 counter

RTL counter 回答“硬件实际做了什么”，GGML trace 回答“真实 graph 为什么选择或没有选择硬件”。
AKV 的主要软件字段为：

| Field | 严格含义 |
| --- | --- |
| `candidate_ops` | 进入 AKV selector 的 `FLASH_ATTN_EXT` node 数，不表示支持或执行 |
| `executed_ops` | 全部 preflight 通过并由 AKV backend 执行的 node 数；emulation/native 必须另由运行模式说明 |
| `groups` | 已执行 node 中按 KV head/GQA group 展开的组数 |
| `executed_v2`、`groups_v2` | 实际选择当前 token-axis context 的 node/group 数；字段名中的 `v2` 是源码保留名称 |
| `kv_group_tokens` | 各已执行 group 的有效 KV token 数之和 |
| `attention_macs` | selector 按实际 Query/KV/D 公式记账的 QK+PV MAC；是逻辑工作量，不是硬件乘法计数 |
| `executed_decode/prefill` | 已执行 node 按 Query token 数分类的次数 |
| `prefill_query_tokens` | 已执行 Prefill node 的 Query token 总数 |
| `prefill_attention_pairs` | causal mask 后实际可见的 Query-KV pair 数 |
| `fallback_runtime` | AKV runtime 未启用或请求 policy 非法 |
| `fallback_capability` | 设备 capability/version/command 不支持 |
| `fallback_threading` | GGML worker/并发执行条件不满足单 context contract |
| `fallback_feature` | ref、sinks、ALiBi、softcap、scale 等算法 feature 不在当前 contract |
| `fallback_shape` | dtype、batch、D、GQA 或 tensor shape 不合法 |
| `fallback_layout` | base/stride/alignment 不能映射当前 fill/view |
| `fallback_mask` | mask 不是可证明的 dense causal prefix |
| `fallback_size` | shape 合法但不满足生产规模门限，例如 Prefill M<64 或 D256 性能门控 |

覆盖率必须给出分母。例如 `executed_ops/candidate_ops` 是 Attention node selection coverage，
`attention_macs` 可给工作量加权覆盖；二者都不是端到端周期占比。QBS 也同理：tensor selection、
operator calls、native command、dot elements 和模型 cycles 是五个不同分母，不能混成一个“覆盖率”。

## 13. 验证体系

### 13.1 Canonical reference：先冻结语义，再验证实现

`verification/qbs/qbs_ref.c` 是 ABI 的可执行规范，独立于 RTL datapath。它负责：

- descriptor validation；
- 九种 profile 的 exact decode 和数值 contract；
- row-major/R4 权重布局，以及 row-major/M4/M8 activation layout；
- trace group/block events；
- fault 前不写结果的 atomic commit。

AKV 不另写一套 Attention 算术黄金模型。`software/akv/src/akv_v2_reference.c` 负责 descriptor、
tile、row/column view 与 Decode 数据流，`akv_prefill_reference.c` 负责 bounded Query block、causal
pair、online Softmax merge 和输出比较。它们的职责分为两层：

- **AKV 搬运 contract**：fill 后的 row/column bytes 必须与源 F16 payload bit-identical；
- **RVV 算法 contract**：QK/Softmax/PV 的执行顺序必须与被接管的 GGML kernel 对齐。

因此 reference 不是“结果差不多就算通过”的容差工具。QBS RTL 应对 canonical accumulators 做
bit-exact comparison；AKV context 应对搬运 bytes bit-exact；只有完整 Attention output 因普通
浮点 kernel 的既定顺序允许时，才使用预先声明的误差指标，而且不能以加宽 tolerance 掩盖算法
边界不一致。

### 13.2 Standalone、command 与系统 handoff RTL

验证从小到大包括：

- constructed format vectors；
- profile decoder/integer engine/FP accumulator unit tests；
- descriptor/read/compute/commit command testbench；
- 默认 M1--M4、可选 M5--M8、N tails、K blocks；
- MMU/PMA/AXI response/RLAST 和 backpressure fault；
- QBS activation context 的 fill/reuse/release、stale generation、abort 和 target SRAM macro；
- AKV descriptor、FULL/REFILL、row/column/panel、tail、RELEASE、fault 与 replay backpressure；
- normal VLSU、QBS、AKV 的 owner 互斥及 QBS-to-AKV handoff；
- real Qwen/Qwen3、SmolLM2、Phi、Gemma shape 的 payload 和 llama.cpp golden。

AKV context 同时跑 generic behavioral SRAM 与目标 64x256 macro wrapper。前者便于功能定位，后者
验证 bank/address/enable 极性和宏拼接；二者都通过才说明“算法正确”没有掩盖“宏映射错误”。系统
handoff test 则专门检查一条 QBS terminal 后 AKV 能获得 VLSU，AKV release 后 normal RVV load
仍能获得接口，并且 held level-valid request 不会被重复接受。

### 13.3 QEMU functional model

QEMU 10.2.0 `Xaraqbs` model复用生成的 ABI header 和 canonical C reference。它检查 capability、
vector/FP state、destination alignment、guest memory fault、窄模式 inactive-element 清零、M=3
保留寄存器、宽模式 active-N 写入与 register-tail 保留，以及 `fflags`。QEMU 无法精确复现具体
Ara 配置的 PMA，因此采用保守 RAM-only contract：descriptor
整段必须先验证为直接 RAM-backed 才能读取；解析尺寸后，activation 和 weight 两个完整范围都
必须先验证为直接 RAM-backed，随后才复制任一 payload。ROM、MMIO/device callback 及其他
MMIO-like 映射直接产生 load-access fault，不执行逐字节设备读。这是**架构/软件功能模型，不是
timing model**。

短契约回归还覆盖两类边界：合法 activation/weight range 跨越 4-KiB 页时逐页验证并成功执行；
range 的前半位于 RAM、尾部进入未映射区时，在修改目的向量前产生 load-access fault。后者同时
检查目的向量保持原值，避免“先算一部分、后发现范围非法”的非原子行为。

冻结的七模型通用性集对每个模型使用各自记录的 prompt，依次运行普通 RVV、native QBS，
以及 native QBS 加 AKV functional-emulation backend，检查输出文本、Top-1、logits、
profile/operator dispatch、GEMV/GEMM、原生命令数和所有 fallback。该集包含五种 GGML
architecture、六个 dense 模型和一个 MoE，共 28 个 Host context cases，均通过。之后
又独立加入 Qwen3-1.7B，使完整模型总数为八个、GGML architecture 总数为六种；Qwen3
的 QBS/Decode AKV 和 M84 Prefill 证据在后文单独列出。

必须准确解释“native”二字：QBS 的 `qbexec` 由 QEMU `Xaraqbs` 指令模型执行 canonical reference，
因此是 guest custom instruction 的功能证据；AKV 在完整模型 QEMU 中仍由 GGML
`GGML_RISCV_AKV_EMULATE=1` 执行 functional reference，用于验证 selector、数据流和数值，不是
QEMU AKV 指令 timing，也不是 RTL execution。AKV 原生命令周期来自独立的 VCS RTL leaf。QEMU
通过只能证明 GGML graph、ISA/runtime 契约和功能数值可工作，不能作为 RTL speedup，也不能把
不同 prompt 的命令数作为跨模型性能比较。

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
| `candidate_tensors` | CPU repack selector 中首次观察到、type 映射到该 QBS trace profile 的唯一 tensor 数；尚不表示运行期执行 |
| `selected_tensors` | dimension/capability/layout/shape 检查后实际选择 QBS R4 repack trait 的 tensor 数；仍不是 operator 调用数 |
| `segmented_tensors` | 因单命令 K 上限而需要软件 K 分段的 tensor 数 |
| `candidate_elements` | 上述候选中合法 2D/3D shape 按 `K*rows*matrix_count` 计算的权重元素数 |
| `selected_elements` | 选择 QBS repack trait 的权重元素数；不表示这些元素已在 timing RTL 执行 |
| `fallback_format_filter` | 因本次格式 allowlist 被明确排除的候选数 |
| `fallback_capability` | 硬件 capability 不支持导致的回退数 |
| `fallback_dimensions` | tensor 维度条件不满足导致的回退数 |
| `fallback_shape` | M/N/K shape 不满足导致的回退数 |
| `fallback_layout` | 无合法 repack/layout 导致的回退数 |
| `fallback_profile` | weight/activation profile 不兼容导致的回退数 |
| `fallback_dispatch` | 运行时派发条件不满足导致的回退数 |
| `gemv_calls/gemm_calls` | 分别进入 QBS Decode 型和 Prefill 型路径的 GGML 调用数 |
| `commands_m1..m8` | 当前 GGML 路径按 logical M 分别发出的 QBS command 数；M5--M8 仅在显式 wide-M 策略实际被选择时非零 |
| `native_qbexec` | QEMU 实际执行的原生 `qbexec` 指令数 |
| `emulated_commands` | GGML 内部软件模拟执行的命令数；硬件闭环应为 0 |

单格式隔离实验通过 `GGML_RISCV_QBS_FORMATS` 只允许目标 profile。模型中的其他格式出现
`fallback_format_filter>0` 是实验设计所致，不是能力失败；目标 profile 自身应满足
`selected_tensors == candidate_tensors`，且 capability/shape/layout/profile/dispatch
fallback 为 0。

归档于 `hardware/paper_results/b73af277_20260827/qemu_validation.json` 的完整
Qwen2.5-1.5B Q4_K_M native-QBS 运行给出如下加载期选择和运行期执行证据：

| Tensor type | Candidate/selected tensors | Candidate/selected elements | GEMV/GEMM calls | Native `qbexec` | Non-filter fallback |
| --- | ---: | ---: | ---: | ---: | ---: |
| Q4_K | `169/169` | `1,114,374,144 / 1,114,374,144` | `2720/5312` | 79,488 | 0 |
| Q6_K | `30/30` | `664,928,256 / 664,928,256` | `496/864` | 12,992 | 0 |
| **合计** | **`199/199`** | **`1,779,302,400 / 1,779,302,400`** | **`3216/6176`** | **92,480** | **0** |

这组 `100%` 的严格名称是**该 GGUF 中 Q4_K/Q6_K 候选权重 tensor 的 QBS repack selection
coverage**。它证明支持检查没有让这些目标格式的权重在加载期回退，但并不单独证明每个 tensor
都形成了 `MUL_MAT`；后两列的 `gemv/gemm_calls` 和 `native_qbexec` 才证明运行期确实进入 QBS
operator path。上述分母不含 RMSNorm、RoPE、dynamic attention、KV cache、elementwise 和
sampling，也不表示这些权重元素已经在 timing RTL 上逐个执行。`emulated_commands=0` 说明命令
没有在 GGML 内部用软件模拟；QEMU 仍只提供 ISA/功能证据，不能替代 RTL 周期或芯片性能。

结束状态也必须同时成立：

```text
QBS_TOKEN_RUN_EXIT=RVV:0         普通 RVV 模型运行成功
QBS_TOKEN_RUN_EXIT=QBS_NATIVE:0  QBS 模型运行成功
QBS_LOGITS_RECORDS=68 status=OK  两组 record 完整且元数据对齐
LLAMA_GUEST_EXIT=0               guest 总体验证成功
```

### 13.9 当前真实模型闭环结果及读法

归档于 2026-08-27 的当前基线使用真实 Qwen2.5 GGUF、相同 69-token 文本和 68 个
teacher-forced 检查点完成以下单 profile 隔离实验：

| Profile | Model | QBS/RVV PPL | Mean KL | Top-1 agreement | Top-5 overlap | Mean RMSE | Global max abs |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Q2_K | Qwen2.5-0.5B pure Q2_K | 1.0004 | 0.00410 | 89.71% | 96.18% | 0.1102 | 0.8252 |
| Q3_K | Qwen2.5-1.5B Q3_K_M | 1.0012 | 0.00833 | 91.18% | 94.12% | 0.1656 | 1.2151 |
| Q4_K | Qwen2.5-1.5B Q4_K_M | 0.9893 | 0.00866 | 89.71% | 92.65% | 0.1715 | 1.1663 |
| Q5_K | Qwen2.5-1.5B Q5_K_M | 1.0230 | 0.00905 | 94.12% | 94.71% | 0.1754 | 1.1069 |
| Q6_K | Qwen2.5-1.5B Q6_K | 0.9855 | 0.00745 | 82.35% | 94.12% | 0.1676 | 1.0965 |
| Q8_0 | Qwen2.5-0.5B Q8_0 | 1.0174 | 0.00235 | 97.06% | 95.59% | 0.0901 | 0.8997 |
| IQ4_NL | Qwen2.5-0.5B pure IQ4_NL | 1.0080 | 0.00217 | 98.53% | 95.00% | 0.0887 | 0.6807 |

这组数据支持以下有限结论：

- 七种目标 profile 均完成 68 条 record，目标 tensor 100% 选择 QBS repack，运行期存在原生
  `qbexec` 且软件模拟为 0；
- PPL ratio 位于约 `0.986..1.023`，Mean KL 均低于 `0.01`，未见模型分布整体崩坏；
- 每一行只比较同一模型文件上的 QBS 与 RVV；0.5B 和 1.5B 行的 logits 尺度、基线 PPL 与 tensor
  mix 不同，不能据此横向给量化格式做质量排名；
- Q5_K 在其短片段上的 PPL 增幅最大，约 2.3%；Q8_0/IQ4_NL 在各自 0.5B 模型上的 KL/RMSE
  较低，但不能与 1.5B 行直接比较；
- Q6_K Top-1 agreement 最低，但 Top-5 overlap 仍为 94.12%、Mean KL 为 0.00745，说明许多
  差异更可能是接近候选的排名交换，而不是直接证明功能错误；仍需结合逐步 margin 和长文本回归；
- 这些数据证明的是当前固定文本上的工程精度闭环，不能表述成标准数据集精度无损，也不能将
  `ppl_ratio<1` 宣称为 QBS 提高了模型质量。

Q4_0/Q5_0 已有真实模型严格生成输出回归，但尚未达到表中七种 profile 相同的 68-step 指标深度。
九种 profile 的算子级 directed test 全部通过，但论文级“所有格式质量等价”仍应补充更长文本、
多个 prompt/seed 和标准 perplexity 数据集。

### 13.10 当前验证覆盖清单和剩余空白

截至本文状态，已经形成的验证深度如下：

| 层次 | 已有覆盖 | 主要证明 |
| --- | --- | --- |
| ABI 生成 | JSON 到 C/SV 生成物一致性、padded tail/link regression | 软件和 RTL 使用同一字段定义 |
| QBS C reference | 九种 profile、两种 activation、R4/M4/M8 layout、shape/地址/原子提交 | canonical arithmetic/validation contract 可执行 |
| AKV runtime/reference | descriptor、D64/D96/D128、GQA1..8、Decode、bounded Prefill、tail、fallback | context/view 与普通 RVV Attention 算法边界可执行 |
| Profile RTL | 9 profiles x physical-wave M1--M4 x row-count 1--4 x 3 data patterns，共 432 cases | decoder、integer subtotal、correction 和 FP 更新逐格式成立；M5--M8 command 由 command test 覆盖两个 wave 的组合 |
| Command RTL | 默认 M1--M4 与自适应 M5--M8、不同 N/K、tail/layout | descriptor 到 commit 的组合路径成立；宽 M 使用两个四行 wave |
| Fault RTL | validation、MMU、PMA、AXI/protocol fault | pre-compute 直接 fault、payload drain 和“失败不提交”均成立 |
| QBS context RTL | generic/target-macro fill、reuse、release、metadata mismatch、abort | 显式 activation snapshot 不泄露半填充状态 |
| AKV context/engine RTL | generic/target-macro FULL/REFILL、row/column/panel、tail、RELEASE、fault、replay | Query row store、8-bank K/V view 与 terminal contract 成立 |
| QBS/AKV handoff | 两个 engine 与 normal VLSU 顺序接管共享端口 | owner 互斥、held-request 防重发和 `vid` 完成边界成立 |
| QEMU directed | 九种 profile、M1--M8、N=35 tail、三 expert `MUL_MAT_ID` | ISA、guest memory、repack、dispatch 与软件 shape 组合成立 |
| 多模型 Host 图 | 7 模型 x 4 个 effective KV，共 28/28 PASS；当前规则为 D64/D96/D128、GQA1..8 | Qwen2/Llama/Gemma3/Phi3/OLMoE 的 operator、profile、shape、MoE routing 和 Attention execute/fallback 可严格统计 |
| 真实 RTL 数据 | `format_closure.csv` 中 Q3_K/Q5_K/Q6_K/Q8_0 代表点及既有 Q4_K/Q6_K workload | 真实 GGUF bytes、activation 和 golden 可穿过 timing RTL |
| AKV 真实 RTL leaves | Qwen2.5 D128/GQA6 三个 KV 点，以及 D64/GQA3、D96/GQA1、D128/GQA2 | 当前支持 shape 的 payload/view/cycle 守恒有实测依据 |
| 多模型 QEMU | 八个模型的 QBS/AKV 选择、fallback 和数值检查 | 六种 GGML architecture、dense/MoE、D64/D96/D128 以及 D256 fallback 均有明确结果 |
| Qwen3 闭环 | dense Qwen3、Q4_K/Q6_K、D128/GQA2 Decode 和 M84 tiled Prefill | 新 architecture/shape 可复用原硬件，且算法边界由 tensor/shape 而非模型名决定 |
| 格式级模型数值 | 七种 profile 有 68-step teacher-forced 指标；Q4_0/Q5_0 有严格生成回归 | 原生 `qbexec` 能运行真实模型且短片段质量未崩坏 |

这仍留下六类空白：

1. Q4_0/Q5_0 尚未达到其余七种 profile 相同的 68-step 指标深度；
2. 八个模型已完成短功能运行，但深度质量统计仍主要基于 Qwen2.5；缺少多模型标准数据集、长文本
   free-running generation 和长上下文质量闭环；
3. 完整模型中的 AKV 是 GGML functional-emulation，尚未像 QBS 一样形成 native QEMU custom
   instruction 执行；其时序结论仍来自独立 RTL leaves；
4. M84 已完成节点级数值闭环，但真实 M>=512 长 Prefill 与强 tiled-RVV 的匹配 RTL 周期
   尚未完成，不能据静态 traffic 外推加速比；
5. module-level fault 已覆盖，但长命令中的 reset、interrupt、debug/kill 和多进程 context invalidation
   系统级压力仍需专门闭环；
6. QEMU 是功能模型，真实 RTL 的全格式、全模型执行成本以及综合/P&R/功耗不能由其替代。

因此“九种 QBS profile 功能闭环”“多模型 selector/graph 闭环”“AKV representative RTL 闭环”
和“完整模型 cycle-accurate/PPA 闭环”是四条不同结论。前三者已有不同深度的证据，第四条尚未
完成，不能用其中任一层替代另一层。

### 13.11 当前测试结果总览

下面汇总的是与本文所核 RTL 对应的当前结果。表中“通过”只对该行列出的证明目标有效，不能跨层
替代。例如 432 个 profile cases 不能证明 MMU fault，QEMU 模型运行也不能证明 RTL timing。

| 验证层次 | 当前结果 | 覆盖范围 | 可以得出的结论 |
| --- | --- | --- | --- |
| ABI/generated check | PASS（2026-08-26 复跑） | JSON 到 C/SV、R4 padded tail、hard-link alias | 软件和 RTL 字段、profile ID 与生成物一致 |
| Canonical C reference | PASS（2026-08-26 复跑） | descriptor、9 profiles、layout/tail/failure | numerical contract 和 validation 有可执行真源 |
| Profile RTL | 432/432 PASS | 9 profiles x physical-wave M1--M4 x row-count 1--4 x 3 patterns | decoder、32-pair integer path、correction 和 FP update 组合成立；M5--M8 的双 wave 调度由 command RTL 覆盖 |
| Descriptor/read/commit RTL | 三个 standalone bench 均 PASS | descriptor legality；page/burst/outstanding/fault；4-lane commit/backpressure | 三个接口边界各自满足定向 contract |
| Compute command RTL | 默认与 adaptive 命令集 PASS，fault discard PASS | 9 profiles、M1--M8、N/K/layout/tail | block adapter 到 hidden accumulator 的命令内路径成立 |
| End-to-end QBS RTL | 33/33 PASS，加 4 类 atomic-fault PASS | descriptor 到 VRF commit；validation/MMU/AXI/PMA fault | 成功结果可提交，失败命令在提交前不可见 |
| QBS activation context | generic 与 target-macro regression PASS；controlled 三操作 48,634 -> 25,480 cycles | M1/Q8_K、最多 16 K blocks、FILL/REUSE/RELEASE、fault/metadata mismatch | snapshot 发布、重放和 15,792-B logical read 消除成立；完整 Decode projection 仅改善 0.94% |
| AKV context/engine | contract、generic SRAM、target-macro、fault、QBS/AKV handoff 均 PASS | FULL/REFILL、row/column/panel、tail/RELEASE/replay | 20-macro 物理组织、owner 互斥和 context 原子发布成立 |
| AKV Decode RTL | 三个 Qwen2.5 D128/GQA6 KV 点均 0 mismatch | KV16/128/256，标准 RVV、强 tiled-RVV 与当前 AKV 严格配对 | AKV 几何平均相对两种基线为 5.74x/1.45x，traffic/view 守恒成立 |
| AKV shape RTL | D64/GQA3 为 30,853 cycles；D96/GQA1 为 10,073 cycles，均 0 mismatch | SmolLM2、Phi-derived real leaves | 当前 D64/D96/D128 支持范围可执行 |
| AKV Prefill | Qwen3 M84 node bit-exact | 64-Query block、M>=64 算法门限和 causal work | 当前生产选择与 GGML tiled Attention 数值边界一致；长点周期仍待补充 |
| 真实数据 RTL closure | 4 对 RVV/QBS 点全部 PASS，两侧对同一 golden 的 mismatch 均为 0 | Q3_K/Q5_K/Q6_K 的 1.5B `attn_q`，Q8_0 的 0.5B `attn_q` | 当前 timing RTL 可消费真实 GGUF bytes 和 activation |
| 多模型全系统 QEMU | 八个模型的相关检查均 PASS | 六种 GGML architecture、七个 dense 模型、一个 MoE 模型 | 真实 GGML graph 能选择 QBS/AKV 或明确回退；AKV 在模型 QEMU 中仍为功能 reference |
| Qwen3 QEMU | Q4_K 169/169、Q6_K 30/30；Decode AKV 56/56；unexpected fallback=0 | Qwen3-1.7B、D128/GQA2、两步 logits 和 node digest | 不改 RTL 即适配新的 dense architecture；native QBS 与 functional AKV 数值决策保持一致 |
| 模型级数值 | 7 profiles 有 68-step teacher-forced；Q4_0/Q5_0 有生成回归 | Q2_K/Q3_K/Q4_K/Q5_K/Q6_K/Q8_0/IQ4_NL logits；其余格式的定向模型回归 | 短固定文本未见分布崩坏；尚不是标准数据集质量结论 |

当前严格配对的四个真实 operator 点如下。Compute 区间包含动态 activation quantization 和
matrix phase；matmul 区间只包含量化矩阵阶段。`AXI R bytes` 是 phase-gated 读数据总线实测值：

| Profile | Shape `K x N x M` | RVV/QBS compute cycles | Compute speedup | RVV/QBS matmul cycles | Matmul speedup | QBS/RVV AXI R bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Q3_K | `1536 x 256 x 1` | 932,095 / 29,250 | 31.87x | 920,462 / 17,614 | 52.26x | 24.6% |
| Q5_K | `1536 x 256 x 1` | 1,365,782 / 33,386 | 40.91x | 1,354,132 / 21,750 | 62.26x | 36.6% |
| Q6_K | `1536 x 256 x 1` | 1,373,329 / 36,756 | 37.36x | 1,361,692 / 25,120 | 54.21x | 43.6% |
| Q8_0 | `896 x 256 x 1` | 168,625 / 31,986 | 5.27x | 163,513 / 26,923 | 6.07x | 110.2% |

四点 compute 和 matmul 几何平均分别为 `22.51x` 和 `32.17x`。所有点的
`useful_pairs == pair_capacity`、
`read_outstanding_max=2`、`fp_table_full_cycles=0`、`commit_backpressure_cycles=0`，且 source
weight、activation、golden 和模型 metadata 的 hash 在 RVV/QBS 两侧严格配对。完整原始字段
位于 `hardware/paper_results/b73af277_20260827/format_closure.csv`；QBS phase 和 probe 是可重叠
活动签名，不能相加成严格 stall breakdown。

测试结论的边界同样明确：当前已经证明 QBS 多格式功能、两类命令级 fault atomicity、QBS/AKV
真实算子 RTL 性能、AKV 多 shape 选择/回退和短文本模型数值闭环；尚未完成所有九种 profile 的
统一 68-step/标准数据集质量、AKV native-QEMU、长 Prefill 匹配周期、完整模型 RTL token/s、
跨 4-lane/1024-bit 以外配置、综合后时序、P&R 和功耗闭环。

## 14. 与相关研究和产品的关系

本节是截至 2026-09-03 的研究位置快照。需要先区分成熟度：Intel AMX、Arm SME2 和 NVIDIA
Blackwell 是已公开的工业 ISA/产品能力；SpacemiT IME 是已经落地的厂商 RISC-V 扩展；RISC-V
IME/AME 是标准工作组方向，不能写成已经 ratified 的统一矩阵 ISA；MixPE、F-BFQ 和 Gemmini
属于论文或开源研究平台。它们可以比较设计取舍，但不能把提案能力当作现成产品数据。

### 14.1 对照总表

| 路线 | 代表 | 架构状态 | 主要优化对象 | 与 QBS/AKV 的关键差异 |
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
| IO-aware exact Attention | FlashAttention | 算法级 tiling 与 online Softmax | 减少 score matrix 和 HBM/SRAM 间 IO | AKV 不替代算法；它为 RVV tiled Attention 提供有界 K/V 驻留和 token-axis view |

### 14.2 从 SpacemiT/进迭时空学到什么

SpacemiT IME 不是“给 RVV 多加一条 dot 指令”。公开架构将 32 个 RVV vector registers 重新解释
为二维 matrix tiles，软件先通过普通 load、TCM/DMA 或 layout transform 准备 tile，再由
register-to-register matrix instruction 送入专用矩阵执行路径，结果仍回到 vector register tile：

```text
memory / TCM
  -> RVV-visible vector-register tiles
  -> IME int4/int8 or FP16/BF16 matrix instruction
  -> dedicated matrix execution path
  -> vector-register result tile
```

公开资料给出了可见 tile 形状：VLEN=256 的 A60 上，INT8 基本形状可表示为
`4x8 * 8x4 -> 4x4`；VLEN=1024 的 A100 上，INT8 与 INT4 可分别达到
`8x16 * 16x8 -> 8x8` 和 `8x32 * 32x8 -> 8x8`。IME 还公开支持 block scaling、layout
transformation、卷积滑窗和 4:2 sparsity 等方向。由这些 ISA 能力可以确认其有区别于普通 RVV
ALU 的矩阵执行路径，但公开文档没有给出完整 RTL、MAC 数量、端口组织、pipeline depth，或该
datapath 究竟采用 systolic array 还是 dot-product array；本文不据产品吞吐反推这些未公开细节。

软件侧同样不能把进迭时空概括成“优化 `ggml_vec_dot_*()`”。当前检查的 llama.cpp SpacemiT
backend 在模型加载时持久 repack，在运行时动态量化 activation，并直接实现完整
`GGML_OP_MUL_MAT` 和 `GGML_OP_MUL_MAT_ID` 的 tiled GEMV/GEMM。其当前选择路径覆盖 Q2_K、
Q3_K、Q4_0、Q4_1、Q4_K、Q5_0、Q5_1、Q5_K、Q6_K 和 Q8_0；源码中有 MXFP4 模板但 dispatch
仍标为 TODO。该 backend 还用 RVV 实现 NORM/RMS_NORM、基础 elementwise、layout/copy 类算子，
并提供受输入类型、head dimension 和 VLEN 条件约束的 F16 Flash Attention。因此它的软件覆盖面
目前比只接管量化线性层的 QBS 更宽。

两条路线在完整 operator 层面已有明显共识：

- 不停留在单输出 `vec_dot`，而是接管完整 quantized `MUL_MAT`；
- 模型加载时一次性重排静态权重，运行时量化 activation；
- Decode 使用 GEMV，Prefill 使用可复用多行 activation 的 GEMM；
- 通过 M/N/K tiling 和多输出 kernel 提高数据复用；
- 用 capability、type 和 shape 选择高性能路径，并保留标准 RVV fallback。

关键差异不在“有没有做矩阵乘”，而在**压缩数据在哪一层变成硬件执行对象**：

| 维度 | SpacemiT IME | QBS |
| --- | --- | --- |
| ISA 抽象 | 通用 register-to-register matrix/tile instruction | profile/layout/shape 驱动的量化 block-stream command |
| 输入驻留 | 软件把 tile 搬入 RVV-visible register state | VLSU 从 memory 直接读取 native/repacked GGUF blocks |
| 中间状态 | vector-register tiles，软件显式管理 layout 和生命周期 | command-local hidden accumulator，成功后才写普通 VRF |
| 格式范围 | INT4/INT8、FP16/BF16、block scaling，并延伸到 conv/sparse | 当前九种 GGML/GGUF weight profile 与两种 Q8 activation |
| 软件覆盖 | quantized GEMV/GEMM、MoE，另有多类 RVV operator kernel | quantized `MUL_MAT` 与受约束 `MUL_MAT_ID`，其余走 RVV |
| 主要优势 | 更通用、可组合的矩阵编程模型和成熟产品软件栈 | 减少压缩权重的显式 load/unpack、VRF 中间流量和指令控制 |
| 主要代价 | tile 装载、layout 和 VRF 占用仍由软件显式组织 | 长命令的 fault/interrupt/preemption、VLSU 互斥和 profile 扩展更复杂 |

所以 QBS 不能以“其他实现只优化单点积、QBS 首次优化完整 `MUL_MAT`”作为贡献。更准确的定位是：
**GGUF-native、profile-driven quantized block-stream engine embedded in an RVV processor**。它用较窄的
GGUF 语义换取更少的中间 register traffic 和命令数；IME 用更通用的矩阵 tile ISA 换取更广的格式、
算子和产品适用范围。长期系统也可以同时包含标准 RVV、通用矩阵能力和 QBS 式块流路径，而不必把
三者描述为互斥替代。

还要注意，upstream llama.cpp 正持续完善通用 RISC-V/RVV repack GEMV/GEMM。研究比较不能把
逐行标量或未 repack 的低效实现当作“RVV 上限”；QBS 应对比同一模型、同一量化格式和同等软件
优化程度的当前 RVV backend，才能把收益归因到 profile-aware hardware execution。

### 14.3 从 Arm KleidiAI 学到什么

KleidiAI 的 int4 matmul 流程明确分为 RHS persistent packing、LHS dynamic quant/packing 和 matmul
microkernel，并用 shape/capability 选择 NEON/SVE/SME 变体。这与 QBS 的 R4 weight、Q8 activation
和 M/N tile 层次高度一致。重要启示不是复制 Arm 指令，而是保持：

- packer 与 microkernel layout 契约一致；
- weight packing 只做一次，activation packing 按调用做；
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

### 14.7 QBS/AKV 当前真正占据的位置

可以用两条轴定位现有方案：

```text
架构状态:  通用 vector state ---- command-local hidden state ---- 独立 tile/scratchpad state
格式语义:  通用整数/浮点 ---- profile 驱动 block quant ---- 固定模型/固定层数据流
```

QBS 位于两条轴的中间：比纯 RVV 更理解 GGUF block 和 tile shape，但比独立 NPU/矩阵 ISA 更少
长期状态；比单一 Q4 加速器覆盖更多 profile，但没有把 Transformer graph 固化。AKV 沿另一条
轴补充运行时 Attention 数据生命周期：它比普通 vector load 理解 K/V tile 与 row/column view，
但不新增专用 Softmax 或 Attention arithmetic state。两者共同体现的研究中心是**把 framework 已
知、逐条 RVV 会丢失的有界语义带到后端，同时让结果和算术回到普通 RVV 完成域**，而不是某个
低比特乘法或一块 SRAM 本身。

同时，这个位置也产生必须正面回答的风险：profile 数增加会不会把 decoder 变成面积/时序负担；
阻塞 VLSU 会不会限制与普通 RVV 的重叠；软件 repack 和动态量化是否吞噬硬件收益；短命令的
descriptor/translation/commit 固定成本是否过高。论文评价应围绕这些问题给出面积、时序、覆盖率、
端到端性能和模型质量证据。

### 14.8 AKV 与 FlashAttention 为什么互补

标准 Attention 若显式形成完整 score matrix `S=QK^T`，会产生随 Query 和 KV token 数乘积增长的
中间存储。FlashAttention 的核心是按 Q/K/V tile 重排计算，并用 online Softmax 在片上合并 max、
denominator 和 output numerator，从而避免将完整 `S` 往返高层 memory；它仍计算 exact Attention，
重点是算法 IO complexity。

AKV 所处层次更低。它没有决定 Query block 多大、causal mask 怎样切、online Softmax 如何合并，
也没有 exp/reduction datapath。软件先选择与 GGML 相同的 tiled schedule，AKV 再为其中一个 K/V
tile提供：

```text
row-major 外部 K/V
  -> 一次 FULL/REFILL
  -> resident token-banked tile
  -> QK 所需 K column/panel view
  -> PV 所需 V row view
  -> 普通 RVV online Softmax 与 FMA
```

因此两者解决不同层次的问题：FlashAttention 避免完整 score matrix 的外部物化，AKV 避免同一个
bounded K/V tile 在 RVV 计算过程中被重复外部读取或用软件转置。若软件仍采用不匹配的逐 token
算法，只有 AKV SRAM 并不会自动得到高性能；反过来，即使 tiled-RVV 已经很好，AKV 相对强
tiled baseline 的实测提升仍可衡量硬件驻留/view 的增量贡献。当前 M<64 回退也说明硬件路径必须
服从上层算法边界，而不是强迫所有 shape 使用同一 schedule。

## 15. 当前方案的优势、限制与不能过度声称的内容

### 15.1 已形成的完整性

- 九组 profile 共用 decoder/dot/correction/FP/commit 主路径；
- GGML 默认 M1--M4/N<=32，受 capability/流量门控的 M5--M8/N<=16 也已贯通软件、RTL 和 QEMU；
  由于当前周期与部分长输入数值证据不支持默认开启，wide-M 仍是显式诊断策略；
- 一个显式 M1/Q8_K activation context 已贯通 ID/generation、FILL/REUSE/RELEASE、target SRAM 与
  read-saving counter，不使用隐式地址预测；
- GGML 模型加载 repack、运行时 dispatch、普通 RVV fallback 已接通；
- profile/capability/packing/planning/execution 已抽成独立 C11 runtime，GGML 只保留 framework adapter；
- 独立测试已覆盖九种 profile、两种 activation、低能力 M2/row-major 设备、M/N tail、split-K 和
  投放前 buffer 容量拒绝；
- QBS 与 Ara normal VLSU 有明确互斥和 assertion；
- fault 前结果不可见，成功后结果进入普通 VRF；
- AKV 已形成 descriptor、FULL/REFILL/row/column/panel/RELEASE、原子 context 发布、目标
  SRAM、共享 VLSU owner 和普通 RVV Attention 算术的完整机制链；
- AKV 生产 selector 覆盖 F32 Q、F16 K/V/mask、F32 output、batch1、D64/D96/D128、GQA1..8、
  单 token Decode 与 M>=64 tiled causal Prefill，其余节点在 side effect 前回退；
- 有七模型通用性集的 28 个 Host context cases，另有 Qwen3 独立闭环，合计八个明确记录模型、完整 `MUL_MAT`、
  真实 OLMoE `MUL_MAT_ID`，以及统一 guest/QEMU/QBS ABI 下的整模型功能闭环；
- QBS 与 AKV 具有独立真实 RTL leaves，周期、payload、命令、MAC/view 和数值均可追溯；没有用
  Host eligibility 或 QEMU wall time 代替 RTL 性能。

### 15.2 当前限制

- QBS 命令阻塞 VLSU，尚未与普通 vector memory traffic 并发；
- dynamic activation quantization 仍在软件/RVV path；
- K>256 blocks 依赖软件分段，现有 R4 子段令 N 降为 4；
- 只覆盖列出的 profile，未覆盖全部 llama.cpp/IQ/TQ/MXFP type；
- 七模型通用性工作集统一采用发布名称中的 Q4_K_M 类别，但不控制各发布者的 quantizer 版本、
  importance matrix 和 calibration 数据；它与九 profile 回归是两个正交验证轴，不是完整的
  七模型乘九 profile 笛卡尔积；
- 当前九种 canonical profile 的 byte ABI 仍与 GGML/GGUF 一致；其他推理运行时尚无实际 adapter，
  非严格同构格式需要经过验证的加载期转换或新增 profile；
- 当前 QBS 数据接入固定为 128-bit AXI read beat，commit mapping 固定为 4 lanes；RTL 约束 VLEN 位于
  256..1024 且为 256 的整数倍，结合
  RVV 对 VLEN 为 2 的幂的要求，实际合法配置为 256/512/1024；这不是任意 Ara 配置已经自动
  支持的声明；
- 当前 ABI JSON、canonical reference 和 QEMU 尚未完整编码上述 `NrLanes/VLEN` 实现约束；reference
  接受的抽象 VLEN 范围比 `qbs_commit.sv` 更宽。VLEN=1024 固定实验不受影响，但在宣称跨配置
  可移植前，必须让 `qbinfo`、reference、QEMU、软件选择和 RTL 使用同一能力边界；
- QBS 只直接覆盖 quantized `MUL_MAT` 和受约束 `MUL_MAT_ID`；AKV 只协助满足严格 contract 的
  `FLASH_ATTN_EXT`，不覆盖完整 Transformer block；
- AKV 只有一个 hidden context，FULL/REFILL 与普通 VLSU/QBS 互斥；没有多 context、多 tenant、
  save/restore 或 normal-load overlap；
- AKV fast path 不支持 D256、batch>1、reference Attention、attention sinks、ALiBi、
  softcap、非 prefix mask 或不规则/未对齐 K/V layout。D256 两段实现功能正确但慢于强 tiled-RVV，
  因而主动回退；
- Prefill 只有 M>=64 且 GGML 已进入 tiled algorithm 时可选择。M84 有真实 graph 节点数值闭环，
  但 M>=512 的 matched native RTL 周期仍待完成；不能把 60.29x 静态 K/V traffic reduction 写成
  同倍数 speedup；
- 完整模型中 AKV 当前使用 GGML functional-emulation 验证路径；尚无与 QBS `Xaraqbs` 同等级的
  native QEMU AKV 指令模型。AKV 周期证据来自 directed VCS RTL leaf；
- 当前 QBS numerical contract v1 追求可执行一致性，不等于所有 GGML kernel 的 bitwise 累加顺序；
- QEMU 是 functional model，不能替代 RTL、综合、P&R 和 power 结果。

### 15.3 七种容易误解的说法

**错误：QBS 是把 Qwen 算子写死进硬件。**

正确：硬件只认识 profile/layout/shape，不认识 layer 名称；Qwen 是真实数据验证来源。

**错误：QBS 取代了 RVV。**

正确：QBS 只接管可支持的量化线性 tile，AKV 只提供 Attention 数据 view；普通 RVV 仍执行
activation quantization、QK/Softmax/PV、store、其他算子和所有 fallback。

**错误：32 pair/cycle 就等于每周期 32 个模型元素。**

正确：decoder、subgroup、M 分配、read wait 和 FP update 都会影响 duty；必须看 useful pairs、
capacity、dot active、phase 和 payload/cycle。

**错误：候选 tensor 的 repack selection coverage 为 100%，所以整个模型都由 QBS 执行。**

正确：该百分比来自 CPU repack selector，只说明目标格式权重通过了 QBS trait 选择。它不是
operator-call coverage；必须再用 `gemv/gemm_calls` 和 `native_qbexec` 证明运行期执行。Attention
core、KV cache、normalization、RoPE、Softmax、elementwise 和 sampling 不在这个分母中，仍由
普通 RVV/标量路径执行。模型级覆盖还必须报告 operator mix、实际调用次数和端到端周期。

**错误：AKV 是完整 Attention accelerator，已经接管 KV-cache 管理。**

正确：AKV 只保存一个有界 K/V tile，并生成 row/column/panel view。KV cache 的分配、增长、
token/head addressing、causal mask、Softmax 和输出状态仍由 llama.cpp 与普通 RVV 管理。它是
Attention 数据供给协同机制，不是独立 Attention/NPU pipeline。

**错误：支持 40K context 就需要 40K 条 K/V 全部放进 AKV SRAM。**

正确：AKV SRAM 固定保存最多 64 个 K/V tokens；更长上下文由软件按 FULL/REFILL 迭代，online
Softmax 合并每个 tile 的状态。模型最大 context length 影响循环次数和外部流量，不线性扩大
hidden SRAM。这里的“支持长上下文”仍需区分功能可分块与已完成长点性能闭环。

**错误：QBS/AKV 已经是一个 ASIC。**

正确：QBS/AKV 是领域专用架构机制及其 accelerator IP；当前已有可综合 SystemVerilog RTL、软件栈、
QEMU 功能模型和验证闭环。只有经过综合才能称为 ASIC-targeted synthesized design，经过布局布线
才能报告 post-layout ASIC implementation，流片后才能称为 ASIC silicon。论文应按真实完成层级写
“implemented in synthesizable RTL”，并只在确有对应报告时补充“evaluated using a 28-nm ASIC
synthesis/P&R flow”。DSA 描述专用化程度，ASIC 描述物理实现形态，二者不是同义词。

## 16. 合理的扩展路线

### 16.1 近期：补齐模型与 Attention 的证据深度

- 将九种 profile 的算子级 directed test、七种 profile 的 68-step teacher-forced 比较，以及
  Q4_0/Q5_0 的严格生成回归保留为固定回归基线；
- 扩展多个 prompt、seed、上下文长度和生成长度，检查误差是否随序列推进而累积；
- 在标准 perplexity 数据集上比较 RVV、QBS 与 QBS+AKV，并同时记录 profile/operator/MAC/cycle
  四类不同覆盖分母；
- 为 AKV 增加 native QEMU 指令语义模型，使完整模型中 AKV 与 QBS 都通过 guest custom instruction，
  但仍不把 QEMU wall time 当成硬件周期；
- 完成至少一个真实 M>=512 Prefill 与强 tiled-RVV 的匹配 RTL 周期点，验证 60.29x traffic reduction
  是否真正转化为 operator speedup，并按 QK/Softmax/PV/replay/command 分项归因；
- 基于扩展结果冻结 QBS numerical contract 和 AKV algorithm-selection boundary，再进行论文级质量结论。

### 16.2 中期：只优化已经测得的 QBS/AKV 瓶颈

- 将 activation quantization 与 QBS command 更紧密地流水化，但先定义 FP 输入和异常边界；
- 设计对 K segmentation 友好的 R4K layout，避免 split-K 时 N 降为 4；
- profile decoder 参数化扩展更多 GGUF type，但只在共享 datapath 足够时加入；
- 根据 Q8_0 的 FP/result bottleneck 调整 FP pipeline，而不是盲目增大 dot array。
- 仅当长 Prefill 证明 column/row replay 或 command setup 已成为关键路径时，再研究更宽 panel、
  replay batching 或受控双 context；不能仅因 SRAM 尚有空间而增加并行状态；
- D256 已知两段路径为 0.764x，因此下一步若要接管 Gemma，应先改变 D-axis 数据流/命令摊销并
  以强 tiled-RVV 为门槛，而不是删除 selector 的性能保护。

### 16.3 更长期：连接相邻阶段而不固化模型 graph

当前 QBS 已覆盖量化线性层，AKV 已覆盖受约束 Decode/Prefill Attention 数据供给。更长期的机会
应优先减少两者和普通 RVV 之间的重复转换，而不是再增加一个固定模型算子：

- QBS output 到下一 activation quantizer 的 on-chip forwarding；
- QBS Q/K/V projection 输出到 AKV Query/K/V fill 的有界 producer-consumer handoff；
- 稀疏/MoE expert routing 下的 gather-aware block stream；
- RMSNorm/activation/quantization fusion；
- 与 cache/prefetch hint 联动的 persistent weight tile；
- 多 QBS/AKV context、普通 VLSU 并发和 context switch/save/restore；
- 只有 profiling 证明 exp/reduction 已成为主要剩余周期时，才考虑增强通用 RVV reduction/SFU，
  不把它悄悄塞进 AKV 变成不可查询的第二套 Attention arithmetic。

每项扩展都必须回答：它增加的是 profile、layout、shape 还是新的 architectural state？是否还能
保持能力查询和 RVV fallback？fault 前如何撤销？对上下文切换有什么影响？是否在至少两个模型
shape 上优于当前强 RVV/QBS/AKV baseline？

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
9. 哪七个层内 projection 可进入 QBS，Attention 的哪些部分由 AKV 提供数据、哪些仍由 RVV 算？
10. 为什么 AKV 支持任意正 KV length 的分块，不等于 hidden SRAM 能保存整个模型最大 context？
11. 为什么 M33 Prefill 必须回退，而 M84 可以选择 AKV；这个边界同时涉及性能还是数值算法？
12. 一次真实模型生成正确，为什么仍不能替代 profile 算术、context bytes 和 RTL fault/commit 验证？

若这些问题尚不清楚，应回看第 2 节的 shape ledger、计算占比和模型到 GGML 的映射，再进入命令
状态机。否则很容易把“局部 QBS/AKV 加速”“整层加速”和“token/s 加速”混成同一结论。

### 17.2 分别从一个 QBS 命令和一个 AKV tile 建立心智模型

建议先选 `Q4_K x Q8_K, M=1, N=4, K-blocks=1`：

1. 在 `qbs_ref.c` 查看一个 block 的 group trace；
2. 对照 `qbs_profile_decoder.sv` 检查 quant/scale/min/bsum；
3. 对照 `qbs_dot_array.sv` 看每周期 pair 如何分配；
4. 对照 `qbs_profile_engine_int.sv` 看 subgroup subtotal；
5. 对照 `qbs_fp_accumulator.sv` 看 FP micro-op 顺序；
6. 对照 `qbs_commit.sv` 看四个 FP32 结果进入哪个 lane/word。

之后再扩到 M4、N32、多 K blocks和 R4/M4 tails，最后单独检查 M5--M8/N16 两 wave 路径。
直接从完整模型波形开始会把 format、layout、
memory 和 FP pipeline 四类问题混在一起。

AKV 建议先选 `D64, GQA1, KV=9`，因为它同时覆盖一个完整 token group 和一个 tail：

1. 在 descriptor 中手算 Q bytes=`1*64*2`、K/V bytes=`9*64*2*2`；
2. 跟踪 FULL 的 descriptor、Q range、K/V range 与 `context_ready` 发布；
3. 选 K dimension 0，检查 bank0..7 产生 token0..7，下一 bank cycle只产生 token8；
4. 检查 column replay 的 `vl=9`，tail 以 byte enable/element count 控制而不是依赖 SRAM 清零；
5. 选一个 V token row，检查 row-major F16 bytes bit-exact 回到 VRF；
6. 检查 RELEASE 后相同 selector 必须失败且不能写 destination；
7. 最后再扩到 D128/GQA6、多 KV tiles、panel4 和 Prefill causal pairs。

这样能把“context 内容是否正确”“view 是否正确”“普通 RVV 算法是否正确”拆开。直接从最终
Attention mismatch 看波形，很容易把一个 mask/Softmax 顺序错误误判成 SRAM banking 错误。

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

AKV 使用相同原则，但证据顺序不同：

```text
先确认 GGML selector 的 dtype/D/GQA/mask/algorithm decision
 -> 核对 descriptor、tile_start/tile_count 和 payload hash
 -> 核对 Q/K/V external-byte 守恒
 -> 核对 row/column/panel 命令与 logical view 数
 -> 核对 replay bytes、bank cycles、conflict/reject
 -> 分离 QK、reduction/Softmax、PV 与 command/replay cycles
 -> 最后才改变 bank、panel 或 context 数
```

特别是先与强 tiled-RVV 比较，再与原始逐 token RVV 比较。否则软件 dataflow 改写的收益会被错误
归入硬件 SRAM/view。

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
| AKV fill 成功但 view 错 | role steering、token bank/group、dimension extract、tail count | 先改 Softmax tolerance |
| AKV output 只在短 Prefill 不同 | GGML `one_chunk`/tiled 边界、Query precision、reduction 顺序 | 把 M 门限当成纯性能参数 |
| AKV external bytes 正确但慢 | replay/command 数、bank cycles、RVV QK/reduction/PV、result grant | 盲目加大 SRAM |
| 某模型 Attention 回退 | 逐项读 fallback reason 与实际 D/GQA/mask/feature/layout | 按模型名称强制开启 |
| 第二条 AKV 命令重复执行 | held request fire 记录、上游 valid withdrawal、engine ready | 放大 watchdog 掩盖 |

### 17.5 掌握当前机制的自检问题

能够独立回答下面问题，才算建立了完整心智模型：

1. Q4_K 的 `d/dmin`、group scale/min 和 Q8_K `bsums` 分别进入哪一项公式？
2. `M=4, N=32, K=1536` 在软件、descriptor、hardware row tile 和 accumulator 中分别怎样表示？
3. 为什么 `M=8, N=16` 仍只需要 32 个 integer pairs 和 128 个 accumulator slots？两个 context
   wave 在 activation bank、weight bank、accumulator index 和 commit byte enable 上怎样衔接？
4. 为什么当前 hardware 循环是 K-block major，并在一个 K block 内遍历 N rows？
5. 为什么 R4 padding 可以多读存储行，却不能多提交 architectural outputs？
6. 一个 AXI RRESP fault 从 read engine 到 sequencer fault 的过程中，哪些状态需要 drain，哪些结果
   必须保持不可见？
7. `pair_utilization=1` 而 `dot_duty` 很低时，为什么不能继续增加 multiplier？
8. GGML 在哪些检查失败后回退，回退是否发生在 repack 前还是命令执行中？
9. 为什么 QEMU native QBS 与 GGML emulation 的“参考”含义不同？
10. 为什么 activation quantization 若按 N tile 重复执行会破坏融合收益？
11. QBS 与 IME/AME/AMX/SME2/F-BFQ 最核心的 architectural-state 和 software-contract 差异是什么？
12. AKV 的 Query、K/V 和 metadata 分别由哪个 RTL module 保存，为什么物理 40 KiB 与有效
    logical 34,816 B 不矛盾？
13. D128/GQA6/KV128 时，Query/K/V external bytes、K columns、V rows 和 FP reductions 应各是多少？
14. local-load early acknowledgement 与 sequencer `vid` completion 为什么必须分开？
15. online Softmax 的 `m/l/o` 如何跨 64-token tiles 合并，tail token 怎样避免读入无效旧值？
16. 为什么 Gemma 的 D256 Attention 走 RVV fallback，而 M84 bit-exact 仍不能证明长 Prefill RTL
    性能闭环？

## 18. 当前源码索引

### 18.1 单一 ABI 真源

- `config/qbs_abi.json`：版本、指令、limits、profile 和 layout 真源。
- `scripts/gen_qbs_abi.py`：生成 C/SystemVerilog ABI。
- `apps/common/qbs_abi.h`：软件/验证生成头。
- `hardware/include/qbs_pkg.sv`：RTL 生成 package。
- `config/akv_abi.json`：AKV descriptor、命令、D/GQA/tile/view 能力真源。
- `scripts/gen_akv_abi.py`：生成 AKV C/SystemVerilog ABI。
- `apps/common/akv_abi.h`：AKV 软件/验证生成头。
- `hardware/include/akv_pkg.sv`：AKV RTL 生成 package。

不要手改生成头和 package；修改任一 JSON 后应重新生成、检查 diff，并同时运行 C contract 与
RTL elaboration。QBS/AKV 共用 `custom-2` opcode，但 funct3 空间、descriptor 和 capability 各自
版本化，不能只改一侧常量。

### 18.2 RTL

- `hardware/include/ara_pkg.sv`
- `hardware/include/ara/ara_typedef.svh`
- `hardware/src/cva6_accel_first_pass_decoder.sv`
- `hardware/src/ara.sv`
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
- `hardware/src/vlsu/qbs/qbs_activation_context.sv`
- `hardware/src/vlsu/akv/akv_engine.sv`
- `hardware/src/vlsu/akv/akv_context.sv`
- `hardware/src/vlsu/akv/akv_v2_context.sv`

package/typedef、first-pass decoder 和三个顶层执行模块共同决定 instruction metadata、owner 与
completion；`qbs/` 决定压缩块算术和 activation snapshot，`akv/` 决定 Attention 数据 snapshot
和 view。排查问题时先按这个职责边界缩小范围。

### 18.3 QBS 公共软件层

- `software/qbs/README.md`：公共 contract、九种当前 profile 的覆盖边界和构建入口。
- `software/qbs/PORTING.md`：其他推理运行时的 exact mapping、加载期转换、fallback 和验证清单。
- `software/qbs/include/qbs/qbs.h`：运行时无关的 C API。
- `software/qbs/src/qbs_runtime.c`：profile、capability、packing、planning 和 checked execution。
- `software/qbs/src/qbs_native_riscv.c`：原生 `qbinfo/qbexec` wrapper。
- `software/qbs/examples/runtime_adapter.c`：不依赖 GGML 的 adapter 边界示例。
- `software/qbs/tests/qbs_runtime_test.c`：九 profile、layout/tail/split-K、容量和受限能力测试。

### 18.4 AKV 公共软件层

- `software/akv/README.md`：公开 contract、能力边界和验证入口。
- `software/akv/include/akv/akv.h`：运行时无关 descriptor、plan 和执行 API。
- `software/akv/include/akv/akv_abi.h`：生成 ABI 头的公共 include 入口。
- `software/akv/src/akv_runtime.c`：capability、shape/stride/tile validation 与 plan。
- `software/akv/src/akv_v2_native_riscv.c`：当前 FULL/REFILL/row/column/panel wrapper；文件名保留 `_v2`。
- `software/akv/src/akv_v2_attention_rvv.S`：当前 token-axis view 的普通 RVV arithmetic。
- `software/akv/src/akv_v2_reference.c`：Decode/reference dataflow。
- `software/akv/src/akv_prefill_reference.c`：bounded Prefill 与 online Softmax reference。
- `software/akv/tests/akv_runtime_test.c`：shape、plan、fallback 和边界测试。

### 18.5 llama.cpp fork

当前本地 GGML 集成位于：

- `/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/qbs.h`
- `/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/qbs.cpp`
- `/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/akv.h`
- `/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/akv.cpp`
- `/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/repack.cpp`

生产 adapter 的 profile、packing 和 planner 由 `software/qbs` 提供。

### 18.6 验证与结果检查

- `verification/qbs/qbs_ref.[ch]`：canonical contract。
- `verification/qbs/qbs_ref_test.c`：constructed format/shape/layout tests。
- `verification/qbs/qbs_real_test.c`：真实 Qwen2.5 数据。
- `verification/qbs/qbs_*_tb.sv`：standalone/command RTL。
- `verification/qbs/qemu/`：QEMU `Xaraqbs` functional model 和整模型脚本。
- `verification/akv/akv_contract_test.c`：encoding、descriptor 和 selector C contract。
- `verification/akv/akv_engine_tb.sv`：当前 generic/target-macro context、命令、fault 和 counter。
- `verification/akv/run_qbs_akv_handoff.sh`：QBS、AKV 与 normal VLSU 的集成 handoff。
- `hardware/scripts/akv/check-goal-closure.py`：从 manifest 校验 QBS+AKV raw artifacts 后生成闭环表。
- `hardware/scripts/akv/summarize-model-generality.py`：多模型 topology/shape/coverage 汇总。
- `hardware/scripts/akv/compare-model-node-digests.py`：定位模型路径首个 node-level 数值分叉。
- `hardware/scripts/akv/analyze_prefill_attention.py`：Prefill pair/traffic/workspace 归因。

### 18.7 补充设计与实验文档

- `hardware/docs/llama_ara_dsa_performance_plan.md`：性能计数器、评测命令和多格式闭环。
- `hardware/docs/llama_q4km_workload_and_ara_optimization.md`：真实模型 benchmark 分层和 shape。
- `hardware/docs/spacemit_ggml_backend_study.md`：进迭时空 GGML backend 的源码研究。
- `hardware/docs/attention_akv_v2_design.md`：当前 token-axis banking、Decode 周期与多 shape closure；源码沿用该文件名。
- `hardware/docs/prefill_attention_query_reuse_design.md`：B64 Prefill、算法门限和长点待验证假设。
- `hardware/docs/qbs_akv_model_closure.md`：七模型、Qwen3、coverage、周期归因和证据边界的结果索引。
- `verification/qbs/README.md`：快速验证入口。
- `verification/qbs/qemu/README.md`：QEMU 构建和整模型检查。

本文是机制教学入口；实验数字和运行目录仍应回到对应评测文档确认。

## 19. 外部资料与延伸阅读

### Qwen、Transformer 与推理基础

1. [Qwen2.5-1.5B-Instruct 官方配置](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct/blob/main/config.json)：本文 `L/D/F/Hq/Hkv/V`、RoPE 和 RMSNorm 参数来源。
2. [Qwen2.5 Technical Report](https://arxiv.org/abs/2412.15115)：Qwen2.5 模型系列、训练和部署背景。
3. [Attention Is All You Need](https://arxiv.org/abs/1706.03762)：Transformer、self-attention、multi-head attention 和 FFN 的原始定义。
4. [RoFormer/RoPE](https://arxiv.org/abs/2104.09864)：通过旋转 Q/K 表示位置和相对距离。
5. [RMSNorm](https://arxiv.org/abs/1910.07467)：RMS normalization 的定义和动机。
6. [Grouped-Query Attention](https://arxiv.org/abs/2305.13245)：query heads 分组共享 KV heads，以降低 KV 开销。
7. [GLU Variants Improve Transformer](https://arxiv.org/abs/2002.05202)：SwiGLU 等 gated FFN 变体。
8. [FlashAttention](https://arxiv.org/abs/2205.14135)：用 IO-aware tiling 和 online Softmax 减少 Attention 在外部 memory 与片上 SRAM 间的数据往返；AKV 与其数据流层次关系见第 14.8 节。
9. [llama.cpp Qwen2 graph](https://github.com/ggml-org/llama.cpp/blob/master/src/models/qwen2.cpp)：GGUF tensor shape 与 Qwen2 GGML graph 的当前实现入口。

### 标准和基础架构

1. [RISC-V Vector Extension 1.0](https://docs.riscv.org/reference/isa/unpriv/v-st-ext)：VLA、VLEN、vector state 和精确异常。
2. [Ara 官方模块说明](https://github.com/pulp-platform/ara/blob/main/docs/source/modules/ara.md)：dispatcher、sequencer、lanes、VLSU、SLDU 和 MASKU。
3. [A New Ara for Vector Computing](https://arxiv.org/abs/2210.08882)：Ara RVV 1.0 lane-based 微结构与吞吐设计。
4. [RISC-V Integrated Matrix Extension charter](https://github.com/riscv-admin/integrated-matrix-extension/blob/main/charter.adoc)：复用 vector registers 的矩阵扩展方向。
5. [RISC-V Attached Matrix Extension charter](https://github.com/riscv-admin/attached-matrix-extension/blob/main/charter.adoc)：独立 matrix state 的另一条方向。

### llama.cpp 与软件微内核

6. [GGUF specification](https://github.com/ggml-org/ggml/blob/master/docs/gguf.md)：container header、metadata、tensor info、alignment 与 payload 布局。
7. [llama.cpp current `ggml_type` block definitions](https://github.com/ggml-org/llama.cpp/blob/master/ggml/src/ggml-common.h)：各 tensor encoding 的 exact C struct、block size 和 metadata；格式细节的首要源码依据。
8. [llama.cpp quantizer](https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/quantize.cpp)：模型级 file type/recipe 怎样为不同 tensor 选择实际 encoding。
9. [llama.cpp Tensor Encoding Schemes](https://github.com/ggml-org/llama.cpp/wiki/Tensor-Encoding-Schemes)：格式族和经验用途索引；exact 位布局仍应以当前源码为准。
10. [llama.cpp CPU repack](https://github.com/ggml-org/llama.cpp/blob/master/ggml/src/ggml-cpu/repack.cpp)：CPU tensor trait、persistent repack 和 GEMV/GEMM 路径。
11. [Arm KleidiAI int4 matmul guide](https://github.com/ARM-software/kleidiai/blob/main/docs/matmul_qsi4cx/README.md)：LHS dynamic quant/packing、RHS persistent packing 和 microkernel contract。

### 产品与实现视角

12. [SpacemiT AI Matrix Extension](https://github.com/spacemit-com/docs-ai/blob/main/en/architecture/ime_extension.md)：复用 RVV register file 的矩阵 tile、INT4/INT8、FP16/BF16、block scaling 和 layout 能力。
13. [SpacemiT IME specification](https://github.com/spacemit-com/riscv-ime-extension-spec)：厂商指令语义、program model 和示例。
14. [llama.cpp SpacemiT build guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/build-riscv64-spacemit.md)：IME/RVV backend 的构建、feature selection 和运行入口。
15. [SpacemiT K3 platform overview](https://github.com/spacemit-com/docs-chip/blob/main/en/key_stone/k3/k3_docs/root_overview.md)：产品级 CPU、TCM/DMA 和 AI 能力背景；不等价于公开 RTL 微结构。
16. [Intel AMX overview](https://www.intel.com/content/www/us/en/products/docs/accelerator-engines/what-is-intel-amx.html)：八个 1 KiB architectural tile registers 与 TMUL。
17. [Arm SME/SME2 matrix model](https://developer.arm.com/community/arm-community-blogs/b/architectures-and-processors-blog/posts/matrix-matrix-multiplication-neon-sve-and-sme-compared)：ZA 二维状态、outer-product 和 scalable tile。
18. [OCP Microscaling Formats MX v1.0](https://www.opencompute.org/documents/ocp-microscaling-formats-mx-v1-0-spec-final-pdf)：MXFP4 的 FP4 element 与 shared E8M0 scale 标准。
19. [NVIDIA NVFP4 documentation](https://docs.nvidia.com/deeplearning/transformer-engine-releases/release-2.14/user-guide/features/low_precision_training/nvfp4/nvfp4.html)：16-element local scale 与 tensor/global scale 组成的 NVFP4。

### 块量化和协同加速研究

20. [QServe, MLSys 2025](https://proceedings.mlsys.org/paper_files/paper/2025/hash/fbe2b2f74a2ece8070d8fb073717bda6-Abstract-Conference.html)：低比特服务中 dequantization overhead、KV quantization 与软硬件协同。
21. [MixPE](https://arxiv.org/abs/2411.16158)：group quantization、mixed-precision PE 和“group dot 后反量化”。
22. [F-BFQ](https://arxiv.org/abs/2510.13401)：面向 llama.cpp block quantization 的可切换格式加速器，是 QBS 必须正面对照的相近工作。
23. [Gemmini](https://arxiv.org/abs/1911.09925)：生成式矩阵加速器的 ISA、scratchpad、软件栈和系统集成视角。

## 20. 术语速查

| 术语 | 含义 |
| --- | --- |
| QBS | Quantized Block Streams，量化块流执行机制 |
| AKV | Attention K/V Context，显式保存有界 Q/K/V snapshot 并向 RVV 提供 row/token-axis view 的机制；不包含 Attention 算术单元 |
| `llama.cpp` | 完整 LLM 推理 runtime；负责模型、graph、KV cache 和 sampling，不是 tensor 文件格式 |
| GGML | `llama.cpp` 使用的 tensor/operator/graph 与 CPU kernel 基础设施 |
| GGUF | 模型容器格式；保存 metadata、逐 tensor shape/type 和 payload，本身不执行计算 |
| GGML backend | 将 GGML operator 映射到 CPU、RVV、QBS 或其他设备实现的执行层 |
| Model file type/recipe | 整份模型的量化策略，例如 Q4_K_M；可让不同 tensor 使用不同 encoding |
| Tensor encoding | 单个 tensor 的 exact block ABI，例如 Q4_K 或 Q6_K |
| bpw | bits per weight，包含 scale/min/codebook 等 metadata 后的平均存储位数 |
| Token | tokenizer 定义的离散文本单元；模型输入和输出使用其整数 ID |
| Embedding | 把 token ID 查表为 hidden vector；不是普通连续数值转换 |
| Hidden state | 某个 token 在某层的内部特征向量，本文 Qwen2.5 宽度为 1536 |
| Activation | 由当前输入运行时产生的中间 tensor，区别于固定模型权重 |
| Logits | 模型对词表中每个候选 token 给出的未归一化分数 |
| Head | Attention 中一个独立的 Q 子空间；每个 head 在本文为 128 维 |
| GQA | 多个 query heads 共享较少的 K/V heads，降低 KV-cache 容量和带宽 |
| GQA ratio / `q_rows` | 一个 KV head 对应的 Query heads 数；例如 12 Q heads/2 KV heads 得到 GQA6 |
| KV cache | 保存历史 token 的 K/V，使 Decode 不必重算历史层状态 |
| KV tile | 从 KV cache 中取出的有界连续 token 区间；AKV 每次最多驻留 64 tokens，而非完整上下文 |
| Prefill | 一次处理 prompt 的多个 token，并建立各层 KV cache |
| Decode | 每次处理一个新 token，读取历史 KV cache 并继续自回归生成 |
| Causal prefix | Query token 只允许观察到自身及其之前 KV token 的连续前缀；当前 AKV selector 只接受可证明的该类 mask |
| Online Softmax | 按 tile 维护 running max、denominator 和 output numerator，在不物化完整 score matrix 时得到等价 Softmax 输出 |
| FlashAttention | IO-aware exact Attention 算法族；通过 tiling/online Softmax 减少中间 memory traffic，不等同于 AKV 硬件 context |
| GGML operator | GGML graph 中带输入、输出和语义的计算节点，例如 `MUL_MAT` |
| Microkernel | operator 在特定架构、格式和小 tile 上调用的底层计算实现 |
| Profile | 一种 weight/activation block 数学与字节布局契约 |
| Native block | GGML 格式定义的最小量化块，当前为 32 或 256 elements |
| Subgroup | block 内共享局部 scale/min 的元素组 |
| R4 | 同一 K block 的四个 output rows 交错存放 |
| M4 | 同一 K block 的四个 activation rows 交错存放 |
| M8 | 同一 K block 的 5..8 个 activation rows 按固定八路交错存放；硬件分两个四行 wave 计算 |
| wide-M | 显式启用、受 capability 和精确输入 byte-cost 门控的 M5--M8/N16 QBS 几何；当前非默认策略 |
| M | 同一命令的 activation/input rows |
| N | 同一命令的 output/weight rows |
| K-blocks | 归约维包含的 native block 数 |
| `bsums` | Q8_K 每 16 elements 的 int16 activation sum，用于 affine min correction |
| `qbinfo` | 软件查询 QBS capability 的指令 |
| `qbexec` | 执行一个 QBS MxNxK-block microtile 的阻塞命令 |
| QBS activation context | 一个显式 ID/generation 标识的 M1/Q8_K snapshot；FILL 发布、REUSE 重放、RELEASE 失效 |
| AKV FULL | 读取 descriptor 和第一组 Q/K/V，成功后原子发布一份 READY context |
| AKV REFILL | 保留已提交 shape/Q 语义并用下一 K/V tile 替换当前 tile；期间 context 不可读，失败则整份失效 |
| AKV RELEASE | 显式使 hidden context 无效；不是释放 GGML 的完整 KV-cache allocation |
| Row view | 从 context 读取某一 token 的连续 D-axis F16 row，主要用于 V 聚合 |
| Column view | 固定一个 head dimension，跨 resident tokens 读取 K 元素形成 token-axis vector，主要用于 QK |
| Panel4 view | 一条 AKV command 同时产生四个连续 K dimensions 的 column views，减少命令/派发开销 |
| Token bank | 用 token index 低位选择的 SRAM bank；AKV 用 8 banks 并行获得一个 token group 的同一 dimension |
| Context snapshot | 成功 fill 时冻结的一份数据副本；源 memory 后续变化不会隐式更新它 |
| Context publication | 全部 payload/range 成功后才置 READY；SRAM 中已写入但未发布的数据不能被 local load 观察 |
| VRF replay | 将 hidden context 的局部 view 通过正常 LDU lane-result handshake 写回普通 vector register |
| Capability discovery | 软件在运行时查询版本、shape、layout 和 profile，而不是按 CPU 名称猜能力 |
| Command-local dataflow | 计算数据在一条命令内部按 valid/ready 流过多个阶段，accumulator 不跨命令；显式 activation/AKV context 是独立的跨命令数据生命周期机制 |
| Hidden accumulator | 命令内部 FP32 部分和，成功前不是架构可见状态 |
| Atomic commit | 所有访问/计算成功后，才将完整结果写入 VRF |
| Split-K | 软件把过长 K 分成多条命令，再按原顺序累加 FP32 partial results |
| Native QBS | guest 实际执行 `qbexec`，区别于 GGML 内部 scalar emulation |
| Functional emulation | 在 GGML/Host 中按同一 contract 计算结果，用于 selector 和数值验证；不代表 custom instruction 或 RTL 周期 |
| Native RTL leaf | 在 VCS/timing RTL 中运行一个真实数据 operator/shape，并核对周期、counter 和 golden 的定向 workload |
| Algorithm boundary | 上游在不同 shape 使用不同 FP schedule 的切换点；例如 GGML M<64 `one_chunk` 与 M>=64 tiled Prefill |
| Strong tiled-RVV baseline | 已采用合理 Query/KV tiling 和复用的标准 RVV 实现，用于隔离硬件 context/view 的增量收益 |
| Repack selection coverage | 目标格式权重中选择 QBS repack trait 的 tensor/elements 比例；不是运行期 operator coverage |
| IME | Integrated Matrix Extension；本文特指复用 RVV register state 表示 matrix tile 的路线 |
| DSA | Domain-Specific Architecture/Accelerator，描述面向特定计算域的专用化，不限定物理载体 |
| ASIC-targeted RTL | 面向 ASIC flow 的可综合 RTL；只有流片后才可称为 ASIC silicon |
| Teacher forcing | 两条路径使用相同历史 token，逐位置比较下一 token 分布，避免自由生成分叉干扰归因 |
| RVV fallback | QBS/AKV 不适用时完整使用标准 RISC-V Vector/GGML 实现，不在产生 side effect 后局部补救 |

掌握 QBS/AKV 的关键不是记住每个状态名，而是始终把五条线对齐：**模型数学、GGML 算法、内存
layout/生命周期、命令 shape 和架构可见性**。QBS 把压缩权重块语义带到后端，AKV 把运行时 K/V
复用和视图语义带到后端；两者都必须在普通 RVV 的依赖、异常、VRF 和 fallback 规则中完成。只有
五条线一致，软件选中的算子才会被硬件按正确字节解释、以可证明顺序完成，并能在模型、上下文
长度或量化 recipe 改变时安全选择或回退。
