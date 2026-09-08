# QBS/AKV 通用性实施记录

基线：`5b914d74`，保留引用 `qbs-akv-portability-base-20260907`。
本轮不运行综合，不修改既有实验结果或论文文件。

## 验收原则

功能、数值契约、原生指令执行、RTL 周期分别验收。Host 通过不等于 VCS
通过；有公共 adapter 不等于完整第二运行时已经接入。未测性能的新增路径
不得自动替代已有快速路径。现有指令编码及默认路径保持兼容。

| 项目 | 当前实现工作 | 验证状态 |
| --- | --- | --- |
| 1 格式 | 三个数学格式族；分组整数到现有编码的精确权重转换 | 56 组格式组合通过 |
| 2 尺寸 | 公共 AKV batch/GQA 分组；保留 QBS M/N/K 分块 | AKV 192 组 shape/layout 组合通过；QBS 原有规划器通过 |
| 3 布局 | batch/head/token stride、显式容量、跨组别名及溢出检查 | 包含在上述 192 组及拒绝路径测试中 |
| 4 Attention 功能 | mask/window、softcap、位置 bias、sink；复用原有算术 | Host、GGML/QEMU、6 组 native VCS 及额外非零组合均通过 |
| 5 外部接口 | 通用 C API、实际 ONNX Q/DQ MatMul 对照、GGML 可选扩展 | ONNX 18 组通过；GGML 18 组通过，不等于完整 ORT EP |
| 6 能力/数值契约 | 查询失败清空设备；拒绝不兼容格式/版本 | Host/ABI 检查、当前 QEMU 原生 QBS 契约通过 |
| 7 状态 | GGML 完整 AKV 生命周期互斥；公共接口区分 preflight/执行失败 | 两个并发 GGML 图及 RTL handoff 通过；不含 OS 抢占 |

## 1. 格式通用化没有改变硬件 profile

新增 `software/qbs/include/qbs/qbs_format.h` 和 `src/qbs_format.c`。
软件按数学表达将九种精确编码归入三类：

| 格式族 | 数学含义 | 当前对应编码 | 本轮新增能力 |
| --- | --- | --- | --- |
| 分组整数 | `w = s_g * (q - z_g)` | Q4_0/Q5_0/Q8_0 | 外部分组整数的精确加载期转换 |
| 分层整数 | block scale 与 subgroup scale/correction 共同恢复权重 | Q2_K 至 Q6_K | 统一分类，保留原有精确 block ABI |
| 码本 | `w = s_g * table[q]` | IQ4_NL | 统一分类，不声称支持任意码本 |

输入接口显式描述 bit 数、signed/unsigned、group、scale、zero point、row stride
和缓冲区容量。目标 profile 必须由调用者指定，不能仅凭 INT4 名称猜测字节布局。
支持 2..8 bit、32/64/128/256 元素分组，K 必须为组长的整数倍。
scale 必须能由有限 F16 精确表示，`q-z` 必须落在目标有符号整数范围内。

例如，外部一个 group64 INT4 block 使用 scale=0.25、zero point=8，
整数值 0..15 对应权重 -2..1.75。转换器把它拆成两个 group32 block，
重复保存同一个 scale，并按现有 Q4_0 nibble 顺序重排；权重数值不变。
scale=0.1 不能被 F16 精确保存，此接口明确拒绝，不偷偷舍入。
6-bit 输入可以显式转为 Q8_0，但会增大存储量，不是免费加速。

**权重转换无损不等于整个算子逐位等价。** 激活量化、FP 累加顺序以及运行时
原本使用 W4A16 还是 W4A8，都要单独核对。转换器不做 activation 量化。
不支持的 F32 scale、部分尾组、GPTQ/AWQ 特殊 packing 仍需 adapter 或 fallback。

## 2. 尺寸和布局通过软件分块处理

`akv_decode_problem_t` 表示 Q/O `[batch, query_head, D]`、
K/V `[batch, kv_head, token, D]`。D 连续，其他轴使用显式字节 stride。
K/V 的 head/token 两轴可以互换，允许行 padding；mask 可跨 batch 共享。
所有输入/输出必须提供真实可访问容量，执行前检查整个输出与所有输入的重叠，
而不只是检查当前一组。

大 GQA 不要求增加硬件 context。例如 2 个 KV head、每个对应 17 个 Query head，
每个 KV head 分成 `8+8+1`，一个 batch 共 6 组，2 个 batch 共 12 组。
每组最多仍使用已有的 8 个 Query 槽。KV 末尾 1..63 个 token 由原 tail 处理。

