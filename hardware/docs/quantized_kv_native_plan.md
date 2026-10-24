# 量化 KV 的原生执行路线与准入条件

## 当前边界

当前 AKV 原生路径仍读取 F16 K/V；PANEL4 只改变列递送方式，不增加量化
格式。GGML 对 Q8_0/Q4_0 KV 有正常的原始执行路径，但这不等于 AKV 硬件
已经加速这些缓存。当前已通过独立 VCS 的完整量化 Attention 切片对照，
并完成默认关闭的 GGML 原生派发、真实缓存步长适配和短序列完整模型功能
验证。包含准入与 K 整理成本的配对 VCS 评估仍在进行。量化路径复用 QBS DIRECT、
标准 RVV 与原 online softmax，不把它描述为 F16 AKV 数据通路直接读取
量化 V。

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
实际量化 K    -> 连续行直接使用；已准入的交错布局按至多32行整理
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
heads、可见 KV128；导出张量的 K token stride 分别为136 B和72 B，恰好
等于四个量化块的行宽。但抽取图在导出前对 Q/K/V 执行了 `ggml_dup`，
因此这些步长描述的是整理后的张量，不能推断模型中的 KV cache 连续。
这两份整理后的数据可直接做 QBS DIRECT，其数据来源收据为
`../../verification/akv/results/quantized-kv-real-capture-20261024.json`。
当前 llama.cpp 的真实两-head KV cache 按 token 存放各 head；D128 时，
Q8_0 K 的 token/head stride 是272/136 B，Q4_0 则是144/72 B。共享 C
入口会检查非重叠、范围和实际步长，不能只删除连续行检查再直接发出
没有 stride 字段的 QBS descriptor。

已实现的接法对每个 KV head、每个至多32-token 面板整理原始量化字节，
供其 M4/M2/M1 Query 分组共用。仅复制可见行，不解码或重新量化 K，也不
保留跨调用 mirror。每次调用使面板缓存失效；连续行仍走零复制分支。
面板容量最大为 `32 * (256/32) * 34 = 8704 B`，与上下文长度无关；连同
原执行工作区及标签共13120 B，属于软件 scratch，不是新增硬件 SRAM。

| D128、两 KV heads | Q8_0 K | Q4_0 K |
| --- | ---: | ---: |
| KV128 的有效压缩数据 | 34816 B | 18432 B |
| 每次完整 gather 的额外读加写 | 69632 B | 36864 B |
| 每个新增 token 的两-head 编码数据 | 272 B | 144 B |

表中额外读写是有效 K 全部整理时的静态字节量，不是实测 AXI 流量。
最后一行不是已经实现的增量更新成本。R4 mirror 若跨调用保留，需要绑定
cache slot、generation、覆盖/清除/搬移；现有整矩阵 repacker 不能直接当作
append helper。当前采用上述有界 gather，其成本纳入新的 VCS 询证；不能
把连续捕获切片的周期直接当成真实交错 cache 的周期。

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
接入必须核对生命周期预约与执行互斥的关系，不能在部分原生执行之后透明
重跑 fallback。DIRECT 与持久 context 的具体关系见本文末节。

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

本计划不修改 RTL 或已封存的 Attention 实验。已通过的范围以下列实际
捕获、数值、完整切片和下文短序列模型证据为准；不以功能通过推断完整
模型加速比或长序列质量。

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
`verification/out/akv-quantkv-rvv-qbs-20261024-01`。这项16点测试本身不代表
完整量化 Attention 接通。生产编译后的 Q4_0 为先乘第一 scale
再融合第二 scale；Q8_0 为先乘两个 scale 再融合 dot。因此必须分别报告
其与 QBS 的位模式及标志差异，不以改变既有容差来取得通过。保留这一
准入条件，再接回原 quantized-V F32 PV；不以“已有真实捕获”替代验收。

