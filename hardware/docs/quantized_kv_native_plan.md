# 量化 KV 的原生执行路线与准入条件

## 当前边界

当前 AKV 原生路径仍读取 F16 K/V；PANEL4 只改变列递送方式，不增加量化
格式。GGML 对 Q8_0/Q4_0 KV 有正常的原始执行路径，但这不等于 AKV 硬件
已经加速这些缓存。此项仍是 QBS/AKV 主线的未完成工作。

权重格式与 KV 格式不是同一件事。模型使用 Q4_K_M 权重，不表示 KV 缓存也
使用 Q4_K；必须读取实际 K/V tensor 的类型、步长和当前有效位置。

## 为什么不能先解成 F16 再直接使用现有 AKV

当前 GGML 量化 K 路径按 K 类型选择 `q_to_vec_dot` 和 `kq_vec_dot`。
Q4_0/Q8_0 K 与 Q8_0 Query 做整数点积，不是与 F16 Query 做浮点乘加。
量化 V 解为 F32 后使用 F32 输出累加；F16 V 使用另一种累加精度。
将两者一律转成 F16 会改变 Query 量化、点积和 PV 的数值契约。

源码依据为外部 llama.cpp 的 `ggml/src/ggml-cpu/ops.cpp`，尤其是
`q_to_vec_dot` 的选择、token 循环和量化 V 的 `v_to_float` 分支。
当前 `arch/riscv/akv.cpp` 的 F16 类型检查不能简单删除。

## 第一种原生候选：复用 QBS 计算量化 K 的 QK

把一个 KV head 的若干 token 看作权重矩阵的输出行：

```text
实际 Query F32 -> 原 GGML 的 Q8_0 Query
实际量化 K    -> 已核实的连续行直接使用；其他布局另行准入
                    |
          QBS：Query x K^T -> F32 score
                    |
原 mask / online softmax / RVV F32 PV -> 输出
```

QBS 已支持 Q4_0/Q8_0 weight 与 Q8_0 activation，D128 对应四个 32-element
block，不需要新增点积算术阵列。最初使用 DIRECT 命令，不借用或破坏正在被
其他投影保留的 activation context。这里的原生加速首先是 QK，不应写成
AKV 已实现量化 V 的片上递送。

以下仅为静态工作量：两 KV heads、每个 KV head 六个 Query heads、KV128，
按 M4+M2、N32 分块，需要 16 次 QK EXEC。它不含准备、搬运、score 写回、
softmax 和 PV，不能据此估算加速比。

## 必须先解决的三项约束

### 1. 缓存步长与更新

QBS descriptor 没有独立的 weight-row byte stride；行主序地址使用
`Kblocks * block_bytes`。实际 llama KV cache 的同 head 相邻 token 可能
跨过其他 heads 的存储，不能未经 tensor stride 核查就零拷贝接入。

现在已有两组新构建、完整来源固定的真实 Qwen2.5 Decode 捕获：K=Q8_0/
V=Q8_0 和 K=Q4_0/V=Q8_0。独立重验确认 D128、12 Query heads、2 KV
heads、可见 KV128；实际 K token stride 分别为136 B和72 B，恰好等于
四个量化块的行宽。同 head 的行已连续，因此这两组可以先直接以原缓存
基址做 QBS DIRECT，不必预先 gather。收据为
`../../verification/akv/results/quantized-kv-real-capture-20261024.json`。
这不是所有模型/布局的通用结论；仍按实际 strides 决定，不能默认创建
mirror 或把下表的可能搬运成本强加给已连续的缓存。

| D128、两 KV heads | Q8_0 K | Q4_0 K |
| --- | ---: | ---: |
| KV128 的有效压缩数据 | 34816 B | 18432 B |
| 每次完整 gather 的额外读加写 | 69632 B | 36864 B |
| 每个新增 token 的两-head 编码数据 | 272 B | 144 B |

最后一行不是已经实现的增量更新成本。R4 mirror 若跨调用保留，需要绑定
cache slot、generation、覆盖/清除/搬移；现有整矩阵 repacker 不能直接当作
append helper。第一版可先使用有界 gather，完整计入成本，收益不足则不部署。