这是公共运行时能力。GGML opt-in adapter 当前接入大 GQA，但其 batch>1、D256
生产选择仍不开放。D256 公共两段实现继续保留，不能用 Host 通过代替性能门槛。
本接口不把不连续物理页拼成“一个大 stride”，不支持 paged KV。

## 3. Attention 数学、选择和性能边界

新增 `akv_features.h`/`akv_features.c`，原生函数与 F32 数学 oracle 使用同一份
score 修饰定义。有效位置的计算顺序为：

```text
dot(Q,K) * scale
  -> 可选 softcap * tanh(score / softcap)
  -> 可选 slope[head] * (key_position - query_position)
  -> 加 F16 mask * mask_scale[head]
  -> online Softmax / PV / 输出归一化
```

mask 为负无穷或位置在 window 外时直接排除。window 使用绝对位置，不能在每个
64-token tile 重新从零计数。sink 是额外的 denominator score，Value 为零；
不是额外读取一条真实 KV。首个 tile 全遮蔽时直接置零权重，避免 `-Inf - -Inf`
产生 NaN；全行遮蔽且无 sink 时返回全零。

GGML ALiBi 的含义是对它已构造好的 mask 按 head 缩放，adapter 不再额外添加
一次位置 slope，避免重复施加 bias。测试覆盖 max_bias、softcap、mask holes、
leading masked tile 和 sink 组合。

`GGML_RISCV_AKV_PORTABLE=1` 才开放这些新增 Decode 场景，默认 selector 不扩大。
softcap 等仍使用软件/RVV 运算，不新增 RTL 单元。功能覆盖扩大不等于速度必然
增加：额外标量处理、head 分组重读 KV 都有开销，真实模型的性能仍需单独测量。
普通 `akv_attention_execute_v2_native` 保留为 NULL-feature 调用。

F32 oracle 使用标准 exp 和 F32 Value 累加；native 沿用 F16 Value 累加及 RVV
exp 近似。因此 GGML 对照是带容差功能测试，不是 bit-exact/cycle 模型。
oracle 须禁用 fast-math；native 调用前须保证 Q/K/V 有限、mask 有限或为负无穷。

## 4. 第二运行时与并发边界

`software/qbs/tests/test_onnx_portability.py` 构造、保存并重新读取真实 ONNX
Q/DQ MatMul，使用 ONNX Runtime CPUExecutionProvider 执行，再将模型中的整数、
scale、zero point 送入公共转换器/QBS planner/canonical instruction reference。
没有写一个“仿 ONNX”的自算结果来替代运行时结果。

18 组为 4/5/8 bit 各 6 个 shape：

| M | N | K | group | QBS 命令数/组 | 最大绝对差 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 5 | 64 | 32 | 1 | 0 |
| 2 | 33 | 128 | 64 | 2 | 0 |
| 3 | 35 | 256 | 128 | 2 | 0 |
| 5 | 17 | 256 | 256 | 2 | 0 |
| 9 | 5 | 64 | 64 | 3 | 0 |
| 2 | 5 | 8256 | 64 | 4 | 0 |

输入使用显式 INT8 Q/DQ activation 和能精确表示的 scale；该零误差不推广到
W4A16/任意浮点模型。没有注册原生 ONNX ExecutionProvider，也没有跑完整 ONNX 模型。

两个 GGML 图即使各自只由 worker-zero 发命令，仍可能并发。adapter 现在用进程内
mutex 包住完整 FULL/REFILL/计算/RELEASE，而不是只锁单条命令。
QBS 原有 generation/reservation 管理继续保留。公共 Decode callback 失败统一返回
EXECUTION，哪怕第一次 callback 失败，也不能假设完全没写输出并偷偷 fallback。
这不解决 OS 抢占、线程迁移、多进程独占或 context save/restore；部署这些场景需要
额外的调度/驱动契约。

## 5. 验证记录和复现

