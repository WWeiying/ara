# QBS-Ara：面向 llama.cpp 块量化线性层的可扩展后端语义流

## 1. 研究定位

### 1.1 研究对象与边界

本项目以 Ara 为实现载体，研究如何在保留 RVV 通用执行路径的同时，高效执行
`llama.cpp`/GGML 中以压缩权重块和动态量化 activation 为输入的线性层。研究对象不是
某个 Qwen 层、某个固定矩阵尺寸或一条孤立的低比特点积，而是下列稳定计算接口：

```text
GGML_OP_MUL_MAT / GGML_OP_MUL_MAT_ID
    compressed block-quantized weight [N,K]
  x block-quantized activation         [M,K]
  -> FP32 output                       [M,N]
```

首版实现选择 `Q4_K x Q8_K` 和 `Q6_K x Q8_K`，因为它们来自真实 Q4_K_M 模型，且分别
覆盖仿射量化和有符号 bit-plane 量化两类不同语义。该选择用于验证公共框架，不把研究
范围永久写死为两个 bit width。当前 4-lane、VLEN=1024 的 Ara 只决定首个实现的物理吞吐
和最大单命令 tile，不应进入软件可见语义。

本工作的合理定位是：

> **QBS-Ara 是一个 format-profiled、shape-tiled、backend-integrated 的块量化线性层
> 执行框架。** 它在 Ara VLSU 与量化计算路径之间保持压缩块的格式、边界、元数据、
> 归属、异常和复用语义，并以阻塞、原子完成的向量命令执行完整 K 维累加。Q4_K/Q6_K
> 是首批 profile；Decode/Prefill 使用同一 K-block-major 调度，只因 `M/N` 不同而获得
> 不同程度的 activation/weight 复用。

它不是任意 GGML 算子加速器，不直接覆盖 RMSNorm、RoPE、Softmax、KV-cache 或非线性
activation；也不是具有独立矩阵寄存器和软件管理 DMA 的通用 NPU。它覆盖的是 LLM 中
占主要计算量的块量化 GEMV/GEMM，并与普通 RVV 指令共同完成其余算子。

### 1.2 三层解耦的通用性

通用性必须来自稳定接口，而不是为每个格式或 shape 增加一个 opcode。QBS-Ara 将变化因素
分为三层：

| 层次 | 描述内容 | 首版选择 | 扩展时允许改变的部分 |
| --- | --- | --- | --- |
| Format profile | block 元素数、payload/metadata 组织、signedness、sub-group、scale 和 correction 规则 | Q4_K、Q6_K，activation 为 Q8_K | 增加 profile decoder/correction，不改变命令、token 生命周期和提交协议 |
| Storage layout | block 在行间的排列和 interleave 方式 | GGUF row-major、4-row interleave | 增加 `layout_id` 和地址映射，不改变数学语义 |
| Execution mapping | `M/N/K` 分块、统一 K-block-major 调度和 physical micro-tile | `M_t<=4`、`N_t<=32`、4-row physical tile | 不同 lane/VLEN 可选择不同物理 tile；软件外层循环不变 |

必须严格区分 **format** 和 **layout**。例如 Q4_K x32 repack 只改变 32 行 weight block 的
存放顺序，不改变 Q4_K 的 scale/min/payload 数学语义；未来改成 4-row interleave 或直接
读取 row-major GGUF 时，不应定义新的量化格式。类似地，`M=1` 与 `M=15` 使用同一格式，
区别只是软件发出的 command tile 数、active context 数和由 shape 自然形成的复用范围。

公共硬件保持不变的部分包括：

```text
命令解码与 capability negotiation
    -> tagged block subrequests
    -> payload/metadata token assembly
    -> format-profile decode/correction interface
    -> command-scoped accumulation
    -> fault containment / atomic commit
    -> ordinary RVV destination registers
```

profile 专属部分只负责把一个完整压缩块转换成公共的 group-dot/correction 操作。首版不做
运行时可编程 decoder；软件只能选择硬件声明支持的 profile。这样既能扩展，又不会把格式
解析器变成难以综合、难以验证的微码机。

### 1.3 尺寸和实现可移植性

软件看到的是任意大的逻辑矩阵，硬件只接受有上限的 command tile：

```text
cap = ara.qbinfo(...)
N_cap = cap.max_N if K_blocks <= cap.max_K_blocks else min(4, cap.max_N)
for m0 in range(0, M_total, min(4, M_total - m0)):
    M_t = min(4, M_total - m0)
    for n0 in range(0, N_total, min(N_cap, N_total - n0)):
        partial = 0
        for k0 in range(0, K_blocks, cap.max_K_blocks):
            K_t = min(cap.max_K_blocks, K_blocks - k0)
            desc = prebuilt_descriptor(profile, layouts, N_t, K_t,
                                       weight_tile_base(n0, k0))
            ara.qbexec vd, desc_ptr, activation_tile_base(m0, k0), M_t
            partial += standard_RVV_read(vd, M_t, N_t)
        standard_RVV_store(output[m0 : m0 + M_t][n0 : n0 + N_t], partial)
```

- `M_total`、`N_total` 不受 `M_t<=4`、`N_t<=32` 限制，较大矩阵由软件平铺为多条命令；
- K 维以 format 的 block 大小表示，K-quant 首版要求 `K % 256 == 0`，非对齐 K 由 padding
  或标准 RVV fallback 处理；
- descriptor 编码最多表达 256 个 K-block，当前 RTL 的 `qbinfo` 同样报告 256；单命令上限对
  K-quant 是 `K<=65536`，对 32-element Q4_0/Q8_0 block 是 `K<=8192`。更长但 block-aligned
  的 K 由 backend 分段发出合法命令并显式累加 FP32 partial，非对齐 K 仍走 padding 或 RVV
  fallback；
- 当前 R4 layout 的 K 子区间只在同一四行 weight group 内连续，因此软件长 K 路径把 N tile
  限制为最多 4；这是无需新增持久化 layout 的功能覆盖方案，不代表长 K 的最终性能设计；
- `M/N` 尾块是命令的显式有效范围，不能靠读取越界后的零值猜测；
- `M_t` 由 `ara.qbexec` 的 2-bit 常量编码，使 dispatcher 在读取 descriptor 前就能预留
  正确的 destination group；`N_t`、profile、layout 和 K-block 数来自 descriptor；
- 每个 activation context 占一个 destination vector register，元素 `0..N_t-1` 为结果，
  该寄存器其余 FP32 元素写零。当前 VLEN=1024 时每个寄存器可承载 32 个结果，最大命令
  输出为 4 个寄存器、128 个 FP32；
- `N_t` 的 ISA 上限为 32，实现还需通过 capability 报告 `min(32, VLEN/32)`。较小 VLEN
  只增加 N 方向命令数，不改变矩阵数学语义；
- physical `4 output rows x 8 K positions` 是首版微结构映射，不属于 ISA，不允许软件依赖。

因此，QBS-Ara 的尺寸通用性不是“一条指令完成任意大矩阵”，而是“同一指令契约可平铺
任意模型 shape，并正确处理 tile tail”。

### 1.4 在 llama.cpp 中的覆盖范围

Qwen2.5 第 0 层已经提供七类真实量化线性层：Attention Q/K/V、Attention output、FFN
gate/up/down；每一类同时存在 Decode `M=1` 和 Prefill `M>1`，共 14 个算子点。它们覆盖：

- `N<K`、`N=K` 和 `N>K` 三种矩阵纵横比；
- Q4_K 和 Q6_K 两个 weight profile；
- `K=1536` 与 `K=8960` 的短、长 reduction 维度；
- 单 activation 重用、多 activation 重用和输出尾块；
- Attention 与 FFN 两个主要 Transformer 子层。

当前六个 RTL 代表点是上述空间的可承受切片，不等于框架只支持六点。后续接入
`GGML_OP_MUL_MAT` 时，weight type 映射 format profile，tensor stride/layout 映射
storage layout，`ne[0..]` 映射逻辑 `M/N/K`；同一 backend kernel 按 M 形成 1--4 个 active
context，硬件调度不再区分名为 Decode 或 Prefill 的模式。`GGML_OP_MUL_MAT_ID` 的首版可由软件计算 expert base 后逐个
发出相同命令，硬件 indexed expert scheduler 属于后续扩展，不纳入首版承诺。

为了证明不是 Qwen2.5 shape 特化，最终评价至少需要：

1. 七类线性层中的代表点和 `M/N/K` 边界 sweep；
2. Decode 与 Prefill 两种执行模式；
3. Q4_K 与 Q6_K 两种语义类别；
4. 第二个采用兼容 GGUF K-quant 的模型，其真实 tensor 只需通过同一 profile/layout 接口；
5. unsupported format、非对齐 K 和超出 tile 能力时的标准 RVV fallback。

### 1.5 软件基线与研究意义

当前完成的 VLEN 适配、32-output repack、GEMV/GEMM 内核和真实数据抽取只承担三项职责：

1. 提供尽可能强且正确的 RVV 软件基线；
2. 提供来自真实模型的输入、权重和 golden output；
3. 暴露通用 RVV 执行 K-quant 时的微结构瓶颈。

这些软件工作不是论文创新。论文创新必须来自可综合的 ISA/微结构机制，并以相同软件
语义、相同输入和相同输出与最优 RVV 软件比较。

这里采用严格的贡献边界：VLEN 适配、repack、intrinsic 调度和 kernel blocking 只用于
排除弱软件基线；它们不进入贡献列表，也不作为硬件消融梯度。论文中的硬件收益必须在
冻结上述最优软件后，通过新增 RTL 的开关消融得到。若某项收益在不改变 RTL 时仅靠
repack 或循环重排即可取得，则该收益属于基线改进，不能归因于 QBS-Ara。

中心问题定义为：

> RVV 只在指令层面表达元素宽度、向量长度和寄存器操作数。GGUF K-quant 的压缩 payload、
> scale/min/bsums 元数据、256-element block 边界及跨输出或 token 的复用期，在普通 load
> 与 arithmetic 指令之间并不保持为后端可见的统一对象。软件因而需要用大量细粒度指令
> 重建这些语义，并将中间结果反复经过 VRF。能否把一个量化块及其执行语义作为有边界、
> 可复用、可精确丢弃的后端 token，从 VLSU 直接送到专用执行路径？

本方案把回答收敛为 **QBS-Ara（Quantized Block Streams for Ara）**：长时延 `ara.qbexec`
在 Ara VLSU 内部生成量化块子请求，返回时形成后端可见的量化块 token；token 将 payload、
元数据、格式 profile、块序号和复用期保持绑定，并直接进入块流缓冲与量化执行单元，避免
先写 VRF 再由普通向量指令逐步解包。统一的 shape-derived 复用、双缓冲和内部
accumulator 是支撑该主机制的微结构，而不是彼此独立的论文贡献。

这项工作的基础意义不只是得到某几个 benchmark 的加速比，而是建立一条可长期复用的
软硬件契约：模型和 GGML backend 负责声明格式、shape 与 layout；Ara 后端由这些字段
推导复用范围，并在精确异常和正常 RVV 提交规则下消费这些语义。后续增加 profile、调整 dot array、
改变 buffer 容量或研究调度策略时，可以保持同一 benchmark、golden、命令边界和消融
口径，避免每次硬件修改都同时重写软件问题定义。

### 1.6 后续 RTL 开始前应冻结的基础产物

定位工作以以下可检查产物为完成标准，而不是以提出一个 DSA 名称为完成标准：

1. **Profile specification**：Q4_K/Q6_K x Q8_K 的逐 block 数学公式、byte layout、reference
   function、profile ID 和兼容 profile pair；
2. **Layout specification**：row-major 与 interleaved layout 的地址公式、alignment、stride、
   tail padding 和版本号；
3. **Command specification**：`ara.qbinfo/ara.qbexec` 的编码、16 B descriptor、destination
   ordering、precise fault、阻塞完成和 context-switch 语义；
4. **Capability/ABI specification**：软件如何发现 profile/layout/tile 能力，如何选择 repack，
   以及何时严格回退 RVV；
5. **Executable reference**：不依赖 RTL 的指令级功能模型，使用与 llama.cpp 相同输入生成
   逐元素 golden；
6. **Generality matrix**：格式、layout、M/N/K tail、七类线性层、第二模型和 negative path；
7. **Frozen performance baseline**：当前最佳正确 RVV 周期、请求、AXI/VRF 流量和计数口径。

只有这些接口冻结后，QBS-Serial、shape-derived reuse、ping-pong overlap 和 buffer-size 变化才是可归因的
硬件消融。否则某一级加速可能来自同时改变 repack、shape 或数学近似，无法判断机制收益。

### 1.7 本轮审查后的 v1 冻结结论

| 项目 | 冻结选择 | 原因 |
| --- | --- | --- |
| 软件可见接口 | `ara.qbinfo` + descriptor-driven `ara.qbexec` | 两个 GPR 同时提供 descriptor/activation pointer，M 在指令中供早期 hazard reservation |
| 首版 profile | Q4_K/Q6_K x Q8_K | 覆盖 affine-min 与 signed-bitplane 两类真实 K-quant 语义 |
| 命令 tile | M<=4，N<=min(32,VLEN/32)，K-block<=64 | 覆盖当前 K<=8960，并限制阻塞命令的最大请求量与无 stall 工作量 |
| 命令状态 | 单 active、阻塞完成、无跨命令 cache/accumulator | fault、interrupt 和 context switch 不需保存隐藏矩阵状态 |
| 后端接入 | 复用 Load PE、VLSU MMU/AXI、LDU result/VRF arbitration | 不扩大 `NrPEs/NrVFUs`，不新增 master 或 operand result source |
| 启动顺序 | CVA6 commit-head + ACC_CONS + dispatcher WAIT_IDLE + core-store drain | 同时覆盖 scalar/vector 前序访存和 Q8 pack->QBS 的生产者消费者顺序 |
| 调度 | 单一 K-block-major，shape-derived M/N consumer lifetime | Decode/Prefill 共用控制器，不暴露软件 reuse policy |
| 计算 | 4 row cluster、32 pair/cycle、16 correction slot、16-entry FP update table | 与 128-bit AXI 和 M=1..4 突发吞吐匹配 |
| 累加/提交 | 8-bank 128xFP32 accumulator，读完无 fault 后完整寄存器原子提交 | 支持 32 B/cycle LDU 写回，fault 时 destination/fflags 均不变 |
| 关闭特性 | 共享 elaboration `QbsEnable` 同时关闭 decode/datapath | 防止 decoder 与 RTL 能力不一致，并保持普通 RVV 等价 |
| 软件回退 | capability/profile/layout/alignment/shape 任一不支持即最佳 RVV | 不用 silent conversion、越界 padding 或模型专属 opcode 扩大覆盖率 |

