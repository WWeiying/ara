# FPGA 软件统一候选与端到端对照

## 当前结论与冻结决定

已完成 Qwen3-1.7B Q4_K_M、135-token prompt、F16 KV 的首组板上对照。
同一位流、单 worker，执行 accepted / generic / auto / auto / generic 五次。
五次正常退出，完整 token 与 logits 逐位一致。最后一个 generic 在观察门禁暂停后
补做，不是完全无间断 ABBA；accepted 只有一次，不能证明所有场景无回归。

| 程序 | 次数 | Prefill 均值秒 | Decode 均值秒 | 推理均值秒 |
|---|---:|---:|---:|---:|
| 原已验收版 accepted | 1 | 331.395450 | 346.688480 | 690.040 |
| 统一版 generic | 2 | 331.191105 | 345.203925 | 688.350 |
| 统一版 auto | 2 | 330.401555 | 339.824160 | 682.175 |

新增选路的独立比较是 generic 到 auto：Decode 时间减少 1.558431%，推理总时间
减少 0.897073%。accepted 到 auto 的推理加速为 1.011529x，不能与以前的
1.312x 或调用级 1.440x 相乘。Prefill 的差异未超过已观测波动，不能认定新增收益。

每次 42 条 logits 记录，每条 151,936 个 FP32；四组配对共比较 25,525,248 个值，
最大误差和位模式差异均为零。主机归档按内容去重保存一份原始 logits，五份板内
文件各自有哈希与四次 cmp 记录，不冒充五次独立主机下载。

第一次 auto 有 paired QK/PANEL4 和 paired PV 的实际退休 PC 证据；第二次 auto
的稀疏采样未捕获这些 helper，不能记为回退，也不能补成直接确认。纯模型加载、
QBS/AKV 算子分段耗时和内部重放命令数未单独测量。

据此保留当前候选和证据，但不晋升为全套板测交付。总推理收益没有达到本轮
大于 1% 且超过同臂观测极差的扩展门槛；该门槛是调度规则，不是统计显著性检验。
其余三组不扩展。用户已要求暂停继续挖掘既有机制收益，后续测试、profiling 或
优化须待进一步指示；本次整理不启动任务。

证据根目录：

```text
/home/wangwy/fpga_runs/fpga_unified_board_20261108_01/acceptance_report_07/
```

其中 `REPORT.md`、`analysis/summary.json`、完整证据包及其 SHA256 已归档。
`tools/verify_evidence.py` 重新核验 469 个文件通过；本仓库只提交数值摘要、身份与
证据引用，不提交大体积 ELF、logits 或压缩包。机读摘要为
`verification/performance/fpga_unified/board_first_case_20261108.json`。

## 构建阶段结果

统一候选已完成完整静态链接和本机控制逻辑检查，状态为
`HOST_QUALIFIED_BOARD_UNTESTED`。该构建阶段没有执行新模型或新板测；后续首组
板测见前节，不反向改写构建收据。

| 项目 | 结果 |
|---|---|
| 版本补丁和启动脚本单元测试 | 10 项通过 |
| QBS trace 原版/候选，GCC 与 Clang sanitizer | 4 个变体通过，日志和计数一致 |
| QBS SDK 回归 | GCC、Clang ASan/UBSan 两套通过 |
| AKV 实际 adapter 选路 | 6 个兼容组合通过 |
| AKV 纯策略矩阵 | 185,760 个组合通过 |
| 完整目标程序 | 218 个 object，最终静态链接通过 |
| 配置的逐文件 ISA/ABI 对照 | 280 个源文件与原板测记录匹配 |

正式交接包路径：

```text
/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/fpga_unified_20261108_03/board_bundle/
```

`result.json` 和独立编译审计在上述目录的上一级；原始编译和 host 测试证据保留在
相邻的 `fpga_unified_20261108_02/`，两者通过 source pins 绑定。

| ELF | SHA256 |
|---|---|
| 新统一版 `llama-f16-unified` | `dd558d625f007216f09fca96ec8fe5cbf5271f5cc52f0d43d6412e953e2a1123` |
| 原最快 F16 版 `llama-f16-accepted` | `d0a1bbfd9a23cf1d90e4c5c6d5b30e619a97d76bc99a3d0174d5ce20a849b570` |

