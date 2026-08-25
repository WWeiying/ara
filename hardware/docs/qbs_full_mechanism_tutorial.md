# QBS 全机制教学：从 llama.cpp 块量化算子到 Ara/RVV 协同执行

> 文档状态：依据 2026-08-25 的 `ara_dsa_next` RTL、QBS ABI、验证参考模型和本地
> llama.cpp QBS backend 核查。本文描述的是当前可执行实现；实验性数值顺序和未来扩展会
> 单独标注，不能视作 v1 已冻结语义。

## 1. 阅读目标与一句话定位

本文希望回答五个连续的问题：

1. llama.cpp 的块量化线性层到底在计算什么，为什么普通 RVV 仍有明显开销；
2. QBS（Quantized Block Streams）把哪些软件语义显式交给硬件；
3. GGML 如何选择、重排、分块并发出 QBS 命令，何时必须回退到标准 RVV；
4. QBS 如何在不破坏 Ara 普通 RVV 功能的前提下复用其 MMU、AXI、sequencer、VRF 和完成域；
5. 当前方案与矩阵扩展、外置加速器、商用 CPU AI 扩展以及块量化研究之间是什么关系。

QBS 不是一种新的模型量化算法，也不是把整个 Transformer graph 固化为硬件。它是一个
**面向 GGML 块量化线性层的、命令级、profile 驱动的压缩数据流执行路径**：软件描述
量化格式、数据布局和 `M/N/K` shape，硬件直接读取压缩权重与动态量化激活，在命令内部完成
解包、整数点积、scale/min correction、FP32 累加，最后把 FP32 输出原子地提交到普通 RVV
向量寄存器。

可以先记住下面这条端到端链路：

```text
GGUF 原始块量化权重
  -> 模型加载时持久化 R4 repack
  -> GGML_OP_MUL_MAT 运行时量化 activation
  -> qbinfo 能力检查与 M/N/K 分块
  -> qbexec(descriptor, activation, vd, M)
  -> QBS 读取压缩块、解码、点积、修正、FP32 累加
  -> 结果写入普通 v8...v11
  -> 标准 RVV vse32.v 写回 GGML 输出 tensor
```

## 2. 为什么先优化量化线性层

### 2.1 Transformer 中的主要计算

Transformer 的 Attention 和 FFN 中，大部分乘加工作来自线性映射：

```text
Attention: Q = X Wq, K = X Wk, V = X Wv, O = Attn(X) Wo
FFN:       G = X Wgate, U = X Wup, Y = activation(G) .* U, Z = Y Wdown
Output:    logits = X Wlm_head
```

在 GGML 中，这些权重矩阵乘通常落到 `GGML_OP_MUL_MAT`。Decode 阶段每次处理很少的 token，
常见形态接近 GEMV；Prefill 阶段同时处理多行 token，形态接近小 `M` 的 GEMM。RMSNorm、RoPE、
Softmax、KV-cache 搬运和 Attention score 同样重要，但它们不是当前 QBS 命令的直接覆盖对象。

用统一的矩阵记号：

```text
A: M x K，运行时 activation
B: N x K，模型权重，按输出行存储
C: M x N，FP32 输出
C[m,n] = sum_k A[m,k] * B[n,k]
```

- `M`：同时处理的 activation 行数。Decode 通常为 1；当前硬件命令支持 1 到 4。
- `N`：本条命令计算的输出行数。当前最大为 `min(VLEN/32, 32)`；VLEN=1024 时为 32。
- `K`：归约维，必须按所选量化 profile 的原生 block 大小整除。

### 2.2 块量化节省容量，却引入执行开销

llama.cpp/GGUF 不只保存低比特整数。一个块通常同时包含：

- packed low-bit payload；
- block scale；
- 某些格式的 subgroup scale；
- 某些格式的 minimum/zero-point correction；
- 动态激活块的 scale 和辅助和 `bsums`。

因此一个量化点积不是单纯 `int4 * int8`。软件需要读取元数据、拆 bit-plane、恢复有符号值、
按 subgroup 归约、计算 correction，再把整数结果转换并缩放到浮点累加器。QServe 的公开结果也
指出，低比特 GEMM 的反量化/修正开销可能占据显著执行时间；这说明“存储位宽低”并不自动
等于“计算路径高效”。