多输出原生测试现已通过：两个捕获的全部12个 Query heads，以 M4+M2
计算各自完整12x128 score 矩阵，另加 M2/N31 与 M4/N1 的有效位置尾块。
共40条命令、3336个输出、24份目标量化 Query。每个硬件输出及每条命令
的累计异常标志均与独立主机 QBS 参考一致；实际工作量满足136768字节
payload、5128个逻辑读取范围，原始 UVM/AXI 与前后身份检查通过。
运行目录为 `verification/out/akv-quantkv-batch-qk-20261024-02`。
它不是全部输出的原 RVV 对照；不能把 QBS 与其参考模型的一致性写成
全部原 RVV score 均逐位一致，也不代表完整 Attention 或模型性能通过。

原批次因测试辅助函数读取未初始化向量尾部、随后被 printf 保存到栈而触发
缓存断言，其 FAIL 未改写。短对照仿真确认相同量化结果下断言由8次降至0次；
仅修正测试的无用标量读数，再以未放宽的完整检查重新执行得到上述 PASS。
没有为此修改 RTL、生产量化器或实际输入，详见
`verification/akv/quantized_kv/drain_probe_README.md`。

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

完整 Attention 的两个真实数据 ELF 已连接上述原语并进入独立 VCS 仿真。
各自使用实际 KV head 0、其全部6个 Query heads、D128和128个有效 token，
按 generic/shared/shared/generic 对照；完整计时包含 Query 量化、描述符、
QK、V 解码、softmax、PV 与结果落存。缩放值按固定 Qwen2 源码表达式
恢复精确 FP32 位模式，不把仅有六位有效数字的捕获 JSON 当作精确参数。
两种 K 格式现已完成全部四轮对照，原始结果经过独立重放，UVM/AXI、
镜像和前后版本检查均通过。每组的四轮768个输出逐位一致，FCSR/VCSR
也一致；与原模型输出的容差检查同时保留。

| 真实切片：D128、6个 Query heads、KV128 | 普通路径两轮周期和 | 共享路径两轮周期和 | 加速比 |
| --- | ---: | ---: | ---: |
| K=Q8_0、V=Q8_0 | 4,159,305 | 1,077,859 | 3.858858x |
| K=Q4_0、V=Q8_0 | 4,214,691 | 1,073,469 | 3.926234x |

这里两条候选路径仍调用原标量 V 解码器，收益来自 QBS QK 和跨 head 的
V 共享。数据不是整个模型的加速比，也不包含每次 GGML 调用的准入扫描。
实际周期、CSR、原始收据及边界见
`verification/akv/quantized_kv/attention_README.md`。

另有已完成独立重放的公共入口对照，计入映射、CSR 读取和逐次准入，
但输入仍是整理后的连续张量，不包含真实交错缓存的 K 整理：

| K 格式 | 双方 V 解码器 | 普通路径两轮周期和 | 候选两轮周期和 | 加速比 |
| --- | --- | ---: | ---: | ---: |
| Q8_0 | 同一个原标量解码器 | 4,229,050 | 1,396,517 | 3.028284x |
| Q4_0 | 同一个原标量解码器 | 4,248,081 | 1,387,385 | 3.061934x |
| Q8_0 | 同一个 RVV 解码器 | 2,578,265 | 1,096,039 | 2.352348x |

每一行是同一个 ELF 内的 ABBA 对照，输出和 FCSR/VCSR 全部精确一致，
原始模型 golden、实际命令和独立后端/AXI 检查均通过。第三行消除了双方
解码器实现不同造成的影响，但 V 解码次数、共享调度与 QBS 仍共同变化，
不能写成纯硬件收益。不同 ELF 的周期不可直接相减来归因某一项开销。
其余解码器/格式组合尚未进入本表，不能当成失败或通过；真实交错缓存的
周期也另待对应 VCS 验收，不沿用此表数字。
已通过项的原始周期、独立审计身份及口径汇总见
`verification/akv/results/common-cost-20261024-01/summary.md`；该批为6种
格式/解码器对照中的3项，不代表整组已经结束。

为避免日后 benchmark 与 GGML 各抄一套，另已封装共享 C ABI；全操作准入
在任何指令/输出修改之前完成，执行中失败不得静默重跑 fallback。其96项
主机连接测试、sanitizer与实际 RISC-V 编译不替代原生或模型验收。接入之前
仍要用同一入口重测真实数据并计入准入成本，详见
`verification/akv/quantized_kv/native_README.md`。