| 检查 | 实测状态 | 范围 |
| --- | --- | --- |
| QBS make/CTest | PASS | 原 runtime、56 组新转换、拒绝及能力查询失败 |
| AKV make/CTest | PASS | 原 runtime、192 组 batch/布局/尾块及 features |
| ABI 生成一致性 | PASS | `gen_qbs_abi.py --check`、AKV ABI contract |
| ONNX Runtime | 18/18 PASS | onnx 1.17.0、onnxruntime 1.19.2；原始结果 `software/qbs/build/onnx/results.json` |
| GGML/RVV QEMU | 18/18 PASS | D64/KV65/GQA3,9,17；6 组功能组合；两个并发图；两条 fallback；旧路径 |
| 当前 QBS QEMU 原生契约 | PASS | M5/M8、tail、访问故障、RNE、fflags、activation context |
| native AKV VCS + handoff | PASS | 6 组定向检查；4 条 QBS、10 条 AKV 和普通 RVV 交接，traps=0 |
| native 非零 score/PV 组合 | PASS | 非零 Q/K、非恒定 V 对照 F32 oracle，64 个输出均满足绝对差 <=0.004；随后 handoff 再次通过 |
| CMake 安装后独立链接 | PASS | `find_package(akv_runtime)`、`akv::runtime`、新公共头文件 |
| GCC 静态分析 | PASS | `-fanalyzer -Werror` 检查三个新增运行时 C 源文件 |
| ASan/UBSan | 未完成 | 系统链接器缺少 libasan/libubsan；普通 Host/CTest 已通过 |
| 完整模型 RTL 速度、综合/PPA | 未测 | 单算子 VCS 周期见第 6 节，不以功能结果推出整个模型速度或面积 |

GGML 对照的最大绝对差为 `5.11413e-5`，门限 `0.002`。
原始日志：`/tmp/qbs-akv-portable-ggml-20260907/final_run/qemu.log`。
当前 QBS QEMU：`/tmp/qbs-current-qemu-20260907/qemu-10.2.0-build/qemu-system-riscv64`；
契约结果：`/tmp/qbs-current-contract-20260907.log`。
旧 `verification/qbs/qemu/build/.../qemu-system-riscv64` 内置 arch-v1/M4，不能用于
当前 arch-v3/M8 契约；它未被覆盖。

VCS 入口 `verification/akv/run_portability_rtl.sh` 会重新编译独立 simv、复制 ELF、
保存软件快照/哈希，串行运行 native feature smoke 和 QBS/AKV/RVV handoff。
已通过目录：`hardware/qbs_akv_portability_runs/baremetal_stdio_20260907/`。
最终完整回归目录：`hardware/qbs_akv_portability_runs/nonzero_final_20260907/`，
`status=PASS`、`exit_code=0`；包含 6 组原生定向测试、额外非零组合和交接回归。
`status`、`exit_code`、`portable/run.vcs.log` 和 `handoff/run.vcs.log` 是完成依据。
前一次 `checked_20260907_0825` 记录保留：新测试误用 libc printf，在
`0x80006c18` 的 `_fstat/ecall` 陷入裸机未提供的系统调用。已仅修正测试程序为项目
`printf.h`；没有据此改 RTL。

```bash
make -C software/qbs check
make -C software/akv check
bash verification/akv/run_contract_test.sh
python3 scripts/gen_qbs_abi.py --check

# 已准备好 cross-compiled GGML 后执行，使用普通 RVV QEMU + AKV oracle。
AKV_GGML_BUILD=/tmp/qbs-akv-portable-ggml-20260907 \
  bash verification/akv/run_ggml_portability_test.sh

# 独立长任务；每次默认使用新的时间戳目录，不覆盖旧结果。
tmux new-session -d -s akv_portable \
  'cd /home/wangwy/openproject/ara_dsa && bash verification/akv/run_portability_rtl.sh'
```

外部 llama.cpp 改动位于 `ggml/src/ggml-cpu/arch/riscv/akv.cpp` 和同级构建配置。
基线为 `f896237df65c8f5d5101d65acfc500e194127a14`，配套 patch 保存在
`software/akv/integrations/llama-cpp-portability.patch`，不会只留在外部软链接目录中。
本轮没有更改 RTL、指令编码、已有权重格式、论文或原实验结果。

本轮解决了七个方向的公共接口及第一批实现，不等于下面这些扩展也已经完成：
完整 ONNX/ExecuTorch 原生后端、任意量化格式、分页 KV、所有 D/stride 的高效路径、
GGML 多 batch、OS 抢占/迁移/跨进程 context 管理，以及完整模型的 RTL 速度。
这些仍需独立工作，不能从当前功能回归推导出来。

## 6. 真实模型覆盖与同数据性能闭环

