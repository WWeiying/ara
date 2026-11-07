# 现有 AKV 资源的完整调用优化与交付

## 1. 结论与范围

本轮不修改 RTL，不增加计算阵列、SRAM、接口宽度或队列。改动是在软件调度层
用好已经存在的 paired-head 和 PANEL4 能力，并将经过实测的路径接入
llama.cpp/GGML。QBS 实现保持不变。

当前 SDK 自动入口在真实 Qwen3 Decode 数据上的完整调用由平均 **52,399**
降到 **36,391 cycles**，周期减少 **30.55%**，加速 **1.440 倍**。
这里的完整调用包括 Query 转换、device query、Decode 检查与 plan 创建、
native 执行及最终排空；不包括串口打印和结果检查。

这是一个实际模型数据的 Attention KV-head group 测量，不是整模型的
token/s 或端到端加速比。GGML 已完成实际交叉编译和选路测试，但本轮没有
重新执行完整模型、FPGA 重建、综合或功耗评估。16 MiB L2 仅为仿真容量配置，
没有改变存储接口宽度或延迟模型。

## 2. 为什么原路径仍有可消除的开销

此前的完整调用 profiling 发现，Qwen3 D128/GQA2/137-token 切片的 QK 和 PV
发射侧时间合计占插桩调用的 61.64%。在 generic 路径中，两个 query head
虽然共享一个 KV head，仍分别把相同 K 列和 V 行从 AKV resident context
重放到向量寄存器。数据已经在片内，但重复重放和逐条命令推进仍占用周期。

现有硬件已经可以一次返回四个 K 列；现有汇编也可以让两个真实 query head
共享这些 K 列，以及同一 V 行。本轮先证明这条已有路径有效，再提高主要
运行时的选择程度，而不是继续增加存储或计算资源。

以 D128、两个 query head、137 个有效 token 为例，三个 tile 为 64、64、9：

| 每次调用的工作 | Generic | Paired-head + PANEL4 |
|---|---:|---:|
| FULL / REFILL / RELEASE | 1 / 2 / 1 | 1 / 2 / 1 |
| K 重放命令 | 768 次单列 | 96 次四列 panel |
| V 行重放命令 | 274 | 137 |
| PERF 记录的上下文与重放命令总数 | 1046 | 237 |
| K/V 外部读取 payload | 70,144 B | 70,144 B |
| context 到 VRF 的 K/V 重放 payload | 140,288 B | 70,144 B |
| Query payload / descriptor | 512 B / 64 B | 512 B / 64 B |

这些命令数量不包含 INFO capability 查询及普通 RVV 算术指令。重放 payload
减少不代表数学工作减半：每个 head 仍完成自己的 QK 和 PV，只是不重复搬运
两者共享的 K/V。

## 3. 保留原数值计算顺序

QK 的 paired helper 按维度递增，对 head 0 和 head 1 分别执行 F16 输入、
F32 累加的 widening FMA。处理某个维度的两个 head 后，再进入下一维度。
因此，每个 head 自己的维度累加顺序没有改变。

PV 同样按 token 递增。每个 head 分别将 old scale 和 score 转成 F16，
对自己的 F16 accumulator 执行原来的缩放和 FMA；两个 head 共享一次 V 行
重放，但不共享 accumulator。最终仍归一化为 F32 输出。

本轮没有改为更高精度累加，没有交换 tile 顺序，也没有调整误差阈值。
SDK 新旧归档之间的差异严格限定为两个公开头文件、native C 入口和一个纯
选择 helper，所有计算汇编字节不变。实测同时要求 generic/候选输出逐位
一致、flags 一致，并通过独立 native tile64 reference 与原模型 golden 检查。

## 4. 当前调用接口与选路

新增的接口如下；它们不改变 descriptor、plan 或 workspace 的 ABI：

```c
akv_attention_execute_v2_native_auto(device, plan, workspace);
akv_attention_execute_v2_with_features_native_auto(
    device, plan, workspace, features);
```

`device` 必须来自已有的、经过平台安全准入的 native capability 查询。
可以缓存 device capability，但每次调用仍重新检查当前形状、精度和 VLEN。
选择在第一个 FULL 之前固定；没有跨调用的可变选择状态，也不通过 `setenv`
改变某一次调用的执行方式。

| 条件 | 当前调度 |
|---|---|
| F16、plain scores、VLEN=1024、D64/D96/D128、2–8 个 head，且所需能力完整 | paired-head + PANEL4 |
| 奇数 head | 完整 head 对使用 paired，最后一个 head 使用 generic |
| D128 / 6-head | 保留原六头专用路径，不改成通用两两配对 |
| 缺少 PANEL4 等配对所需能力，但原 AKV 调用本身合法 | 保留原 generic / 专用调度 |
| 只有一个 head | 原 generic 路径 |
| D256 | 原 segmented 路径 |
| softcap、位置偏置、sinks、窗口或 mask 等使 score 不能归一化为 plain | 原 feature 路径，不自动启用 paired |
| 原 AKV 准入就不成立 | 仍由 GGML 原有检查返回普通 RVV fallback |