后续 RTL 不再重新讨论“独立 QBS VFU、`vqbset`、两套 Decode/Prefill controller、32-row
硬件 tile 或跨命令 accumulator”这些方向，除非上述冻结选择被实验数据明确证伪。

## 2. 评测数据核查

### 2.1 数据来源和覆盖范围

六个评测点均来自 Qwen2.5-1.5B-Instruct-Q4_K_M 第 0 层的真实 tensor capture，capture
对应的 `llama.cpp` commit 为 `316e72d38da2bf9af84f946fb6e99419d80849f9`。每个目录的
`generated/provenance.json` 保存 tensor 名称、原始 shape、切片范围和 SHA-256；当前六点
均通过 llama.cpp golden comparison，mismatch 为 0。

| Case | Format | 评测 shape `(M,N,K)` | 原始 capture | 覆盖性质 |
| --- | --- | ---: | --- | --- |
| Decode Attention-Q | Q4_K x Q8_K | `1 x 1536 x 1536` | `1 x 1536 x 1536` | 完整算子 |
| Decode FFN-gate | Q4_K x Q8_K | `1 x 4096 x 1536` | `1 x 8960 x 1536` | 真实输出行切片 |
| Decode FFN-down | Q6_K x Q8_K | `1 x 256 x 8960` | `1 x 1536 x 8960` | 真实输出行切片 |
| Prefill Attention-Q | Q4_K x Q8_K | `4 x 1536 x 1536` | `15 x 1536 x 1536` | 真实 token 切片 |
| Prefill FFN-gate | Q4_K x Q8_K | `4 x 4096 x 1536` | `15 x 8960 x 1536` | token 与输出行切片 |
| Prefill FFN-down | Q6_K x Q8_K | `4 x 64 x 8960` | `15 x 1536 x 8960` | token 与输出行切片 |

论文中必须称后三类为 **real-data operator slices**，不能把它们写成完整 FFN 算子。切片
保留真实权重、activation 和控制流，适合 RTL 周期级对比；完整 shape 的结论需要由 N/M
sweep 验证线性缩放，再用于模型级估算。

### 2.2 最优正确软件基线

硬件比较必须对每个点采用已经验证正确的最低 matmul cycles，而不能机械采用最近一次
运行。尤其是 Q6 Decode：最新软件路径从 7,336,274 cycles 回退到 7,939,226 cycles，
慢 8.22%。硬件 baseline 应固定为前者，同时保留后者用于解释无 reduction 的 32-output
映射为何仍因更多解包、load 和 permute 而退化。

| Case | 最优 matmul cycles | 真实计算 lane-slot 利用率 | 整数 MAC lane-slot 利用率 | AXI read bytes |
| --- | ---: | ---: | ---: | ---: |
| Q4 Decode Attention-Q | 1,495,946 | 20.09% | 11.71% | 1,400,832 |
| Q4 Decode FFN-gate | 3,987,745 | 20.10% | 11.71% | 3,735,552 |
| Q6 Decode FFN-down | 7,336,274 | 16.39% | 5.86% | 5,651,456 |
| Q4 Prefill Attention-Q | 2,325,724 | 38.39% | 30.12% | 1,474,560 |
| Q4 Prefill FFN-gate | 6,197,762 | 38.41% | 30.14% | 3,932,160 |
| Q6 Prefill FFN-down | 2,225,789 | 25.38% | 12.88% | 1,187,200 |

这里的 MAC lane-slot 利用率只表示当前 MFPU 接受整数 MAC 的 lane-cycle 比例，不等于
INT8 峰值利用率。新增 counter 将进一步按 EW8/EW16/EW32/EW64 记录发射和有效元素；
在新数据完成前，不应用旧的 `int8_mac_peak_utilization` 支撑硬件结论。

### 2.3 Roofline 与流量放大

下表采用两个有意偏乐观的下界：计算下界假设专用数据通路每周期完成 32 个
weight-activation pair；访存下界假设 128-bit AXI 每周期持续传输 16 B。总下界取二者
较大值，不包含控制、scale/min 修正、流水填充和写回，因此只能量化 headroom，不能当作
性能预测。

| Case | Products | 原生 weight+activation bytes | 主导下界 cycles | 实测/下界 | AXI/原生流量 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Q4 Decode Attention-Q | 2,359,296 | 1,328,856 | 83,054 | 18.01x | 1.05x |
| Q4 Decode FFN-gate | 6,291,456 | 3,540,696 | 221,294 | 18.02x | 1.06x |
| Q6 Decode FFN-down | 2,293,760 | 1,891,820 | 118,239 | 62.05x | 2.99x |
| Q4 Prefill Attention-Q | 9,437,184 | 1,334,112 | 294,912 | 7.89x | 1.11x |
| Q4 Prefill FFN-gate | 25,165,824 | 3,545,952 | 786,432 | 7.88x | 1.11x |
| Q6 Prefill FFN-down | 2,293,760 | 511,280 | 71,680 | 31.05x | 2.32x |

由此得到两个不同的根因：

- **Q4 不是外存字节问题。** 当前流量已接近原生格式下限，主要开销是 load/bitwise/shift/
  MAC 等细粒度请求、operand requester 竞争、VRF 中间读写和后端反压。
- **Q6 同时存在语义展开和数据复读。** Decode/Prefill 的 AXI 流量分别放大到 2.99x/
  2.32x，说明 activation block 复用和 command-local accumulator 必须由硬件显式支持。

因此，单纯扩大 L2、增加 outstanding 或只提高 MAC 峰值都不能同时解决六个点。

### 2.4 源码与数据通路交叉核查

当前 Q4 32-output 内核把 32 个输出行映射为向量元素，以 activation byte 为标量广播，
避免每个输出行做横向规约；这解释了它为什么比单输出内核快。它仍需通过普通 RVV 指令
分别装载 payload/metadata、拆分 nibble、构造 scale/min 修正并执行 widening MAC。
Q6 32-output 内核同样把输出行映射为向量元素，但 `q6k_value32()` 需从低 4-bit plane 和
高 2-bit plane 恢复值，`q6k_weighted_value32()` 又将其扩展到 i32 并施加 group scale，
随后才与标量 activation 做 MAC。该映射消除了横向 reduction，却把 unpack、i32 中间值
和 activation replay 放大，因此最新 Q6 Decode 仍比旧的 reduction 版本慢 8.22%。

下表进一步用已完成的 matmul 窗口核查“细粒度命令和中间结果”是否是真实瓶颈。
`Req/input block` 用 Ara 接受的 vector request 数除以原生 weight block 与 activation
block 数；`Result/native` 仅统计 ALU/MFPU 已握手结果的有效字节，再除以原生输入字节。
它不是完整 VRF 流量，因而是保守指标，不能与 AXI bytes 相加。

| Case | Vector requests | Req/input block | ALU+MFPU result bytes | Result/native |
| --- | ---: | ---: | ---: | ---: |
| Q4 Decode Attention-Q | 230,019 | 24.94 | 9,636,864 | 7.25x |
| Q4 Decode FFN-gate | 613,379 | 24.95 | 25,698,304 | 7.26x |
| Q6 Decode FFN-down | 1,014,458 | 112.78 | 44,335,360 | 23.44x |
| Q4 Prefill Attention-Q | 495,792 | 53.66 | 29,260,800 | 21.93x |
| Q4 Prefill FFN-gate | 1,322,112 | 53.74 | 78,028,800 | 22.01x |
| Q6 Prefill FFN-down | 308,227 | 129.51 | 18,073,472 | 35.35x |

因此硬件研究对象不是“再写一个更好的 Q4/Q6 软件循环”，而是把一次原生 block 消费从
约 25--130 条后端请求压缩成少量块命令，并使 compressed payload、metadata 和部分和
不再反复成为普通 VRF 值。

## 3. K-Quant 精确语义

### 3.1 Q4_K x Q8_K

一个 Q4_K block 表示 256 个权重，由 128 B 4-bit payload、12 B scale/min 元数据和
两个 FP16 super-scale 构成，共 144 B。Q8_K activation block 由 256 个 INT8、一个
FP32 scale 和 16 个 INT16 `bsums` 构成，共 292 B。令 `g=0..7` 表示 32-element
weight group，`B_g=bsums[2g]+bsums[2g+1]`，则一个 block 对一个输出的精确分解为：

```text
I_dot = sum_g scale_g * sum_i(q4[g,i] * q8[g,i])
I_min = sum_g min_g   * B_g

acc = acc
    + fp32(d_w)    * d_x * fp32(I_dot)
    - fp32(dmin_w) * d_x * fp32(I_min)
```

`d_w` 与 `dmin_w` 是两个不同的 FP16 super-scale，不能把正项和 min correction 先合成
一个整数和再统一乘 `d_w`。因此 Q4_K 不是普通 `INT4 dot INT8`；`bsums` 已由 activation
quantization 产生，硬件直接读取并组合相邻两个 16-element sum，不重复规约 Q8 数据。

首版 profile 的 byte mapping 与 `llama.cpp` 的 `block_q4_K` 逐字节一致，所有多字节字段
均按 little-endian 解释：

| Byte range | 字段 | 精确含义 |
| --- | --- | --- |
| `0..1` | `d` | FP16 `d_w` |
| `2..3` | `dmin` | FP16 `dmin_w` |
| `4..15` | `scales[12]` | 八组 6-bit scale 与八组 6-bit min 的压缩表示 |
| `16..143` | `qs[128]` | 256 个 unsigned 4-bit quant |

对 `g=0..7`，scale/min decoder 必须逐位实现以下参考函数，不能把 12 B 直接解释为两个
连续的 8-entry 数组：

```text
if g < 4:
    scale[g] = scales[g]     & 0x3f
    min[g]   = scales[g + 4] & 0x3f
else:
    scale[g] = (scales[g + 4] & 0x0f) | ((scales[g - 4] >> 6) << 4)
    min[g]   = (scales[g + 4] >> 4)   | ((scales[g]     >> 6) << 4)
```

对 `p=0..3, l=0..31`，`qs[32*p+l]` 的低 nibble 对应元素 `64*p+l`，高 nibble 对应元素
`64*p+32+l`。因此 group `2*p` 使用低 nibble，group `2*p+1` 使用高 nibble。该映射与
scale/min 解码共同构成 profile ABI，任一项不同都必须分配新的 profile ID。

### 3.2 Q6_K x Q8_K

一个 Q6_K block 由 128 B 低 4-bit plane、64 B 高 2-bit plane、16 个有符号 group
scale 和一个 FP16 super-scale 构成，共 210 B。硬件需在 decoder 到 dot array 的边界
组合低/高 bitplane，恢复带符号 6-bit 值，完成 group integer dot 后再施加 scale。
令 `g=0..15` 表示 16-element group，则：

```text
I_q6 = sum_g signed_scale_g * sum_i(q6_signed[g,i] * q8[g,i])
acc  = acc + fp32(d_w) * d_x * fp32(I_q6)
```

若软件先展开成 INT8/i32 vector，压缩权重会在 VRF 和 operand path 中膨胀，并引入当前
实测的大量 shift、bitwise、permute 和 activation reread。

Q6_K 的原生 210 B 顺序为：

| Byte range | 字段 | 精确含义 |
| --- | --- | --- |
| `0..127` | `ql[128]` | 256 个 quant 的低 4 bit |
| `128..191` | `qh[64]` | 256 个 quant 的高 2 bit |
| `192..207` | `scales[16]` | 每 16 元素一个 signed INT8 group scale |
| `208..209` | `d` | FP16 super-scale `d_w` |

对半块 `h=0,1` 和 `l=0..31`，令 `L=ql[64*h:]`、`H=qh[32*h:]`、`S=scales[8*h:]`，
profile decoder 必须产生：

```text
k = 128*h
q[k+l   ] = ((L[l]    & 0x0f) | (((H[l] >> 0) & 3) << 4)) - 32; scale=S[l/16+0]
q[k+l+32] = ((L[l+32] & 0x0f) | (((H[l] >> 2) & 3) << 4)) - 32; scale=S[l/16+2]
q[k+l+64] = ((L[l]    >> 4)   | (((H[l] >> 4) & 3) << 4)) - 32; scale=S[l/16+4]
q[k+l+96] = ((L[l+32] >> 4)   | (((H[l] >> 6) & 3) << 4)) - 32; scale=S[l/16+6]
```

这里的 `-32`、scale 的 signedness 和四个 plane 的索引都属于 profile 语义；不能由
storage layout 或实现优化改变。

### 3.3 公共 format-profile 契约

QBS-Ara 不应让 scheduler、VLSU 或 accumulator 直接理解 `block_q4_K` 这样的 C 结构体。
这些公共模块只使用 profile table 提供的结构描述：

```text
profile_id
weight_block_elements
weight_block_bytes
activation_profile / activation_block_bytes
payload_plane_count and packing
subgroup_count / subgroup_elements
quant signedness and bias convention
scale encoding and scale scope
correction kind: none / signed-scale / affine-min-bsums / future
decoder and correction capability bits
```

软件只传递 weight/activation `profile_id`；上述详细字段由实现内部只读 capability table 给出，不能由普通
程序任意改写。Block Stream Adapter 用 byte count 和 layout 形成完整 token，profile
decoder 再产生统一的 group operation：低比特 weight、Q8 activation、group scale、
可选 correction 和 block scale。下游 dot array、accumulator、异常和提交路径不依赖
payload 原始排布。

共享的 Q8_K activation profile 固定为 292 B：byte `0..3` 是 little-endian FP32 `d_x`，
byte `4..259` 是 `qs[256]`，byte `260..291` 是十六个 little-endian signed INT16
`bsums[g]`，其中 `bsums[g]=sum(qs[16*g:16*g+16])`。`A_M4_INTERLEAVED` 只重排四个
Q8_K block 的存储顺序，不改变任何一路 Q8_K 的这些字段和值。

这种接口把“可扩展”限定为 **新增经过硬件实现和验证的 profile**，而不是声称一套固定
电路能执行任意量化公式。它也使同一个 profile 可以配合不同 storage layout，而无需复制
decoder。

### 3.4 格式扩展层级

llama.cpp 当前 K-quant family 都以 256 个元素为 super-block，但编码和 correction 并不
相同。实现先以 Q4_K 与 Q6_K 建立两类主要数据通路，随后在不改变 descriptor、token、
调度和提交协议的前提下扩展到 Q3_K、Q5_K、Q8_0 和 Q4_0：