本阶段在七项公共接口实现之上，检查真实模型是否进入预期路径，以及新增通用处理
是否拖慢原有输入。不修改 RTL、ISA、context 容量，不运行综合/PPA，不覆盖旧实验。
接口冻结提交为硬件仓库 `c824aae2`、私有 llama.cpp 仓库 `8ed9403e3`。
后续改动的完整软件差异、ELF 和模拟器哈希保存在各次运行目录中。

### 6.1 模型和判据

| 模型 | Attention 拓扑 | 本阶段检查内容 | 明确不宣称的能力 |
| --- | --- | --- | --- |
| Qwen2.5-1.5B-Instruct Q4_K_M | D128，12 Q heads / 2 KV heads，GQA6 | 原有 Decode 是否保持数值与性能 | 不把 3-token 检查解释为长篇生成质量评测 |
| Qwen3-1.7B Q4_K_M | D128，16 Q heads / 8 KV heads，GQA2 | 不同头数与分组的模型执行 | 本轮未重新做 Qwen3 的完整 RTL 模型执行 |
| Refact-1.6B-fim Q4_K_M | D64，32 Q heads / 1 KV head，MQA32，ALiBi max_bias=8 | 大 GQA 分组及真实 ALiBi mask；原 selector 会拒绝的路径 | Prefill ALiBi 仍回退；不是更新模型质量排名的比较 |
| Gemma3-1B Q4_K_M | D256，4 Q heads / 1 KV head | 性能不合格的 D256 路径应继续 fallback | 不为提高覆盖率而强行启用较慢的 D256 组合 |

Refact 的官方配置包含 multi-query 和 32 个 Query heads，当前
`llama.cpp/src/models/refact.cpp` 设置 ALiBi max_bias=8；它用于区分 GQA 和位置
偏置机制，不是用模型名称筛选硬件。
模型配置来源：<https://huggingface.co/refactai/Refact-1_6B-fim/blob/main/config.json>。
GGUF 固定为 `oblivious/Refact-1.6B-fim-GGUF` 的
`b7f7deb2cdb47de16f808d9c334b9b34e10543f6` 修订，文件 SHA-256：
`241741c3bb51c99d53ecb2e1891b66e8058e99876e07e82d21f050deb2f090c9`。

QEMU 模型检查在同一任务内运行 RVV、QBS_ONLY、QBS_AKV_V2 三种配置，
prompt 为 `The answer is`，采集 3 份 logits，包含 Prefill 后的首份和两次 Decode。
QBS 使用当前 arch-v3/M8 自定义指令 QEMU；AKV 使用 GGML 功能执行器，
不是 QEMU 中新增的逐周期 AKV 硬件模型。
门限不放宽：token/Top-1 相同，最大 KL <=0.02，最小 cosine >=0.98，
最小 Top-5 overlap >=0.8；最大绝对差单独报告。

短 prompt 不满足 Prefill 的最小规模门限。因此这里要验证的是 Decode 及可靠回退，
不能据此宣布“Prefill 不支持”，也不能宣布“所有 Attention 都已加速”。
每次拒绝现在按 Decode/Prefill 及原因记录，所有候选必须等于执行数与回退数之和。

### 6.2 同一份真实数据的 VCS 结果

配置均为 4 lanes、VLEN=1024、simulation-only L2=16 MiB，复用同一 simv。
下列数字是算子本体的实际硬件周期，不是 QEMU wall time 或模型级外推。
Qwen 两点来自既有真实模型 KV16/KV128 capture；Refact 来自真实 host llama.cpp
层 0 Decode，保存 Q、K、V、mask、op 参数和原输出，未用随机矩阵代替。

| 实际算子 | RVV cycles | 原 AKV cycles | 通用 AKV cycles | 通用 AKV / RVV 加速 | 相对原 AKV 周期增加 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen2.5，D128/GQA6，KV16，12 heads | 129219 | 35473 | 36348 | 3.555x | 2.47% |
| Qwen2.5，D128/GQA6，KV128，12 heads | 771502 | 105503 | 108420 | 7.116x | 2.76% |
| Refact，D64/MQA32，KV16，32 heads，ALiBi | 291471 | 不支持 | 143217 | 2.035x | 不适用 |

三组都对完整输出检查通过，`mismatches=0`；通用 AKV 日志必须出现
`ATTENTION_DISPATCH native_v2=1 portable=1`，不允许实际 fallback 却记为快速路径。
Refact 的四组 Query 会分别装载 K/V，所以“可以分组”并不代表跨组 K/V 读取免费。

