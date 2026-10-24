# 两头共享 K/V：正式运行时接入约束

## 目标与当前状态

目标是把已测得收益的两头共享递送接入现有 llama.cpp/GGML Attention，
而不是增加另一个仅供测试的后端。复用原有 AKV 指令、存储和 RVV 运算，
保留每个输出的累加顺序、状态标志、异常处理和普通 RVV fallback。

目前 `software/akv/experimental/paired_heads/native_bench.c` 只用于单线程
对照，其 `bench_active` 和 `bench_pair_enabled` 是全局可变状态。
不得直接把这个入口接入 GGML 多线程执行。当前三方完整算子测试和六头
PANEL4 测试仍在运行；以下是接入要求，不代表生产接入已经验收。

## 从现有调用链修改

正式入口继续使用 `akv_attention_execute_v2_native` 及其 features 路径，
不新增独立的 GGML 算子实现。现有计划和工作区检查通过后、第一次 FULL
之前，为本次调用选择 QK/PV 函数或局部调度模式。选择结果只存在于调用栈，
不得通过全局开关在不同调用间传递。

两头叶函数处理真实存在的两个 Query heads。包装函数按两头递进，奇数
尾头调用原 generic 函数。Decode 的 score 行距为 64 个 FP32，F16 部分和
行距为 256 个 F16；这两个固定工作区行距不得替换为有效 D。

F32 Prefill 的输出布局不同，行距按实际 D 和工作区契约计算，不能复用
Decode 的固定 512 B 部分和行距。F32 内核须独立验收，不能用 F16 Decode
的通过记录代替。

## 选择与回退

| 条件 | 行为 |
| --- | --- |
| D128、每组六头 | 保留已有六头 QK/PV 特化，不退化为三个两头组 |
| F16、D64/96/128、每组 2--8 头且设备能力满足 | 候选两头共享，奇数尾头走原 generic |
| 单头、D256 分段或其他不支持形状 | 保留原有路径 |
| 能力查询失败或缺少必要能力 | 在发出 FULL 前选择原有路径，不部分执行后重试 |
| 原 GGML 类型/布局/特性检查不支持 | 保留原 GGML/RVV fallback，不扩大准入条件 |

必要能力至少包含有效且启用的设备、F16 payload、足够的 q_rows 和 context、
token-axis 启用、64-token tile、row view、token tail、column PANEL4，
以及对应 D 的支持。D96 依赖 D-axis tail，不得仅凭 D128 能力放行。
能力检查本身的指令与周期必须计入完整算子性能。

不得捕获一次失败后静默改走 RVV：FULL 之后可能已建立设备状态或写入部分
结果，恢复必须沿原有生命周期和错误契约处理。函数选择不得改变 context
获取、释放和并发串行化规则；无全局开关不等于硬件天然支持并行 context。

## 数值契约

- QK 保持每个输出按 dimension 的原始 FP32 widening-FMA 顺序。
- Decode PV 保持原 F16 scale 转换、初始缩放及 token 顺序的 F16 FMA。
- generic 与 paired 在相同输入、初始 CSR 下要求逐位和 FCSR/VCSR 一致。
- 普通 RVV 与 AKV 保留各自原有数值路径，均需通过原始模型 golden 容差；
  不强制两者原始位模式相同。
- 负无穷 mask、特殊 features 和尾部不能通过虚构第二个 head 或额外无效
  FMA 来实现；复用原有 softmax/mask 逻辑。

## 接入前必须闭合的证据

1. 同输入普通 RVV、generic AKV、paired AKV 完整算子重复对照，包含准备、
   能力选择、QK、softmax、PV、归一化、输出完成，不只计叶函数。
2. 第二个真实上下文 KV256，保留捕获来源、原始 K/V/mask 和对应 golden，
   不复制 KV128 数据伪造长度。
3. 奇数头的完整调度，至少三头；验证配对部分、尾头、行间空隙和 guards。
4. 能力缺失、形状不支持、六头特化保持及 default/opt-in 选择测试；没有
   查询提供者的裸机环境必须按明确契约回退。
5. 实际 GGML 调用链测试，包括多线程调用的选择状态隔离。主测试和后端
   使用同一叶函数，避免把实验源码复制成独立实现。
6. 原独立 UVM/AXI 检查、生命周期、实际命令与流量核对、执行前后源码和
   镜像哈希一致。失败运行不能列入已验证性能结果。

以上完成后才能接受生产选择。完整模型收益仍需单独测量；减少片上 replay
不是减少 DDR 读取，命令 busy 和指令退休也不是浮点单元利用率。