### 2. 点积数值顺序

QBS 使用已定义的 scale product 和 FMADD 累加。当前 RVV Q4_0 源码的
`(sumi*dw)*dq` 与之存在乘法舍入顺序差异；Q8_0 的 `sumi*(dw*dq)` 也必须
核对生产编译后的 contraction 与累加顺序。量化字节相同不证明 score
逐位相同。不得静默更换原 Query quantizer 或放宽既有模型误差阈值。

先区分逐位一致、数值容差内一致和无法准入三类结果，再决定是否需要保留
原执行路径，或单独定义且验证不同数值顺序；不能把未验证路径默认打开。

### 3. Mask 和生命周期

GGML 的原 token 循环在 `mv == -INFINITY` 时直接跳过，不执行该 token 的
K dot 或 V 读取。因此不能批量计算原本被屏蔽、可能尚未初始化的 cache 行，
再仅在 softmax 前覆盖 score；这可能增加无效访问或浮点异常。

第一版应只接入已核实的有效连续前缀；其他 mask 形状在 issue 前回退。若将来
压紧可见 token，必须保留其逻辑索引和原 token 顺序，计入 gather/map 成本，
并测试带空洞的 mask。共享 QBS/AKV 的硬件仲裁不等于软件 reservation 安全；
完整操作需使用已有生命周期互斥，不能在部分原生执行之后透明重跑 fallback。

## 验证与实施顺序

1. 在真实模型中实际配置 Q8_0/Q4_0 cache，捕获 K/V tensor 字节、类型、
   strides、mask、实际 Q8_0 Query 和原始 score。旧 F16 capture 不能替代。
2. 用相同 query quantizer 与缓存字节核对 QBS QK 的逐位输出、FCSR 和异常
   边界；覆盖有效长度 63/64/65/128、两个 KV heads、尾块和屏蔽位置。
3. 接回原 online softmax 和量化 V 的 F32 PV，核对完整 Attention，而不只
   验证整数 dot。保留原始 token 顺序、softcap 和其他已有特性。
4. 检查 append、覆盖、清除、位置变换和非紧密 stride；当前无法满足的
   类型/形状/缓存状态必须在 issue 前回退。
5. 完整计时包含 Query 准备、gather 或 mirror 更新、所有命令、score 落存和
   剩余计算。只有完整算子实际受益且数值准入通过后才接入正式 GGML 选择。

本计划不修改 RTL 或当前封存中的 Attention 实验，也不宣称新模型/量化 KV
已经通过。优先完成当前 F16 列递送和跨头共享的完整算子评估，再推进此项。

## 当前数据闭环的位置

真实量化 K/V、F32 Query、F16 mask 和 Attention 输出已采集且独立核对。
捕获使用独立新建的 host binary/shared libraries，源文件、模型、输入、
二进制及张量哈希固定；没有改写旧捕获或使用 F16 normalizer。它完成的是
数据来源与布局检查，不是 RVV 或 QBS 计算验收。

当前数值测试已将完整、未改写的生产 RVV `quants.c` 目标文件与原始捕获
Query/K、QBS 原生执行和原始 QBS 参考模型链接在同一 ELF 中。它选择
Query heads0/6、各自 KV head 的 token0/63/64/127，共执行16条 QBS
DIRECT 命令，并导出目标量化器实际生成的四份136字节 Query。

主机检查直接读取这些导出字节，用主机浮点实现重新执行 QBS 参考；硬件
score、片内参考和主机参考的位模式及 fflags 必须一致。实际硬件记录还需
满足16条命令、144个逻辑读取范围和4096字节 payload，并通过独立 UVM
后端/AXI 读写检查、前后输入哈希与执行镜像核对。检查器及执行入口的
10项 host 测试已通过；它们不是实际 RTL 的计算结果。