| Qwen 点 / 实现 | 退休向量指令 | 退休标量指令 | 共享 VLSU AR bytes |
| --- | ---: | ---: | ---: |
| KV16 原 AKV | 2792 | 8712 | 44992 |
| KV16 通用 AKV | 2792 | 9135 | 44992 |
| KV128 原 AKV | 6818 | 17750 | 183936 |
| KV128 通用 AKV | 6818 | 19741 | 183936 |

这说明当前额外代价主要留在公共参数检查与分组调度：向量指令数和外部 AR 量未增加。
不能说通用化完全零开销。默认 `GGML_RISCV_AKV_PORTABLE` 仍关闭，原有模型可继续
使用原 selector；新增特性按实际收益选择，不无条件替换所有 Attention。

初测发现空 feature 对象也触发逐 token 的标量 score 处理，还计算未启用 ALiBi
的幂函数。KV16/KV128 因此分别用了 52179/215737 cycles。
静态路径与分阶段计数相符后，仅修改共享软件：关闭全部特性且 mask 全零时，
回到原向量化 score 路径；ALiBi 系数按启用位计算。对应周期降至表中数值。
mask holes、有限 bias、window、sink 保持完整路径，未靠丢弃语义提速。

### 6.3 数值检查的分层

公共 `with_features_reference` 是 F32 数学 oracle，而原 GGML Decode 使用 F16
Value accumulator。两者即使数学表达相同，也不是可随意交换的模型级数值实现。
初次 Refact QEMU 路径误用了前者：QBS 与 RVV logits 完全相同，但 AKV 与 QBS_ONLY
最大 logits 差为 2.77442551，第 3 个 Top-1/token 不同，严格检查判为失败。
该失败记录保留，不能因 KL=0.0134171788 小于门限就宣称通过。

GGML 功能执行器已改为沿用原 F16 累加，在 score 上应用特性，并在 F32 输出阶段
按 GGML 顺序处理 sink。数学 oracle 仍保留为独立检查工具。
这没有改变原生 RTL 的算术或硬件接口；原生算法的 tile/reduction/exp 舍入仍需
实际 VCS 误差验证，不能用功能执行器代替。

本阶段已通过的辅助检查包括 192 组 Host 布局/shape 组合、特性及错误输入测试，
18 组 GGML 特性/两图并发测试，以及 7 组 native 定向、非零组合和
QBS/AKV/普通 RVV 交接测试。

2026-09-07 最终四个模型均通过严格检查。下表中的 logits/token 比较是
QBS_AKV_V2 对 QBS_ONLY，不是宣称原生 RTL 对整模型逐位相同。

| 模型 | Decode 已执行/候选 | Prefill 回退 | 三份 AKV logits 最大绝对差 | token 相同 |
| --- | ---: | --- | ---: | --- |
| Qwen2.5-1.5B | 56/56 | 28 次，短 prompt 规模门限 | 0 | 是 |
| Qwen3-1.7B | 56/56 | 28 次，短 prompt 规模门限 | 0 | 是 |
| Refact-1.6B | 64/64 | 32 次，ALiBi 未接入 Prefill 快速路径 | 0 | 是 |
| Gemma3-1B | 0/52 | 26 次，短 prompt 规模门限；Decode 因 D256 回退 | 0 | 是 |

四个模型均确认 QBS 进入原生自定义指令 QEMU 路径，选中全部适用的量化矩阵候选，
`emulated_commands=0`。这仍不代表非矩阵算子都被 QBS 加速。
三个快速路径模型的 Decode 调用覆盖为 100%；这个比例不是整模型时间覆盖率。
本轮不增加生成长度、不更换 prompt 来规避 Refact 的数值首错，修正后仍使用同一输入。

大 GQA 的统计也已修正：`groups` 表示实际 Query 分组数，不再默认等于 KV head 数。
例如 Refact 的一个 MQA32 调用分四组，K/V payload 的重读因子为 4，不能记成 1。
带通用特性的模型只生成 dynamic coverage；禁止直接套用原 Qwen GQA6 的旧周期曲线。
汇总脚本新增分组/重读量测试，连同已有模型归因测试共 20 项通过。

### 6.4 复现和结果语义

入口：`verification/akv/run_portability_stage2.py`。
`prepare` 下载并校验固定模型、制作只读磁盘；`build` 创建独立 GGML；`models`
执行三路模型功能对照；`capture` 保存真实层输入；`rtl_base` 执行 Qwen 两个 KV
点的三种实现；`rtl_refined` 只重测修正后的通用实现；`rtl_refact` 比较 Refact。
运行目录存在时拒绝覆盖。VCS 每点最多 10800 秒。