### 2.3 标准 RVV 的价值与边界

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

同一 activation 块会被许多输出行重复消费。若每个输出行都从“单点积”开始，权重格式解析、
activation 递送和 reduction 控制会反复出现。QBS 的优化对象正是这个**完整量化线性 microtile**，
不是只替换一个乘法器。

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
-普通 2D 以及受 R4 边界约束的 expert/MoE 3D tensor。

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

QBS 只在普通 VLSU idle 时接受命令。命令 active 期间：

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
  -> atomic QBS commit
  -> existing LDU result interface
  -> ordinary Ara VRF (v8...v11)
  -> standard RVV store
```

因此后续 RVV 指令可以正常消费结果，操作系统看到的仍是标准 vector state。代价是 commit
受到 LDU result port 和 VRF grant 的带宽约束，但当前计数器可直接观察该 backpressure。

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
12. **Commit**：按 lane/word 映射写满一个 architectural vector register，inactive N 元素清零。
13. **Terminal**：成功完成 vid；软件恢复 `vl=N`，用 `vse32.v v8` 存结果。

任何 validation、MMU、PMA、AXI response/protocol fault 都会进入 fault drain。架构结果直到 commit
前不可见，因此不会留下“前半个 tile 已写回”的部分状态。

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
VALIDATE/RUN -> COMPUTE_FAULT_DRAIN -> FAULT
```

它保存 command id、vd、M、descriptor/activation 地址、round mode、cache/prot 属性；调度 logical
read ranges；连接 compute 和 commit；保存 fault attribution；导出互斥 phase counter。

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

### 9.10 `qbs_commit.sv`：原子地映射到 lane VRF

commit 只有在所有读取和计算无 fault 后启动。它按 VLEN 和 4 lanes 将 FP32 accumulator word
转换为 LDU result request：

- 每个 64-bit lane word承载两个 FP32 elements；
- 每次提交四个 lane word，共八个 FP32 results；
- 对每个有效 M 写满一个 architectural vector register；
- `element >= N` 的 inactive output 清零；
- M=3 不写保留的第四个 destination register。

`commit_word_count` 必须等于 `M * words_per_register`，且每个 active element 在 commit 前已有
valid accumulator。VRF grant 不足时停在 commit，并计入 backpressure。

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

QBS 只有读请求，descriptor/weight/activation 都通过同一 MMU 和 physical-range check。当前
PMA 门控只允许整个请求范围落在 cacheable、idempotent 区域；非幂等 MMIO 或跨越不允许区域的
请求以 load-access fault 结束，而不会把长 block stream 投向有副作用的设备地址。当前
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
| `commit_word_count` | 实际提交的完整 register words 数 |
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

## 14. 与相关研究和产品的关系

### 14.1 对照总表

| 路线 | 代表 | 架构状态 | 主要优化对象 | 与 QBS 的关键差异 |
| --- | --- | --- | --- | --- |
| 通用 VLA vector | RVV 1.0、Ara | 标准 vector registers | 通用 data parallel | QBS 在其上增加 profile/shape 命令，RVV 保留为 fallback |
| 集成矩阵扩展 | SpacemiT IME/Zvvm 方向 | 复用 vector registers 表示 2D tile | register-to-register matrix ops | QBS 从 memory 直接流入压缩 blocks，不把完整输入 tile 都架构化 |
| 独立 tile 扩展 | Intel AMX、RISC-V AME 方向 | 独立 tile registers | dense matrix multiply | QBS 无独立长期 tile state，command-local accumulator 后提交 VRF |
| 软件微内核库 | Arm KleidiAI | 由 NEON/SVE/SME 状态决定 | pack + GEMV/GEMM microkernel | QBS 将 block decode/correction/reuse 下沉到硬件，但同样强调 capability、packing 和 fallback |
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

### 14.3 从 Arm KleidiAI 学到什么

KleidiAI 的 int4 matmul流程明确分为 RHS persistent packing、LHS dynamic quant/packing 和 matmul
microkernel，并用 shape/capability 选择 NEON/SVE/SME 变体。这与 QBS 的 R4 weight、Q8 activation
和 M/N tile 层次高度一致。重要启示不是复制 Arm 指令，而是保持：