| 层级 | 格式 | 与首版共享内容 | 需要新增内容 | 承诺范围 |
| --- | --- | --- | --- | --- |
| 实现 profile | Q4_K | block stream、Q8_K、dot、affine correction、accumulator | 4-bit payload、packed scale/min decoder | 已实现并验证 |
| 实现 profile | Q5_K | Q4_K 的 affine-min-bsums correction 主路径 | low4/high1 payload plane 与 scale/min decoder | 已实现并验证 |
| 实现 profile | Q6_K | block stream、Q8_K、dot、signed group scale、accumulator | low4/high2 bit-plane decoder | 已实现并验证 |
| 实现 profile | Q3_K | Q6_K 的 signed group-scale 主路径 | low2/high1 bit-plane 与 scale decoder | 已实现并验证 |
| 实现 profile | Q8_0/Q4_0 | block request、R4 layout、dot、accumulator、atomic commit | 32-element block、Q8_0 activation 与相应 payload decoder | 已实现并验证 |
| 自然扩展 | Q2_K | Q4_K/Q5_K 的 affine correction 主路径 | 2-bit payload 与 Q2_K scale/min decoder | ISA/token 无需改变，但需新增 RTL profile |
| 非自然扩展 | IQ family | block request、token、buffer、commit | codebook/LUT、sign grid 和新的 correction datapath | 只保留架构扩展点，不在首版支持声明内 |
| 非自然扩展 | MXFP/FP4 | block request、token、buffer、commit | shared exponent、低精度浮点乘加和舍入 | 需要新的 arithmetic profile，不称为免费兼容 |

Q8_K 和 Q8_0 是独立 activation profile，而不是写死在 weight decoder 中。F32 到 Q8_K/Q8_0
的动态量化当前由 GGML CPU 路径完成；若未来把它移入块流入口，必须增加明确的输入或
activation-side profile，不能悄悄改变同一 `profile_id` 的数学结果。

### 3.5 数值位宽与结果契约

低比特乘法和 group correction 必须保持整数精确，不允许以饱和或截断换取面积。首版采用
以下保守位宽：Q4 group dot 为 signed 18 bit，Q6 group dot 为 signed 18 bit，scale/min
乘积和每个 block 的两个整数 subtotal 均使用 signed 32 bit。Q4 分别保存 `I_dot` 与
`I_min`，Q6 保存 `I_q6`，直到 block 边界才转换为 FP32。

FP16 super-scale 扩展到 FP32 是精确转换；block 按 K 地址递增顺序更新 FP32 accumulator。
数值契约 version 1 固定以下逐 output、逐 K-block 的 FP32 操作顺序，其中每个
`fcvt/fmul/fmadd` 均使用固定 RNE 并在每步舍入；动态 `frm` 不参与 QBS numerical contract v1：

```text
Q4_K:
  dot_f = fcvt_s_w(I_dot); min_f = fcvt_s_w(I_min)
  sd = fmul(fp16_to_fp32(d_w),    d_x)
  sm = fmul(fp16_to_fp32(dmin_w), d_x)
  acc = fmadd( sd, dot_f, acc)
  acc = fmadd(-sm, min_f, acc)

Q6_K:
  dot_f = fcvt_s_w(I_q6)
  sd = fmul(fp16_to_fp32(d_w), d_x)
  acc = fmadd(sd, dot_f, acc)
```

QBS FP pipeline 在命令 context 中 OR 合并所有 IEEE exception flags。功能模型必须固定与
RTL 相同的转换、乘法和累加顺序。整数中间级逐位相等；最终 FP32
结果既报告逐位比较，也使用当前真实模型回归的 `atol=rtol=2e-3` 判断与 llama.cpp 的
数值兼容性。只有逐位差异来自已记录的 FP 运算重排时才允许通过容差，不能用容差掩盖
payload、scale/min、bsums 或 tail 映射错误。

## 4. 文献重叠审计

### 4.1 已被覆盖、不能作为主创新的内容

- XpulpNN、Quark、Sparq 和 SPEED 已覆盖 sub-byte packed arithmetic、load-dot、
  multiply-shift-accumulate 和低比特 systolic/vector datapath。只增加 INT4 x INT8 dot
  不足以构成创新。
- MXDOTP 使用 Stream Semantic Registers 给 RISC-V MXFP8 dot 持续供数；VMXDOTP 在
  RVV 中支持 MXFP4/MXFP8、硬件 block scale、可变软件 block size 和输出并行，并达到
  97% 左右利用率。仅提出“块尺度 dot + 流式供数”已经重叠。
- F-BFQ 直接面向 llama.cpp GGUF K-quant，已实现 Q2_K/Q3_K 的 super-block parser、
  输入/权重 cache、格式切换、scheduler、accumulator 和 MatMul opcode。仅提出“原生
  K-quant decoder + buffer + accumulator”也已经重叠。
- SA-ANT、MixPE 和 QServe 已分别覆盖低比特 decoder、group integer accumulation 后
  dequantization、权重重排和 register-level reuse。延迟反量化是必要设计原则，不是
  独立贡献。
- QFactory 已说明量化参数的共享范围、延迟反量化和数据布局/调度协同能够显著影响量化
  kernel。该工作属于编译器/GPU 数据流优化，也进一步要求本文使用充分优化的软件基线；
  “发现 metadata 可以复用”本身不能作为硬件创新。
- VecR、VME/IME/AME 和 SpacemiT IME 已覆盖内部 accumulation state、vector/matrix
  tile 和多精度矩阵计算。单独增加 accumulator bank 或 tile instruction 不新颖。
- SSR/ISSR 已证明用地址生成流绕过显式 load/store 可显著提高利用率，甚至讨论了
  codebook decoding。因此“memory streaming”本身不能作为新概念。

### 4.2 对照矩阵

| 工作 | 量化语义 | 供数方式 | 与 RVV 后端关系 | 内部累加/复用 | 本方案仍可区分之处 |
| --- | --- | --- | --- | --- | --- |
| Quark/Sparq/SPEED | 通用 1--4 bit | VRF/专用阵列 | Ara/RVV 扩展 | 部分支持 | 不理解 GGUF 元数据和块边界 |
| MXDOTP | MXFP8 block scale | SSR memory streams | 标量 RISC-V + SSR | dot accumulate | 格式简单，且引入独立 SSR 状态 |
| VMXDOTP | MXFP4/8 block scale | VRF，scale 预取 | 紧耦合 RVV VFU | vector output tile | payload 仍经 VRF，不含 Q4 min/bsums 或 Q6 bitplane |
| F-BFQ | GGUF Q2_K/Q3_K | 独立 AXI-stream accelerator | CPU driver + 独立 scheduler | cache + accumulator | 非 Ara VLSU/sequencer 域，当前不支持 Q4_K/Q6_K |
| SA-ANT/MixPE | 自定义/通用 group quant | accelerator array | 独立加速器 | group accumulate | 不处理 RVV 命令、异常和 fallback |
| VecR/VME/IME | 无格式语义 | VRF/矩阵状态 | RVV 或矩阵扩展 | 是 | 不绑定压缩 payload 与元数据流 |
| **QBS-Ara** | 精确 Q4_K/Q6_K profile | **VLSU 形成语义 token，直接送 QBS** | **共享 Ara 顺序、异常和完成域** | 命令域 accumulator + 双向复用 | 核心待实验证明 |

### 4.3 可辩护的主贡献与继承关系

本方案不要求每个组成部件都与已有研究完全不重合。低比特点积、块格式 decoder、流式
供数、局部 buffer 和 accumulator 都有明确先例；QBS-Ara 继承这些原则。需要由实现和
消融证明的主贡献是：

> **后端可见量化块流。** QBS-Ara 在 Ara 的 vector memory/compute 边界引入带语义的
> block token。QBS block subrequest 返回的数据不先成为普通向量寄存器值，而是与格式 profile、
> payload/metadata 角色、K-block identity、异常状态和复用期绑定。QBS command context
> 跟踪这些内部 token，Ara sequencer 只跟踪整条命令的 `vid` 和目的寄存器；fault 时命令域
> 状态可整体丢弃，成功时只在明确边界提交。

该主机制由三个相互约束的部分构成，而不是三个彼此独立的新颖性声明：

1. **Profiled compressed-domain execution**：首版严格实现 Q4_K 和 Q6_K 两个 profile，
   在 decoder 边界恢复低比特值，group dot 后才执行 scale/min/bsums 修正。首版不声称
   任意格式可编程；profile 契约为后续 Q2/Q3/Q5 留出可验证的扩展点。
2. **Shape-derived command-local reuse**：统一 K-block-major schedule 将 Q8_K block 跨
   output microtile 重用，并将 weight block 跨 active context 重用。复用范围由 M/N/K
   command shape 唯一推导，不增加模型专属 mode 或软件可调微结构 policy。
3. **RVV-integrated atomic completion**：内部 block request、部分和和 result commit 都
   属于一个未退休向量命令，复用 Ara 的地址翻译、load ordering、hazard 和异常域，不
   引入软件可见的大型矩阵状态。

这比“完整 MatMul accelerator”更适合 Ara/RVV 论文：块流操作仍可与普通 RVV 指令组合，
VLSU、sequencer、异常和 fallback 仍属于处理器后端；QBS 只接管格式密集的内层块计算。
若 standalone dot 的算术吞吐很高，但 `QBS-Serial` 仍不能把 RVV 的 request/VRF 膨胀转化
为端到端收益，或者 reuse/overlap 对完整 QBS 没有额外贡献，则实验结论应收窄，不能仅靠
token 命名维持上述定位。

## 5. ISA 与 token 契约

### 5.1 最小命令集

首版扩展暂命名为 `Xaraqbs`，使用尚未被本仓库其他指令占用的 `custom-2` major opcode。
自定义指令助记符带 `ara.` 前缀；工具链尚未支持该扩展时由 `.insn` 封装，不在应用中散布
裸编码。命令集只有 capability query 和 tile execution：

```text
ara.qbinfo rd, rs1
ara.qbexec vd, rs1, rs2, M
```

确切 32-bit 编码冻结如下。未列出的 reserved 位非零或字段组合一律产生 illegal instruction：