配置的编译数据库还包含未选中的示例目标，不能把配置条目数说成实际编译的
object 数。主机 stub、sanitizer 和符号检查也不能替代新版本的板测数值验收。

## 1. 统一的内容

目标是把已经在板上有效的 QBS 软件优化与已通过代表性 RTL 验证的 AKV
自动选路放入同一个完整 llama.cpp 程序。此次不修改 RTL，不运行综合，不重新
生成位流，不替换板上现有程序，也不把新候选标为已经通过板测的交付版。

| 内容 | 固定来源 |
|---|---|
| 完整 llama.cpp，包括 M4 和原有量化 KV 源码 | `da56aa750559c180d631b466de983ff2bb5d54d9` |
| QBS/AKV SDK | `b7c9e6c3c1f8c5e469c130f46ec5bbfaf37a55d1` |
| QBS SDK 的等价板测修复版本 | `130730b5bb25eeba375a5b04eefb67d9e8635f34` |
| QBS 诊断查询补丁 | `verification/performance/fpga_unified/qbs_trace_context.patch` |
| AKV GGML 自动选路补丁 | `verification/performance/fpga_unified/akv_auto.patch` |
| AKV 自动入口的既有 RTL 验收 | `AKV_PAIR_FULL_CALL_OPTIMIZATION_20261107.md` |
| 已测完整源码的 Git 快照 | llama.cpp `ara-qbs-akv-unified-20261108`，`2d67251bf44e33e0b6e2ca1987ce0228edd56aaa` |

QBS 目录的 Git tree 必须与 `130730b5b` 完全一致。AKV SDK 相比板测交付
`1e48e205d` 只允许两个公开头文件、native C 入口和 `auto_policy.h` 四个文件
变化。计算汇编仍取自交付归档，不使用当前未提交的汇编。

这里不能用当前 llama.cpp HEAD 的干净归档直接替代交付源码：当前 HEAD
没有包含板测交付中的部分 M4、量化 KV 等文件。工作区保留的这些内容不能因为
构建版本统一而丢失。构建脚本使用交付提交完整归档，只修改两个 GGML adapter；
补丁后的 QBS adapter 必须与已验收板测候选的 SHA256 完全一致。

原构建采用“固定提交加固定补丁”。整理时另将相同的完整源码保存成上述候选
分支：父提交为 `da56aa750559`，仅 QBS 与 AKV 两个 adapter 不同，两个文件与
实际构建输入逐字节一致。没有切换现有 llama.cpp 分支、索引或工作文件，也没有
新建工作树。不要把当前脏工作区整体提交来重建候选。

快照分支已经包含两份补丁，不应再重复应用。历史构建脚本仍按原固定提交加补丁
复现，避免改变已封存的 producer 身份。SDK 必须仍固定为 `b7c9e6c3c`，不能仅靠
llama.cpp 的版本推断 SDK 或位流身份。原交付标签和已验收 ELF 不变。

## 2. 实际调用与改变的位置

```text
llama-simple -> libllama -> GGML CPU backend
  linear projection -> qbs.cpp -> QBS SDK -> native custom instructions
  attention         -> akv.cpp -> AKV SDK -> resident KV replay + RVV arithmetic
```

SDK 和 adapter 都编译进 `libggml-cpu.a`，再静态链接到 `llama-simple`，并不是
另外启动一个 SDK 程序。源码在独立构建输入目录中冻结，板上运行的 ELF 不需要
访问主机目录。

QBS 改动只把命令级 trace/lifetime 开关查询移动到一次阻塞调用的 context
构造阶段。计数、错误返回及日志保留，下一次调用会重新读取开关，不是永久
缓存全局环境变量，也不是关闭诊断换速度。

AKV 改动在 `AKV_PAIR_HEADS` 未设置时使用已有 cached device 和新 auto API。
显式设置该变量仍走旧入口。只有满足能力、形状和数值条件的调用才配对；奇数
head 的尾部、缺能力、特殊 score、D128/GQA6 和 D256 保留已有处理。

原有 worker 0、context mutex、FULL 到 RELEASE 的所有权、平台内存准入与
执行失败传播规则没有取消。不得在部分执行失败后通过重新运行来掩盖错误。