- packer 与 microkernel layout 契约一致；
- weight packing 只做一次，activation packing按调用做；
- kernel selection 显式检查 type/shape/capability；
- 优化失败时能回到正确 baseline。

### 14.4 从 Intel AMX 和 RISC-V Matrix 提案看状态成本

AMX 通过八个 1 KiB tile registers 和 TMUL 获得高密度矩阵计算，但 OS 需要管理 tile config 和
tile state。RISC-V 当前也同时探索 Integrated Matrix Extension（复用 vector registers）和
Attached Matrix Extension（独立 matrix state）。这些方案更适合广泛 dense matrix programming。

QBS 用较窄的 software contract 换取较小的 architectural surface：没有通用 tile load/store、
transpose 或持久 tile state，只支持声明的 block profiles 和 M/N/K。其优势是系统接入简单、
与现有 GGML 语义贴合；限制是不能冒充通用矩阵 ISA。

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
- v1 commit mapping 固定为 4 lanes；RTL 约束 VLEN 位于 256..1024 且为 256 的整数倍，结合
  RVV 对 VLEN 为 2 的幂的要求，实际合法配置为 256/512/1024；这不是任意 Ara 配置已经自动
  支持的声明；
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

### 16.1 近期：完善现有 profile 的模型闭环

- 对每种 profile 用真实 GGUF 权重和真实 activation 验证 GEMV/GEMM；
- 记录选中 tensor、fallback reason、M/N/K、split-K 和命令覆盖；
- 用较长 token generation 比较 logits/生成文本，而不只看两 token；
- 冻结 numerical contract 后再做物理综合。

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

### 17.1 从一个命令建立心智模型

建议先选 `Q4_K x Q8_K, M=1, N=4, K-blocks=1`：

1. 在 `qbs_ref.c` 查看一个 block 的 group trace；
2. 对照 `qbs_profile_decoder.sv` 检查 quant/scale/min/bsum；
3. 对照 `qbs_dot_array.sv` 看每周期 pair 如何分配；
4. 对照 `qbs_profile_engine_int.sv` 看 subgroup subtotal；
5. 对照 `qbs_fp_accumulator.sv` 看 FP micro-op 顺序；
6. 对照 `qbs_commit.sv` 看四个 FP32 结果进入哪个 lane/word。

之后再扩到 M4、N32、多 K blocks 和 R4/M4 tails。直接从完整模型波形开始会把 format、layout、
memory 和 FP pipeline 四类问题混在一起。

### 17.2 性能问题的证据顺序

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
10. [Intel AMX overview](https://www.intel.com/content/www/us/en/products/docs/accelerator-engines/what-is-intel-amx.html)：architectural tile registers 与 TMUL。

### 块量化和协同加速研究

11. [QServe, MLSys 2025](https://proceedings.mlsys.org/paper_files/paper/2025/hash/fbe2b2f74a2ece8070d8fb073717bda6-Abstract-Conference.html)：低比特服务中 dequantization overhead 与软硬件协同。
12. [MixPE](https://arxiv.org/abs/2411.16158)：group quantization、mixed-precision PE 和反量化位置。
13. [F-BFQ](https://arxiv.org/abs/2510.13401)：面向 llama.cpp block quantization 的可切换格式加速器，是 QBS 必须正面对照的相近工作。
14. [Gemmini](https://arxiv.org/abs/1911.09925)：生成式矩阵加速器的 ISA、scratchpad、软件栈和系统集成视角。

## 20. 术语速查

| 术语 | 含义 |
| --- | --- |
| QBS | Quantized Block Streams，量化块流执行机制 |
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
| Hidden accumulator | 命令内部 FP32 部分和，成功前不是架构可见状态 |
| Atomic commit | 所有访问/计算成功后，才将完整结果写入 VRF |
| RVV fallback | QBS 不适用时使用标准 RISC-V Vector 实现 |

掌握 QBS 的关键不是记住每个状态名，而是始终把四条线对齐：**量化数学、内存 layout、命令
shape 和架构可见性**。只有四者一致，软件选中的算子才会被硬件按正确字节解释、以可证明的
顺序完成，并在普通 RVV 程序中保持可组合性。
