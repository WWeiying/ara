# 两头共享 K/V：正式运行时接入约束

## 目标与当前状态

目标是把已测得收益的两头共享递送接入现有 llama.cpp/GGML Attention，
而不是增加另一个仅供测试的后端。复用原有 AKV 指令、存储和 RVV 运算，
保留每个输出的累加顺序、状态标志、异常处理和普通 RVV fallback。

正式 native 入口现在包含调用内选择的 Decode 两头共享与 Prefill PV 调度，
分别以 `AKV_PAIR_HEADS=1` 和 `AKV_PREFILL_PAIR_PV=1` 显式开启，默认关闭。
`software/akv/experimental/paired_heads/native_bench.c` 仍只用于单线程
对照，其 `bench_active` 和 `bench_pair_enabled` 不能接入 GGML 多线程执行。
正式路径不引用这两个全局变量。六头 PANEL4、KV128 与 KV256
三方完整算子测试已经独立复核通过；这些仍是算子证据，不代表生产 GGML
接入已经验收。三方收据分别见
`verification/akv/results/paired-heads-threeway-20261024.json` 和
`verification/akv/results/paired-heads-kv256-threeway-20261024.json`。

## 从现有调用链修改

正式入口继续使用 `akv_attention_execute_v2_native` 及其 features 路径，
不新增独立的 GGML 算子实现。现有计划和工作区检查通过后、第一次 FULL
之前，为本次调用选择 QK/PV 函数或局部调度模式。选择结果只存在于调用栈，
不得用全局可变的执行状态在不同调用间传递本次选择。

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

当前外部 llama.cpp 的 `ggml/src/ggml-cpu/arch/riscv/akv.cpp` 已由 worker 0
执行完整节点，其他 workers 在节点屏障等待；不同 graph 的 worker 0 则由
`context_mutex()` 保护整个 FULL/REFILL/compute/RELEASE 生命周期。这一锁
不能缩短到单条命令，也不能因为引入调用内选择就移除。其 CMake 通过
`GGML_RISCV_AKV_RUNTIME_DIR` 编译共享的 native C 和汇编；正式接入应沿用
这条源文件路径，而不是在 `akv.cpp` 内另写一份配对内核。

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

## Decode 与 Prefill 的同源组合

`verification/akv/paired_heads/build_combined_candidate.py` 将已定向验证的
Decode 调度和 Prefill PV 调度组合到一份候选 native C 中，并将原汇编、
F16 配对叶函数和 F32 配对叶函数部分链接。两个转换的调用点互不覆盖，
选择仍在各次调用第一次 FULL 之前完成；两种 opt-in 相互独立。
两项组合检查与 GNU Linux C/汇编部分链接已通过。符号检查要求原 generic、
六头特化、features、Prefill API 和三个新增共享叶函数同时存在，不允许
`bench_active` / `bench_pair_enabled` 混入运行时。此处只是编译证据。

`build_ggml_candidate.py` 用独立 runtime overlay 交给现有生产 CMake：
实际 `arch/riscv/akv.cpp` 不重写，原有互斥和 GGML worker 协作不改变。
overlay 仅替换候选 C 与汇编入口，其余运行时源码和头文件指向当前规范
来源；不修改原运行时、外部 llama.cpp 或在跑测试的封存输入。

构建必须明确关闭默认启用、但本轮未纳入硬件契约的 `Zicbop`、
`Zihintpause` 与 BF16 扩展，实际命令仅允许 `rv64gcv_zfh_zvfh`。
C/C++ 固定 `-fno-fast-math -ffp-contract=off`，REFILL overlap 仍关闭。
每个 compile command 都重新核查，不能只看 CMake 选项显示已关闭。
接入前的候选构建有33个 GGML 编译单元通过，654个输入文件及产物哈希独立复核。
收据为 `verification/akv/results/combined-ggml-candidate-20261024.json`；
这些是接入前的候选记录；当前正式源码应使用下节的 live builder，不能
对已接入源码再次应用旧转换器。

生产 CPU 静态库编译成功只能证明接线和编译兼容，不能证明 native 数值、
多线程执行或完整模型通过。实际 native 路径继续由独立 VCS/UVM 验收；
现有 QBS QEMU 镜像未实现这些 AKV 自定义指令，不得用它的普通 RVV 或
软件 emulation 通过记录冒充 AKV native 执行。

## 正式源码接入与验收范围

规范 `src/akv_v2_native_riscv.c` 与已审查的组合候选逐字节一致；规范汇编
包含相同的两个已验证叶函数源文件，不另抄一份实现。新入口位于正常构建
范围，不依赖 D256 测试宏。GNU Linux 对象的指令及重定位记录与组合候选
相同。Standalone CMake 的3项宿主测试通过，实际 QBS+AKV GGML 的36个
编译单元也已通过，并独立复核了1006个输入文件及产物哈希。

Standalone 与 GGML 按源文件约束 AKV 的 `-fno-fast-math -ffp-contract=off`；
没有全局更改普通 GGML/RVV 或 QBS 的浮点选项。外部 GGML 的小补丁保存在
`software/akv/integrations/llama-cpp-fp-contract.patch`。当前外部源码修改
尚未提交，不代表已推送到其远程仓库。

规范源码接入后已重新编译并执行 Decode 的4种形状、12次 OFF/ON/OFF 调用，
不复用旧运行时对象。当前 worker 为正常 PASS；独立审计重新核对原始数值、
CSR、3680条命令、UVM/AXI及源码和镜像身份，并确认输出与接入前候选一致。
收据为 `verification/akv/results/canonical-decode-runtime-20261024.json`。
早期候选 worker 的文档漂移 FAIL 及其限定审计仍保留，没有改写为 PASS；
它不再是当前规范源码执行验收的替代证据。

规范 Prefill 也已重新执行并独立验收通过：原位置32--35、全部9个 Query /
3个 KV heads、D64、每次2304个输出，generic/paired 位模式及 CSR 一致，
均满足原 golden 容差。当前 ABBA 总周期404094降至380421，减少5.858%，
收据为 `verification/akv/results/canonical-prefill-runtime-20261024.json`。
这是同一完整切片内 generic AKV 与配对 PV 的对照，不是普通 RVV 基线或
模型级加速比，也不代表完整 M64 GGML 形状已经执行。

源码接入收据为 `verification/akv/results/paired-runtime-source-promotion-20261024.json`。
接入后的 Decode/Prefill 新 ELF 代表性 RTL 回归已闭合，完整 GGML 图与
模型级执行/测量仍须另行验收；不能用源码等价或切片通过冒充。原候选
生成器现在只用于固定接入前源码的测试，
会拒绝对已经接入的源码二次转换；当前 live 构建入口是
`verification/akv/paired_heads/build_live_ggml_runtime.py`，不是私有 runtime
overlay。后续重点是实际 GGML 调用和整模型测量，而不是重复旧候选转换。
