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
实际量化 K    -> 受控 gather 或正确维护的 R4 视图
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