16点原生数值测试已通过，独立复核了原始日志、实际 Query 导出、主机参考、
硬件工作量和 UVM。两种格式各8个 score 的位模式及浮点标志均与原 RVV
一致。收据为 `verification/akv/results/quantized-kv-qk-numeric-20261024.json`。
这一结果只适用于所测位置，不能由此消除不同舍入顺序的潜在影响。
原生执行入口为
`verification/akv/quantized_kv/run_rvv_qbs.py`，独立运行目录为
`verification/out/akv-quantkv-rvv-qbs-20261024-01`。尚不宣称量化 KV
Attention 已接通。生产编译后的 Q4_0 为先乘第一 scale
再融合第二 scale；Q8_0 为先乘两个 scale 再融合 dot。因此必须分别报告
其与 QBS 的位模式及标志差异，不以改变既有容差来取得通过。保留这一
准入条件，再接回原 quantized-V F32 PV；不以“已有真实捕获”替代验收。

多输出后续 ELF 已构建，使用两个捕获的全部12个 Query heads，M4+M2
计算各自完整12x128 score 矩阵，另加 M2/N31 与 M4/N1 的有效位置尾块。
共40条命令、3336个输出、24份目标量化 Query。严格批量检查器与独立
执行入口已经补齐，执行前检查及5项批量 host 测试通过。每个硬件输出
及每条命令的累计异常标志均需通过主机参考；实际计数还必须满足136768
字节 payload、5128个逻辑读取范围。它不是逐输出的原 RVV 对照，且不能
把当前16点的通过记录外推为全部 Query heads 或多输出已通过。

## 量化 V 与完整 Attention 的软件调度候选

生产 `ops.cpp` 的 quantized-V 分支把一行 V 解码为 F32，再调用
`ggml_vec_mad_f32` 累加到 F32 分子。它不是现有 F16 AKV 分子路径，不能
先转为 F16 再声称数值等价。Decode 的 M=1 不满足原 tiled 路径的 Query
长度条件；量化 K 也不满足原 F16/F32 split-KV 的类型条件。本候选需要
与这条真实生产分支比较，不人为关闭一个本来可用的快速路径。

实际 `ggml-quants.c` 已整文件编译，保留原 `dequantize_row_q8_0`；薄包装
只调用生产 `vec.h` 中的 F32 scale/mad，不复制或重写其 RVV 实现。当前
GNU 配置下 V 解码循环是标量 `fcvt.s.w/fmul.s/fsw`，scale/mad 是动态
VL 的 RVV F32 运算。该反汇编事实只属于本次编译配置，不代表所有工具链。
编译收据为 `verification/akv/results/quantized-kv-pv-primitives-20261024.json`。

共享候选位于 `software/akv/experimental/quantized_kv/online.h`：

1. 原调度按 head、token 递进，每个 head 都重新加载和解码 V。
2. 共享调度每次只暂存32个 token 的 score，用4/2/1个 head 的 QK 分组，
   每个 token 的 V 只解码一次，再分别更新这些真实 head 的 F32 分子。
3. 每个 head 内仍按原 token 顺序执行最大值更新、必要的分子缩放、FMA、
   `S=S*ms+vs` 及最终归一化。没有合并归约、丢弃尾头或额外转换成 F16。
4. 只为已完成 admission 的有限值、共享零 mask 有效前缀提供调度；softcap、
   ALiBi、sinks、mask 空洞和其他布局不因此取得准入。回调错误向上返回，
   已执行部分不能透明重跑 fallback。

两种调度共用逐 head 的数值步骤，并提供独立的完整 double softmax 参考。
320项 host 组合涵盖 D32/64/96/128/256、1--8个 head、token长度
1/31/32/33/63/64/65/128，输出与累计浮点标志逐位一致，padding未改写。
回调计数确认 V 解码从 `heads*tokens` 减到 `tokens`；还检查错误传播、
步长溢出及 signaling-NaN scale 的无副作用拒绝。

这些是调度和编译证据，不是量化模型或目标 RTL 的完整 Attention 验收。
下一步应把同一头文件与上述生产原语、真实 K/V/Query/mask/golden 连接，
完整计时包含 Query 量化、描述符、QK、V 解码、softmax、PV 与结果落存。
只有整段受益并通过原模型容差及回退检查后，才接入 GGML；当前未新增
RTL、指令、SRAM 或默认开启的生产快速路径。