自动配对还要求 F16 payload、足够的 head/context 容量、token-axis、tail、row-view、
PANEL4、64-token tile，以及对应 D 维度能力。这里没有新增其他 VLEN 的支持承诺。
“generic AKV fallback”和“普通 RVV fallback”不是同一个层级。

旧 `akv_attention_execute_v2_native()` 和带 features 的旧入口保留原来的
`AKV_PAIR_HEADS` 语义：缺省不打开 paired。新 auto API 本身不读这个变量。
GGML 在未设置该变量时使用 cached device 和新 auto API；若显式设置任何值，
则调用旧入口，保持原调试开关行为。例如 `AKV_PAIR_HEADS=0` 仍能选择旧路径。

GGML 仍只由 worker 0 执行 native 调用，原有 `context_mutex` 继续覆盖完整
FULL/REFILL/compute/RELEASE 生命周期。执行开始后若返回错误，不重新执行
generic/RVV 来掩盖部分执行。平台 native opt-in、内存适用条件和上下文所有权
要求均未取消；本轮仿真不构成板上 NORMAL_MEMORY 准入证明。

## 5. 实测性能

每组采用同一 ELF 内的 Generic/Candidate/Candidate/Generic 顺序。四个数
均为未插桩 SDK 完整调用周期，最终 drain 已计入；各组之间不混用分母。

| 测试 | Generic 两次 | 候选两次 | Generic 均值 | 候选均值 | 周期减少 | 加速比 |
|---|---|---|---:|---:|---:|---:|
| 首轮 Qwen3 D128/H2/T137，原 opt-in paired | 52,899 / 52,297 | 37,522 / 37,478 | 52,598 | 37,500 | 28.70% | 1.403× |
| 首轮 SmolLM2 D64/H3/T5，原 opt-in paired | 15,524 / 14,691 | 14,145 / 14,302 | 15,107.5 | 14,223.5 | 5.85% | 1.062× |
| 当前 Qwen3 D128/H2/T137，call-local auto API | 52,677 / 52,121 | 36,203 / 36,579 | 52,399 | 36,391 | 30.55% | 1.440× |

两份 Qwen3 数据均选择真实 KV head 0 及其 query heads 0、1，capacity=256，
有效前缀 137；SmolLM2 选择真实 KV head 0 及其 query heads 0、1、2，
capacity=256，有效前缀 5。后者的原始 capture 没有独立 source receipt，
因此保留 `source_receipt_verified=false`，通过固定的原始 tensor/metadata
哈希与独立数值 reference 核查，不把它描述为新增完整模型运行。

推广门槛预先固定为：主形状至少减少 5% 周期，第二真实形状也有正收益，
候选的两个样本均快于 generic 的两个样本，平均收益超过最大的同臂波动。
当前 auto API 的平均收益为 16,008 cycles，最大同臂 spread 为 556 cycles。
短 SmolLM2 点的收益较小，不能据此声称所有短上下文都获得相同加速。

首轮 opt-in 和当前 auto API 属于不同软件 ELF。不能把两组均值的差全部
归因于某一条优化；已证明的结论是各自同 ELF 的配对收益。auto API 在源码上
消除了额外的配对 capability 查询，但跨 ELF 的代码布局也可能影响周期。

两轮 Qwen3 均检查了 1024 个完整输出值，generic/候选逐位相同，且相对独立
native tile64 reference 的最大绝对误差为 0。相对模型 capture golden 的
最大绝对误差为 0.0009320676，沿用原阈值 `0.003 + 0.02*abs(golden)`。
FCSR 均为 3，VCSR/VSTART 均为 0；这里的 3 是合法的 underflow/inexact sticky
flags，不是失败。SDK 不清零调用方 CSR，清零只发生在配对测量固件中。

## 6. 当前 SDK 的边界与回退验收

以下四组是从既有 Qwen2.5 capture 派生的功能边界，不是四个新模型。
每组执行 OFF/AUTO/OFF，比较整个 output buffer、flags、输入与 guard。

| D / heads / tokens | AUTO 行为 | 三次 native 命令数 | 结果 |
|---|---|---|---|
| 64 / 3 / 1 | 一个 head 对 + 奇数尾 head generic | 197 / 84 / 197 | PASS |
| 96 / 3 / 65 | 64+1 两个 tile，D96 尾部与奇数 head | 774 / 373 / 774 | PASS |
| 128 / 6 / 7 | 保留原六头专用路径 | 137 / 137 / 137 | PASS |
| 128 / 2 / 64 | AUTO 的局部 device 副本关闭 PANEL4，正确回退 generic | 386 / 386 / 386 | PASS |

共 12 次调用、3968 条 native 命令、4 条 INFO。Vector trace 中还包含 12 条
D96 preservation maintenance 微操作，因此 raw custom allocation 为 3980。
这些不是额外执行的模型算子。检查器同时核验维护三元组、VID 生命周期、
架构 start/retire、实际 ELF PC/指令及命令计数，不能简单按 `arch_seq` 去重。
边界测试保留非零 VCSR=5，确认调用不破坏调用方的 sticky CSR 状态。