```bash
# 使用新目录，分阶段执行；长任务放入 tmux。
python3 verification/akv/run_portability_stage2.py prepare --output hardware/NEW_RUN
python3 verification/akv/run_portability_stage2.py build --output hardware/NEW_RUN
python3 verification/akv/run_portability_stage2.py models --output hardware/NEW_RUN
python3 verification/akv/run_portability_stage2.py rtl_base --output hardware/NEW_RUN
python3 verification/akv/run_portability_stage2.py capture --models refact_1p6b_q4km --output hardware/NEW_RUN
python3 verification/akv/run_portability_stage2.py rtl_refact --output hardware/NEW_RUN

python3 verification/akv/summarize_portability_stage2.py \
  --run-root hardware/qbs_akv_portability_stage2_20260907_r2 \
  --run-root hardware/qbs_akv_portability_stage2_20260907_r3 \
  --run-root hardware/qbs_akv_portability_stage2_20260907_r4 \
  --output hardware/qbs_akv_portability_stage2_20260907_summary
```

实际目录 `r2` 保存初测，`r3` 保存去除空特性开销后的数据，`r4` 保存 Refact
功能执行器的数值复测。旧目录不删除、不拼接成一个貌似全新的运行。
`rtl.csv` 保存同数据/同 simv 对照，`rtl_all_metrics.csv` 保存全部 LLM_PERF phase
字段和 AKV command 字段，`models.json` 保存分配置覆盖、数值及回退原因。
背景收尾通过 pidfd 等待指定任务退出后自动严格复核、汇总，不持续轮询仿真。

几个统计边界必须保留：

- `fp_issue_activity = fp_exec_lane_fires / (monitor_cycles * lanes)` 表示 FP 单元接收
  操作的活动比例，不是峰值 FLOP 利用率或“每个元素都在有效计算”的比例。
- `axi_ar_bytes` 位于正常 VLSU/QBS/AKV 共用 AXI 出口，已包含 AKV 读请求；
  不能再加 `akv_q_external_bytes + akv_kv_external_bytes`。
- AKV Q/KV external bytes 来自 read-data 接收时的 strobe popcount，表示 payload；
  不含 descriptor。`replay_bytes` 是内部递送量，不是外存读取量。
- phase 行重复保存整次运行的 AKV command totals，不应跨 phase 再求和。
- `kernel_cycles` 与 monitor cycles 包含不同的标记开销；派生比例使用相应分母。
- 旧脚本在运行期间编辑导致收尾解析失败的记录，保留 worker 的 FAIL，只在完整
  PASS/零 mismatch/正常结束日志重新核实后标记 `PASS_REVALIDATED`，不是重跑。
- 模型日志重查只收集 dynamic coverage，不依赖旧的周期校准 CSV；不修改数值门限。
- 完成情况按明确选择的最新 cohort 判断；旧失败仍展示，不用旧 PASS 替换新 FAIL。

本阶段最终收尾为 `r4/finalize.status.json: PASS`。选用 Qwen2.5/Qwen3/Gemma 的
`r3` 模型结果、Refact 的 `r4` 模型结果，原生性能使用 `r2/r3` 同数据对照。
小型结果快照纳入 `verification/akv/results/portability_stage2_20260907/`，
原始日志/ELF/大型编译产物仍留在独立运行目录，不加入 Git。

## 必须保留的边界

- 通用格式族不等于任意变体已被硬件支持。当前转换的目标仍是已实现的
  profile；分层与码本保留原生精确编码。
- 权重值不变不等于外部矩阵计算逐位一致。activation 量化、分组 FP 累加顺序
  均属于算子数值契约，不能静默改变。
- 任意 lane/VLEN、分页 KV、系统级抢占/恢复是独立扩展，不能靠移除检查完成。
- D256 原生组合已在有限短点功能通过，但没有默认准入。后续 D256 共享递送将
  同仿真器 KV17 从 47,393 降至 30,255 周期，仍未达到强 RVV 的 1.2x 门槛；
  KV140 又暴露两条 tiled 路径共有的 F16 舍入顺序边界。详见
  [D256 实测与边界](akv_d256_efficiency.md)，不得解释为全部长上下文已经通过。
- 有限的功能回归可以先完成；超过十分钟的 VCS 必须隔离后台运行，不持续轮询。