## 3. 构建与本机检查

入口为 `verification/performance/fpga_unified/build_v2.py`。输出必须使用
`ara_dsa_signoff_integration/verification/out/` 下一个不存在的新目录。

```bash
python3 -B -m unittest discover \
  -s verification/performance/fpga_unified -p 'test_*.py' -v

python3 -B verification/performance/fpga_unified/build_v2.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/fpga_unified_rebuild_01 \
  --jobs 8
```

脚本依次完成：

1. 检查板测交接清单、三个原 ELF、QBS runtime 和冻结测试的身份。
2. 从固定提交提取源码，检查补丁只修改两个 adapter，且未导入本地脏文件。
3. 用 GCC 和 Clang ASan/UBSan 对比 trace 的原版和候选，检查四组开关、两个
   profile、M1 至 M8、错误返回、输出及计数。这里的 native 调用由 host stub
   代替，只验证 C/C++ 控制逻辑，不作为硬件数值验收。
4. 分别执行 GCC 与 Clang sanitizer 的 QBS SDK 回归。
5. 编译实际 AKV helper，检查旧 SDK、新 SDK、关闭新宏与 portable 开关六种
   组合，包括 emulation、显式 override 和错误传播；执行 185,760 个策略组合。
6. 用 CVA6 SDK 工具链、Release/O3、静态链接编译完整 `llama-simple`。
   GGML 最终 ISA 为 `rv64gcv_zfh_zvfh`、ABI 为 `lp64d`。原生 F16 AKV C
   runtime 必须保留 `-fno-fast-math -ffp-contract=off`。
7. 核对最终 ELF 中的 auto API、QBS native 和 paired/PANEL4 符号，重新检查
   source pins，生成独立 `board_bundle/`。

量化 KV、Register-PV 与 Grouped Prefill 保留原有编译支持，但本次 F16
端到端对照明确关闭它们。编译存在不代表已经执行，更不代表重新验收了量化 KV。

成功状态为 `HOST_QUALIFIED_BOARD_UNTESTED`；检查 `result.json`、
`host-tests.json`、`compile-audit.json`、`composition.json`、`commands.json`
和 `source-pins.json`。失败目录与日志不能覆盖成成功结果，重试必须使用新目录。

首个准备目录 `fpga_unified_20261108_01` 因 Git 子目录过滤未实际应用补丁，
被源码差异检查拒绝，未进入编译。后继 `fpga_unified_20261108_02` 完成全部
host 测试及完整 ELF 链接，但旧检查器误将 CPU kernel 的 ISA 选项要求施加于
通用 GGML 层，原始状态保留 FAIL。正确规则是每个源文件的 ISA/ABI 选项及顺序
均匹配已板测的编译记录：通用层为 `rv64gcv`，CPU kernel 再追加 Zfh/Zvfh。
v2 对已完成产物重新核验全部 source pins、原始逐文件编译记录、浮点选项及
最终链接符号，另存独立结果，不重编译、不重跑硬件，也不把旧 worker 改成 PASS。
`--reuse-build` 仅接受这一种已证明的检查器误拒绝，不接受任意失败任务。

## 4. 板上应比较的三组

| Arm | 程序 | `AKV_PAIR_HEADS` | 目的 |
|---|---|---|---|
| accepted | 原 `final_F16_trace_M4` ELF | 不设置 | 保留原四组最快结果的参照 |
| generic | 新统一 ELF | `0` | 同一程序中的旧调度对照 |
| auto | 新统一 ELF | 不设置 | 验证自动配对的增量收益 |

`generic` 与 `auto` 使用同一个 ELF，可以隔离自动选路收益。`accepted` 与
`generic` 是不同 ELF，用于检查整合和工具链重建是否引入回归；两者之间的差异
不能全部归因于算法。

bundle 含原已验收 ELF、新 ELF、SHA256 清单、manifest 和启动脚本。脚本在
运行前核验 ELF，使用干净环境，固定单 worker、原生执行、M4 四项和上下文复用，
关闭量化 KV，不设置 NORMAL_MEMORY 承诺；保留完整 stdout/stderr、logits、
退出码和起止时间。每次使用新输出目录，失败后不自动重试或改走模拟执行。