| 命令 | opcode | funct3 | funct7 | `rd` 字段 | `rs1` | `rs2` | CVA6 分类 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ara.qbexec` | `custom-2` (`0x5b`) | `000` | `{5'b0,M_minus_1[1:0]}` | vector `vd` | descriptor pointer | activation pointer | `ACCEL_OP_LOAD`、`vfp=1` |
| `ara.qbinfo` | `custom-2` (`0x5b`) | `001` | `7'b0` | scalar `rd` | capability index | `x0` | `ACCEL_OP` |

CVA6 first-pass decoder 对 `ara.qbexec` 读取两个 GPR，但把 scoreboard entry 的 scalar `rd`
强制为 `x0`；原始指令的 `rd` 位仍随 `insn[31:0]` 送往 Ara，后者把它解释为 vector `vd`。
`ara.qbinfo` 则正常声明 scalar `rd`，在 Ara dispatcher 内直接返回 capability，不进入
sequencer。`ara.qbexec` 会产生 FP32 运算和 `fflags`，因此与 RVV 浮点指令一样要求
`mstatus.VS`、`mstatus.FS` 可用。`QbsEnable=0` 时 first-pass decoder 不识别这两个编码，
从而保持原 RTL 并产生标准 illegal-instruction trap。

- `ara.qbinfo` 以 `rs1` 为 capability word index，将一个 XLEN capability word 写入标量
  `rd`。未知 index 返回 0；软件先查询 profile、layout、tile 和 descriptor version，再选择
  QBS 或 RVV fallback。
- `ara.qbexec` 中 `rs1` 指向 16 B immutable descriptor，`rs2` 是 activation tile 的虚拟
  地址，`vd` 是向量目的寄存器。`M` 是指令 `funct7[1:0]` 编码的 `M_t-1`，取值 1--4；
  `funct7[6:2]` 首版必须为零。
- `M` 必须在指令中而不能只放 descriptor。Ara sequencer 在 descriptor 被访存读取之前就
  必须进行 destination hazard 检查并预留寄存器组；前端不可依赖尚未读取的内存内容。
- `M=1/2/3/4` 分别按 LMUL=1/2/4/4 预留 destination group，并遵守相应的 `vd` 对齐；
  `M=3` 保守预留四个寄存器，但只修改前三个。
- 每个 active context 写一个完整 destination register：元素 `0..N-1` 为 FP32 output，
  其余 FP32 元素写零。写完整寄存器避免 Ara 的 EEW-shuffled VRF 在部分覆盖后留下旧布局；
  未使用的第四个寄存器在 `M=3` 时保持不变。
- 命令内部遍历全部 K-block 和 N 方向 4-row physical micro-tile。命令完成后，普通 RVV
  指令从 `vd+m` 读取或存储结果；QBS 不引入矩阵寄存器文件。
- v1 要求 CVA6 accelerator-consistent mode (`CSR_ACC_CONS[0]`) 为 1。关闭时 dispatcher 将
  `qbexec` 作为 illegal instruction，软件回退 RVV；否则 CVA6 不保证 accelerator load 与
  scalar store 的 pending/issue 顺序，QBS 不能自行恢复该语义。

一条 `ara.qbexec` 只描述一个 command tile，不描述完整模型、完整层或任意大矩阵。tensor
数据仍在内存，较大的 `M_total/N_total` 由 GGML backend 循环发出多条命令。K 未超过
capability 时完整留在单条命令内部；长 K 的每条分段命令各自完成并退休，partial 通过普通
FP32 软件运算显式累加，因此不会形成跨已退休指令的隐藏 QBS 状态。

不采用 `vqbset`。隐藏配置会增加 context-save ABI，而且前一条长命令在飞时还需要配置
snapshot；把配置保存在命令自己的 immutable descriptor 中可消除这两类状态。首版 descriptor
按 little-endian 定义如下，地址必须 16 B 对齐：

```text
offset 0x00, header[63:0]
  [ 3: 0] descriptor_version       = 1
  [ 7: 4] weight_profile
  [11: 8] activation_profile
  [15:12] weight_layout
  [19:16] activation_layout
  [24:20] N_minus_1                # N = 1..32
  [32:25] K_blocks_minus_1         # K_blocks = 1..256
  [63:33] reserved                 # must be zero

offset 0x08, weight_base[63:0]     # virtual address
```

首版 ID 固定为：

| 字段 | ID 1 | ID 2 | ID 0/其他 |
| --- | --- | --- | --- |
| `weight_profile` | Q4_K | Q6_K | unsupported |
| `activation_profile` | Q8_K | reserved | unsupported |
| `weight_layout` | `W_ROW_MAJOR` | `W_R4_BLOCK_MAJOR` | unsupported |
| `activation_layout` | `A_ROW_MAJOR` | `A_M4_INTERLEAVED` | unsupported |

profile/layout ID 是版本化 ABI，不复用旧 ID 表示新数学或新 byte mapping。descriptor 字段
可以表达 256 个 K-block，当前 RTL 的 capability 上限也是 256；backend 对更长 K 进行软件
分段，绝不向硬件提交越界 descriptor。

canonical stride 由 profile、layout 和 K-block 数推导；非 canonical tensor 先 repack 或走
RVV fallback。descriptor 在命令完成前必须保持不变。实现启动时一次性复制 16 B，不在命令
执行过程中重新读取，因此它不是隐藏架构状态。

weight 与 activation byte range 同样必须在命令完成前保持稳定。CVA6 本 hart 的年轻
scalar store 已被 pending-load 规则阻止；其他 hart、DMA 或 device 对这些 range 的并发写入
属于软件数据竞争，QBS 不提供跨整个长命令的内存快照。

不采用暴露给软件的 `vqbload -> vqbmac -> vqbcommit` 多指令协议。该协议会让未提交
accumulator 跨多条已退休指令存在，遇到 page fault、interrupt 或 context switch 时需要
保存大型隐藏状态。首版 `ara.qbexec` 直到结果提交完成才向 CVA6 返回，accumulator 生命周期
限制在一个未退休指令内，是
精确异常和低 OS 负担的关键约束。

软件通过 intrinsic 封装 custom opcode；未检测到扩展时回退到当前最优 RVV 内核。软件
repack 和 dispatch 仅是使用硬件的必要接口，不计入硬件贡献或 speedup。

### 5.2 Command context 与动态 token

首版只有一个 active command，不设置第二条命令队列。命令级双缓冲并不能改善一个 tile
内部的主计算，却会引入两份 fault、destination、context 和完成状态；需要隐藏内存延迟的
是 weight block ping-pong 和最多两个在途 AXI burst，而不是第二条架构命令。

“token 绑定语义”也不等于在每个 AXI beat 上重复携带所有 shape 和 profile 位。静态字段
保存在 active command context，动态 subrequest 只携带定位返回数据所需的索引：

```text
active command context (exactly one)
  vid / vd / encoded M
  weight_profile / act_profile
  weight_layout / activation_layout
  active N and K-block count
  descriptor/weight/activation bases
  current block/microtile and commit state
  first fault and accumulated fflags

ordered read-subrequest tag
  subreq_seq
  role: descriptor / weight / activation
  K-block index and N microtile index
  row/context and destination buffer bank
  virtual address, leading byte offset and expected byte count
  received byte count, last and fault

buffer-entry state
  valid / filling / compute_ready
  active consumers and consumed
```

payload 与 metadata 不能成为两个可独立前进的无标签 FIFO，否则跨 block backpressure 时
可能错配。返回 beat 按 subrequest tag 和 byte offset 写入同一 buffer entry；只有整个原生
block 的 payload、scale/min、bsums 和 super-scale 全部到齐且无 fault 后，entry 才能进入
`compute_ready`。首版所有 QBS AR 使用同一 AXI ID，利用 AXI 同 ID 有序返回；2-entry
subrequest-tag FIFO 在每个 `R.last` 弹出，不能用未标记的全局 byte counter 猜测归属。

weight/activation layout 只控制 read scheduler 的地址公式和 Block Stream Adapter 的 byte
映射；block 完整后，profile decoder 看到统一的原生 block view，layout 不再传播到 dot
array。`correction_kind`、block byte count 等由只读 profile table 推导，不在每个 token
重复保存。

首版同时最多存在一个 activation entry 和两个 weight banks。buffer 所有权以
`{role, block, microtile, bank}` 唯一确定；命令结束、fault 或 reset 时统一按 active command
清空，禁止残留 token 被下一条命令误用。

### 5.3 异常、顺序与上下文

- CVA6 first-pass decoder 将 `ara.qbexec` 标为 `ACCEL_OP_LOAD`。该路径只在指令到达 commit
  头部、已经非推测后才送入 Ara；pending-load tracking 阻止更年轻的 scalar store 越过
  命令。该保证以 `acc_cons_en=1` 为前提，dispatcher 在 QBS decode 时强制检查。QBS 还必须
  像普通 AddrGen 一样等待 `core_st_pending_i==0`，确保更老的 scalar
  store 已经排空后才读取 descriptor 或 tensor。dispatcher 的 `WAIT_IDLE` 还保证更老的
  vector load/store 和其写回已完成，这对读取刚由 RVV quantize/pack 生成的 activation
  buffer 是必要的顺序边界；更年轻 scalar load 可以与 QBS 只读流并发，更年轻 scalar
  store 则由 CVA6 的 accelerator-load pending 规则阻止。
- QBS 复用 Ara 的 accelerator MMU 端口，对每个虚拟地址区间按 4 KiB page 和 AXI 最大
  burst 拆分，逐段完成 translation/PMP 检查。`qbs_read_engine` 直接产生连续 byte-range
  请求，因为 144/210/292 B block 不能由普通 `SEW/VL` 地址流无损表达；它不建立第二个
  外部 AXI master。
- 当前 accelerator MMU response 没有 PBMT/cacheability 字段。首版只接受一个 translated
  physical byte range 完整落入同一条 `CVA6Cfg.CachedRegion*` 规则，且不与任何
  `CVA6Cfg.NonIdempotent*` 规则相交的地址；检查必须覆盖 range 的首尾和溢出，不能只检查
  起始地址。这是静态 PMA 近似，只支持配置声明的 idempotent normal-memory region，不得
  宣称支持任意 device/MMIO 或完整 PBMT 判定。Linux/缓存一致系统还必须沿用 Ara 的共享
  内存和 cache-maintenance 约束，QBS 本身不新增 coherence。
- 当前 `ara_soc` 使用 write-through CVA6 D-cache；`core_st_pending_i` 排空后，scalar 生成的
  descriptor/activation 对 Ara master 可见。v1 在 `QbsEnable=1` 时对该 cache mode 做
  elaboration check。若未来改为 write-back cache，必须先增加可证明的 clean/coherence
  协议和软件 ABI，不能仅靠 `fence` 或继续沿用本结论。
- descriptor validation 失败产生 illegal-instruction exception；descriptor、weight 或
  activation translation fault 保留原 load page/access-fault cause 和 faulting virtual
  address；AXI `RRESP` error 转换为 load access fault。多个 fault 只报告逻辑 subrequest
  顺序最早者。
- 所有可能 fault 的读请求和返回在任何 VRF writeback 之前结束。此前可以更新内部 block
  buffer 和 accumulator，但它们不是架构状态；一旦 fault，QBS 先 drain 已发出的 AXI
  response，再清空 command-local state，目的寄存器完全不变，command fflags 也以
  `valid=0` 丢弃。只有成功命令把累计 flags 送入 CVA6。
- 成功命令进入短 `COMMIT` 阶段，通过既有 LDU lane result port 分周期写回。QBS destination
  在 sequencer write list 中强制 `wait_complete=1`，所以更年轻消费者不能在部分写回时
  chaining。只有最后一个 VRF grant 后，QBS 才在同一 terminal event 产生 Load-PE
  `vinsn_done` 和 `addrgen_ack`；sequencer 据此返回成功 response，dispatcher 的既有一级
  completion register 随后只产生一次 `load_complete`。因此不存在“命令已退休但隐藏
  accumulator 仍在运行”或“消费者看到半提交 destination”的窗口。
- 首版要求 architectural `vstart==0`，不支持 block 内元素级 restart。同步 fault 时目的
  状态未改变，软件从 `ara.qbexec` 开头重试；成功后 `vstart` 保持 0。命令为阻塞式且
  首个 RTL 限制 `K_blocks<=64`，interrupt 在命令完成前不会观察到需要保存的 QBS 微结构状态。
  该上限约束的是发出的 byte range 和计算工作量；与普通 load 一样，若 memory response
  可以无限期停顿，则 wall-clock latency 并非架构上有界。该设计以不可抢占、memory-dependent
  的命令延迟换取无隐藏架构上下文；性能回归必须在固定 memory model 下报告最长命令周期。
  若未来
  需要更低 interrupt latency，应缩小软件 tile 或定义可保存的异步版本，不能暗中改变 v1。
- 没有 `vqbset` 或跨命令 cache，所以 context switch 只需保存标准 scalar/vector 架构
  状态；descriptor、block buffer 和 accumulator 都不属于可见上下文。

### 5.4 GGML backend 映射与回退

GGML backend 只在下列条件同时满足时选择 QBS：

```text
op is supported quantized MUL_MAT or software-decomposed MUL_MAT_ID
weight type maps to a supported weight_profile
activation type maps to a supported act_profile
K is block-aligned
layout and address alignment are supported, or one-time repack is available
output tile fits the accepted RVV destination register group
```

软件将逻辑矩阵平铺为 command tile，并分别处理 `M/N` tail。Decode、Prefill 不是两个
opcode，也没有软件可见的 reuse-policy bit。硬件由 `M/N` 推导统一的 K-block-major
schedule：每个 activation block 在全部 N microtile 间复用，每个 weight block 在全部 M
context 间复用。任何条件不满足时都走现有 RVV kernel，不能以错误结果、越界 padding 或
silent format conversion 换取覆盖率。

这一映射使同一 ISA 可以服务 Attention Q/K/V/O、FFN gate/up/down、输出投影以及软件
拆分后的 expert projection。不同算子只改变 base、shape、profile 和 layout，不增加专用
指令。

### 5.5 Capability、版本与软件 ABI

GGML backend 不能通过处理器名称猜测硬件行为。初始化时应获得至少以下 capability：

```text
ara.qbinfo index 0x00, basic:
  [ 7: 0] QBS architecture version          = 1
  [15: 8] descriptor version                = 1
  [23:16] descriptor bytes                  = 16
  [25:24] max_M_minus_1                     = 3
  [30:26] max_N_minus_1                     = min(31, VLEN/32-1)
  [38:31] max_K_blocks_minus_1              = 63 in the first RTL
  [42:39] numerical-contract version        = 1
  [43]    blocking completion               = 1
  [44]    atomic destination                = 1
  [45]    requires vstart==0                = 1
  [46]    idempotent normal memory only     = 1
  [47]    requires accelerator consistency  = 1
  [63:48] reserved                          = 0

ara.qbinfo index 0x01, layout/alignment:
  [15: 0] supported weight-layout bitmap
  [31:16] supported activation-layout bitmap
  [39:32] descriptor alignment log2         = 4
  [47:40] weight-base alignment log2        = 1
  [55:48] activation-base alignment log2    = 2
  [63:56] output element width in bits      = 32

ara.qbinfo index (0x10 + weight_profile):
  [15:0] compatible activation-profile bitmap; other bits zero

ara.qbinfo index (0x20 + weight_profile):
  [15: 0] weight block bytes
  [31:16] weight block elements
  [39:32] subgroup count
  [47:40] subgroup elements; other bits zero

ara.qbinfo index (0x30 + activation_profile):
  [15: 0] activation block bytes
  [31:16] activation block elements
  [39:32] bsums count; other bits zero
```

未知 index 返回 0。软件先通过平台 ISA discovery 或受控 illegal-instruction probe 确认
`Xaraqbs` 存在，再执行 `ara.qbinfo`；不能把执行 `qbinfo` 本身当成无异常的存在性测试。
首版 Q4_K/Q6_K 的 compatibility word 都只置位 Q8_K 的 ID 1。`max_N` 由 VLEN 推导，
`max_K_blocks` 是实现的延迟/资源约束而不是 descriptor 编码极限。

profile ID 和 layout ID 一旦发布，其数学语义和 byte mapping 不得改变。新增格式使用新 ID；
同一格式的新吞吐实现只改变 capability-advertised tile，不改变结果。模型加载阶段根据
capability 决定保留 row-major、生成哪一种 repacked buffer，或完全不创建 QBS buffer；
运行阶段只做 shape/tail dispatch，不能再次解释 GGUF payload。

软件接口中不出现 `attn_q`、`ffn_down`、Qwen hidden size 或固定 `n32` 等模型专属编号。
这些信息只用于选择 tensor base 和外层 tile 数。建议用版本化 intrinsic/backend wrapper
隐藏 custom opcode 编码，并始终保留同一数学接口的 RVV reference path。这样 ISA 编码、
首版物理 tile 或未来 profile 扩展时，llama.cpp 上层 graph 无需改变。

### 5.6 首版 storage layout 契约

weight 与 activation 必须使用两个独立 layout ID；二者不能压成一个组合编号，否则新增
activation packing 会复制所有 weight layout。首版定义：

```text
W_ROW_MAJOR:
  W(n,b) = weight_base
         + n * (K_blocks * weight_block_bytes)
         + b * weight_block_bytes

W_R4_BLOCK_MAJOR:
  W(n,b) = weight_base
         + ((n / 4) * K_blocks + b) * (4 * weight_block_bytes)
         + (n % 4) * weight_block_bytes

A_ROW_MAJOR:
  A(m,b) = activation_base
         + m * (K_blocks * activation_block_bytes)
         + b * activation_block_bytes

A_M4_INTERLEAVED:
  A4(b) = activation_base + b * sizeof(block_q8_Kx4)
```

其中 `n` 是命令内输出行，`m` 是 activation row，`b` 是 K-block。
`A_M4_INTERLEAVED` 对应 llama.cpp 的 `block_q8_Kx4` 语义：四个 `d`、四路交错的 `qs`
和四路交错的 `bsums` 总计 1168 B；首版只在 `M=4` 时接受该 layout。非 canonical stride
需要一次性 repack 或 RVV fallback，不在 descriptor v2 中增加任意 stride。

`W_R4_BLOCK_MAJOR` 的 final N microtile 必须由软件补齐到四个合法 block，但 hardware 只
更新 `n<N` 的 accumulator；`W_ROW_MAJOR` 则不读取 inactive row。两种 weight layout 与
两种 activation layout 必须产生相同的 active FP32 output。layout 只描述内存顺序，不
暴露 dot array 的周期级组织。

当前软件最佳基线使用 Q4_K x32 repack；它保留为 RVV baseline，不能要求 QBS 以 32 行
作为物理处理宽度。模型加载器为 QBS 单独生成 R4 layout，并记录 layout version、原始
shape 和 tail padding；转换后的有效 weight bytes 不变，只允许最后不足四行的 padding。

## 6. 微结构方案

```text
CVA6 first-pass decode (custom-2, ACCEL_OP_LOAD)
          |
Ara dispatcher (descriptor pointer, activation pointer, M, vd)
          |
Ara sequencer (one Load-PE vid, destination hazard reservation)
          |
VLSU ownership mux
  |- ordinary AddrGen + VLDU + VSTU
  `- QBS engine
       |- descriptor fetch/validation
       |- page-aware MMU + two-outstanding read engine
       |- tagged block adapter
       |- activation bank + weight ping-pong banks
       |- Q4/Q6 profile decoder
       |- 4-row, 32-pair dot array
       |- correction slots + exact INT32 block subtotal
       |- FP32 command accumulator
       `- QBS-to-LDU commit adapter
                         |
existing LDU lane result ports -> existing VRF bank arbitration
```

### 6.1 现有 Ara 中的具体接入边界

Ara 当前只有 `NrLanes+4` 个 PE response slot，并把 Load/Store/Mask/Slide 放在固定全局
offset。新增独立 `VFU_QBS` 会扩大 sequencer running bitmap、queue counter、PE response
数组和 lane result arbitration，而 `ara.qbexec` 实际只有一个整体完成条件。首版因此不
新增 VFU/PE：

- `ara_op_e` 增加 `VQBEXEC`；`vfu()` 和 `target_vfus()` 将其映射到 `VFU_LoadUnit`，
  `is_load()` 与 `no_src_vrf()` 显式包含它；
- first-pass decoder 对 `ara.qbexec` 设置 `rs1/rs2`、`ACCEL_OP_LOAD` 和 `vfp`，但不声明
  scalar `rd`；对 `ara.qbinfo` 声明 `rs1/rd` 和 `ACCEL_OP`。Ara dispatcher 直接完成
  `qbinfo`，只把 `qbexec` 送入 sequencer；
- dispatcher 将 `rs1/rs2` 放入既有 `scalar_op/stride`，设置 `use_scalar_op=0`，并合成
  EW32、`vm=1`、`vstart=0`、由 M 得到的 `emul` 和覆盖 M 个完整寄存器的 internal `vl`，
  但不修改架构 `vl/vtype` CSR。它还必须设置 `ignore_zero_vl_check`，避免当前 CSR `vl=0`
  把 QBS 命令误判为 no-op。与 vector CSR/segment-memory 的保守路径相同，`qbexec` 先经过
  dispatcher 既有 `WAIT_IDLE` 至少一拍，只有 `!ara_req_valid_o && ara_idle_i` 后才送 sequencer。
  custom decode 同时置 `is_vload=1`，确保 illegal/fault/success 均正确平衡 CVA6 的
  `ACCEL_OP_LOAD` pending counter；
- sequencer 用既有 physical-register hazard table 预留目的组，以一个 Load-PE `vid` 跟踪
  命令；`destination_wait_complete` 对 `VQBEXEC` 强制置位，使 RAW/WAW 消费者等待整个命令
  的 `vinsn_done`，而不是按 LDU result pulse 提前 chaining。QBS 没有 VRF source，不进入
  lane operand requester；
- VLSU 根据 `pe_req.op` 把 request 只路由给普通 AddrGen/VLDU/VSTU 或 QBS。新增的
  `normal_vlsu_idle` 必须同时覆盖 AddrGen queue/FSM、VLDU request/result/R outstanding、
  VSTU request/data/B outstanding 以及 AXI cut 内未完成 channel。QBS 只在该条件成立时
  拉高自己的 Load-PE ready；握手后锁存一次 request、撤销 ready 并置 `qbs_active`，下一拍
  才把 MMU/AXI/result mux 所有权切给 QBS。dispatcher 的 idle barrier 是功能保证，VLSU
  idle check 是局部防线，两者不允许用“若干固定等待周期”代替；
- QBS commit adapter 在 VLSU 内与 VLDU result output 做互斥 mux，继续使用每 lane 64-bit
  `ldu_result_{id,addr,wdata,be}` 和既有 VRF bank arbitration，不给 operand requester 增加
  新的 result source；
- QBS 只在 terminal success/fault state 产生一次 mux 后的 `addrgen_ack`、Load-PE
  `vinsn_done` 和 `qbs_load_complete`；`qbs_load_complete` 并入 VLSU 既有
  `load_complete_o`，dispatcher 再由既有 completion register 延迟一拍形成 CVA6 看到的
  `load_complete`。成功和 fault 都必须各自平衡一次 `ACCEL_OP_LOAD` pending count，但只有
  成功 terminal event 允许 `qbs_fflags_valid`。VLSU 增加只在该成功事件有效的
  `qbs_fflags_o/valid_o`，sequencer
  同步采样并通过新增的 `ara_resp_t.fflags/fflags_valid` 返回，dispatcher 再与普通 lane flags
  合并；不能把长命令期间的 QBS flags 接到无 transaction tag 的逐周期 lane flag 线上。

`ara.qbexec` decode 的 `vfp=1` 保证 `mstatus.FS=Off` 时非法，任意 accelerator instruction
commit 继续把 `mstatus.VS` 置 Dirty。当前 CVA6 的 accelerator fflags 路径会更新
`fcsr.fflags`，但没有把该事件纳入 FS-dirty 条件；接入 QBS 时必须同时把
`acc_fflags_ex_valid_i` 纳入 `mstatus.FS/vsstatus.FS` 的 Dirty 更新。否则数值结果虽然正确，
architectural FP state summary 仍不完整。

`QbsEnable` 不能在 CVA6 decoder 和 Ara datapath 中分别配置。首版在 `qbs_pkg.sv` 定义一个
由唯一构建选项产生的共享 elaboration constant，并在 `Bender.yml` 中把该 package 排在
`ara_pkg.sv` 和 CVA6 first-pass decoder 之前；first-pass decoder、dispatcher decode 和 VLSU
generate 共同引用它。`QbsEnable=0` 时 generate 完全移除 QBS，first-pass decoder 不识别
custom 编码，正常 RTL 行为必须与当前版本等价；启用但 idle
时，normal path 只经过由寄存器化 `qbs_active_q` 控制的窄 mux，profile decode 不得进入
普通 load 的组合关键路径。

现有源码的修改边界冻结为：

| 文件 | 必要修改 | 明确不做的修改 |
| --- | --- | --- |
| `hardware/include/qbs_pkg.sv` | 新增共享 enable、opcode/profile/layout/descriptor 与 dependency-free token 字段/参数 | 不依赖 `ara_pkg`，不保存运行时状态 |
| `hardware/include/ara_pkg.sv` | 增加 `VQBEXEC`，更新 `is_load()` | 不增加第八个 VFU enum |
| `hardware/src/cva6_accel_first_pass_decoder.sv` | 受共享 `QbsEnable` 控制的 custom-2 decode、GPR/FP/load 分类 | 不改变普通 RVV opcode decode |
| `hardware/deps/cva6/core/csr_regfile.sv` | accelerator fflags 有效时同步把 FS 状态置 Dirty | 不改变 fflags 数值合并规则 |
| `hardware/src/ara.sv` | `ara_resp_t` 增加 command fflags，连接 QBS/VLSU 信号 | 不增加 accelerator master |
| `hardware/src/ara_dispatcher.sv` | `qbinfo/qbexec` decode、ACC_CONS/vstart/encoding 检查、WAIT_IDLE、internal EW32/vl/emul | 不修改架构 vl/vtype |
| `hardware/src/ara_sequencer.sv` | LoadUnit mapping、`no_src_vrf`、destination `wait_complete`、terminal fflags | 不扩 `NrPEs/NrVFUs` 和 lane operand path |
| `hardware/src/vlsu/{addrgen,vldu,vstu}.sv` | 仅补齐可证明的 idle/outstanding 状态输出 | 不解释 QBS descriptor/profile |
| `hardware/src/vlsu/vlsu.sv` | normal/QBS ownership mux、QBS instance、LDU commit mux | 不建立第二个 AXI/MMU port |
| `hardware/src/vlsu/qbs_*.sv` | 新增第 6.3 节除 package 外的运行时模块 | 不修改普通 load/store datapath |
| Bender/Flist/build rules | 加入 package/module 顺序和唯一 `ARA_QBS_ENABLE` 定义 | 不让 decode/datapath 使用不同开关 |

`pe_req_t` 不新增 descriptor/activation pointer 字段：既有 64-bit `scalar_op` 与 `stride`
分别承载 `rs1/rs2`，`fp_rm/vl/vstart/vtype/vd/emul/id` 也全部可复用。只有 command-local
fflags 无现成带 tag 的返回路径，因此必须按上表扩展，不能借用逐 lane 的无 tag pulse。

### 6.2 为什么接在 VLSU 返回与 VRF 之间

当前 Ara 的普通 load 由 VLSU result queue 写入 lane VRF，随后 ALU/MFPU 通过 operand
requester 再读出。K-quant 软件随后还会把 unpack 和 widened intermediates 写回 VRF。
QBS block subrequest 在数据进入普通 VLSU writeback arbitration 前分流，直接写 block buffer，
从结构上消除“压缩 payload 写 VRF -> 再读 -> 展开值再写 -> 再读”的往返。普通 RVV
load/store、MFPU 和 VRF 端口不改变。

普通 AddrGen 不能直接作为 QBS 内部 sequencer：它一次解释一个 `pe_req` 的 SEW/VL 地址
流，不能表达 descriptor、weight 和 activation 三种长度与地址公式。`qbs_read_engine`
只复用 VLSU 已有的外部 MMU/AXI 接口和 store-order gate，不复制第二个 master；这比生成
数百条内部伪 vector load 更小，也更容易证明完成和异常语义。

### 6.3 模块划分与控制状态机

| 模块 | 主要职责 | 不应承担的职责 |
| --- | --- | --- |
| `qbs_pkg.sv` | opcode/profile/layout/descriptor/token 类型和常量 | 运行时状态 |
| `qbs_engine.sv` | active command、主 FSM、循环计数、fault/complete | 直接解释 AXI beat |
| `qbs_read_engine.sv` | page split、MMU、AR、RRESP、tag FIFO | profile 数学 |
| `qbs_block_adapter.sv` | 按 role/offset 组装原生 block 和 metadata | 地址翻译 |
| `qbs_profile_decoder.sv` | Q4 scale/min、Q6 bit-plane、Q8 side metadata | command 调度 |
| `qbs_dot_array.sv` | 32 pair/cycle、group partial sum | FP32 累加 |
| `qbs_correction.sv` | group scale/min/bsums 与 INT32 subtotal | AXI/VRF |
| `qbs_fp_update.sv` | 16-entry stream-private state table、fpnew micro-op 调度和 fflags | block 读取 |
| `qbs_accumulator.sv` | banked 128-entry FP32 command accumulator 和 valid bitmap | 输出存储 |
| `qbs_commit.sv` | accumulator 到 LDU result 的 shuffle/address/BE | 普通 VLDU queue |

主 FSM 至少包含：

```text
IDLE -> ACQUIRE_VLSU -> FETCH_DESC -> VALIDATE -> CLEAR_ACC
     -> LOAD_ACT -> LOAD_WEIGHT_0 -> COMPUTE
     -> DRAIN_CORRECTION -> NEXT_N_MICRO / NEXT_K_BLOCK
     -> FINAL_DRAIN -> COMMIT -> COMPLETE -> IDLE

任一读取/验证错误 -> FAULT_DRAIN -> FAULT_RESP -> IDLE
```

`ACQUIRE_VLSU` 是 request 握手后的单周期所有权切换，并断言 `normal_vlsu_idle`；它不是
按经验等待排空的状态。`FETCH_DESC` 复制完整 16 B；`VALIDATE` 检查 version、reserved、profile/layout pair、M/N/K
上限、vd alignment、`vstart==0`、base alignment，并用 65-bit 中间地址检查全部 canonical
range 计算不会越过 XLEN 地址空间；地址公式溢出按 invalid command/illegal instruction
拒绝。translated
segment 再执行 idempotent normal-memory rule。`CLEAR_ACC` 在一个周期
清除 accumulator valid bitmap，不串行写零 128 个 data entry。`COMPLETE` 与 `FAULT_RESP`
各自只能触发一次 sequencer response 和 `vinsn_done`；`load_complete` 由 dispatcher 的既有
completion register 延后一拍形成，也必须恰好一次。

### 6.4 Read engine 与 block assembly

读引擎以 byte range 为单位，不假设 144/210/292 B block 与 128-bit AXI beat 对齐。每个
range 按以下步骤处理：

1. 按 4 KiB page、AXI 最大 burst 和目标 buffer 剩余空间切分；
2. 等待更老 core store 排空，向 accelerator MMU 翻译当前虚拟页；
3. 检查 translation exception，并用同一条 cached-region rule 覆盖包含 head/tail alignment
   padding 的整个 physical AXI transfer range，同时确认它与所有 non-idempotent rule 均不相交；
4. 生成 aligned AR，并记录 leading offset、有效 byte 数和语义 tag；
5. R beat 只把有效 byte 写入 tag 指定 entry，`R.last` 校验长度并弹出 tag；
6. `RRESP!=OKAY` 记录 load access fault，停止新 AR 并 drain 已发出的 response。

首版最多两个 AR burst outstanding，使用同一 AXI ID保证返回顺序，tag FIFO 深度为 2。
这与“一个 active command”不同：前者隐藏 page/burst latency，后者避免两份架构完成状态。
所有 byte/cycle counter 只按真实 handshake 更新。

每个计划的 page/burst segment 还分配单调递增的 16-bit `subreq_seq`，包括在 translation
阶段就 fault、尚未形成 AR 的 segment。观察到任一 fault 后停止分配新 segment，但先 drain
所有更早已发请求；若更早 tag 随后报告 `RRESP` error，以更小 `subreq_seq` 替换 fault
record。只有 drain 完成后才冻结最终 cause/tval，因此报告的是程序定义的 logical
subrequest 顺序最早 fault，而不是电路最早看到的 fault。

block adapter 按 tag 和 byte offset 将 payload 与 metadata 写入同一 entry。weight bank 按
四个 output row 分 bank；activation bank 按最多四个 context 分 bank。block 完整时一次
解码 side metadata：Q4 得到八组 6-bit scale/min，Q6 得到十六个 signed scale，Q8 得到
`d_x` 和十六个 signed bsums；payload 保持压缩形式供 dot array 按需读取。

`A_M4_INTERLEAVED` 的 1168 B 映射也必须固定：先是四个 FP32 `d[m]`，随后
`qs[4*i+m]=A(m).qs[i]`，最后
`bsums[8*g+4*h+m]=A(m).bsums[2*g+h]`，其中 `m=0..3`、`i=0..255`、
`g=0..7`、`h=0..1`。这与当前软件 `block_q8_Kx4` 一致；若未来更改 interleave，必须使用
新的 activation layout ID。

### 6.5 计算宽度与 correction

当前 128-bit AXI 峰值为 16 B/cycle。忽略 activation 重用后的边际开销，Q4_K 的 4.5
bits/weight 对应约 28.4 weights/cycle，Q6_K 的 6.5625 bits/weight 对应约 19.5
weights/cycle。因此首版可以保留 32 pair/cycle 的物理峰值，但不应把它实现成 32 个输出
行的大 buffer。更合适的物理 micro-tile 是 `4 output rows x 8 K positions`：Decode 每周期
对 4 个输出各处理 8 个 K 元素；`M=4` Prefill 则重映射为
`4 output rows x 4 input contexts x 2 K positions`。两种映射都使用 32 个乘法对。

一个 4-row Q4 tile 为 `4 x 144 = 576 B`，以 16 B/cycle 装载需要至少 36 cycles，而
`4 x 256` 个 pair 的理想计算时间为 32 cycles，因此 Decode 自然接近带宽平衡。Q6 tile
为 `4 x 210 = 840 B`，至少需要 53 cycles，物理阵列会受内存限制到约 19.5 pair/cycle；
Prefill 因相同 weight tile 被四个 activation context 使用，计算时间增至 128 cycles，
阵列可接近满载。

dot array 分成四个 row cluster，每个 cluster 八个低比特 x INT8 pair。M=1/2/3/4 时每个
context 分别获得 8/4/2/2 个 K position；M=3 有两个 pair/cluster 空闲，峰值 utilization
为 75%。weight 在 M context 间广播，activation 在四个 row cluster 间广播。每个
`{row,context}` 保存当前 group partial sum。

局部 buffer 的真实读端口按“广播前的数据”配置，而不是按 pair 数简单复制。weight buffer
分四个 row bank，M=1/2/3/4 时每个 bank 分别提供 8/4/2/2 个 quant，总数为
32/16/8/8；activation buffer 分四个 context bank，每个 active bank 同样分别提供
8/4/2/2 个 Q8 byte，总数为 8/8/6/8。weight 在 context 间广播，activation 在 row
cluster 间广播后形成 32/32/24/32 个有效 pair。Q4 bank 读取所需 nibble，Q6 bank 同周期读取对应 low4/high2 plane，
profile decoder 在寄存器边界后组合。建议流水级冻结为：

每个 weight row bank 内再按 payload plane 分子 bank：Q4 使用一个 `qs` 子 bank，Q6 使用
独立 `ql` 与 `qh` 子 bank，side metadata 使用小寄存器阵列。不能期望一个单端口 SRAM 在
同周期读取相距 128 B 的 Q6 low/high plane。Block Adapter 在填充时按 profile 将原生 byte
写入对应子 bank；这只改变物理 banking，不改变 token 的原生格式语义。

```text
S0  schedule: {block, n_micro, row, context, k_cursor} -> bank address
S1  synchronous buffer read + Q4/Q6/Q8 unpack
S2  4 clusters x 8 signed products
S3  registered adder tree + stream-private group accumulation
S4  group-complete pulse -> correction slot
```

S0 只有在 S1--S4 能接受时推进 k cursor；valid 与完整索引逐级寄存。最后不足四行的 N tail
在 S0 禁用 inactive row，不能在写回时才丢弃其错误计算。

group 完成是突发事件：M=4 的 Q4 可同周期完成 16 个 row-context group。首版为 16 个
`{row,context}` 各设一个 correction slot，而不是做 16-way multi-push FIFO。round-robin
scheduler 每周期消费一个 Q4 slot或两个 Q6 slot；每条 stream 的下一 group 到达间隔不
短于公平轮询清空当前 slot 的时间。稳定性边界可直接列出：

| Profile | M=1 | M=2 | M=3 | M=4 | Scheduler capacity |
| --- | --- | --- | --- | --- | --- |
| Q4_K | 4 slots / 4 cycles | 8 / 8 | 12 / 16 | 16 / 16 | 1 slot/cycle |
| Q6_K | 4 slots / 2 cycles | 8 / 4 | 12 / 8 | 16 / 8 | 2 slots/cycle |

表中“slots / cycles”表示一次同相 group-complete 突发及同一 stream 下一次突发的最短
间隔。M=1/2/4 的边界恰好等于 scheduler capacity，因此 slot 必须支持同一时钟沿的
`consume_old + refill_new`：scheduler 先读取旧内容，寄存器更新后保留新 group，不能先
清零再丢失 refill。round-robin 还必须保证任一 slot 在下一次同 stream group 到达前至少
被选中一次。RTL 断言应为
`group_complete -> (!slot.valid || correction_consume_same_slot)`，并另加有界公平性断言；
不能使用更强但在满吞吐边界会误报的 `group_complete -> !slot.valid`。下游 FP 更新不能
反压这些 slot，因此 correction 输出先进入独立的 16-entry FP update state table。

correction 共享两个 signed integer multiplier。Q4 每周期处理一个 slot，同时计算
`scale*dot` 与 `min*(bsum_even+bsum_odd)`；Q6 每周期处理两个 slot，各计算
`signed_scale*dot`。结果进入 signed-32-bit block subtotal；Q4 正项与 min 项分开保存，
Q6 保存一个 subtotal。每个 `{row,context}` 的最后一个 group 将完整 block subtotal 写入
同 index 的 FP update table entry；entry 保存 profile、accumulator index、整数 subtotal、
两个 block scale、`d_x`、当前 FP accumulator/intermediate 和微序列状态。Q6 每周期完成的两个 stream 写两个不同 entry，
不需要双写口 FIFO；同一 stream 的旧 entry 未清除前禁止再次写入。

一个本地、可每周期接收一条 micro-op 的 fpnew primitive 轮询这些 entry，执行第 3.5 节
固定的数值序列。Q4 每个 output 需要 6 条 FP micro-op，Q6 需要 3 条；最紧的 Q4 M=1
场景每 32 个 dot cycles 产生 4 个 output，即 24 条 micro-op，M=4 每 128 cycles 产生
16 个 output，即 96 条 micro-op，均低于单发射 FP primitive 的可用周期。Q6 余量更大。
fpnew 配置还必须保证相关结果反馈延迟不超过 4 cycles，使最小的 M=1 四 entry 轮询也能
隐藏依赖；scheduler 只选择 operands-ready 的 entry。因此 16-entry table 可吸收 block-end
突发且长期稳定。若实综合不能同时做到 initiation interval 1 和 feedback latency <=4，
必须降低 dot issue、增加 FP throughput 或显式插入 scheduler stall，不能靠丢弃/覆盖 entry。

### 6.6 统一的跨 shape 调度

首版不暴露 reuse-policy bit。统一 K-block-major loop 同时获得 activation 和 weight 复用：

```text
for b in 0 .. K_blocks-1:
    load all active A[m,b] into activation bank
    load W[n_micro=0,b] into weight bank 0
    for n_micro in 0 .. ceil(N/4)-1:
        compute W[n_micro,b] x all active A[:,b]
        while computing, load W[n_micro+1,b] into the other weight bank
        drain correction and update this block's FP32 outputs
    wait until every update for block b is complete
```

activation block 跨最多八个 N microtile 复用，weight microtile 跨最多四个 context 复用。
Decode 只有前一种复用，Prefill 同时获得两种复用，但使用同一控制器和 datapath。同一
output 的 FP32 block update 必须保持 K-block 地址递增顺序。

一个 activation bank 已能正确运行。只有 counter 证明 `LOAD_ACT` bubble 在小 N 上成为
关键瓶颈后才增加第二个 activation bank；首版先用 weight ping-pong 覆盖占比更高的流量。

### 6.7 FP32 accumulator 与写回

每个 4-row microtile 的整数 subtotal 在 block 边界进入一个本地流水化 FP32 datapath。
该 datapath 复用 fpnew primitive 和 `pe_req.fp_rm`，但不占 lane MFPU operand/result network；
Q4 对每个 output 更新正项与 min correction，Q6 更新一个 scale 项，flags OR 到 command
context。最大 accumulator 为 `4 x 32 x FP32 = 512 B`。

accumulator 物理组织冻结为 8 bank x 16 entry x 32 bit，逻辑 index 为 `m*32+n`，bank 为
`n[2:0]`。FP update 每周期至多写一个 bank；COMMIT 已在 `FINAL_DRAIN` 之后，不与 update
并发，可同时从八个 bank 读取连续八个 FP32 result，以匹配 4 lane x 64-bit 的 32 B/cycle
写回带宽。128-bit valid bitmap 在命令开始时单周期清零；第一次更新 valid=0 的 entry 时
以 `+0.0` 为旧 accumulator，避免串行 128-cycle data clear。对同一逻辑 output 的更新必须
按 K-block index 递增，scoreboard/assertion 禁止同一 entry 存在两个未完成 FP update。

`FINAL_DRAIN` 确认 read tag、correction slot、FP update table 和 FP pipeline 全空，且所有
active accumulator valid 后才进入
COMMIT。commit adapter：

- 依次选择 `vd+m`，按 EW32 的 `shuffle_index()` 和 `vaddr()` 生成每 lane result；
- `n<N` 写 accumulator，`n>=N` 写 `+0.0`，使整个 active register 获得一致 EW32 layout；
- 携带 QBS Load-PE `vid`，保持 request/data/BE 直到 lane grant；
- 4-lane、VLEN=1024 时每周期最多写 32 B，每个寄存器 4 cycles，M=4 最多 16 cycles；
- 最后一个 final grant 前不置 `vinsn_done`，消费者不会看到部分结果。

### 6.8 首版资源与时序边界

建议首版资源：

- 32 个低比特 x INT8 pair/cycle 的共享 dot datapath，物理组织为 4 个 row cluster；
- 两个 weight ping-pong buffer，单 buffer 容纳 4 个 Q4_K/Q6_K block，最大有效载荷
  840 B，可按 1 KiB 实现；
- 一个 1280 B activation bank，其中 1168 B 为四个 Q8_K context 的有效数据；
- 16 个 correction slot、两个共享整数乘法器和 signed-32-bit block subtotal；
- 16-entry stream-private FP update state table 和一个 initiation interval 为 1 的本地 FP32 micro-op datapath；
- 8-bank、128-entry FP32 accumulator 与 128-bit valid bitmap，覆盖一个 logical tile 的最大
  `32 output rows x 4 input contexts`；物理 dot array 仍一次只处理 4 个 output rows；
- 一个 active command context和 2-entry read-subrequest tag FIFO。

两个 weight buffer、activation bank 和 accumulator 本身为 3.75 KiB；计入 correction
slot/subtotal、16-entry FP update state 及其流水中间值后，首版 command-local data state
保守估计约 4.6--5.0 KiB，另加 tag、valid 和控制位。最终数字必须以综合后的 memory/flop
bit count 为准，不能把这一范围当作面积报告。该容量仍显著小于缓存 32 行完整 compressed
weight tile。weight/activation
arrays 必须按真实读取并行度 bank，并优先推断同步 memory；若目标库没有合适宏，再比较
latch/flop 实现。profile unpack、dot tree、correction multiply 和 FP update 之间分别寄存，
禁止形成跨四级语义的单周期路径。

首版参数冻结为 `MaxM=4`、`MaxN=32`、`MaxKBlocks=256`、`DotPairs=32`、
`ReadOutstanding=2`。后续可以综合/性能 sweep `DotPairs`、buffer 和 outstanding，但不得
改变 ISA/descriptor。软件 32-row repack 只是 RVV baseline；QBS 使用字节数不变的 R4
offline repack，并单独报告一次性转换成本和尾行 padding。

最大合法 Q6 命令的原生输入量为
`32*256*210 + 4*256*292 + 16 = 2019344 B`，有效 pair 数为
`4*32*256*256 = 8388608`。因此在 8 B/cycle 持续读带宽和 32 pair/cycle 下，纯读与纯 dot
下界分别约 252.4k 和 262.1k cycles；实际 QBS-Full 可部分重叠二者，但还需计入 activation
切换、correction、FP update、commit 和 memory stall。该计算用于给 watchdog、interrupt
latency 测量和性能 sanity check 定量边界，不是固定周期承诺。

### 6.9 必须随 RTL 实现的断言

断言不是收尾工作，而是模块接口的一部分。至少覆盖：

- **Decode/command**：reserved encoding 为零；M、vd alignment/range、N/K capability 和
  vstart 合法；一个 accepted `qbexec` 只锁存一次 request，并只分配一个 Load-PE vid。
- **Ownership/order**：`qbs_active` 时普通 AddrGen/VLDU/VSTU 不产生 MMU/AXI/result request；
  QBS 获得所有权前 `normal_vlsu_idle`；第一条 QBS memory request 前
  `core_st_pending_i==0`；normal/QBS AXI ownership one-hot。
- **Read protocol**：AR 不跨 4 KiB，`len/size/leading_offset/effective_bytes` 一致；tag FIFO
  不 overflow/underflow；每个 tag 接收恰好 expected bytes 和一个正确 `R.last`；fault 后
  不再发新 AR，但所有已发 response 均被 drain；单个命令内 `subreq_seq` 不回绕，fault
  priority comparison 始终使用尚未回绕的逻辑序号。
- **Token/profile**：entry 在全部 byte 到齐前不能 `compute_ready`；payload/metadata role、
  block/microtile/context/bank 始终匹配；任何 entry 不被覆盖或跨 command 复用。
- **Compute**：group completion 时对应 correction slot 为空或同周期被消费；同周期
  consume/refill 后 slot 保留新数据；round-robin 在下一次同 stream group 到达前必选中旧
  slot；目标 FP update entry 为空；整数
  intermediate 不溢出冻结位宽；同一 accumulator entry 至多一个 update 在飞，且 K-block
  index 严格递增。
- **Atomic commit**：存在未完成或可能 fault 的 read/tag 时无 QBS VRF write；fault command
  零 destination write；COMMIT 只写 `vd..vd+M-1`，inactive N 写 `+0.0`，M=3 的第四个
  reserved register 无 write；destination consumer 在 terminal `vinsn_done` 前不能解除
  `wait_complete` hazard。
- **Completion**：每个 accepted command 恰好产生 success 或 fault 二者之一；
  `addrgen_ack`、`vinsn_done`、command fflags response 和 dispatcher `load_complete` 均不重复；
  reset 后不存在旧 tag、slot、valid bit 或 terminal pulse。

仿真环境还必须保留一个受 plusarg 控制的周期 trace，按 command/tag 输出 FSM、MMU/AR/R
handshake、buffer state、dot issue、correction、FP update、accumulator write和 commit grant。
默认关闭，首错时只抓相关 command 和前后有限周期，避免依赖全量 FSDB 才能定位。

### 6.10 性能计数器与严格口径

计数器按真实 handshake 或真实执行事件递增，不能用“峰值乘 busy cycles”反推。当前
`QBS_PERF` 每条命令输出下列已实现字段：

| 类别 | 必需 counter | 事件定义 |
| --- | --- | --- |
| Command | `success`、`fault`、`busy_cycles` | terminal outcome 与 accepted command 的完整忙周期 |
| Exclusive phase | `phase_setup/activation/weight/compute/overlap/drain/scheduler/commit/fault/terminal_cycles` | 每个 busy cycle 只进入一个固定优先级类别；十项之和必须等于 `busy_cycles` |
| Memory | `read_ranges`、`translations`、`ar`、`r_beats`、`read_backpressure_cycles` | logical range、翻译、AXI handshake 和有效 R 被阻塞周期 |
| Outstanding | `read_outstanding_occ_sum/max/full_cycles` | 已发 AR 到对应 RLAST 之间的事务数积分、峰值和两槽均满周期 |
| Bytes | `payload_bytes`、`weight_bytes`、`activation_bytes`、`commit_groups` | 有效 R payload、被计算消费的输入字节和最终寄存器写回组数 |
| Compute | `useful_pairs`、`pair_capacity`、`dot_active_cycles`、`tiles` | 对 active M/N/K 有贡献的 pair、启用 slot、真实 dot 活跃周期和完成 tile |
| FP/acc | `fp_uop_issue`、`fp_table_occ_sum/max/full_cycles`、`accumulator_updates` | fpnew input fire、state-table 占用和最终 accumulator update |
| Full overlap | `weight_prefetch_wait_cycles` | 当前 tile 已结束但下一 weight bank 尚未完整，因而不能切换的周期 |
| Commit | `commit_backpressure_cycles` | commit 已有有效 lane write，但既有 LDU result port 未接受的周期 |

派生指标固定为：

```text
pair_utilization       = qbs_useful_pairs / qbs_pair_capacity
read_bandwidth         = (weight_bytes + activation_bytes + desc_bytes) / qbs_busy_cycles
traffic_amplification  = measured_input_bytes / native_required_input_bytes
read_outstanding_avg   = read_outstanding_occ_sum / busy_cycles
compute_overlap_ratio  = phase_overlap_cycles /
                         (phase_compute_cycles + phase_overlap_cycles)
input_wait_ratio       = (phase_activation_cycles + phase_weight_cycles) / busy_cycles
```

`pair_capacity` 只在 dot scheduler 实际允许发射的周期累计已启用 physical pair slot；M=3 的
结构性空槽因此进入分母，memory stall 周期不进入。phase 分类采用固定优先级并保持互斥，
其和严格覆盖 QBS busy cycle；AXI backpressure 和 outstanding 则是可与 phase 同周期发生的
接口诊断信号，不能再次与 phase 相加。显式的 weight/activation block load/consumer-use 和
correction-slot stall 尚未作为独立字段导出，因此当前不能从 byte 或 tile 数反推严格复用率。

## 7. 量化目标与停止条件

### 7.1 性能目标

目标不是任意指定。采用比峰值保守的工程包络：AXI 仅持续达到 8 B/cycle，Q4 dot 达到
24 pair/cycle，Q6 dot 达到 16 pair/cycle，并在 memory/compute 较大者上再增加 25% 的
token、correction、tail 和流水开销；同时计入 logical `N=32` 命令重复装载 activation 的
流量。由此六点的估算上限分别约为 6.8x、6.8x、23.9x、4.7x、4.7x 和 12.4x。该计算只
用于判断设计是否有足够 headroom，不替代 RTL 结果；它说明下面的最低目标有物理依据，
同时给 Q6 decoder、异常处理和结果写回保留了较大折损空间。

目标均相对第 2.2 节的最佳正确 RVV 软件：

| 类别 | 最低目标 | 进取目标 |
| --- | ---: | ---: |
| Q4 Decode matmul speedup | 4.0x | 6.0x |
| Q4 Prefill matmul speedup | 3.0x | 4.0x |
| Q6 Decode matmul speedup | 6.0x | 10.0x |
| Q6 Prefill matmul speedup | 4.0x | 6.0x |
| 六点几何平均 | 4.0x | 6.0x |
| QBS 有效 pair utilization | 60% | 75% |
| Q6 AXI/原生流量 | <=1.30x | <=1.15x |
| vector request 与 VRF bytes 降幅 | >=70% | >=85% |

物理目标：新增面积不超过 Ara vector subsystem 的 10%，目标频率下降不超过 5%，相对
最佳 RVV 软件的能效提高至少 2.5x。所有 Q4_K/Q6_K 点必须与 llama.cpp reference 在
当前容差下通过，硬件不得通过重新量化改变模型数值。

### 7.2 可证伪条件

以下任一结果出现时，当前主张需要缩小或重构：

- `QBS-Serial` 相比最佳 RVV 不能降低至少 70% 的 VRF bytes 或 vector requests，说明
  直接块流没有解决已测瓶颈；
- shape-derived reuse 相比 `QBS-Serial` 不能显著降低 Q6 AXI bytes，或 Q6 的 AXI traffic
  amplification 仍高于 1.5x，说明跨消费者复用没有起作用；
- ping-pong/2-outstanding 相比串行 QBS 不能降低 input-wait cycles，说明 memory/compute
  overlap 不是当前有效机制；
- 机制只对固定 `M=4` 或固定 N 尾部有效，N/M/K sweep 出现明显不可解释退化；
- 新增面积超过 15% 或频率下降超过 10%，且系统级能效不足 2x；
- 只能支持 Q4_K，Q6_K 需要完全独立的数据通路，无法支撑共享 profile engine 的论点。

## 8. DATE 实验设计

### 8.1 必须比较的版本

1. upstream/标准 RVV 可运行基线；
2. 当前最佳 VLEN=1024、多输出 repack RVV 软件；
3. `QBS-Serial`：完整 profile 算术与直接 VLSU-to-QBS block stream，但每次只保留一个
   consumer 所需 block，关闭跨 N/M 复用、weight ping-pong 和第二个 outstanding；
4. `QBS-Reuse`：在相同 datapath 上打开由 M/N shape 推导的 activation/weight 复用，
   memory 与 compute 仍串行；
5. `QBS-Full`：再打开 weight ping-pong 和两个有序 outstanding，使 memory/compute 重叠。

三种 QBS 配置使用同一 opcode、descriptor、profile、layout、数值顺序和 destination
语义，只通过 elaboration/验证开关改变内部调度，不能让软件选择隐藏 policy。standalone
Q4/Q6 block engine 另行报告 peak pair/cycle、correction 和 FP update 吞吐，用于说明算术
上限，但不伪装成可直接与完整 GGML kernel 比较的系统版本。

软件优化只定义第 2 项基线，不作为消融梯度或论文贡献。

### 8.2 工作负载和图表

- 六个真实数据切片全部报告 correctness、cycles、speedup、requests、VRF read/write bytes、
  AXI bytes、pair utilization、buffer stall 和 accumulator occupancy。
- 为避免结论只适用于 Qwen2.5-1.5B，最终至少从第二个 GGUF Q4_K_M 模型抽取 2--3 个
  不同 hidden/intermediate shape 的 Q4_K/Q6_K 线性层切片。若时间不足，论文必须把
  结论限定为已测模型和 shape，不能直接声称覆盖所有 llama.cpp 模型。
- Q4_K/Q6_K 额外做 `K={256,...,8960}`、`N={16,...,full}`、`M={1,2,4,8,15}` sweep；
  `M>4` 由软件拆成多个 `M<=4` 命令，用于验证命令拼接和尾部，而不是声称硬件直接容纳
  8 或 15 个 activation context。
- 主性能图按 Decode/Prefill 与 Q4/Q6 分组，比较最佳 RVV、QBS-Serial、QBS-Reuse、QBS-Full。
- 机制图只画三条证据链：请求/VRF traffic 降幅、QBS pair utilization、AXI traffic
  amplification；不要堆叠不能相加的 stall counter。
- 面积图给出 Block Stream Adapter、buffers、decoder/dot、correction、accumulator 的
  breakdown；功耗用 PrimeTime PX 对相同六点的代表窗口评估。
- 至少完成 synthesis，最好完成 28 nm place-and-route，并报告 setup slack、频率、面积
  和 post-layout power。DATE 对只有行为仿真、没有物理代价的数据说服力不足。

### 8.3 公平性

- 所有版本使用相同真实 tensor 和 golden；offline repack 不计 token latency，但必须
  报告模型大小变化和一次性转换成本。
- baseline 取每个 shape 的最佳正确软件，而不是统一取最新提交。
- QBS speedup 只统计硬件实际执行的相同 timed region；不能排除 activation quantize
  后又把它计入 baseline。
- 行为级 L2 结果需补可调 latency/bandwidth sweep，防止 0-stall memory 掩盖系统限制。
- real-data slices 与完整模型推算分开报告，完整模型收益必须按真实层类型占比加权。
- 完整 Qwen token generation 至少在功能模型中使用同一 ISA 路径通过；RTL 过慢时可以用
  RTL operator cycles 对各层加权，但必须明确标成 model-level projection，而非实测
  tokens/s。

通用性验证与主性能点分开。主性能点使用真实 tensor；小尺寸 sweep 用 directed data
覆盖边界，不要求每个点都运行完整模型：

| 维度 | 必测值 | 回答的问题 |
| --- | --- | --- |
| Weight profile | Q4_K、Q6_K | 两类数学语义是否共享命令、token、dot 和 commit 主路径 |
| Layout | row-major、首版 repacked layout | format 与 storage layout 是否真正解耦；若首版只实现一种，必须收窄声明 |
| `M_total` | 1、2、4、5、15 | Decode、满 tile、跨命令拼接和 M-tail |
| `N_total` | 1、3、31、32、33、64、真实 N | N-tail、跨 logical tile 和不同纵横比 |
| K | 256、512、1536、8960 | 单 block、稳态 block stream 和长 reduction |
| Layer role | Q/K/V/O、gate/up/down 中的代表点 | 同一接口是否跨 Attention 与 FFN 使用 |
| Negative path | unsupported profile、K 非对齐、非法 layout | capability rejection 和标准 RVV fallback 是否正确 |

若论文声称 ISA 对不同 VLEN 具有实现可移植性，还必须至少用第二个 VLEN 配置验证
`qbinfo.max_N=min(32,VLEN/32)`、完整 destination-register zero fill 和软件 N 方向拼接；
若只综合 VLEN=1024，则只能声称 lane 数不进入命令语义，不能把未测的多 VLEN 写成
实验结论。`N<=32` 是 v1 tile 契约，不应被表述成任意 N 的单命令支持。

## 9. 分阶段实施与验收

实现按“先冻结语义、再验证算术、最后接系统”的顺序推进。任何阶段未通过 exit criteria，
都不进入下一阶段；不得在完整系统仿真里同时猜测 decoder、调度和异常三个问题。

### 9.1 Phase 0：可执行契约与基线冻结

先建立独立于 RTL 的 `qbs_ref`：解析 16 B descriptor 和四种首版 layout，逐字节实现第 3 节
Q4_K/Q6_K/Q8_K profile，并严格执行 numerical-contract version 1。reference 同时输出
每个 block 的 decoded quant、group dot、correction subtotal、逐 block FP accumulator 和
最终 destination image，便于从系统首错回溯到最小语义级。

必须冻结以下输入：六个真实 operator slice、14 点软件功能集、第二模型的 2--3 个线性层、
最佳 RVV cycles/traffic、descriptor/layout generator 以及 unsupported fallback。exit criteria：

- 原生 row-major 与 repacked layout 对所有 active output 产生相同结果；
- Q4/Q6 随机 block 的 integer intermediate 与 llama.cpp reference 逐位相等；
- numerical-contract output 逐位可复现，并在当前容差下通过全部真实 golden；
- descriptor/profile/layout/capability 文档与 C header 由同一常量定义或自动交叉检查。

### 9.2 Phase 1：无 datapath 的接入骨架

实现共享 `QbsEnable`、custom-2 first-pass decode、`ara.qbinfo`、`VQBEXEC` decode、Load-PE 映射、
destination reservation、dispatcher idle barrier 和 VLSU ownership mux。此阶段的 control
stub 允许 `qbexec` 走完 request/vid/terminal 生命周期，但只返回明确的 illegal exception，
绝不产生成功 response 或伪 VRF 结果；重点验证控制接口没有破坏普通 RVV。

exit criteria：

- `QbsEnable=0` 时 lint/elaboration/synthesis 通过，所有现有严格 RVV 随机回归与未修改 RTL
  行为一致，custom-2 产生标准 illegal instruction；
- `QbsEnable=1` 时 `qbinfo` 编码逐 word 正确，非法 reserved/M/vd/vstart 组合均拒绝；
- `CSR_ACC_CONS[0]=0` 时 `qbexec` 确定性 illegal，打开后标量 store pending/order directed
  test 通过；
- QBS request 只分配一个 Load-PE vid，M=1/2/3/4 分别预留 1/2/4/4 个寄存器，M=3 第四个
  register 不更新 EEW metadata；
- success、illegal 和 fault 路径都把 `ACCEL_OP_LOAD` pending count 恰好恢复到零；QBS
  fflags 只在 success terminal event 更新，并把 `mstatus.FS` 置 Dirty；fault 不改变 fflags；
- normal VLSU 与 QBS 的 MMU/AXI/result ownership 永不重叠，idle mux 不进入普通 load
  的新增长组合路径。

### 9.3 Phase 2：Standalone profile engine

在不接 Ara memory system 的 unit-test top 中实现 block adapter、Q4/Q6 decoder、32-pair dot、
correction slots、FP update table 和 banked accumulator。testbench 直接推送完整 native block，
逐级与 `qbs_ref` 比较，而不是只比较最终 float。

覆盖 `profile x M={1,2,3,4} x row={1..4}`、全零/最大/最小 quant、scale/min 边界、NaN/Inf/
subnormal scale 和随机 block。exit criteria：

- decoded quant、group partial、INT32 subtotal 逐位相等，最终 FP32 遵守固定运算顺序；
- correction slot、FP update table 和 accumulator 无 overflow/overwrite，M=1--4 稳态均满足
  第 6.5 节吞吐证明；
- standalone 实测达到 32 useful pair/cycle 的定义峰值，M=3 明确报告 75% structural utilization；
- 单独综合后 dot tree、profile decoder、correction 和 FP update 间不存在跨多级长组合路径。

### 9.4 Phase 3：Q4_K M=1 系统闭环

接入 descriptor fetch、MMU、page/burst split、2-entry tag FIFO、Q4 row-major/R4 weight read、
Q8 activation、atomic commit 和 command-local fflags。第一条端到端目标固定为完整
Decode Attention-Q，不先追求六点同时通过。

除正常地址外必须注入 descriptor/weight/activation page fault、AXI RRESP error、非幂次
对齐、4 KiB page 边界和 VRF grant backpressure。exit criteria：

- destination 在任意 fault 下逐位保持旧值，成功时全寄存器 EW32 写回且 tail 为 `+0.0`；
- 每个 subrequest 的 byte count、R.last、tag 和 fault virtual address 正确；
- terminal success/fault 各只有一次 response、`vinsn_done` 和 `load_complete`；
- Attention-Q 与 `qbs_ref` 通过，QBS-Serial 已显著降低 vector requests/VRF bytes；若仍未达到
  3x，先用 counter/周期 trace 定位，不进入 Q6 或扩大 buffer。

### 9.5 Phase 4：完整 profile、shape 与调度

在已通过的 Q4 M=1 路径上依次加入 M=2/3/4、N tail、K-block sweep、A_M4、Q6 profile，最后
打开 shape-derived reuse、weight ping-pong 和第二个 outstanding。每加一项都复用同一
descriptor 和 reference，不增加软件可见 policy bit。

最低 directed matrix 为：

```text
weight profile : Q4_K, Q6_K
layout          : W_ROW_MAJOR, W_R4_BLOCK_MAJOR; A_ROW_MAJOR, A_M4_INTERLEAVED(M=4)
M               : 1, 2, 3, 4
N               : 1, 3, 4, 31, 32
K_blocks        : 1, 2, 6, 35, 64, 256
address         : aligned, beat-misaligned, page-tail
```

exit criteria：所有合法组合通过、非法组合确定性拒绝；同一 output 的 K update 严格递增；
Q6 AXI/native traffic 不超过 1.30x；QBS-Serial、QBS-Reuse、QBS-Full 三档 counter 能解释
traffic 和 stall 的逐级变化，且开启 overlap 不改变任何功能结果。

### 9.6 Phase 5：GGML backend 与模型通用性

模型加载阶段按 capability 生成/缓存 R4 weight layout，runtime wrapper 构造 immutable
descriptor，并按 `M_total/N_total` 分块发出 `ara.qbexec`。所有 unsupported type/layout/
alignment/K/shape 明确走现有最佳 RVV kernel。先完成 `GGML_OP_MUL_MAT`，
`MUL_MAT_ID` v1 由软件计算 expert base 后复用相同命令。

exit criteria：六个高成本 RTL 点、14 点软件功能集、第二模型代表层和完整 token-generation
功能模型均通过；repack size/time、fallback 次数与端到端 projected speedup 分开报告。

### 9.7 Phase 6：物理闭环与最终去留

完成 DC、P&R 和 PrimeTime PX，分别报告 decoder/dot、block buffers、correction/FP update、
accumulator、read/commit control 的面积和功耗。若频率或面积越界，优先 sweep DotPairs、
memory banking 和 FP primitive latency，不改变 ISA/descriptor/numerical contract。

最终 go/no-go：Q4 系统闭环不能达到 3x 时停止扩 profile；Q4 成功而 Q6 无法共享主数据通路
时把论文范围收敛到 Q4；QBS-Full 相对最佳 RVV 的六点几何平均不足 4x、能效不足 2.5x，
或新增面积超过 15% 且无法通过参数缩放修复时，不维持当前完整 DSA 主张。

### 9.8 当前 RTL 检查点与可复现实验

截至 2026-08-23，Phase 0--4 已形成可执行闭环，Phase 5 的普通 `GGML_OP_MUL_MAT`
集成已完成端到端功能验证。当前实现已在统一 Q3_K/Q4_K/Q5_K/Q6_K/Q8_0/Q4_0 profile
datapath、shape-derived reuse 和 atomic commit 之上加入两个 weight bank 与两个有序 AXI
read outstanding，达到 `QBS-Full` 检查点。inactive weight bank 只预取同一 K-block 的下一
4-row microtile；当前整数结果全部送入 FP update path 且下一 bank 完整后才切换 bank。K-block
边界仍清除 activation 和两个 weight bank，不进行跨 K 猜测。read engine 使用两项 logical
range FIFO 和两项 burst-tag FIFO；所有 AR 使用同一 AXI ID，R 按 tag 头顺序交付，任一故障后
停止新 AR、排空已发 response，并按 subrequest sequence 报告最早故障。

Standalone 与系统级验证共同覆盖 descriptor validation、MMU/page/burst split、两个同 ID
outstanding、completion backpressure、先发现年轻 PMA fault 后返回年老 AXI fault、AXI
RRESP/RLAST、VRF backpressure、M=3 destination reservation、success/fault terminal balance
以及 fault 前 destination 不可见。六种 weight profile 均已通过 standalone numerical、
descriptor/command 和系统级 shape/layout 定向验证；其中 N=35 覆盖 32-row command 加
3-row R4 尾块，M=8 覆盖两个独立 M4 activation group。Q3_K、Q5_K、Q6_K 和 Q8_0 还使用
真实 Qwen2.5 权重、activation 与 llama.cpp golden 完成独立 QBS RTL 点验证。物理综合与
P&R 不属于当前检查点。

整模型验证使用 Qwen2.5-1.5B-Instruct Q4_K_M，在同一 RISC-V QEMU/Linux 环境中分别运行
普通 RVV 与 QBS correctness emulation。两条路径均完成 10-token prompt 和 2-token greedy
generation，输出逐字节一致。QBS 路径实际记录到 Q4_K 的 8,032 次 GEMV、2,656 次 GEMM，
以及 Q6_K 的 1,360 次 GEMV、432 次 GEMM，覆盖 decode M1、prefill M4、持久化 R4 repack
和格式分派。该 QEMU 结果只验证 GGML 集成、调度和数值语义，不用于性能结论；性能仍来自
等价真实模型算子的 QBS RTL/RVV 对比。

完整 Decode Attention-Q（Q4_K，M=1，N=1536，K=1536）的最佳正确 RVV baseline 为
1,495,946 matmul cycles。QBS 首个正确系统闭环为 293,329 cycles；将 R4 四行物理连续数据从
四个串行 weight range 合并为一个连续 range 后，结果保持 `mismatches=0`，matmul 降至
217,297 cycles，即相对 RVV 为 6.884x、相对合并前为 1.350x。该变化没有减少 payload、
native block 或 useful pair：48 条命令的 pair utilization 始终为 1.0；它只消除了与 R4
layout 不匹配的请求粒度。对应计数器如下：

| 指标 | 合并前 | R4 四行 range 合并后 | 变化 |
| --- | ---: | ---: | ---: |
| QBS busy cycles | 292,032 | 216,000 | -26.0% |
| read ranges | 9,552 | 2,640 | -72.4% |
| AXI AR | 9,840 | 2,928 | -70.2% |
| payload bytes | 1,411,968 | 1,411,968 | 不变 |
| useful pairs | 2,359,296 | 2,359,296 | 不变 |
| dot active / busy | 0.2525 | 0.3413 | +35.2% |
| payload B / busy cycle | 4.835 | 6.537 | +35.2% |

这一结果说明 Reuse 检查点的首个瓶颈是 read-range 启动开销，不是 dot-array capacity、
FP update table 或结果提交。QBS-Full 保持相同 ISA、descriptor、R4 payload、pair 数和 FP
运算顺序，在完整 Decode Attention-Q 上进一步得到：

| 指标 | QBS-Reuse | QBS-Full | 变化 |
| --- | ---: | ---: | ---: |
| matmul cycles | 217,297 | 133,861 | 1.623x faster |
| benchmark compute cycles | 228,939 | 145,503 | 1.573x faster |
| QBS busy cycles | 216,000 | 132,564 | 1.629x faster |
| payload bytes | 1,411,968 | 1,411,968 | 不变 |
| useful pairs / capacity | 2,359,296 / 2,359,296 | 2,359,296 / 2,359,296 | 不变 |
| dot active / busy | 0.3413 | 0.5562 | +62.9% |
| payload B / busy cycle | 6.537 | 10.651 | +62.9% |

QBS-Full 的 `read_outstanding_max=2`、平均 outstanding 为 0.866，两个槽同时占用的周期占
9.21%；compute-state 中 87.19% 的周期同时存在下一 weight range 活动。该点
`fp_table_full_cycles=0`、read/commit backpressure 均为 0，且 checksum、mismatch 和误差位型
与 QBS-Reuse 完全一致。相对同一最佳 RVV matmul baseline，单点加速由 6.884x 提升到
11.175x。该历史完整 Attention-Q 点用于解释 QBS-Full 的结构收益；多格式闭环必须另用
严格配对的当前 RTL、相同输入哈希和同一 llama.cpp golden 形成总表，不能把本单点替代为
跨格式几何平均。

六点 Q4_K/Q6_K 真实 Qwen2.5 回归使用独立目录，应用构建串行以避免共享 linker script 和 common object
竞争，仿真可六路并行且不会覆盖日志：

```bash
make -C hardware llama_qbs_eval_build
make -C hardware llama_qbs_eval_compile
make -C hardware llama_qbs_eval_parallel
make -C hardware llama_qbs_eval_status
make -C hardware llama_qbs_eval_sum
```

每个 case 分别生成 `result.csv`、`metrics.csv`、`qbs_perf.csv` 和逐命令
`qbs_commands.csv`；最后一个命令仅在六点均通过时生成套件总表。Q6_K/M1 还包含一个针对
staging hard-link alias 的生成器回归，保证 R4 输出不会原地改写 row-major source。

多格式闭环另取每种模型的 `blk.0.attn_q.weight` 前 256 个输出行，分别比较标准 RVV 与
QBS。汇总器要求两条路径的模型元数据、capture commit、shape、source weight、activation
和 golden 的字节数与 SHA-256 全部一致，并拒绝任一非 PASS 或 mismatch 非零的结果：

```bash
make -C hardware llama_format_sum \
  rvv_root=/path/to/rvv_format_eval_runs/TIMESTAMP \
  qbs_root=/path/to/qbs_format_eval_runs/TIMESTAMP
```

该表覆盖 Q3_K、Q5_K、Q6_K 和 Q8_0 的真实模型数据；Q4_K/Q6_K 的完整 token generation
也已通过，用于验证真实模型中 Decode GEMV、Prefill GEMM、持久化 R4 repack 和普通 RVV
fallback。

## 10. 最终论文贡献结构

适合 DATE 的贡献结构应保持一主两辅，并明确哪些思想继承自已有量化和流式架构：

1. **可扩展的后端量化块执行契约**：将 format、layout 和 execution mapping 分离；在
   Ara/RVV 后端中把 payload、metadata、块边界和复用期保持为 VLSU-to-compute token，
   并给出 capability、fallback、顺序、fault containment 和 atomic commit 规则；
2. **共享的 compressed-domain engine**：以 Q4_K 的仿射修正和 Q6_K 的 signed bitplane
   两类真实 profile 证明公共 block stream/dot/accumulator 可以承载不同 K-quant 语义，
   并明确 Q2/Q3/Q5 与 IQ/MXFP 的不同扩展成本；
3. **shape-derived lifetime/reuse mapping**：同一 K-block-major controller 根据命令的
   `M/N/K` 自然推导 activation 和 weight token 的 consumer count 与释放时刻，同时获得跨
   N 和跨 M 复用，不引入 Decode/Prefill 专属 mode 或软件调度 policy；以七类线性层、
   tail sweep、第二模型和物理实现验证收益与代价。

论文不能声称“首个 K-quant accelerator”，F-BFQ 已覆盖该范围；也不能声称“首个流式
量化 RISC-V”，SSR/MXDOTP 已覆盖相邻范围。论文的区别应落在一条可测的系统链路上：

```text
GGML block-quantized MUL_MAT semantics
  -> profile/layout/shape contract
  -> metadata-bound VLSU-to-compute stream
  -> compressed-domain execution and command-local reuse
  -> normal RVV exception, completion and destination state
```

这里允许 decoder、dot、buffer 和 accumulator 与已有研究有技术重叠。创新强度来自上述
端到端契约是否解决了实测的请求/VRF 膨胀，shape-derived reuse/overlap 是否比串行块流
获得额外收益，以及
是否跨格式、shape 和模型保持有效，而不是依靠把常见部件换一个名称。

## 11. 主要参考资料

- [RISC-V Vector Extension](https://docs.riscv.org/reference/isa/unpriv/v-st-ext.html)
- [RISC-V Toolchain Conventions: Extension Naming](https://github.com/riscv-non-isa/riscv-toolchain-conventions/blob/main/src/toolchain-conventions.adoc)
- [llama.cpp K-quant block definitions at the captured commit](https://github.com/ggml-org/llama.cpp/blob/316e72d38da2bf9af84f946fb6e99419d80849f9/ggml/src/ggml-common.h)
- [llama.cpp RISC-V repack backend](https://github.com/ggml-org/llama.cpp/blob/master/ggml/src/ggml-cpu/arch/riscv/repack.cpp)
- [F-BFQ: Flexible Block Floating-Point Quantization Accelerator for LLMs](https://arxiv.org/abs/2510.13401)
- [VMXDOTP: A RISC-V Vector ISA Extension for Efficient Microscaling](https://arxiv.org/abs/2603.04979)
- [MXDOTP: A RISC-V ISA Extension for Enabling Microscaling Dot Products](https://arxiv.org/abs/2505.13159)
- [Stream Semantic Registers](https://arxiv.org/abs/1911.08356)
- [SA-ANT: Efficient Low-Bit Group-Wise Quantization for LLMs](https://past.date-conference.com/proceedings-archive/2026/DATA/1613.pdf)
- [MixPE: Quantization and Hardware Co-design for Efficient LLM Inference](https://arxiv.org/abs/2411.16158)
- [QServe: W4A8KV4 Quantization and System Co-design](https://arxiv.org/abs/2405.04532)
- [QFactory: Compiler Support for Quantized LLM Inference](https://www.usenix.org/conference/atc25/presentation/zhang-qihao)
- [Quark: An Integer RISC-V Vector Processor for Sub-Byte Quantized DNN Inference](https://arxiv.org/abs/2302.05996)
- [Sparq: A Custom RISC-V Vector Processor for Sub-Byte Quantized Inference](https://arxiv.org/abs/2306.09905)
- [SPEED: A Scalable RISC-V Vector Processor for Multi-Precision DNN Inference](https://arxiv.org/abs/2401.16872)
- [XpulpNN: Flexible Inference of Quantized Neural Networks](https://arxiv.org/abs/2011.14325)
- [The RISC-V VecR Extension](https://eprints.gla.ac.uk/386005/)
- [RISC-V Vector-Matrix Extension Charter](https://riscv.atlassian.net/wiki/spaces/VMEX/pages/663912452/Vector-Matrix%2BExtension%2BVME%2BCharter)
- [SpacemiT RISC-V IME Extension](https://github.com/spacemit-com/riscv-ime-extension-spec)
- [DATE 2027 Call for Papers](https://www.date-conference.com/date-2027-call-papers)