量化 V 解码另有标准 RVV 的 VLA 候选，只替换有限 Q8_0 解码，不改 Query
量化、QK或PV顺序。8轮真实数据对照和3584个有限浮点边界组合均已通过，
262144个真实输出精确一致，独立协议和原始证据重放通过。两份捕获的解码
配对加速比分别为3.741763x和3.742391x，周期降低约73.28%。这是解码器
自身的结果，不能与完整 Attention 的加速比直接相乘；目前未替换上述封存
实验的 V 回调。当前显式开启的 GGML 接入口已使用该 RVV 解码器；精度约束与收据见
`verification/akv/quantized_kv/value_decode_fast_README.md`。
默认生产选择仍须以完整入口收益、原模型容差及回退检查为门槛；当前的
GGML 接入是显式开启的测试分支，未新增 RTL、指令、SRAM 或默认开启的
生产快速路径。

## 实际 GGML 接入与剩余门槛

默认关闭的 `GGML_RISCV_AKV_QUANT_KV` 已接入现有 Attention 派发入口，
运行时还需显式开启量化路径及正常内存声明。实际 GGML 图通过原生 QBS
Linux QEMU：两种 K 格式各重复两次，全部12个 Query heads、两个 KV
heads、每次1536个输出；共64条 QBS 命令，六项 mask、线程和内存策略
回退均通过。它使用共享 C 入口和已验证的 RVV V 解码器，不是测试程序
绕过 GGML 直接调用内核。原始日志及714项输入身份已独立复核，收据为
`verification/akv/results/quantized-kv-ggml-live-20261024.json`。

上述受控图使用连续张量。真实缓存布局的后续验收同时覆盖连续和
token-major 交错视图、128/5 两个可见前缀、两种 K 格式及重复调用。
16次原生调用实际发出160条命令，整理40个面板，复制110656 B；全部
1536个输出、重复位模式、配对 FCSR/VCSR、输入保持和六项回退检查通过。
此处复制字节不是外部总流量；收据为
`verification/akv/results/quantized-kv-ggml-strided-20261024.json`。

新分支保持三态结果：完成、执行前回退、开始执行后失败。最后一种直接
报错，不能透明重跑普通路径。普通 RVV 和已有 F16 AKV 路径未被替换。
此处 QEMU 只证明原生指令功能和实际派发，不提供 RTL 周期或完整模型
性能。外部私有 llama.cpp 未自动提交；已将可复现源码补丁和基准提交归档
在 `verification/akv/quantized_kv/llama_integration_strided_20261024/`，其中明确
保留了已有私有修改，不能将所有补丁行都归因于本轮接入。

`ggml_decode.h` 已使用真实 `ggml_tensor` 定义完成元数据映射。Query 的
head 步长是 `nb[2]`，输出的 head 步长是 `nb[1]`；量化 K/V 的 `nb[0]`
表示整个32元素编码块，不是单个标量。映射成功不等于准入成功：公共 C
入口仍统一检查范围、别名、mask、数值域、设备和工作区，避免维护两套
不一致的条件或重复扫描全部 KV 数据。2048组布局/形状组合及两份原始
真实捕获已通过主机测试和 sanitizer，但这不替代实际 GGML 算子执行。

公共入口的两种格式 ELF 已完成构建，并在原完整切片验收、独立重放且
确认有收益之后自动启动 VCS。计时包含映射、CSR读取、全部逐调用准入、
Query量化、命令、Softmax、PV和完成排空；不把只测内部循环的收益当作
运行时收益。两种调度使用一致的显式浮点编译策略，原有 F16 AKV 源码
的编译策略不变。详见 `verification/akv/quantized_kv/common_attention_README.md`。