另有纯策略矩阵 185,760 个组合通过；旧准入矩阵 100,620 个断言、24,576 个
调度组合通过。实际 GGML helper 在旧 SDK、新 SDK、关闭新宏、emulation 和
显式 override 等 12 个编译/执行组合中通过。Host 测试不替代 RTL 数值验收。

普通 RVV 与 QBS 没有代码变化；最终复核同一镜像已有的 RVV VADD 和真实 Q6
完整调用 PASS 证据及其 pins。它们是重新核验的既有代表点，不冒充本轮重跑。

## 7. 检查器问题与证据保留

首轮两个 worker 的原始报告仍保持 FAIL，没有覆盖或重新标成 PASS：

- SmolLM2 的旧 parser 把 VCS 命令横幅里的 `+AKV_PERF` 当作未知计数器。
  后继审计只接受与真实启动命令逐项一致的一条横幅，仍拒绝其他未知/损坏记录。
- D96 的旧 vector checker 假定每个架构标签只能有一次 backend allocation。
  frozen dispatcher 会让内部重排微操作继承原指令标签。后继审计严格验证
  六个 D96 维护三元组、完整架构退休与 ELF 对应，不忽略任意重复。

两次后继审计均重新执行独立 UVM/protocol 检查并验证所有原 source/image/ELF
pins；没有重跑 VCS、改 RTL、修改原日志或放宽数值阈值。当前 SDK 的两路新
VCS worker 则直接以完整 gate 得到 PASS，不依赖上述失败 worker 的重新标记。

GGML 首次 clean-archive 编译还发现：已提交 CMake 缺少 runtime 的严格浮点
选项。仅将现有工作区中相应 9 行 `-fno-fast-math -ffp-contract=off` 纳入版本，
未吸收其他量化 KV 扩展。第二次交叉编译通过，实际编译 36 个 translation units，
同时确认 adapter 引用、canonical SDK 定义了两个 auto API。

## 8. 固定版本与复现入口

| 内容 | 版本 |
|---|---|
| Ara 分支 | `ara_dsa`，路径 `/home/wangwy/openproject/ara_dsa` |
| SDK 实现提交 | `b7c9e6c3c1f8c5e469c130f46ec5bbfaf37a55d1` |
| llama.cpp 分支 | `qbs-activation-context`，路径 `/home/wangwy/llama/llama.cpp` |
| GGML 完整交付提交 | `03959acc0f649f9071668d5b72888284e4676d2b` |
| 共同 VCS 镜像 SHA256 | `3ed8bc6b761d49664162b9f3b45e525e5c051923618950cbdb2b38ea403486a6` |
| 镜像配置 | 4 lanes、VLEN=1024、128-bit AXI、16 MiB simulation L2、shared integer multiplier、原 FMA |

结果根目录为 `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/`：

| 证据 | 相对目录 / 文件 |
|---|---|
| 首轮 Qwen3 配对 PASS | `akv_pair_qwen3_vcs_20261107_01/result.json` |
| 首轮 SmolLM2 独立后继审计 | `akv_pair_smollm_audit_20261107_01/result.json` |
| 首轮边界独立后继审计 | `akv_pair_boundary_audit_20261107_01/result.json` |
| 初始收益准入决定 | `akv_pair_initial_decision_20261107_01.json` |
| 当前 auto API 配对 PASS | `akv_pair_integration_vcs_20261107_01/result.json` |
| 当前 auto API 边界/回退 PASS | `akv_pair_integration_boundary_vcs_20261107_01/result.json` |
| 实际 GGML 交叉编译 | `akv_pair_ggml_build_20261107_02/result.json` |
| 最终逐项验收 | `akv_pair_acceptance_20261107_01/result.json` |

构建与运行入口在 `verification/performance/akv_pair_eval/`。`integration/`
是当前 Qwen3 auto API 配对测试；`integration_boundary/` 是当前边界/回退测试。
`build_ggml.py` 使用固定 Git 归档，而不是直接编译存在未提交改动的目录。
每次需指定不存在的新输出目录；不要复用旧 run 目录。

```bash
python3 -B verification/performance/akv_pair_eval/integration/build.py \
  --output "$OUT/akv_pair_integration_build_20261107_retest"

python3 -B verification/performance/akv_pair_eval/integration/run.py \
  --build "$OUT/akv_pair_integration_build_20261107_retest" \
  --output "$OUT/akv_pair_integration_vcs_20261107_retest"

python3 -B verification/performance/akv_pair_eval/integration_boundary/build.py \
  --seal-ready --output "$OUT/akv_pair_integration_boundary_build_20261107_retest"
```

上例中的 `OUT` 为本节结果根目录。长运行由直接持有 worker 的 systemd 用户
服务管理；每次 VCS 限定三小时，本轮五路实际仿真均约 14–20 分钟完成。
原有未提交文件被保留，尤其未将未交付的 AKV 汇编纳入任何构建归档。
本轮提交了技术节点，未变更 FPGA delivery tag，也未推送远程。
