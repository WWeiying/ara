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
| 本轮模型速度、综合/PPA | 未测 | 不以功能结果推出加速比或面积数字 |

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
GGML 多 batch、OS 抢占/迁移/跨进程 context 管理，以及新增路径的真实模型速度。
这些仍需独立工作，不能从当前功能回归推导出来。

## 必须保留的边界

- 通用格式族不等于任意变体已被硬件支持。当前转换的目标仍是已实现的
  profile；分层与码本保留原生精确编码。
- 权重值不变不等于外部矩阵计算逐位一致。activation 量化、分组 FP 累加顺序
  均属于算子数值契约，不能静默改变。
- 任意 lane/VLEN、分页 KV、系统级抢占/恢复是独立扩展，不能靠移除检查完成。
- D256 原生组合已功能通过但性能不合格，不自动开启。
- 有限的功能回归可以先完成；超过十分钟的 VCS 必须隔离后台运行，不持续轮询。