接入 GGML 时还必须取得从 tensor data 指针起实际可访问的内存范围，
确认是可由处理器访问的正常内存，而不是仅凭形状推算更大的分配范围。
初始映射只接收 `nth=1、ith=0`；`use_ref`、批量、多 Query token、不同
mask及未准入格式继续原路径。执行已开始后发生错误必须上报，不能让另一个
CPU worker透明重试并覆盖部分输出。线程间一致准入、多序列和不符合
有限值/零 mask 前缀要求的场景仍回退，不因模型短序列通过而扩大准入。

完整 Qwen2.5-1.5B-Instruct Q4_K_M 已通过原生 QBS QEMU 的短生成对照：
全部28层，四个 prompt tokens，每个独立 context 生成三个 tokens；
K=Q8_0/Q4_0、V=Q8_0 各有普通与候选一组。请求 context128，实际 runtime
向上取整为256。候选的112次 Decode Attention 调用全部原生完成，共448条
QBS 命令、224个 K 面板和128128 B 复制；多 token Prefill 的56次回退符合
当前范围。两种模式均输出 ` jumps over the`，六次 logits 对照的最大差、
RMSE、KL 均为0；投影也实际使用 Q4_K/Q6_K 原生命令而非软件模拟。
收据为 `verification/akv/results/quantized-kv-model-strided-20261024.json`。
这只证明该短序列的功能、布局和派发闭环，不是长文本质量或 RTL 性能。

当前共享实现为 `runtime_strided.c/.h` 和 `ggml_entry_strided.h`，保留
相同量化器、DIRECT 回调及逐 head token 顺序。完整切片的公开入口 VCS
对照现已另加真实交错布局，并让两条路径共用同一个 RVV V 解码器；计时
包含映射、准入和 K 整理。它不计 GGML 图调度及 backend host-extent 查询，
也不能将 QBS 加共享调度的收益写成纯硬件收益。已构建的尾块 RTL 测试另
包含5与33个可见 token，并导出实际 Query/QK score 逐位重放，避免只用
最终输出容差掩盖面板复用错误；其 RTL 结果仍待验收，不能预先记为通过。运行和验收范围见
`verification/akv/quantized_kv/strided_attention_README.md`。

### DIRECT 与既有 activation context 的关系

不能仅因两条路径都使用 QBS 就无条件清空已有投影 context，也不能未经
分析套用“等待 reserved=false”的互斥。`qbs.cpp` 的跨算子预约可能跨越
不修改原 activation 的普通算子；若新算子等待预约释放，而释放又依赖
同一图后面的投影执行，会形成集成层的潜在等待环。这是接入时要防止的
情形，不是现有运行时已经复现的故障。

当前量化 QK 使用 DIRECT。RTL `qbs_engine.sv` 仅在 FILL 模式产生
context写入/提交/中止，仅在 RELEASE 模式产生context释放；DIRECT
使用普通读路径，不产生这些持久状态操作。`qbs_activation_context.sv`
的 committed有效位也不因普通DIRECT请求而改变。因此当前静态逻辑支持
保留既有投影的 AQ 数据，而不是为了接入 Attention 强制废弃其复用收益。
软件桥在整个量化 Attention 调用期间持有 QBS 执行互斥锁，但不等待跨算子
reservation 释放，不修改其 owner、generation 或 resident 状态；外层
固定先取得 AKV 锁，再取得 QBS 锁。受限执行回调只允许 DIRECT，不能
借此发送 FILL/RELEASE。这个区别保证前后两个投影之间的 Attention
不会等待后面的投影先释放资源。

实际 GGML 三节点图已验证这一交错：投影 FILL/REUSE，量化 Attention，
投影 REUSE/RELEASE。两种真实 K 格式共四次原生生命周期，24条投影命令
和64条 Attention 命令；后续投影确实跳过量化，generation 和 activation
sequence 保持一致，投影输出逐位匹配，Attention 输出满足原容差且重复
一致。源码、原始轨迹及727项身份已独立复核，见
`verification/akv/quantized_kv/ggml_interleave/README.md`。
它仍不替代任意并发图、错误恢复、OS线程迁移或完整模型回归；不能将
单指令仲裁或这一受控图测试扩大解释为所有生命周期组合均已验证。