先由 FPGA 会话确认仍是交接清单对应的位流、时钟、模型和内存条件，再分发
bundle。以下命令只在板上执行，本次本机工作不自动执行：

```bash
sh run_board.sh accepted /qwen3.gguf /tmp/qwen3_prompt.txt 64 /tmp/unified_accepted_01
sh run_board.sh generic  /qwen3.gguf /tmp/qwen3_prompt.txt 64 /tmp/unified_generic_01
sh run_board.sh auto     /qwen3.gguf /tmp/qwen3_prompt.txt 64 /tmp/unified_auto_01
```

先检查一组代表性完整回答的 logits、native/fallback 路径及时间。成立后，再
对原四组输入采用同一上下文、输出长度、缓存准备条件和交错运行次序回归。
不要把输入解析、模型加载等主机观察时间与模型推理时间混为一谈。

验收时分别核对以下内容，不能只看回答文本相同：

- 以完整 logits 和 token 序列检查数值，普通 F16 paired 路径预期不改变逐 head
  累加顺序；出现不同必须保留首个差异，不因为自然语言回答看似相同而放过。
- QBS 的形状、M4 使用和命令工作量保持一致，AKV 的高层 Attention 工作量保持
  一致；AKV 内部 K/V 重放命令应允许减少，不能错误地要求所有 native 计数相等。
- 记录 Prefill、Decode、模型推理总时间与主机观察总耗时，使用各自相同的分母。
- 若位流不具备自动配对需要的 capability，正常回退不是故障，但也不能记为
  paired 路径性能验收。不能仅凭编译符号存在或环境变量缺省认定快路径已执行。
- 新版本通过回归后，再将经审核的软件修改纳入两个仓库的正式交付；不要把
  当前工作区的全部未提交内容一起提交，也不要移动原交付标签。

先前 FPGA 的 1.312x 是完整推理软件收益；本会话 1.440x 是真实 Qwen3
Attention group 的完整 SDK 调用收益。本轮统一版首组结果见开头，不能把不同
比较的倍率相乘、相加或推广成其余模型和输入的结果。

## 5. 利用程度与跨模型边界

本次 Qwen3 每次有 1,528,632 条成功 QBEXEC、576,576 条 M4 命令和 854,074 条
activation-context REUSE；1176 个 Attention 操作执行，包含 1148 个 Decode 和
28 个 Prefill。候选路径没有意外 fallback。这证明主要机制实际使用，但不是物理
计算单元利用率、模型时间占比或理论上限证明。

选路按格式和 tensor contract，不按模型名。QBS 支持九种权重 profile 及受约束
的 MoE 矩阵路径；不意味着全部模型、格式和维度的笛卡尔组合都已验证。
既有跨模型结果的 Host、QEMU 功能与 RTL 切片证据应与本轮板测严格分开。

| 模型或形状 | 当前含义 |
|---|---|
| Qwen3 D128/GQA2 | 本轮首组实际板测；自动配对有小幅增量收益 |
| Qwen2.5 D128/GQA6 | 保留已有六头专用调度，不强行改成三个两头组 |
| TinyLlama、Llama-3.2、SmolLM2 的 D64 多头 | 既有功能/选路证据；新 auto 符合形状条件，未据此声称全部完成新版板测 |
| Phi D96/GQA1、OLMoE D128/GQA1 | 既有 QBS/AKV 支持；没有两个真实共享 head，不适用两头复用 |
| Gemma D256 | QBS 适用的投影保留；GGML Attention 维持 RVV fallback，已有两段 D256 未胜过强 RVV 基线 |

Prefill 两头 PV 和量化 KV 的 Register-PV/Grouped Prefill 不是本轮新 auto Decode
路径，不能由本轮结果证明收益。M8 曾有退化，不是应当无条件打开的闲置能力。
代表性 QBS RTL 切片中 dot-issue/busy 约 87.9%；理想消除所观测到的计算尾端
空隙，完整切片估算仅约 3.5%，这不是实测优化或全局上限。

当前结论是：主要既有机制已被实质利用，尚无已证明低风险且能显著改善端到端
性能的小改方向。保留正确性与收益证据，暂停本轮收益挖掘；不以此宣称所有资源
接近理论满载，也不把支持范围扩展混同于免费的性能提升。
